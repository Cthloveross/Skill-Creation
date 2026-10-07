#!/usr/bin/env python3
"""End-to-end FJSP baseline repair entrypoint.

Reads optional JSON config on stdin, writes solution.json + schedule.csv, and
prints a JSON report on stdout.

Stdin (all optional):
  {"data_dir":str,"output_dir":str,"instance":str,"baseline":str,
   "downtime":str,"policy":str,"baseline_metrics":str,"status":str}
Defaults: data_dir=/app/data, output_dir=/app/output.
"""
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fjsp_lib as F  # noqa: E402


def read_json(path):
    with open(path) as fh:
        return json.load(fh)


def main():
    raw = sys.stdin.read()
    cfg = json.loads(raw) if raw.strip() else {}
    data_dir = cfg.get("data_dir", "/app/data")
    out_dir = cfg.get("output_dir", "/app/output")
    p_instance = cfg.get("instance", os.path.join(data_dir, "instance.txt"))
    p_baseline = cfg.get("baseline", os.path.join(data_dir, "baseline_solution.json"))
    p_downtime = cfg.get("downtime", os.path.join(data_dir, "downtime.csv"))
    p_policy = cfg.get("policy", os.path.join(data_dir, "policy.json"))
    p_metrics = cfg.get("baseline_metrics", os.path.join(data_dir, "baseline_metrics.json"))
    status = cfg.get("status", "repaired")

    report = {"ok": False, "warnings": []}
    try:
        with open(p_instance) as fh:
            elig, J, M, ops_per_job = F.parse_instance(fh.read())
        baseline_rows = F.load_baseline(read_json(p_baseline))
        with open(p_downtime) as fh:
            downtime = F.parse_downtime(fh.read())
        try:
            policy = F.parse_policy(read_json(p_policy))
        except (OSError, ValueError):
            policy = F.parse_policy({})
            report["warnings"].append("policy.json unreadable; treated as empty")

        baseline_makespan = None
        try:
            bm = read_json(p_metrics)
            if isinstance(bm, dict):
                for k, v in bm.items():
                    if "makespan" in str(k).lower() and isinstance(v, (int, float)):
                        baseline_makespan = int(v)
                        break
        except (OSError, ValueError):
            pass
        if baseline_makespan is None and baseline_rows:
            baseline_makespan = max(r["end"] for r in baseline_rows)

        rows, info = F.repair(elig, baseline_rows, downtime, policy)
        report["warnings"].extend(info["warnings"])

        problems = F.validate_schedule(rows, elig, baseline_rows, downtime, policy)
        dv = F.count_downtime_violations(rows, downtime)
        makespan = info["makespan"]

        os.makedirs(out_dir, exist_ok=True)
        sol = {
            "status": status,
            "makespan": makespan,
            "schedule": [
                {"job": r["job"], "op": r["op"], "machine": r["machine"],
                 "start": r["start"], "end": r["end"], "dur": r["dur"]}
                for r in rows
            ],
        }
        sol_path = os.path.join(out_dir, "solution.json")
        csv_path = os.path.join(out_dir, "schedule.csv")
        with open(sol_path, "w") as fh:
            json.dump(sol, fh, indent=2)
        with open(csv_path, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["job", "op", "machine", "start", "end", "dur"])
            for r in sorted(rows, key=lambda x: (x["job"], x["op"])):
                w.writerow([r["job"], r["op"], r["machine"],
                            r["start"], r["end"], r["dur"]])

        max_mc = policy.get("max_machine_changes")
        max_shift = policy.get("max_total_start_shift")
        mc = info["machine_changes"]
        shift = info["total_start_shift"]
        mc_ok = (max_mc is None) or (mc <= max_mc)
        shift_ok = (max_shift is None) or (shift <= max_shift)
        if max_mc is None:
            report["warnings"].append("no machine-change budget found in policy")
        if max_shift is None:
            report["warnings"].append("no L1 start-shift budget found in policy")
        if baseline_makespan is not None and makespan > baseline_makespan:
            report["warnings"].append(
                "makespan %d exceeds baseline %d" % (makespan, baseline_makespan))

        report.update({
            "ok": (dv == 0 and not problems and mc_ok and shift_ok),
            "makespan": makespan,
            "baseline_makespan": baseline_makespan,
            "machine_changes": mc,
            "total_start_shift": shift,
            "downtime_violations": dv,
            "num_ops": len(rows),
            "budget": {
                "max_machine_changes": max_mc,
                "max_total_start_shift": max_shift,
                "machine_changes_ok": mc_ok,
                "shift_ok": shift_ok,
            },
            "freeze": {
                "threshold": policy.get("freeze_threshold"),
                "fields": policy.get("freeze_fields"),
            },
            "problems": problems,
            "solution_path": sol_path,
            "schedule_csv_path": csv_path,
        })
    except Exception as exc:  # noqa: BLE001
        report["error"] = "%s: %s" % (type(exc).__name__, exc)

    print(json.dumps(report, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
