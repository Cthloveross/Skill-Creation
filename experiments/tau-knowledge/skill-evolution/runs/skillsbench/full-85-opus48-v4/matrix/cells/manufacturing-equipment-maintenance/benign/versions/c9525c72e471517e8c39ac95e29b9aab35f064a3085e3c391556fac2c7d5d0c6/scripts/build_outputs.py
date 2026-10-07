#!/usr/bin/env python3
"""Assemble /app/output/q01.json .. q05.json from handbook-derived parameters.

All policy values come from the config (which the executor fills in after
reading the handbook). This script only applies deterministic selection, sort,
and rounding rules. Review each produced file against the handbook before
submitting.

stdin config (fields are optional; a question is skipped if its block is absent):
{
  "out_dir": "/app/output",
  "thermo_csv": "/app/data/thermocouples.csv",
  "thermo_columns": {...optional overrides...},
  "all_run_ids": [...],          # authoritative run universe (e.g. from mes_log)
  "run_family": {run_id: board_family},

  "q1": {"preheat": {"temp_low":..,"temp_high":..,"boundary":"both_in_band"},
          "ramp_limit": 3.0,
          "representative": "max_metric"},   # max_metric|min_metric|specific
  "q1_specific_tc": "TC1",

  "q2": {"liquidus": 217, "tal_inclusive": true,
          "min_tal": 45, "max_tal": 90,
          "representative": "max_metric"},

  "q3": {"required_min_peak": 235.0,
          "representative": "min_metric"},    # coldest sensor = worst case

  "q4": {"required_min_speed_cm_min": 30.0,     # OR give derivation below
          "heated_length_cm": 100.0, "max_dwell_s": 200.0,
          "max_speed_cm_min": null,
          "mes_csv": "/app/data/mes_log.csv",
          "columns": {"run_id":..,"speed":..,"distance":..,"time":..},
          "speed_in": "cm_min"},                # cm_min|cm_s|mm_s|m_min

  "q5": {"priority": [{"metric":"yield","dir":"desc"},
                       {"metric":"speed","dir":"desc"}],
          "defects_csv": "/app/data/test_defects.csv",
          "defect_columns": {"run_id":..,"defects":..,"total":..}}
}
"""
import json
import os
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from helpers import (  # noqa: E402
    read_csv,
    detect_thermo_columns,
    group_traces,
    max_preheat_ramp,
    time_above,
    peak_temp,
    to_float,
    guess_col,
    rnd,
    sort_run_ids,
)


def pick_rep(by_tc, key, mode, specific=None):
    """Choose (tc_id, value) from {tc: value} by representative rule."""
    items = [(tc, v) for tc, v in by_tc.items() if v is not None]
    if not items:
        return None, None
    if mode == "specific" and specific in by_tc:
        return specific, by_tc[specific]
    if mode == "min_metric":
        return min(items, key=lambda kv: kv[1])
    # default max_metric
    return max(items, key=lambda kv: kv[1])


def load_metrics(cfg):
    header, rows = read_csv(cfg["thermo_csv"])
    cols = detect_thermo_columns(header, cfg.get("thermo_columns"))
    traces = group_traces(rows, cols)
    return traces


def conv_speed(val, unit):
    if val is None:
        return None
    return {
        "cm_min": val,
        "cm_s": val * 60.0,
        "mm_s": val * 6.0,
        "m_min": val * 100.0,
    }.get(unit, val)


def build_q1(cfg, traces, run_ids):
    q = cfg["q1"]
    ph = q.get("preheat", {})
    low, high = ph.get("temp_low"), ph.get("temp_high")
    boundary = ph.get("boundary", "both_in_band")
    limit = q.get("ramp_limit")
    mode = q.get("representative", "max_metric")
    specific = cfg.get("q1_specific_tc")
    by_run = {}
    violating = []
    for run in run_ids:
        tcs = traces.get(run, {})
        ramps = {tc: max_preheat_ramp(s, low, high, boundary) for tc, s in tcs.items()}
        tc_id, val = pick_rep(ramps, "ramp", mode, specific)
        by_run[run] = {"tc_id": tc_id, "max_preheat_ramp_c_per_s": rnd(val)}
        if val is not None and limit is not None and val > limit:
            violating.append(run)
    return {
        "ramp_rate_limit_c_per_s": limit,
        "violating_runs": sort_run_ids(violating),
        "max_ramp_by_run": {r: by_run[r] for r in sort_run_ids(by_run)},
    }


