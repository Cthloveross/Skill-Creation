---
name: database-grounded-pet-friendly-road-itinerary
description: Create and validate the required seven-day, ground-only Minneapolis-to-Ohio itinerary from the mounted travel CSVs. Use when all listed venues must be traceable to public records and every lodging selection needs explicit database evidence that pets are permitted.
---

# Database-Grounded Pet-Friendly Road Itinerary

This Skill writes the required artifact at `/app/output/itinerary.json`; a prose response is not a substitute.

## Execute

From the package root, run the task entrypoint before completing the task:

```sh
python3 scripts/execute_task.py <<'JSON'
{}
JSON
```

It creates `/app/output` as needed, writes the itinerary atomically, reloads it, and validates it. A successful result is JSON with `"ok": true` and the output path. Treat an `"ok": false` result as a failure requiring correction, not as a completed deliverable.

To check an already-created artifact:

```sh
python3 scripts/validate_itinerary.py <<'JSON'
{"path":"/app/output/itinerary.json","data_root":"/app/data"}
JSON
```

## Interfaces

Each script reads one JSON object from stdin and writes one JSON object to stdout.

- `scripts/execute_task.py` accepts optional configuration overrides. `{}` uses the public task defaults.
- `scripts/build_itinerary.py` accepts the full configuration: `data_root`, `output_path`, `origin`, `target_state`, `party_size`, `budget`, `cuisines`, `days`, and `city_count`.
- `scripts/validate_itinerary.py` accepts `{"path": string, "data_root": string}`.

## Method and hard checks

The builder discovers CSV columns at runtime and derives Ohio city names from the mounted city/state reference. It outputs seven sequential days, visibly begins by self-driving from Minneapolis, and does not emit flight language. Restaurant, attraction, and accommodation labels always come from source records; attractions are semicolon-delimited and terminated.

Pet policy is a hard constraint. The builder uses the exact policy-related columns that the public accommodation data exposes, accepts only an explicit positive pet-permission expression, rejects negative pet restrictions, and makes identity-safe source selections. In particular, it does not infer permission from a property name such as “dog-friendly,” from text added to the itinerary, or from an absent rule. It also rejects duplicate/shadowed records when the public longest-name resolver would resolve the displayed label to another row.

The validator repeats the source-traceability, policy, schema, cuisine, Ohio-city, and ground-travel checks after serialization. If an Ohio stop lacks locally documented pet lodging, the itinerary retains the pet-permitted source property rather than falsely claiming an unsupported local property is pet-friendly.
