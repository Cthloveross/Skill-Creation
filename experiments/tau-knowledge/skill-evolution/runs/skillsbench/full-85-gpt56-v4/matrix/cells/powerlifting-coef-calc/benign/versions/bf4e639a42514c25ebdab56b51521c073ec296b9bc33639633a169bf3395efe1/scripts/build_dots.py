#!/usr/bin/env python3
"""Build formula-based IPF Dots results in an XLSX workbook.

Reads a JSON request from stdin and writes a JSON result or JSON error to stdout.
See SKILL.md for the request schema.
"""
from __future__ import annotations

import copy
import json
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import openpyxl
from openpyxl.utils import get_column_letter


# Canonical source-field aliases. Matching is normalized and exact so that an
# attempt field such as Squat1Kg is never accidentally used as a best lift.
ALIASES = {
    "name": ["name", "liftername", "athletename", "competitorname"],
    "sex": ["sex", "gender"],
    "bodyweight": ["bodyweightkg", "bodyweight", "bwkg", "weightkg"],
    "squat": ["best3squatkg", "bestsquatkg", "bestsquat"],
    "bench": ["best3benchkg", "bestbenchkg", "bestbench"],
    "deadlift": ["best3deadliftkg", "bestdeadliftkg", "bestdeadlift"],
}
MALE_TOKENS = {"m", "male", "men", "man"}
FEMALE_TOKENS = {"f", "female", "women", "woman"}


def norm(value: Any) -> str:
    """Normalize a header or categorical value for controlled comparisons."""
    return "".join(ch.lower() for ch in str(value).strip() if ch.isalnum())


def json_error(message: str, **detail: Any) -> None:
    payload = {"ok": False, "error": message}
    payload.update(detail)
    print(json.dumps(payload, ensure_ascii=False))


def find_header_row(ws) -> Tuple[int, Dict[str, int]]:
    """Locate a header row by finding the row with the most required fields."""
    best = None
    max_row = min(ws.max_row, 30)
    for row in range(1, max_row + 1):
        index: Dict[str, int] = {}
        for col in range(1, ws.max_column + 1):
            value = ws.cell(row, col).value
            if value is not None and norm(value):
                index.setdefault(norm(value), col)
        resolved = sum(any(a in index for a in aliases) for aliases in ALIASES.values())
        candidate = (resolved, row, index)
        if best is None or candidate[0] > best[0]:
            best = candidate
    if best is None or best[0] < len(ALIASES):
        available = [] if best is None else list(best[2].keys())
        raise ValueError(
            "Could not locate a row containing all Dots input headers. "
            f"Normalized headers from the best candidate row: {available}"
        )
    return best[1], best[2]


def resolve_columns(header_index: Dict[str, int]) -> Dict[str, int]:
    resolved: Dict[str, int] = {}
    for field, aliases in ALIASES.items():
        matches = [header_index[a] for a in aliases if a in header_index]
        # Multiple aliases in the same header row must not silently choose one.
        if len(matches) != 1:
            raise ValueError(
                f"Required field {field!r} is not uniquely resolvable; "
                f"matched columns {matches}."
            )
        resolved[field] = matches[0]
    return resolved


def snapshot_values(ws) -> List[List[Any]]:
    return [[ws.cell(r, c).value for c in range(1, ws.max_column + 1)]
            for r in range(1, ws.max_row + 1)]


def copy_cell(source, target) -> None:
    """Copy displayed cell content and presentation, without sharing styles."""
    target.value = source.value
    if source.has_style:
        target._style = copy.copy(source._style)
    if source.number_format:
        target.number_format = source.number_format
    if source.alignment:
        target.alignment = copy.copy(source.alignment)
    if source.protection:
        target.protection = copy.copy(source.protection)


def clear_values(ws) -> None:
    # Do not delete rows/columns: this preserves any worksheet-level layout.
    for row in ws.iter_rows():
        for cell in row:
            cell.value = None


def number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def sex_kind(value: Any) -> str | None:
    token = norm(value)
    if token in MALE_TOKENS:
        return "male"
    if token in FEMALE_TOKENS:
        return "female"
    return None


def excel_string(value: Any) -> str:
    return '"' + str(value).replace('"', '""') + '"'


