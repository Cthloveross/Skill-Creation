#!/usr/bin/env python3
"""Stream quarterly 13F TSV tables and write an answers.json task response.

Input: JSON object on stdin as documented in SKILL.md.
Output: JSON diagnostic object on stdout; the required response is written to
output_path.  Raises a clear error on missing data or an ambiguous/incomplete
result instead of producing an invalid answer file.
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import sys
import zipfile
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Tuple


def clean(value: object) -> str:
    return "" if value is None else str(value).strip()


def normalized(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", clean(value).lower()).strip()


def field(row: Dict[str, str], name: str) -> str:
    """Get a TSV field despite a BOM or accidental header whitespace."""
    wanted = name.upper()
    for key, value in row.items():
        if clean(key).lstrip("\ufeff").upper() == wanted:
            return clean(value)
    return ""


def decimal_value(value: str) -> Decimal:
    text = clean(value).replace(",", "").replace("$", "")
    if not text:
        return Decimal(0)
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError("Invalid VALUE field: {!r}".format(value)) from exc


def name_score(query: str, candidate: str) -> float:
    """Deterministic fuzzy score emphasizing normalized token containment."""
    q, c = normalized(query), normalized(candidate)
    if not q or not c:
        return 0.0
    ratio = SequenceMatcher(None, q, c).ratio()
    qt, ct = set(q.split()), set(c.split())
    overlap = len(qt & ct) / len(qt) if qt else 0.0
    containment = 1.0 if q in c else 0.0
    return 0.55 * ratio + 0.35 * overlap + 0.10 * containment


class Dataset:
    """Read named TSV files from a directory tree or a ZIP archive."""

    def __init__(self, source: str):
        self.source = Path(source)
        if not self.source.exists():
            raise FileNotFoundError("Dataset source does not exist: " + str(self.source))
        self.is_zip = self.source.is_file() and zipfile.is_zipfile(self.source)
        if not self.is_zip and not self.source.is_dir():
            raise ValueError("Dataset must be a directory or a readable ZIP: " + str(self.source))

    def _member(self, table: str) -> str:
        wanted = table.lower()
        if self.is_zip:
            with zipfile.ZipFile(self.source) as archive:
                matches = [n for n in archive.namelist()
                           if not n.endswith("/") and Path(n).name.lower() == wanted]
            if not matches:
                raise FileNotFoundError("{} not found in {}".format(table, self.source))
            return sorted(matches, key=len)[0]
        matches = [p for p in self.source.rglob("*")
                   if p.is_file() and p.name.lower() == wanted]
        if not matches:
            raise FileNotFoundError("{} not found under {}".format(table, self.source))
        return str(sorted(matches, key=lambda p: len(str(p)))[0])

    def rows(self, table: str) -> Iterator[Dict[str, str]]:
        member = self._member(table)
        if self.is_zip:
            archive = zipfile.ZipFile(self.source)
            binary = archive.open(member, "r")
            text = io.TextIOWrapper(binary, encoding="utf-8-sig", errors="replace", newline="")
            try:
                yield from csv.DictReader(text, delimiter="\t")
            finally:
                text.close()
                archive.close()
        else:
            with open(member, "r", encoding="utf-8-sig", errors="replace", newline="") as text:
                yield from csv.DictReader(text, delimiter="\t")


def discover(quarter: str, supplied: Optional[str]) -> str:
    if supplied:
        return supplied
    root = Path("/root")
    candidates = [root / "2025-" / quarter, root / ("2025-" + quarter),
                  root / ("13f-2025-" + quarter + ".zip"),
                  root / ("2025-" + quarter + ".zip")]
    for item in candidates:
        if item.exists():
            return str(item)
    raise FileNotFoundError("Cannot discover {} dataset; provide {}_path".format(quarter, quarter))


def select_manager(data: Dataset, query: str) -> Tuple[str, str, float]:
    candidates: List[Tuple[float, int, str, str]] = []
    for row in data.rows("COVERPAGE.tsv"):
        name = field(row, "FILINGMANAGER_NAME")
        accession = field(row, "ACCESSION_NUMBER")
        if not name or not accession:
            continue
        # On an equal name score, prefer an original filing over an amendment.
        amendment_penalty = 1 if field(row, "ISAMENDMENT").upper() == "Y" else 0
        candidates.append((name_score(query, name), amendment_penalty, name, accession))
    if not candidates:
        raise ValueError("COVERPAGE.tsv contains no usable manager/accession rows")
    candidates.sort(key=lambda x: (-x[0], x[1], normalized(x[2]), x[3]))
    score, _, name, accession = candidates[0]
    if score < 0.45:
        raise ValueError("No credible COVERPAGE match for {!r}; best was {!r} ({:.3f})".format(query, name, score))
    return name, accession, score


def is_stock_share(row: Dict[str, str]) -> bool:
    """Task policy: a non-option share position, not a PRN debt position."""
    return (field(row, "SSHPRNAMTTYPE").upper() == "SH" and
            not field(row, "PUTCALL").strip())


def identify_issuer_cusip(data: Dataset, query: str) -> Tuple[str, str, float]:
    best: Optional[Tuple[float, str, str]] = None
    # Issuer strings recur across many rows; retain the highest-scoring valid CUSIP.
    for row in data.rows("INFOTABLE.tsv"):
        issuer = field(row, "NAMEOFISSUER")
        cusip = field(row, "CUSIP")
        if not issuer or not cusip:
            continue
        candidate = (name_score(query, issuer), issuer, cusip)
        if best is None or candidate[0] > best[0] or (candidate[0] == best[0] and candidate[2] < best[2]):
            best = candidate
    if best is None or best[0] < 0.45:
        raise ValueError("No credible INFOTABLE issuer match for {!r}".format(query))
    return best[2], best[1], best[0]


def scan_q3(data: Dataset, renaissance_accession: str, berkshire_accession: str,
            issuer_cusip: str, count_unit: str) -> Tuple[Decimal, int, Dict[str, Decimal], Dict[str, Decimal]]:
    aum = Decimal(0)
    stock_keys = set()
    stock_rows = 0
    berkshire = defaultdict(Decimal)
    holders = defaultdict(Decimal)
    for row in data.rows("INFOTABLE.tsv"):
        accession = field(row, "ACCESSION_NUMBER")
        cusip = field(row, "CUSIP")
        value = decimal_value(field(row, "VALUE"))
        if accession == renaissance_accession:
            aum += value
            if is_stock_share(row) and cusip:
                stock_rows += 1
                stock_keys.add(cusip)
        if accession == berkshire_accession and is_stock_share(row) and cusip:
            berkshire[cusip] += value
        if cusip == issuer_cusip:
            holders[accession] += value
    count = len(stock_keys) if count_unit == "unique_cusips" else stock_rows
    return aum, count, dict(berkshire), dict(holders)


def scan_berkshire(data: Dataset, accession_target: str) -> Dict[str, Decimal]:
    positions = defaultdict(Decimal)
    for row in data.rows("INFOTABLE.tsv"):
        if field(row, "ACCESSION_NUMBER") != accession_target or not is_stock_share(row):
            continue
        cusip = field(row, "CUSIP")
        if cusip:
            positions[cusip] += decimal_value(field(row, "VALUE"))
    return dict(positions)


def manager_names_for_accessions(data: Dataset, wanted: Iterable[str]) -> Dict[str, str]:
    targets = set(wanted)
    result: Dict[str, str] = {}
    for row in data.rows("COVERPAGE.tsv"):
        accession = field(row, "ACCESSION_NUMBER")
        if accession in targets and accession not in result:
            result[accession] = field(row, "FILINGMANAGER_NAME")
    return result


def json_number(value: Decimal):
    """Emit integer dollars where possible, while retaining valid decimal data."""
    if value == value.to_integral_value():
        return int(value)
    return float(value)


def validate_answer(answer: Dict[str, object]) -> None:
    if not isinstance(answer.get("q1_answer"), (int, float)):
        raise ValueError("q1_answer is not numeric")
    if not isinstance(answer.get("q2_answer"), int):
        raise ValueError("q2_answer is not an integer count")
    for key, length in (("q3_answer", 5), ("q4_answer", 3)):
        value = answer.get(key)
        if not isinstance(value, list) or len(value) != length or not all(isinstance(x, str) and x for x in value):
            raise ValueError("{} must be a {}-element list of nonempty strings".format(key, length))


def main() -> None:
    raw = sys.stdin.read().strip()
    config = json.loads(raw) if raw else {}
    if not isinstance(config, dict):
        raise ValueError("stdin must be a JSON object")
    unit = config.get("stock_count_unit", "unique_cusips")
    if unit not in {"unique_cusips", "rows"}:
        raise ValueError("stock_count_unit must be unique_cusips or rows")

    q2 = Dataset(discover("q2", config.get("q2_path")))
    q3 = Dataset(discover("q3", config.get("q3_path")))
    ren_name, ren_acc, ren_score = select_manager(q3, config.get("renaissance_query", "renaissance technologies"))
    berk_q2_name, berk_q2_acc, _ = select_manager(q2, config.get("berkshire_query", "berkshire hathaway"))
    berk_q3_name, berk_q3_acc, _ = select_manager(q3, config.get("berkshire_query", "berkshire hathaway"))
    pal_cusip, pal_issuer, pal_score = identify_issuer_cusip(q3, config.get("palantir_query", "palantir"))

    aum, stock_count, berk_q3, pal_holders = scan_q3(q3, ren_acc, berk_q3_acc, pal_cusip, unit)
    berk_q2 = scan_berkshire(q2, berk_q2_acc)
    increases = []
    for cusip in set(berk_q2) | set(berk_q3):
        change = berk_q3.get(cusip, Decimal(0)) - berk_q2.get(cusip, Decimal(0))
        if change > 0:
            increases.append((change, cusip))
    increases.sort(key=lambda item: (-item[0], item[1]))
    if len(increases) < 5:
        raise ValueError("Fewer than five Berkshire CUSIPs had positive Q3 dollar increases")

    name_map = manager_names_for_accessions(q3, pal_holders)
    ranked_holders = [(value, acc, name_map.get(acc, "")) for acc, value in pal_holders.items() if name_map.get(acc)]
    ranked_holders.sort(key=lambda item: (-item[0], normalized(item[2]), item[1]))
    if len(ranked_holders) < 3:
        raise ValueError("Fewer than three named Q3 holders found for issuer CUSIP " + pal_cusip)

    answer = {
        "q1_answer": json_number(aum),
        "q2_answer": stock_count,
        "q3_answer": [cusip for _, cusip in increases[:5]],
        "q4_answer": [name for _, _, name in ranked_holders[:3]],
    }
    validate_answer(answer)
    output = Path(config.get("output_path", "/root/answers.json"))
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8") as handle:
        json.dump(answer, handle, indent=2)
        handle.write("\n")
    print(json.dumps({
        "output_path": str(output), "answer": answer,
        "selected": {
            "renaissance": {"name": ren_name, "accession": ren_acc, "score": round(ren_score, 4)},
            "berkshire_q2": {"name": berk_q2_name, "accession": berk_q2_acc},
            "berkshire_q3": {"name": berk_q3_name, "accession": berk_q3_acc},
            "palantir": {"issuer": pal_issuer, "cusip": pal_cusip, "score": round(pal_score, 4)},
            "stock_count_unit": unit,
        },
    }, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("ERROR: " + str(error), file=sys.stderr)
        sys.exit(1)
