---
name: reflow-maintenance-compliance
summary: Compute handbook-governed reflow ramp, TAL, peak, conveyor, and run-ranking results from a PDF handbook plus MES, thermocouple, and defect CSV exports.
---

# Reflow maintenance and compliance

Use this Skill when a task requires process-compliance decisions that must be derived from the supplied reflow handbook rather than from generic reflow constants. It writes the five required JSON artifacts and deliberately fails when a required handbook rule is ambiguous, rather than inventing a limit or ranking rule.

## Method

1. Extract and inspect the handbook and the actual CSV schemas:
   ```bash
   python3 scripts/inspect_inputs.py <<'JSON'
   {"data_dir":"/app/data","handbook_path":"/app/data/handbook.pdf"}
   JSON
   ```
   The resulting JSON includes column inventories, PDF text, and keyword contexts. Check the original PDF when a table's extracted layout is unclear.
2. Transcribe only the applicable handbook rules into a JSON policy. The policy is an auditable bridge between handbook language/tables and calculation code; do not supply remembered industry defaults. Save it, for example, as `/app/policy.json`.
3. Run the solver:
   ```bash
   python3 scripts/solve_reflow.py <<'JSON'
   {"data_dir":"/app/data","output_dir":"/app/output","policy_path":"/app/policy.json"}
   JSON
   ```
   It emits a JSON summary on stdout and creates `/app/output/q01.json` through `/app/output/q05.json`.
4. Read the summary and inspect all five artifacts. Lists and maps are deterministic: runs, board families, and IDs are sorted ascending. All finite calculated floats are rounded to two decimals.

The scripts use CSV header aliases only to discover common fields. If discovery selects an unsuitable column, set the relevant `columns` member in the policy to the exact observed column name. This is preferable to renaming source data.

## Policy JSON schema

All numeric process rules must come from the current handbook. Values may be scalar defaults or dictionaries keyed by the observed material or board-family value. A minimal complete policy commonly has this shape (the values below are placeholders, not process recommendations):

```json
{
  "columns": {
    "run_id": "optional exact MES run column",
    "board_family": "optional exact MES family column",
    "material": "optional exact MES alloy column",
    "actual_speed": "optional exact MES speed column",
    "thermo_run_id": "optional exact TC run column",
    "tc_id": "optional exact TC sensor column",
    "time": "optional exact TC elapsed-time/timestamp column",
    "temperature": "optional exact TC temperature column",
    "defects_run_id": "optional exact defects run column"
  },
  "ramp": {
    "preheat_min_c": 0,
    "preheat_max_c": 0,
    "limit_c_per_s": 0,
    "segment_rule": "fully_within",
    "statistic": "heating",
    "representative": "maximum"
  },
  "tal": {
    "liquidus_c_by_material": {"observed-material": 0},
    "default_liquidus_c": null,
    "min_s": 0,
    "max_s": 0,
    "scope": "each_tc"
  },
  "peak": {
    "min_c_by_material": {"observed-material": 0},
    "default_min_c": null,
    "liquidus_margin_c": null
  },
  "conveyor": {
    "heated_length_cm_by_family": {"observed-family": 0},
    "default_heated_length_cm": null,
    "max_dwell_s": 0,
    "allowed_min_speed_cm_min": null,
    "allowed_max_speed_cm_min": null,
    "actual_speed_unit": "cm_min"
  },
  "ranking": {
    "criteria": [
      {"source":"defects","field":"observed defect field","aggregate":"sum","direction":"asc"},
      {"source":"mes","field":"observed efficiency field","direction":"desc"}
    ]
  }
}
```

`segment_rule` is `fully_within` when the handbook excludes boundary-crossing temperature segments, or `clip_to_region` when it calls for interpolation at preheat boundaries. `statistic` is `heating` (largest positive slope) or `absolute`. `representative` currently supports `maximum` and selects the TC with the largest per-TC result; this matches handbooks that designate the worst/highest-ramp TC. If the handbook specifies a named TC, filter to it before solving or use an exact one-sensor input.

For TAL, `scope: "each_tc"` produces one result per usable trace, while `scope: "representative"` retains the trace with the highest TAL per run. Use only the handbook's stated sensor-selection rule. TAL is integrated piecewise linearly above liquidus, including interpolated crossings. Peak policy may state a direct minimum or a liquidus margin; direct material-specific minimum takes precedence.

Conveyor required minimum speed is `max(allowed_min_speed, heated_length / max_dwell * 60)` for rules supplied by the handbook. `meets` additionally enforces an optional handbook maximum speed. Supported input speed units are `cm_min`, `mm_s`, `mm_min`, `m_min`, and `cm_s`.

For ranking, criteria are applied in listed priority order (lexicographically), so handbook tie-breakers should be listed too. Criteria read a MES value per run or aggregate all defect-record values for that run using `sum`, `mean`, `min`, or `max`. Missing criterion values rank after present values. The selected best run is the first ranked run; `runner_up_run_ids` contains all other family runs sorted by ID as required by the task.

## Validation and failure handling

The solver validates required columns, numeric values, duplicate/non-increasing TC times, and all required policy rules before writing output. It ignores only unusable individual TC samples, reporting missing-data results as `null` where the requested format allows them. A run with no usable TC trace is included and fails the peak requirement. If a handbook rule, material mapping, geometry mapping, or ranking priority cannot be supported by evidence, the script exits without writing partial answers. Correct the policy from the handbook and rerun.

No script action changes equipment or performs a banking/action-tool operation. The output is a calculation artifact for the execution agent to review against the handbook.