def dots_formula(total_ref: str, bw_ref: str, sex_ref: str, male_source_values: Iterable[Any]) -> str:
    """Return an Excel formula using published IPF Dots polynomial constants."""
    checks = [f"{sex_ref}={excel_string(v)}" for v in sorted(set(male_source_values), key=str)]
    male_test = checks[0] if len(checks) == 1 else "OR(" + ",".join(checks) + ")"
    men = (
        f"(-0.000001093*{bw_ref}^4+0.0007391293*{bw_ref}^3"
        f"-0.1918759221*{bw_ref}^2+24.0900756*{bw_ref}-307.75076)"
    )
    women = (
        f"(-0.0000010706*{bw_ref}^4+0.0005158568*{bw_ref}^3"
        f"-0.1126655495*{bw_ref}^2+13.6175032*{bw_ref}-57.96288)"
    )
    return f"=ROUND({total_ref}*500/IF({male_test},{men},{women}),3)"


def try_recalculate(xlsx_path: Path) -> Tuple[bool, str]:
    """Recalculate via LibreOffice in an isolated directory, if available."""
    executable = next((x for x in ("libreoffice", "soffice") if shutil.which(x)), None)
    if executable is None:
        return False, "No libreoffice/soffice executable found; formulas were retained without cached recalculation."
    with tempfile.TemporaryDirectory(prefix="dots-recalc-") as tmp:
        tmp_path = Path(tmp)
        source_dir = tmp_path / "source"
        output_dir = tmp_path / "output"
        source_dir.mkdir()
        output_dir.mkdir()
        staged = source_dir / "workbook.xlsx"
        shutil.copy2(xlsx_path, staged)
        command = [executable, "--headless", "--convert-to", "xlsx", "--outdir", str(output_dir), str(staged)]
        completed = subprocess.run(command, text=True, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, timeout=180)
        converted = output_dir / "workbook.xlsx"
        if completed.returncode != 0 or not converted.exists():
            detail = (completed.stderr or completed.stdout).strip()[-600:]
            return False, f"Spreadsheet recalculation did not complete: {detail}"
        shutil.copy2(converted, xlsx_path)
    return True, f"Recalculated with {executable}."


