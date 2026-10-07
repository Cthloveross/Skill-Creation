---
name: database-grounded-pet-friendly-road-itinerary
description: Build the required seven-day no-flight road itinerary artifact from supplied local travel CSVs, selecting traceable attractions, restaurants, and lodging whose public policy text explicitly permits pets.
---

# Database-Grounded Pet-Friendly Road Itinerary

Use this Skill when a local travel-data task requires a JSON itinerary rather than an itinerary written from memory. It discovers the supplied CSV schema at runtime and creates `/app/output/itinerary.json` for the current Minneapolis-to-Ohio request.

## Execute

From the package root, with the public files available under `/app/data`, run:

```sh
python3 scripts/execute_task.py <<'JSON'
{}
JSON
```

The script reads a JSON object from stdin and emits one JSON status object to stdout. On success it atomically creates `/app/output/itinerary.json` and returns `{"ok":true,...}`. It must be run before completion; this package itself does not create the task artifact.

Then validate the artifact:

```sh
python3 scripts/validate_itinerary.py <<'JSON'
{"path":"/app/output/itinerary.json","data_root":"/app/data"}
JSON
```

Do not claim success if either command reports `"ok": false`.

## Entrypoint schema

`execute_task.py` accepts optional overrides for `data_root`, `output_path`, `origin`, `target_state`, `start_date`, `end_date`, `party_size`, `budget`, `cuisines`, `days`, `city_count`, and `pet_required`. With `{}`, it uses the public request exactly: seven inclusive days from 2022-03-17 through 2022-03-23, Minneapolis departure, three Ohio cities, two travelers, $5100 budget, four requested cuisines, no flights, and pets required.

`build_itinerary.py` accepts the complete version of that object and returns either:

- `{"ok":true,"output_path":...,"chosen_cities":[...],"known_cost":...}`, or
- `{"ok":false,"error":"..."}`.

`validate_itinerary.py` accepts `{"path":"...","data_root":"..."}` and returns `{"ok":true,...}` or an error object.

## Method and safeguards

The builder reads only local supplied files. It identifies Ohio city spellings by comparing dataset city values with the supplied city/state reference, extracts explicitly positive pet policy evidence only from accommodation policy-like columns, and rejects any policy containing a contrary no-pets restriction. It mirrors source-name matching when selecting records so an output label cannot accidentally resolve to a longer, non-pet-friendly database property.

All printed lodging, restaurant, and attraction names are source record names. Restaurant selections collectively cover American, Mediterranean, Chinese, and Italian source cuisine values. Attractions are source names separated with semicolons and terminated with a semicolon. The plan has exactly seven ordered day objects and only ground self-driving transportation. When usable distance-matrix origin/destination columns are present, routes with represented Minneapolis and inter-city driving legs are preferred. Numeric lodging and meal data, if discoverable, are used to prefer lower known cost and to reject a fully-known plan over budget.

If fewer than three distinct Ohio cities with positively pet-permitted, traceable lodging exist, or a needed source category is unavailable, the builder fails rather than fabricating an unsupported itinerary.
