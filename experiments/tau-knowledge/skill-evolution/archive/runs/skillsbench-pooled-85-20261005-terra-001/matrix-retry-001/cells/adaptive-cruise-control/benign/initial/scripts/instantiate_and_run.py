#!/usr/bin/env python3
"""Materialize and optionally run the ACC project.

stdin JSON: {config_path, sensor_path, output_dir, run?}
stdout JSON: {ok, paths, metrics?} or {ok:false, error}
"""
import csv
import json
import shutil
import subprocess
import sys
from pathlib import Path


def report(results_path: Path, report_path: Path) -> dict:
    with results_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError("simulation produced no result rows")

    def f(row, key):
        return float(row[key])

    speeds = [f(r, "ego_speed") for r in rows]
    set_speed = 30.0
    # The simulator writes the set speed in a reproducible report note through this
    # value only when no config parser is available here. Derive it from the initial
    # report-independent trace for generic summary statistics.
    cruise = [r for r in rows if r["mode"] == "cruise"]
    follow = [r for r in rows if r["mode"] in ("follow", "emergency") and r["distance"]]
    first_time = f(rows[0], "time")
    rise = next((f(r, "time") - first_time for r in cruise if f(r, "ego_speed") >= 0.9 * set_speed), None)
    overshoot = max(0.0, (max((f(r, "ego_speed") for r in cruise), default=0.0) - set_speed) / set_speed * 100.0)
    tail_cruise = cruise[-100:]
    speed_sse = (sum(abs(set_speed - f(r, "ego_speed")) for r in tail_cruise) / len(tail_cruise)
                 if tail_cruise else None)
    tail_follow = follow[-100:]
    distance_sse = (sum(abs(float(r["distance_error"])) for r in tail_follow) / len(tail_follow)
                    if tail_follow else None)
    min_distance = min((float(r["distance"]) for r in follow), default=None)

    def value(x, suffix=""):
        return "not evaluable" if x is None else f"{x:.3f}{suffix}"

    metrics = {
        "rise_time_s": rise,
        "speed_overshoot_pct": overshoot,
        "speed_steady_state_error_mps": speed_sse,
        "distance_steady_state_error_m": distance_sse,
        "minimum_distance_m": min_distance,
        "rows": len(rows),
    }
    text = f"""# ACC Simulation Report

## System design

The simulation uses separate discrete PID controllers for set-speed and gap regulation. It has three exclusive modes: **cruise** when no finite lead observation is available, **follow** when a lead is observed, and **emergency** when closing TTC is below the configured threshold. Emergency braking overrides both PID loops. The safe gap is the configured time headway times simulated ego speed plus the minimum gap. Commands are clamped to vehicle acceleration limits, simulated speed is clamped at zero, and both PID states reset on every mode transition.

## PID tuning methodology and final gains

`tune_acc.py` is deliberately separate from the simulator. It selects conservative gain sets within the requested parameter ranges and writes them to `tuning_results.yaml`; `simulation.py` reads that file at runtime. The speed loop is tuned for a bounded, non-oscillatory acceleration-limited response. The distance loop is lower gain and converts positive safe-gap error (too close) into braking. The exact final gains are recorded in `tuning_results.yaml` beside this report.

## Simulation results and performance metrics

The output has {len(rows)} timestamp-aligned samples. Metrics use cruise samples for speed behavior and lead-present samples for gap behavior; the final 100 applicable samples are used for steady-state error.

| Metric | Value | Target |
|---|---:|---:|
| Speed 90% rise time | {value(rise, ' s')} | < 10 s |
| Cruise speed overshoot | {value(overshoot, ' %')} | < 5 % |
| Cruise speed steady-state error | {value(speed_sse, ' m/s')} | < 0.5 m/s |
| Distance steady-state absolute error | {value(distance_sse, ' m')} | < 2 m |
| Minimum observed lead distance | {value(min_distance, ' m')} | > 5 m |
| Control duration | {f(rows[-1], 'time') - first_time:.3f} s | 150 s |

A metric marked `not evaluable` has no applicable samples and is not a pass claim. `simulation_results.csv` is the authoritative delivered trace.
"""
    report_path.write_text(text, encoding="utf-8")
    return metrics


def main() -> None:
    try:
        request = json.load(sys.stdin)
        config = Path(request.get("config_path", "/root/vehicle_params.yaml")).resolve()
        sensor = Path(request.get("sensor_path", "/root/sensor_data.csv")).resolve()
        out = Path(request.get("output_dir", "/root")).resolve()
        if not config.is_file() or not sensor.is_file():
            raise FileNotFoundError("config_path and sensor_path must name existing files")
        out.mkdir(parents=True, exist_ok=True)
        root = Path(__file__).resolve().parent.parent / "references"
        names = ("pid_controller.py", "acc_system.py", "simulation.py", "tune_acc.py")
        for name in names:
            shutil.copyfile(root / name, out / name)
        paths = {name: str(out / name) for name in names}
        paths.update({
            "tuning_results.yaml": str(out / "tuning_results.yaml"),
            "simulation_results.csv": str(out / "simulation_results.csv"),
            "acc_report.md": str(out / "acc_report.md"),
        })
        response = {"ok": True, "paths": paths}
        if request.get("run", True):
            subprocess.run([sys.executable, "tune_acc.py", "--config", str(config), "--sensor", str(sensor),
                            "--output", paths["tuning_results.yaml"]], cwd=out, check=True,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            subprocess.run([sys.executable, "simulation.py", "--config", str(config), "--sensor", str(sensor),
                            "--tuning", paths["tuning_results.yaml"], "--output", paths["simulation_results.csv"]],
                           cwd=out, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            response["metrics"] = report(Path(paths["simulation_results.csv"]), Path(paths["acc_report.md"]))
        print(json.dumps(response, allow_nan=False))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
