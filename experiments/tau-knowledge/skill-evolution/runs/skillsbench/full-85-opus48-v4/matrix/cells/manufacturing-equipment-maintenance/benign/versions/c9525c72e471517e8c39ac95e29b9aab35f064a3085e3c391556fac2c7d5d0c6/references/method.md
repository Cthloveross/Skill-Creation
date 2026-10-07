# Method and formulas

This Skill separates **deterministic math** (packaged scripts) from
**process policy** (read from the handbook at runtime and passed in as config).

## Formulas
- Segment ramp: `r = (T2 - T1) / (t2 - t1)`, with `t2 > t1`.
  Max preheat ramp = largest segment ramp over samples inside the handbook's
  preheat temperature band. `boundary` controls whether a segment counts when
  only one endpoint is in band (`both_in_band` default, `any_overlap`, `all`).
- Time Above Liquidus: sum of segment durations above the handbook liquidus,
  with crossing time `t_cross = t1 + (t2 - t1) * (Tref - T1)/(T2 - T1)`.
  `tal_inclusive` controls whether `T == Tref` counts as above.
- Peak: max valid temperature sample of the trace.
- Conveyor speed: `v = d / t`; pitch `= L + S`. Convert all lengths to cm and
  times to the stated unit before comparing. `required_min_speed_cm_min` can be
  given directly or derived from `heated_length_cm / max_dwell_s * 60`.

## Representative-sensor selection
The handbook decides which thermocouple represents a run. Options in config:
- `max_metric` – the sensor with the largest value (worst-case ramp/TAL).
- `min_metric` – the sensor with the smallest value (e.g. coldest peak = worst
  case for a *minimum* peak requirement; this is the Q3 default).
- `specific` – a named sensor position stated in the handbook
  (`q1_specific_tc` / `q2_specific_tc` / `q3_specific_tc`).
Always confirm the handbook's wording; do not guess the rule.

## Missing data
- No thermocouple trace for a run: Q1/Q2 metrics are `null`; the run is forced
  into Q3 `failing_runs`, and its Q2 status becomes `non-compliant`.
- Zero/negative `dt` segments and duplicate timestamps are skipped.
- Equal-endpoint segments at the threshold are handled without divide-by-zero.

## Run ranking (Q5)
There is no universal weighting. Supply `priority` as an ordered list of
`{"metric": name, "dir": "asc"|"desc"}` taken from the handbook/instruction
(e.g. highest yield, then lowest defect count, then fastest feasible speed).
The script sorts each board_family's runs by that lexicographic priority with a
deterministic `run_id` tie-break, picks `best_run_id`, and lists the rest as
`runner_up_run_ids`. Available built-in metrics: `defects`, `yield` (needs a
total/inspected column). Pass any additional per-run metrics (speed, TAL, peak
compliance flags, throughput) via `q5.extra_metrics = {run_id: {metric: value}}`
after computing them. If the handbook states no priority, report the evidence
and do not invent weights.

## Output discipline
- Floats rounded to 2 decimals.
- Arrays sorted ascending by `run_id` / `board_family` / `board_id`.
- `null` only for genuinely missing/unavailable values.
- Match each JSON schema exactly (object vs array, key names, status strings
  `compliant`/`non-compliant`, boolean `meets`).
