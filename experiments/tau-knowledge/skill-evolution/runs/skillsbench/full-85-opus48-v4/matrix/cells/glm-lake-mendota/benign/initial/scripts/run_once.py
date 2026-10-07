#!/usr/bin/env python3
"""Configure the namelist with an explicit parameter set, run one clean GLM
simulation, and report run status + temperature RMSE.

stdin JSON (all optional except where defaults are task specific):
  nml, glm_bin, obs_csv, start, stop, out_dir, out_fn, nsave,
  set_params: {name: value, ...}  # only existing namelist keys are changed

stdout JSON: {ok, rmse, n, out_nc, skipped, run:{returncode,stdout,stderr}}
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import glm_lib as G  # noqa: E402


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
    set_params = cfg.get("set_params", {})

    workdir = os.path.dirname(os.path.abspath(nml))
    out_abs_dir = out_dir if os.path.isabs(out_dir) else os.path.join(workdir, out_dir)
    out_nc = os.path.join(out_abs_dir, out_fn + ".nc")

    text = G.read_text(nml)
    text = G.configure_run(text, start, stop, out_dir, out_fn, nsave=nsave)
    text, skipped = G.apply_params(text, set_params)
    G.write_text(nml, text)

    G.clean_dir(out_abs_dir)
    run = G.run_glm(nml, glm_bin)
    result = {"out_nc": out_nc, "skipped": skipped, "run": run}
    if run["returncode"] != 0 or not os.path.exists(out_nc):
        result.update({"ok": False, "rmse": None, "n": 0})
        print(json.dumps(result))
        return
    obs = G.load_obs(obs_csv)
    rmse, n = G.compute_rmse(out_nc, obs)
    result.update({"ok": True, "rmse": rmse, "n": n})
    print(json.dumps(result))


if __name__ == "__main__":
    main()
