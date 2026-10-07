"""Reusable, task-independent helpers for reflow-process compliance.

All numeric policy (limits, bands, thresholds, geometry, priorities) is passed
in by the caller after reading the handbook. Nothing here hardcodes a factory
policy or an instance answer.
"""
import csv
import io
import math


def read_csv(path):
    """Return (header_list, list_of_row_dicts). Uses only the stdlib."""
    with open(path, newline="", encoding="utf-8-sig", errors="replace") as fh:
        reader = csv.reader(fh)
        rows = list(reader)
    if not rows:
        return [], []
    header = [h.strip() for h in rows[0]]
    out = []
    for r in rows[1:]:
        if not any(c.strip() for c in r):
            continue
        d = {header[i]: (r[i] if i < len(r) else "") for i in range(len(header))}
        out.append(d)
    return header, out


def to_float(v):
    try:
        if v is None:
            return None
        s = str(v).strip()
        if s == "" or s.lower() in ("nan", "none", "null"):
            return None
        return float(s)
    except (TypeError, ValueError):
        return None


def guess_col(header, *keywords):
    """Return first header whose lowercased name contains any keyword."""
    low = {h: h.lower() for h in header}
    for kw in keywords:
        for h in header:
            if kw in low[h]:
                return h
    return None


def detect_thermo_columns(header, override=None):
    override = override or {}
    cols = {
        "run_id": override.get("run_id") or guess_col(header, "run"),
        "tc_id": override.get("tc_id")
        or guess_col(header, "tc", "thermocouple", "sensor", "channel"),
        "time": override.get("time")
        or guess_col(header, "time", "sec", "timestamp", "t_s", "elapsed"),
        "temp": override.get("temp")
        or guess_col(header, "temp", "celsius", "deg", "_c"),
    }
    return cols


def group_traces(rows, cols):
    """Return {run_id: {tc_id: [(t, temp), ...sorted by t]}}."""
    traces = {}
    for r in rows:
        run = r.get(cols["run_id"])
        tc = r.get(cols["tc_id"])
        t = to_float(r.get(cols["time"]))
        temp = to_float(r.get(cols["temp"]))
        if run is None or tc is None or t is None or temp is None:
            continue
        traces.setdefault(run, {}).setdefault(tc, []).append((t, temp))
    for run in traces:
        for tc in traces[run]:
            traces[run][tc].sort(key=lambda p: p[0])
    return traces


def max_preheat_ramp(samples, temp_low, temp_high, boundary="both_in_band"):
    """Max segment ramp (T2-T1)/(t2-t1) within the preheat temperature band.

    boundary:
      'both_in_band' - include a segment only if both endpoint temps lie in
                        [temp_low, temp_high].
      'any_overlap'  - include a segment if either endpoint is in band.
      'all'          - ignore band, use every valid segment.
    Returns max ramp (float) or None if no usable segment.
    """
    best = None
    for (t1, T1), (t2, T2) in zip(samples, samples[1:]):
        dt = t2 - t1
        if dt <= 0:
            continue
        if boundary != "all":
            in1 = (temp_low is None or T1 >= temp_low) and (
                temp_high is None or T1 <= temp_high
            )
            in2 = (temp_low is None or T2 >= temp_low) and (
                temp_high is None or T2 <= temp_high
            )
            if boundary == "both_in_band" and not (in1 and in2):
                continue
            if boundary == "any_overlap" and not (in1 or in2):
                continue
        r = (T2 - T1) / dt
        if best is None or r > best:
            best = r
    return best


def time_above(samples, threshold, inclusive=True):
    """Duration (s) a trace is above `threshold`, with linear interpolation of
    crossings. Handles equal endpoints and duplicate timestamps."""
    total = 0.0
    for (t1, T1), (t2, T2) in zip(samples, samples[1:]):
        dt = t2 - t1
        if dt <= 0:
            continue
        a1 = T1 > threshold or (inclusive and T1 == threshold)
        a2 = T2 > threshold or (inclusive and T2 == threshold)
        if a1 and a2:
            total += dt
        elif not a1 and not a2:
            continue
        else:
            # one endpoint above, one below -> interpolate crossing
            if T2 == T1:
                # cannot cross; treat per a1
                if a1:
                    total += dt
                continue
            frac = (threshold - T1) / (T2 - T1)
            frac = min(max(frac, 0.0), 1.0)
            t_cross = t1 + dt * frac
            if a1 and not a2:
                total += t_cross - t1
            else:  # not a1 and a2
                total += t2 - t_cross
    return total


def peak_temp(samples):
    if not samples:
        return None
    return max(T for _, T in samples)


def rnd(x, nd=2):
    if x is None:
        return None
    try:
        return round(float(x), nd)
    except (TypeError, ValueError):
        return None


def sort_run_ids(ids):
    return sorted(ids, key=lambda s: (str(s)))
