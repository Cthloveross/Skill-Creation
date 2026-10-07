"""Independently validate CSV Wigner grids already written to disk.

Input JSON (stdin):
  {"output_dir": ".", "cases": [1,2,3,4], "grid": 1000,
   "xmin": -6, "xmax": 6}
Output JSON (stdout): per-file shape/finiteness/normalization + distinctness.
"""
import json
import os
import sys

import numpy as np


def main():
    data = sys.stdin.read()
    cfg = json.loads(data) if data.strip() else {}
    outdir = cfg.get("output_dir", ".")
    cases = cfg.get("cases", [1, 2, 3, 4])
    grid = int(cfg.get("grid", 1000))
    xmin = float(cfg.get("xmin", -6.0))
    xmax = float(cfg.get("xmax", 6.0))
    dx = (xmax - xmin) / (grid - 1)

    results = {}
    arrays = {}
    ok = True
    for idx in cases:
        path = os.path.join(outdir, "%d.csv" % idx)
        if not os.path.exists(path):
            results[str(idx)] = {"exists": False}
            ok = False
            continue
        W = np.loadtxt(path, delimiter=",")
        arrays[idx] = W
        shape_ok = (W.shape == (grid, grid))
        finite = bool(np.all(np.isfinite(W)))
        norm = float(np.sum(W) * dx * dx)
        results[str(idx)] = {
            "exists": True,
            "shape": list(W.shape),
            "shape_ok": shape_ok,
            "finite": finite,
            "norm": norm,
            "norm_ok": 0.8 < norm < 1.2,
        }
        if not (shape_ok and finite):
            ok = False

    distinct = {}
    all_distinct = True
    cl = [c for c in cases if c in arrays]
    for i in range(len(cl)):
        for j in range(i + 1, len(cl)):
            a, b = cl[i], cl[j]
            d = float(np.max(np.abs(arrays[a] - arrays[b])))
            distinct["%s-%s" % (a, b)] = d
            if d < 1e-9:
                all_distinct = False

    print(json.dumps({"status": "ok" if ok and all_distinct else "warn",
                      "results": results, "distinct": distinct,
                      "all_distinct": all_distinct}))


if __name__ == "__main__":
    main()
