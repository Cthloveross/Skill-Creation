"""Reusable helpers for configuring, running, and evaluating GLM.

All functions are task-independent: paths, spans, parameters and observation
columns are supplied by the caller / detected at runtime. Nothing instance
specific is hardcoded.
"""
import os
import re
import shutil
import subprocess
from datetime import datetime, timedelta

import numpy as np


def read_text(path):
    with open(path, "r") as f:
        return f.read()


def write_text(path, text):
    with open(path, "w") as f:
        f.write(text)


def param_exists(text, name):
    return re.search(r"(?mi)^\s*" + re.escape(name) + r"\s*=", text) is not None


def get_param(text, name):
    m = re.search(r"(?mi)^\s*" + re.escape(name) + r"\s*=\s*(.*)$", text)
    return m.group(1).strip() if m else None


def set_param(text, name, value, is_string=False):
    """Replace the value of an existing namelist parameter (first occurrence).

    Returns (new_text, changed_bool). Does NOT create missing parameters.
    """
    if is_string:
        val = "'%s'" % value
    else:
        val = str(value)
    pat = re.compile(r"(?mi)^(\s*" + re.escape(name) + r"\s*=).*$")
    if not pat.search(text):
        return text, False

    def _repl(m):
        return m.group(1) + " " + val

    return pat.sub(_repl, text, count=1), True


def apply_params(text, params):
    """params: dict name -> value or (value, is_string). Returns (text, skipped)."""
    skipped = []
    for name, spec in params.items():
        if isinstance(spec, (list, tuple)) and len(spec) == 2:
            value, is_string = spec
        else:
            value, is_string = spec, isinstance(spec, str)
        text, changed = set_param(text, name, value, is_string=is_string)
        if not changed:
            skipped.append(name)
    return text, skipped


def configure_run(text, start, stop, out_dir, out_fn, nsave=24):
    """Set span/output in the namelist. Only sets parameters that exist."""
    for name, value, is_str in [
        ("timefmt", 2, False),
        ("start", start, True),
        ("stop", stop, True),
        ("out_dir", out_dir, True),
        ("out_fn", out_fn, True),
        ("nsave", nsave, False),
    ]:
        text, _ = set_param(text, name, value, is_string=is_str)
    return text


def run_glm(nml_path, glm_bin="/usr/local/bin/glm", timeout=1800):
    workdir = os.path.dirname(os.path.abspath(nml_path))
    cmd = [glm_bin]
    if os.path.basename(nml_path) != "glm3.nml":
        cmd += ["--nml", nml_path]
    try:
        r = subprocess.run(
            cmd, cwd=workdir, capture_output=True, text=True, timeout=timeout
        )
        return {
            "returncode": r.returncode,
            "stdout": r.stdout[-4000:],
            "stderr": r.stderr[-4000:],
        }
    except Exception as e:  # noqa: BLE001
        return {"returncode": -1, "stdout": "", "stderr": str(e)}


def _parse_time_units(vals, units):
    m = re.match(r"(\w+)\s+since\s+(.+)", units.strip())
    unit = m.group(1).lower()
    base = m.group(2).strip()
    base_dt = None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            base_dt = datetime.strptime(base, fmt)
            break
        except ValueError:
            continue
    if base_dt is None:
        raise ValueError("Cannot parse time units: %s" % units)
    mult_days = {
        "seconds": 1.0 / 86400,
        "minutes": 1.0 / 1440,
        "hours": 1.0 / 24,
        "hour": 1.0 / 24,
        "days": 1.0,
        "day": 1.0,
    }[unit]
    return [base_dt + timedelta(days=float(v) * mult_days) for v in np.asarray(vals)]


def load_sim(nc_path):
    """Return (times[list datetime], z[time,z], temp[time,z], NS[time]).

    z = elevation of layer tops (m), increasing with index up to NS.
    """
    try:
        from netCDF4 import Dataset

        ds = Dataset(nc_path)
        temp = np.ma.filled(ds.variables["temp"][:], np.nan)
        z = np.ma.filled(ds.variables["z"][:], np.nan)
        tvar = ds.variables["time"]
        units = tvar.units
        tvals = tvar[:]
        if "NS" in ds.variables:
            ns = np.asarray(ds.variables["NS"][:]).astype(int)
        else:
            ns = np.isfinite(temp).sum(axis=1).astype(int)
        ds.close()
    except ImportError:
        import xarray as xr

        ds = xr.open_dataset(nc_path, decode_times=False)
        temp = np.asarray(ds["temp"].values, dtype=float)
        z = np.asarray(ds["z"].values, dtype=float)
        units = ds["time"].attrs["units"]
        tvals = np.asarray(ds["time"].values)
        if "NS" in ds:
            ns = np.asarray(ds["NS"].values).astype(int)
        else:
            ns = np.isfinite(temp).sum(axis=1).astype(int)
        ds.close()
    times = _parse_time_units(tvals, units)
    return times, z, temp, ns


