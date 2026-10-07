"""Shared helpers for running GLM, editing its namelist, and scoring RMSE.

These functions are task-independent: all file paths, spans, and parameters are
supplied by the caller / current task at runtime.
"""
import os
import re
import shutil
import subprocess

import numpy as np


# ----------------------------- namelist I/O -----------------------------

def read_text(path):
    with open(path, "r") as fh:
        return fh.read()


def write_text(path, text):
    with open(path, "w") as fh:
        fh.write(text)


def _fmt_value(v):
    if isinstance(v, bool):
        return ".true." if v else ".false."
    if isinstance(v, (int, float)):
        return repr(v)
    s = str(v)
    # numeric-looking strings are left bare; everything else is single-quoted
    if re.fullmatch(r"[-+]?\d+(\.\d*)?([eE][-+]?\d+)?", s.strip()):
        return s.strip()
    if s.startswith("'") or s.startswith('"'):
        return s
    return "'%s'" % s


def get_param(text, key):
    m = re.search(r"(?m)^\s*" + re.escape(key) + r"\s*=\s*(.*?)\s*$", text)
    if not m:
        return None
    return m.group(1).split("!")[0].strip()


def set_param(text, key, value, block=None):
    """Replace `key = ...` (keeping leading indent); insert into &block if absent."""
    val = _fmt_value(value)
    pat = re.compile(r"(?m)^(\s*)" + re.escape(key) + r"\s*=.*$")
    if pat.search(text):
        return pat.sub(lambda m: "%s%s = %s" % (m.group(1), key, val), text, count=1)
    if block:
        bpat = re.compile(r"(?m)^(\s*&" + re.escape(block.lstrip('&')) + r"\s*)$")
        bm = bpat.search(text)
        if bm:
            insert = "\n   %s = %s" % (key, val)
            return text[: bm.end()] + insert + text[bm.end():]
    raise KeyError("key %r not found and no usable block %r" % (key, block))


# Mapping of calibration/control keys to their namelist block, so missing keys
# can be inserted in a sensible place.
KEY_BLOCK = {
    "timefmt": "time", "start": "time", "stop": "time", "dt": "time",
    "timezone": "time", "num_days": "time",
    "out_dir": "output", "out_fn": "output", "nsave": "output",
    "Kw": "light",
    "wind_factor": "meteorology", "sw_factor": "meteorology",
    "lw_factor": "meteorology", "rain_factor": "meteorology",
    "at_factor": "meteorology", "rh_factor": "meteorology",
    "cd": "meteorology", "ce": "meteorology", "ch": "meteorology",
    "coef_mix_conv": "glm_setup", "coef_mix_hyp": "glm_setup",
    "coef_wind_stir": "glm_setup", "coef_mix_shear": "glm_setup",
    "coef_mix_turb": "glm_setup", "coef_mix_KH": "glm_setup",
}


def apply_params(text, params):
    for k, v in params.items():
        text = set_param(text, k, v, block=KEY_BLOCK.get(k))
    return text


# ----------------------------- running GLM -----------------------------

def clean_dir(path):
    if os.path.isdir(path):
        shutil.rmtree(path)
    os.makedirs(path, exist_ok=True)


def run_glm(glm_bin, cwd, timeout=1800):
    attempts = [[glm_bin], [glm_bin, "--nml", "glm3.nml"]]
    last = None
    for cmd in attempts:
        try:
            p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                               timeout=timeout)
        except FileNotFoundError as e:
            return {"returncode": 127, "stdout": "", "stderr": str(e)}
        except subprocess.TimeoutExpired as e:
            return {"returncode": 124, "stdout": "", "stderr": "timeout: %s" % e}
        last = {"returncode": p.returncode,
                "stdout": p.stdout[-4000:], "stderr": p.stderr[-4000:]}
        if p.returncode == 0:
            return last
    return last


# ----------------------------- reading output.nc -----------------------------

def load_sim(output_nc):
    import netCDF4
    import pandas as pd
    nc = netCDF4.Dataset(output_nc)
    try:
        tvar = nc.variables["time"]
        raw = tvar[:]
        units = getattr(tvar, "units", "hours since 2000-01-01 00:00:00")
        cal = getattr(tvar, "calendar", "standard")
        try:
            dts = netCDF4.num2date(np.asarray(raw), units, calendar=cal,
                                   only_use_cftime_datetimes=False,
                                   only_use_python_datetimes=True)
            times = pd.to_datetime([d.isoformat() for d in np.atleast_1d(dts)])
        except Exception:
            dts = netCDF4.num2date(np.asarray(raw), units, calendar=cal)
            times = pd.to_datetime([str(d) for d in np.atleast_1d(dts)])
        tname = "temp" if "temp" in nc.variables else _find_var(nc, ["temp", "wtr"])
        zname = "z" if "z" in nc.variables else _find_var(nc, ["z", "heights"])
        temp = np.asarray(nc.variables[tname][:], dtype=float)
        z = np.asarray(nc.variables[zname][:], dtype=float)
        if "NS" in nc.variables:
            ns = np.asarray(nc.variables["NS"][:]).astype(int).reshape(-1)
        else:
            ns = np.full(temp.shape[0], temp.shape[1], dtype=int)
        # mask fill / huge sentinel values
        fill = 1e30
        temp = np.where(np.abs(temp) > fill, np.nan, temp)
        z = np.where(np.abs(z) > fill, np.nan, z)
        return {"times": times, "temp": temp, "z": z, "ns": ns}
    finally:
        nc.close()


