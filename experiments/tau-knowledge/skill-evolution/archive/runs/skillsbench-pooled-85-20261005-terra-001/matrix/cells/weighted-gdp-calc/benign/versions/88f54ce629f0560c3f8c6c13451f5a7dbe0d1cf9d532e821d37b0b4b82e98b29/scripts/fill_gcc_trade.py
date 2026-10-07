#!/usr/bin/env python3
"""Populate a GCC trade/GDP formula template without changing workbook layout.

stdin JSON schema:
  {"input_path": "/path/in.xlsx", "output_path": "/path/out.xlsx"}
output_path is optional and defaults to input_path.
stdout JSON reports the written formula ranges and inferred lookup metadata.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

import openpyxl
from openpyxl.utils import get_column_letter

TASK_SHEET = "Task"
DATA_SHEET = "Data"
SOURCE_FIRST_ROW = 21
SOURCE_LAST_ROW = 40
LOOKUP_BLOCKS = ((12, 17), (19, 24), (26, 31))
YEAR_ROW = 10
YEAR_FIRST_COL = 8  # H
YEAR_LAST_COL = 12  # L
NET_FIRST_ROW = 35
NET_LAST_ROW = 40


class WorkbookSchemaError(ValueError):
    """Raised where formula generation would otherwise require a guess."""


def _display(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _canonical(value: Any) -> str:
    """A comparison key used only for schema discovery, never in written formulas."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, (int, float)):
        if float(value).is_integer():
            return str(int(value))
        return format(float(value), ".15g")
    return str(value).strip()


def _native_kind(value: Any) -> str:
    """Kinds Excel MATCH can compare without implicit text/number conversion."""
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (datetime, date)):
        return "date"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "text"
    return type(value).__name__


def _a1(col: int, row: int, absolute: bool = False) -> str:
    letter = get_column_letter(col)
    return f"${letter}${row}" if absolute else f"{letter}{row}"


def _quote_sheet(name: str) -> str:
    return "'" + name.replace("'", "''") + "'"


def _target_codes(task) -> List[Any]:
    values: List[Any] = []
    for first, last in LOOKUP_BLOCKS:
        for row in range(first, last + 1):
            value = task.cell(row, 4).value
            if _canonical(value) == "":
                raise WorkbookSchemaError(f"Task!D{row} is blank; a series code is required.")
            values.append(value)
    return values


def _periods(task) -> List[Any]:
    values = [task.cell(YEAR_ROW, col).value for col in range(YEAR_FIRST_COL, YEAR_LAST_COL + 1)]
    if any(_canonical(v) == "" for v in values):
        raise WorkbookSchemaError("Task!H10:L10 must all contain period keys.")
    if len({_canonical(v) for v in values}) != len(values):
        raise WorkbookSchemaError("Task!H10:L10 contains duplicate period keys.")
    return values


def _find_code_column(data, codes: Sequence[Any]) -> int:
    wanted = Counter(_canonical(v) for v in codes)
    candidates: List[int] = []
    for col in range(1, data.max_column + 1):
        observed = Counter(_canonical(data.cell(row, col).value)
                           for row in range(SOURCE_FIRST_ROW, SOURCE_LAST_ROW + 1))
        if all(observed[key] == count for key, count in wanted.items()):
            candidates.append(col)
    if len(candidates) != 1:
        raise WorkbookSchemaError(
            "Could not identify one Data series-code column in rows 21:40 with exact "
            f"matches for all requested codes (candidate columns: {candidates or 'none'})."
        )
    return candidates[0]


def _find_year_header(data, periods: Sequence[Any]) -> Tuple[int, List[int]]:
    wanted = [_canonical(v) for v in periods]
    candidates: List[Tuple[int, List[int]]] = []
    for row in range(1, SOURCE_FIRST_ROW):
        found: List[int] = []
        valid = True
        for period, key in zip(periods, wanted):
            cols = [col for col in range(1, data.max_column + 1)
                    if _canonical(data.cell(row, col).value) == key]
            if len(cols) != 1:
                valid = False
                break
            source_value = data.cell(row, cols[0]).value
            if _native_kind(source_value) != _native_kind(period):
                raise WorkbookSchemaError(
                    f"Period {period!r} is {_native_kind(period)} on Task but "
                    f"{_native_kind(source_value)} in Data!{_a1(cols[0], row)}. "
                    "Excel MATCH requires compatible native types."
                )
            found.append(cols[0])
        if valid:
            candidates.append((row, found))
    if not candidates:
        raise WorkbookSchemaError("No Data header row above row 21 uniquely matches all Task periods.")
    # The header nearest the declared source observations is the relevant table header.
    row, cols = max(candidates, key=lambda item: item[0])
    return row, cols


