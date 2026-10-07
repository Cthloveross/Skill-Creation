"""Reusable helpers for SEC Form 13F EDGAR bulk-data analysis.

All functions are task-independent: callers pass the quarter directory and the
search/aggregation parameters at runtime. No instance answers are hard-coded.
"""
import csv
import os
import re
import sys
import zipfile
from difflib import SequenceMatcher

csv.field_size_limit(min(sys.maxsize, 2**31 - 1))


def ensure_extracted(zip_path, dir_path):
    """Return a directory that contains the quarter's TSV tables.

    If dir_path already has a COVERPAGE table, use it. Otherwise extract the
    zip into dir_path. Raises FileNotFoundError if neither is available.
    """
    if dir_path and os.path.isdir(dir_path) and find_file(dir_path, "COVERPAGE.tsv"):
        return dir_path
    if zip_path and os.path.isfile(zip_path):
        target = dir_path or (zip_path[:-4] if zip_path.endswith(".zip") else zip_path + "_x")
        os.makedirs(target, exist_ok=True)
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(target)
        return target
    if dir_path and os.path.isdir(dir_path):
        return dir_path
    raise FileNotFoundError(
        "No 13F data found. Looked for folder %r and zip %r" % (dir_path, zip_path)
    )


def find_file(root, filename):
    """Walk root and return the first file whose basename matches filename
    (case-insensitive). Returns None if not found.
    """
    want = filename.lower()
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            if f.lower() == want:
                return os.path.join(dirpath, f)
    return None


def require_file(root, filename):
    p = find_file(root, filename)
    if not p:
        raise FileNotFoundError("%s not found under %s" % (filename, root))
    return p


def _open(path):
    return open(path, "r", encoding="utf-8-sig", newline="")


def load_coverpage(quarter_dir):
    """Return list of dicts: {name, accession, isamendment} from COVERPAGE.tsv."""
    path = require_file(quarter_dir, "COVERPAGE.tsv")
    rows = []
    with _open(path) as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        fields = {k.upper(): k for k in (reader.fieldnames or [])}
        name_k = fields.get("FILINGMANAGER_NAME")
        acc_k = fields.get("ACCESSION_NUMBER")
        amd_k = fields.get("ISAMENDMENT")
        for r in reader:
            rows.append({
                "name": (r.get(name_k) or "").strip(),
                "accession": (r.get(acc_k) or "").strip(),
                "isamendment": (r.get(amd_k) or "").strip().upper() if amd_k else "",
            })
    return rows


def _norm(s):
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def fuzzy_best(query, cover_rows):
    """Return (best_name, score, rows_for_name) for the best fuzzy match.

    Strategy: lowercase/normalize. Prefer candidates whose name contains all
    query tokens; among those pick the highest SequenceMatcher ratio. If none
    contains all tokens, fall back to the single highest ratio.
    """
    q = _norm(query)
    q_tokens = set(q.split())
    best = None  # (contains_all, ratio, name)
    for r in cover_rows:
        name = r["name"]
        n = _norm(name)
        n_tokens = set(n.split())
        contains_all = q_tokens.issubset(n_tokens) if q_tokens else False
        ratio = SequenceMatcher(None, q, n).ratio()
        key = (1 if contains_all else 0, ratio)
        if best is None or key > best[0]:
            best = (key, name, ratio)
    if best is None:
        return None, 0.0, []
    best_name = best[1]
    rows_for_name = [r for r in cover_rows if r["name"] == best_name]
    return best_name, best[2], rows_for_name


def select_primary_accession(rows_for_name, acc_totals):
    """Choose the primary filing accession.

    Prefer non-amendment accessions; among the chosen set pick the one with the
    largest total reported value (from acc_totals: accession -> total_value).
    rows_for_name: list of {accession, isamendment}.
    """
    accs = [(r["accession"], r["isamendment"]) for r in rows_for_name if r["accession"]]
    if not accs:
        return None
    non_amd = [a for a, amd in accs if amd != "Y"]
    pool = non_amd if non_amd else [a for a, _ in accs]
    return max(pool, key=lambda a: acc_totals.get(a, 0.0))


def _info_indices(header):
    idx = {name.upper(): i for i, name in enumerate(header)}
    return {
        "acc": idx.get("ACCESSION_NUMBER"),
        "issuer": idx.get("NAMEOFISSUER"),
        "title": idx.get("TITLEOFCLASS"),
        "cusip": idx.get("CUSIP"),
        "value": idx.get("VALUE"),
        "ssh": idx.get("SSHPRNAMT"),
        "sshtype": idx.get("SSHPRNAMTTYPE"),
        "putcall": idx.get("PUTCALL"),
    }


def _to_float(x):
    if x is None:
        return 0.0
    x = x.strip().replace(",", "")
    if not x:
        return 0.0
    try:
        return float(x)
    except ValueError:
        return 0.0


def _is_equity(putcall, sshtype):
    pc = (putcall or "").strip()
    st = (sshtype or "").strip().upper()
    return pc == "" and st == "SH"


