---
name: database-grounded-pet-road-itinerary
description: Build and validate the required seven-day, no-flight road itinerary from mounted travel CSVs. Use for travel tasks requiring traceable venues, cuisine coverage, and lodging whose database policy explicitly permits pets.
---

# Database-Grounded Pet Road Itinerary

Run the public-task entrypoint to create the required artifact:

```sh
python3 scripts/execute_task.py <<'JSON'
{}
JSON
```

It reads `/app/data`, writes `/app/output/itinerary.json` atomically, reloads the artifact, and validates it. A successful stdout result is `{"ok": true, ...}`. Do not treat an error result as a completed deliverable.

## Interfaces

Every script reads one JSON object from stdin and emits one JSON object on stdout.

- `scripts/execute_task.py`: accepts `{}` or optional public-task configuration overrides. It creates `/app/output/itinerary.json`.
- `scripts/build_itinerary.py`: accepts `data_root`, `output_path`, `origin`, `target_state`, `party_size`, `budget`, `cuisines`, `days`, and `city_count`; it writes the artifact.
- `scripts/validate_itinerary.py`: accepts `{"path":"/app/output/itinerary.json","data_root":"/app/data"}` and checks an already-written artifact.

To validate an existing file:

```sh
python3 scripts/validate_itinerary.py <<'JSON'
{"path":"/app/output/itinerary.json","data_root":"/app/data"}
JSON
```

## Method

The builder discovers headers and Ohio cities from the supplied files at runtime. It preserves database display names and uses the same normalized longest-name provenance rule as the public checks. It selects three Ohio cities with database restaurants and attractions, then assigns requested cuisines to actual scheduled city-days.

Pet permission is a hard constraint for every overnight entry. A lodging record is eligible only when policy-like source columns contain explicit positive evidence (`pet-friendly`, `pets allowed`, `pets welcome`, `allows pets`, `dogs allowed`, or `dog-friendly`) and no explicit no-pets restriction. Property titles and itinerary prose are never accepted as evidence.

The output always uses seven ordered day objects, a visible Minneapolis self-driving departure, no air-travel wording, source-grounded meals and attractions, and semicolon-terminated attraction lists. The post-write validator repeats schema, provenance, cuisine, origin, Ohio-city, transport, and pet-policy validation.