def _normalized_text(value: Any) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", _display(value).lower())).strip()


def _summary_kind_for_row(task, row: int) -> str | None:
    # Search label text on the row but exclude the year-output cells themselves.
    text = " ".join(_normalized_text(task.cell(row, col).value)
                    for col in range(1, task.max_column + 1)
                    if not YEAR_FIRST_COL <= col <= YEAR_LAST_COL)
    if not text:
        return None
    if "weighted" in text and ("mean" in text or "average" in text):
        return "weighted"
    if (("25" in text and ("percent" in text or "quart" in text)) or
            "first quartile" in text):
        return "p25"
    if (("75" in text and ("percent" in text or "quart" in text)) or
            "third quartile" in text):
        return "p75"
    if "median" in text:
        return "median"
    if "minimum" in text or re.search(r"\bmin\b", text):
        return "min"
    if "maximum" in text or re.search(r"\bmax\b", text):
        return "max"
    if (("simple" in text or "arithmetic" in text) and ("mean" in text or "average" in text)):
        return "mean"
    # A plain mean/average is accepted only after weighted mean was excluded above.
    if "mean" in text or "average" in text:
        return "mean"
    return None


def _find_summary_rows(task) -> Dict[str, int]:
    expected = {"min", "max", "median", "mean", "p25", "p75", "weighted"}
    found: Dict[str, List[int]] = {kind: [] for kind in expected}
    for row in range(NET_LAST_ROW + 1, task.max_row + 1):
        kind = _summary_kind_for_row(task, row)
        if kind in found:
            found[kind].append(row)
    missing = sorted(kind for kind, rows in found.items() if not rows)
    duplicated = {kind: rows for kind, rows in found.items() if len(rows) > 1}
    if missing or duplicated:
        parts = []
        if missing:
            parts.append("missing labels: " + ", ".join(missing))
        if duplicated:
            parts.append("ambiguous labels: " + repr(duplicated))
        raise WorkbookSchemaError("Unable to locate unique summary rows (" + "; ".join(parts) + ").")
    return {kind: rows[0] for kind, rows in found.items()}


def _is_percent_format(number_format: str) -> bool:
    # Excel percent displays use %, including formats such as 0.0% or 0%;-0%.
    return "%" in (number_format or "")


def _net_formula(col: int, ratio_as_percent: bool) -> str:
    letter = get_column_letter(col)
    ratio = f"({letter}12-{letter}19)/{letter}26"
    return f"={ratio}" if ratio_as_percent else f"={ratio}*100"


