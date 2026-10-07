#!/usr/bin/env python3
"""Compute timestamp-nearest and vertically interpolated temperature RMSE.
JSON stdin -> JSON stdout. Requires numpy, pandas, and xarray.
"""
import json, sys
import numpy as np
import pandas as pd
import xarray as xr


def choose(options, requested, candidates, label):
    if requested:
        if requested not in options:
            raise ValueError(f"{label} {requested!r} not found; available: {list(options)}")
        return requested
    lower = {str(x).lower(): x for x in options}
    for candidate in candidates:
        if candidate in lower:
            return lower[candidate]
    hits = [x for x in options if any(c in str(x).lower() for c in candidates)]
    if len(hits) == 1:
        return hits[0]
    raise ValueError(f"cannot uniquely identify {label}; specify it explicitly; available: {list(options)}")


def main():
    try:
        s = json.load(sys.stdin)
        obs = pd.read_csv(s["observations"])
        tc = choose(obs.columns, s.get("obs_time"), ["datetime", "date_time", "date", "time"], "observation time column")
        dc = choose(obs.columns, s.get("obs_depth"), ["depth", "depth_m", "z"], "observation depth column")
        vc = choose(obs.columns, s.get("obs_temperature"), ["temperature", "temp", "water_temp", "water_temperature"], "observation temperature column")
        otime = pd.to_datetime(obs[tc], errors="coerce")
        odeps = pd.to_numeric(obs[dc], errors="coerce").to_numpy(float)
        oval = pd.to_numeric(obs[vc], errors="coerce").to_numpy(float)
        valid_obs = otime.notna().to_numpy() & np.isfinite(odeps) & np.isfinite(oval)
        ds = xr.open_dataset(s["netcdf"], decode_times=True)
        tempname = s.get("temperature_variable")
        if not tempname:
            candidates = [n for n, a in ds.data_vars.items() if "temp" in n.lower() or "temperature" in str(a.attrs.get("standard_name", "")).lower()]
            if len(candidates) != 1:
                raise ValueError(f"cannot uniquely identify temperature variable; specify temperature_variable; candidates={candidates}")
            tempname = candidates[0]
        da = ds[tempname].squeeze(drop=True)
        tdim = s.get("model_time_dimension") or choose(da.dims, None, ["time", "datetime", "date"], "model time dimension")
        other_dims = [d for d in da.dims if d != tdim]
        if len(other_dims) != 1:
            raise ValueError(f"temperature variable must have time plus one vertical dimension; dims={da.dims}")
        zdim = s.get("model_depth_dimension") or other_dims[0]
        if tdim not in ds.coords:
            raise ValueError(f"no time coordinate for dimension {tdim}")
        mtime = pd.DatetimeIndex(pd.to_datetime(ds[tdim].values))
        if not mtime.is_monotonic_increasing:
            raise ValueError("model time coordinate is not increasing")
        zname = s.get("depth_variable")
        if zname:
            zarr = ds[zname]
        elif zdim in ds.coords:
            zarr = ds[zdim]
        else:
            found = [n for n, a in ds.variables.items() if zdim in a.dims and any(q in n.lower() for q in ("depth", "z", "layer"))]
            if len(found) != 1:
                raise ValueError(f"cannot identify depth coordinate for {zdim}; specify depth_variable")
            zarr = ds[found[0]]
        values = np.asarray(da.transpose(tdim, zdim).values, dtype=float)
        zvalues = np.asarray(zarr.values, dtype=float)
        if zvalues.ndim == 1:
            zvalues = np.broadcast_to(zvalues, values.shape)
        elif zvalues.shape != values.shape:
            # Permit reversed dimension order for a time-varying vertical coordinate.
            zvalues = np.asarray(zarr.transpose(tdim, zdim).values, dtype=float)
        if zvalues.shape != values.shape:
            raise ValueError(f"depth shape {zvalues.shape} does not match temperature shape {values.shape}")
        tolerance = pd.Timedelta(s.get("max_time_gap", "12h"))
        query = pd.DatetimeIndex(otime[valid_obs])
        idx = mtime.get_indexer(query, method="nearest", tolerance=tolerance)
        original = np.flatnonzero(valid_obs)
        pred = np.full(len(obs), np.nan)
        mode = s.get("depth_mode", "direct")
        for oi, mi in zip(original, idx):
            if mi < 0:
                continue
            z = zvalues[mi].copy()
            y = values[mi].copy()
            target = odeps[oi]
            if mode == "absolute":
                z = np.abs(z)
            elif mode == "from_surface":
                target = np.nanmax(z) - target
            elif mode != "direct":
                raise ValueError("depth_mode must be direct, absolute, or from_surface")
            good = np.isfinite(z) & np.isfinite(y)
            if good.sum() < 2:
                continue
            z, y = z[good], y[good]
            order = np.argsort(z)
            z, y = z[order], y[order]
            if target < z[0] or target > z[-1]:
                continue
            pred[oi] = np.interp(target, z, y)
        use = valid_obs & np.isfinite(pred)
        rmse = float(np.sqrt(np.mean((pred[use] - oval[use]) ** 2))) if use.any() else None
        maxrmse = s.get("max_rmse")
        result = {"ok": bool(use.any()), "rmse_celsius": rmse, "matched": int(use.sum()),
                  "valid_observations": int(valid_obs.sum()), "unmatched_time_or_invalid": int((~valid_obs).sum() + ((idx < 0).sum() if len(idx) else 0)),
                  "unmatched_depth_or_profile": int(valid_obs.sum() - use.sum() - (idx < 0).sum()),
                  "mapping": {"obs_time": tc, "obs_depth": dc, "obs_temperature": vc,
                              "temperature_variable": tempname, "depth_variable": zarr.name,
                              "depth_mode": mode, "max_time_gap": str(tolerance)},
                  "model_time_range": [str(mtime.min()), str(mtime.max())],
                  "observation_time_range": [str(otime[valid_obs].min()), str(otime[valid_obs].max())],
                  "all_predictions_finite": bool(np.isfinite(pred[use]).all())}
        if maxrmse is not None:
            result["max_rmse"] = float(maxrmse)
            result["meets_threshold"] = bool(rmse is not None and rmse < float(maxrmse))
        ds.close()
        print(json.dumps(result))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}))

if __name__ == "__main__":
    main()
