---
name: adaptive-cruise-control-simulation
description: Materialize, tune, run, and validate a Python Adaptive Cruise Control (ACC) simulation from a sensor CSV and nested vehicle-parameter YAML. Use when required deliverables include PID and ACC source files, runtime-loaded tuning gains, an aligned simulation CSV, and a measured Markdown report.
---

## Purpose

This Skill creates a self-contained ACC project in the requested directory. `tune_pid.py` writes `tuning_results.yaml`; `simulation.py` subsequently loads that file at runtime. The simulator derives ego speed only by Euler-integrating its own acceleration commands. Sensor lead speed and distance are external observations used for mode selection and reporting.

The control priority is:

1. `emergency` if a valid lead is present, ego is closing, and TTC is below the configured threshold;
2. `follow` if a valid lead is present;
3. `cruise` otherwise.

The generated results record state before integrating the row's command. Thus the first row contains initial speed and its first command, while the following row contains the speed resulting from the preceding command. This is consistent with the required Euler dynamics check.

## Runtime inputs

- A sensor CSV containing `time`, `ego_speed`, `lead_speed`, and `distance`. Blank `lead_speed` and `distance` together mean no lead detection.
- A vehicle YAML configuration, normally containing nested `acc_settings` and `vehicle` mappings.
- Python 3 and PyYAML.

For the supplied task, inputs are normally `/root/sensor_data.csv` and `/root/vehicle_params.yaml`.

## Materialize and run

Run the materializer with JSON on stdin:

```json
{"output_dir":"/root"}
```

It emits `{"written":[...]}` and writes these project sources:

- `pid_controller.py`
- `acc_system.py`
- `tune_pid.py`
- `simulation.py`

Then run the generated programs in this order:

```text
python /root/tune_pid.py --sensor /root/sensor_data.csv --config /root/vehicle_params.yaml --output /root/tuning_results.yaml
python /root/simulation.py --sensor /root/sensor_data.csv --config /root/vehicle_params.yaml --tuning /root/tuning_results.yaml --output /root/simulation_results.csv --report /root/acc_report.md
```

`tune_pid.py` evaluates a small deterministic set of bounded gains using the supplied trace. Its speed candidates use no integral action because the specified longitudinal model has no drag term; this avoids saturation windup and cruise overshoot while retaining a fast, bounded response. All emitted gains meet the stated ranges. Tuning logic is separate from `simulation.py`; the latter only loads its gain file.

The PID implementation follows the public discrete update exactly: integral is incremented by `error * dt`, derivative is `(error - previous_error) / dt`, and reset initializes previous error to zero. ACC-selected operating gains avoid derivative kick in the speed loop while preserving the general PID interface.

## Output semantics and limitations

`simulation.py` rejects an empty trace, missing required columns, nonfinite values, incomplete lead observations, negative observed gaps, and non-increasing timestamps. It preserves each input timestamp and writes exactly one output row per input row.

- Cruise rows leave `distance_error`, `distance`, and `ttc` blank.
- Lead rows report the supplied observed distance and `distance_error = headway * ego_speed + minimum_gap - distance`.
- TTC is blank unless ego speed exceeds lead speed. When defined it is computed from the same row state values reported to the CSV, with high-precision numeric rendering.
- Emergency commands are the configured maximum braking command.

A reported gap is an external sensor observation, not a state controlled by this simulator. If supplied lead observations themselves include a gap at or below a safety target, no compliant output can both reproduce that observation and claim the observed target was met. The report therefore measures and states the observed minimum rather than fabricating a safe gap.

## Validate artifacts

Use the packaged validator after running the pipeline. Its JSON stdin schema is:

```json
{
  "results_csv":"/root/simulation_results.csv",
  "tuning_yaml":"/root/tuning_results.yaml",
  "required_rows":1501
}
```

It writes JSON with `valid`, `errors`, `rows`, and `modes`. It checks exact CSV column order, row count, finite state values, ordered time, legal modes, lead-field blank semantics, physical command/speed bounds, and gain ranges. A validation failure requires correcting the input or generated project and rerunning the documented pipeline; do not invent result rows or performance claims.
