---
name: database_travel_itinerary
version: 1.0.0
description: Build and validate a fixed-length, no-flight road-trip itinerary from supplied travel CSV databases. Use when a task requires source-grounded cities, pet-friendly lodging, restaurants, attractions, and a JSON itinerary artifact.
---

# Database-grounded itinerary builder

Use this Skill instead of inventing POIs, lodging, routes, or cuisine claims. It inspects the CSV headers and records at runtime, selects only records in the requested state, verifies pet policy and capacity where those fields are available, and writes the required JSON artifact.

## Runtime inputs

`scripts/build_itinerary.py` reads one JSON object from stdin. Its schema is:

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

`data_root` must contain the public task's `accommodations/`, `restaurants/`, `attractions/`, `background/`, and (when route validation is wanted) `googleDistanceMatrix/` directories. The script emits a JSON execution report to stdout and writes the itinerary to `output`. It exits nonzero rather than silently making up records when a hard constraint cannot be supported.

## Execution procedure

1. Translate the request into the JSON above. Do not pass flight data: this planner is intentionally road-only.
2. Run the script, for example:

   ```sh
   python3 /app/environment/skills/current/scripts/build_itinerary.py <<'JSON'
   {"origin":"Minneapolis","state":"Ohio","city_count":3,"days":7,"party_size":2,"budget":5100,"pets":true,"cuisines":["American","Mediterranean","Chinese","Italian"],"data_root":"/app/data","output":"/app/output/itinerary.json"}
   JSON
   ```

3. Inspect the JSON report. A successful report names selected cities, source CSVs, estimated known cost, and any unknown-cost count.
4. Mechanically validate the generated artifact with `scripts/validate_itinerary.py`, supplying the same configuration. Do not hand-edit selected names, because that would lose database provenance.

The generated `tool_called` reports the database search capabilities actually used. The plan has exactly the requested number of day objects, sequential day numbers, road-only transportation, three meal fields, semicolon-terminated attraction strings, and pet-friendly accommodations selected from the lodging data.

## Constraint interpretation

A policy is pet-friendly only when its source text positively permits pets and does not contain a negated pet restriction. Missing policy text is not treated as permission. If a capacity field can be identified, it must cover the entire party. Restaurant cuisine matching is performed against the cuisine/category field, not against the restaurant name. A route uses a source distance-matrix edge when a matching directed edge exists; if the matrix does not expose a usable city-level schema, the report explicitly identifies that it could not be checked rather than claiming a route lookup.

Known lodging and restaurant costs are conservatively summed when recognizable price columns exist. The candidate must remain at or below `budget` using known costs. Missing prices remain unknown and are reported, not converted to zero.