def main(request: Dict[str, Any]) -> Dict[str, Any]:
    input_path = Path(request["input_path"])
    output_path = Path(request["output_path"])
    source_name = request.get("source_sheet", "Data")
    destination_name = request.get("destination_sheet", "Dots")
    recalculate = bool(request.get("recalculate", True))
    if not input_path.is_file():
        raise ValueError(f"Input workbook does not exist: {input_path}")
    readme_path = request.get("readme_path")
    readme_read = False
    if readme_path:
        rp = Path(readme_path)
        if rp.is_file():
            rp.read_text(encoding="utf-8", errors="replace")
            readme_read = True

    wb = openpyxl.load_workbook(input_path, data_only=False)
    if source_name not in wb.sheetnames or destination_name not in wb.sheetnames:
        raise ValueError(f"Expected sheets {source_name!r} and {destination_name!r}; found {wb.sheetnames}")
    source = wb[source_name]
    dest = wb[destination_name]
    before_source = snapshot_values(source)
    header_row, header_index = find_header_row(source)
    fields = resolve_columns(header_index)
    ordered_cols = sorted(set(fields.values()))
    source_headers = [source.cell(header_row, c).value for c in ordered_cols]
    dest_positions = {source_col: idx + 1 for idx, source_col in enumerate(ordered_cols)}

    male_values: List[Any] = []
    first_data_row = header_row + 1
    records = 0
    for r in range(first_data_row, source.max_row + 1):
        # A fully blank physical row is not a record.
        if all(source.cell(r, c).value is None for c in range(1, source.max_column + 1)):
            continue
        records += 1
        values = {key: source.cell(r, col).value for key, col in fields.items()}
        if values["name"] in (None, ""):
            raise ValueError(f"Record at Data row {r} has no lifter name.")
        if sex_kind(values["sex"]) is None:
            raise ValueError(f"Unsupported or missing sex at Data row {r}: {values['sex']!r}")
        for key in ("bodyweight", "squat", "bench", "deadlift"):
            if not number(values[key]):
                raise ValueError(f"Missing/non-numeric {key} at Data row {r}: {values[key]!r}")
        if sex_kind(values["sex"]) == "male":
            male_values.append(values["sex"])

    clear_values(dest)
    for target_col, source_col in enumerate(ordered_cols, start=1):
        copy_cell(source.cell(header_row, source_col), dest.cell(1, target_col))
    total_col = len(ordered_cols) + 1
    dots_col = total_col + 1
    total_header = dest.cell(1, total_col)
    dots_header = dest.cell(1, dots_col)
    total_header.value = "TotalKg"
    dots_header.value = "Dots"
    # Copy a nearby numeric style where possible, then explicitly use 3 decimals.
    lift_style = source.cell(header_row + 1, fields["squat"])
    for header in (total_header, dots_header):
        header._style = copy.copy(source.cell(header_row, ordered_cols[-1])._style)
    for output_row, source_row in enumerate(range(first_data_row, source.max_row + 1), start=2):
        if all(source.cell(source_row, c).value is None for c in range(1, source.max_column + 1)):
            continue
        for target_col, source_col in enumerate(ordered_cols, start=1):
            copy_cell(source.cell(source_row, source_col), dest.cell(output_row, target_col))
        squat = f"{get_column_letter(dest_positions[fields['squat']])}{output_row}"
        bench = f"{get_column_letter(dest_positions[fields['bench']])}{output_row}"
        deadlift = f"{get_column_letter(dest_positions[fields['deadlift']])}{output_row}"
        total_ref = f"{get_column_letter(total_col)}{output_row}"
        bw_ref = f"{get_column_letter(dest_positions[fields['bodyweight']])}{output_row}"
        sex_ref = f"{get_column_letter(dest_positions[fields['sex']])}{output_row}"
        dest.cell(output_row, total_col).value = f"=ROUND(SUM({squat},{bench},{deadlift}),3)"
        dest.cell(output_row, dots_col).value = dots_formula(total_ref, bw_ref, sex_ref, male_values)
        dest.cell(output_row, total_col).number_format = "0.000"
        dest.cell(output_row, dots_col).number_format = "0.000"
        # Retain a sensible number style even when the source has no style.
        if lift_style.has_style:
            dest.cell(output_row, total_col)._style = copy.copy(lift_style._style)
            dest.cell(output_row, dots_col)._style = copy.copy(lift_style._style)
            dest.cell(output_row, total_col).number_format = "0.000"
            dest.cell(output_row, dots_col).number_format = "0.000"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output_path)
    recalculated, recalc_message = (False, "Recalculation disabled by request.")
    if recalculate:
        recalculated, recalc_message = try_recalculate(output_path)

    # Formula-structure and source-integrity checks after final output is written.
    check_wb = openpyxl.load_workbook(output_path, data_only=False)
    if snapshot_values(check_wb[source_name]) != before_source:
        raise RuntimeError("Validation failed: Data values changed while preparing Dots.")
    check_dest = check_wb[destination_name]
    expected_headers = source_headers + ["TotalKg", "Dots"]
    actual_headers = [check_dest.cell(1, c).value for c in range(1, len(expected_headers) + 1)]
    if actual_headers != expected_headers:
        raise RuntimeError(f"Validation failed: output headers are {actual_headers!r}, expected {expected_headers!r}")
    for r in range(2, records + 2):
        if not (isinstance(check_dest.cell(r, total_col).value, str) and check_dest.cell(r, total_col).value.startswith("=")):
            raise RuntimeError(f"Validation failed: TotalKg at row {r} is not a formula.")
        if not (isinstance(check_dest.cell(r, dots_col).value, str) and check_dest.cell(r, dots_col).value.startswith("=")):
            raise RuntimeError(f"Validation failed: Dots at row {r} is not a formula.")

    cached_numeric = None
    if recalculated:
        cached = openpyxl.load_workbook(output_path, data_only=True)[destination_name]
        cached_numeric = all(number(cached.cell(r, total_col).value) and number(cached.cell(r, dots_col).value)
                             for r in range(2, records + 2))
        if not cached_numeric:
            raise RuntimeError("Validation failed: recalculated TotalKg/Dots cached values are not numeric.")

    return {
        "ok": True,
        "output_path": str(output_path),
        "readme_read": readme_read,
        "source_sheet": source_name,
        "destination_sheet": destination_name,
        "header_row_in_source": header_row,
        "records": records,
        "resolved_source_columns": {key: source.cell(header_row, col).value for key, col in fields.items()},
        "copied_headers": source_headers,
        "derived_columns": {"TotalKg": get_column_letter(total_col), "Dots": get_column_letter(dots_col)},
        "recalculated": recalculated,
        "recalculation_message": recalc_message,
        "cached_results_numeric": cached_numeric,
        "validations": ["Data values unchanged", "headers/order verified", "derived formulas verified"],
    }


if __name__ == "__main__":
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise ValueError("The stdin JSON value must be an object.")
        print(json.dumps(main(request), ensure_ascii=False))
    except Exception as exc:
        json_error(str(exc))
        sys.exit(1)
