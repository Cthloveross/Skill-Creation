#!/usr/bin/env python3
"""Validate structural and formula requirements of a built Dots worksheet.

JSON input:
{
  "workbook_path": "completed.xlsx",
  "source_sheet": "Data",
  "output_sheet": "Dots",
  "require_cached_values": false
}
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

from dots_common import discover_headers, source_record_rows


def validate(config: dict) -> dict:
    workbook_path = Path(config["workbook_path"])
    source_sheet = config.get("source_sheet", "Data")
    output_sheet = config.get("output_sheet", "Dots")
    require_cached = bool(config.get("require_cached_values", False))
    if not workbook_path.is_file():
        raise FileNotFoundError(f"Workbook does not exist: {workbook_path}")

    formulas_book = load_workbook(workbook_path, data_only=False)
    if source_sheet not in formulas_book.sheetnames or output_sheet not in formulas_book.sheetnames:
        raise ValueError(f"Required sheets missing; found {formulas_book.sheetnames}")
    source = formulas_book[source_sheet]
    output = formulas_book[output_sheet]
    header = discover_headers(source)
    source_rows = source_record_rows(source, header)
    selected = sorted(header.fields.items(), key=lambda item: item[1])

    errors = []
    for out_col, (_, source_col) in enumerate(selected, start=1):
        expected_header = source.cell(header.row, source_col).value
        if output.cell(1, out_col).value != expected_header:
            errors.append(
                f"Header mismatch at {get_column_letter(out_col)}1: "
                f"expected {expected_header!r}, found {output.cell(1, out_col).value!r}"
            )
    total_col = len(selected) + 1
    dots_col = total_col + 1
    if output.cell(1, total_col).value != "TotalKg":
        errors.append("Missing TotalKg header immediately after copied fields")
    if output.cell(1, dots_col).value != "Dots":
        errors.append("Missing Dots header immediately after TotalKg")

    for out_row, source_row in enumerate(source_rows, start=2):
        for out_col, (_, source_col) in enumerate(selected, start=1):
            if output.cell(out_row, out_col).value != source.cell(source_row, source_col).value:
                errors.append(f"Copied value mismatch at output row {out_row}, column {out_col}")
                break
        total_value = output.cell(out_row, total_col).value
        dots_value = output.cell(out_row, dots_col).value
        if not isinstance(total_value, str) or not total_value.startswith("="):
            errors.append(f"TotalKg formula missing at {get_column_letter(total_col)}{out_row}")
        if not isinstance(dots_value, str) or not dots_value.startswith("="):
            errors.append(f"Dots formula missing at {get_column_letter(dots_col)}{out_row}")
        if output.cell(out_row, total_col).number_format != "0.000":
            errors.append(f"TotalKg number format is not 0.000 at row {out_row}")
        if output.cell(out_row, dots_col).number_format != "0.000":
            errors.append(f"Dots number format is not 0.000 at row {out_row}")

    cached_checked = False
    if require_cached:
        cached_checked = True
        values_book = load_workbook(workbook_path, data_only=True)
        values = values_book[output_sheet]
        for row in range(2, len(source_rows) + 2):
            # Blank is allowed for incomplete source records. For formula cells
            # with complete input, a compatible engine must have produced a value.
            if values.cell(row, total_col).value is None:
                errors.append(f"No cached TotalKg value after recalculation at row {row}")
            if values.cell(row, dots_col).value is None:
                errors.append(f"No cached Dots value after recalculation at row {row}")

    return {
        "ok": not errors,
        "workbook_path": str(workbook_path),
        "records_checked": len(source_rows),
        "cached_values_checked": cached_checked,
        "errors": errors,
    }


def main() -> None:
    try:
        result = validate(json.load(sys.stdin))
        print(json.dumps(result, ensure_ascii=False))
        if not result["ok"]:
            raise SystemExit(1)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
