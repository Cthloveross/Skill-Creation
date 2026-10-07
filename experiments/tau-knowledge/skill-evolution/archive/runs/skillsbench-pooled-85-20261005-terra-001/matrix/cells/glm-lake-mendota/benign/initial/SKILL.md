---
name: glm-temperature-calibration
description: Run and reproducibly calibrate a General Lake Model (GLM) namelist against depth-resolved temperature observations, producing a clean NetCDF output and a recomputed RMSE. Use when GLM forcing, a glm3.nml configuration, field temperature observations, and an executable are supplied.
---

# GLM temperature calibration

This Skill calibrates a small, physically meaningful set of existing GLM meteorological and mixing parameters. It never invents forcing values or changes lake geometry. It records every attempted model run, excludes failed runs from selection, writes the selected parameters into the supplied namelist, then runs that exact namelist from a clean output directory.

## Prerequisites

* A runnable GLM executable.
* A GLM 3 namelist whose filename is `glm3.nml` (the GLM executable's normal default input name).
* A configuration with `&time` `start` and `stop` fields and an `&output` group. The script patches those fields so the requested output period and destination are explicit.
* A NetCDF reader available to Python: `netCDF4` is preferred; `scipy.io.netcdf_file` is accepted for NetCDF classic files.
* Observation CSV containing a date/time column, a depth column, and a water-temperature column. Common header spellings are detected case-insensitively.

The calibration script uses the supplied configuration and forcing paths at runtime. It tries, only when present in the namelist, `at_offset`, `sw_factor`, `wind_factor`, and a coherent group of GLM mixing coefficients. The search is coordinate-based, bounded to plausible perturbations around the supplied values, and limited by `max_runs`.

## Run

Run the executable entrypoint by sending JSON on stdin. For the supplied Lake Mendota task, use:

```json
{
  "executable": "/usr/local/bin/glm",
  "config_path": "/root/glm3.nml",
  "observation_csv": "/root/field_temp_oxy.csv",
  "output_path": "/root/output/output.nc",
  "start": "2009-01-01",
  "stop": "2015-12-30",
  "rmse_target": 2.0,
  "max_runs": 24,
  "timeout_sec": 500
}
```

Invoke `scripts/calibrate_glm.py` with that JSON. It emits one JSON object containing the selected parameter changes, per-run status, final validation, and paths to retained logs/report. GLM stdout and stderr are retained under `glm_calibration_runs/` beside the namelist; they are not mixed into the script's JSON stdout.

`output_path` must end in the output filename GLM should create (normally `output.nc`). Its parent directory is cleaned before every candidate and before the final reproduction run. Do not point it at a directory containing unrelated files.

## Validation and interpretation

The final JSON's `final_validation` is calculated from the final `output.nc`, not from an earlier candidate. It checks that:

1. the requested time interval is represented in the output time coordinate;
2. a temperature variable and vertical coordinate can be identified;
3. observations are matched by timestamp and interpolated by depth, rather than matched by row number;
4. matched temperatures are finite; and
5. RMSE and the number of matched observations are reported.

A `success: true` result requires a successful final GLM execution, valid output, at least one matched observation, and RMSE below `rmse_target`. If it is false, inspect `runs`, the retained logs, and `final_validation.error`; do not report an unvalidated candidate as calibrated.

To independently recompute validation after the run, send the same `observation_csv`, `output_path`, `start`, and `stop` to `scripts/validate_glm_output.py`. Its JSON output includes the detected variable names, coordinate convention selected for depth, coverage, match count, and RMSE.

## Input/output schema

### `calibrate_glm.py`

Required JSON keys: `executable`, `config_path`, `observation_csv`, `output_path`, `start`, `stop`.

Optional keys: `rmse_target` (default `2.0`), `max_runs` (default `24`), and `timeout_sec` (default `500`). Dates may be ISO dates or ISO datetimes. The script writes the final selected namelist at `config_path`, the requested NetCDF file at `output_path`, and a JSON report beside the namelist.

### `validate_glm_output.py`

Required JSON keys: `observation_csv`, `output_path`, `start`, `stop`. It performs no model execution and writes only a JSON validation result to stdout.

Both scripts return structured JSON errors for missing files, unavailable NetCDF support, unrecognized observation schema, invalid time/depth coordinates, failed GLM runs, or no usable observation/simulation matches.
