#!/usr/bin/env python3
"""Create a demographic workbook with actual registered OOXML pivot tables.

Input: JSON object on stdin with optional income_path, population_pdf_path, output_path.
Output: JSON result on stdout.  Source income values are preserved verbatim; only
separate parsing for the derived fields treats suppression markers as missing.
"""
from __future__ import annotations

import json
import math
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

MISSING = {"", "na", "n/a", "null", "none", "np", "not publishable", "-", ".."}
SHEETS = ["Population by State", "Earners by State", "Regions by State", "State Income Quartile", "SourceData"]


def txt(v: Any) -> str:
    return "" if v is None else re.sub(r"\s+", " ", str(v)).strip()


def norm(v: Any) -> str:
    return re.sub(r"[^A-Z0-9]+", "", txt(v).upper())


def headers(values: tuple | list) -> list[str]:
    counts: Counter[str] = Counter()
    result = []
    for n, value in enumerate(values, 1):
        base = txt(value) or f"COLUMN_{n}"
        counts[base] += 1
        result.append(base if counts[base] == 1 else f"{base}_{counts[base]}")
    return result


def number(v: Any) -> float | None:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        out = float(v)
        return out if math.isfinite(out) else None
    raw = txt(v)
    if raw.lower() in MISSING:
        return None
    raw = raw.replace(",", "").replace("$", "").replace("%", "")
    raw = re.sub(r"^\((.*)\)$", r"-\1", raw)
    try:
        out = float(raw)
    except ValueError:
        return None
    return out if math.isfinite(out) else None


def number_or_blank(v: Any) -> int | float | None:
    out = number(v)
    if out is None:
        return None
    return int(out) if out.is_integer() else out


def key(v: Any) -> str:
    """Join-key normalization without changing values copied into SourceData."""
    if v is None or isinstance(v, bool):
        return ""
    if isinstance(v, (int, float)):
        if not math.isfinite(float(v)):
            return ""
        return str(int(v)) if float(v).is_integer() else format(float(v), ".15g")
    raw = txt(v)
    if raw.lower() in MISSING:
        return ""
    if re.fullmatch(r"[0-9]+\.0+", raw):
        raw = raw.split(".", 1)[0]
    return re.sub(r"\s+", "", raw).upper()


def field(cols: list[str], role: str, required: bool = True) -> str | None:
    candidates = []
    for col in cols:
        n = norm(col)
        matched = {
            "key": "SA2" in n and ("CODE" in n or n.startswith("SA2")),
            "population": "POPULATION" in n or n in {"POP2023", "POP2023ESTIMATE"},
            "earners": "EARNER" in n or n in {"NUMBEROFEARNERS", "NUMEARNERS"},
            "median": "MEDIAN" in n and ("INCOME" in n or "EARNING" in n),
            "state": n == "STATE" or n.startswith("STATE") or "STATENAME" in n,
        }[role]
        if matched:
            candidates.append(col)
    if not candidates:
        if required:
            raise ValueError(f"could not identify {role} column in {cols!r}")
        return None
    preferred = {
        "key": {"SA2CODE", "SA2CODE2021", "SA2CODE2016"},
        "population": {"POPULATION2023", "POP2023"},
        "earners": {"EARNERS"}, "median": {"MEDIANINCOME"}, "state": {"STATE"},
    }[role]
    return next((x for x in candidates if norm(x) in preferred), candidates[0])


def nonblank(values: list | tuple) -> bool:
    return any(txt(v) for v in values)


def income_records(path: Path) -> tuple[list[str], list[dict], dict]:
    from openpyxl import load_workbook
    wb = load_workbook(path, read_only=True, data_only=False)
    selected = None
    for ws in wb.worksheets:
        sample = list(ws.iter_rows(min_row=1, max_row=min(40, ws.max_row), values_only=True))
        for rowno, row in enumerate(sample):
            cols = headers(row)
            try:
                field(cols, "key"); field(cols, "earners"); field(cols, "median")
            except ValueError:
                continue
            selected = (cols, list(ws.iter_rows(min_row=rowno + 2, values_only=True)))
            break
        if selected:
            break
    wb.close()
    if selected is None:
        raise ValueError("income workbook has no table containing SA2, EARNERS, and MEDIAN_INCOME")
    cols, raw_rows = selected
    records = []
    for raw in raw_rows:
        padded = list(raw[:len(cols)]) + [None] * max(0, len(cols) - len(raw))
        if nonblank(padded):
            records.append(dict(zip(cols, padded)))
    if not records:
        raise ValueError("income table has no data rows")
    return cols, records, {"key": field(cols, "key"), "earners": field(cols, "earners"),
                           "median": field(cols, "median"), "state": field(cols, "state", False)}


