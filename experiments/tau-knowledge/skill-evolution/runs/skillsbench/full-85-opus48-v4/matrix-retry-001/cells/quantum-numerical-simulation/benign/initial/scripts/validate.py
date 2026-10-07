#!/usr/bin/env python3
"""Validate already-written Wigner CSV grids without recomputing.

stdin JSON: {"files": ["1.csv", ...] | null, "outdir": ".",
             "ngrid": 1000, "xmin": -6, "xmax": 6}
If "files" is null, defaults to 1.csv..4.csv in outdir.
stdout JSON: per-file shape/finite/normalization plus overall distinctness.
"""
import sys
import os
import json

import numpy as np


def main():
    raw = sys.stdin.read()
    cfg = json.loads(raw) if raw.strip() else {}
    outdir = cfg.get("outdir", ".")
    ngrid = int(cfg.get("ngrid", 1000))
    xmin = float(cfg.get("xmin", -6.0))
    xmax = float(cfg.get("xmax", 6.0))
    files = cfg.get("files")
    if not files:
        files = ["1.csv", "2.csv", "3.csv", "4.csv"]

    dx = (xmax - xmin) / (ngrid - 1)
    out = {"ok": True, "files": [], "distinct": None, "errors": []}
    mats = []
    for f in files:
        path = f if os.path.isabs(f) else os.path.join(outdir, f)
        rec = {"file": path}
        try:
            W = np.loadtxt(path, delimiter=",")
            mats.append(W)
            rec["shape"] = [int(W.shape[0]), int(W.shape[1])]
            rec["finite"] = bool(np.all(np.isfinite(W)))
            rec["norm"] = float(np.sum(W) * dx * dx)
            rec["shape_ok"] = (W.shape == (ngrid, ngrid))
            if not (rec["finite"] and rec["shape_ok"]
                    and abs(rec["norm"] - 1.0) < 0.15):
                out["ok"] = False
                out["errors"].append("%s failed basic checks" % path)
        except Exception as exc:
            out["ok"] = False
            out["errors"].append("%s: %s" % (path, exc))
            mats.append(None)
        out["files"].append(rec)

    good = [m for m in mats if isinstance(m, np.ndarray)]
    if len(good) >= 2:
        distinct = True
        for i in range(len(good)):
            for j in range(i + 1, len(good)):
                if good[i].shape == good[j].shape and \
                        float(np.max(np.abs(good[i] - good[j]))) < 1e-9:
                    distinct = False
        out["distinct"] = distinct
        if not distinct:
            out["ok"] = False
            out["errors"].append("grids not distinct")

    print(json.dumps(out))
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
