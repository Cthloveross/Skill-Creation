#!/usr/bin/env python3
"""End-to-end GLM calibration entrypoint.

Configures the namelist to the requested span/output, runs a baseline
simulation, and if the temperature RMSE does not meet the target performs a
greedy one-parameter-at-a-time search over physically meaningful calibration
parameters that already exist in the namelist. The best configuration is
written back into the same glm3.nml and a final clean run verifies it.

stdin JSON (optional) overrides any default:
  nml, glm_bin, obs_csv, start, stop, out_dir, out_fn, nsave,
  target_rmse (default 2.0), calibrate (default true),
  candidates: [[name,[values...],is_string], ...]  # optional custom search

stdout JSON summary: baseline, calibration trace, final, verify, nml_params.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import glm_lib as G  # noqa: E402

# Physically meaningful calibration candidates (name, values, is_string).
# Only those present in the supplied namelist are used; current value is kept
# as the fallback for each group. Ranges are plausible bounds, not answers.
DEFAULT_CANDIDATES = [
    ("wind_factor", [0.9, 1.0, 1.1, 1.2], False),
    ("sw_factor", [0.9, 1.0, 1.1], False),
    ("lw_factor", [0.9, 1.0, 1.1], False),
    ("at_factor", [0.95, 1.0, 1.05], False),
    ("ce", [0.0012, 0.0013, 0.0014], False),
    ("ch", [0.0012, 0.0013, 0.0014], False),
    ("coef_mix_hyp", [0.5, 0.6, 0.7], False),
    ("coef_wind_stir", [0.23, 0.4, 0.6], False),
    ("Kw", [0.3, 0.4, 0.5], False),
]


def eval_text(nml, text, glm_bin, out_abs_dir, out_nc, obs):
    G.write_text(nml, text)
    G.clean_dir(out_abs_dir)
    run = G.run_glm(nml, glm_bin)
    if run["returncode"] != 0 or not os.path.exists(out_nc):
        return {"ok": False, "rmse": None, "n": 0, "run": run}
    rmse, n = G.compute_rmse(out_nc, obs)
    return {"ok": True, "rmse": rmse, "n": n, "run": run}


def main():
    raw = sys.stdin.read()
    cfg = json.loads(raw) if raw.strip() else {}
    nml = cfg.get("nml", "/root/glm3.nml")
    glm_bin = cfg.get("glm_bin", "/usr/local/bin/glm")
    obs_csv = cfg.get("obs_csv", "/root/field_temp_oxy.csv")
    start = cfg.get("start", "2009-01-01 00:00:00")
    stop = cfg.get("stop", "2015-12-30 00:00:00")
    out_dir = cfg.get("out_dir", "output")
    out_fn = cfg.get("out_fn", "output")
    nsave = cfg.get("nsave", 24)
    target = float(cfg.get("target_rmse", 2.0))
    do_cal = bool(cfg.get("calibrate", True))
    candidates = cfg.get("candidates") or DEFAULT_CANDIDATES

    workdir = os.path.dirname(os.path.abspath(nml))
    out_abs_dir = out_dir if os.path.isabs(out_dir) else os.path.join(workdir, out_dir)
    out_nc = os.path.join(out_abs_dir, out_fn + ".nc")

    obs = G.load_obs(obs_csv)

    base_text = G.read_text(nml)
    base_text = G.configure_run(base_text, start, stop, out_dir, out_fn, nsave=nsave)

    summary = {"n_obs": len(obs), "target_rmse": target, "trace": []}

    baseline = eval_text(nml, base_text, glm_bin, out_abs_dir, out_nc, obs)
    summary["baseline"] = {k: baseline[k] for k in ("ok", "rmse", "n")}
    if not baseline["ok"]:
        summary["baseline"]["stderr"] = baseline["run"]["stderr"]

    best_rmse = baseline["rmse"] if (baseline["ok"] and baseline["rmse"] is not None) else float("inf")
    best_text = base_text

    meets = baseline["ok"] and baseline["rmse"] is not None and baseline["rmse"] < target

    if do_cal and not meets:
        for name, values, is_str in candidates:
            if not G.param_exists(best_text, name):
                continue
            group_best_val = None
            for v in values:
                trial, changed = G.set_param(best_text, name, v, is_string=is_str)
                if not changed:
                    continue
                res = eval_text(nml, trial, glm_bin, out_abs_dir, out_nc, obs)
                rmse = res["rmse"] if res["ok"] else None
                summary["trace"].append(
                    {"param": name, "value": v, "ok": res["ok"], "rmse": rmse}
                )
                if res["ok"] and rmse is not None and rmse < best_rmse:
                    best_rmse = rmse
                    best_text = trial
                    group_best_val = v
            summary.setdefault("chosen", {})
            if group_best_val is not None:
                summary["chosen"][name] = group_best_val
            if best_rmse < target:
                break

    # Final clean run using the best configuration (writes best params to nml).
    final = eval_text(nml, best_text, glm_bin, out_abs_dir, out_nc, obs)
    verify = G.verify_output(out_nc)
    span_ok = False
    try:
        if verify.get("time_min") and verify.get("time_max"):
            span_ok = (
                verify["time_min"][:4] <= start[:4]
                and verify["time_max"][:4] >= stop[:4]
            )
    except Exception:  # noqa: BLE001
        span_ok = False
    verify["span_ok"] = span_ok

    summary["final"] = {
        "ok": final["ok"],
        "rmse": final["rmse"],
        "n": final["n"],
        "meets_target": bool(
            final["ok"] and final["rmse"] is not None and final["rmse"] < target
        ),
        "run": {
            "returncode": final["run"]["returncode"],
            "stderr": final["run"]["stderr"],
        },
    }
    summary["verify"] = verify
    summary["nml"] = nml
    summary["out_nc"] = out_nc
    summary["nml_params"] = {
        k: G.get_param(best_text, k)
        for k in ("start", "stop", "out_dir", "out_fn", "nsave", "timefmt")
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
