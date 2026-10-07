#!/usr/bin/env python3
"""Write requested GCC trade/GDP formulas while preserving an XLSX template.

stdin:  {"input_path": "/path/in.xlsx", "output_path": "/path/out.xlsx"}
stdout: JSON status, inferred schema, and formula counts.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any

import openpyxl
from openpyxl.utils import get_column_letter

TASK, DATA = "Task", "Data"
SRC_FIRST, SRC_LAST = 21, 40
BLOCKS = ((12, 17), (19, 24), (26, 31))
C1, C2 = 8, 12  # H:L
NET1, NET2 = 35, 40


class SchemaError(ValueError):
    pass


def canon(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, bool):
        return str(v).lower()
    if isinstance(v, (int, float)):
        return str(int(v)) if float(v).is_integer() else format(float(v), ".15g")
    return str(v).strip()


def kind(v: Any) -> str:
    if isinstance(v, bool): return "bool"
    if isinstance(v, (datetime, date)): return "date"
    if isinstance(v, (int, float)): return "number"
    if isinstance(v, str): return "text"
    return type(v).__name__


def ref(col: int, row: int, absolute: bool = True) -> str:
    letter = get_column_letter(col)
    return f"${letter}${row}" if absolute else f"{letter}{row}"


def qsheet(name: str) -> str:
    return "'" + name.replace("'", "''") + "'"


def target_codes(task) -> list[Any]:
    result = []
    for first, last in BLOCKS:
        for row in range(first, last + 1):
            value = task.cell(row, 4).value
            if not canon(value):
                raise SchemaError(f"Task!D{row} is blank; a series-code key is required.")
            result.append(value)
    return result


def find_code_column(data, codes: list[Any]) -> int:
    needed = Counter(canon(v) for v in codes)
    candidates = []
    for col in range(1, data.max_column + 1):
        available = Counter(canon(data.cell(row, col).value) for row in range(SRC_FIRST, SRC_LAST + 1))
        if all(available[key] == count for key, count in needed.items()):
            candidates.append(col)
    if len(candidates) != 1:
        raise SchemaError("Could not identify one Data source-code column with exact Task-key matches "
                          f"in rows 21:40 (candidates: {candidates or 'none'}).")
    return candidates[0]


def task_period_candidates(task, col: int) -> list[tuple[int, Any]]:
    """Nonblank possible period keys in this output column, preferring row 10."""
    found = [(row, task.cell(row, col).value) for row in range(1, 12)
             if canon(task.cell(row, col).value)]
    return sorted(found, key=lambda item: (abs(item[0] - 10), -item[0]))


def find_period_schema(task, data) -> tuple[int, list[int], list[tuple[int, int]]]:
    """Return Data header row, source columns, and (Task column, Task key row)."""
    possibilities = []
    for header_row in range(1, SRC_FIRST):
        source_cols, task_keys = [], []
        valid = True
        for col in range(C1, C2 + 1):
            chosen = None
            for task_row, value in task_period_candidates(task, col):
                matches = [dc for dc in range(1, data.max_column + 1)
                           if canon(data.cell(header_row, dc).value) == canon(value)]
                if len(matches) == 1 and kind(data.cell(header_row, matches[0]).value) == kind(value):
                    chosen = (matches[0], task_row)
                    break
            if chosen is None:
                valid = False
                break
            source_cols.append(chosen[0])
            task_keys.append((col, chosen[1]))
        if valid and len(set(source_cols)) == len(source_cols):
            possibilities.append((header_row, source_cols, task_keys))
    if not possibilities:
        raise SchemaError("No Data header row and same-column Task period keys could be matched uniquely.")
    # The header directly above the source table is the most likely source header.
    return max(possibilities, key=lambda x: x[0])


def norm(v: Any) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", str(v or "").lower())).strip()


def summary_type(task, row: int) -> str | None:
    text = " ".join(norm(task.cell(row, col).value) for col in range(1, task.max_column + 1)
                    if not C1 <= col <= C2)
    if "weighted" in text and ("mean" in text or "average" in text): return "weighted"
    if ("25" in text and ("percent" in text or "quart" in text)) or "first quartile" in text: return "p25"
    if ("75" in text and ("percent" in text or "quart" in text)) or "third quartile" in text: return "p75"
    if "median" in text: return "median"
    if "minimum" in text or re.search(r"\bmin\b", text): return "min"
    if "maximum" in text or re.search(r"\bmax\b", text): return "max"
    if "mean" in text or "average" in text: return "mean"
    return None


def find_summary_rows(task) -> dict[str, int]:
    found = {key: [] for key in ("min", "max", "median", "mean", "p25", "p75", "weighted")}
    for row in range(NET2 + 1, task.max_row + 1):
        what = summary_type(task, row)
        if what in found: found[what].append(row)
    bad = {k: v for k, v in found.items() if len(v) != 1}
    if bad:
        raise SchemaError(f"Could not identify one row for each required summary label: {bad!r}.")
    return {k: v[0] for k, v in found.items()}


def populate(input_path: str, output_path: str) -> dict[str, Any]:
    src, dst = Path(input_path), Path(output_path)
    if src.suffix.lower() != ".xlsx" or dst.suffix.lower() != ".xlsx":
        raise SchemaError("Only .xlsx input and output paths are supported.")
    if not src.is_file(): raise FileNotFoundError(f"Workbook not found: {src}")
    wb = openpyxl.load_workbook(src, data_only=False)
    if TASK not in wb.sheetnames or DATA not in wb.sheetnames:
        raise SchemaError("Workbook must contain existing Task and Data sheets.")
    task, data = wb[TASK], wb[DATA]
    code_col = find_code_column(data, target_codes(task))
    header_row, source_year_cols, period_keys = find_period_schema(task, data)
    summaries = find_summary_rows(task)

    first, last = min(source_year_cols), max(source_year_cols)
    ds = qsheet(DATA)
    vals = f"{ds}!${get_column_letter(first)}${SRC_FIRST}:${get_column_letter(last)}${SRC_LAST}"
    codes = f"{ds}!${get_column_letter(code_col)}${SRC_FIRST}:${get_column_letter(code_col)}${SRC_LAST}"
    heads = f"{ds}!${get_column_letter(first)}${header_row}:${get_column_letter(last)}${header_row}"
    key_rows = dict(period_keys)

    lookups = []
    for start, end in BLOCKS:
        for row in range(start, end + 1):
            for col in range(C1, C2 + 1):
                # Keys remain Task-local and copy safely across a row/column.
                formula = (f"=INDEX({vals},MATCH($D{row},{codes},0),"
                           f"MATCH({ref(col, key_rows[col])},{heads},0))")
                task.cell(row, col).value = formula
                lookups.append(task.cell(row, col).coordinate)

    net_cells = []
    for row in range(NET1, NET2 + 1):
        offset = row - NET1
        export_row, import_row, gdp_row = 12 + offset, 19 + offset, 26 + offset
        for col in range(C1, C2 + 1):
            letter = get_column_letter(col)
            task.cell(row, col).value = f"=({letter}{export_row}-{letter}{import_row})/{letter}{gdp_row}*100"
            net_cells.append(task.cell(row, col).coordinate)

    templates = {
        "min": "=MIN({c}$35:{c}$40)", "max": "=MAX({c}$35:{c}$40)",
        "median": "=MEDIAN({c}$35:{c}$40)", "mean": "=AVERAGE({c}$35:{c}$40)",
        "p25": "=PERCENTILE.INC({c}$35:{c}$40,0.25)",
        "p75": "=PERCENTILE.INC({c}$35:{c}$40,0.75)",
        "weighted": "=SUMPRODUCT({c}$35:{c}$40,{c}$26:{c}$31)/SUM({c}$26:{c}$31)",
    }
    summary_count = 0
    for name, row in summaries.items():
        for col in range(C1, C2 + 1):
            task.cell(row, col).value = templates[name].format(c=get_column_letter(col))
            summary_count += 1
    try:
        wb.calculation.fullCalcOnLoad = True
        wb.calculation.forceFullCalc = True
        wb.calculation.calcMode = "auto"
    except AttributeError:
        pass
    dst.parent.mkdir(parents=True, exist_ok=True)
    wb.save(dst)
    check = openpyxl.load_workbook(dst, data_only=False, read_only=True)
    sheet = check[TASK]
    for cell in lookups + net_cells:
        if not isinstance(sheet[cell].value, str) or not sheet[cell].value.startswith("="):
            raise RuntimeError(f"Formula did not persist in Task!{cell}.")
    check.close()
    return {"ok": True, "output_path": str(dst), "source_code_column": get_column_letter(code_col),
            "source_year_header_row": header_row,
            "task_period_key_cells": [f"{get_column_letter(c)}{r}" for c, r in period_keys],
            "lookup_formula_count": len(lookups), "net_export_formula_count": len(net_cells),
            "summary_rows": summaries, "summary_formula_count": summary_count,
            "calculation_note": "Formulas were written; recalculate in a compatible spreadsheet engine for cached values."}


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict): raise SchemaError("stdin must be a JSON object.")
        inp = payload.get("input_path", "/root/gdp.xlsx")
        out = payload.get("output_path", inp)
        if not isinstance(inp, str) or not isinstance(out, str): raise SchemaError("Paths must be strings.")
        print(json.dumps(populate(inp, out), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ok": False, "error_type": type(exc).__name__, "error": str(exc)}, sort_keys=True))
        sys.exit(1)

if __name__ == "__main__":
    main()
