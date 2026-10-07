---
name: reflow-handbook-compliance-analysis
description: Analyze reflow oven thermocouple profiles, MES logs, and defect records using the process-specific definitions and limits extracted from a supplied handbook. Use when required to produce auditable JSON answers for preheat ramp, TAL, peak, conveyor feasibility, and run ranking without inventing process constants.
---

# Reflow handbook compliance analysis

This Skill deliberately does **not** supply thermal limits, liquidus values, sensor rules, geometry, ranking weights, or sample answers. Those are process-specific and must be transcribed from the current handbook before calculation.

## Inputs and outputs

The task files are normally `/app/data/handbook.pdf`, `thermocouples.csv`, `mes_log.csv`, and `test_defects.csv`. The end-to-end script reads a policy JSON document on stdin and writes these files to the configured output directory:

* `q01.json` — one handbook-representative preheat ramp per run;
* `q02.json` — TAL results, either for every trace or the handbook-selected trace;
* `q03.json` — minimum/required peak evidence per run, including a missing-data failure;
* `q04.json` — conveyor speed evidence per run; and
* `q05.json` — one lexicographically ranked best run and all remaining runs per family.

All scripts use JSON stdin/stdout. They use only Python's standard library and do not alter source files.

## Procedure

1. Extract and inspect the actual handbook rather than relying on general reflow knowledge. For a text PDF, run:

   ```sh
   printf '{"pdf":"/app/data/handbook.pdf"}' | python /app/environment/skills/current/scripts/extract_handbook.py > /tmp/handbook.json
   ```

   Read the returned page text around terms such as *preheat*, *ramp*, *liquidus*, *TAL*, *peak*, *conveyor*, *dwell*, *board*, *representative*, *quality*, and *tie*. If embedded text extraction is empty, use a locally available PDF viewer/OCR and record the relevant page numbers. Do not treat an unextractable page as evidence of a limit.

2. Inspect the actual CSV headers and a few rows, including units, timestamp format, run IDs, board family/material fields, speed, and defect granularity. `inspect_csv.py` provides a type-neutral inventory:

   ```sh
   printf '{"paths":["/app/data/thermocouples.csv","/app/data/mes_log.csv","/app/data/test_defects.csv"]}' | python /app/environment/skills/current/scripts/inspect_csv.py
   ```

3. Build a policy JSON from the handbook. Use exact CSV headers in `columns` where automatic aliases would be ambiguous. Every numerical constant in `policy` must be traceable to a handbook page. Important handbook decisions to transcribe include:
   * preheat lower/upper temperatures, whether crossing segments are clipped, positive versus absolute ramp, the limit, and how a representative thermocouple is chosen;
   * material-dependent liquidus, TAL min/max, comparison inclusivity, and whether TAL is reported per trace or one selected trace;
   * required peak by material (or liquidus plus stated margin) and the mandated peak sensor selection;
   * heated length, maximum dwell, machine speed bounds, and the required feasibility conjunction; and
   * quality/efficiency priority order and stated tie-breakers.

4. Run the engine, for example:

   ```sh
   python /app/environment/skills/current/scripts/reflow_analysis.py < /tmp/handbook_policy.json
   ```

5. Validate that all five files parse as JSON; lists and dictionary keys are in ascending required order; numbers are JSON numbers rounded to two decimals; IDs remain strings; every MES run expected by the task is represented where applicable; and `q03.failing_runs` contains all runs with no usable thermocouple trace. Spot-check one preheat segment, one interpolated TAL crossing, one peak, and one conveyor computation against source rows and handbook equations.

## Engine input schema

`reflow_analysis.py` accepts one JSON object:

```json
{
  "paths": {
    "thermocouples": "/app/data/thermocouples.csv",
    "mes": "/app/data/mes_log.csv",
    "defects": "/app/data/test_defects.csv",
    "output_dir": "/app/output"
  },
  "columns": {
    "thermocouples": {"run_id": "run_id", "tc_id": "tc_id", "time": "time_s", "temperature": "temperature_c"},
    "mes": {"run_id": "run_id", "board_family": "board_family", "material": "solder", "speed": "conveyor_speed_cm_min"},
    "defects": {"run_id": "run_id"}
  },
  "policy": { }
}
```

Only `paths` and `policy` are required. Omitted column mappings are resolved using conservative common aliases and the script returns a clear error if a required column cannot be found. Times may be numeric seconds, ISO-8601 values, or `HH:MM:SS`; all are converted to elapsed seconds per trace.

Required `policy` members are:

```json
{
  "preheat": {
    "lower_c": 0, "upper_c": 0, "ramp_limit_c_per_s": 0,
    "segment_mode": "within", "ramp_mode": "heating",
    "representative": "max"
  },
  "tal": {
    "liquidus_c": 0, "liquidus_by_material": {"optional material": 0},
    "min_s": 0, "max_s": 0, "inclusive": true,
    "output_scope": "all", "representative": "min"
  },
  "peak": {
    "required_min_c": 0, "required_min_by_material": {"optional material": 0},
    "representative": "min"
  },
  "conveyor": {
    "heated_length_cm": 0, "max_dwell_s": 0,
    "machine_min_speed_cm_min": 0, "machine_max_speed_cm_min": 0
  },
  "ranking": {
    "rules": [
      {"source": "defects", "field": "defect_count", "aggregate": "sum", "direction": "asc"},
      {"source": "mes", "field": "throughput", "direction": "desc"}
    ]
  }
}
```

`segment_mode` is `within` (only segments whose two sampled endpoints are in the specified region) or `clip` (linearly clip a crossing segment to the region). `ramp_mode` is `heating`, `absolute`, or `signed`. A representative is `max`, `min`, `median`, or `tc_id:<exact-id>`. Ties use ascending TC ID. `output_scope` is `all` or `representative`. TAL always integrates linearly over every valid ordered segment above the handbook liquidus, including partial crossing segments.

The reported required minimum conveyor speed is `heated_length_cm / max_dwell_s * 60`. A run meets conveyor requirements only when its actual speed is at least this value and within each non-null machine bound. Do not reverse this relationship unless the handbook itself defines a different requested output.

Ranking is lexicographic in handbook order, not a fabricated weighted score. Each rule reads a numeric field from `mes` or `defects`; optional `aggregate` is one of `sum`, `mean`, `min`, `max`, or `count` (default `sum` for defects and `mean` for MES). `direction` is `asc` or `desc`. A final deterministic run-ID tie break is used only after all stated handbook priorities tie. If the handbook has no ranking priorities, stop and report that evidence gap rather than inventing rules.

## Failure handling

The engine rejects absent required policy values, duplicate MES run IDs, unreadable CSVs, unusable time ordering, and unknown requested selectors. It excludes invalid individual thermocouple rows but does not silently convert a run with no usable trace into compliance: Q1 gives null selected values, Q3 marks it failing, and TAL output is absent unless a usable trace exists. Use `null` only where the requested format permits missing evidence; do not replace a handbook rule with `null`.
