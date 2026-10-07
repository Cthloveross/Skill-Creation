---
name: glm-lake-temperature-calibration
description: >
  Configure, run, and calibrate the General Lake Model (GLM) 1-D lake
  simulation so that simulated vertical water temperature matches field
  observations within a target RMSE (e.g. < 2 degC). Use when a task provides a
  GLM binary, a `glm3.nml` configuration, meteorological/hydrological forcing
  CSVs, field temperature observations, and asks you to produce a NetCDF output
  over a given time span whose temperature RMSE is below a threshold while the
  final `glm3.nml` still runs successfully.
---

# GLM lake temperature calibration

This Skill drives GLM end-to-end: it edits the Fortran namelist to the requested
simulation span and output location, runs the model from a clean output
directory, reads the produced NetCDF, interpolates simulated temperature to the
observed depths/times, computes RMSE against the field data, and (if needed)
runs a small, reproducible, one-parameter-at-a-time (greedy coordinate) search
over physically meaningful calibration parameters until the RMSE target is met.
The best parameters are written back into the same `glm3.nml`, and a final clean
run verifies that this exact configuration reproduces a valid output file.

## Why these steps (from the calibration background)

- Compare simulated vs observed temperature **only after aligning timestamps and
  depths** — the scripts match by calendar day and interpolate temperature onto
  each observation depth below the (time-varying) lake surface.
- Calibrate a **small set of physically meaningful parameters** within plausible
  bounds, changing **one coherent group at a time**, and keep both the objective
  value and the model-run status (a failed run is never a valid candidate).
- The **final configuration must itself reproduce the simulation**: the Skill
  re-runs from a clean output directory, confirms the requested span and the
  `temp` variable exist, recomputes the RMSE from that file, and checks for
  missing values / truncated periods.

## Inputs (read the current task's actual paths at runtime)

Typical sandbox layout for this task (override via stdin JSON if different):

- GLM binary: `/usr/local/bin/glm`
- Namelist: `/root/glm3.nml`
- Forcing CSVs: `/root/bcs/*.csv` (referenced from the namelist, not edited here)
- Field observations: `/root/field_temp_oxy.csv`
- Required output: `/root/output/output.nc`
- Requested span: `2009-01-01` .. `2015-12-30`, target RMSE `< 2` degC

## Prerequisites

The scripts need `numpy`, `pandas`, and `netCDF4` (xarray is used as a fallback
for NetCDF reading if `netCDF4` is absent). Internet is allowed in this task, so
if an import fails install them first:

```bash
python3 -c "import numpy,pandas,netCDF4" 2>/dev/null || pip install numpy pandas netCDF4
```

## How the executor should use this Skill

1. (Optional) Inspect inputs: `head /root/glm3.nml`, `head /root/field_temp_oxy.csv`.
2. Run the entrypoint. It reads defaults for this task; you may pipe JSON on
   stdin to override any path, the span, the target RMSE, or disable calibration.

```bash
cd /root
python3 /app/environment/skills/current/scripts/run_task.py <<'JSON'
{}
JSON
```

   or with overrides:

```bash
python3 /app/environment/skills/current/scripts/run_task.py <<'JSON'
{"nml":"/root/glm3.nml","glm_bin":"/usr/local/bin/glm",
 "obs_csv":"/root/field_temp_oxy.csv",
 "start":"2009-01-01 00:00:00","stop":"2015-12-30 00:00:00",
 "out_dir":"output","out_fn":"output","target_rmse":2.0,"calibrate":true}
JSON
```

3. Read the JSON printed on stdout. Key fields:
   - `final.ok` (model ran and produced the NetCDF),
   - `final.rmse`, `final.n` (RMSE and number of matched obs),
   - `final.meets_target`,
   - `verify.out_nc`, `verify.has_temp`, `verify.time_min`, `verify.time_max`,
     `verify.span_ok`, `verify.finite_fraction`.
4. Success condition for the public task: `verify.out_nc` exists at
   `/root/output/output.nc`, `verify.has_temp` is true, `verify.span_ok` is true,
   `final.rmse` is finite and `< target_rmse`, and the on-disk `glm3.nml` is the
   one that produced it (the entrypoint writes the chosen parameters back and does
   the final run from that file). If `final.meets_target` is false, widen the
   calibration ranges (see `references/glm_notes.md`) via the single-eval helper
   and re-run, or inspect `final.run.stderr` for model failures.

## Single-shot evaluation helper

`scripts/run_once.py` configures the namelist with an explicit parameter set,
runs one clean simulation, and reports status + RMSE. Use it to probe specific
parameters or to re-verify a chosen configuration. stdin JSON:

```json
{"nml":"/root/glm3.nml","glm_bin":"/usr/local/bin/glm",
 "obs_csv":"/root/field_temp_oxy.csv",
 "start":"2009-01-01 00:00:00","stop":"2015-12-30 00:00:00",
 "out_dir":"output","out_fn":"output",
 "set_params":{"wind_factor":1.1,"sw_factor":1.0}}
```

stdout JSON: `{"ok":bool,"rmse":float|null,"n":int,"out_nc":str,"run":{...}}`.
Only parameters that already exist in the namelist are changed; unknown names are
reported in `skipped` and otherwise ignored (never invent namelist keys).

## Failure handling

- If GLM exits non-zero or no NetCDF appears, `ok` is false and `run.stderr`
  carries the model message; fix the namelist/forcing issue before trusting any
  RMSE. A failed run is not a calibration candidate.
- If no observations match the simulated days (`n==0`), check the observation CSV
  column detection and the simulated time axis; RMSE is reported as `null`.
- Do not hardcode any instance's parameter values or RMSE into the Skill; the
  calibration search derives them at runtime from the supplied data.
