---
name: database-grounded-pet-friendly-road-itinerary
description: Build and validate the required seven-day road-trip itinerary JSON from mounted travel datasets. Use for travel deliverables requiring database-traceable venues, explicit pet-permitted lodging, cuisine coverage, and a fixed output path.
---

# Database-Grounded Pet-Friendly Road Itinerary

Run the public-task entrypoint before completing the task:

```sh
python3 scripts/execute_task.py <<'JSON'
{}
JSON
```

It reads the mounted CSVs under `/app/data`, writes `/app/output/itinerary.json` atomically, reloads the artifact, and validates it. A successful result is a JSON object containing `"ok": true`. Treat a nonzero exit or `"ok": false` as incomplete rather than claiming a deliverable was produced.

## Interfaces

Every script receives one JSON object on stdin and emits one JSON object on stdout.

- `scripts/execute_task.py`: accepts `{}` or overrides for the public defaults. It creates `/app/output/itinerary.json` by default.
- `scripts/build_itinerary.py`: accepts `data_root`, `output_path`, `origin`, `target_state`, `party_size`, `budget`, `cuisines`, `days`, and `city_count`.
- `scripts/validate_itinerary.py`: accepts `{"path":"/app/output/itinerary.json","data_root":"/app/data"}` and validates an existing artifact.

To validate an already-created deliverable:

```sh
python3 scripts/validate_itinerary.py <<'JSON'
{"path":"/app/output/itinerary.json","data_root":"/app/data"}
JSON
```

## Method

The builder discovers source headers at runtime and derives target-state cities from the supplied city/state reference. It requires every selected city to have source-grounded restaurants, attractions, and at least one lodging candidate whose **verifier-resolved public record** has explicit positive pet permission.

Pet permission is a hard constraint. The builder and validator use the public positive and negative policy expressions against policy-like fields (pet, rule, policy, or amenity columns). They never infer permission from a listing title, itinerary wording, or missing information. Before accepting a lodging name, they resolve it with the same longest-source-name behavior used for provenance checks and inspect that exact resolved row. This also handles duplicate or overlapping listing names safely.

The output contains seven ordered day objects, only self-driving transportation, Minneapolis departure, three selected Ohio cities, traceable meals and attractions, semicolon-terminated attraction strings, and requested cuisine coverage. Lodging, restaurants, and attractions are selected in the scheduled city. The validator repeats structural, provenance, policy, route-text, cuisine, and formatting checks after serialization.
