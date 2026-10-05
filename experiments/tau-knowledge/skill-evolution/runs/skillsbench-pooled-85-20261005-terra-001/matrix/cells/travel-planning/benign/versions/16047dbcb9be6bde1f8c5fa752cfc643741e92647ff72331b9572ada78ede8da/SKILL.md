---
name: database-grounded-pet-friendly-road-itinerary
description: Build the required seven-day ground-only itinerary JSON from mounted travel CSVs. Use for Minneapolis departures, Ohio-city coverage, source-traceable restaurants and attractions, and lodging that has explicit positive pet permission in the accommodations data.
---

# Database-Grounded Pet-Friendly Road Itinerary

This Skill creates the required artifact; a textual response is not a substitute. It reads the public CSV files at runtime, chooses only source-record names, and writes `/app/output/itinerary.json` atomically.

## Required execution

From the Skill package root, run this entrypoint before completing the task:

```sh
python3 scripts/execute_task.py <<'JSON'
{}
JSON
```

A successful stdout result has `"ok": true` and `"output_path": "/app/output/itinerary.json"`. Do not complete the task if it reports an error. The entrypoint creates `/app/output` when necessary, writes the JSON artifact, reloads it, and validates it against the mounted sources.

To validate a pre-existing artifact separately:

```sh
python3 scripts/validate_itinerary.py <<'JSON'
{"path":"/app/output/itinerary.json","data_root":"/app/data"}
JSON
```

## Script interfaces

All scripts consume exactly one JSON object on stdin and emit one JSON object on stdout.

- `scripts/execute_task.py`: accepts optional overrides for `data_root`, `output_path`, `origin`, `target_state`, `party_size`, `budget`, `cuisines`, `days`, and `city_count`. `{}` uses the public task defaults.
- `scripts/build_itinerary.py`: accepts the complete configuration and writes its configured output path.
- `scripts/validate_itinerary.py`: accepts `{"path": string, "data_root": string}` and reports whether the file satisfies the source-grounding and output checks.

## Selection and validation method

The builder discovers CSV columns instead of assuming their capitalization. It derives Ohio city names from the supplied city/state reference using the same normalized whole-name matching used for source records. It visibly routes from Minneapolis through three distinct derived Ohio cities by self-driving and never emits air-travel wording.

Every restaurant and attraction output is a source name. Restaurants selected over the seven days cover American, Mediterranean, Chinese, and Italian based on the cuisine field, and each attraction field is semicolon-terminated. Lodging selection is stricter: policy, amenity, and house-rule text must match a positive pet-permission expression and must not contain a contrary no-pets expression. The builder verifies that the selected accommodation text resolves back to that same pet-permitted source record; adding a "pet-friendly" label to an unsupported property is never used as evidence.

Pet-permitted lodging is preferred in each routed Ohio city. If a routed city has no explicitly pet-permitted source lodging, the builder uses another explicitly pet-permitted source property rather than falsely treating missing policy text as permission. This preserves the hard pet-policy requirement while retaining all three Ohio cities in the road route.