def aggregate_accessions(quarter_dir, accessions):
    """Single pass over INFOTABLE for a set of accessions.

    Returns dict accession -> {
        total_value, row_count, equity_row_count,
        cusip_all (set), cusip_equity (set),
        cusip_equity_value (dict cusip->summed value, equity only)
    }
    """
    accset = set(accessions)
    out = {a: {
        "total_value": 0.0, "row_count": 0, "equity_row_count": 0,
        "cusip_all": set(), "cusip_equity": set(), "cusip_equity_value": {},
    } for a in accset}
    if not accset:
        return out
    path = require_file(quarter_dir, "INFOTABLE.tsv")
    with _open(path) as fh:
        reader = csv.reader(fh, delimiter="\t")
        header = next(reader, None)
        if not header:
            return out
        ix = _info_indices(header)
        for row in reader:
            try:
                acc = row[ix["acc"]].strip()
            except (IndexError, TypeError):
                continue
            if acc not in accset:
                continue
            rec = out[acc]
            value = _to_float(row[ix["value"]]) if ix["value"] is not None else 0.0
            cusip = (row[ix["cusip"]].strip().upper() if ix["cusip"] is not None else "")
            putcall = row[ix["putcall"]] if ix["putcall"] is not None else ""
            sshtype = row[ix["sshtype"]] if ix["sshtype"] is not None else ""
            rec["total_value"] += value
            rec["row_count"] += 1
            if cusip:
                rec["cusip_all"].add(cusip)
            if _is_equity(putcall, sshtype):
                rec["equity_row_count"] += 1
                if cusip:
                    rec["cusip_equity"].add(cusip)
                    rec["cusip_equity_value"][cusip] = (
                        rec["cusip_equity_value"].get(cusip, 0.0) + value
                    )
    return out


def find_cusips_by_issuer(quarter_dir, substring, equity_only=True):
    """Return dict cusip -> example issuer name for rows whose NAMEOFISSUER
    contains substring (case-insensitive).
    """
    needle = substring.lower()
    found = {}
    path = require_file(quarter_dir, "INFOTABLE.tsv")
    with _open(path) as fh:
        reader = csv.reader(fh, delimiter="\t")
        header = next(reader, None)
        if not header:
            return found
        ix = _info_indices(header)
        for row in reader:
            try:
                issuer = row[ix["issuer"]]
            except (IndexError, TypeError):
                continue
            if issuer and needle in issuer.lower():
                if equity_only:
                    pc = row[ix["putcall"]] if ix["putcall"] is not None else ""
                    st = row[ix["sshtype"]] if ix["sshtype"] is not None else ""
                    if not _is_equity(pc, st):
                        continue
                cusip = (row[ix["cusip"]].strip().upper() if ix["cusip"] is not None else "")
                if cusip:
                    found.setdefault(cusip, issuer.strip())
    return found


def value_by_accession_for_cusips(quarter_dir, cusips, equity_only=True):
    """Return dict accession -> summed VALUE for rows whose CUSIP is in cusips."""
    cset = {c.strip().upper() for c in cusips}
    out = {}
    if not cset:
        return out
    path = require_file(quarter_dir, "INFOTABLE.tsv")
    with _open(path) as fh:
        reader = csv.reader(fh, delimiter="\t")
        header = next(reader, None)
        if not header:
            return out
        ix = _info_indices(header)
        for row in reader:
            try:
                cusip = row[ix["cusip"]].strip().upper()
            except (IndexError, TypeError, AttributeError):
                continue
            if cusip not in cset:
                continue
            if equity_only:
                pc = row[ix["putcall"]] if ix["putcall"] is not None else ""
                st = row[ix["sshtype"]] if ix["sshtype"] is not None else ""
                if not _is_equity(pc, st):
                    continue
            acc = row[ix["acc"]].strip()
            value = _to_float(row[ix["value"]]) if ix["value"] is not None else 0.0
            out[acc] = out.get(acc, 0.0) + value
    return out


def cover_name_map(quarter_dir):
    """Return dict accession -> FILINGMANAGER_NAME."""
    m = {}
    for r in load_coverpage(quarter_dir):
        if r["accession"]:
            m[r["accession"]] = r["name"]
    return m


def compute_change_ranking(q2_cusip_value, q3_cusip_value):
    """Outer-merge two cusip->value dicts; return list of
    (cusip, q2, q3, change) sorted by change descending.
    """
    cusips = set(q2_cusip_value) | set(q3_cusip_value)
    rows = []
    for c in cusips:
        v2 = q2_cusip_value.get(c, 0.0)
        v3 = q3_cusip_value.get(c, 0.0)
        rows.append((c, v2, v3, v3 - v2))
    rows.sort(key=lambda t: t[3], reverse=True)
    return rows


def stock_count(rec, mode):
    """Return a stock count for an accession aggregation record per mode."""
    if mode == "unique_cusip_all":
        return len(rec["cusip_all"])
    if mode == "rows_equity":
        return rec["equity_row_count"]
    if mode == "rows_all":
        return rec["row_count"]
    return len(rec["cusip_equity"])  # unique_cusip_equity (default)
