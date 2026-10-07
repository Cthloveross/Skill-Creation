#!/usr/bin/env python3
"""Copy an xlsx workbook and replace every original textual placeholder numerically.

stdin schema:
{
  "input_path": str, "output_path": str, "placeholder": str (default "???"),
  "updates": [{"sheet": str, "cell": str, "value": int|float}, ...]
}
stdout schema on success:
{"ok": true, "output_path": str, "replacement_count": int,
 "updates": [{"sheet": str, "cell": str, "value": number}, ...]}
"""
import json
import math
import os
import sys
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.cell.cell import MergedCell


def fail(message):
    raise ValueError(message)


def cell_snapshot(wb):
    """Stored cell values/formulas, keyed so unrelated content can be compared."""
    result = {}
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                # Include allocated cells only. This excludes merely iterated empties.
                if cell.coordinate in ws._cells or cell.value is not None:
                    result[(ws.title, cell.coordinate)] = cell.value
    return result


def main():
    request = json.load(sys.stdin)
    required = ("input_path", "output_path", "updates")
    if any(key not in request for key in required):
        fail("input_path, output_path, and updates are required")
    source = request["input_path"]
    destination = request["output_path"]
    placeholder = request.get("placeholder", "???")
    updates = request["updates"]
    if not isinstance(source, str) or not isinstance(destination, str):
        fail("input_path and output_path must be strings")
    if not isinstance(placeholder, str) or not isinstance(updates, list):
        fail("placeholder must be a string and updates must be a list")
    if not os.path.isfile(source):
        raise FileNotFoundError(source)
    if os.path.abspath(source) == os.path.abspath(destination):
        fail("output_path must differ from input_path")

    before_wb = load_workbook(source, data_only=False, read_only=False)
    before = cell_snapshot(before_wb)
    originals = set()
    for ws in before_wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                if cell.value == placeholder:
                    originals.add((ws.title, cell.coordinate))
    if not originals:
        fail("no placeholder cells were found in the input workbook")

    normalized = []
    seen = set()
    for item in updates:
        if not isinstance(item, dict):
            fail("each update must be an object")
        sheet, address, value = item.get("sheet"), item.get("cell"), item.get("value")
        if not isinstance(sheet, str) or not isinstance(address, str):
            fail("each update requires string sheet and cell")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            fail("each replacement value must be a JSON number, not text or boolean")
        if not math.isfinite(float(value)):
            fail("replacement values must be finite")
        key = (sheet, address.upper())
        if key in seen:
            fail("duplicate update for %s!%s" % key)
        seen.add(key)
        if sheet not in before_wb.sheetnames:
            fail("unknown sheet: " + sheet)
        cell = before_wb[sheet][address]
        if isinstance(cell, MergedCell):
            fail("cannot write a non-anchor merged cell: %s!%s" % key)
        if cell.value != placeholder:
            fail("target was not an original placeholder: %s!%s" % key)
        normalized.append((sheet, cell.coordinate, value))

    targets = {(s, c) for s, c, _ in normalized}
    if targets != originals:
        absent = sorted(originals - targets)
        extra = sorted(targets - originals)
        fail("updates must replace exactly all placeholders; missing=%r extra=%r" % (absent, extra))

    # Reuse the loaded workbook so styles, formulas, sheet arrangement, and metadata
    # are retained; assignment changes only the target cell's stored value.
    for sheet, address, value in normalized:
        before_wb[sheet][address].value = value
    output_parent = Path(destination).expanduser().resolve().parent
    output_parent.mkdir(parents=True, exist_ok=True)
    before_wb.save(destination)

    # Reload the actual artifact, not the in-memory workbook, before declaring success.
    after_wb = load_workbook(destination, data_only=False, read_only=False)
    after = cell_snapshot(after_wb)
    remaining = []
    for ws in after_wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                if cell.value == placeholder:
                    remaining.append((ws.title, cell.coordinate))
    if remaining:
        fail("placeholder remains after save: %r" % remaining)
    for sheet, address, value in normalized:
        stored = after_wb[sheet][address].value
        if isinstance(stored, bool) or not isinstance(stored, (int, float)):
            fail("saved target is not numeric: %s!%s" % (sheet, address))
        if stored != value:
            fail("saved value differs from requested value: %s!%s" % (sheet, address))
    changed_elsewhere = []
    all_keys = set(before) | set(after)
    for key in all_keys:
        if key not in targets and before.get(key) != after.get(key):
            changed_elsewhere.append(key)
    if changed_elsewhere:
        fail("non-target stored values changed after save: %r" % changed_elsewhere[:20])

    print(json.dumps({
        "ok": True,
        "output_path": str(Path(destination).resolve()),
        "replacement_count": len(normalized),
        "updates": [{"sheet": s, "cell": c, "value": v} for s, c, v in normalized],
    }, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"ok": False, "error": type(exc).__name__, "message": str(exc)}))
        sys.exit(1)
