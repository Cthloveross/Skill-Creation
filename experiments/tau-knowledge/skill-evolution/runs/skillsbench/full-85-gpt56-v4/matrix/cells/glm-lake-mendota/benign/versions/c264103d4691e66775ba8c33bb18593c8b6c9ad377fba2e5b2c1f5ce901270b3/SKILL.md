---
name: glm-vertical-temperature-calibration
description: Run and calibrate a General Lake Model (GLM) configuration against timestamped, depth-resolved water-temperature observations. Use when forcing CSVs, a GLM namelist, observations, and a required NetCDF output location are supplied and the final namelist must rerun successfully.
---

# GLM vertical-temperature calibration

This Skill provides small utilities for inspecting supplied lake-model data, changing existing namelist values deliberately, running GLM from a clean output directory, and computing a reproducible depth- and time-aligned temperature RMSE from the resulting NetCDF file.

## Inputs and assumptions

* GLM executable, namelist, forcing files, observations, and desired output path are supplied by the task.
* The namelist already describes the lake and forcing. Do not create a synthetic configuration or replace supplied forcing with invented values.
* Observation times and depths must be matched by their values, never by CSV row number.
* `xarray`, `pandas`, and `numpy` must be available to use `score_glm.py`. If they are unavailable, report that prerequisite rather than claiming an RMSE.

All scripts read one JSON object from standard input and write one JSON object to standard output. They return structured errors in JSON; inspect `ok`, `returncode`, and `error` before treating a candidate as valid.

## Recommended workflow

1. **Inspect before editing.** Examine the namelist and run:
   ```sh
   printf '%s' '{"observations":"/root/field_temp_oxy.csv","forcing_dir":"/root/bcs"}' | python3 scripts/inspect_inputs.py
   ```
   Confirm the observation timestamp, depth, and temperature columns; date coverage; missingness; forcing schemas; and depth convention. Inspect the NetCDF coordinates after an initial successful run as well.

2. **Make the requested simulation period and output location explicit using only fields that already exist in the namelist.** `patch_namelist.py` accepts raw Fortran right-hand-side values and refuses to add unknown fields. For example, after confirming exact field names in the supplied namelist:
   ```sh
   printf '%s' '{"path":"/root/glm3.nml","backup":"/root/glm3.nml.before","updates":{"start_time":"'"'"'YYYY-MM-DD 00:00:00'"'"'","num_days":"N","out_dir":"'"'"'/root/output'"'"'"}}' | python3 scripts/patch_namelist.py
   ```
   Use the task's actual start/end dates and GLM's actual existing fields. If the configuration uses an end-date field rather than a duration, patch that existing field instead. Check the returned `changed` and `missing` lists.

3. **Establish a baseline.** Run from the namelist directory, with a clean target output directory:
   ```sh
   printf '%s' '{"config":"/root/glm3.nml","glm_bin":"/usr/local/bin/glm","output":"/root/output/output.nc"}' | python3 scripts/run_glm.py
   ```
   A nonzero process exit, absent output, or stale/unreadable NetCDF makes the candidate invalid.

4. **Score the actual generated file.** Supply explicit column and variable names when auto-detection is not unambiguous:
   ```sh
   printf '%s' '{"netcdf":"/root/output/output.nc","observations":"/root/field_temp_oxy.csv","obs_time":"DATE_COLUMN","obs_depth":"DEPTH_COLUMN","obs_temperature":"TEMPERATURE_COLUMN","temperature_variable":"temp","depth_mode":"direct","max_time_gap":"12h","max_rmse":2.0}' | python3 scripts/score_glm.py
   ```
   `depth_mode` is `direct` when observation and NetCDF vertical coordinates use the same convention, `absolute` when they differ only by sign, and `from_surface` when the model coordinate is elevation and observations are positive depth below the modeled water surface. The latter uses the maximum modeled layer elevation at each matched time as the surface. Review `matched`, `unmatched_time`, `unmatched_depth`, and returned ranges; a low RMSE based on a tiny or truncated overlap is not an acceptable calibration.

5. **Calibrate reproducibly.** Change one coherent physically meaningful group at a time (for example, mixing/turbulence controls, or a justified surface-exchange group), remaining within documented/plausible bounds. Keep a table of: raw namelist updates, GLM run status, matched count, temporal tolerance, depth convention, and RMSE. Start coarse and narrow around successful candidates. Do not score a failed run, and do not interpret a coefficient or a forcing column without checking its units.

6. **Finalize.** Leave the selected values in the supplied final namelist. Delete the output directory and invoke `run_glm.py` once more from the final namelist; then rerun `score_glm.py` against that newly generated file. Confirm that output exists at the exact requested path, contains finite temperatures, covers the requested period, and meets the requested RMSE threshold. The final configuration, not an earlier candidate output, must reproduce the result.

## Script contracts

* `inspect_inputs.py`: input `observations` and optional `forcing_dir`; output CSV columns, row counts, non-null counts, and samples/date ranges.
* `patch_namelist.py`: input `path`, `updates` (mapping of existing namelist keys to raw Fortran values), optional `backup`; output changed and missing keys. It never guesses syntax or appends keys.
* `run_glm.py`: input `config`, optional `glm_bin`, required `output`, optional `timeout_sec`; removes only the parent directory of the declared output before launching GLM, and reports the captured process status and output existence.
* `score_glm.py`: input `netcdf`, `observations`, optional explicit names and matching controls; output selected mappings, coverage, match accounting, finite-value checks, RMSE, and threshold status.

If a required field cannot be identified, time/depth units cannot be reconciled, or fewer than a meaningful number of observations match, stop and correct the data/configuration interpretation rather than fabricating a result.
