#!/usr/bin/env python3
"""Create answers.json for the 2025 Q2/Q3 SEC 13F holdings task.

Reads one JSON object from stdin and writes the answer object to stdout and to
output_path.  See SKILL.md for the input schema.
"""
import csv
import io
import json
import os
import re
import sys
import zipfile
from collections import defaultdict
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher


def norm(value):
    """Canonical text used for field names and identity comparisons."""
    return re.sub(r"[^A-Z0-9]+", "", str(value or "").upper())


def text(value):
    return str(value or "").strip()


def field(row, name):
    return row.get(norm(name), "")


def number(value):
    """Parse an EDGAR numeric field exactly, returning Decimal."""
    cleaned = text(value).replace(",", "").replace("$", "")
    if not cleaned:
        return Decimal(0)
    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError("Invalid VALUE field: {!r}".format(value)) from exc


def json_number(value):
    """Preserve integral filing values as JSON integers."""
    if value == value.to_integral_value():
        return int(value)
    return float(value)


def default_source(quarter):
    choices = [
        "/root/13f-2025-{}.zip".format(quarter),
        "/root/2025-{}".format(quarter),
        "/root/13f-2025-{}".format(quarter),
    ]
    for candidate in choices:
        if os.path.exists(candidate):
            return candidate
    raise FileNotFoundError("No supplied source found for Q{}: {}".format(quarter, choices))


def table_in_directory(source, table):
    desired = table.upper()
    for base, _, files in os.walk(source):
        for filename in files:
            if filename.upper() == desired:
                return os.path.join(base, filename)
    raise FileNotFoundError("{} not found below {}".format(table, source))


@contextmanager
def table_rows(source, table):
    """Yield a streaming iterator of normalized TSV rows from a directory or ZIP."""
    if os.path.isdir(source):
        path = table_in_directory(source, table)
        with open(path, "r", encoding="utf-8-sig", errors="replace", newline="") as handle:
            yield normalized_rows(handle)
        return
    if not zipfile.is_zipfile(source):
        raise ValueError("Source is neither a directory nor a readable ZIP: {}".format(source))
    with zipfile.ZipFile(source) as archive:
        matches = [name for name in archive.namelist()
                   if not name.endswith("/") and os.path.basename(name).upper() == table.upper()]
        if not matches:
            raise FileNotFoundError("{} not found in {}".format(table, source))
        # Prefer the shallowest matching archive member deterministically.
        member = sorted(matches, key=lambda n: (n.count("/"), n))[0]
        with archive.open(member) as binary, io.TextIOWrapper(
                binary, encoding="utf-8-sig", errors="replace", newline="") as handle:
            yield normalized_rows(handle)


def normalized_rows(handle):
    reader = csv.DictReader(handle, delimiter="\t")
    if not reader.fieldnames:
        raise ValueError("TSV has no header row")
    for raw in reader:
        yield {norm(key): text(value) for key, value in raw.items() if key is not None}


def load_coverpage(source):
    records = []
    with table_rows(source, "COVERPAGE.tsv") as rows:
        for index, row in enumerate(rows):
            accession = field(row, "ACCESSION_NUMBER")
            name = field(row, "FILINGMANAGER_NAME")
            if accession and name:
                records.append({
                    "accession": accession,
                    "name": name,
                    "amendment": norm(field(row, "ISAMENDMENT")) == "Y",
                    "index": index,
                })
    if not records:
        raise ValueError("COVERPAGE contains no rows with accession and manager name")
    return records


def similarity(query, candidate):
    q = norm(query)
    c = norm(candidate)
    sequence = SequenceMatcher(None, q, c).ratio()
    q_tokens = set(re.findall(r"[A-Z0-9]+", str(query).upper()))
    c_tokens = set(re.findall(r"[A-Z0-9]+", str(candidate).upper()))
    token_score = len(q_tokens & c_tokens) / max(1, len(q_tokens))
    # A direct normalized substring deserves priority over incidental edit similarity.
    return sequence * 0.65 + token_score * 0.35 + (0.30 if q in c else 0.0)


def resolve_manager(cover, query):
    ranked = []
    for record in cover:
        ranked.append((similarity(query, record["name"]), record))
    # Original/non-amendment is preferred only after similarity, never over a better name.
    ranked.sort(key=lambda pair: (-pair[0], pair[1]["amendment"], pair[1]["index"]))
    score, selected = ranked[0]
    if score < 0.45:
        raise ValueError("No credible COVERPAGE match for {!r}; best was {!r}".format(
            query, selected["name"]))
    return selected


def preferred_accessions(cover):
    """Choose one filing per manager, preferring a non-amendment filing."""
    grouped = defaultdict(list)
    for record in cover:
        grouped[norm(record["name"])].append(record)
    result = {}
    for _, records in grouped.items():
        records.sort(key=lambda r: (r["amendment"], r["index"]))
        selected = records[0]
        result[selected["accession"]] = selected["name"]
    return result


def stock_row(row, policy):
    cusip = field(row, "CUSIP")
    if not cusip:
        return False
    if policy == "all_unique_cusip":
        return True
    putcall = norm(field(row, "PUTCALL"))
    amount_type = norm(field(row, "SSHPRNAMTTYPE"))
    basic = not putcall and amount_type == "SH"
    if policy in ("share_non_option_unique_cusip", "row_count"):
        return basic
    if policy == "common_share_unique_cusip":
        title = norm(field(row, "TITLEOFCLASS"))
        return basic and ("COM" in title or title.startswith("CLASS") or title.startswith("CL"))
    raise ValueError("Unsupported stock_policy: {}".format(policy))


