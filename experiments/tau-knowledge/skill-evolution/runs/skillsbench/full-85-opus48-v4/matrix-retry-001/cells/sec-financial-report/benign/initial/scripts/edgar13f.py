"""Reusable helpers for SEC 13F EDGAR bulk TSV analysis.

No task answers are hardcoded here; callers pass query strings and paths.
"""
import os
import zipfile
from difflib import SequenceMatcher

import pandas as pd

INFO_COLS = {
    "ACCESSION_NUMBER", "NAMEOFISSUER", "TITLEOFCLASS", "CUSIP",
    "VALUE", "SSHPRNAMT", "SSHPRNAMTTYPE", "PUTCALL",
}
COVER_COLS = {"ACCESSION_NUMBER", "FILINGMANAGER_NAME", "ISAMENDMENT"}
SUMMARY_COLS = {"ACCESSION_NUMBER", "TABLEENTRYTOTAL", "TABLEVALUETOTAL"}


def norm(s):
    return " ".join(str(s).lower().split())


def find_file(root, fname):
    """Recursively locate a file by case-insensitive name; None if absent."""
    fl = fname.lower()
    for dp, _dn, fn in os.walk(root):
        for f in fn:
            if f.lower() == fl:
                return os.path.join(dp, f)
    return None


def ensure_dir(data_dir, zip_path):
    """Return a directory containing COVERPAGE.tsv, unzipping if needed."""
    if data_dir and os.path.isdir(data_dir) and find_file(data_dir, "COVERPAGE.tsv"):
        return data_dir
    target = data_dir
    if not target:
        if zip_path and zip_path.lower().endswith(".zip"):
            target = zip_path[:-4]
        else:
            target = (zip_path or "") + "_extracted"
    os.makedirs(target, exist_ok=True)
    if find_file(target, "COVERPAGE.tsv"):
        return target
    if not (zip_path and os.path.isfile(zip_path)):
        raise FileNotFoundError(
            f"No COVERPAGE.tsv under {target!r} and no zip at {zip_path!r}")
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(target)
    if not find_file(target, "COVERPAGE.tsv"):
        raise FileNotFoundError(f"COVERPAGE.tsv not found after extracting {zip_path!r}")
    return target


def _read_tsv(path, cols):
    return pd.read_csv(
        path, sep="\t", dtype=str,
        usecols=lambda c: c in cols, low_memory=False,
    )


def load_coverpage(data_dir):
    path = find_file(data_dir, "COVERPAGE.tsv")
    if not path:
        raise FileNotFoundError(f"COVERPAGE.tsv not found under {data_dir!r}")
    df = _read_tsv(path, COVER_COLS)
    for c in ["FILINGMANAGER_NAME", "ISAMENDMENT", "ACCESSION_NUMBER"]:
        if c in df:
            df[c] = df[c].fillna("")
    return df


def load_infotable(data_dir):
    path = find_file(data_dir, "INFOTABLE.tsv")
    if not path:
        raise FileNotFoundError(f"INFOTABLE.tsv not found under {data_dir!r}")
    df = _read_tsv(path, INFO_COLS)
    df["VALUE"] = pd.to_numeric(df.get("VALUE"), errors="coerce").fillna(0.0)
    for c in ["PUTCALL", "SSHPRNAMTTYPE", "NAMEOFISSUER", "TITLEOFCLASS"]:
        if c in df:
            df[c] = df[c].fillna("")
    if "CUSIP" in df:
        df["CUSIP"] = df["CUSIP"].fillna("").str.strip().str.upper()
    if "ACCESSION_NUMBER" in df:
        df["ACCESSION_NUMBER"] = df["ACCESSION_NUMBER"].fillna("")
    return df


def load_summary(data_dir):
    path = find_file(data_dir, "SUMMARYPAGE.tsv")
    if not path:
        return None
    df = _read_tsv(path, SUMMARY_COLS)
    if "ACCESSION_NUMBER" in df:
        df["ACCESSION_NUMBER"] = df["ACCESSION_NUMBER"].fillna("")
    return df


