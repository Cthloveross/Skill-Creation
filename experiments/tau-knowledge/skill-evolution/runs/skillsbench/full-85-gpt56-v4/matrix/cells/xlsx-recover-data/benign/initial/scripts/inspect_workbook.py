#!/usr/bin/env python3
"""Emit a JSON inventory of an xlsx workbook.

stdin schema: {"input_path": str, "placeholder": str (optional, default "???")}
stdout schema: {"input_path": str, "sheets": [...], "placeholder_count": int}
"""
import datetime as dt
import json
import math
import os
import sys
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter


def json_value(value):
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if math.isfinite(value):
            return value
        return repr(value)
    if isinstance(value, (dt.datetime, dt.date, dt.time)):
        return value.isoformat()
    if isinstance(value, dt.timedelta):
        return str(value)
    return str(value)


def main():
    request = json.load(sys.stdin)
    path = request.get("input_path")
    placeholder = request.get("placeholder", "???")
    if not isinstance(path, str) or not path:
        raise ValueError("input_path must be a nonempty string")
    if not isinstance(placeholder, str):
        raise ValueError("placeholder must be a string")
    if not os.path.isfile(path):
        raise FileNotFoundError(path)

    # data_only=False is intentional: recovery requires the actual formula text.
    wb = load_workbook(path, data_only=False, read_only=False)
    result = {"input_path": str(Path(path).resolve()), "placeholder": placeholder,
              "sheets": [], "placeholder_count": 0}
    for ws in wb.worksheets:
        cells = []
        missing = []
        # Iterating the used range also exposes styled-but-empty cells only when they
        # are in worksheet dimensions; only nonempty values are emitted.
        for row in ws.iter_rows():
            for cell in row:
                if cell.value is None:
                    continue
                item = {
                    "coordinate": cell.coordinate,
                    "row": cell.row,
                    "column": cell.column,
                    "column_letter": get_column_letter(cell.column),
                    "value": json_value(cell.value),
                    "data_type": cell.data_type,
                    "number_format": cell.number_format,
                }
                if cell.data_type == "f" or (isinstance(cell.value, str) and cell.value.startswith("=")):
                    item["formula"] = str(cell.value)
                cells.append(item)
                if cell.value == placeholder:
                    missing.append({
                        "coordinate": cell.coordinate,
                        "row": cell.row,
                        "column": cell.column,
                        "number_format": cell.number_format,
                        "style_id": cell.style_id,
                    })
        hidden_rows = [idx for idx, dim in ws.row_dimensions.items() if dim.hidden]
        hidden_columns = [key for key, dim in ws.column_dimensions.items() if dim.hidden]
        sheet = {
            "title": ws.title,
            "max_row": ws.max_row,
            "max_column": ws.max_column,
            "merged_ranges": [str(rng) for rng in ws.merged_cells.ranges],
            "hidden_rows": hidden_rows,
            "hidden_columns": hidden_columns,
            "cells": cells,
            "placeholders": missing,
        }
        result["sheets"].append(sheet)
        result["placeholder_count"] += len(missing)
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"ok": False, "error": type(exc).__name__, "message": str(exc)}), file=sys.stdout)
        sys.exit(1)
