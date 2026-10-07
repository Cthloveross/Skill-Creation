#!/usr/bin/env python3
"""Populate the public protein-expression workbook task regions with formulas.

Reads one JSON object from stdin and emits one JSON object to stdout.  No source
identifiers or numeric results are embedded in this program.
"""
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter, quote_sheetname


class WorkbookLayoutError(ValueError):
    """A workbook does not provide the unambiguous structure required here."""


def cell_key(value):
    """Return an exact printable key without normalizing identifier spelling."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def label_key(value):
    """Normalization used only for semantic Control/Treated row labels."""
    if value is None:
        return ""
    return "".join(ch.lower() for ch in str(value) if ch.isalnum())


def coords_in_range(ws, min_row, max_row, min_col, max_col):
    for row in ws.iter_rows(min_row=min_row, max_row=max_row,
                            min_col=min_col, max_col=max_col):
        for cell in row:
            yield cell


def require_distinct(values, description):
    keys = [cell_key(v) for v in values]
    if any(v is None or v == "" for v in keys):
        raise WorkbookLayoutError(f"{description} contains a blank key")
    duplicates = sorted({v for v in keys if keys.count(v) > 1})
    if duplicates:
        raise WorkbookLayoutError(f"{description} contains duplicate keys: {duplicates}")
    return keys


def unique_source_axis(ws, requested_keys, axis):
    """Find exactly one row/column that contains each requested key exactly once."""
    candidates = []
    if axis == "column":
        for col in range(1, ws.max_column + 1):
            values = [cell_key(ws.cell(r, col).value) for r in range(1, ws.max_row + 1)]
            if all(values.count(key) == 1 for key in requested_keys):
                candidates.append(col)
    elif axis == "row":
        for row in range(1, ws.max_row + 1):
            values = [cell_key(ws.cell(row, c).value) for c in range(1, ws.max_column + 1)]
            if all(values.count(key) == 1 for key in requested_keys):
                candidates.append(row)
    else:
        raise ValueError("axis must be row or column")

    if not candidates:
        raise WorkbookLayoutError(
            f"No Data {axis} contains every requested key exactly once; "
            "do not substitute partial or approximate matches."
        )
    if len(candidates) != 1:
        rendered = [get_column_letter(x) if axis == "column" else x for x in candidates]
        raise WorkbookLayoutError(
            f"Ambiguous Data {axis} candidates {rendered}; source key structure is not unique."
        )
    return candidates[0]


def classify_stat_row(value):
    s = label_key(value)
    group = "control" if "control" in s else "treated" if "treated" in s else None
    if not group:
        return None
    if "mean" in s or "average" in s or "avg" in s:
        return (group, "mean")
    if "stdev" in s or "std" in s or "standarddeviation" in s or s.endswith("sd"):
        return (group, "sd")
    return None


def statistic_rows(task):
    expected = [("control", "mean"), ("control", "sd"),
                ("treated", "mean"), ("treated", "sd")]
    detected = {}
    labeled_count = 0
    for row in range(24, 28):
        kind = classify_stat_row(task.cell(row, 1).value)
        if kind is not None:
            labeled_count += 1
            if kind in detected:
                raise WorkbookLayoutError(f"Duplicate statistic row label for {kind}")
            detected[kind] = row
    if labeled_count == 0:
        return dict(zip(expected, range(24, 28)))
    if set(detected) != set(expected):
        raise WorkbookLayoutError(
            "Statistic labels in Task!A24:A27 are incomplete or unsupported; "
            "supply all Control/Treated mean/standard-deviation labels or none."
        )
    return detected


def statistic_column_mapping(task, targets):
    """Map statistic columns to target indices from headers, or declared order."""
    target_index = {key: i for i, key in enumerate(targets)}
    mapping = {}
    seen_indices = set()
    any_header_match = False
    for col in range(2, 12):
        matches = []
        # Headers are expected above the statistics output. Searching this small
        # region avoids treating expression-output cells as headers.
        for row in range(1, 24):
            key = cell_key(task.cell(row, col).value)
            if key in target_index:
                matches.append(target_index[key])
        matches = sorted(set(matches))
        if matches:
            any_header_match = True
        if len(matches) > 1:
            raise WorkbookLayoutError(
                f"More than one target ID appears above statistic column {get_column_letter(col)}"
            )
        if len(matches) == 1:
            if matches[0] in seen_indices:
                raise WorkbookLayoutError("Statistic headers map more than one column to one target")
            mapping[col] = matches[0]
            seen_indices.add(matches[0])
    if not any_header_match:
        return {col: col - 2 for col in range(2, 12)}
    if len(mapping) != 10 or seen_indices != set(range(10)):
        raise WorkbookLayoutError(
            "Statistic headers are present but do not provide a one-to-one mapping for all targets"
        )
    return mapping


def fold_target_mapping(task, targets):
    index = {key: i for i, key in enumerate(targets)}
    raw = [cell_key(task.cell(row, 2).value) for row in range(32, 42)]
    if all(v is None or v == "" for v in raw):
        return {row: row - 32 for row in range(32, 42)}
    if any(v not in index for v in raw):
        raise WorkbookLayoutError("Fold-change IDs in Task!B32:B41 do not exactly match target IDs")
    if len(set(raw)) != len(raw):
        raise WorkbookLayoutError("Fold-change IDs in Task!B32:B41 are duplicated")
    return {row: index[raw[row - 32]] for row in range(32, 42)}


def snapshot(ws, excluded):
    """Snapshot ordinary cell content/style for cells that must remain untouched."""
    saved = {}
    for row in ws.iter_rows():
        for cell in row:
            if cell.coordinate not in excluded:
                saved[cell.coordinate] = (cell.value, cell.data_type, cell.style_id, cell.number_format)
    return saved


def verify_snapshot(ws, original, sheet_name):
    for coordinate, prior in original.items():
        cell = ws[coordinate]
        current = (cell.value, cell.data_type, cell.style_id, cell.number_format)
        if current != prior:
            raise WorkbookLayoutError(f"Unexpected change to {sheet_name}!{coordinate}")


def set_recalc_properties(wb):
    """Request Excel-compatible recalculation without attempting to calculate."""
    props = getattr(wb, "calculation", None)
    if props is None:
        props = getattr(wb, "calculation_properties", None)
    if props is not None:
        try:
            props.fullCalcOnLoad = True
            props.forceFullCalc = True
            props.calcMode = "auto"
        except Exception:
            pass


def recalculate_with_office(path, timeout):
    executable = shutil.which("libreoffice") or shutil.which("soffice")
    if not executable:
        raise WorkbookLayoutError(
            "recalculate was requested, but neither libreoffice nor soffice is installed"
        )
    path = Path(path).resolve()
    with tempfile.TemporaryDirectory(prefix="xlsx_recalc_") as tmp:
        temp_dir = Path(tmp)
        completed = subprocess.run(
            [executable, "--headless", "--convert-to", "xlsx", "--outdir", str(temp_dir), str(path)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout, check=False,
        )
        converted = temp_dir / path.name
        if completed.returncode != 0 or not converted.exists():
            detail = (completed.stderr or completed.stdout).strip()
            raise WorkbookLayoutError(f"LibreOffice recalculation/conversion failed: {detail}")
        shutil.copy2(converted, path)


def finite_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def main(config):
    input_path = Path(config.get("input_path", "/root/protein_expression.xlsx"))
    output_path = Path(config.get("output_path", "/root/protein_expression_completed.xlsx"))
    recalculate = bool(config.get("recalculate", False))
    timeout = config.get("recalc_timeout_sec", 120)
    if not isinstance(timeout, int) or timeout <= 0:
        raise WorkbookLayoutError("recalc_timeout_sec must be a positive integer")
    if input_path.suffix.lower() != ".xlsx" or output_path.suffix.lower() != ".xlsx":
        raise WorkbookLayoutError("This skill supports .xlsx input and output paths only")
    if not input_path.is_file():
        raise WorkbookLayoutError(f"Input workbook does not exist: {input_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    wb = load_workbook(input_path, data_only=False)
    if "Task" not in wb.sheetnames or "Data" not in wb.sheetnames:
        raise WorkbookLayoutError("Workbook must contain sheets named Task and Data")
    task, data = wb["Task"], wb["Data"]

    targets = require_distinct([task.cell(r, 1).value for r in range(11, 21)], "Target protein IDs")
    samples = require_distinct([task.cell(10, c).value for c in range(3, 13)], "Requested sample names")
    groups = [label_key(task.cell(9, c).value) for c in range(3, 13)]
    if any(g not in {"control", "treated"} for g in groups):
        raise WorkbookLayoutError("Task!C9:L9 must contain only Control or Treated group labels")
    group_columns = {
        name: [c for c, g in zip(range(3, 13), groups) if g == name]
        for name in ("control", "treated")
    }
    if any(len(cols) < 2 for cols in group_columns.values()):
        raise WorkbookLayoutError("Each group requires at least two samples for STDEV.S")

    source_key_col = unique_source_axis(data, targets, "column")
    source_header_row = unique_source_axis(data, samples, "row")
    source_col_letter = get_column_letter(source_key_col)
    last_col_letter = get_column_letter(data.max_column)
    data_ref = quote_sheetname(data.title)
    key_range = f"{data_ref}!${source_col_letter}$1:${source_col_letter}${data.max_row}"
    header_range = f"{data_ref}!$A${source_header_row}:${last_col_letter}${source_header_row}"
    matrix_range = f"{data_ref}!$A$1:${last_col_letter}${data.max_row}"

    stat_rows = statistic_rows(task)
    stat_cols = statistic_column_mapping(task, targets)
    target_to_stat_col = {target_i: col for col, target_i in stat_cols.items()}
    folds = fold_target_mapping(task, targets)

    changed = set()
    for r in range(11, 21):
        for c in range(3, 13):
            changed.add(task.cell(r, c).coordinate)
    for r in range(24, 28):
        for c in range(2, 12):
            changed.add(task.cell(r, c).coordinate)
    for r in range(32, 42):
        for c in range(3, 5):
            changed.add(task.cell(r, c).coordinate)
    data_before = snapshot(data, set())
    task_before = snapshot(task, changed)
    changed_styles = {coord: task[coord].style_id for coord in changed}

    # Exact two-key lookup formulas. Full-sheet matrix bounds deliberately share
    # A1 as their origin with both MATCH ranges, so MATCH indices align with INDEX.
    for r in range(11, 21):
        for c in range(3, 13):
            task.cell(r, c).value = (
                f"=INDEX({matrix_range},MATCH($A{r},{key_range},0),"
                f"MATCH({get_column_letter(c)}$10,{header_range},0))"
            )

    for dest_col, target_i in stat_cols.items():
        source_row = 11 + target_i
        for group_name in ("control", "treated"):
            refs = ",".join(f"{get_column_letter(c)}{source_row}" for c in group_columns[group_name])
            mean_row = stat_rows[(group_name, "mean")]
            sd_row = stat_rows[(group_name, "sd")]
            task.cell(mean_row, dest_col).value = f"=AVERAGE({refs})"
            task.cell(sd_row, dest_col).value = f"=STDEV.S({refs})"

    control_mean_row = stat_rows[("control", "mean")]
    treated_mean_row = stat_rows[("treated", "mean")]
    for row, target_i in folds.items():
        stat_col = target_to_stat_col[target_i]
        stat_letter = get_column_letter(stat_col)
        task.cell(row, 3).value = f"={stat_letter}{treated_mean_row}-{stat_letter}{control_mean_row}"
        task.cell(row, 4).value = f"=2^C{row}"

    set_recalc_properties(wb)
    wb.save(output_path)

    # Structural post-save validation prior to any optional external recalculation.
    saved = load_workbook(output_path, data_only=False)
    saved_task, saved_data = saved["Task"], saved["Data"]
    verify_snapshot(saved_data, data_before, "Data")
    verify_snapshot(saved_task, task_before, "Task")
    for coord, style_id in changed_styles.items():
        if saved_task[coord].style_id != style_id:
            raise WorkbookLayoutError(f"Formatting changed unexpectedly at Task!{coord}")
    for coord in changed:
        if not isinstance(saved_task[coord].value, str) or not saved_task[coord].value.startswith("="):
            raise WorkbookLayoutError(f"Expected a formula at Task!{coord}")

    if recalculate:
        recalculate_with_office(output_path, timeout)
        formula_book = load_workbook(output_path, data_only=False)
        for coord in changed:
            if not isinstance(formula_book["Task"][coord].value, str) or not formula_book["Task"][coord].value.startswith("="):
                raise WorkbookLayoutError(f"Formula was lost during recalculation at Task!{coord}")
        value_book = load_workbook(output_path, data_only=True)
        for coord in changed:
            if not finite_number(value_book["Task"][coord].value):
                raise WorkbookLayoutError(
                    f"Recalculated value is not a finite number at Task!{coord}"
                )

    return {
        "ok": True,
        "output_path": str(output_path),
        "source_key_column": source_col_letter,
        "source_header_row": source_header_row,
        "recalculated": recalculate,
        "details": {
            "lookup_formula_cells": 100,
            "statistic_formula_cells": 40,
            "fold_formula_cells": 20,
        },
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise WorkbookLayoutError("JSON input must be an object")
        print(json.dumps(main(payload), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        sys.exit(2)
