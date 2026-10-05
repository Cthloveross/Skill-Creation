---
name: database-grounded-pet-friendly-road-itinerary
description: Create the required seven-day no-flight itinerary JSON from supplied local travel CSVs, with three source-backed target-state cities, source-backed venues, and explicitly pet-permitted lodging.
---

# Database-Grounded Pet-Friendly Road Itinerary

Use `scripts/build_itinerary.py` to inspect the supplied CSV schemas at runtime and write the itinerary artifact. It uses only local data and the Python standard library; it never uses flight data or memory-based POIs.

## Input and invocation

The builder reads one JSON object from stdin and writes a JSON status object to stdout. Required input fields are:

- `data_root`: supplied travel-data directory;
- `output_path`: destination JSON file;
- `origin`: departure city;
- `target_state`: state containing the three visit cities;
- `start_date`, `end_date`: inclusive ISO dates;
- `party_size`: positive integer;
- `budget`: positive number;
- `cuisines`: nonempty ordered array of requested cuisine labels.

Optional `days` and `city_count` both default to 7 and 3 respectively, but this Skill supports only the required seven-day/three-city artifact. `pet_required` is accepted only as `true`: this task requires pet accommodations and the builder deliberately refuses to weaken that hard constraint.

```sh
python3 scripts/build_itinerary.py <<'JSON'
{"data_root":"/app/data","output_path":"/app/output/itinerary.json","origin":"Minneapolis","target_state":"Ohio","start_date":"2022-03-17","end_date":"2022-03-23","party_size":2,"budget":5100,"cuisines":["American","Mediterranean","Chinese","Italian"],"pet_required":true}
JSON
```

On success the status includes `ok`, `output_path`, selected cities, known cost, and cuisine coverage. The itinerary itself is written only to `output_path` atomically.

## Method and hard checks

1. The builder discovers the accommodation, restaurant, attraction, and distance CSVs from names and headers, then detects columns from normalized runtime headers.
2. It establishes target-state city membership from the supplied city/state reference text or an explicitly state-qualified source location.
3. Every usable accommodation must have a numeric price, capacity for the full party, and explicit positive pet evidence in a policy, rules, pet, or amenity column. It rejects any record with `no pets`, `pets not allowed`, or equivalent negative evidence. Output wording cannot make an unsupported property pet-friendly.
4. It selects three distinct eligible cities and requires directed source distance rows for the Minneapolis-to-first-city and both inter-city self-driving legs.
5. Restaurants and attractions are selected by their exact source names. A feasible route must collectively cover every requested cuisine; each attraction string is semicolon-delimited and ends in `;`.
6. It accounts for one lodging night per day and each selected meal for the party, rejects plans above the budget, and writes exactly `plan` and `tool_called` at the top level.

If data cannot prove any hard requirement, including explicit positive pet permission for **every** selected lodging day, the builder returns an error and does not publish a partial file.

## Validation

```sh
python3 scripts/validate_itinerary.py <<'JSON'
{"path":"/app/output/itinerary.json"}
JSON
```

The validator checks the public JSON structure, seven ordered days, required field types, semicolon attraction syntax, and lack of flight language. The builder additionally validates all selected lodging records against their source policy text before writing the artifact.