def population_records(path: Path) -> tuple[list[str], list[dict], dict]:
    try:
        import pdfplumber
    except ImportError as exc:
        raise RuntimeError("pdfplumber is required for population PDF extraction") from exc
    found_cols = None
    records = []
    with pdfplumber.open(str(path)) as pdf:
        if not pdf.pages:
            raise ValueError("population PDF has no pages")
        for page in pdf.pages:
            tables = page.extract_tables()
            if not tables:
                tables = page.extract_tables({"vertical_strategy": "text", "horizontal_strategy": "text",
                                              "intersection_tolerance": 5, "snap_tolerance": 4})
            for table in tables or []:
                hit = None
                for i, row in enumerate(table[:8]):
                    cols = headers(row)
                    try:
                        field(cols, "key"); field(cols, "population")
                        hit = (i, cols)
                        break
                    except ValueError:
                        pass
                if hit is None:
                    continue
                rowstart, cols = hit
                if found_cols is None:
                    found_cols = cols
                kcol, pcol = field(cols, "key"), field(cols, "population")
                for raw in table[rowstart + 1:]:
                    padded = list(raw[:len(cols)]) + [None] * max(0, len(cols) - len(raw))
                    rec = dict(zip(cols, padded))
                    if not nonblank(padded) or not key(rec[kcol]):
                        continue
                    # Repeated page heading.
                    if norm(rec[kcol]) == norm(kcol) or norm(rec[pcol]) == norm(pcol):
                        continue
                    records.append(rec)
    if found_cols is None or not records:
        raise ValueError("could not extract a population table with SA2 and population columns")
    schema = {"key": field(found_cols, "key"), "population": field(found_cols, "population"),
              "state": field(found_cols, "state", False)}
    if not any(number(rec.get(schema["population"])) is not None for rec in records):
        raise ValueError("extracted population records have no numeric population values")
    return found_cols, records, schema


def index_rows(rows: list[dict], key_col: str, label: str) -> dict[str, dict]:
    result, duplicates = {}, []
    for rec in rows:
        k = key(rec.get(key_col))
        if not k:
            continue
        if k in result:
            duplicates.append(k)
        else:
            result[k] = rec
    if duplicates:
        raise ValueError(f"{label} has duplicate SA2 identifiers, including {duplicates[:5]!r}")
    if not result:
        raise ValueError(f"{label} has no usable SA2 identifiers")
    return result


def available(base: str, existing: list[str], prefix: str) -> str:
    if base not in existing:
        return base
    candidate, n = f"{prefix}_{base}", 2
    while candidate in existing:
        candidate, n = f"{prefix}_{base}_{n}", n + 1
    return candidate


def join_sources(ih: list[str], ir: list[dict], inf: dict, ph: list[str], pr: list[dict], pnf: dict):
    incomes, populations = index_rows(ir, inf["key"], "income workbook"), index_rows(pr, pnf["key"], "population PDF")
    shared = sorted(set(incomes) & set(populations))
    if not shared:
        raise ValueError("income and population sources have no overlapping SA2 identifiers")
    cols = ["SA2_CODE", "STATE", "POPULATION_2023", "EARNERS", "MEDIAN_INCOME"]
    excluded_i = {inf["key"], inf["earners"], inf["median"], inf.get("state")}
    excluded_p = {pnf["key"], pnf["population"], pnf.get("state")}
    imap, pmap = {}, {}
    for source, mapping, excluded, prefix in ((ih, imap, excluded_i, "INCOME"), (ph, pmap, excluded_p, "POPULATION")):
        for h in source:
            if h not in excluded:
                target = available(h, cols, prefix)
                cols.append(target)
                mapping[h] = target
    rows = []
    for k in shared:
        inc, pop = incomes[k], populations[k]
        state = inc.get(inf["state"]) if inf.get("state") else pop.get(pnf["state"]) if pnf.get("state") else None
        if not txt(state):
            raise ValueError(f"joined SA2 {k!r} has no STATE value")
        # Important: income fields intentionally retain the exact supplied values.
        row = {"SA2_CODE": inc.get(inf["key"]), "STATE": txt(state),
               "POPULATION_2023": number_or_blank(pop.get(pnf["population"])),
               "EARNERS": inc.get(inf["earners"]), "MEDIAN_INCOME": inc.get(inf["median"])}
        for source, target in imap.items():
            row[target] = inc.get(source)
        for source, target in pmap.items():
            row[target] = pop.get(source)
        rows.append(row)
    audit = {"income_rows_with_key": len(incomes), "population_rows_with_key": len(populations),
             "joined_rows": len(rows), "income_only_keys": len(set(incomes) - set(populations)),
             "population_only_keys": len(set(populations) - set(incomes))}
    return cols, rows, audit


def derive(cols: list[str], rows: list[dict]) -> tuple[list[str], tuple[float, float, float, float, float]]:
    valid = [number(r["MEDIAN_INCOME"]) for r in rows]
    valid = [v for v in valid if v is not None]
    if not valid:
        raise ValueError("no numeric MEDIAN_INCOME values remain after joining")
    lo, hi = min(valid), max(valid)
    width = (hi - lo) / 4
    bounds = (lo, lo + width, lo + 2 * width, lo + 3 * width, hi)
    for row in rows:
        earn, income = number(row["EARNERS"]), number(row["MEDIAN_INCOME"])
        if income is None:
            row["Quarter"] = None
        elif width == 0 or income < bounds[1]:
            row["Quarter"] = "Q1"
        elif income < bounds[2]:
            row["Quarter"] = "Q2"
        elif income < bounds[3]:
            row["Quarter"] = "Q3"
        else:
            row["Quarter"] = "Q4"
        row["Total"] = None if earn is None or income is None else earn * income
    return cols + ["Quarter", "Total"], bounds


