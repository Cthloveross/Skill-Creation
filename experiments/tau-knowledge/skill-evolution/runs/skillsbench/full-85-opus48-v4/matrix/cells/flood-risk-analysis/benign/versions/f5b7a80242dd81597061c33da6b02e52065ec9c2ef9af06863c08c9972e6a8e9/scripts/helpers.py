"""Reusable helpers for flood-risk analysis.

Task-independent building blocks: parse the station list, load NWS flood-stage
thresholds, select gage-height columns, and count flood days from USGS IV data.
"""
import re


def parse_station_ids(path):
    """Return ordered unique list of USGS station IDs (strings) from a file.

    Extracts runs of 8+ digits so leading zeros are preserved and header text
    is ignored. Falls back to any digit run of length >=5 if none of length 8.
    """
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    ids = re.findall(r"\d{8,}", text)
    if not ids:
        ids = re.findall(r"\d{5,}", text)
    seen = set()
    out = []
    for s in ids:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def _find_col(columns, needle):
    needle = needle.lower().replace(" ", "")
    for c in columns:
        if str(c).lower().replace(" ", "") == needle:
            return c
    for c in columns:
        if needle in str(c).lower().replace(" ", ""):
            return c
    return None


def load_nws_thresholds(url):
    """Return dict {usgs_id_str: flood_stage_float} for valid numeric stages."""
    import pandas as pd

    df = pd.read_csv(url, dtype=str, low_memory=False)
    usgs_col = _find_col(df.columns, "usgs id")
    stage_col = _find_col(df.columns, "flood stage")
    if usgs_col is None or stage_col is None:
        raise RuntimeError(
            "NWS report missing 'usgs id' or 'flood stage' columns; got %s"
            % list(df.columns)
        )
    thresholds = {}
    for _, row in df.iterrows():
        sid = row[usgs_col]
        if sid is None:
            continue
        sid = str(sid).strip()
        if not sid or sid.lower() == "nan":
            continue
        stage = pd.to_numeric(row[stage_col], errors="coerce")
        if stage != stage:  # NaN -> missing/non-numeric, exclude
            continue
        thresholds[sid] = float(stage)
    return thresholds


def gage_height_series(df):
    """Extract a numeric daily-indexable gage-height Series from an IV DataFrame.

    Selects columns containing parameter code 00065, excluding qualifier (_cd)
    columns, coerces to numeric, and reduces multiple sensors to the row-wise
    max. Returns a pandas Series indexed by the original datetime index, or None
    if no usable column is found.
    """
    import pandas as pd

    if df is None or len(df) == 0:
        return None
    cols = [
        c
        for c in df.columns
        if "00065" in str(c) and not str(c).endswith("_cd")
    ]
    if not cols:
        return None
    sub = df[cols].apply(pd.to_numeric, errors="coerce")
    series = sub.max(axis=1)
    series = series.dropna()
    if len(series) == 0:
        return None
    return series


def count_flood_days(series, flood_stage, start_date, end_date):
    """Count calendar days in [start_date, end_date] with daily-max >= stage.

    `series` is a datetime-indexed numeric Series of gage heights. Resamples to
    daily maximum, restricts to the requested date range (inclusive), and
    counts days meeting or exceeding the flood stage.
    """
    import pandas as pd

    if series is None or len(series) == 0:
        return 0
    s = series.copy()
    try:
        s.index = pd.to_datetime(s.index)
    except Exception:
        return 0
    # Drop timezone to align resampling to local calendar days.
    try:
        if getattr(s.index, "tz", None) is not None:
            s.index = s.index.tz_localize(None)
    except Exception:
        pass
    daily = s.resample("D").max().dropna()
    start = pd.Timestamp(start_date).normalize()
    end = pd.Timestamp(end_date).normalize()
    daily = daily[(daily.index.normalize() >= start) & (daily.index.normalize() <= end)]
    return int((daily >= flood_stage).sum())
