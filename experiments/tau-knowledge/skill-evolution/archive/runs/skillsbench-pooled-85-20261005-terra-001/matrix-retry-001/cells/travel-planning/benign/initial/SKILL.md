---
name: database-grounded-road-itinerary
version: 1.0.0
description: Build and validate a budgeted, pet-friendly, multi-city road itinerary from supplied CSV travel databases. Use when the task requires a JSON itinerary whose lodging, restaurants, attractions, cities, and driving legs must be grounded in local data rather than memory.
---

# Database-Grounded Road Itinerary

Use `scripts/build_itinerary.py` to inspect the supplied CSV schemas at runtime, select source-backed entities, and write the required itinerary JSON. It never uses flights and does not query a network service.

## Preconditions

The data root must contain CSVs for accommodations, restaurants, attractions, and a road distance matrix. The script discovers columns rather than relying on a fixed CSV schema. A feasible result requires:

- the requested number of distinct cities in the requested state with source-backed pet-permitted lodging, restaurants, and attractions;
- explicitly pet-permitted lodging with known nightly price, capacity for the full party, and a compatible minimum stay when that field is present;
- represented directed road-matrix legs from the origin through the selected cities;
- source-backed restaurants with known prices; and
- a route whose computed lodging and meals ledger is within the budget.

Unknown pet policies, unknown prices, and missing route legs are not treated as satisfying hard requirements. The script emits a JSON error rather than inventing an itinerary when a hard prerequisite is absent.

## Input and execution

The script reads one JSON object from stdin and emits a JSON status object to stdout. Required input keys are:

- `data_root`: root directory containing the supplied travel data;
- `output_path`: desired itinerary JSON path;
- `origin`: starting city;
- `state`: requested state;
- `days`, `city_count`, `party_size`, and `budget`;
- `cuisines`: preferred cuisine labels, in priority/rotation order.

Optional keys:

- `state_aliases`: representations found in the data, such as a full state name and abbreviation;
- `origin_aliases`: alternate origin spellings represented by the distance matrix;
- `pet_required` (defaults to `true`);
- `dataset_paths`: object overriding discovered file paths with `accommodations`, `restaurants`, `attractions`, and `distance` keys; and
- `tool_called`: replacement list for the output provenance labels.

For a seven-day, three-city task, supply `days: 7` and `city_count: 3`. The script allocates days 1--2, 3--4, and 5--7 to the three destination cities, with driving transitions on days 1, 3, and 5. It does not silently add a return trip because return requirements vary by task.

Example invocation (values must come from the current task):

```bash
python3 scripts/build_itinerary.py <<'JSON'
{"data_root":"/app/data","output_path":"/app/output/itinerary.json","origin":"<origin>","state":"<state>","state_aliases":["<state>","<state abbreviation>"],"days":7,"city_count":3,"party_size":2,"budget":<budget>,"pet_required":true,"cuisines":["American","Mediterranean","Chinese","Italian"]}
JSON
```

On success stdout has `{"ok": true, "output_path": ..., "estimated_total": ..., "cuisine_coverage": [...]}`. The output file has exactly the task contract's top-level `plan` and `tool_called` keys. On failure stdout has `ok: false`, an explanatory `error`, and no success claim.

## Method and validation

The helper resolves likely name, city, price, capacity, policy, cuisine, and route endpoint fields from actual headers. It identifies requested-state cities from explicit state data or the supplied city/state reference file, requires a directed road edge for each transition, ranks feasible routes by preferred-cuisine coverage and cost, and keeps a ledger using nightly lodging plus restaurant price times party size. Preferred cuisines are optimized but remain preferences: when a city has no restaurant in the requested rotation category, another source-backed restaurant is used and the reduced coverage is reported.

Before writing, it validates the exact seven-day-style object shape, integer sequential day numbers, non-flight transportation text, semicolon-terminated nonempty attraction fields, pet-policy evidence, source membership of every named entity, route edges, and budget. The executor should inspect the status JSON and use only the generated file on success; it must not replace missing records with remembered POIs or claim a failed search succeeded.
