#!/usr/bin/env python3
"""Populate requested formula cells in a protein-expression .xlsx workbook.

JSON stdin: {"input_path": str, "output_path": str, "recalculate": bool=True}
JSON stdout on success describes the saved workbook.  The program never writes
constants in place of requested calculations.
"""
from __future__ import annotations

import json
import math
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

import openpyxl
from openpyxl.utils import get_column_letter

TASK, DATA = "Task", "Data"
LOOKUP_ROWS = range(11, 21)
LOOKUP_COLS = range(3, 13)
STATS_ROWS = range(24, 28)
STATS_COLS = range(2, 12)
FOLD_ROWS = range(32, 42)


def fail(message: str) -> None:
    raise RuntimeError(message)


def text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def quote_sheet(name: str) -> str:
    # Quotes work in Excel and LibreOffice even where a sheet name needs none.
    return "'" + name.replace("'", "''") + "'"


def a1(col: int, row: int, absolute: bool = True) -> str:
    letter = get_column_letter(col)
    return f"${letter}${row}" if absolute else f"{letter}{row}"


def a1range(left: int, top: int, right: int, bottom: int) -> str:
    return f"{a1(left, top)}:{a1(right, bottom)}"


def task_keys(task_ws) -> tuple[list[str], list[str]]:
    proteins = [text(task_ws.cell(r, 1).value) for r in LOOKUP_ROWS]
    samples = [text(task_ws.cell(10, c).value) for c in LOOKUP_COLS]
    if len(set(proteins)) != 10 or any(not x for x in proteins):
        fail("Task A11:A20 must have ten nonblank, unique protein identifiers.")
    if len(set(samples)) != 10 or any(not x for x in samples):
        fail("Task C10:L10 must have ten nonblank, unique sample names.")
    groups = [text(task_ws.cell(9, c).value).casefold() for c in LOOKUP_COLS]
    if any(x not in {"control", "treated"} for x in groups) or groups.count("control") < 2 or groups.count("treated") < 2:
        fail("Task C9:L9 must identify at least two Control and two Treated samples.")
    return proteins, samples


