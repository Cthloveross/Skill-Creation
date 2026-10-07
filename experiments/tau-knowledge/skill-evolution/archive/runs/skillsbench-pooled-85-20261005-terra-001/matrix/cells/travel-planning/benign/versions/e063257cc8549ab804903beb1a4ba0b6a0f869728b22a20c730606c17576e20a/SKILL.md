---
name: database-grounded-pet-friendly-road-itinerary
description: Create and validate the required seven-day, no-flight itinerary JSON from mounted travel CSVs. Use this Skill for fixed-path travel deliverables requiring source-traceable venues and accommodations with explicit public-record pet permission.
---

# Database-Grounded Pet-Friendly Road Itinerary

Create the required artifact before completing the task:

```sh
python3 scripts/execute_task.py <<'JSON'
{}
JSON
```

This reads `/app/data`, writes `/app/output/itinerary.json` atomically, reloads it, and validates it. A successful stdout result is `{"ok": true, ...}`. Do not consider the task complete on a nonzero exit or an `ok: false` result.

## Script interfaces

All scripts accept one JSON object on stdin and emit one JSON object on stdout.

- `scripts/execute_task.py` accepts `{}` or overrides for the public defaults and creates the deliverable.
- `scripts/build_itinerary.py` accepts `data_root`, `output_path`, `origin`, `target_state`, `party_size`, `budget`, `cuisines`, `days`, and `city_count`.
- `scripts/validate_itinerary.py` accepts `{"path":"/app/output/itinerary.json","data_root":"/app/data"}`.

Validate an existing artifact with:

```sh
python3 scripts/validate_itinerary.py <<'JSON'
{"path":"/app/output/itinerary.json","data_root":"/app/data"}
JSON
```

## Method and safeguards

The builder discovers CSV headers and derives target-state city names from the mounted city/state reference at runtime. It selects three Ohio cities that have database attractions and collectively support the requested cuisine coverage. Restaurants and attractions are emitted under their source names.

Pet accommodation is a hard constraint. The builder uses the same explicit positive/negative pet-policy expressions as the public requirement and examines policy-like columns in the matched accommodation record. It does **not** infer permission from a listing name, from wording added to the itinerary, or from a missing policy. Crucially, it resolves the output name using the public longest-name matching behavior *before* testing the policy. This prevents duplicate listing names from causing selection of a different, non-pet-permitted record.

The result has exactly seven ordered days, source-grounded meal and attraction names, semicolon-terminated attraction lists, Minneapolis departure, and self-driving-only transportation. The validator repeats schema, provenance, pet-policy, cuisine, route, and formatting checks after serialization.
