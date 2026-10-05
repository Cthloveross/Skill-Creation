---
name: database-grounded-pet-friendly-road-itinerary
description: Create the required seven-day, no-flight road itinerary JSON from mounted travel CSVs. Use when a travel task requires traceable restaurants and attractions, requested cuisine coverage, and lodging with explicit database-record pet permission.
---

# Database-Grounded Pet-Friendly Road Itinerary

Use the packaged entrypoint to create the required artifact. Do not hand-author venue names or substitute a plausible itinerary when the builder reports an error.

```sh
python3 scripts/execute_task.py <<'JSON'
{}
JSON
```

The entrypoint reads `/app/data`, writes `/app/output/itinerary.json` atomically, reloads it, and validates the result. Success is JSON with `"ok": true`; a nonzero exit or `"ok": false` means the deliverable is incomplete.

## Script interfaces

All scripts accept one JSON object on stdin and emit one JSON object on stdout.

- `scripts/execute_task.py` accepts `{}` or public-default overrides and creates `/app/output/itinerary.json`.
- `scripts/build_itinerary.py` accepts `data_root`, `output_path`, `origin`, `target_state`, `party_size`, `budget`, `cuisines`, `days`, and `city_count`.
- `scripts/validate_itinerary.py` accepts `{"path":"/app/output/itinerary.json","data_root":"/app/data"}` and validates an existing artifact.

For an existing output, run:

```sh
python3 scripts/validate_itinerary.py <<'JSON'
{"path":"/app/output/itinerary.json","data_root":"/app/data"}
JSON
```

## Method and safeguards

The builder discovers CSV headers at runtime and derives Ohio cities from the supplied city/state file. It only schedules cities that have database-grounded restaurants, attractions, and qualifying lodging. It uses exact source display names so the public records remain traceable.

Pet permission is a hard constraint. A candidate is accepted only if the same longest-name matching procedure used for output provenance resolves it to an accommodation record whose policy-like columns contain explicit positive wording (`pet-friendly`, `pets allowed`, `pets welcome`, `allows pets`, `dogs allowed`, or `dog-friendly`) and no explicit prohibition. Listing titles, itinerary prose, and missing policy statements never count as pet permission.

The generated artifact has exactly seven ordered day objects, a Minneapolis self-driving departure, three Ohio cities, only ground-transport wording, semicolon-terminated attraction lists, and database-backed meal selections covering American, Mediterranean, Chinese, and Italian cuisine. The post-write validator repeats schema, provenance, cuisine, formatting, origin, Ohio-city, and pet-policy checks.
