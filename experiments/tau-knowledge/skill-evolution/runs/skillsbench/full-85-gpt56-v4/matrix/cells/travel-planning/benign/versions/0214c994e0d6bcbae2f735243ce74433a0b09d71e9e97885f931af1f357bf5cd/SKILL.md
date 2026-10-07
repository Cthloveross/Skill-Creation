---
name: database_travel_itinerary
version: 1.1.0
description: Build and validate a fixed-length road-trip itinerary from supplied travel CSVs, including requested-state cities, lodging policy and capacity, restaurant cuisines, attractions, budget, and directed driving links. Use for source-grounded JSON travel-itinerary artifact tasks.
---

# Database-grounded itinerary builder

Use this Skill when the task supplies travel CSVs and requires an itinerary artifact. It reads the supplied data at runtime; it does not invent POIs, lodgings, cuisines, or routes. The generated plan is road-only and reports the data-search capabilities used in `tool_called`.

## Input and execution

`scripts/build_itinerary.py` accepts one JSON object on stdin:

```json
{
  "origin": "origin city",
  "state": "destination state",
  "city_count": 3,
  "days": 7,
  "party_size": 2,
  "budget": 5100,
  "pets": true,
  "cuisines": ["American", "Mediterranean", "Chinese", "Italian"],
  "data_root": "/app/data",
  "output": "/app/output/itinerary.json"
}
```

`data_root` must contain `accommodations/clean_accommodations_2022.csv`, `restaurants/clean_restaurant_2022.csv`, `attractions/attractions.csv`, `background/citySet_with_states.txt`, and, when directed route validation is required, `googleDistanceMatrix/distance.csv`. It writes the artifact to `output` and emits a JSON report to stdout with selected cities, known cost, unknown-cost count, and source paths. It exits nonzero with a JSON `error` if no source-supported itinerary meets a hard constraint.

For example:

```sh
python3 /app/environment/skills/current/scripts/build_itinerary.py <<'JSON'
{"origin":"Minneapolis","state":"Ohio","city_count":3,"days":7,"party_size":2,"budget":5100,"pets":true,"cuisines":["American","Mediterranean","Chinese","Italian"],"data_root":"/app/data","output":"/app/output/itinerary.json"}
JSON
python3 /app/environment/skills/current/scripts/validate_itinerary.py <<'JSON'
{"output":"/app/output/itinerary.json","days":7}
JSON
```

## Selection method and assumptions

1. Read headers rather than assuming a particular CSV capitalization. Restrict destination cities using the supplied state/city mapping.
2. Require every selected city to have an attraction and at least one restaurant whose *cuisine/category field* matches each requested cuisine. Names are never used as cuisine evidence.
3. For a pet request, exclude a lodging only if its supplied house-rule field explicitly prohibits pets, and require capacity when a capacity value is present. This dataset represents pet restrictions with phrases such as `No pets`; a blank rule has no recorded prohibition, not an asserted amenity. If the task requires affirmative pet permission rather than this restriction-based convention, do not use this inference: stop with an unsupported-policy error or obtain a data source with a positive policy field.
4. Allocate consecutive days across exactly the requested number of cities, check each lodging's minimum stay against its city allocation, and require each directed origin-to-city and city-to-city driving edge when the matrix has recognizable endpoints. No flight records are read or emitted.
5. Select a deterministic affordable route and source records. Known lodging prices and meal prices (multiplied by party size) are summed; missing prices remain visible as unknown rather than zero. The script refuses a known total above the budget.

The artifact has exactly `days` sequential day objects with the requested keys, transition strings for driving days, source restaurant and attraction names, semicolon-terminated attraction strings, and a `Pet-friendly` label when `pets` is true. It intentionally does not add fields that a task's output schema did not request.

## Validation and failure handling

Run `validate_itinerary.py` after building. It reads `{ "output": "...", "days": N }` from stdin and emits `{ "valid": true, "errors": [] }` or `{ "valid": false, "errors": [...] }`. It checks the required top-level/day keys, day ordering, string types, road-only transport labels, semicolon termination, and lodging labels. A successful structural validation complements—not replaces—the builder's database filtering and cost/route checks.

Do not hand-edit selected names after generation: rerun the builder after changing constraints so source provenance and validation remain aligned. If CSV records, state mapping, route edges, policy/capacity data, or required cuisine coverage are absent, report the builder error instead of substituting memory-based places or a flight.
