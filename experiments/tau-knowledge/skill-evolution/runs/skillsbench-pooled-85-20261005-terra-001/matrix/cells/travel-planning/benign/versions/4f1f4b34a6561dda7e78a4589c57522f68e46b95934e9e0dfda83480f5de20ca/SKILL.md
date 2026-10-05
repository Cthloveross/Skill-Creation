---
name: database-grounded-pet-friendly-road-itinerary
description: Build the required seven-day, no-flight Minneapolis-to-Ohio itinerary artifact from the supplied local CSV databases, using only traceable venues and lodging with explicit positive pet permission.
---

# Database-Grounded Pet-Friendly Road Itinerary

Use this Skill for the current travel-planning task. The deliverable is the file `/app/output/itinerary.json`, not a chat description. **Run the entrypoint before completing the task.** It reads the supplied CSVs, selects source records at runtime, writes the required artifact atomically, and validates it.

## Required execution

From the Skill package root, with public data mounted at `/app/data`, run:

```sh
python3 scripts/execute_task.py <<'JSON'
{}
JSON
```

The script accepts one JSON object on stdin and emits one JSON status object on stdout. With `{}`, it implements this task's Minneapolis departure, March 17–23, 2022 duration, two-person party, $5,100 budget, three Ohio cities, requested cuisine coverage, ground-only transport, and pet requirement. Success is reported as `{"ok": true, "output_path": "/app/output/itinerary.json", ...}`.

If the script reports `ok: false`, do not fabricate an itinerary. Its `error` identifies a public-data constraint that could not be supported.

To independently inspect the completed artifact, run:

```sh
python3 scripts/validate_itinerary.py <<'JSON'
{"path":"/app/output/itinerary.json","data_root":"/app/data"}
JSON
```

## Script interfaces

- `scripts/execute_task.py` stdin is an optional JSON object containing overrides for `data_root`, `output_path`, `origin`, `target_state`, `start_date`, `end_date`, `party_size`, `budget`, `cuisines`, `days`, and `city_count`. It writes a JSON status object to stdout.
- `scripts/build_itinerary.py` stdin is a complete configuration object with those fields. It writes the artifact and emits the same status schema.
- `scripts/validate_itinerary.py` stdin is `{"path": string, "data_root": string}`. It emits `{"ok": true, "path": string}` or `{"ok": false, "error": string}`.

## Method and safeguards

The builder reads only the supplied accommodations, restaurants, attractions, city/state, and distance CSV/text data. It discovers identity columns at runtime and retains exact source names in itinerary fields so entries remain traceable.

An accommodation is eligible only if policy-like source columns explicitly match positive wording such as `pet-friendly`, `pets allowed`, `pets welcome`, `allows pets`, `dogs allowed`, or `dog-friendly`, with no explicit no-pets wording. A label added to the JSON never substitutes for source policy evidence.

The generated plan has exactly seven ordered day objects, uses self-driving transport only, visibly departs Minneapolis, includes three distinct Ohio cities, gives every day a semicolon-terminated attraction string, and makes restaurant choices whose recorded cuisines cover American, Mediterranean, Chinese, and Italian. The builder uses direct indexed filtering rather than quadratic all-record comparisons, so it can finish reliably against the supplied datasets.
