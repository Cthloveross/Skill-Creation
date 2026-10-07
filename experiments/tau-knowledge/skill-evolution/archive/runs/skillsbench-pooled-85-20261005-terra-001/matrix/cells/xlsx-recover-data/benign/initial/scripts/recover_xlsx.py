#!/usr/bin/env python3
"""Inspect, safely repair, and validate marker values in an xlsx workbook.

JSON is read from stdin and a single JSON object is written to stdout.
"""
import json
import math
import os
import re
import shutil
import sys
from datetime import date, datetime, time
from pathlib import Path

try:
    import openpyxl
except ImportError as exc:
    raise SystemExit(json.dumps({"ok": False, "error": "openpyxl is required", "detail": str(exc)}))

DEFAULT_MARKER = "???"
# Captures optional quoted/unquoted sheet qualifier and an A1 reference. This is an
# inventory aid, not a full Excel formula parser.
REF_RE = re.compile(r"(?:(?:'((?:[^']|'')+)'|([A-Za-z_][A-Za-z0-9_. ]*))!)?(\$?[A-Z]{1,3}\$?\d+)")


def fail(message, **extra):
    result = {"ok": False, "error": message}
    result.update(extra)
    print(json.dumps(result, ensure_ascii=False, default=str))
    raise SystemExit(1)


def json_value(value):
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return str(value)
    return value


def load(path):
    if not isinstance(path, str) or not path:
        fail("input_path must be a nonempty string")
    source = Path(path)
    if not source.is_file():
        fail("workbook does not exist", input_path=path)
    try:
        return openpyxl.load_workbook(source, data_only=False, keep_links=True)
    except Exception as exc:
        fail("unable to load workbook", detail=str(exc), input_path=path)


def exact_markers(wb, marker):
    targets = []
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                if cell.value == marker:
                    targets.append(f"{ws.title}!{cell.coordinate}")
    return targets


def formula_references(formula, current_sheet):
    refs = []
    for match in REF_RE.finditer(formula):
        quoted_sheet, plain_sheet, address = match.groups()
        sheet = quoted_sheet.replace("''", "'") if quoted_sheet is not None else plain_sheet
        refs.append({"sheet": sheet or current_sheet, "address": address.replace("$", "")})
    return refs


def inspect(wb, marker):
    sheets = []
    all_formulas = []
    for ws in wb.worksheets:
        cells = []
        for row in ws.iter_rows():
            for cell in row:
                if cell.value is None:
                    continue
                entry = {
                    "coordinate": cell.coordinate,
                    "value": json_value(cell.value),
                    "data_type": cell.data_type,
                    "number_format": cell.number_format,
                }
                if cell.data_type == "f" and isinstance(cell.value, str):
                    refs = formula_references(cell.value, ws.title)
                    entry["references"] = refs
                    all_formulas.append({"cell": f"{ws.title}!{cell.coordinate}", "formula": cell.value, "references": refs})
                cells.append(entry)
        sheets.append({
            "name": ws.title,
            "max_row": ws.max_row,
            "max_column": ws.max_column,
            "merged_ranges": [str(rng) for rng in ws.merged_cells.ranges],
            "hidden_rows": [idx for idx, dim in ws.row_dimensions.items() if dim.hidden],
            "hidden_columns": [idx for idx, dim in ws.column_dimensions.items() if dim.hidden],
            "nonempty_cells": cells,
        })
    return {
        "ok": True,
        "marker": marker,
        "marker_count": len(exact_markers(wb, marker)),
        "targets": exact_markers(wb, marker),
        "sheet_names": wb.sheetnames,
        "sheets": sheets,
        "formulas": all_formulas,
    }


def split_target(target, wb):
    if not isinstance(target, str) or "!" not in target:
        fail("repair address must be Sheet!A1", target=target)
    sheet_name, address = target.rsplit("!", 1)
    if sheet_name not in wb.sheetnames:
        fail("repair refers to an unknown worksheet", target=target)
    try:
        # This also rejects ranges such as A1:B2 when indexing below.
        cell = wb[sheet_name][address]
        if not hasattr(cell, "coordinate"):
            raise ValueError("not a single cell")
    except Exception:
        fail("repair address is not a valid single-cell A1 address", target=target)
    return sheet_name, cell.coordinate


def populated_snapshot(wb, excluded):
    """Values/types of populated non-target cells, used to catch accidental edits."""
    result = {}
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                key = f"{ws.title}!{cell.coordinate}"
                if key in excluded or cell.value is None:
                    continue
                result[key] = (cell.value, cell.data_type)
    return result


def require_number(value, target):
    # bool is an int subclass but should not be written as a recovered number.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        fail("each repair value must be a JSON number, not text", target=target, value=value)
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        fail("repair value must be finite", target=target)


