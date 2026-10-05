#!/usr/bin/env python3
"""Compute an annual log-HP-cycle correlation from supplied spreadsheet files.

JSON stdin schema is documented in SKILL.md.  On success, writes the requested
text artifact and emits a compact JSON audit record on stdout.
"""

from __future__ import annotations

import json
import math
import os
import re
import sys
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

try:
    import numpy as np
    import pandas as pd
except Exception as exc:  # handled by main so stdout remains JSON
    np = None  # type: ignore
    pd = None  # type: ignore
    IMPORT_ERROR = str(exc)
else:
    IMPORT_ERROR = None

YEAR_RE = re.compile(r"^\s*((?:19|20)\d{2})\s*$")
QUARTER_RE = re.compile(
    r"^\s*((?:19|20)\d{2})\s*(?::|\-|\s+)\s*(?:Q(?:U?ARTER)?\s*)?(IV|I{1,3}|[1-4])\s*$",
    re.IGNORECASE,
)
DATE_TEXT_RE = re.compile(r"^\s*(?:\d{4}[-/]\d{1,2}(?:[-/]\d{1,2})?|\d{1,2}[-/]\d{1,2}[-/]\d{2,4})\s*$")


def numeric(value: Any) -> Optional[float]:
    """Return a finite numeric value, accepting common spreadsheet formatting."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float, np.integer, np.floating)):
        out = float(value)
        return out if math.isfinite(out) else None
    text = str(value).strip()
    if not text or text.lower() in {"na", "n.a.", "nan", "--", "—", "-"}:
        return None
    # Remove display-only separators/currency and trailing footnote marks.
    cleaned = text.replace(",", "").replace("$", "").replace("%", "")
    cleaned = re.sub(r"\s*\([A-Za-z]+\)\s*$", "", cleaned).strip()
    try:
        out = float(cleaned)
    except ValueError:
        return None
    return out if math.isfinite(out) else None


def period(value: Any) -> Optional[Tuple[int, str]]:
    """Recognize source labels denoting an annual observation or a quarter."""
    if isinstance(value, (int, np.integer)) and 1800 <= int(value) <= 2200:
        return int(value), "annual"
    if isinstance(value, (float, np.floating)) and value.is_integer() and 1800 <= value <= 2200:
        return int(value), "annual"
    if not isinstance(value, str):
        return None
    text = value.strip()
    annual = YEAR_RE.match(text)
    if annual:
        return int(annual.group(1)), "annual"
    quarterly = QUARTER_RE.match(text)
    if quarterly:
        token = quarterly.group(2).upper()
        roman = {"I": 1, "II": 2, "III": 3, "IV": 4}
        q = roman.get(token, int(token) if token.isdigit() else 0)
        if 1 <= q <= 4:
            return int(quarterly.group(1)), "q" + str(q)
    return None


def read_sheets(path: str) -> List[Tuple[str, "pd.DataFrame"]]:
    """Read every worksheet with no header assumption; support HTML disguised as XLS."""
    try:
        workbook = pd.ExcelFile(path)
        return [(name, pd.read_excel(workbook, sheet_name=name, header=None)) for name in workbook.sheet_names]
    except Exception as excel_error:
        # Some government files named .xls are actually HTML tables.
        try:
            tables = pd.read_html(path, header=None)
            return [("html_table_%d" % i, table) for i, table in enumerate(tables)]
        except Exception as html_error:
            raise ValueError(
                "Cannot read %s as Excel or HTML table. Install a compatible .xls reader "
                "(usually xlrd for binary .xls). Excel error: %s; HTML fallback: %s"
                % (path, excel_error, html_error)
            )


def choose_period_and_total(frame: "pd.DataFrame") -> Optional[Tuple[int, int, int]]:
    """Find (period_column, first_total_column, recognized_period_count)."""
    if frame.empty:
        return None
    best: Optional[Tuple[int, int]] = None
    for col in range(frame.shape[1]):
        count = sum(period(v) is not None for v in frame.iloc[:, col].tolist())
        if best is None or count > best[1]:
            best = (col, count)
    if best is None or best[1] < 4:
        return None
    pcol, count = best
    recognized_rows = [r for r in range(frame.shape[0]) if period(frame.iat[r, pcol]) is not None]
    # The task's "Total, column 1" contract means select the first usable
    # numeric column after the semantic period column, not a guessed header name.
    for col in range(pcol + 1, frame.shape[1]):
        n_numeric = sum(numeric(frame.iat[r, col]) is not None for r in recognized_rows)
        if n_numeric >= max(3, min(8, len(recognized_rows) // 3)):
            return pcol, col, count
    return None


def extract_nominal(path: str, start: int, end: int) -> Tuple[Dict[int, float], Dict[int, int], str]:
    """Extract annual observations, using final-year available-quarter mean if present."""
    candidates: List[Tuple[int, "pd.DataFrame", int, int, str]] = []
    for sheet, frame in read_sheets(path):
        found = choose_period_and_total(frame)
        if found is not None:
            pcol, total_col, count = found
            candidates.append((count, frame, pcol, total_col, sheet))
    if not candidates:
        raise ValueError("No worksheet has a recognizable annual/quarter period column and Total column")
    _, frame, pcol, total_col, sheet = max(candidates, key=lambda x: x[0])

    annual: Dict[int, float] = {}
    quarters: Dict[int, List[float]] = {}
    for row in range(frame.shape[0]):
        label = period(frame.iat[row, pcol])
        if label is None:
            continue
        year, kind = label
        if year < start or year > end:
            continue
        value = numeric(frame.iat[row, total_col])
        if value is None:
            continue
        if kind == "annual":
            if year in annual and not math.isclose(annual[year], value, rel_tol=1e-10, abs_tol=1e-10):
                raise ValueError("Conflicting duplicate annual values for year %d in %s" % (year, sheet))
            annual[year] = value
        else:
            quarters.setdefault(year, []).append(value)

    values: Dict[int, float] = {}
    quarter_counts: Dict[int, int] = {}
    for year in range(start, end + 1):
        # The specified partial-year convention applies whenever final-year
        # quarter rows are present, even if a stale annual-looking row exists.
        if year == end and quarters.get(year):
            values[year] = float(np.mean(quarters[year]))
            quarter_counts[year] = len(quarters[year])
        elif year in annual:
            values[year] = annual[year]
        else:
            raise ValueError("Missing annual nominal observation for year %d in %s" % (year, path))
    return values, quarter_counts, sheet


def parse_date(value: Any) -> Optional[datetime]:
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    if isinstance(value, str) and DATE_TEXT_RE.match(value):
        converted = pd.to_datetime(value, errors="coerce")
        if not pd.isna(converted):
            return converted.to_pydatetime()
    return None


def extract_annual_cpi(path: str, start: int, end: int) -> Tuple[Dict[int, float], str]:
    """Discover a dated CPI table and average all available observations by year."""
    best: Optional[Tuple[int, "pd.DataFrame", int, int, str]] = None
    for sheet, frame in read_sheets(path):
        for dcol in range(frame.shape[1]):
            dated_rows = [(r, parse_date(frame.iat[r, dcol])) for r in range(frame.shape[0])]
            dated_rows = [(r, dt) for r, dt in dated_rows if dt is not None]
            if len(dated_rows) < 4:
                continue
            for vcol in range(frame.shape[1]):
                if vcol == dcol:
                    continue
                numeric_count = sum(numeric(frame.iat[r, vcol]) is not None for r, _ in dated_rows)
                score = min(len(dated_rows), numeric_count)
                candidate = (score, frame, dcol, vcol, sheet)
                if best is None or score > best[0]:
                    best = candidate
    if best is None or best[0] < 4:
        raise ValueError("Could not locate a dated numeric CPI series in %s" % path)
    _, frame, dcol, vcol, sheet = best
    grouped: Dict[int, List[float]] = {}
    for row in range(frame.shape[0]):
        dt = parse_date(frame.iat[row, dcol])
        val = numeric(frame.iat[row, vcol])
        if dt is not None and val is not None and start <= dt.year <= end:
            grouped.setdefault(dt.year, []).append(val)
    annual: Dict[int, float] = {}
    for year in range(start, end + 1):
        if not grouped.get(year):
            raise ValueError("CPI has no usable observation for year %d" % year)
        annual[year] = float(np.mean(grouped[year]))
        if not math.isfinite(annual[year]) or annual[year] <= 0:
            raise ValueError("CPI annual average is invalid for year %d" % year)
    return annual, sheet


def hp_cycle(log_values: "np.ndarray", smoothing: float) -> "np.ndarray":
    n = len(log_values)
    if n < 3:
        raise ValueError("HP filtering requires at least three observations")
    if not math.isfinite(smoothing) or smoothing < 0:
        raise ValueError("lambda must be a finite nonnegative number")
    # D has rows [0,...,1,-2,1,...,0], so D'D is the HP curvature penalty.
    d = np.zeros((n - 2, n), dtype=float)
    for row in range(n - 2):
        d[row, row : row + 3] = (1.0, -2.0, 1.0)
    trend = np.linalg.solve(np.eye(n) + smoothing * (d.T @ d), log_values)
    return log_values - trend


def require_input(obj: Dict[str, Any], key: str, expected: type) -> Any:
    value = obj.get(key)
    if expected is str:
        if not isinstance(value, str) or not value:
            raise ValueError("%s must be a nonempty string" % key)
    elif expected is int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("%s must be an integer" % key)
    return value


def run(spec: Dict[str, Any]) -> Dict[str, Any]:
    if IMPORT_ERROR:
        raise RuntimeError("Required Python packages pandas and numpy are unavailable: " + IMPORT_ERROR)
    pce_path = require_input(spec, "pce_xls", str)
    pfi_path = require_input(spec, "pfi_xls", str)
    cpi_path = require_input(spec, "cpi_xlsx", str)
    output = require_input(spec, "output", str)
    start = require_input(spec, "start_year", int)
    end = require_input(spec, "end_year", int)
    smoothing = spec.get("lambda")
    if isinstance(smoothing, bool) or not isinstance(smoothing, (int, float)):
        raise ValueError("lambda must be numeric")
    smoothing = float(smoothing)
    if start >= end:
        raise ValueError("start_year must precede end_year")
    for path in (pce_path, pfi_path, cpi_path):
        if not os.path.isfile(path):
            raise ValueError("Input file does not exist: " + path)

    pce, pce_quarters, pce_sheet = extract_nominal(pce_path, start, end)
    pfi, pfi_quarters, pfi_sheet = extract_nominal(pfi_path, start, end)
    cpi, cpi_sheet = extract_annual_cpi(cpi_path, start, end)
    years = list(range(start, end + 1))
    pce_real = np.array([pce[y] / cpi[y] * 100.0 for y in years], dtype=float)
    pfi_real = np.array([pfi[y] / cpi[y] * 100.0 for y in years], dtype=float)
    if not np.all(np.isfinite(pce_real)) or not np.all(np.isfinite(pfi_real)):
        raise ValueError("Deflation produced nonfinite values")
    if np.any(pce_real <= 0) or np.any(pfi_real <= 0):
        raise ValueError("Nominal/CPI inputs must yield strictly positive real values before logging")
    pce_cycle = hp_cycle(np.log(pce_real), smoothing)
    pfi_cycle = hp_cycle(np.log(pfi_real), smoothing)
    if float(np.std(pce_cycle)) == 0.0 or float(np.std(pfi_cycle)) == 0.0:
        raise ValueError("At least one HP cycle has zero variance; Pearson correlation is undefined")
    coefficient = float(np.corrcoef(pce_cycle, pfi_cycle)[0, 1])
    if not math.isfinite(coefficient):
        raise ValueError("Pearson correlation is nonfinite")
    rounded = format(coefficient, ".5f")
    parent = os.path.dirname(os.path.abspath(output))
    if not os.path.isdir(parent):
        raise ValueError("Output directory does not exist: " + parent)
    with open(output, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(rounded + "\n")
    return {
        "ok": True,
        "correlation": coefficient,
        "written": rounded,
        "output": output,
        "years": [start, end],
        "n_observations": len(years),
        "lambda": smoothing,
        "source_sheets": {"first_series": pce_sheet, "second_series": pfi_sheet, "cpi": cpi_sheet},
        "final_year_quarter_counts": {"first_series": pce_quarters.get(end, 0), "second_series": pfi_quarters.get(end, 0)},
    }


def main() -> None:
    try:
        spec = json.load(sys.stdin)
        if not isinstance(spec, dict):
            raise ValueError("stdin must contain one JSON object")
        result = run(spec)
        print(json.dumps(result, sort_keys=True, allow_nan=False))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        sys.exit(1)


if __name__ == "__main__":
    main()