def build_q2(cfg, traces, run_ids):
    q = cfg["q2"]
    liq = q.get("liquidus")
    inc = q.get("tal_inclusive", True)
    mn, mx = q.get("min_tal"), q.get("max_tal")
    mode = q.get("representative", "max_metric")
    specific = cfg.get("q2_specific_tc")
    out = []
    for run in run_ids:
        tcs = traces.get(run, {})
        tals = {tc: time_above(s, liq, inc) for tc, s in tcs.items()} if liq is not None else {}
        tc_id, val = pick_rep(tals, "tal", mode, specific)
        status = None
        if val is not None:
            ok = True
            if mn is not None:
                ok = ok and val >= mn
            if mx is not None:
                ok = ok and val <= mx
            status = "compliant" if ok else "non-compliant"
        else:
            status = "non-compliant"
        out.append({
            "run_id": run,
            "tc_id": tc_id,
            "tal_s": rnd(val),
            "required_min_tal_s": mn,
            "required_max_tal_s": mx,
            "status": status,
        })
    out.sort(key=lambda d: str(d["run_id"]))
    return out


def build_q3(cfg, traces, run_ids):
    q = cfg["q3"]
    req = q.get("required_min_peak")
    mode = q.get("representative", "min_metric")
    specific = cfg.get("q3_specific_tc")
    by_run = {}
    failing = []
    for run in run_ids:
        tcs = traces.get(run, {})
        peaks = {tc: peak_temp(s) for tc, s in tcs.items()}
        tc_id, val = pick_rep(peaks, "peak", mode, specific)
        by_run[run] = {
            "tc_id": tc_id,
            "peak_temp_c": rnd(val),
            "required_min_peak_c": req,
        }
        if val is None or (req is not None and val < req):
            failing.append(run)
    return {
        "failing_runs": sort_run_ids(failing),
        "min_peak_by_run": {r: by_run[r] for r in sort_run_ids(by_run)},
    }


def build_q4(cfg, run_ids):
    q = cfg["q4"]
    req_min = q.get("required_min_speed_cm_min")
    if req_min is None and q.get("heated_length_cm") and q.get("max_dwell_s"):
        # min speed (cm/min) that still keeps part <= max dwell in heated zone
        req_min = q["heated_length_cm"] / q["max_dwell_s"] * 60.0
    req_max = q.get("max_speed_cm_min")
    if req_max is None and q.get("heated_length_cm") and q.get("min_dwell_s"):
        req_max = q["heated_length_cm"] / q["min_dwell_s"] * 60.0
    header, rows = read_csv(q["mes_csv"])
    cmap = q.get("columns", {})
    rcol = cmap.get("run_id") or guess_col(header, "run")
    scol = cmap.get("speed") or guess_col(header, "speed", "conveyor")
    dcol = cmap.get("distance") or guess_col(header, "distance", "length")
    tcol = cmap.get("time") or guess_col(header, "time", "duration")
    unit = q.get("speed_in", "cm_min")
    actual = {}
    for r in rows:
        run = r.get(rcol)
        if run is None:
            continue
        sp = to_float(r.get(scol)) if scol else None
        if sp is None and dcol and tcol:
            d = to_float(r.get(dcol))
            t = to_float(r.get(tcol))
            if d is not None and t:
                sp = (d / t) * 60.0  # assume cm & s -> cm/min; adjust unit below
                unit = "cm_min"
        actual[run] = conv_speed(sp, unit)
    out = []
    for run in run_ids:
        a = actual.get(run)
        meets = None
        if a is not None:
            meets = True
            if req_min is not None:
                meets = meets and a >= req_min
            if req_max is not None:
                meets = meets and a <= req_max
        out.append({
            "run_id": run,
            "required_min_speed_cm_min": rnd(req_min),
            "actual_speed_cm_min": rnd(a),
            "meets": meets,
        })
    out.sort(key=lambda d: str(d["run_id"]))
    return out


