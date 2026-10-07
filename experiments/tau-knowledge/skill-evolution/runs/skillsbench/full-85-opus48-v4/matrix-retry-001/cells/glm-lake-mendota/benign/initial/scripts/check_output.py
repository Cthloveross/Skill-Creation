#!/usr/bin/env python3
"""Validate a GLM output.nc: covers requested span, has finite temperature.

stdin JSON: {"output_nc":..,"start":..,"stop":..}
stdout JSON: {"ok":bool,"covers_span":bool,"has_temp":bool,"finite":bool,
              "t_first":str,"t_last":str,"n_times":int,"error":str?}
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import glm_lib


def main():
    req = json.load(sys.stdin)
    out = {"ok": False}
    try:
        import pandas as pd
        if not os.path.exists(req["output_nc"]):
            out["error"] = "output.nc missing"
            json.dump(out, sys.stdout); sys.stdout.write("\n"); return
        sim = glm_lib.load_sim(req["output_nc"])
        times = sim["times"]
        out["n_times"] = int(len(times))
        out["t_first"] = str(times.min())
        out["t_last"] = str(times.max())
        out["has_temp"] = bool(sim["temp"].size)
        # finite over active layers of the last few steps
        finite = True
        for i in range(len(times)):
            n = int(sim["ns"][i])
            if n > 0 and not np.isfinite(sim["temp"][i][:n]).any():
                finite = False
                break
        out["finite"] = bool(finite)
        covers = True
        if req.get("start") is not None:
            covers &= times.min() <= pd.to_datetime(req["start"]) + pd.Timedelta(days=2)
        if req.get("stop") is not None:
            covers &= times.max() >= pd.to_datetime(req["stop"]) - pd.Timedelta(days=2)
        out["covers_span"] = bool(covers)
        out["ok"] = bool(out["has_temp"] and out["finite"] and covers)
    except Exception as e:  # noqa: BLE001
        out["error"] = repr(e)
    json.dump(out, sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