def holdings_for_accession(source, accession, policy):
    """Return CUSIP -> VALUE after applying the specified comparable-stock policy."""
    values = defaultdict(Decimal)
    with table_rows(source, "INFOTABLE.tsv") as rows:
        for row in rows:
            if field(row, "ACCESSION_NUMBER") != accession or not stock_row(row, policy):
                continue
            values[field(row, "CUSIP")] += number(field(row, "VALUE"))
    if not values:
        raise ValueError("No eligible INFOTABLE holdings for accession {}".format(accession))
    return values


def renaissance_metrics(source, accession, policy):
    total = Decimal(0)
    holding_keys = set()
    row_count = 0
    with table_rows(source, "INFOTABLE.tsv") as rows:
        for row in rows:
            if field(row, "ACCESSION_NUMBER") != accession:
                continue
            total += number(field(row, "VALUE"))
            if stock_row(row, policy):
                row_count += 1
                holding_keys.add(field(row, "CUSIP"))
    if total == 0:
        raise ValueError("No INFOTABLE value found for Renaissance accession {}".format(accession))
    return total, (row_count if policy == "row_count" else len(holding_keys))


def palantir_cusip(source):
    """Find Palantir's CUSIP from issuer labels without hardcoding an identifier."""
    candidates = defaultdict(lambda: [0.0, 0])
    with table_rows(source, "INFOTABLE.tsv") as rows:
        for row in rows:
            issuer = field(row, "NAMEOFISSUER")
            cusip = field(row, "CUSIP")
            if not cusip or "PALANTIR" not in norm(issuer):
                continue
            score = similarity("palantir technologies", issuer)
            candidates[cusip][0] = max(candidates[cusip][0], score)
            candidates[cusip][1] += 1
    if not candidates:
        raise ValueError("Could not identify a Palantir CUSIP from NAMEOFISSUER")
    return sorted(candidates, key=lambda c: (-candidates[c][0], -candidates[c][1], c))[0]


def top_palantir_managers(source, cover):
    cusip = palantir_cusip(source)
    accession_to_name = preferred_accessions(cover)
    values = defaultdict(Decimal)
    with table_rows(source, "INFOTABLE.tsv") as rows:
        for row in rows:
            accession = field(row, "ACCESSION_NUMBER")
            if accession in accession_to_name and field(row, "CUSIP") == cusip:
                values[accession] += number(field(row, "VALUE"))
    ranked = sorted(values.items(), key=lambda pair: (-pair[1], accession_to_name[pair[0]].upper()))
    names = [accession_to_name[accession] for accession, _ in ranked[:3]]
    if len(names) != 3:
        raise ValueError("Fewer than three managers hold detected Palantir CUSIP {}".format(cusip))
    return names


def validate_answers(answer):
    if not isinstance(answer["q1_answer"], (int, float)) or isinstance(answer["q1_answer"], bool):
        raise ValueError("q1_answer must be a JSON number")
    if not isinstance(answer["q2_answer"], int) or answer["q2_answer"] < 0:
        raise ValueError("q2_answer must be a nonnegative JSON integer")
    if len(answer["q3_answer"]) != 5 or any(not isinstance(x, str) or not x for x in answer["q3_answer"]):
        raise ValueError("q3_answer must contain exactly five nonblank CUSIP strings")
    if len(answer["q4_answer"]) != 3 or any(not isinstance(x, str) or not x for x in answer["q4_answer"]):
        raise ValueError("q4_answer must contain exactly three nonblank manager names")


def main(config):
    q2_source = config.get("q2_source") or default_source("q2")
    q3_source = config.get("q3_source") or default_source("q3")
    policy = config.get("stock_policy", "share_non_option_unique_cusip")

    q2_cover = load_coverpage(q2_source)
    q3_cover = load_coverpage(q3_source)
    renaissance = resolve_manager(q3_cover, "renaissance technologies")
    berkshire_q2 = resolve_manager(q2_cover, "berkshire hathaway")
    berkshire_q3 = resolve_manager(q3_cover, "berkshire hathaway")

    aum, stock_count = renaissance_metrics(q3_source, renaissance["accession"], policy)
    q2_values = holdings_for_accession(q2_source, berkshire_q2["accession"], policy)
    q3_values = holdings_for_accession(q3_source, berkshire_q3["accession"], policy)
    increases = []
    for cusip in set(q2_values) | set(q3_values):
        change = q3_values.get(cusip, Decimal(0)) - q2_values.get(cusip, Decimal(0))
        if change > 0:
            increases.append((cusip, change))
    increases.sort(key=lambda pair: (-pair[1], pair[0]))
    if len(increases) < 5:
        raise ValueError("Fewer than five positive Berkshire CUSIP value increases")

    answer = {
        "q1_answer": json_number(aum),
        "q2_answer": stock_count,
        "q3_answer": [cusip for cusip, _ in increases[:5]],
        "q4_answer": top_palantir_managers(q3_source, q3_cover),
    }
    validate_answers(answer)
    output_path = config.get("output_path", "/root/answers.json")
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(answer, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    return answer


if __name__ == "__main__":
    try:
        supplied = json.load(sys.stdin)
        if not isinstance(supplied, dict):
            raise ValueError("stdin must contain one JSON object")
        print(json.dumps(main(supplied), ensure_ascii=False))
    except Exception as exc:
        print("ERROR: {}".format(exc), file=sys.stderr)
        sys.exit(1)
