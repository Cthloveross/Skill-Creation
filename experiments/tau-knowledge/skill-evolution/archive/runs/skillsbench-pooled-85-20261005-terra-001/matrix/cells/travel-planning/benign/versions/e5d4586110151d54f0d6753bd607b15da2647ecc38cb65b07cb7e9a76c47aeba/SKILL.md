---
name: database-grounded-pet-friendly-road-itinerary
description: Build the required seven-day, ground-only Minneapolis-to-Ohio itinerary from mounted CSV data, with traceable venues and accommodation records that explicitly permit pets. Use for travel-planning tasks requiring a JSON artifact at a fixed path.
---

# Database-Grounded Pet-Friendly Road Itinerary

This Skill creates the required deliverable file, not merely a prose itinerary. Execute it before completing the task:

```sh
python3 scripts/execute_task.py <<'JSON'
{}
JSON
```

The command reads the mounted public data at `/app/data`, writes `/app/output/itinerary.json` atomically, reloads the file, and validates it. Success is a JSON result containing `"ok": true`. If it returns `"ok": false`, the artifact was not successfully produced and the task is not complete.

## Input/output interfaces

All scripts read one JSON object from stdin and emit one JSON object on stdout.

- `scripts/execute_task.py`: accepts `{}` or configuration overrides, and uses the public task defaults otherwise.
- `scripts/build_itinerary.py`: accepts full configuration with `data_root`, `output_path`, `origin`, `target_state`, `party_size`, `budget`, `cuisines`, `days`, and `city_count`.
- `scripts/validate_itinerary.py`: accepts `{"path": "/app/output/itinerary.json", "data_root": "/app/data"}`.

Example validation after creation:

```sh
python3 scripts/validate_itinerary.py <<'JSON'
{"path":"/app/output/itinerary.json","data_root":"/app/data"}
JSON
```

## Method

The builder discovers CSV headers at runtime, derives requested-state cities from the supplied city/state reference, and selects three Ohio cities with documented attractions. It writes exactly seven ordered day records. The first day visibly self-drives from Minneapolis; no transportation string contains flight or air-travel language.

Every listed restaurant, attraction, and lodging name is copied from a source record. Restaurant choices collectively cover American, Mediterranean, Chinese, and Italian when those categories are available. Attraction lists are semicolon-separated and end with `;`.

Pet lodging is a hard constraint. The builder examines public columns whose names indicate a pet rule, policy, or amenity and accepts a lodging record only when its row contains an explicit positive permission such as `pets allowed`, `pets welcome`, or `pet-friendly`, with no contrary prohibition. It never treats a property name, an itinerary prefix, or missing house-rule text as evidence that pets are permitted. The same verified lodging record is used for each overnight field if no local Ohio record has documented pet permission.

The builder avoids expensive whole-table pairwise matching. It filters rows linearly, then performs the public longest-name traceability check only for the small set of selected records. It also rejects a candidate whose displayed name would resolve to a different source row.

The validator repeats schema, source traceability, explicit pet-policy, cuisine coverage, Ohio-city coverage, Minneapolis departure, ground-only transport, and attraction-format checks after serialization.
