"""End-to-end entrypoint for the open-Dicke steady-state Wigner task.

Reads a JSON config from stdin, writes <case>.csv files, and prints a JSON
validation summary to stdout. See SKILL.md for the schema.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np  # noqa: E402
import dicke_lib as dl  # noqa: E402


def _read_config():
    data = sys.stdin.read()
    if not data.strip():
        return {}
    return json.loads(data)


def main():
    cfg = _read_config()
    N = int(cfg.get("N", 4))
    n_max = int(cfg.get("n_max", 16))
    w0 = float(cfg.get("w0", 1.0))
    wc = float(cfg.get("wc", 1.0))
    kappa = float(cfg.get("kappa", 1.0))
    g = float(cfg.get("g", 2.0 / np.sqrt(N)))
    grid = int(cfg.get("grid", 1000))
    xmin = float(cfg.get("xmin", -6.0))
    xmax = float(cfg.get("xmax", 6.0))
    outdir = cfg.get("output_dir", ".")
    cases = cfg.get("cases", [1, 2, 3, 4])
    method = cfg.get("steadystate_method")
    fmt = cfg.get("fmt", "%.12e")
    validate_only = bool(cfg.get("validate_only", False))

    try:
        if validate_only:
            # Small, cheap instance for the pre-grid sanity checks.
            sv_nphot = int(cfg.get("validate_nphot", 6))
            sv_grid = int(cfg.get("validate_grid", 60))
            results = {}
            grids = {}
            for idx in cases:
                W, m = dl.run_case(idx, N, sv_nphot, w0, wc, g, kappa,
                                   sv_grid, xmin, xmax,
                                   steadystate_method=method)
                results[str(idx)] = m
                grids[idx] = W
            distinct, all_distinct = _distinctness(grids, cases)
            print(json.dumps({"status": "ok", "mode": "validate",
                              "results": results, "distinct": distinct,
                              "all_distinct": all_distinct}))
            return

        os.makedirs(outdir, exist_ok=True)
        results = {}
        grids = {}
        for idx in cases:
            W, m = dl.run_case(idx, N, n_max, w0, wc, g, kappa,
                               grid, xmin, xmax, steadystate_method=method)
            path = os.path.join(outdir, "%d.csv" % idx)
            np.savetxt(path, W, delimiter=",", fmt=fmt)
            m["path"] = path
            results[str(idx)] = m
            grids[idx] = W
        distinct, all_distinct = _distinctness(grids, cases)
        print(json.dumps({"status": "ok", "results": results,
                          "distinct": distinct, "all_distinct": all_distinct}))
    except Exception as exc:  # pragma: no cover
        print(json.dumps({"status": "error", "error": repr(exc)}))
        sys.exit(1)


def _distinctness(grids, cases):
    import numpy as np
    distinct = {}
    all_distinct = True
    cl = list(cases)
    for i in range(len(cl)):
        for j in range(i + 1, len(cl)):
            a, b = cl[i], cl[j]
            d = float(np.max(np.abs(grids[a] - grids[b])))
            distinct["%s-%s" % (a, b)] = d
            if d < 1e-9:
                all_distinct = False
    return distinct, all_distinct


if __name__ == "__main__":
    main()
