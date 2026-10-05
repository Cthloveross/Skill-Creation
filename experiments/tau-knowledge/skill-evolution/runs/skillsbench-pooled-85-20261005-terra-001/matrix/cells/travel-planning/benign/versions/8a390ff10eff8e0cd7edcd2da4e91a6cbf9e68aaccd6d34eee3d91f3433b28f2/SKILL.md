---
name: database-grounded-road-itinerary
description: Build and validate the required seven-day, three-city, no-flight road itinerary JSON from supplied travel CSV files. Use when lodging, restaurant, attraction, city/state, and road-distance data must be selected from local data rather than memory.
---

# Database-Grounded Road Itinerary

Use `scripts/build_itinerary.py` to discover the supplied CSV schemas at runtime, select a route and source-backed records, and write the required artifact. It uses only the Python standard library and does not use flight data.

## Build input

Pass one JSON object on stdin. Required fields are:

- `data_root`: directory containing the supplied travel data;
- `output_path`: destination for the JSON artifact;
- `origin`: departure city;
- `target_state`: state containing the destination cities;
- `start_date` and `end_date`: ISO dates, inclusive;
- `party_size`: positive integer;
- `budget`: positive number;
- `cuisines`: ordered preferred cuisine labels.

Optional fields are `days` (defaults to 7), `city_count` (defaults to 3), `pet_required` (defaults to `true`), `lodging_price_unit` (defaults to `per_night`), `meal_price_unit` (defaults to `per_person`), and `strict_preferences` (defaults to `false`). The date span, `days`, and `city_count` must be 7, 7, and 3 because that is the artifact contract for this task.

A runnable invocation has the form:

```sh
python3 scripts/build_itinerary.py <<'JSON'
{"data_root":"<supplied-data-root>","output_path":"<required-output-path>","origin":"<origin>","target_state":"<state>","start_date":"<YYYY-MM-DD>","end_date":"<YYYY-MM-DD>","party_size":<positive-integer>,"budget":<positive-number>,"cuisines":["<cuisine>","<cuisine>"]}
JSON
```

The script emits a JSON status object on stdout and atomically creates the requested artifact only after structural validation succeeds.

## Selection method

1. The script inventories CSVs under `data_root` and identifies accommodations, restaurants, attractions, and road-distance data by runtime filenames and headers. It detects relevant columns from normalized header names rather than assuming a fixed capitalization or CSV layout.
2. It reads the supplied city/state reference text when present. A target city is accepted only when its source location explicitly includes the target state or is corroborated by that reference.
3. Lodging is accepted only with explicit pet permission, a known numeric nightly price, and a known capacity sufficient for the party. A negated pet policy is never treated as permission.
4. It finds cities with source-backed lodging, restaurants, and attractions; evaluates ordered three-city routes; and requires directed distance-matrix rows for the origin-to-first-city and each inter-city leg. It never substitutes a reverse route.
5. It schedules seven days as arrival, stay, transfer, stay, transfer, stay, stay. It selects attraction and meal names from the source rows, cycles requested cuisine labels when matching categories are available, uses only self-driving transportation text, and calculates known lodging and per-person meal costs. It rejects plans above the supplied budget.
6. The artifact contains exactly `plan` and `tool_called`. `tool_called` truthfully records the database-search stages performed by this script: city, accommodation, restaurant, attraction, and distance-matrix searches.

`lodging_price_unit=per_night` and `meal_price_unit=per_person` are explicit accounting assumptions. If the discovered data documents incompatible units, supply the correct supported unit values; unsupported units cause a failure rather than an invented conversion.

## Failure handling

The builder fails with a JSON error and does not write a partial itinerary when a required data class is absent, target-state membership cannot be verified, pet/capacity/price evidence is missing, a directed road leg is absent, or no route fits the budget. With `strict_preferences=true`, it also fails unless all requested cuisine labels occur in the selected route's restaurant data. With the default false setting, cuisine coverage is optimized but a missing preference is not converted into a hard constraint.

## Validation

Validate a produced artifact independently with `scripts/validate_itinerary.py`:

```sh
python3 scripts/validate_itinerary.py <<'JSON'
{"path":"<required-output-path>"}
JSON
```

It checks JSON parsing, exact top-level keys, seven sequential integer day numbers, required string fields, semicolon-terminated attraction strings, and absence of flight transportation. The builder performs this validation before publishing its output.