def _find_var(nc, cands):
    for c in cands:
        for name in nc.variables:
            if name.lower() == c.lower():
                return name
    for c in cands:
        for name in nc.variables:
            if c.lower() in name.lower():
                return name
    raise KeyError("none of %r in output variables %r" % (cands, list(nc.variables)))


def temp_at_depth(z_row, t_row, ns, depth):
    n = int(ns)
    if n <= 0:
        return np.nan
    zs = np.asarray(z_row[:n], dtype=float)
    ts = np.asarray(t_row[:n], dtype=float)
    ok = np.isfinite(zs) & np.isfinite(ts)
    zs, ts = zs[ok], ts[ok]
    if zs.size == 0:
        return np.nan
    order = np.argsort(zs)
    zs, ts = zs[order], ts[order]
    surface = zs[-1]
    target = surface - float(depth)  # depth measured downward from surface
    return float(np.interp(target, zs, ts))


# ----------------------------- field observations -----------------------------

def load_field(field_csv, cols=None):
    import pandas as pd
    df = pd.read_csv(field_csv)
    cols = cols or {}
    tcol = cols.get("time") or _detect_col(df, ["datetime", "date", "time", "sampledate"])
    dcol = cols.get("depth") or _detect_col(df, ["depth", "z"])
    vcol = cols.get("temp") or _detect_temp_col(df)
    out = pd.DataFrame({
        "time": pd.to_datetime(df[tcol], errors="coerce"),
        "depth": pd.to_numeric(df[dcol], errors="coerce"),
        "temp": pd.to_numeric(df[vcol], errors="coerce"),
    }).dropna()
    return out, {"time": tcol, "depth": dcol, "temp": vcol}


def _detect_col(df, keys):
    low = {c.lower(): c for c in df.columns}
    for k in keys:
        for lc, orig in low.items():
            if lc == k:
                return orig
    for k in keys:
        for lc, orig in low.items():
            if k in lc:
                return orig
    raise KeyError("could not detect column among %r in %r" % (keys, list(df.columns)))


def _detect_temp_col(df):
    low = {c.lower(): c for c in df.columns}
    for lc, orig in low.items():
        if lc in ("temp", "wtemp", "wtr", "watertemp", "temperature"):
            return orig
    for lc, orig in low.items():
        if "temp" in lc and "oxy" not in lc and "do" not in lc:
            return orig
    raise KeyError("could not detect temperature column in %r" % list(df.columns))


# ----------------------------- RMSE -----------------------------

def compute_rmse(output_nc, field_csv, start=None, stop=None, cols=None,
                 tol_hours=24.0):
    import pandas as pd
    sim = load_sim(output_nc)
    field, used = load_field(field_csv, cols)
    if start is not None:
        field = field[field["time"] >= pd.to_datetime(start)]
    if stop is not None:
        field = field[field["time"] <= pd.to_datetime(stop)]
    sim_times = sim["times"]
    sim_int = sim_times.view("int64")
    tol_ns = int(tol_hours * 3600 * 1e9)
    pairs = []
    by_depth = {}
    for _, row in field.iterrows():
        ot = np.int64(pd.Timestamp(row["time"]).value)
        pos = int(np.searchsorted(sim_int, ot))
        best = None
        for cand in (pos - 1, pos):
            if 0 <= cand < len(sim_int):
                d = abs(int(sim_int[cand]) - int(ot))
                if best is None or d < best[0]:
                    best = (d, cand)
        if best is None or best[0] > tol_ns:
            continue
        idx = best[1]
        st = temp_at_depth(sim["z"][idx], sim["temp"][idx], sim["ns"][idx], row["depth"])
        if not np.isfinite(st):
            continue
        err = st - float(row["temp"])
        pairs.append(err)
        by_depth.setdefault(round(float(row["depth"]), 2), []).append(err)
    pairs = np.asarray(pairs, dtype=float)
    rmse = float(np.sqrt(np.mean(pairs ** 2))) if pairs.size else None
    bd = {str(k): float(np.sqrt(np.mean(np.asarray(v) ** 2)))
          for k, v in sorted(by_depth.items())}
    return {"rmse": rmse, "n": int(pairs.size), "by_depth": bd,
            "columns_used": used}
