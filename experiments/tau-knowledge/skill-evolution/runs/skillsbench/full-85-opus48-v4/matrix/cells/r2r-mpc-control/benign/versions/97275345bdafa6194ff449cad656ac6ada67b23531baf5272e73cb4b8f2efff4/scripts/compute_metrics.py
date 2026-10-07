#!/usr/bin/env python3
"""Recompute metrics.json from an existing control_log.json.

Usage:
  python3 compute_metrics.py --log control_log.json --config system_config.json \
      --out metrics.json

Definitions (explicit, from the delivered trace):
  per-step error = mean(|tensions - reference_tensions|)
  steady_state_error = mean of per-step error over the final 1.0 s
  settling_time = earliest time after which error stays <= 2.0 N
  max_tension / min_tension = extrema over all logged tensions
"""
import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mpc_lib as ml  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", default="/root/control_log.json")
    ap.add_argument("--config", default="/root/system_config.json")
    ap.add_argument("--out", default="/root/metrics.json")
    ap.add_argument("--band", type=float, default=2.0)
    ap.add_argument("--ss-window", type=float, default=1.0)
    args = ap.parse_args()

    with open(args.log) as f:
        log = json.load(f)
    data = log["data"] if isinstance(log, dict) else log
    config = ml.load_config(args.config)
    ref_T, _, _ = ml.extract_references(config)

    ref_T = np.asarray(ref_T, float)
    times = np.array([d["time"] for d in data], float)
    Tmat = np.array([d["tensions"] for d in data], float)
    errs = np.mean(np.abs(Tmat - ref_T[None, :]), axis=1)
    tend = times[-1]
    mask = times >= (tend - args.ss_window)
    ss = float(np.mean(errs[mask])) if mask.any() else float(errs[-1])
    settle = float(tend)
    for i in range(len(errs)):
        if np.all(errs[i:] <= args.band):
            settle = float(times[i])
            break
    metrics = {
        "steady_state_error": ss,
        "settling_time": settle,
        "max_tension": float(np.max(Tmat)),
        "min_tension": float(np.min(Tmat)),
    }
    with open(args.out, "w") as f:
        json.dump(metrics, f, indent=2)
    print(json.dumps(metrics))


if __name__ == "__main__":
    main()
