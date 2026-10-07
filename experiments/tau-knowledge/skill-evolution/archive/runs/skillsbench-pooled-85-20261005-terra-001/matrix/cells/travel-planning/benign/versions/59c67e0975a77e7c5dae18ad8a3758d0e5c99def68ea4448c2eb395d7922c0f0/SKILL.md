---
name: database-grounded-pet-friendly-road-itinerary
description: Create and validate the required seven-day, ground-only Minneapolis-to-Ohio itinerary JSON using the supplied local travel databases. Use when accommodations must have explicit source-supported pet permission and meals, attractions, and lodging must be traceable to CSV records.
---

# Database-Grounded Pet-Friendly Road Itinerary

This Skill produces the required deliverable at `/app/output/itinerary.json`; a chat response is not a substitute for that file. Run the entrypoint once before completing the task. It reads the mounted public data at runtime, writes the artifact atomically, then validates the written JSON against the same public sources.

## Required execution

From the Skill package root, run:

```sh
python3 scripts/execute_task.py <<'JSON'
{}
JSON
```

Do not replace this with manually invented venue names. On success the command emits a JSON status object with `ok: true` and `output_path: "/app/output/itinerary.json"`. The artifact is already present at that path when the success object is emitted.

If it reports `ok: false`, inspect its public-data error rather than writing unsupported lodging or venues. A lodging is eligible only when its public policy/house-rules/amenity text contains explicit positive pet wording and contains no no-pets restriction.

To inspect an existing output independently, run:

```sh
python3 scripts/validate_itinerary.py <<'JSON'
{"path":"/app/output/itinerary.json","data_root":"/app/data"}
JSON
```

## Interfaces

All scripts receive one JSON object on stdin and write one JSON object on stdout.

- `scripts/execute_task.py` accepts optional overrides for `data_root`, `output_path`, `origin`, `target_state`, `start_date`, `end_date`, `party_size`, `budget`, `cuisines`, `days`, and `city_count`. Empty `{}` uses the current task requirements and must be used for the required output path.
- `scripts/build_itinerary.py` accepts the complete configuration with those fields and writes the configured output artifact.
- `scripts/validate_itinerary.py` accepts `{"path": string, "data_root": string}` and emits either `{"ok": true, "path": string}` or `{"ok": false, "error": string}`.

## Method

The builder discovers CSV columns at runtime, retains exact selected source names, and selects three Ohio cities only from cities that have explicitly pet-permitted accommodation records. It selects database restaurant records to cover American, Mediterranean, Chinese, and Italian cuisines and database attraction records for every day. The plan contains exactly seven sequential days, semicolon-terminated attraction lists, a visible Minneapolis self-driving departure, and no air-travel wording.

Pet status is determined from the accommodation record, not from a descriptive prefix added in the itinerary. The validator also resolves every named lodging, restaurant, and attraction back to a source record, checks every accommodation policy, checks cuisine coverage across the selected restaurant records, and checks the required JSON shape before reporting success.
