#!/usr/bin/env python3
"""Create a joined demographic workbook with real openpyxl pivot definitions.

Reads a JSON request from stdin and writes a JSON audit/result to stdout.
"""
from __future__ import annotations

import json
import math
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


MISSING_TOKENS = {"", "na", "n/a", "null", "none", "np", "not publishable", "-", ".."}


def text(value: Any) -> str:
    """Return a trimmed, single-line textual representation."""
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def norm_header(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]+", "", text(value).upper())


def unique_headers(values: Sequence[Any]) -> List[str]:
    result: List[str] = []
    counts: Counter[str] = Counter()
    for i, value in enumerate(values, start=1):
        base = text(value) or f"COLUMN_{i}"
        counts[base] += 1
        result.append(base if counts[base] == 1 else f"{base}_{counts[base]}")
    return result


def as_number(value: Any) -> Optional[float]:
    """Parse common exported numeric formatting; return None for suppression/missing."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        numeric = float(value)
        return numeric if math.isfinite(numeric) else None
    raw = text(value)
    if raw.lower() in MISSING_TOKENS:
        return None
    cleaned = raw.replace(",", "").replace("$", "").replace("%", "")
    cleaned = re.sub(r"^\((.*)\)$", r"-\1", cleaned)
    try:
        numeric = float(cleaned)
    except ValueError:
        return None
    return numeric if math.isfinite(numeric) else None


def numeric_or_blank(value: Any) -> Optional[Any]:
    numeric = as_number(value)
    if numeric is None:
        return None
    return int(numeric) if numeric.is_integer() else numeric


def normalize_key(value: Any) -> str:
    """Preserve leading zeroes in text IDs but normalize numeric Excel/PDF rendering."""
    if value is None:
        return ""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if not math.isfinite(float(value)):
            return ""
        return str(int(value)) if float(value).is_integer() else format(float(value), ".15g")
    raw = text(value)
    if raw.lower() in MISSING_TOKENS:
        return ""
    # Excel/PDF frequently renders an integral identifier as 12345.0.
    if re.fullmatch(r"[0-9]+\.0+", raw):
        return raw.split(".", 1)[0]
    return re.sub(r"\s+", "", raw).upper()


def choose_field(headers: Sequence[str], role: str, required: bool = True) -> Optional[str]:
    """Find a supplied header by semantic role, without depending on positions."""
    norms = {header: norm_header(header) for header in headers}
    candidates: List[str] = []
    for header, n in norms.items():
        if role == "key":
            matched = ("SA2" in n and ("CODE" in n or n.startswith("SA2")))
        elif role == "population":
            matched = "POPULATION" in n or n in {"POP2023", "POP2023ESTIMATE"}
        elif role == "earners":
            matched = "EARNER" in n or n in {"NUMBEROFEARNERS", "NUMEARNERS"}
        elif role == "median_income":
            matched = "MEDIAN" in n and ("INCOME" in n or "EARNING" in n)
        elif role == "state":
            matched = n == "STATE" or n.startswith("STATE") or "STATENAME" in n
        else:
            raise ValueError(f"unknown field role {role}")
        if matched:
            candidates.append(header)
    if candidates:
        # Prefer the least ambiguous canonical-looking name, then first source order.
        preferred = {
            "key": {"SA2CODE", "SA2CODE2021", "SA2CODE2016"},
            "population": {"POPULATION2023", "POP2023"},
            "earners": {"EARNERS"},
            "median_income": {"MEDIANINCOME"},
            "state": {"STATE"},
        }[role]
        for candidate in candidates:
            if norms[candidate] in preferred:
                return candidate
        return candidates[0]
    if required:
        raise ValueError(f"could not identify a {role} column in headers: {list(headers)!r}")
    return None


def is_nonempty_row(row: Sequence[Any]) -> bool:
    return any(text(cell) for cell in row)


def read_income(path: Path) -> Tuple[List[str], List[Dict[str, Any]], Dict[str, str]]:
    from openpyxl import load_workbook

    wb = load_workbook(path, read_only=True, data_only=False)
    best: Optional[Tuple[List[str], List[List[Any]]]] = None
    best_score = -1
    for ws in wb.worksheets:
        sample = list(ws.iter_rows(min_row=1, max_row=min(ws.max_row, 40), values_only=True))
        for idx, raw_header in enumerate(sample):
            headers = unique_headers(raw_header)
            try:
                key = choose_field(headers, "key")
                earners = choose_field(headers, "earners")
                median = choose_field(headers, "median_income")
            except ValueError:
                continue
            score = int(key is not None) + int(earners is not None) + int(median is not None)
            if score > best_score:
                rows = [list(r) for r in ws.iter_rows(min_row=idx + 2, values_only=True)]
                best = (headers, rows)
                best_score = score
    wb.close()
    if best is None:
        raise ValueError("no income worksheet/header row contains SA2, EARNERS, and MEDIAN_INCOME")
    headers, raw_rows = best
    records: List[Dict[str, Any]] = []
    for raw in raw_rows:
        padded = raw[:len(headers)] + [None] * max(0, len(headers) - len(raw))
        record = {headers[i]: padded[i] for i in range(len(headers))}
        if is_nonempty_row(padded):
            records.append(record)
    if not records:
        raise ValueError("income worksheet has no data rows below its header")
    fields = {
        "key": choose_field(headers, "key"),
        "earners": choose_field(headers, "earners"),
        "median_income": choose_field(headers, "median_income"),
        "state": choose_field(headers, "state", required=False),
    }
    return headers, records, fields


def pdf_tables(path: Path) -> List[List[List[Any]]]:
    try:
        import pdfplumber
    except ImportError as exc:
        raise RuntimeError("pdfplumber is required to extract the supplied population PDF") from exc
    all_tables: List[List[List[Any]]] = []
    with pdfplumber.open(str(path)) as pdf:
        if not pdf.pages:
            raise ValueError("population PDF has no pages")
        for page in pdf.pages:
            tables = page.extract_tables()
            # A whitespace-aligned report may lack ruling lines. Try a text strategy then.
            if not tables:
                tables = page.extract_tables({
                    "vertical_strategy": "text", "horizontal_strategy": "text",
                    "intersection_tolerance": 5, "snap_tolerance": 4,
                })
            for table in tables or []:
                if table:
                    all_tables.append(table)
    return all_tables


def extract_population(path: Path) -> Tuple[List[str], List[Dict[str, Any]], Dict[str, str]]:
    tables = pdf_tables(path)
    chosen_headers: Optional[List[str]] = None
    raw_records: List[Dict[str, Any]] = []
    for table in tables:
        header_index: Optional[int] = None
        table_headers: Optional[List[str]] = None
        for index, row in enumerate(table[:8]):
            headers = unique_headers(row)
            try:
                choose_field(headers, "key")
                choose_field(headers, "population")
                header_index, table_headers = index, headers
                break
            except ValueError:
                continue
        if header_index is None or table_headers is None:
            continue
        if chosen_headers is None:
            chosen_headers = table_headers
        # Tables on later pages normally have the same heading. Map by normalized header
        # rather than relying on exactly identical whitespace/wrapping.
        for row in table[header_index + 1:]:
            if not is_nonempty_row(row):
                continue
            padded = list(row[:len(table_headers)]) + [None] * max(0, len(table_headers) - len(row))
            candidate = {table_headers[i]: padded[i] for i in range(len(table_headers))}
            try:
                local_key = choose_field(table_headers, "key")
                local_pop = choose_field(table_headers, "population")
            except ValueError:
                continue
            if (norm_header(candidate.get(local_key)) == norm_header(local_key) or
                    norm_header(candidate.get(local_pop)) == norm_header(local_pop)):
                continue  # repeated page header
            if not normalize_key(candidate.get(local_key)):
                continue  # page footer/title or malformed fragment
            raw_records.append(candidate)
    if chosen_headers is None or not raw_records:
        raise ValueError("could not extract a population table with SA2 and population columns from every usable PDF page")
    fields = {
        "key": choose_field(chosen_headers, "key"),
        "population": choose_field(chosen_headers, "population"),
        "state": choose_field(chosen_headers, "state", required=False),
    }
    # Require that extraction genuinely found population values, avoiding a shifted text table.
    if not any(as_number(row.get(fields["population"])) is not None for row in raw_records):
        raise ValueError("extracted population rows contain no numeric population values")
    return chosen_headers, raw_records, fields


def indexed(records: Iterable[Dict[str, Any]], key_field: str, source_name: str) -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}
    duplicates: List[str] = []
    for record in records:
        key = normalize_key(record.get(key_field))
        if not key:
            continue
        if key in result:
            duplicates.append(key)
        else:
            result[key] = record
    if duplicates:
        raise ValueError(f"{source_name} has duplicate SA2 identifiers (for example {duplicates[:5]!r})")
    if not result:
        raise ValueError(f"{source_name} contains no usable SA2 identifiers")
    return result


def copy_field_name(existing: List[str], preferred: str, provenance: str) -> str:
    if preferred not in existing:
        return preferred
    candidate = f"{provenance}_{preferred}"
    suffix = 2
    while candidate in existing:
        candidate = f"{provenance}_{preferred}_{suffix}"
        suffix += 1
    return candidate


def build_joined_rows(
    income_headers: List[str], income_rows: List[Dict[str, Any]], income_fields: Dict[str, str],
    pop_headers: List[str], pop_rows: List[Dict[str, Any]], pop_fields: Dict[str, str],
) -> Tuple[List[str], List[Dict[str, Any]], Dict[str, int]]:
    income_index = indexed(income_rows, income_fields["key"], "income workbook")
    pop_index = indexed(pop_rows, pop_fields["key"], "population PDF")
    common = sorted(set(income_index) & set(pop_index))
    if not common:
        raise ValueError("income and population sources have no overlapping SA2 identifiers")
    # Canonical analysis fields make the pivot schema unambiguous. All remaining source
    # columns are retained with deterministic source provenance when names collide.
    output_headers = ["SA2_CODE", "STATE", "POPULATION_2023", "EARNERS", "MEDIAN_INCOME"]
    income_extra = [h for h in income_headers if h not in {income_fields["key"], income_fields["earners"], income_fields["median_income"], income_fields.get("state")}]
    pop_extra = [h for h in pop_headers if h not in {pop_fields["key"], pop_fields["population"], pop_fields.get("state")}]
    income_mapped: Dict[str, str] = {}
    pop_mapped: Dict[str, str] = {}
    for header in income_extra:
        name = copy_field_name(output_headers, header, "INCOME")
        output_headers.append(name)
        income_mapped[header] = name
    for header in pop_extra:
        name = copy_field_name(output_headers, header, "POPULATION")
        output_headers.append(name)
        pop_mapped[header] = name

    rows: List[Dict[str, Any]] = []
    for key in common:
        inc, pop = income_index[key], pop_index[key]
        state = inc.get(income_fields["state"]) if income_fields.get("state") else pop.get(pop_fields["state"]) if pop_fields.get("state") else None
        if not text(state):
            raise ValueError(f"joined SA2 {key!r} has no STATE value in either source")
        row: Dict[str, Any] = {
            "SA2_CODE": key,
            "STATE": text(state),
            "POPULATION_2023": numeric_or_blank(pop.get(pop_fields["population"])),
            "EARNERS": numeric_or_blank(inc.get(income_fields["earners"])),
            "MEDIAN_INCOME": numeric_or_blank(inc.get(income_fields["median_income"])),
        }
        for source, target in income_mapped.items():
            row[target] = inc.get(source)
        for source, target in pop_mapped.items():
            row[target] = pop.get(source)
        rows.append(row)
    audit = {
        "income_rows_with_key": len(income_index), "population_rows_with_key": len(pop_index),
        "joined_rows": len(rows), "income_only_keys": len(set(income_index) - set(pop_index)),
        "population_only_keys": len(set(pop_index) - set(income_index)),
    }
    return output_headers, rows, audit


def add_derivations(headers: List[str], rows: List[Dict[str, Any]]) -> Tuple[List[str], Tuple[float, float, float, float, float]]:
    incomes = [float(row["MEDIAN_INCOME"]) for row in rows if row.get("MEDIAN_INCOME") is not None]
    if not incomes:
        raise ValueError("no numeric MEDIAN_INCOME values remain after joining; cannot make income ranges")
    low, high = min(incomes), max(incomes)
    width = (high - low) / 4.0
    boundaries = (low, low + width, low + 2 * width, low + 3 * width, high)
    for row in rows:
        income = row.get("MEDIAN_INCOME")
        if income is None:
            quarter = None
        elif width == 0:
            quarter = "Q1"
        elif income < boundaries[1]:
            quarter = "Q1"
        elif income < boundaries[2]:
            quarter = "Q2"
        elif income < boundaries[3]:
            quarter = "Q3"
        else:  # The maximum is deliberately included in Q4.
            quarter = "Q4"
        row["Quarter"] = quarter
        earners = row.get("EARNERS")
        row["Total"] = None if earners is None or income is None else earners * income
    return headers + ["Quarter", "Total"], boundaries


def make_pivot(target_ws: Any, cache: Any, source_headers: List[str], name: str,
               state_field: str, value_field: str, subtotal: str,
               quarter_field: Optional[str] = None) -> Any:
    from openpyxl.pivot.table import DataField, Location, PivotField, RowColField, TableDefinition

    state_index = source_headers.index(state_field)
    value_index = source_headers.index(value_field)
    quarter_index = source_headers.index(quarter_field) if quarter_field else None
    fields = []
    for index in range(len(source_headers)):
        if index == state_index:
            fields.append(PivotField(axis="axisRow"))
        elif quarter_index is not None and index == quarter_index:
            fields.append(PivotField(axis="axisCol"))
        elif index == value_index:
            fields.append(PivotField(dataField=True))
        else:
            fields.append(PivotField())
    # Location is the pivot object's output anchor. Excel calculates its true occupied range
    # after refreshing the cache on opening.
    pivot = TableDefinition(
        name=name, cacheId=0, dataCaption="Values",
        location=Location(ref="A3:Z1048576", firstHeaderRow=1, firstDataRow=1, firstDataCol=1),
        pivotFields=fields,
        rowFields=[RowColField(x=state_index)],
        colFields=[RowColField(x=quarter_index)] if quarter_index is not None else [],
        dataFields=[DataField(name=("Count of " if subtotal == "count" else "Sum of ") + value_field,
                              fld=value_index, subtotal=subtotal)],
    )
    pivot.cache = cache
    target_ws._pivots.append(pivot)
    return pivot


def write_workbook(output: Path, headers: List[str], rows: List[Dict[str, Any]]) -> None:
    from openpyxl import Workbook, load_workbook
    from openpyxl.pivot.cache import CacheDefinition, CacheField, CacheSource, WorksheetSource
    from openpyxl.worksheet.table import Table, TableStyleInfo

    wb = Workbook()
    default = wb.active
    wb.remove(default)
    names = ["Population by State", "Earners by State", "Regions by State", "State Income Quartile", "SourceData"]
    sheets = {name: wb.create_sheet(name) for name in names}
    source = sheets["SourceData"]
    source.append(headers)
    for row in rows:
        source.append([row.get(header) for header in headers])
    source.freeze_panes = "A2"
    source.auto_filter.ref = f"A1:{__import__('openpyxl').utils.get_column_letter(len(headers))}{len(rows) + 1}"
    table_ref = source.auto_filter.ref
    table = Table(displayName="SourceDataTable", ref=table_ref)
    table.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showFirstColumn=False,
                                          showLastColumn=False, showRowStripes=True, showColumnStripes=False)
    source.add_table(table)

    source_ref = table_ref
    cache = CacheDefinition(
        cacheSource=CacheSource(type="worksheet", worksheetSource=WorksheetSource(ref=source_ref, sheet="SourceData")),
        cacheFields=[CacheField(name=header) for header in headers],
        refreshOnLoad=True, enableRefresh=True, saveData=False,
    )
    make_pivot(sheets["Population by State"], cache, headers, "PopulationByState", "STATE", "POPULATION_2023", "sum")
    make_pivot(sheets["Earners by State"], cache, headers, "EarnersByState", "STATE", "EARNERS", "sum")
    make_pivot(sheets["Regions by State"], cache, headers, "RegionsByState", "STATE", "SA2_CODE", "count")
    make_pivot(sheets["State Income Quartile"], cache, headers, "StateIncomeQuartile", "STATE", "EARNERS", "sum", "Quarter")
    output.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output)

    # Verify persisted OOXML/openpyxl pivot structures rather than merely worksheet values.
    checked = load_workbook(output, read_only=False, data_only=False)
    if checked.sheetnames != names:
        raise RuntimeError(f"saved workbook sheet layout changed unexpectedly: {checked.sheetnames!r}")
    if [cell.value for cell in checked["SourceData"][1]] != headers:
        raise RuntimeError("saved SourceData headers do not match the generated schema")
    for name in names[:4]:
        pivots = checked[name]._pivots
        if len(pivots) != 1:
            raise RuntimeError(f"{name!r} does not contain exactly one registered pivot table")
        pivot = pivots[0]
        if pivot.cache is None or len(pivot.cache.cacheFields) != len(headers):
            raise RuntimeError(f"{name!r} pivot cache field list is incomplete")
        if len(pivot.pivotFields) != len(headers) or not pivot.rowFields or not pivot.dataFields:
            raise RuntimeError(f"{name!r} pivot role/reference fields are incomplete")
    checked.close()


def main(request: Dict[str, Any]) -> Dict[str, Any]:
    income_path = Path(request.get("income_path", "/root/income.xlsx"))
    population_path = Path(request.get("population_pdf_path", "/root/population.pdf"))
    output_path = Path(request.get("output_path", "/root/demographic_analysis.xlsx"))
    if not income_path.is_file():
        raise FileNotFoundError(f"income workbook not found: {income_path}")
    if not population_path.is_file():
        raise FileNotFoundError(f"population PDF not found: {population_path}")
    income_headers, income_rows, income_fields = read_income(income_path)
    pop_headers, pop_rows, pop_fields = extract_population(population_path)
    headers, rows, audit = build_joined_rows(income_headers, income_rows, income_fields, pop_headers, pop_rows, pop_fields)
    headers, bounds = add_derivations(headers, rows)
    write_workbook(output_path, headers, rows)
    return {
        "ok": True, "output_path": str(output_path), "source_headers": headers,
        "audit": audit,
        "income_range_boundaries": {"min": bounds[0], "q1_q2": bounds[1], "q2_q3": bounds[2], "q3_q4": bounds[3], "max": bounds[4]},
        "quarter_method": "equal-width MEDIAN_INCOME ranges; upper boundary belongs to Q4",
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("stdin JSON must be an object")
        result = main(payload)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, default=str))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        sys.exit(1)