def temp_at_depth(z_row, temp_row, ns_t, depth):
    n = int(ns_t)
    if n <= 0:
        return np.nan
    zr = np.asarray(z_row[:n], dtype=float)
    tr = np.asarray(temp_row[:n], dtype=float)
    good = np.isfinite(zr) & np.isfinite(tr)
    zr, tr = zr[good], tr[good]
    if zr.size == 0:
        return np.nan
    order = np.argsort(zr)
    zr, tr = zr[order], tr[order]
    bottoms = np.concatenate(([0.0], zr[:-1]))
    mids = (bottoms + zr) / 2.0
    surface = zr[-1]
    target_elev = surface - float(depth)
    if target_elev <= mids[0]:
        return float(tr[0])
    if target_elev >= mids[-1]:
        return float(tr[-1])
    return float(np.interp(target_elev, mids, tr))


def load_obs(csv_path):
    """Return list of (datetime, depth_m, temp_C). Columns auto-detected."""
    import pandas as pd

    df = pd.read_csv(csv_path)
    lc = {c.lower(): c for c in df.columns}

    def find(include, exclude=()):
        for low, orig in lc.items():
            if any(k in low for k in include) and not any(e in low for e in exclude):
                return orig
        return None

    dcol = find(["datetime", "sampledate", "date", "time"], exclude=["flag"])
    depthcol = find(["depth"], exclude=["flag"])
    tcol = find(["temp"], exclude=["flag"])
    if dcol is None or depthcol is None or tcol is None:
        raise ValueError(
            "Could not detect date/depth/temp columns in %s; found %s"
            % (csv_path, list(df.columns))
        )
    df[dcol] = pd.to_datetime(df[dcol], errors="coerce")
    out = []
    for _, r in df.iterrows():
        try:
            d = r[dcol]
            if pd.isna(d):
                continue
            depth = float(r[depthcol])
            tv = float(r[tcol])
            if not np.isfinite(depth) or not np.isfinite(tv):
                continue
            out.append((d.to_pydatetime(), depth, tv))
        except (ValueError, TypeError):
            continue
    return out


def compute_rmse(nc_path, obs, day_tolerance_sec=86400):
    times, z, temp, ns = load_sim(nc_path)
    sim_dates = [t.date() for t in times]
    date_index = {}
    for i, d in enumerate(sim_dates):
        date_index.setdefault(d, i)
    sq = []
    for dt_obs, depth, tobs in obs:
        d = dt_obs.date()
        if d in date_index:
            j = date_index[d]
        else:
            diffs = [abs((t - dt_obs).total_seconds()) for t in times]
            if not diffs:
                continue
            j = int(np.argmin(diffs))
            if diffs[j] > day_tolerance_sec:
                continue
        tsim = temp_at_depth(z[j], temp[j], ns[j], depth)
        if not np.isfinite(tsim):
            continue
        sq.append((tsim - tobs) ** 2)
    if not sq:
        return None, 0
    return float(np.sqrt(np.mean(sq))), len(sq)


def clean_dir(path):
    if os.path.isdir(path):
        shutil.rmtree(path)
    os.makedirs(path, exist_ok=True)


def verify_output(nc_path):
    info = {
        "out_nc": nc_path,
        "exists": os.path.exists(nc_path),
        "has_temp": False,
        "time_min": None,
        "time_max": None,
        "finite_fraction": None,
    }
    if not info["exists"]:
        return info
    try:
        times, z, temp, ns = load_sim(nc_path)
        info["has_temp"] = True
        info["time_min"] = times[0].isoformat()
        info["time_max"] = times[-1].isoformat()
        info["n_times"] = len(times)
        finite = np.isfinite(temp)
        info["finite_fraction"] = float(finite.mean()) if temp.size else 0.0
    except Exception as e:  # noqa: BLE001
        info["error"] = str(e)
    return info
