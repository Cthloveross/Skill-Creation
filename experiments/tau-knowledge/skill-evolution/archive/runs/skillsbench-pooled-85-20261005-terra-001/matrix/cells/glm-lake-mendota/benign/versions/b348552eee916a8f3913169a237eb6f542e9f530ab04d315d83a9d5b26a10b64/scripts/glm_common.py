"""Shared deterministic parsing and validation helpers for GLM calibration scripts."""
from __future__ import annotations

import csv
import datetime as dt
import math
import os
import re
from typing import Any, Dict, List, Tuple


def json_error(message: str, **extra: Any) -> Dict[str, Any]:
    result: Dict[str, Any] = {"ok": False, "error": message}
    result.update(extra)
    return result


def parse_datetime(value: Any) -> dt.datetime:
    text = str(value).strip().replace("Z", "+00:00")
    if not text:
        raise ValueError("empty datetime")
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        parsed = None
        for fmt in ("%Y/%m/%d", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S", "%m/%d/%Y %H:%M"):
            try:
                parsed = dt.datetime.strptime(text, fmt)
                break
            except ValueError:
                pass
        if parsed is None:
            raise ValueError("unrecognized datetime: %r" % text)
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(dt.timezone.utc).replace(tzinfo=None)
    return parsed


def normalized(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def pick_column(names: List[str], exact: Tuple[str, ...], contains: Tuple[str, ...]) -> str:
    indexed = [(name, normalized(name)) for name in names]
    for target in exact:
        for name, norm in indexed:
            if norm == target:
                return name
    for token in contains:
        for name, norm in indexed:
            if token in norm:
                return name
    raise ValueError("could not identify a required column; available columns: " + ", ".join(names))


def read_observations(path: str, start: dt.datetime, stop: dt.datetime) -> Tuple[List[Tuple[dt.datetime, float, float]], Dict[str, str]]:
    """Read CSV records as (datetime, positive-down depth in m, temperature C)."""
    with open(path, "r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError("observation CSV has no header")
        fields = [x for x in reader.fieldnames if x]
        date_col = pick_column(fields, ("datetime", "date", "sampledate", "timestamp", "time"), ("date", "time"))
        depth_col = pick_column(fields, ("depth", "depthm", "depthmeters", "depthmeter"), ("depth", "dep"))
        temp_col = pick_column(fields, ("temperature", "temp", "watertemp", "watertemperature", "tempc"), ("temperature", "watertemp", "temp"))
        rows: List[Tuple[dt.datetime, float, float]] = []
        for row in reader:
            try:
                when = parse_datetime(row[date_col])
                depth = float(str(row[depth_col]).strip())
                temp = float(str(row[temp_col]).strip())
            except (TypeError, ValueError, KeyError):
                continue
            if not (math.isfinite(depth) and math.isfinite(temp)):
                continue
            # Celsius is expected. Explicit Fahrenheit-labelled columns are converted.
            if "fahrenheit" in normalized(temp_col) or normalized(temp_col).endswith("tempf"):
                temp = (temp - 32.0) * 5.0 / 9.0
            # CSVs that explicitly state centimetres are normalized to metres.
            if "cm" in normalized(depth_col) and "m" not in normalized(depth_col).replace("cm", ""):
                depth /= 100.0
            if start <= when <= stop and depth >= 0:
                rows.append((when, depth, temp))
    if not rows:
        raise ValueError("no finite observation records fall within the requested interval")
    rows.sort(key=lambda x: x[0])
    return rows, {"date": date_col, "depth": depth_col, "temperature": temp_col}


def _open_dataset(path: str):
    """Return (dataset, closer, backend), preferring netCDF4 but allowing scipy classic."""
    try:
        from netCDF4 import Dataset  # type: ignore
        ds = Dataset(path, "r")
        return ds, ds.close, "netCDF4"
    except ImportError:
        try:
            from scipy.io import netcdf_file  # type: ignore
            ds = netcdf_file(path, "r", mmap=False)
            return ds, ds.close, "scipy.netcdf_file"
        except ImportError as exc:
            raise RuntimeError("NetCDF support unavailable: install netCDF4 or scipy") from exc


def _attr(var: Any, name: str, default: str = "") -> str:
    try:
        if hasattr(var, "getncattr"):
            value = var.getncattr(name)
        else:
            value = getattr(var, name)
        if isinstance(value, bytes):
            return value.decode("utf-8", "replace")
        return str(value)
    except Exception:
        return default


def _find_variable(variables: Dict[str, Any], preferred: Tuple[str, ...], contains: Tuple[str, ...], reject: Tuple[str, ...] = ()) -> str:
    names = list(variables.keys())
    lower = {name: name.lower() for name in names}
    for wanted in preferred:
        for name in names:
            if lower[name] == wanted:
                return name
    for token in contains:
        for name in names:
            val = lower[name]
            if token in val and not any(bad in val for bad in reject):
                return name
    raise ValueError("could not identify NetCDF variable; available: " + ", ".join(names))


def _decode_times(values: Any, units: str) -> List[dt.datetime]:
    import numpy as np  # type: ignore
    match = re.match(r"^\s*(seconds?|minutes?|hours?|days?)\s+since\s+(.+?)\s*$", units, re.I)
    if not match:
        raise ValueError("unsupported NetCDF time units: %r" % units)
    unit, origin_text = match.groups()
    origin = parse_datetime(origin_text.strip().replace(" UTC", ""))
    scale = {"second": 1, "minute": 60, "hour": 3600, "day": 86400}
    key = unit.lower().rstrip("s")
    flat = np.asarray(values, dtype=float).reshape(-1)
    return [origin + dt.timedelta(seconds=float(v) * scale[key]) for v in flat]


def _extract_temp_and_depth(ds: Any) -> Tuple[List[dt.datetime], Any, Any, Dict[str, str]]:
    import numpy as np  # type: ignore
    variables = ds.variables
    time_name = _find_variable(variables, ("time", "datetime"), ("time",))
    temp_name = _find_variable(variables, ("temp", "temperature", "water_temp"), ("temp", "temperature"), ("surface", "air", "sed", "ice"))
    time_var = variables[time_name]
    times = _decode_times(time_var[:], _attr(time_var, "units"))
    tvar = variables[temp_name]
    dims = list(getattr(tvar, "dimensions", ()))
    if time_name not in dims:
        # Case-insensitive dimension matching for some old NetCDF writers.
        candidates = [i for i, x in enumerate(dims) if x.lower() == time_name.lower()]
        if not candidates:
            raise ValueError("temperature variable has no time dimension")
        time_axis = candidates[0]
    else:
        time_axis = dims.index(time_name)
    depth_candidates = []
    for i, dim in enumerate(dims):
        low = dim.lower()
        if i != time_axis and (low in ("z", "depth", "depths", "layer") or "depth" in low):
            depth_candidates.append((i, dim))
    if depth_candidates:
        depth_axis, depth_dim = depth_candidates[0]
        depth_name = depth_dim if depth_dim in variables else _find_variable(variables, ("z", "depth"), ("depth", "z"))
    else:
        depth_name = _find_variable(variables, ("z", "depth", "depths"), ("depth", "z"))
        depth_dim = getattr(variables[depth_name], "dimensions", (depth_name,))[0]
        if depth_dim not in dims:
            raise ValueError("cannot associate vertical coordinate with temperature variable")
        depth_axis = dims.index(depth_dim)

    # Index singleton geographic or ensemble dimensions at zero. Non-singleton extras are unsafe to average silently.
    raw = tvar[:]
    shape = list(np.asarray(raw).shape)
    index = []
    retained = []
    for i, size in enumerate(shape):
        if i in (time_axis, depth_axis):
            index.append(slice(None))
            retained.append(i)
        elif size == 1:
            index.append(0)
        else:
            raise ValueError("temperature has unsupported non-singleton dimension %s" % dims[i])
    arr = np.ma.filled(np.asarray(raw)[tuple(index)], np.nan).astype(float)
    # retained indexes are still in original order after indexing.
    if retained != [time_axis, depth_axis]:
        # The sliced result axes occur in retained order.
        source_time_axis = retained.index(time_axis)
        source_depth_axis = retained.index(depth_axis)
        arr = np.moveaxis(arr, (source_time_axis, source_depth_axis), (0, 1))
    if arr.ndim != 2 or arr.shape[0] != len(times):
        raise ValueError("temperature extraction did not produce time by depth values")

    zvar = variables[depth_name]
    zraw = np.ma.filled(zvar[:], np.nan).astype(float)
    if zraw.ndim == 1:
        z = np.tile(zraw.reshape(1, -1), (arr.shape[0], 1))
    elif zraw.ndim == 2:
        zdims = list(getattr(zvar, "dimensions", ()))
        if time_name in zdims:
            za = zdims.index(time_name)
            z = np.moveaxis(zraw, za, 0)
        else:
            z = zraw
        if z.shape != arr.shape:
            raise ValueError("time-varying vertical coordinate shape differs from temperature")
    else:
        raise ValueError("vertical coordinate must be one- or two-dimensional")
    units = _attr(tvar, "units").lower()
    if units in ("k", "kelvin") or (not units and np.nanmedian(arr) > 100):
        arr = arr - 273.15
    meta = {
        "time_variable": time_name,
        "temperature_variable": temp_name,
        "depth_variable": depth_name,
        "depth_positive": _attr(zvar, "positive"),
        "depth_standard_name": _attr(zvar, "standard_name"),
    }
    return times, z, arr, meta


def _depth_transform(z: Any, mode: str) -> Any:
    import numpy as np  # type: ignore
    if mode == "raw":
        return z
    if mode == "absolute":
        return np.abs(z)
    maxv = np.nanmax(z, axis=1, keepdims=True)
    minv = np.nanmin(z, axis=1, keepdims=True)
    if mode == "max_minus":
        return maxv - z
    if mode == "minus_min":
        return z - minv
    if mode == "negative_minus_min":
        return -z + np.nanmax(-z, axis=1, keepdims=True) * 0.0
    raise ValueError("unknown depth transform")


def _choose_depth_mode(z: Any, obs_depths: List[float], meta: Dict[str, str]) -> str:
    """Select a documented coordinate convention based on attributes and usable range."""
    positive = meta.get("depth_positive", "").lower()
    standard = meta.get("depth_standard_name", "").lower()
    if "down" in positive or standard == "depth":
        return "raw"
    candidates = ("raw", "absolute", "max_minus", "minus_min", "negative_minus_min")
    best_mode, best_score = "raw", -1
    for mode in candidates:
        transformed = _depth_transform(z, mode)
        lo = float(__import__("numpy").nanmin(transformed))
        hi = float(__import__("numpy").nanmax(transformed))
        score = sum(1 for d in obs_depths if lo - 1e-6 <= d <= hi + 1e-6)
        if score > best_score:
            best_mode, best_score = mode, score
    return best_mode


def _profile_value(depths: Any, temperatures: Any, query_depth: float) -> float:
    import numpy as np  # type: ignore
    valid = np.isfinite(depths) & np.isfinite(temperatures)
    if valid.sum() < 2:
        return float("nan")
    x = depths[valid]
    y = temperatures[valid]
    order = np.argsort(x)
    x, y = x[order], y[order]
    x, unique_idx = np.unique(x, return_index=True)
    y = y[unique_idx]
    if len(x) < 2 or query_depth < x[0] or query_depth > x[-1]:
        return float("nan")
    return float(np.interp(query_depth, x, y))


def validate_output(output_path: str, observation_csv: str, start_value: Any, stop_value: Any) -> Dict[str, Any]:
    """Recompute depth/time-aligned RMSE from a produced GLM NetCDF file."""
    if not os.path.isfile(output_path):
        return json_error("expected output NetCDF does not exist", output_path=output_path)
    try:
        start, stop = parse_datetime(start_value), parse_datetime(stop_value)
        observations, columns = read_observations(observation_csv, start, stop)
        ds, closer, backend = _open_dataset(output_path)
        try:
            times, z, temps, meta = _extract_temp_and_depth(ds)
        finally:
            closer()
        if not times:
            return json_error("output has an empty time coordinate")
        mode = _choose_depth_mode(z, [r[1] for r in observations], meta)
        z = _depth_transform(z, mode)
        numeric_times = [(x - dt.datetime(1970, 1, 1)).total_seconds() for x in times]
        matched_sq: List[float] = []
        for when, depth, observed in observations:
            value = (when - dt.datetime(1970, 1, 1)).total_seconds()
            idx = __import__("bisect").bisect_left(numeric_times, value)
            if idx == 0:
                if value != numeric_times[0]:
                    continue
                simulated = _profile_value(z[0], temps[0], depth)
            elif idx >= len(numeric_times):
                continue
            else:
                left, right = idx - 1, idx
                a = _profile_value(z[left], temps[left], depth)
                b = _profile_value(z[right], temps[right], depth)
                if not (math.isfinite(a) and math.isfinite(b)):
                    continue
                fraction = (value - numeric_times[left]) / (numeric_times[right] - numeric_times[left])
                simulated = a + fraction * (b - a)
            if math.isfinite(simulated):
                matched_sq.append((simulated - observed) ** 2)
        coverage = {
            "first": times[0].isoformat(sep=" "),
            "last": times[-1].isoformat(sep=" "),
            "requested_start": start.isoformat(sep=" "),
            "requested_stop": stop.isoformat(sep=" "),
            "contains_requested_bounds": times[0] <= start and times[-1] >= stop,
        }
        if not matched_sq:
            return json_error("no finite observation/simulation matches after time and depth alignment", coverage=coverage, observation_columns=columns, **meta)
        rmse = math.sqrt(sum(matched_sq) / len(matched_sq))
        return {
            "ok": True,
            "rmse_celsius": rmse,
            "matched_observations": len(matched_sq),
            "input_observations_in_period": len(observations),
            "coverage": coverage,
            "observation_columns": columns,
            "depth_transform": mode,
            "netcdf_backend": backend,
            **meta,
        }
    except Exception as exc:
        return json_error(str(exc), output_path=output_path)