def populate(input_path: str, output_path: str) -> Dict[str, Any]:
    source = Path(input_path)
    destination = Path(output_path)
    if source.suffix.lower() != ".xlsx" or destination.suffix.lower() != ".xlsx":
        raise WorkbookSchemaError("This Skill supports .xlsx input and output paths only.")
    if not source.is_file():
        raise FileNotFoundError(f"Workbook not found: {source}")

    wb = openpyxl.load_workbook(source, data_only=False)
    if TASK_SHEET not in wb.sheetnames or DATA_SHEET not in wb.sheetnames:
        raise WorkbookSchemaError("Workbook must contain existing sheets named Task and Data.")
    task = wb[TASK_SHEET]
    data = wb[DATA_SHEET]

    codes = _target_codes(task)
    periods = _periods(task)
    code_col = _find_code_column(data, codes)
    header_row, source_year_cols = _find_year_header(data, periods)
    summary_rows = _find_summary_rows(task)

    # Use a continuous source matrix bounded by the matched year columns. MATCH maps
    # each Task period to the appropriate column inside it.
    value_first_col, value_last_col = min(source_year_cols), max(source_year_cols)
    data_name = _quote_sheet(DATA_SHEET)
    values_ref = (f"{data_name}!${get_column_letter(value_first_col)}${SOURCE_FIRST_ROW}:"
                  f"${get_column_letter(value_last_col)}${SOURCE_LAST_ROW}")
    code_ref = (f"{data_name}!${get_column_letter(code_col)}${SOURCE_FIRST_ROW}:"
                f"${get_column_letter(code_col)}${SOURCE_LAST_ROW}")
    header_ref = (f"{data_name}!${get_column_letter(value_first_col)}${header_row}:"
                  f"${get_column_letter(value_last_col)}${header_row}")

    lookup_cells: List[str] = []
    for first, last in LOOKUP_BLOCKS:
        for row in range(first, last + 1):
            for col in range(YEAR_FIRST_COL, YEAR_LAST_COL + 1):
                destination_cell = task.cell(row, col)
                series_key = f"$D{row}"
                period_key = f"{get_column_letter(col)}${YEAR_ROW}"
                destination_cell.value = (
                    f"=INDEX({values_ref},MATCH({series_key},{code_ref},0),"
                    f"MATCH({period_key},{header_ref},0))"
                )
                lookup_cells.append(destination_cell.coordinate)

    # Preserve the template's existing unit convention: percent-formatted cells store
    # ratios; non-percent-formatted cells store percentage points.
    net_cells: List[str] = []
    unit_modes = set()
    for row in range(NET_FIRST_ROW, NET_LAST_ROW + 1):
        for col in range(YEAR_FIRST_COL, YEAR_LAST_COL + 1):
            cell = task.cell(row, col)
            ratio_as_percent = _is_percent_format(cell.number_format)
            unit_modes.add(ratio_as_percent)
            cell.value = _net_formula(col, ratio_as_percent)
            net_cells.append(cell.coordinate)
    if len(unit_modes) != 1:
        raise WorkbookSchemaError(
            "Net-export target cells mix percent and non-percent number formats; "
            "their formula units would be inconsistent."
        )
    ratio_as_percent = unit_modes.pop()

    statistic_templates = {
        "min": "=MIN({col}$35:{col}$40)",
        "max": "=MAX({col}$35:{col}$40)",
        "median": "=MEDIAN({col}$35:{col}$40)",
        "mean": "=AVERAGE({col}$35:{col}$40)",
        "p25": "=PERCENTILE.INC({col}$35:{col}$40,0.25)",
        "p75": "=PERCENTILE.INC({col}$35:{col}$40,0.75)",
        "weighted": "=SUMPRODUCT({col}$35:{col}$40,{col}$26:{col}$31)/SUM({col}$26:{col}$31)",
    }
    summary_cells: Dict[str, List[str]] = {kind: [] for kind in statistic_templates}
    for kind, row in summary_rows.items():
        for col in range(YEAR_FIRST_COL, YEAR_LAST_COL + 1):
            letter = get_column_letter(col)
            cell = task.cell(row, col)
            cell.value = statistic_templates[kind].format(col=letter)
            summary_cells[kind].append(cell.coordinate)

    # Request calculation by Excel/LibreOffice on next open without introducing VBA.
    try:
        wb.calculation.fullCalcOnLoad = True
        wb.calculation.forceFullCalc = True
        wb.calculation.calcMode = "auto"
    except AttributeError:
        # Older openpyxl versions may expose calculation properties differently;
        # formula structure remains valid even if these optional flags are unavailable.
        pass

    destination.parent.mkdir(parents=True, exist_ok=True)
    wb.save(destination)

    # Structural reopen: confirms formulas survived serialization. openpyxl cannot
    # calculate cached values, so this deliberately does not claim numeric validation.
    check = openpyxl.load_workbook(destination, data_only=False, read_only=True)
    checked_task = check[TASK_SHEET]
    for coordinate in lookup_cells + net_cells:
        if not isinstance(checked_task[coordinate].value, str) or not checked_task[coordinate].value.startswith("="):
            raise RuntimeError(f"Formula did not persist in Task!{coordinate}.")
    check.close()

    return {
        "ok": True,
        "output_path": str(destination),
        "source_code_column": get_column_letter(code_col),
        "source_year_header_row": header_row,
        "source_year_columns": [get_column_letter(c) for c in source_year_cols],
        "lookup_formula_count": len(lookup_cells),
        "net_export_formula_count": len(net_cells),
        "summary_rows": summary_rows,
        "summary_formula_count": sum(len(cells) for cells in summary_cells.values()),
        "net_export_unit": "ratio_with_percent_number_format" if ratio_as_percent else "percentage_points",
        "calculation_note": "Formulas were written and calculation-on-open was requested; use a spreadsheet engine to refresh cached values if required."
    }


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise WorkbookSchemaError("stdin must contain a JSON object.")
        input_path = payload.get("input_path", "/root/gdp.xlsx")
        output_path = payload.get("output_path", input_path)
        if not isinstance(input_path, str) or not isinstance(output_path, str):
            raise WorkbookSchemaError("input_path and output_path must be strings.")
        print(json.dumps(populate(input_path, output_path), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc), "error_type": type(exc).__name__}, sort_keys=True))
        sys.exit(1)


if __name__ == "__main__":
    main()
