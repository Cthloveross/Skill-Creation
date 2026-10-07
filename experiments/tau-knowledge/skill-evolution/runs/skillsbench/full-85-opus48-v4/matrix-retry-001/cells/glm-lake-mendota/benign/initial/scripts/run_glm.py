#!/usr/bin/env python3
"""End-to-end GLM run + optional calibration + verification.

See SKILL.md for the full input schema. Minimal input only needs the paths and
span; sensible defaults are applied. All instance-specific values come from the
caller / current task at runtime.
"""
import itertools
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import glm_lib


def _grid_combos(grid):
    if not grid:
        return []
    keys = list(grid.keys())
    combos = []
    for vals in itertools.product(*[grid[k] for k in keys]):
        combos.append(dict(zip(keys, vals)))
    return combos


def _finalize_text(text, start, stop, out_dir, out_fn):
    text = glm_lib.set_param(text, "timefmt", 2, block="time")
    if start is not None:
        text = glm_lib.set_param(text, "start", start, block="time")
    if stop is not None:
        text = glm_lib.set_param(text, "stop", stop, block="time")
    text = glm_lib.set_param(text, "out_dir", out_dir, block="output")
    text = glm_lib.set_param(text, "out_fn", out_fn, block="output")
    return text


def _run_and_score(cfg, base_text, params):
    text = glm_lib.apply_params(base_text, params) if params else base_text
    glm_lib.write_text(cfg["nml"], text)
    glm_lib.clean_dir(cfg["out_abs_dir"])
    run = glm_lib.run_glm(cfg["glm_bin"], cfg["cwd"])
    rec = {"params": params, "returncode": run["returncode"], "rmse": None,
           "ok": False, "stderr_tail": run.get("stderr", "")[-800:]}
    if run["returncode"] == 0 and os.path.exists(cfg["output_nc"]):
        try:
            score = glm_lib.compute_rmse(cfg["output_nc"], cfg["field_csv"],
                                         start=cfg["start"], stop=cfg["stop"],
                                         cols=cfg["cols"])
            rec["rmse"] = score["rmse"]
            rec["n"] = score["n"]
            rec["ok"] = score["rmse"] is not None
        except Exception as e:  # noqa: BLE001
            rec["error"] = repr(e)
    return rec


def main():
    req = json.load(sys.stdin)
    cwd = req.get("cwd", "/root")
    out_dir = req.get("out_dir", "output")
    out_fn = req.get("out_fn", "output")
    cfg = {
        "nml": req.get("nml", os.path.join(cwd, "glm3.nml")),
        "glm_bin": req.get("glm_bin", "glm"),
        "cwd": cwd,
        "out_abs_dir": out_dir if os.path.isabs(out_dir) else os.path.join(cwd, out_dir),
        "field_csv": req.get("field_csv", os.path.join(cwd, "field_temp_oxy.csv")),
        "start": req.get("start"),
        "stop": req.get("stop"),
        "cols": req.get("cols"),
    }
    cfg["output_nc"] = os.path.join(cfg["out_abs_dir"], out_fn + ".nc")
    target = float(req.get("target_rmse", 2.0))
    do_cal = req.get("calibrate", True)
    grid = req.get("grid", {"wind_factor": [0.9, 1.0, 1.1],
                             "Kw": [0.3, 0.6], "sw_factor": [1.0]})
    max_runs = int(req.get("max_runs", 12))

    # Fix controllable namelist fields once; this becomes the baseline text.
    base_text = _finalize_text(glm_lib.read_text(cfg["nml"]),
                               cfg["start"], cfg["stop"], out_dir, out_fn)

    history = []
    baseline = _run_and_score(cfg, base_text, {})
    history.append(baseline)
    best = baseline if baseline["ok"] else None

    if do_cal and (best is None or best["rmse"] is None or best["rmse"] >= target):
        for params in _grid_combos(grid):
            if len(history) >= max_runs + 1:
                break
            rec = _run_and_score(cfg, base_text, params)
            history.append(rec)
            if rec["ok"] and (best is None or best["rmse"] is None
                              or rec["rmse"] < best["rmse"]):
                best = rec
            if best is not None and best["rmse"] is not None and best["rmse"] < target:
                break

    # Finalize: write best params and perform one clean verification run.
    best_params = (best["params"] if best else {}) or {}
    final_text = glm_lib.apply_params(base_text, best_params) if best_params else base_text
    glm_lib.write_text(cfg["nml"], final_text)
    final = _run_and_score(cfg, final_text, {})
    final_status = "ok" if (final["returncode"] == 0 and final["ok"]) else "failed"

    result = {
        "baseline_rmse": baseline.get("rmse"),
        "best_params": best_params,
        "final_rmse": final.get("rmse"),
        "final_status": final_status,
        "final_returncode": final["returncode"],
        "target_rmse": target,
        "passed": bool(final.get("rmse") is not None and final["rmse"] < target
                       and final_status == "ok"),
        "output_nc": cfg["output_nc"],
        "nml": cfg["nml"],
        "history": history,
        "final_stderr_tail": final.get("stderr_tail", ""),
    }
    json.dump(result, sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