def match_manager(cover, query):
    """Fuzzy-match a FILINGMANAGER_NAME; return dict with name, score, accession."""
    qn = norm(query)
    qt = qn.split()
    best_idx = None
    best_score = -1.0
    best_name = None
    for idx, nm in cover["FILINGMANAGER_NAME"].items():
        c = norm(nm)
        if not c:
            continue
        score = SequenceMatcher(None, qn, c).ratio()
        if qt and all(t in c for t in qt):
            score += 1.0
        if score > best_score:
            best_score = score
            best_idx = idx
            best_name = nm
    rows = cover[cover["FILINGMANAGER_NAME"] == best_name]
    if "ISAMENDMENT" in rows:
        non = rows[rows["ISAMENDMENT"].str.upper().str.startswith("N")]
        if len(non):
            rows = non
    accessions = list(dict.fromkeys(rows["ACCESSION_NUMBER"].tolist()))
    accession = accessions[0] if accessions else None
    return {
        "query": query,
        "matched_name": best_name,
        "score": round(float(best_score), 4),
        "accession": accession,
        "all_accessions": accessions,
    }


def equity_mask(df):
    """Share-based equity positions: no option flag, not principal-amount."""
    pc = df["PUTCALL"].fillna("").str.strip()
    tp = df["SSHPRNAMTTYPE"].fillna("").str.strip().str.upper()
    return (pc == "") & (tp != "PRN")


def holdings_for(info, accession):
    return info[info["ACCESSION_NUMBER"] == accession]


def aum(info, accession):
    sub = holdings_for(info, accession)
    return float(sub["VALUE"].sum())


def stock_counts(info, accession):
    sub = holdings_for(info, accession)
    eq = sub[equity_mask(sub)]
    return {
        "all_rows": int(len(sub)),
        "all_unique_cusip": int(sub["CUSIP"].nunique()),
        "equity_rows": int(len(eq)),
        "equity_unique_cusip": int(eq["CUSIP"].nunique()),
    }


def cusip_value_by_quarter(info, accession):
    sub = info[(info["ACCESSION_NUMBER"] == accession)]
    sub = sub[equity_mask(sub)]
    g = sub.groupby("CUSIP")["VALUE"].sum()
    return g


def top_increases(info_q2, acc_q2, info_q3, acc_q3, top=5):
    v2 = cusip_value_by_quarter(info_q2, acc_q2).rename("v2")
    v3 = cusip_value_by_quarter(info_q3, acc_q3).rename("v3")
    merged = pd.concat([v2, v3], axis=1).fillna(0.0)
    merged["change"] = merged["v3"] - merged["v2"]
    merged = merged[merged.index != ""]
    merged = merged.sort_values("change", ascending=False)
    return merged.head(top).index.tolist(), merged


def top_holders_of_security(info_q3, cover_q3, term, top=3):
    pal = info_q3[info_q3["NAMEOFISSUER"].str.contains(term, case=False, na=False)]
    cusips = sorted([c for c in pal["CUSIP"].unique() if c])
    grp = pal.groupby("ACCESSION_NUMBER")["VALUE"].sum().reset_index()
    names = cover_q3[["ACCESSION_NUMBER", "FILINGMANAGER_NAME"]].drop_duplicates(
        "ACCESSION_NUMBER")
    grp = grp.merge(names, on="ACCESSION_NUMBER", how="left")
    grp["FILINGMANAGER_NAME"] = grp["FILINGMANAGER_NAME"].fillna("")
    grp = grp.sort_values("VALUE", ascending=False)
    grp = grp.drop_duplicates(subset="FILINGMANAGER_NAME", keep="first")
    top_rows = grp.head(top)
    return top_rows["FILINGMANAGER_NAME"].tolist(), cusips, grp
