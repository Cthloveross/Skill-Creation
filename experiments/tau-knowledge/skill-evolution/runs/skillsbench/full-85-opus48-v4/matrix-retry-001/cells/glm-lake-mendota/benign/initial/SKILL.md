---
name: glm-lake-temperature-calibration
description: Run and calibrate the General Lake Model (GLM) to simulate vertical lake water temperature from meteorological/hydrological forcing and a Fortran-namelist config, then verify RMSE against field observations below a target threshold. Use when a task provides a `glm` binary, a `glm3.nml` config, forcing CSVs, and field temperature observations, and asks you to produce a NetCDF simulation over a time span whose RMSE vs observations is under a limit (e.g. < 2 degC).
---

# GLM lake temperature calibration

This Skill drives the General Lake Model (GLM) end-to-end: it fixes the
simulation time span and output location in the namelist, runs the model from a
clean output directory, extracts simulated temperatures at observed depths and
times, recomputes RMSE from the produced NetCDF file, and (if needed) performs a
small, reproducible calibration over physically meaningful parameters until the
RMSE target is met. The final `glm3.nml` must itself reproduce the submitted
`output.nc`.

## When this applies

The public task supplies:
- a GLM executable (commonly `/usr/local/bin/glm`),
- a Fortran namelist config (`glm3.nml`) describing setup, time, output,
  morphometry, meteorology, inflow/outflow, and initial profiles,
- forcing CSVs under a `bcs/` directory (meteo, inflows, outflow),
- field observations CSV (datetime, depth, temperature, possibly oxygen),
- a required simulation span and output path (e.g. `/root/output/output.nc`),
- an RMSE acceptance threshold.

The grader checks that GLM runs successfully with the *final* parameters in
`glm3.nml` and that the produced `output.nc` yields RMSE below the threshold.
Read the actual opening message and files at runtime; do not assume values.

## Method (follow in order)

1. **Inspect inputs first.** Print the head of `glm3.nml` and of each supplied
   CSV. Confirm the forcing file paths referenced in the namelist are correct
   relative to the working directory where GLM runs (GLM reads `glm3.nml` from
   its current directory and resolves relative paths from there). Confirm the
   forcing covers the requested span, units, time zone, depth convention, and
   that morphometry / initial profiles are consistent. A failed run is never a
   valid calibration candidate.
2. **Fix the controllable namelist fields.** Set `timefmt=2`, `start` and
   `stop` to the requested span (quoted `'YYYY-MM-DD HH:MM:SS'`), `out_dir`
   and `out_fn` so the output lands at the required path (for
   `/root/output/output.nc` use `out_dir='output'`, `out_fn='output'` with
   cwd `/root`). Do not disturb morphometry or initial profiles.
3. **Run from a clean output directory.** Delete and recreate the output dir
   before every run so stale/truncated files cannot be mistaken for success.
4. **Recompute RMSE from the file.** Match each observation to the nearest
   simulated time (within one day) and interpolate simulated temperature at the
   observation depth using the GLM layer heights (`z`) and layer temperatures
   (`temp`), honouring the active-layer count `NS`. Never trust an RMSE printed
   by the model; derive it from `output.nc`.
5. **Calibrate only if needed.** If the baseline already meets the threshold,
   keep it. Otherwise search a small set of physically meaningful parameters
   within plausible bounds (surface-flux scalers and light attenuation are the
   most sensitive for surface/epilimnion temperature). Change one coherent
   group at a time, record both RMSE and run status, and keep the best valid
   run.
6. **Finalize and self-verify.** Write the chosen parameters into `glm3.nml`,
   run once more from a clean output directory, confirm the dataset covers the
   full requested span and contains finite `temp`, and recompute RMSE. The
   submitted `glm3.nml` plus a fresh run must reproduce the passing result.

## Scripts

All scripts read a single JSON object on stdin and print a single JSON object on
stdout. Run them with the task's Python (ensure `numpy`, `pandas`, and
`netCDF4` are importable; if `netCDF4` is missing and internet is allowed,
`pip install netCDF4` first — `output.nc` is HDF5-backed NetCDF4 that `scipy`
cannot read).

### `scripts/run_glm.py` (end-to-end entrypoint)
Input JSON keys (all optional except where your task differs from defaults):
```
{
  "nml": "/root/glm3.nml",
  "glm_bin": "glm",
  "cwd": "/root",
  "out_dir": "output",          // relative to cwd; file becomes <out_dir>/<out_fn>.nc
  "out_fn": "output",
  "field_csv": "/root/field_temp_oxy.csv",
  "start": "2009-01-01 00:00:00",
  "stop":  "2015-12-30 00:00:00",
  "target_rmse": 2.0,
  "calibrate": true,
  "grid": {"wind_factor":[0.9,1.0,1.1], "Kw":[0.3,0.6], "sw_factor":[1.0]},
  "max_runs": 12,
  "cols": {"time":null, "depth":null, "temp":null}  // override auto-detection if needed
}
```
It edits the namelist time/output fields, runs the baseline, calibrates if the
baseline misses `target_rmse`, writes the best valid parameters back into the
namelist, and performs a final clean verification run. Output JSON reports
`baseline_rmse`, `best_params`, `final_rmse`, `final_status`, `output_nc`, and
per-run history. Example:
```
echo '{"nml":"/root/glm3.nml","field_csv":"/root/field_temp_oxy.csv","start":"2009-01-01 00:00:00","stop":"2015-12-30 00:00:00","target_rmse":2.0}' \
  | python3 /app/environment/skills/current/scripts/run_glm.py
```
Interpret the result: if `final_rmse` is below `target_rmse` and
`final_status=="ok"`, the task deliverables are in place (`output.nc` and the
final `glm3.nml`). If not, widen `grid` (e.g. add `lw_factor`, `ce`, `ch`, more
`wind_factor`/`Kw` points) and rerun, or inspect `history` for failing runs.

### `scripts/compute_rmse.py`
Input `{"output_nc":...,"field_csv":...,"start":...,"stop":...,"cols":{...}}`;
output `{"rmse":..,"n":..,"by_depth":{..},"depths":[..]}`. Use it to
independently re-verify any `output.nc` against the observations.

### `scripts/check_output.py`
Input `{"output_nc":...,"start":...,"stop":...}`; output
`{"ok":bool,"covers_span":bool,"has_temp":bool,"finite":bool,"t_first":..,"t_last":..,"n_times":..}`.
Use it to confirm the produced dataset is complete and not stale/truncated.

### `scripts/nml_tools.py`
Input `{"nml":...,"action":"get"|"set","params":{key:value,...},"block":optional}`.
`get` returns current values; `set` edits in place (adding a key to the given
`&block` if absent). Useful for manual namelist adjustments.

## Failure handling

- If GLM exits nonzero, read the captured stderr tail in the script output;
  common causes are forcing coverage shorter than the span, wrong file paths,
  or inconsistent initial profiles. Fix the namelist/paths before treating any
  run as a candidate.
- If no observation matches a simulated day, loosen the time tolerance only if
  justified by the data cadence; otherwise re-check time zone/date parsing.
- If `netCDF4` cannot open `output.nc`, install it; do not substitute a reader
  that silently fails on NetCDF4/HDF5.
- Do not hardcode any instance's parameter values or RMSE into the Skill; the
  calibration and verification are recomputed from the current data each run.
