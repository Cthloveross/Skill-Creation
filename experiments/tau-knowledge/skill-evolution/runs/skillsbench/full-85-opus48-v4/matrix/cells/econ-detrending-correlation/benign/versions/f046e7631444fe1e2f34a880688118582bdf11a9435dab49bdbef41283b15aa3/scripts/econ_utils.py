"""Shared helpers for the econ-detrending-correlation Skill.

All functions derive structure from the supplied workbooks at runtime; nothing
here hardcodes instance answers, sheet names, or cell coordinates.
"""
import re


def read_sheet(path):
    """Return the first worksheet as a list of row lists (ragged ok).

    Uses pandas with an engine chosen by extension; falls back across engines.
    """
    import pandas as pd
    engines = []
    low = path.lower()
    if low.endswith(".xlsx") or low.endswith(".xlsm"):
        engines = ["openpyxl", None]
    elif low.endswith(".xls"):
        engines = ["xlrd", None]
    else:
        engines = [None, "openpyxl", "xlrd"]
    last = None
    for eng in engines:
        try:
            if eng is None:
                df = pd.read_excel(path, header=None)
            else:
                df = pd.read_excel(path, header=None, engine=eng)
            return df.values.tolist()
        except Exception as e:  # pragma: no cover - environment dependent
            last = e
    raise RuntimeError("could not read %s: %s" % (path, last))


def _get(row, i):
    return row[i] if 0 <= i < len(row) else None


def to_float(v):
    """Coerce a cell to float or return None."""
    if v is None:
        return None
    try:
        import math
        if isinstance(v, float) and math.isnan(v):
            return None
    except Exception:
        pass
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = v.strip().replace(",", "")
        if s in ("", "-", "...", "n.a.", "NA", "na", "--"):
            return None
        try:
            return float(s)
        except ValueError:
            return None
    return None


def parse_year(v):
    """Return an int year in [1900,2100] if the cell looks like one, else None."""
    if isinstance(v, str):
        s = v.strip()
        m = re.fullmatch(r"(19|20)\d\d", s)
        if m:
            return int(s)
    f = to_float(v)
    if f is None:
        return None
    if abs(f - round(f)) < 1e-6 and 1900 <= f <= 2100:
        return int(round(f))
    return None


_QUARTER_TOKENS = {"I": 1, "II": 2, "III": 3, "IV": 4,
                   "Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4}


def detect_quarter(row):
    """Return a quarter int if any cell marks a quarter, else None.

    Matches standalone roman numerals I/II/III/IV, Q1-Q4, and embedded
    'YYYY:I' / 'YYYY I' style labels.
    """
    for cell in row:
        if not isinstance(cell, str):
            continue
        s = cell.strip()
        up = s.upper()
        if up in _QUARTER_TOKENS:
            return _QUARTER_TOKENS[up]
        m = re.search(r"(19|20)\d\d\s*[:\s]\s*(IV|III|II|I|Q[1-4])\b", up)
        if m:
            return _QUARTER_TOKENS.get(m.group(2), 1)
    return None


def detect_year_col(rows, ncols):
    best, best_count = 0, -1
    for c in range(ncols):
        cnt = sum(1 for r in rows if parse_year(_get(r, c)) is not None)
        if cnt > best_count:
            best, best_count = c, cnt
    return best


def detect_total_col(rows, ncols, year_col):
    year_rows = [r for r in rows if parse_year(_get(r, year_col)) is not None]
    n = max(1, len(year_rows))
    for c in range(year_col + 1, ncols):
        cnt = 0
        for r in year_rows:
            v = _get(r, c)
            if to_float(v) is not None and parse_year(v) is None:
                cnt += 1
        if cnt >= 0.5 * n:
            return c
    # fallback: first column after year_col with any numeric
    for c in range(year_col + 1, ncols):
        if any(to_float(_get(r, c)) is not None for r in year_rows):
            return c
    raise RuntimeError("no total column found right of year column")


def extract_erp_totals(path, year_col=None, total_col=None):
    """Extract {year: total} from an ERP .xls table.

    Annual rows win; a year that only appears with quarter markers gets the
    mean of its available quarters. Returns (totals, debug).
    """
    rows = read_sheet(path)
    ncols = max((len(r) for r in rows), default=0)
    rows = [list(r) + [None] * (ncols - len(r)) for r in rows]
    if year_col is None:
        year_col = detect_year_col(rows, ncols)
    if total_col is None:
        total_col = detect_total_col(rows, ncols, year_col)

    annual = {}
    quarterly = {}
    current_year = None
    for r in rows:
        yv = parse_year(_get(r, year_col))
        if yv is not None:
            current_year = yv
        q = detect_quarter(r)
        tot = to_float(_get(r, total_col))
        if tot is None:
            continue
        if q is not None:
            if current_year is not None:
                quarterly.setdefault(current_year, []).append(tot)
        elif yv is not None:
            annual.setdefault(yv, tot)

    totals = {}
    source = {}
    for y in set(annual) | set(quarterly):
        if y in annual:
            totals[y] = annual[y]
            source[y] = "annual"
        else:
            vals = quarterly[y]
            totals[y] = sum(vals) / len(vals)
            source[y] = "quarterly-avg(%d)" % len(vals)
    debug = {"year_col": year_col, "total_col": total_col,
             "n_annual": len(annual), "n_quarterly_years": len(quarterly),
             "source": source}
    return totals, debug


def _year_from_date(v):
    if isinstance(v, bool):
        return None
    if hasattr(v, "year"):
        try:
            return int(v.year)
        except Exception:
            pass
    if isinstance(v, str):
        m = re.match(r"(19|20)\d\d", v.strip())
        if m:
            return int(m.group(0))
    return None


def extract_cpi_annual(path):
    """Return {year: annual_average_cpi} from a (monthly) CPI workbook."""
    rows = read_sheet(path)
    buckets = {}
    for r in rows:
        year = None
        for cell in r:
            y = _year_from_date(cell)
            if y is not None:
                year = y
                break
        if year is None:
            continue
        val = None
        for cell in r:
            f = to_float(cell)
            if f is None:
                continue
            # skip cells that are themselves plain years
            if 1900 <= f <= 2100 and abs(f - round(f)) < 1e-6:
                continue
            val = f
            break
        if val is None:
            continue
        buckets.setdefault(year, []).append(val)
    return {y: sum(v) / len(v) for y, v in buckets.items()}


def hp_filter(y, lam):
    """Return (trend, cycle) using the standard HP filter solution."""
    import numpy as np
    y = np.asarray(y, dtype=float)
    T = len(y)
    if T < 3:
        return y.copy(), np.zeros_like(y)
    I = np.eye(T)
    D = np.zeros((T - 2, T))
    for i in range(T - 2):
        D[i, i] = 1.0
        D[i, i + 1] = -2.0
        D[i, i + 2] = 1.0
    trend = np.linalg.solve(I + lam * (D.T @ D), y)
    return trend, y - trend


def pearson(a, b):
    import numpy as np
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    return float(np.corrcoef(a, b)[0, 1])
