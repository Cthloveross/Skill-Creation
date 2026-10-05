---
name: database-grounded-pet-friendly-road-itinerary
description: Create and validate the required seven-day Minneapolis-to-Ohio no-flight itinerary JSON using only supplied local travel CSV records, with traceable restaurants, attractions, and explicitly pet-permitted lodging.
---

# Database-Grounded Pet-Friendly Road Itinerary

Use this Skill for the supplied travel-planning task. The required deliverable is not the console response: it is `/app/output/itinerary.json`. **Run the entrypoint below before completing the task.** It reads the public databases, writes the artifact atomically, and validates it.

## Required execution

From the package root, with the public data mounted at `/app/data`, run:

```sh
python3 scripts/execute_task.py <<'JSON'
{}
JSON
```

The entrypoint consumes one JSON object from stdin and emits one JSON status object to stdout. With `{}`, it uses the current public request and creates `/app/output/itinerary.json`. A successful result has `"ok": true`. If it returns `"ok": false`, do not claim that an itinerary was produced: inspect the reported unavailable constraint instead of inventing venue or pet-policy data.

Optionally run the validator independently after creation:

```sh
python3 scripts/validate_itinerary.py <<'JSON'
{"path":"/app/output/itinerary.json","data_root":"/app/data"}
JSON
```

## Entrypoint input/output

`execute_task.py` accepts an optional override object. Supported keys are `data_root`, `output_path`, `origin`, `target_state`, `start_date`, `end_date`, `party_size`, `budget`, `cuisines`, `days`, `city_count`, and `pet_required`. Defaults exactly implement the current request: Minneapolis departure; March 17–23, 2022; two travelers; $5,100; three Ohio cities; American, Mediterranean, Chinese, and Italian cuisine coverage; no flights; and pets required.

It returns either:

- `{"ok": true, "output_path": "/app/output/itinerary.json", "chosen_cities": [...], "known_cost": number|null}`, or
- `{"ok": false, "error": "..."}`.

`validate_itinerary.py` accepts `{"path": string, "data_root": string}` and emits `{"ok":true,...}` or a JSON error object.

## Selection method

The builder discovers CSV columns at runtime rather than assuming a fixed schema. It derives target-state city names from the supplied city/state reference, searches accommodations, restaurants, attractions, and the driving matrix, and preserves selected database names in the artifact.

A lodging record is eligible only when its policy-like fields contain explicit positive evidence such as `pet-friendly`, `pets allowed`, `pets welcome`, `allows pets`, or `dog-friendly`, and contain no contrary no-pets restriction. It also checks the same longest-name matching behavior used for output traceability, so adding a descriptive prefix cannot cause an output lodging label to resolve to a different non-pet-friendly property.

Every plan contains exactly seven ordered days. Transportation uses self-driving only. Restaurant selections are database records whose recorded cuisine values collectively cover all requested cuisines. Each attraction field contains one or more source attraction names separated by semicolons and ends in a semicolon. The builder uses known nightly and meal costs where discoverable and rejects a fully-known plan over budget. It fails explicitly when the public data cannot support a hard requirement.