def discover_data_layout(data_ws, proteins: list[str], samples: list[str]) -> dict[str, int]:
    """Find one identifier column and one header row satisfying every Task key."""
    wanted_proteins = set(proteins)
    columns: dict[int, list[str]] = defaultdict(list)
    for row in data_ws.iter_rows():
        for cell in row:
            if text(cell.value) in wanted_proteins:
                columns[cell.column].append(text(cell.value))
    protein_columns = [c for c, values in columns.items() if set(values) == wanted_proteins and len(values) == len(wanted_proteins)]
    if len(protein_columns) != 1:
        fail("Could not find one Data column that uniquely contains all Task protein IDs.")
    protein_col = protein_columns[0]

    # Data labels may have a stable prefix not present in the Task labels.  The
    # actual match is checked uniquely now; the spreadsheet formula uses the
    # equivalent suffix wildcard so it remains an auditable two-key lookup.
    possible: dict[int, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    for row in data_ws.iter_rows():
        for cell in row:
            label = text(cell.value)
            if not label:
                continue
            for sample in samples:
                if label == sample or label.endswith(sample):
                    possible[cell.row][sample].append(cell.column)
    header_rows = [r for r, matched in possible.items() if set(matched) == set(samples) and all(len(matched[s]) == 1 for s in samples)]
    if len(header_rows) != 1:
        fail("Could not find one Data header row with unique matches for all Task samples.")
    header_row = header_rows[0]
    sample_columns = [possible[header_row][sample][0] for sample in samples]
    if len(set(sample_columns)) != len(sample_columns):
        fail("Task sample names do not resolve to distinct Data columns.")

    protein_rows = [r for r in range(1, data_ws.max_row + 1) if text(data_ws.cell(r, protein_col).value) in wanted_proteins]
    if header_row >= min(protein_rows):
        fail("The Data sample-header row must be above the matched protein rows.")
    return {"protein_col": protein_col, "header_row": header_row,
            "first_protein_row": min(protein_rows), "last_protein_row": max(protein_rows),
            "first_sample_col": min(sample_columns), "last_sample_col": max(sample_columns)}


def metric_rows(task_ws) -> dict[tuple[str, str], int]:
    """Map the four labelled statistic rows without assuming their order."""
    answer: dict[tuple[str, str], int] = {}
    for row in STATS_ROWS:
        label = text(task_ws.cell(row, 1).value).casefold()
        group = "control" if "control" in label else "treated" if "treated" in label else None
        statistic = "mean" if ("mean" in label or "average" in label) else "sd" if ("std" in label or "standard" in label) else None
        if group and statistic:
            key = (group, statistic)
            if key in answer:
                fail(f"Duplicate summary label for {group} {statistic}.")
            answer[key] = row
    needed = {(g, s) for g in ("control", "treated") for s in ("mean", "sd")}
    if set(answer) != needed:
        fail("Task A24:A27 must label control/treated mean and standard-deviation rows.")
    return answer


def fold_columns(task_ws) -> tuple[int, int]:
    """Return (fold-change column, log2-fold-change column) from row-31 headings."""
    ordinary = logarithmic = None
    for col in (3, 4):
        label = text(task_ws.cell(31, col).value).casefold()
        # Templates often abbreviate the logarithmic heading as "Log2 FC".
        if "log" in label and ("fold" in label or "fc" in label):
            logarithmic = col if logarithmic is None else -1
        elif "fold" in label or "fc" in label:
            ordinary = col if ordinary is None else -1
    if ordinary is None or logarithmic is None or ordinary == -1 or logarithmic == -1:
        fail("Task C31:D31 must identify one Fold Change and one Log2 Fold Change column.")
    return ordinary, logarithmic


def lookup_formula(layout: dict[str, int], task_row: int, task_col: int) -> str:
    sheet = quote_sheet(DATA)
    ids = f"{sheet}!{a1range(layout['protein_col'], layout['first_protein_row'], layout['protein_col'], layout['last_protein_row'])}"
    headers = f"{sheet}!{a1range(layout['first_sample_col'], layout['header_row'], layout['last_sample_col'], layout['header_row'])}"
    values = f"{sheet}!{a1range(layout['first_sample_col'], layout['first_protein_row'], layout['last_sample_col'], layout['last_protein_row'])}"
    index = f'INDEX({values},MATCH($A${task_row},{ids},0),MATCH("*"&{get_column_letter(task_col)}$10,{headers},0))'
    # INDEX displays an empty source cell as zero in Calc/Excel.  Test the
    # referenced source before returning it so missing proteomics values stay
    # missing rather than becoming observed zeroes.
    return f'=IF(ISBLANK({index}),"",{index})'


def populate(wb) -> dict[str, Any]:
    if TASK not in wb.sheetnames or DATA not in wb.sheetnames:
        fail("Workbook must contain sheets named Task and Data.")
    task, data = wb[TASK], wb[DATA]
    proteins, samples = task_keys(task)
    layout = discover_data_layout(data, proteins, samples)
    rows = metric_rows(task)
    fold_col, log_col = fold_columns(task)

    for r in LOOKUP_ROWS:
        for c in LOOKUP_COLS:
            task.cell(r, c).value = lookup_formula(layout, r, c)

    group_columns = {group: [c for c in LOOKUP_COLS if text(task.cell(9, c).value).casefold() == group]
                     for group in ("control", "treated")}
    # Summary columns are the ordered ten target proteins: B maps to Task row
    # 11, C to row 12, etc.  Build ordinary AVERAGE/STDEV argument lists
    # from the metadata-selected columns.  These functions ignore the empty
    # strings returned for missing measurements, unlike SUMPRODUCT on formula
    # cells, and do not require an array-formula entry mode.
    for col in STATS_COLS:
        source_row = 11 + col - 2
        for group in ("control", "treated"):
            refs = ",".join(f"{get_column_letter(c)}{source_row}" for c in group_columns[group])
            mean_row = rows[(group, "mean")]
            sd_row = rows[(group, "sd")]
            task.cell(mean_row, col).value = f'=AVERAGE({refs})'
            task.cell(sd_row, col).value = f'=IF(COUNT({refs})<2,"",STDEV({refs}))'

    # The fold-change rows are the same ordered target proteins as the summary
    # columns.  Honor the template's row-31 headings rather than assuming C/D
    # ordering; log2 FC is treated mean minus control mean.
    for row in FOLD_ROWS:
        index = row - 32
        stats_col = 2 + index
        control = a1(stats_col, rows[("control", "mean")])
        treated = a1(stats_col, rows[("treated", "mean")])
        log_ref = a1(log_col, row)
        task.cell(row, log_col).value = f'={treated}-{control}'
        task.cell(row, fold_col).value = f'=2^{log_ref}'
    return {"layout": layout, "stats_rows": {f"{g}_{s}": r for (g, s), r in rows.items()},
            "fold_change_column": get_column_letter(fold_col), "log2_fold_change_column": get_column_letter(log_col)}


def changed_cells():
    for r in LOOKUP_ROWS:
        for c in LOOKUP_COLS:
            yield r, c
    for r in STATS_ROWS:
        for c in STATS_COLS:
            yield r, c
    for r in FOLD_ROWS:
        yield r, 3
        yield r, 4


def validate(path: Path, need_cached_values: bool) -> None:
    formulas = openpyxl.load_workbook(path, data_only=False, read_only=True)
    try:
        ws = formulas[TASK]
        absent = [f"{get_column_letter(c)}{r}" for r, c in changed_cells()
                  if not (isinstance(ws.cell(r, c).value, str) and ws.cell(r, c).value.startswith("="))]
        if absent:
            fail("Expected formulas are absent from: " + ", ".join(absent))
    finally:
        formulas.close()
    if need_cached_values:
        cached = openpyxl.load_workbook(path, data_only=True, read_only=True)
        try:
            ws = cached[TASK]
            # STDEV is mathematically undefined for a group with fewer than
            # two observed values.  The written IF returns blank in that case;
            # every other requested calculation must calculate numerically.
            # Identify standard-deviation rows from their formula structure;
            # metric rows may be arranged differently in a compatible template.
            formula_book = openpyxl.load_workbook(path, data_only=False, read_only=True)
            try:
                formula_ws = formula_book[TASK]
                sd_rows = {r for r in STATS_ROWS
                           if isinstance(formula_ws.cell(r, 2).value, str)
                           and "STDEV" in formula_ws.cell(r, 2).value.upper()}
            finally:
                formula_book.close()
            bad = []
            for r, c in changed_cells():
                value = ws.cell(r, c).value
                is_lookup = r in LOOKUP_ROWS and c in LOOKUP_COLS
                # Standard-deviation rows alone may have the native
                # insufficient-observations error.
                is_sd = r in sd_rows
                if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)):
                    continue
                # A missing raw expression remains an empty lookup result.
                if is_lookup and value is None:
                    continue
                # The formula intentionally returns blank when fewer than two
                # selected measurements exist, rather than converting missing
                # values to zero or exposing a division-by-zero error.
                if is_sd and value is None:
                    continue
                bad.append(f"{get_column_letter(c)}{r}")
            if bad:
                fail("Formula recalculation did not produce finite numeric values in: " + ", ".join(bad))
        finally:
            cached.close()


