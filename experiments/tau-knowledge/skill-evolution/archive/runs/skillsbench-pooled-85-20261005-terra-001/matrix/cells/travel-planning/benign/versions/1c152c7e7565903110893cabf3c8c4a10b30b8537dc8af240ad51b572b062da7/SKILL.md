---
name: database-grounded-pet-friendly-road-itinerary
description: Produce the required seven-day Minneapolis-to-Ohio, no-flight itinerary artifact from local CSV data, using only source-backed venues and accommodations with explicit positive pet permission.
---

# Database-Grounded Pet-Friendly Road Itinerary

This Skill creates the required artifact at `/app/output/itinerary.json`. The artifact is **not** created merely by reading this Skill: the executor must run the packaged entrypoint before completion.

## Required execution

Run this exact command from the package root after the supplied data is available at `/app/data`:

```sh
python3 scripts/execute_task.py <<'JSON'
{}
JSON
```

The entrypoint reads a JSON object from stdin, writes a JSON status object to stdout, and atomically writes `/app/output/itinerary.json` on success. Its default request is the public task: Minneapolis departure; March 17--23, 2022; two travelers; up to 5100 budget; three Ohio cities; American, Mediterranean, Chinese, and Italian cuisine coverage; and pets required.

Optional stdin overrides may use the same fields as `scripts/build_itinerary.py` (`data_root`, `output_path`, `origin`, `target_state`, `start_date`, `end_date`, `party_size`, `budget`, `cuisines`, `days`, `city_count`, and `pet_required`). For the current task, do not override the defaults.

A successful status has `"ok": true`. If it reports an error, do not invent an itinerary or claim completion; resolve the reported source-data constraint instead. The builder never publishes a partial artifact.

Then validate the written file:

```sh
python3 scripts/validate_itinerary.py <<'JSON'
{"path":"/app/output/itinerary.json"}
JSON
```

Completion requires both a successful build and a present, valid `/app/output/itinerary.json`.

## Builder contract

`scripts/build_itinerary.py` accepts one JSON object on stdin and emits either:

- `{"ok":true,"output_path":...,"chosen_cities":[...],"known_cost":...,"preference_coverage":...}`, or
- `{"ok":false,"error":"..."}`.

It discovers CSV schemas at runtime, reads only supplied local data, and uses source spellings in the output. It selects exactly three distinct cities supported by the supplied Ohio city/state reference and verifies directed local distance-matrix rows for the Minneapolis departure and inter-city driving legs. It does not use flight data.

Every restaurant and attraction printed in the itinerary is an exact source record name. Meals collectively cover each requested cuisine. Attractions are emitted as semicolon-separated source names ending with `;`.

Pet accommodation is a hard constraint: on every day, the selected source accommodation must have policy-like source text matching positive permission such as `pet-friendly`, `pets allowed`, `pets welcome`, `allows pets`, or `dog-friendly`; any `no pets`, `pets not allowed`, or equivalent contrary text rejects that record. Prefixing an unsupported accommodation name with “Pet-friendly” is never treated as evidence.

The builder requires numeric lodging and restaurant cost data, accommodation capacity for the party, and rejects a plan whose known lodging plus meal costs exceed the supplied budget. It writes precisely the required top-level `plan` and `tool_called` keys, with seven ordered day objects.

## Validator contract

`scripts/validate_itinerary.py` reads `{"path":"..."}` from stdin and emits `{"ok":true,"path":"..."}` or `{"ok":false,"error":"..."}`. It checks JSON shape, day ordering, required types, nonempty travel/lodging fields, no flight terminology in transportation, and final-semicolon attraction formatting. Source-grounding, pet policy, road links, cuisine coverage, and budget validation are performed by the builder before publication.
