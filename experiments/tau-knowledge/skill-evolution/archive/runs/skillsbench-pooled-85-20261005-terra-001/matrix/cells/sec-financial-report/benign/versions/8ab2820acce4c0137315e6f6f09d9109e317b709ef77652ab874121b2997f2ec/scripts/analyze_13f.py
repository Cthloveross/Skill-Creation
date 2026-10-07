#!/usr/bin/env python3
"""Create answers.json for the SEC 13F Q2/Q3 quarterly holdings task.

stdin: JSON object with optional q2_source, q3_source, and output_path strings.
stdout: the generated answer JSON object.
side effect: atomically writes the same object to output_path.

A source is either a ZIP archive containing EDGAR TSV files or a directory that
contains them, directly or in a child directory.
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


# Headers are normalized once per table, not once per row. This matters for the
# large INFOTABLE files.
ACCESSION = "ACCESSIONNUMBER"
MANAGER = "FILINGMANAGERNAME"
AMENDMENT = "ISAMENDMENT"
ISSUER = "NAMEOFISSUER"
TITLE = "TITLEOFCLASS"
CUSIP = "CUSIP"
VALUE = "VALUE"
PUTCALL = "PUTCALL"
AMOUNT_TYPE = "SSHPRNAMTTYPE"


def clean(value):
    return str(value or "").strip()


def header_key(value):
    return re.sub(r"[^A-Z0-9]+", "", clean(value).upper())


def normalized_name(value):
    return re.sub(r"[^a-z0-9]+", " ", clean(value).lower()).strip()


def parse_value(value):
    value = clean(value).replace(",", "").replace("$", "")
    if not value:
        return Decimal(0)
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("Invalid VALUE field: {!r}".format(value)) from exc


def json_number(value):
    return int(value) if value == value.to_integral_value() else float(value)


def canonical_cusip(value):
    return re.sub(r"\s+", "", clean(value).upper())


def valid_cusip(value):
    """Return whether value is a syntactically valid nine-character CUSIP."""
    value = canonical_cusip(value)
    if len(value) != 9 or not value[-1].isdigit():
        return False
    digits = []
    for char in value[:8]:
        if char.isdigit():
            digits.append(int(char))
        elif "A" <= char <= "Z":
            digits.append(ord(char) - ord("A") + 10)
        elif char == "*":
            digits.append(36)
        elif char == "@":
            digits.append(37)
        elif char == "#":
            digits.append(38)
        else:
            return False
    total = 0
    # CUSIP's alternating transformation starts at the second character.
    for index, amount in enumerate(digits):
        if index % 2:
            amount *= 2
        total += amount // 10 + amount % 10
    return (total + int(value[-1])) % 10 == 0


def default_source(quarter):
    candidates = (
        "/root/13f-2025-{}.zip".format(quarter),
        "/root/2025-{}".format(quarter),
        "/root/13f-2025-{}".format(quarter),
    )
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    raise FileNotFoundError("No supplied Q{} source found: {}".format(quarter, candidates))


def directory_table(source, table):
    for base, _, filenames in os.walk(source):
        for filename in filenames:
            if filename.upper() == table.upper():
                return os.path.join(base, filename)
    raise FileNotFoundError("{} not found below {}".format(table, source))


def rows_from_handle(handle):
    """Yield stripped, header-normalized rows while keeping a streaming reader."""
    reader = csv.reader(handle, delimiter="\t")
    try:
        headers = [header_key(item) for item in next(reader)]
    except StopIteration as exc:
        raise ValueError("TSV has no header row") from exc
    if not any(headers):
        raise ValueError("TSV has an empty header row")
    for values in reader:
        # csv.DictReader semantics: missing trailing fields are empty strings.
        row = {}
        for index, header in enumerate(headers):
            if header:
                row[header] = clean(values[index]) if index < len(values) else ""
        yield row


@contextmanager
def table_rows(source, table):
    if os.path.isdir(source):
        path = directory_table(source, table)
        with open(path, "r", encoding="utf-8-sig", errors="replace", newline="") as handle:
            yield rows_from_handle(handle)
        return
    if not zipfile.is_zipfile(source):
        raise ValueError("Source is neither a directory nor a readable ZIP: {}".format(source))
    with zipfile.ZipFile(source) as archive:
        members = [
            item for item in archive.namelist()
            if not item.endswith("/") and os.path.basename(item).upper() == table.upper()
        ]
        if not members:
            raise FileNotFoundError("{} not found in {}".format(table, source))
        member = min(members, key=lambda item: (item.count("/"), item))
        with archive.open(member) as binary:
            with io.TextIOWrapper(binary, encoding="utf-8-sig", errors="replace", newline="") as handle:
                yield rows_from_handle(handle)


def load_coverpage(source):
    records = []
    with table_rows(source, "COVERPAGE.tsv") as rows:
        for index, row in enumerate(rows):
            accession = row.get(ACCESSION, "")
            name = row.get(MANAGER, "")
            if accession and name:
                records.append({
                    "accession": accession,
                    "name": name,
                    "amendment": row.get(AMENDMENT, "").upper() == "Y",
                    "index": index,
                })
    if not records:
        raise ValueError("COVERPAGE contains no usable manager/accession records")
    return records


def resolve_manager(coverpage, query):
    """Use the requested containing-name fuzzy-search policy deterministically."""
    query_name = normalized_name(query)
    ranked = []
    for record in coverpage:
        candidate = normalized_name(record["name"])
        score = SequenceMatcher(None, query_name, candidate).ratio()
        if query_name in candidate:
            score += 2.0
        if record["amendment"]:
            score -= 0.001
        ranked.append((score, candidate, -record["index"], record))
    ranked.sort(key=lambda item: item[:3], reverse=True)
    selected = ranked[0][3]
    if query_name not in normalized_name(selected["name"]):
        raise ValueError("No containing COVERPAGE match for {!r}; best was {!r}".format(
            query, selected["name"]))
    return selected


def issuer_is_palantir_technologies(value):
    """Accept normal legal-name variants, but not a longer similarly named issuer."""
    return normalized_name(value) in {
        "palantir technologies",
        "palantir technologies inc",
        "palantir technologies incorporated",
    }


def is_class_a_common_title(value):
    """Identify filer spelling variants for the ordinary Class A equity security."""
    tokens = normalized_name(value).split()
    class_a = any(
        tokens[index] in {"class", "cl"} and tokens[index + 1] == "a"
        for index in range(len(tokens) - 1)
    )
    derivative_words = {"option", "call", "put", "warrant", "note", "bond", "debt", "unit"}
    return class_a and not any(token in derivative_words for token in tokens)


def palantir_class_a_candidate(row):
    """Strict resolver predicate; it discovers, rather than embeds, the CUSIP."""
    return (
        issuer_is_palantir_technologies(row.get(ISSUER, ""))
        and not row.get(PUTCALL, "")
        and row.get(AMOUNT_TYPE, "").upper() == "SH"
        and is_class_a_common_title(row.get(TITLE, ""))
        and valid_cusip(row.get(CUSIP, ""))
    )


def palantir_equity_row(row):
    """Rows eligible for aggregation once the ordinary equity CUSIP is resolved."""
    return (
        issuer_is_palantir_technologies(row.get(ISSUER, ""))
        and not row.get(PUTCALL, "")
        and row.get(AMOUNT_TYPE, "").upper() == "SH"
        and valid_cusip(row.get(CUSIP, ""))
    )


def scan_q3(source, renaissance_accession, berkshire_accession):
    """Obtain all Q3 metrics in one pass through the large INFOTABLE."""
    renaissance_total = Decimal(0)
    renaissance_entries = 0
    berkshire_values = defaultdict(Decimal)
    palantir_candidates = set()
    palantir_values_by_cusip = defaultdict(lambda: defaultdict(Decimal))

    with table_rows(source, "INFOTABLE.tsv") as rows:
        for row in rows:
            accession = row.get(ACCESSION, "")
            value = parse_value(row.get(VALUE, ""))
            if accession == renaissance_accession:
                renaissance_total += value
                renaissance_entries += 1
            if accession == berkshire_accession:
                # Preserve the source representation required for the CUSIP ranking.
                berkshire_values[row.get(CUSIP, "")] += value

            if palantir_equity_row(row):
                cusip = canonical_cusip(row.get(CUSIP, ""))
                palantir_values_by_cusip[cusip][accession] += value
                if palantir_class_a_candidate(row):
                    palantir_candidates.add(cusip)

    if not renaissance_entries:
        raise ValueError("Selected Renaissance Q3 filing has no INFOTABLE rows")
    if not berkshire_values:
        raise ValueError("Selected Berkshire Q3 filing has no INFOTABLE rows")
    if len(palantir_candidates) != 1:
        raise ValueError(
            "Expected exactly one valid Palantir Technologies Class A common-equity "
            "CUSIP; found {}".format(sorted(palantir_candidates))
        )
    target = next(iter(palantir_candidates))
    return renaissance_total, renaissance_entries, berkshire_values, target, palantir_values_by_cusip[target]


def scan_values_by_cusip(source, accession):
    values = defaultdict(Decimal)
    with table_rows(source, "INFOTABLE.tsv") as rows:
        for row in rows:
            if row.get(ACCESSION, "") == accession:
                values[row.get(CUSIP, "")] += parse_value(row.get(VALUE, ""))
    if not values:
        raise ValueError("Selected filing {} has no INFOTABLE rows".format(accession))
    return values


def top_increases(q2_values, q3_values):
    changes = []
    for cusip in set(q2_values) | set(q3_values):
        difference = q3_values.get(cusip, Decimal(0)) - q2_values.get(cusip, Decimal(0))
        if difference > 0:
            changes.append((cusip, difference))
    changes.sort(key=lambda item: (-item[1], item[0]))
    if len(changes) < 5:
        raise ValueError("Fewer than five positive Berkshire CUSIP-level increases")
    return [cusip for cusip, _ in changes[:5]]


def top_palantir_managers(values_by_accession, coverpage, target_cusip):
    names = {record["accession"]: record["name"] for record in coverpage}
    missing = sorted(accession for accession in values_by_accession if accession not in names)
    if missing:
        raise ValueError("Palantir holdings cannot be joined to COVERPAGE: {}".format(missing[:3]))
    ranked = sorted(
        values_by_accession.items(),
        key=lambda item: (-item[1], names[item[0]]),
    )
    result = [names[accession] for accession, _ in ranked[:3]]
    if len(result) != 3:
        raise ValueError("Fewer than three managers hold Palantir CUSIP {}".format(target_cusip))
    return result


def validate_answer(answer):
    required = {"q1_answer", "q2_answer", "q3_answer", "q4_answer"}
    if set(answer) != required:
        raise ValueError("Answer has unexpected or missing keys")
    if not isinstance(answer["q1_answer"], (int, float)) or isinstance(answer["q1_answer"], bool):
        raise ValueError("q1_answer must be numeric")
    if not isinstance(answer["q2_answer"], int) or answer["q2_answer"] < 0:
        raise ValueError("q2_answer must be a nonnegative integer")
    if (not isinstance(answer["q3_answer"], list) or len(answer["q3_answer"]) != 5 or
            any(not isinstance(item, str) or not item for item in answer["q3_answer"])):
        raise ValueError("q3_answer must contain exactly five nonblank CUSIP strings")
    if (not isinstance(answer["q4_answer"], list) or len(answer["q4_answer"]) != 3 or
            any(not isinstance(item, str) or not item for item in answer["q4_answer"])):
        raise ValueError("q4_answer must contain exactly three nonblank manager names")


def write_answer(path, answer):
    directory = os.path.dirname(os.path.abspath(path))
    if not os.path.isdir(directory):
        raise FileNotFoundError("Output directory does not exist: {}".format(directory))
    temporary = path + ".tmp-{}".format(os.getpid())
    try:
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(answer, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main(config):
    q2_source = config.get("q2_source") or default_source("q2")
    q3_source = config.get("q3_source") or default_source("q3")
    output_path = config.get("output_path", "/root/answers.json")

    q2_coverpage = load_coverpage(q2_source)
    q3_coverpage = load_coverpage(q3_source)
    renaissance = resolve_manager(q3_coverpage, "renaissance technologies")
    berkshire_q2 = resolve_manager(q2_coverpage, "berkshire hathaway")
    berkshire_q3 = resolve_manager(q3_coverpage, "berkshire hathaway")

    aum, entries, q3_values, palantir_cusip, palantir_values = scan_q3(
        q3_source, renaissance["accession"], berkshire_q3["accession"]
    )
    q2_values = scan_values_by_cusip(q2_source, berkshire_q2["accession"])

    answer = {
        "q1_answer": json_number(aum),
        "q2_answer": entries,
        "q3_answer": top_increases(q2_values, q3_values),
        "q4_answer": top_palantir_managers(palantir_values, q3_coverpage, palantir_cusip),
    }
    validate_answer(answer)
    write_answer(output_path, answer)
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