def recalculate(stage: Path, out_dir: Path) -> Path:
    executable = shutil.which("libreoffice") or shutil.which("soffice")
    if not executable:
        fail("Formula recalculation requires libreoffice or soffice.")
    out_dir.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run([executable, "--headless", "--convert-to", "xlsx", "--outdir", str(out_dir), str(stage)],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=180, check=False)
    converted = out_dir / stage.name
    if completed.returncode != 0 or not converted.is_file():
        fail("LibreOffice recalculation/conversion failed: " + (completed.stderr or completed.stdout).strip())
    return converted


def main() -> None:
    try:
        request = json.load(sys.stdin)
        source = Path(request["input_path"]).expanduser().resolve()
        output = Path(request["output_path"]).expanduser().resolve()
        calculate = bool(request.get("recalculate", True))
        if source.suffix.lower() != ".xlsx" or output.suffix.lower() != ".xlsx":
            fail("Only .xlsx input and output paths are supported.")
        if not source.is_file():
            fail(f"Input workbook does not exist: {source}")
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="protein-expression-") as temp:
            stage = Path(temp) / "workbook.xlsx"
            wb = openpyxl.load_workbook(source, data_only=False)
            try:
                metadata = populate(wb)
                wb.calculation.fullCalcOnLoad = True
                wb.calculation.forceFullCalc = True
                wb.calculation.calcMode = "auto"
                wb.save(stage)
            finally:
                wb.close()
            shutil.copy2(recalculate(stage, Path(temp) / "recalculated") if calculate else stage, output)
        validate(output, calculate)
        print(json.dumps({"output_path": str(output), "recalculated": calculate, **metadata}, sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
