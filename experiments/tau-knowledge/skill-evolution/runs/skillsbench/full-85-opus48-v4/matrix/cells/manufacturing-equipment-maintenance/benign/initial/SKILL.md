---
name: reflow-process-compliance
description: >-
  Answer reflow-oven maintenance and process-compliance questions by reading all
  policy values (preheat region, ramp limit, liquidus temperature, TAL window,
  peak reference + margin, board geometry, dwell/speed feasibility, run-ranking
  priorities) from a supplied handbook.pdf at runtime, then computing per-trace
  quantities from thermocouple/MES/defect CSVs. Produces /app/output/q01.json ..
  q05.json in the exact requested schemas. Use when a task gives a reflow
  handbook plus thermocouples.csv, mes_log.csv, test_defects.csv and asks for
  ramp rate, time-above-liquidus, peak temperature, conveyor-speed feasibility,
  and best-run selection.
---

# Reflow process compliance

## When to use
Use this Skill for the manufacturing-equipment-maintenance style task: a reflow
machine `handbook.pdf` and three CSVs (`thermocouples.csv`, `mes_log.csv`,
`test_defects.csv`) under `/app/data/`, with five questions whose answers go to
`/app/output/q01.json` .. `q05.json`.

## Core principle (do not hardcode policy)
Every numeric policy value is **process-specific and lives in the handbook**:
preheat temperature region, ramp equation + allowable limit (Q1); liquidus
reference and TAL window min/max + inclusivity (Q2); peak reference + margin
(Q3); board geometry, heated length, dwell requirement, allowable conveyor speed
(Q4); and run-ranking priorities/tie-breakers (Q5). Read them from the handbook
at runtime. Never substitute a remembered IPC/J-STD band. The scripts here do the
deterministic math; **you** supply the handbook-derived parameters.

## Workflow
1. **Read the handbook.** Run `scripts/extract_handbook.py` to dump text per page
   (it tries pdfplumber, PyPDF2, then `pdftotext`). Record, with page numbers:
   - preheat definition + temperature region (low/high °C) + ramp equation +
     allowable ramp limit (°C/s) and its sign/inclusivity;
   - which thermocouple is "most representative" (a named sensor position, or a
     worst-case rule);
   - solder liquidus temperature, TAL window (min & max seconds), and whether
     the comparison is strict or inclusive;
   - peak temperature requirement = reference temperature + margin (or explicit
     minimum peak), and how sensors combine;
   - board length/spacing, heated-zone length, required dwell (e.g. dwell above
     liquidus or heated-length dwell), and the feasible conveyor-speed rule
     (lower bound / upper bound / interval);
   - any stated run-selection priority order and tie-breakers.
2. **Discover the data schema.** Run `scripts/inspect_data.py` to print columns,
   dtypes, sample rows, unique `run_id`s and `board_family`s for each CSV. Do not
   assume column names; map them explicitly.
3. **Compute per-trace metrics.** Run `scripts/thermal_metrics.py` with the
   thermocouple column mapping and the handbook preheat band + liquidus. It
   returns, per run and per thermocouple: max preheat ramp (°C/s), TAL (s), and
   peak (°C). Inspect these before applying selection rules.
4. **Assemble answers.** Run `scripts/build_outputs.py` with a single config JSON
   carrying all handbook-derived parameters and column mappings. It writes all
   five `qNN.json` files applying the selection/sort/rounding rules. Review each
   file; adjust the config (not the data) where the handbook rule differs.
5. **Verify.** Re-derive one run by hand from the raw CSV (one ramp segment, one
   TAL crossing, one peak) and confirm it matches the JSON. Confirm arrays are
   sorted ascending by key, floats rounded to 2 decimals, and `null` used for
   genuinely missing data. Runs with no usable thermocouple data must appear as
   failing in Q3.

## Output contracts (must match exactly)
- **q01.json**: object `{ramp_rate_limit_c_per_s, violating_runs:[run_id],
  max_ramp_by_run:{R#:{tc_id, max_preheat_ramp_c_per_s}}}`. `violating_runs` are
  runs whose representative max preheat ramp exceeds the handbook limit.
- **q02.json**: array of `{run_id, tc_id, tal_s, required_min_tal_s,
  required_max_tal_s, status}` with status `compliant`/`non-compliant`.
- **q03.json**: object `{failing_runs:[run_id],
  min_peak_by_run:{R#:{tc_id, peak_temp_c, required_min_peak_c}}}`. Pick the
  sensor with the **minimum** peak per run (coldest, worst case) unless the
  handbook names a representative sensor; a run with no thermocouple data fails
  (report `null` metrics and include it in `failing_runs`).
- **q04.json**: array of `{run_id, required_min_speed_cm_min, actual_speed_cm_min,
  meets}`.
- **q05.json**: array of `{board_family, best_run_id, runner_up_run_ids}`.

## Script I/O
All scripts read a JSON object from **stdin** and write JSON to **stdout**.
See `references/method.md` for config field details and formulas. Example:
```bash
echo '{"pdf_path":"/app/data/handbook.pdf"}' | python3 scripts/extract_handbook.py
echo '{"paths":["/app/data/thermocouples.csv","/app/data/mes_log.csv","/app/data/test_defects.csv"]}' | python3 scripts/inspect_data.py
echo '{"thermo_csv":"/app/data/thermocouples.csv","preheat":{"temp_low":50,"temp_high":150},"liquidus":217}' | python3 scripts/thermal_metrics.py
cat config.json | python3 scripts/build_outputs.py   # writes /app/output/q0*.json
```

## Failure / missing-data handling
- Missing or unreadable handbook value: stop and re-extract; do not guess. If a
  value is truly absent, emit `null` for the dependent field and document it.
- Missing thermocouple trace for a run: Q1/Q2 metrics `null`; Q3 run fails.
- Duplicate timestamps, equal endpoints, out-of-order samples: `thermal_metrics`
  sorts by time, skips zero/negative dt segments, and handles equal-temp
  crossings explicitly.
- Unit mismatches: normalize (s, °C, cm, cm/min) before comparing; the speed
  helpers convert explicitly.
