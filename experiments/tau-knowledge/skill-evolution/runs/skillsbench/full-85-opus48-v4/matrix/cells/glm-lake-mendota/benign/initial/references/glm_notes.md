# GLM namelist and output notes

These notes support the scripts; verify details against the actual `glm3.nml`
and NetCDF of the current task rather than assuming them.

## Namelist sections commonly present

- `&glm_setup`: `sim_name`, `max_layers`, `min_layer_vol`, `min_layer_thick`,
  `max_layer_thick`, and mixing-related `density_model` on some builds.
- `&mixing`: `coef_mix_conv`, `coef_wind_stir`, `coef_mix_shear`,
  `coef_mix_turb`, `coef_mix_KH`, `coef_mix_hyp`, `deep_mixing`.
- `&morphometry`: hypsography (`H`, `A`), lake name, latitude/longitude.
- `&time`: `timefmt`, `start`, `stop`, `dt` (seconds), `num_days`.
  With `timefmt = 2` the run is bounded by the `start`/`stop` strings
  `'YYYY-MM-DD HH:MM:SS'`.
- `&output`: `out_dir`, `out_fn`, `nsave` (output every `nsave` steps). With
  `dt = 3600` and `nsave = 24` output is daily. Output goes to
  `<cwd>/<out_dir>/<out_fn>.nc` when `out_dir` is relative.
- `&init_profiles`: initial temperature/salinity vs depth.
- `&meteorology`: forcing CSV path/columns plus bulk-transfer and scaling
  factors used for calibration: `wind_factor`, `sw_factor`, `lw_factor`,
  `at_factor`, `rh_factor`, `rain_factor`, `ce` (latent), `ch` (sensible),
  `cd` (momentum).
- `&light`: `light_mode`, `Kw` (background light extinction coefficient).
- `&inflow` / `&outflow`: hydrological forcing CSVs (e.g. yahara, pheasant,
  outflow). Not edited by this Skill.

## Calibration guidance

Tune a small, physical set within plausible bounds, one group at a time:

- Surface heat balance: `sw_factor`, `lw_factor`, `at_factor`, `ce`, `ch`.
- Wind-driven mixing: `wind_factor`, `coef_wind_stir`, `coef_mix_*`.
- Light penetration / stratification: `Kw` (lower `Kw` -> deeper heating).

If the greedy search in `run_task.py` cannot reach the target, widen the value
lists via the `candidates` field on stdin, or probe individual parameters with
`run_once.py` and `set_params`. Always keep the run status: a non-zero GLM exit
or a missing NetCDF is not a valid calibration candidate.

## NetCDF output structure (for RMSE)

- `time`: numeric with a `units` attribute like `"hours since YYYY-MM-DD ..."`.
- `z[time, z]`: elevation (m) of the top of each layer, increasing with index up
  to `NS` active layers; the surface elevation at time t is `z[t, NS[t]-1]`.
- `temp[time, z]`: layer temperatures (deg C). Unused upper indices are
  masked/fill.
- `NS[time]`: number of active layers (fallback: count of finite `temp`).

To evaluate at an observation depth `d`: surface = top active layer elevation;
target elevation = surface - d; interpolate temperature vs layer-midpoint
elevation. Observations are matched to simulated output by calendar day (within
a one-day tolerance). RMSE is the root mean square of (sim - obs) over all
matched depth/time pairs.
