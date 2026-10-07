#!/usr/bin/env python3
"""Compute an annual real-series HP-cycle correlation from supplied workbooks.

Reads one JSON object from stdin and emits a JSON summary to stdout.  See SKILL.md
for the schema.  The requested single-number deliverable is written separately.
"""
import json
import math
import re
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

YEAR_RE = re.compile(r"^\s*((?:18|19|20)\d{2})(?:\s*(?:\*|\([^)]*\)|[a-z]))?\s*$", re.I)
QUARTER_RE = re.compile(
    r"^\s*((?:18|19|20)\d{2})\s*(?::|,|\-|\s)?\s*(?:q(?:uarter)?\s*)?([1-4])\s*$", re.I
)
DATE_PREFIX_RE = re.compile(r"^\s*((?:18|19|20)\d{2})[-/]\d{1,2}(?:[-/]\d{1,2})?\s*$")


def numeric(value):
    """Return a finite numeric value, or None, while preserving missing markers."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if isinstance(value, (int, float, np.number)) and not isinstance(value, bool):
        value = float(value)
        return value if math.isfinite(value) else None
    text = str(value).strip()
    if not text or text.lower() in {"na", "n.a.", "--", "-", "…"}:
        return None
    # ERP footnote marks commonly follow otherwise numeric cell text.
    cleaned = re.sub(r"[$,]", "", text)
    cleaned = re.sub(r"\s*(?:\*|†|‡|[a-z])\s*$", "", cleaned, flags=re.I)
    try:
        result = float(cleaned)
        return result if math.isfinite(result) else None
    except ValueError:
        return None


def annual_label(value):
    if isinstance(value, (int, np.integer)) and 1800 <= int(value) <= 2100:
        return int(value)
    if isinstance(value, float) and value.is_integer() and 1800 <= value <= 2100:
        return int(value)
    match = YEAR_RE.match(str(value))
    return int(match.group(1)) if match else None


def quarter_label(value):
    match = QUARTER_RE.match(str(value))
    return (int(match.group(1)), int(match.group(2))) if match else None


def workbook_frames(path):
    """Load all nonempty sheets raw, retaining title rows and merged-header layout."""
    try:
        book = pd.ExcelFile(path)
    except Exception as exc:
        raise RuntimeError(f"Cannot open workbook {path!r}: {exc}") from exc
    frames = []
    for sheet in book.sheet_names:
        frame = pd.read_excel(book, sheet_name=sheet, header=None)
        if not frame.empty:
            frames.append((sheet, frame))
    if not frames:
        raise RuntimeError(f"No nonempty worksheets in {path!r}")
    return frames


def extract_erp_total(path, start_year, end_year):
    """Extract annual total levels, falling back to within-year quarter averages."""
    candidates = []
    for sheet, frame in workbook_frames(path):
        # ERP labels occur in a single column. Score columns by annual/quarter label count.
        label_scores = []
        for col in range(frame.shape[1]):
            annuals = sum(annual_label(v) is not None for v in frame.iloc[:, col])
            quarters = sum(quarter_label(v) is not None for v in frame.iloc[:, col])
            label_scores.append((annuals + quarters, annuals, -col, col))
        _, annual_count, _, year_col = max(label_scores)
        if annual_count == 0:
            continue

        labeled_rows = []
        for ridx, value in enumerate(frame.iloc[:, year_col]):
            year = annual_label(value)
            quarter = None
            if year is None:
                q = quarter_label(value)
                if q:
                    year, quarter = q
            if year is not None and start_year <= year <= end_year:
                labeled_rows.append((ridx, year, quarter))
        if not labeled_rows:
            continue

        # The total is the leftmost consistently populated numeric column after year.
        # This derives structure from the data table, not a fixed workbook coordinate.
        col_scores = []
        for col in range(year_col + 1, frame.shape[1]):
            count = sum(numeric(frame.iat[ridx, col]) is not None for ridx, _, _ in labeled_rows)
            if count:
                col_scores.append((count, -col, col))
        if not col_scores:
            continue
        best_count, _, total_col = max(col_scores)
        if best_count < max(2, int(0.75 * len(labeled_rows))):
            continue

        annual = {}
        quarterly = defaultdict(list)
        for ridx, year, quarter in labeled_rows:
            val = numeric(frame.iat[ridx, total_col])
            if val is None:
                continue
            if quarter is None:
                annual[year] = val
            else:
                quarterly[year].append((quarter, val))
        coverage = sum(y in annual or y in quarterly for y in range(start_year, end_year + 1))
        candidates.append((coverage, sheet, annual, quarterly, year_col, total_col))

    if not candidates:
        raise RuntimeError(f"Could not identify ERP annual data in {path!r}")
    _, sheet, annual, quarterly, year_col, total_col = max(candidates, key=lambda x: x[0])
    result, fallback = {}, []
    missing = []
    for year in range(start_year, end_year + 1):
        if year in annual:
            result[year] = annual[year]
        elif year in quarterly:
            # If a publication has only part of a year, average only its available quarters.
            result[year] = float(np.mean([v for _, v in quarterly[year]]))
            fallback.append(year)
        else:
            missing.append(year)
    if missing:
        raise RuntimeError(f"Missing ERP observations for {missing} in {path!r}")
    if any(v <= 0 for v in result.values()):
        raise RuntimeError(f"Nonpositive extracted total values in {path!r}")
    return result, {"sheet": sheet, "year_column": int(year_col), "total_column": int(total_col),
                    "quarterly_fallback_years": fallback}


def date_year(value):
    """Get calendar year from a dated CPI cell without treating bare years as dates."""
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return int(value.year)
    text = str(value).strip()
    match = DATE_PREFIX_RE.match(text)
    if match:
        return int(match.group(1))
    # Supports spreadsheet text such as 'Jan 1973' but avoids title/header strings.
    if re.search(r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)", text, re.I) and re.search(r"(?:18|19|20)\d{2}", text):
        parsed = pd.to_datetime(text, errors="coerce")
        if not pd.isna(parsed):
            return int(parsed.year)
    return None


def extract_annual_cpi(path, start_year, end_year):
    observations = defaultdict(list)
    for _, frame in workbook_frames(path):
        for _, row in frame.iterrows():
            values = row.tolist()
            date_positions = [(i, date_year(v)) for i, v in enumerate(values)]
            date_positions = [(i, y) for i, y in date_positions if y is not None]
            for pos, year in date_positions:
                if not start_year <= year <= end_year:
                    continue
                # CPI observation is normally immediately right of the date, but locate
                # the first numeric field after it to accommodate harmless blank columns.
                val = next((numeric(v) for v in values[pos + 1:] if numeric(v) is not None), None)
                if val is not None and val > 0:
                    observations[year].append(val)
                break
    missing = [y for y in range(start_year, end_year + 1) if not observations[y]]
    if missing:
        raise RuntimeError(f"CPI workbook lacks dated observations for years {missing}")
    return {year: float(np.mean(observations[year])) for year in range(start_year, end_year + 1)}


def hp_cycle(log_values, lam):
    """Return x - trend for the standard two-sided HP minimization problem."""
    x = np.asarray(log_values, dtype=float)
    n = len(x)
    if n < 3:
        raise ValueError("HP filtering requires at least three annual observations")
    if not np.all(np.isfinite(x)) or lam <= 0:
        raise ValueError("HP inputs must be finite and lambda must be positive")
    d = np.zeros((n - 2, n), dtype=float)
    for i in range(n - 2):
        d[i, i:i + 3] = (1.0, -2.0, 1.0)
    trend = np.linalg.solve(np.eye(n) + float(lam) * (d.T @ d), x)
    return x - trend


def main(config):
    start = int(config.get("start_year", 1973))
    end = int(config.get("end_year", 2024))
    lam = float(config.get("lambda", 100))
    if start > end:
        raise ValueError("start_year must not exceed end_year")
    pce_path = config.get("pce_path", "/root/ERP-2025-table10.xls")
    pfi_path = config.get("pfi_path", "/root/ERP-2025-table12.xls")
    cpi_path = config.get("cpi_path", "/root/CPI.xlsx")
    answer_path = Path(config.get("answer_path", "/root/answer.txt"))

    pce, pce_info = extract_erp_total(pce_path, start, end)
    pfi, pfi_info = extract_erp_total(pfi_path, start, end)
    cpi = extract_annual_cpi(cpi_path, start, end)
    years = list(range(start, end + 1))
    real_pce = np.array([pce[y] / cpi[y] for y in years], dtype=float)
    real_pfi = np.array([pfi[y] / cpi[y] for y in years], dtype=float)
    if np.any(real_pce <= 0) or np.any(real_pfi <= 0):
        raise RuntimeError("Deflation produced nonpositive real values")
    pce_cycle = hp_cycle(np.log(real_pce), lam)
    pfi_cycle = hp_cycle(np.log(real_pfi), lam)
    corr = float(np.corrcoef(pce_cycle, pfi_cycle)[0, 1])
    if not math.isfinite(corr):
        raise RuntimeError("Pearson correlation is not finite")
    answer_path.parent.mkdir(parents=True, exist_ok=True)
    answer_path.write_text(f"{corr:.5f}\n", encoding="utf-8")
    return {"correlation": corr, "rounded": f"{corr:.5f}", "years_used": len(years),
            "year_range": [start, end], "lambda": lam,
            "pce_extraction": pce_info, "pfi_extraction": pfi_info,
            "answer_path": str(answer_path)}


if __name__ == "__main__":
    try:
        raw = sys.stdin.read()
        config = json.loads(raw) if raw.strip() else {}
        if not isinstance(config, dict):
            raise ValueError("stdin JSON must be an object")
        print(json.dumps(main(config), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        sys.exit(1)
