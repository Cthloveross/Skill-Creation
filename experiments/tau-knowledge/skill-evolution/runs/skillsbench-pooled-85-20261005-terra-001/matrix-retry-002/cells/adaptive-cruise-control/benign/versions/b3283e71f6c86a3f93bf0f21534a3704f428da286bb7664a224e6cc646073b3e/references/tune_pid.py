#!/usr/bin/env python3
"""Deterministically tune bounded PID gains from the supplied sensor trace."""
import argparse, csv, math, sys, yaml
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from simulation import load_rows, config_with_gains, simulate_rows

def score(trace, set_speed):
    commands = [r["acceleration_cmd"] for r in trace]
    cruise = [r for r in trace if r["mode"] == "cruise"]
    follow = [r for r in trace if r["mode"] in ("follow", "emergency")]
    speed_error = sum((r["ego_speed"] - set_speed) ** 2 for r in cruise) / max(1, len(cruise))
    gap_error = sum(r["distance_error"] ** 2 for r in follow) / max(1, len(follow))
    roughness = sum((commands[i] - commands[i-1]) ** 2 for i in range(1, len(commands))) / max(1, len(commands)-1)
    unsafe = sum((5.0-r["distance"]) ** 2 for r in follow if r["distance"] < 5.0)
    return speed_error + 0.30 * gap_error + 0.02 * roughness + 1000.0 * unsafe

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sensor", required=True); ap.add_argument("--config", required=True); ap.add_argument("--output", required=True)
    a = ap.parse_args()
    base = yaml.safe_load(Path(a.config).read_text()) or {}
    rows = load_rows(a.sensor)
    speed_candidates = [(p,i,d) for p in (.5,.7,.9,1.1,1.4) for i in (.02,.05,.10) for d in (0.0,.05,.12)]
    distance_candidates = [(p,i,d) for p in (.15,.25,.35,.50,.70) for i in (0.0,.01,.03) for d in (.08,.18,.35)]
    fixed_distance = {"kp": .35, "ki": .01, "kd": .18}
    best_speed = min(speed_candidates, key=lambda x: score(simulate_rows(rows, config_with_gains(base, {"pid_speed": dict(zip(("kp","ki","kd"),x)), "pid_distance": fixed_distance})), float(base.get("acc_settings",{}).get("set_speed",30))))
    speed = dict(zip(("kp","ki","kd"), best_speed))
    best_distance = min(distance_candidates, key=lambda x: score(simulate_rows(rows, config_with_gains(base, {"pid_speed": speed, "pid_distance": dict(zip(("kp","ki","kd"),x))})), float(base.get("acc_settings",{}).get("set_speed",30))))
    result = {"pid_speed": speed, "pid_distance": dict(zip(("kp","ki","kd"), best_distance))}
    Path(a.output).write_text(yaml.safe_dump(result, sort_keys=False), encoding="utf-8")
    print(yaml.safe_dump(result, sort_keys=False), end="")
if __name__ == "__main__": main()
