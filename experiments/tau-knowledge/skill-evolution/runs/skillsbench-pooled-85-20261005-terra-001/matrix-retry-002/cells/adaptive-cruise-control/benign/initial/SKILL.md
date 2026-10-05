---
name: adaptive-cruise-control-simulation
description: Create, tune, run, and validate a Python Adaptive Cruise Control (ACC) simulation from a sensor CSV and nested vehicle-parameter YAML. Use when deliverables must include PID and ACC source files, runtime-loaded tuning results, an aligned simulation CSV, and an evidence-based Markdown report.
---

## Purpose

This Skill materializes a self-contained ACC project into the requested working directory. It keeps tuning out of the simulator: `tune_pid.py` writes `tuning_results.yaml`, then `simulation.py` loads that file at runtime. The simulator derives ego speed from its own integrated acceleration commands; it uses sensor lead speed and distance only as external observations.

The implementation supports the requested cruise, follow, and emergency hierarchy:

1. `emergency` when a lead is present, the ego is closing, and TTC is below the configured threshold;
2. `follow` when a valid lead observation is present;
3. `cruise` otherwise.

The generated CSV reports state before integration at each sensor timestamp, matching the requested example (`t=0` has initial speed and the first command; `t=0.1` has the speed after the previous command). Lead-only fields are blank in cruise, and TTC is blank when the ego is not closing.

## Required runtime inputs

- Sensor CSV with `time`, `ego_speed`, `lead_speed`, and `distance` columns. Blank lead fields mean no detected lead.
- YAML vehicle configuration. Expected settings may be under `acc_settings` and/or `vehicle`; common aliases for the documented settings are accepted.
- Python 3 with PyYAML available.

The supplied task inputs are normally `/root/sensor_data.csv` and `/root/vehicle_params.yaml`.

## Produce the project and artifacts

Run the materializer from the Skill package. Its JSON stdin schema is:

```json
{"output_dir":"/root"}
```

It emits a JSON object listing written source paths. It writes:

- `pid_controller.py`
- `acc_system.py`
- `tune_pid.py`
- `simulation.py`

Then execute these generated programs in order (paths may be changed consistently if a different output directory was selected):

```text
python /root/tune_pid.py --sensor /root/sensor_data.csv --config /root/vehicle_params.yaml --output /root/tuning_results.yaml
python /root/simulation.py --sensor /root/sensor_data.csv --config /root/vehicle_params.yaml --tuning /root/tuning_results.yaml --output /root/simulation_results.csv --report /root/acc_report.md
```

`tune_pid.py` performs a deterministic bounded grid search using the supplied lead trace. It scores speed tracking, following-gap error, excessive acceleration changes, and unsafe observed gaps. Its output always has `pid_speed` and `pid_distance` mappings with gains inside the stated ranges. It does not modify the simulator or embed a tuning procedure in it.

`simulation.py` rejects malformed/nonmonotonic timestamps, missing required columns, or an empty trace. For the stated ACC task, input must contain 1501 sensor records, so the expected result has exactly 1501 data rows plus its header.

## Validate produced deliverables

Run the packaged validator after generation. JSON stdin schema:

```json
{
  "results_csv":"/root/simulation_results.csv",
  "tuning_yaml":"/root/tuning_results.yaml",
  "required_rows":1501
}
```

It emits JSON with `valid`, `errors`, and summary counts. It verifies exact result column order, row count, finite numeric values, ordered timestamps, legal modes, blank-field semantics, bounded commands, nonnegative ego speeds, and gain bounds. A failed validation means the executor must correct the input/configuration issue and rerun the documented pipeline; never invent CSV rows or report metrics.

## Interpretation and limitations

The report calculates metrics from the delivered trace and labels an unavailable metric `N/A` rather than claiming a target was met. Safety targets involving reported lead gap describe the observed sensor distance; the lead vehicle is externally controlled and cannot be changed by the ego controller. If a lead observation is malformed (one of speed/distance missing, nonfinite, or negative distance), the simulator fails explicitly instead of silently treating it as cruise.