def pivot(ws: Any, cache: Any, cols: list[str], name: str, value: str, subtotal: str, quarter: bool = False) -> None:
    from openpyxl.pivot.table import DataField, Location, PivotField, RowColField, TableDefinition
    state_i, value_i = cols.index("STATE"), cols.index(value)
    quarter_i = cols.index("Quarter") if quarter else None
    role_fields = []
    for i in range(len(cols)):
        role_fields.append(PivotField(axis="axisRow") if i == state_i else
                           PivotField(axis="axisCol") if i == quarter_i else
                           PivotField(dataField=True) if i == value_i else PivotField())
    definition = TableDefinition(name=name, cacheId=0, dataCaption="Values",
        location=Location(ref="A3:Z1048576", firstHeaderRow=1, firstDataRow=1, firstDataCol=1),
        pivotFields=role_fields, rowFields=[RowColField(x=state_i)],
        colFields=[RowColField(x=quarter_i)] if quarter else [],
        dataFields=[DataField(name=("Count of " if subtotal == "count" else "Sum of ") + value,
                              fld=value_i, subtotal=subtotal)])
    definition.cache = cache
    ws._pivots.append(definition)


def write_book(path: Path, cols: list[str], rows: list[dict]) -> None:
    from openpyxl import Workbook, load_workbook
    from openpyxl.pivot.cache import CacheDefinition, CacheField, CacheSource, WorksheetSource
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.table import Table, TableStyleInfo
    wb = Workbook()
    wb.remove(wb.active)
    ws = {name: wb.create_sheet(name) for name in SHEETS}
    source = ws["SourceData"]
    source.append(cols)
    for row in rows:
        source.append([row.get(c) for c in cols])
    source.freeze_panes = "A2"
    ref = f"A1:{get_column_letter(len(cols))}{len(rows) + 1}"
    source.auto_filter.ref = ref
    table = Table(displayName="SourceDataTable", ref=ref)
    table.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True,
                                          showFirstColumn=False, showLastColumn=False, showColumnStripes=False)
    source.add_table(table)
    cache = CacheDefinition(cacheSource=CacheSource(type="worksheet", worksheetSource=WorksheetSource(ref=ref, sheet="SourceData")),
                            cacheFields=[CacheField(name=c) for c in cols], refreshOnLoad=True,
                            enableRefresh=True, saveData=False)
    pivot(ws["Population by State"], cache, cols, "PopulationByState", "POPULATION_2023", "sum")
    pivot(ws["Earners by State"], cache, cols, "EarnersByState", "EARNERS", "sum")
    pivot(ws["Regions by State"], cache, cols, "RegionsByState", "SA2_CODE", "count")
    pivot(ws["State Income Quartile"], cache, cols, "StateIncomeQuartile", "EARNERS", "sum", True)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    check = load_workbook(path, data_only=False)
    try:
        if check.sheetnames != SHEETS:
            raise RuntimeError(f"saved sheet layout differs: {check.sheetnames!r}")
        if [c.value for c in check["SourceData"][1]] != cols:
            raise RuntimeError("saved SourceData headers differ from generated schema")
        for title in SHEETS[:4]:
            items = check[title]._pivots
            if len(items) != 1:
                raise RuntimeError(f"{title!r} does not have exactly one registered pivot")
            item = items[0]
            if item.cache is None or len(item.cache.cacheFields) != len(cols):
                raise RuntimeError(f"{title!r} has an incomplete pivot cache schema")
            if len(item.pivotFields) != len(cols) or not item.rowFields or not item.dataFields:
                raise RuntimeError(f"{title!r} has incomplete pivot role references")
    finally:
        check.close()


def main(request: dict) -> dict:
    income = Path(request.get("income_path", "/root/income.xlsx"))
    population = Path(request.get("population_pdf_path", "/root/population.pdf"))
    output = Path(request.get("output_path", "/root/demographic_analysis.xlsx"))
    if not income.is_file():
        raise FileNotFoundError(f"income workbook not found: {income}")
    if not population.is_file():
        raise FileNotFoundError(f"population PDF not found: {population}")
    ih, ir, inf = income_records(income)
    ph, pr, pnf = population_records(population)
    cols, rows, audit = join_sources(ih, ir, inf, ph, pr, pnf)
    cols, bounds = derive(cols, rows)
    write_book(output, cols, rows)
    return {"ok": True, "output_path": str(output), "source_headers": cols, "audit": audit,
            "income_range_boundaries": {"min": bounds[0], "q1_q2": bounds[1], "q2_q3": bounds[2], "q3_q4": bounds[3], "max": bounds[4]},
            "quarter_method": "equal-width MEDIAN_INCOME ranges; upper boundary belongs to Q4"}


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("stdin JSON must be an object")
        print(json.dumps(main(payload), ensure_ascii=False, sort_keys=True, default=str))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        sys.exit(1)
