#!/usr/bin/env python3
"""Create answers.json for the SEC 13F Q2/Q3 quarterly holdings task.

stdin: JSON object with optional q2_source, q3_source, and output_path strings.
stdout: generated answer JSON object. The same object is written to output_path.
Sources can be ZIP archives or extracted directories containing EDGAR TSV tables.
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


def text(value):
    return str(value or "").strip()


def key(value):
    return re.sub(r"[^A-Z0-9]+", "", text(value).upper())


def name_norm(value):
    return re.sub(r"[^a-z0-9]+", " ", text(value).lower()).strip()


def row_field(row, name):
    return row.get(key(name), "")


def value_number(value):
    cleaned = text(value).replace(",", "").replace("$", "")
    if not cleaned:
        return Decimal(0)
    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError("Invalid VALUE field: {!r}".format(value)) from exc


def json_number(value):
    return int(value) if value == value.to_integral_value() else float(value)


def default_source(quarter):
    candidates = (
        "/root/13f-2025-{}.zip".format(quarter),
        "/root/2025-{}".format(quarter),
        "/root/13f-2025-{}".format(quarter),
    )
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    raise FileNotFoundError("No supplied source found for Q{}: {}".format(quarter, candidates))


def directory_table(source, table):
    for base, _, files in os.walk(source):
        for filename in files:
            if filename.upper() == table.upper():
                return os.path.join(base, filename)
    raise FileNotFoundError("{} not found below {}".format(table, source))


def normalized_rows(handle):
    reader = csv.DictReader(handle, delimiter="\t")
    if not reader.fieldnames:
        raise ValueError("TSV has no header row")
    for raw in reader:
        yield {key(header): text(value) for header, value in raw.items() if header is not None}


@contextmanager
def table_rows(source, table):
    """Provide a streaming normalized-row iterator from a directory or ZIP."""
    if os.path.isdir(source):
        with open(directory_table(source, table), "r", encoding="utf-8-sig",
                  errors="replace", newline="") as handle:
            yield normalized_rows(handle)
        return
    if not zipfile.is_zipfile(source):
        raise ValueError("Source is neither a directory nor a readable ZIP: {}".format(source))
    with zipfile.ZipFile(source) as archive:
        members = [member for member in archive.namelist()
                   if not member.endswith("/")
                   and os.path.basename(member).upper() == table.upper()]
        if not members:
            raise FileNotFoundError("{} not found in {}".format(table, source))
        member = min(members, key=lambda item: (item.count("/"), item))
        with archive.open(member) as binary, io.TextIOWrapper(
                binary, encoding="utf-8-sig", errors="replace", newline="") as handle:
            yield normalized_rows(handle)


def load_coverpage(source):
    records = []
    with table_rows(source, "COVERPAGE.tsv") as rows:
        for index, row in enumerate(rows):
            accession = row_field(row, "ACCESSION_NUMBER")
            manager = row_field(row, "FILINGMANAGER_NAME")
            if accession and manager:
                records.append({
                    "accession": accession,
                    "name": manager,
                    "amendment": row_field(row, "ISAMENDMENT").upper() == "Y",
                    "index": index,
                })
    if not records:
        raise ValueError("COVERPAGE contains no usable manager/accession rows")
    return records


def resolve_manager(coverpage, query):
    query_n = name_norm(query)
    ranked = []
    for record in coverpage:
        candidate_n = name_norm(record["name"])
        score = SequenceMatcher(None, query_n, candidate_n).ratio()
        if query_n in candidate_n:
            score += 2
        if record["amendment"]:
            score -= Decimal("0.001")
        ranked.append((score, candidate_n, record))
    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    _, _, selected = ranked[0]
    if query_n not in name_norm(selected["name"]):
        raise ValueError("No containing COVERPAGE match for {!r}; best was {!r}".format(
            query, selected["name"]))
    return selected


def renaissance_metrics(source, accession):
    total = Decimal(0)
    entries = 0
    with table_rows(source, "INFOTABLE.tsv") as rows:
        for row in rows:
            if row_field(row, "ACCESSION_NUMBER") == accession:
                total += value_number(row_field(row, "VALUE"))
                entries += 1
    if not entries:
        raise ValueError("No INFOTABLE rows for Renaissance accession {}".format(accession))
    return total, entries


def values_by_cusip(source, accession):
    values = defaultdict(Decimal)
    with table_rows(source, "INFOTABLE.tsv") as rows:
        for row in rows:
            if row_field(row, "ACCESSION_NUMBER") == accession:
                values[row_field(row, "CUSIP")] += value_number(row_field(row, "VALUE"))
    if not values:
        raise ValueError("No INFOTABLE rows for accession {}".format(accession))
    return values


def canonical_cusip(value):
    return re.sub(r"\s+", "", text(value).upper())


def valid_cusip(value):
    """Validate a nine-character CUSIP, including its standard check digit."""
    cusip = canonical_cusip(value)
    if len(cusip) != 9 or not cusip[8].isdigit():
        return False
    amounts = []
    for char in cusip[:8]:
        if char.isdigit():
            amounts.append(int(char))
        elif "A" <= char <= "Z":
            amounts.append(ord(char) - ord("A") + 10)
        elif char == "*":
            amounts.append(36)
        elif char == "@":
            amounts.append(37)
        elif char == "#":
            amounts.append(38)
        else:
            return False
    total = 0
    for index, amount in enumerate(amounts):
        if index % 2 == 1:
            amount *= 2
        total += amount // 10 + amount % 10
    return (total + int(cusip[8])) % 10 == 0


def palantir_issuer(issuer):
    """Match the company identity, allowing normal legal suffix variations."""
    normalized = name_norm(issuer)
    return normalized == "palantir technologies" or normalized.startswith("palantir technologies inc")


def class_a_common_equity(title):
    """Recognize common Class A labels without treating options or debt as stock."""
    normalized = name_norm(title)
    tokens = normalized.split()
    has_class_a = any(tokens[i] in ("class", "cl") and tokens[i + 1] == "a"
                      for i in range(len(tokens) - 1))
    has_common_marker = "common" in tokens or "com" in tokens or has_class_a
    return has_class_a and has_common_marker


def is_palantir_common_equity(row):
    """Structured predicate for the requested ordinary Palantir stock security."""
    return (
        palantir_issuer(row_field(row, "NAMEOFISSUER"))
        and not row_field(row, "PUTCALL")
        and row_field(row, "SSHPRNAMTTYPE").upper() == "SH"
        and class_a_common_equity(row_field(row, "TITLEOFCLASS"))
        and valid_cusip(row_field(row, "CUSIP"))
    )


def resolve_palantir_cusip(source):
    """Find one CUSIP meeting all company, equity, and identifier constraints."""
    candidates = set()
    with table_rows(source, "INFOTABLE.tsv") as rows:
        for row in rows:
            if is_palantir_common_equity(row):
                candidates.add(canonical_cusip(row_field(row, "CUSIP")))
    if len(candidates) != 1:
        raise ValueError(
            "Expected exactly one valid share-based Palantir Class A common-equity "
            "CUSIP; found {}".format(sorted(candidates)))
    return next(iter(candidates))


def top_palantir_managers(source, coverpage):
    target = resolve_palantir_cusip(source)
    accession_to_name = {record["accession"]: record["name"] for record in coverpage}
    values = defaultdict(Decimal)
    with table_rows(source, "INFOTABLE.tsv") as rows:
        for row in rows:
            if not is_palantir_common_equity(row):
                continue
            if canonical_cusip(row_field(row, "CUSIP")) != target:
                continue
            accession = row_field(row, "ACCESSION_NUMBER")
            if accession in accession_to_name:
                values[accession] += value_number(row_field(row, "VALUE"))
    ranked = sorted(values.items(), key=lambda item: (-item[1], accession_to_name[item[0]]))
    names = [accession_to_name[accession] for accession, _ in ranked[:3]]
    if len(names) != 3:
        raise ValueError("Fewer than three managers hold Palantir CUSIP {}".format(target))
    return names


def validate_answer(answer):
    if set(answer) != {"q1_answer", "q2_answer", "q3_answer", "q4_answer"}:
        raise ValueError("Answer has unexpected keys")
    if not isinstance(answer["q1_answer"], (int, float)) or isinstance(answer["q1_answer"], bool):
        raise ValueError("q1_answer must be numeric")
    if not isinstance(answer["q2_answer"], int) or answer["q2_answer"] < 0:
        raise ValueError("q2_answer must be a nonnegative integer")
    if len(answer["q3_answer"]) != 5 or any(not isinstance(x, str) or not x for x in answer["q3_answer"]):
        raise ValueError("q3_answer must contain exactly five nonblank CUSIP strings")
    if len(answer["q4_answer"]) != 3 or any(not isinstance(x, str) or not x for x in answer["q4_answer"]):
        raise ValueError("q4_answer must contain exactly three nonblank manager names")


def main(config):
    q2_source = config.get("q2_source") or default_source("q2")
    q3_source = config.get("q3_source") or default_source("q3")
    output_path = config.get("output_path", "/root/answers.json")

    q2_cover = load_coverpage(q2_source)
    q3_cover = load_coverpage(q3_source)
    renaissance = resolve_manager(q3_cover, "renaissance technologies")
    berkshire_q2 = resolve_manager(q2_cover, "berkshire hathaway")
    berkshire_q3 = resolve_manager(q3_cover, "berkshire hathaway")

    aum, entries = renaissance_metrics(q3_source, renaissance["accession"])
    q2_values = values_by_cusip(q2_source, berkshire_q2["accession"])
    q3_values = values_by_cusip(q3_source, berkshire_q3["accession"])
    changes = []
    for cusip in set(q2_values) | set(q3_values):
        change = q3_values.get(cusip, Decimal(0)) - q2_values.get(cusip, Decimal(0))
        if change > 0:
            changes.append((cusip, change))
    changes.sort(key=lambda item: (-item[1], item[0]))
    if len(changes) < 5:
        raise ValueError("Fewer than five positive Berkshire CUSIP value increases")

    answer = {
        "q1_answer": json_number(aum),
        "q2_answer": entries,
        "q3_answer": [cusip for cusip, _ in changes[:5]],
        "q4_answer": top_palantir_managers(q3_source, q3_cover),
    }
    validate_answer(answer)
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(answer, handle, ensure_ascii=False, indent=2)
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