def build_q5(cfg, run_ids, run_family):
    q = cfg["q5"]
    priority = q.get("priority", [])
    # gather per-run metrics table
    metrics = {run: {} for run in run_ids}
    dc = q.get("defects_csv")
    if dc:
        header, rows = read_csv(dc)
        dcols = q.get("defect_columns", {})
        rcol = dcols.get("run_id") or guess_col(header, "run")
        defcol = dcols.get("defects") or guess_col(header, "defect", "fail")
        totcol = dcols.get("total") or guess_col(header, "total", "inspected", "qty", "count")
        agg = {}
        for r in rows:
            run = r.get(rcol)
            if run is None:
                continue
            d = to_float(r.get(defcol)) or 0.0
            t = to_float(r.get(totcol)) if totcol else None
            a = agg.setdefault(run, {"def": 0.0, "tot": 0.0, "rows": 0})
            a["def"] += d
            if t is not None:
                a["tot"] += t
            a["rows"] += 1
        for run, a in agg.items():
            if run not in metrics:
                metrics[run] = {}
            metrics[run]["defects"] = a["def"]
            if a["tot"] > 0:
                metrics[run]["yield"] = 1.0 - a["def"] / a["tot"]
    # merge any externally supplied metrics (speed, tal, peak compliance...)
    for run, extra in (q.get("extra_metrics") or {}).items():
        metrics.setdefault(run, {}).update(extra)

    def sort_key(run):
        k = []
        for p in priority:
            v = metrics.get(run, {}).get(p["metric"])
            if v is None:
                v = float("-inf") if p["dir"] == "desc" else float("inf")
            k.append(-v if p["dir"] == "desc" else v)
        k.append(str(run))  # deterministic tie-break
        return tuple(k)

    fams = {}
    for run in run_ids:
        fam = run_family.get(run)
        fams.setdefault(fam, []).append(run)
    out = []
    for fam in sorted(fams, key=lambda x: str(x)):
        runs = sorted(fams[fam], key=sort_key)
        best = runs[0] if runs else None
        out.append({
            "board_family": fam,
            "best_run_id": best,
            "runner_up_run_ids": sort_run_ids([r for r in runs if r != best]),
        })
    return out


def main():
    cfg = json.load(sys.stdin)
    out_dir = cfg.get("out_dir", "/app/output")
    os.makedirs(out_dir, exist_ok=True)
    traces = load_metrics(cfg) if cfg.get("thermo_csv") else {}
    run_ids = cfg.get("all_run_ids") or sort_run_ids(list(traces.keys()))
    run_ids = sort_run_ids(run_ids)
    run_family = cfg.get("run_family", {})
    written = []
    if "q1" in cfg:
        with open(os.path.join(out_dir, "q01.json"), "w") as f:
            json.dump(build_q1(cfg, traces, run_ids), f, indent=2)
        written.append("q01.json")
    if "q2" in cfg:
        with open(os.path.join(out_dir, "q02.json"), "w") as f:
            json.dump(build_q2(cfg, traces, run_ids), f, indent=2)
        written.append("q02.json")
    if "q3" in cfg:
        with open(os.path.join(out_dir, "q03.json"), "w") as f:
            json.dump(build_q3(cfg, traces, run_ids), f, indent=2)
        written.append("q03.json")
    if "q4" in cfg:
        with open(os.path.join(out_dir, "q04.json"), "w") as f:
            json.dump(build_q4(cfg, run_ids), f, indent=2)
        written.append("q04.json")
    if "q5" in cfg:
        with open(os.path.join(out_dir, "q05.json"), "w") as f:
            json.dump(build_q5(cfg, run_ids, run_family), f, indent=2)
        written.append("q05.json")
    print(json.dumps({"out_dir": out_dir, "written": written,
                      "n_runs": len(run_ids)}))


if __name__ == "__main__":
    main()
