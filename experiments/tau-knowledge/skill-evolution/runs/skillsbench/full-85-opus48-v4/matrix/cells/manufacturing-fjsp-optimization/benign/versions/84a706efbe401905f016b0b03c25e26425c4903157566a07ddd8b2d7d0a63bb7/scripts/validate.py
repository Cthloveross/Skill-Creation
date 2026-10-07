#!/usr/bin/env python3
"""Validate already-written solution.json + schedule.csv against inputs.

Stdin (optional): {"data_dir":str,"output_dir":str,...same path keys as run_repair}.
Stdout: JSON {ok, problems, downtime_violations, makespan, csv_matches_json,
              key_set_ok, machine_changes, total_start_shift}.
This checks the actual files on disk; run_repair.py already validates what it
writes, but this lets you re-verify independently.
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
    sol_path = cfg.get("solution", os.path.join(out_dir, "solution.json"))
    csv_path = cfg.get("schedule_csv", os.path.join(out_dir, "schedule.csv"))

    out = {"ok": False}
    try:
        with open(p_instance) as fh:
            elig, _J, _M, _opj = F.parse_instance(fh.read())
        baseline_rows = F.load_baseline(read_json(p_baseline))
        with open(p_downtime) as fh:
            downtime = F.parse_downtime(fh.read())
        try:
            policy = F.parse_policy(read_json(p_policy))
        except (OSError, ValueError):
            policy = F.parse_policy({})

        sol = read_json(sol_path)
        rows = [
            {"job": int(r["job"]), "op": int(r["op"]), "machine": int(r["machine"]),
             "start": int(r["start"]), "end": int(r["end"]), "dur": int(r["dur"])}
            for r in sol["schedule"]
        ]

        csv_rows = []
        with open(csv_path, newline="") as fh:
            for r in csv.DictReader(fh):
                csv_rows.append((int(r["job"]), int(r["op"]), int(r["machine"]),
                                 int(r["start"]), int(r["end"]), int(r["dur"])))
        json_tuples = set((r["job"], r["op"], r["machine"], r["start"], r["end"], r["dur"])
                          for r in rows)
        csv_matches = set(csv_rows) == json_tuples

        problems = F.validate_schedule(rows, elig, baseline_rows, downtime, policy)
        dv = F.count_downtime_violations(rows, downtime)
        key_set_ok = set((r["job"], r["op"]) for r in rows) == set(
            (b["job"], b["op"]) for b in baseline_rows)
        reported = sol.get("makespan")
        computed = max((r["end"] for r in rows), default=0)
        makespan_ok = reported == computed

        base_by_key = {(b["job"], b["op"]): b for b in baseline_rows}
        mc = sum(1 for r in rows
                 if (r["job"], r["op"]) in base_by_key
                 and r["machine"] != base_by_key[(r["job"], r["op"])]["machine"])
        shift = sum(abs(r["start"] - base_by_key[(r["job"], r["op"])]["start"])
                    for r in rows if (r["job"], r["op"]) in base_by_key)

        out.update({
            "ok": (not problems and dv == 0 and csv_matches and key_set_ok
                   and makespan_ok),
            "problems": problems,
            "downtime_violations": dv,
            "makespan": computed,
            "reported_makespan": reported,
            "makespan_ok": makespan_ok,
            "csv_matches_json": csv_matches,
            "key_set_ok": key_set_ok,
            "machine_changes": mc,
            "total_start_shift": shift,
        })
    except Exception as exc:  # noqa: BLE001
        out["error"] = "%s: %s" % (type(exc).__name__, exc)

    print(json.dumps(out, indent=2))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
