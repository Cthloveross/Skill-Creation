#!/usr/bin/env python3
"""Recompute RMSE of a GLM output.nc against field observations.

stdin JSON: {"output_nc":..,"field_csv":..,"start":..,"stop":..,"cols":{...},"tol_hours":24}
stdout JSON: {"rmse":..,"n":..,"by_depth":{..},"columns_used":{..}}
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import glm_lib


def main():
    req = json.load(sys.stdin)
    res = glm_lib.compute_rmse(
        req["output_nc"], req["field_csv"],
        start=req.get("start"), stop=req.get("stop"),
        cols=req.get("cols"), tol_hours=float(req.get("tol_hours", 24.0)),
    )
    json.dump(res, sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