def apply(payload):
    marker = payload.get("marker", DEFAULT_MARKER)
    if not isinstance(marker, str):
        fail("marker must be a string")
    input_path = payload.get("input_path")
    output_path = payload.get("output_path")
    if not isinstance(output_path, str) or not output_path:
        fail("output_path must be a nonempty string")
    if os.path.abspath(str(input_path)) == os.path.abspath(output_path):
        fail("output_path must differ from input_path")
    output = Path(output_path)
    if not output.parent.is_dir():
        fail("output directory does not exist", output_path=output_path)
    repairs = payload.get("repairs")
    if not isinstance(repairs, dict) or not repairs:
        fail("repairs must be a nonempty object mapping Sheet!A1 to JSON numbers")

    wb = load(input_path)
    original_targets = set(exact_markers(wb, marker))
    normalized = {}
    for target, value in repairs.items():
        require_number(value, target)
        sheet, address = split_target(target, wb)
        canonical = f"{sheet}!{address}"
        if canonical in normalized:
            fail("duplicate repair after address normalization", target=target)
        if canonical not in original_targets:
            fail("repairs may change only cells containing the original marker", target=canonical)
        normalized[canonical] = value

    allow_partial = payload.get("allow_partial", False)
    if not isinstance(allow_partial, bool):
        fail("allow_partial must be boolean")
    missing = sorted(original_targets - set(normalized))
    if missing and not allow_partial:
        fail("repair set does not cover every marker", missing_targets=missing)

    before = populated_snapshot(wb, set(normalized))
    # Start from a byte-level source copy so unrelated package parts are retained as
    # far as openpyxl's normal save behavior permits.
    try:
        shutil.copy2(input_path, output_path)
        out_wb = openpyxl.load_workbook(output_path, data_only=False, keep_links=True)
        target_formats = {}
        for canonical, value in normalized.items():
            sheet, address = canonical.rsplit("!", 1)
            cell = out_wb[sheet][address]
            target_formats[canonical] = cell.number_format
            cell.value = value
        out_wb.save(output_path)
    except Exception as exc:
        fail("unable to save repaired workbook", detail=str(exc), output_path=output_path)

    reloaded = load(output_path)
    remaining = exact_markers(reloaded, marker)
    changed = []
    after = populated_snapshot(reloaded, set(normalized))
    for key in set(before) | set(after):
        if before.get(key) != after.get(key):
            changed.append(key)
    target_report = []
    for canonical in sorted(normalized):
        sheet, address = canonical.rsplit("!", 1)
        cell = reloaded[sheet][address]
        target_report.append({
            "target": canonical,
            "value": json_value(cell.value),
            "data_type": cell.data_type,
            "number_format": cell.number_format,
            "format_preserved": cell.number_format == target_formats[canonical],
            "is_numeric": isinstance(cell.value, (int, float)) and not isinstance(cell.value, bool),
        })
    if changed:
        fail("verification detected changed non-target cell values or types", changed_non_target_cells=sorted(changed))
    if not allow_partial and remaining:
        fail("verification found markers after a claimed complete repair", remaining_targets=remaining)
    if any(not item["is_numeric"] or not item["format_preserved"] for item in target_report):
        fail("verification failed for a repaired cell", repaired_cells=target_report)
    return {
        "ok": True,
        "output_path": output_path,
        "repaired_cells": target_report,
        "remaining_targets": remaining,
        "non_target_value_or_type_changes": [],
    }


def validate(payload):
    marker = payload.get("marker", DEFAULT_MARKER)
    wb = load(payload.get("input_path"))
    expected = payload.get("expected_repairs", {})
    if not isinstance(expected, dict):
        fail("expected_repairs must be an object when supplied")
    checked = []
    for target in expected:
        sheet, address = split_target(target, wb)
        cell = wb[sheet][address]
        checked.append({
            "target": f"{sheet}!{address}",
            "value": json_value(cell.value),
            "data_type": cell.data_type,
            "number_format": cell.number_format,
            "is_numeric": isinstance(cell.value, (int, float)) and not isinstance(cell.value, bool),
        })
    return {"ok": True, "marker": marker, "marker_count": len(exact_markers(wb, marker)),
            "remaining_targets": exact_markers(wb, marker), "checked_cells": checked}


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception as exc:
        fail("stdin must contain one JSON object", detail=str(exc))
    if not isinstance(payload, dict):
        fail("stdin JSON must be an object")
    action = payload.get("action")
    if action == "inspect":
        marker = payload.get("marker", DEFAULT_MARKER)
        if not isinstance(marker, str):
            fail("marker must be a string")
        result = inspect(load(payload.get("input_path")), marker)
    elif action == "apply":
        result = apply(payload)
    elif action == "validate":
        result = validate(payload)
    else:
        fail("action must be inspect, apply, or validate")
    print(json.dumps(result, ensure_ascii=False, default=json_value, allow_nan=False))


if __name__ == "__main__":
    main()
