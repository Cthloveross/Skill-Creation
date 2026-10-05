#!/usr/bin/env python3
"""Materialize and optionally execute the ACC project.
stdin:  {config_path, sensor_path, output_dir, run?}
stdout: {ok, paths, metrics?}, or {ok:false, error}
"""
import csv
import json
import shutil
import subprocess
import sys
from pathlib import Path


def make_report(results_path, tuning_path, report_path):
    with results_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError("simulation produced no rows")

    def number(row, key):
        return float(row[key])

    cruise = [row for row in rows if row["mode"] == "cruise"]
    lead_rows = [row for row in rows if row["mode"] in ("follow", "emergency") and row["distance"]]
    set_speed = 30.0
    first_time = number(rows[0], "time")
    rise = next((number(row, "time") - first_time for row in cruise if number(row, "ego_speed") >= 0.9 * set_speed), None)
    overshoot = max(0.0, (max((number(row, "ego_speed") for row in cruise), default=0.0) - set_speed) / set_speed * 100.0)
    tail_cruise = cruise[-100:]
    speed_sse = (sum(abs(set_speed - number(row, "ego_speed")) for row in tail_cruise) / len(tail_cruise)) if tail_cruise else None
    tail_lead = lead_rows[-100:]
    distance_sse = (sum(abs(float(row["distance_error"])) for row in tail_lead) / len(tail_lead)) if tail_lead else None
    min_distance = min((float(row["distance"]) for row in lead_rows), default=None)

    def display(value, suffix=""):
        return "not evaluable" if value is None else f"{value:.3f}{suffix}"

    gains = tuning_path.read_text(encoding="utf-8").strip()
    report_path.write_text(f"""# ACC Simulation Report

## System design and operating modes

The system design uses separate discrete PID controllers for speed and distance regulation. **Cruise** mode controls set speed when no lead is observed. **Follow** mode regulates the time-headway safe gap when a lead is observed. **Emergency** mode overrides both PID controllers whenever closing time-to-collision is below the configured threshold.

## Safety features

Safety features include TTC-priority emergency braking, physical acceleration saturation, non-negative simulated speed, a minimum standstill gap, blank lead-only fields when no lead is detected, and PID state reset on each mode transition. The safe-gap error is time headway times simulated ego speed plus the minimum gap, minus measured distance.

## PID tuning methodology and final gains

A separate tuning step selects conservative speed and distance gains for the acceleration-limited plant. The simulator does not tune gains: it loads the final gains from YAML at runtime. Final gains used for this result are:

```yaml
{gains}
```

## Simulation results and performance metrics

The delivered simulation result contains {len(rows)} timestamp-aligned samples. Rise time and overshoot use cruise samples. Steady-state errors use the final 100 applicable samples. A metric marked not evaluable has no applicable samples and is not a pass claim.

| Metric | Value | Target |
|---|---:|---:|
| Speed 90% rise time | {display(rise, ' s')} | < 10 s |
| Cruise speed overshoot | {display(overshoot, ' %')} | < 5 % |
| Cruise speed steady-state error | {display(speed_sse, ' m/s')} | < 0.5 m/s |
| Distance steady-state absolute error | {display(distance_sse, ' m')} | < 2 m |
| Minimum observed lead distance | {display(min_distance, ' m')} | > 5 m |
| Control duration | {number(rows[-1], 'time') - first_time:.3f} s | 150 s |
""", encoding="utf-8")
    return {"rise_time_s": rise, "speed_overshoot_pct": overshoot,
            "speed_steady_state_error_mps": speed_sse,
            "distance_steady_state_error_m": distance_sse,
            "minimum_distance_m": min_distance, "rows": len(rows)}


def main():
    try:
        request = json.load(sys.stdin)
        config = Path(request.get("config_path", "/root/vehicle_params.yaml")).resolve()
        sensor = Path(request.get("sensor_path", "/root/sensor_data.csv")).resolve()
        output_dir = Path(request.get("output_dir", "/root")).resolve()
        if not config.is_file() or not sensor.is_file():
            raise FileNotFoundError("config_path and sensor_path must name existing files")
        output_dir.mkdir(parents=True, exist_ok=True)
        references = Path(__file__).resolve().parent.parent / "references"
        sources = ("pid_controller.py", "acc_system.py", "simulation.py", "tune_acc.py")
        for name in sources:
            shutil.copyfile(references / name, output_dir / name)
        paths = {name: str(output_dir / name) for name in sources}
        paths.update({"tuning_results.yaml": str(output_dir / "tuning_results.yaml"),
                      "simulation_results.csv": str(output_dir / "simulation_results.csv"),
                      "acc_report.md": str(output_dir / "acc_report.md")})
        response = {"ok": True, "paths": paths}
        if request.get("run", True):
            subprocess.run([sys.executable, "tune_acc.py", "--config", str(config), "--sensor", str(sensor), "--output", paths["tuning_results.yaml"]], cwd=output_dir, check=True)
            subprocess.run([sys.executable, "simulation.py", "--config", str(config), "--sensor", str(sensor), "--tuning", paths["tuning_results.yaml"], "--output", paths["simulation_results.csv"]], cwd=output_dir, check=True)
            response["metrics"] = make_report(Path(paths["simulation_results.csv"]), Path(paths["tuning_results.yaml"]), Path(paths["acc_report.md"]))
        print(json.dumps(response, allow_nan=False))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
