---
name: database-grounded-travel-itinerary
description: Build a multi-day, multi-city travel itinerary strictly from the supplied TravelPlanner-style CSV databases (accommodations, restaurants, attractions, distance matrix, city/state lists). Use when a request asks for an N-day itinerary from an origin, covering K cities in a given state/region, with hard constraints (dates, party size, pet-friendly lodging, no flights / self-driving, budget) and cuisine preferences, and requires a JSON file with a per-day `plan` array plus a `tool_called` list. Discovers CSV schema at runtime, validates every entity against source records, builds a cost ledger, and writes the itinerary JSON.
---

# Database-Grounded Travel Itinerary Planning

## What this Skill does
Given a natural-language travel request plus a directory of structured CSV data, it:
1. parses the request into hard constraints and preferences (you supply these as a small params JSON derived from the current instruction);
2. discovers the actual column layout of each CSV at runtime (no fixed column names assumed);
3. selects K cities in the requested state that have pet-friendly lodging, restaurants and attractions, and valid driving legs;
4. builds a day-by-day plan (travel days use `"from A to B"`, self-driving only, no flights);
5. assigns distinct restaurants (covering the preferred cuisines when possible), distinct attractions, and pet-friendly accommodations;
6. computes a cost ledger (lodging by night, meals by party, driving by leg) and checks it against the budget;
7. writes the required JSON to the output path and prints a machine-readable validation summary.

It never uses POIs from memory: every named entity resolves to a row in the supplied CSVs.

## When to use / assumptions
- Route pattern produced is: origin -> city1 -> city2 -> ... -> cityK -> origin, with 2 nights per city, giving `2*K + 1` days. For this task K=3 gives exactly 7 days. If `days != 2*K+1` the generator pads/trims stay days in the last city to hit the required day count.
- "No flights" => every transition is `Self-driving: from A to B`; flights CSV is never read.
- "Pet-friendly" => accommodation `house_rules` must NOT contain `no pets` (case-insensitive).
- Party capacity => accommodation `maximum occupancy >= people`; minimum-nights must be `<= nights booked` (2).
- Cuisine list is a *preference*: covered across the trip when the data allows, never a hard reject.

## Files
- `scripts/travel_db.py` — reusable loaders/queries (schema discovery, filtering, distance lookup, cost formulas).
- `scripts/plan_itinerary.py` — end-to-end entrypoint: reads params JSON on stdin, writes the itinerary file, prints a validation summary JSON on stdout.
- `scripts/search_cities.py`, `scripts/search_accommodations.py`, `scripts/search_restaurants.py`, `scripts/search_attractions.py`, `scripts/search_distance_matrix.py` — thin stdin/stdout query tools over the same helper (useful for inspection and to honor the "use skills to search the database" rule).
- `references/field-notes.md` — notes on the dataset conventions and cost model.

## How the executor runs it

1. Read the current instruction and build a params JSON. For the present task this is:

```bash
cat > /tmp/params.json <<'JSON'
{
  "data_root": "/app/data",
  "output_path": "/app/output/itinerary.json",
  "origin": "Minneapolis",
  "state": "Ohio",
  "num_cities": 3,
  "days": 7,
  "people": 2,
  "budget": 5100,
  "cuisines": ["American", "Mediterranean", "Chinese", "Italian"],
  "pet_friendly": true,
  "no_flights": true
}
JSON
cat /tmp/params.json | python3 /app/environment/skills/current/scripts/plan_itinerary.py
```

   Always set `origin`, `state`, `num_cities`, `days`, `people`, `budget`, `cuisines` from the *current* instruction — do not rely on the example values if the instruction differs.

2. Inspect the printed summary. It is JSON with keys: `ok`, `output_path`, `cities`, `route_legs`, `legs_valid`, `cost` (ledger with `accommodation`, `meals`, `driving`, `total`), `budget`, `within_budget`, `cuisines_requested`, `cuisines_covered`, `cuisines_missing`, `warnings`. Treat `legs_valid=false`, `within_budget=false`, or non-empty `warnings` as problems to fix before trusting the file.

3. Verify the file independently (always re-run the entrypoint rather than trusting a stale file):
```bash
python3 - <<'PY'
import json
d=json.load(open('/app/output/itinerary.json'))
assert set(d)>={'plan','tool_called'}
assert len(d['plan'])==7
for day in d['plan']:
    for k in ['day','current_city','transportation','breakfast','lunch','dinner','attraction','accommodation']:
        assert k in day, k
    assert 'flight' not in day['transportation'].lower()
print('format OK', len(d['plan']))
PY
```

4. If a requirement cannot be satisfied from the data (e.g. no valid self-driving leg, or no pet-friendly lodging in a chosen city), the generator records it in `warnings` and avoids that city; if it still cannot, it emits `"-"` for the unsatisfiable field rather than inventing a record. Report such gaps honestly; do not fabricate entities.

## Params schema (stdin to plan_itinerary.py)
- `data_root` (str): root of the CSV tree (default `/app/data`).
- `output_path` (str): where to write the JSON (default `/app/output/itinerary.json`).
- `origin` (str, required): starting city.
- `state` (str, required): state whose cities must be covered.
- `num_cities` (int, required): how many cities to cover.
- `days` (int, required): total day objects to emit.
- `people` (int): party size (default 2).
- `budget` (number): ceiling (default large).
- `cuisines` (list[str]): preferred cuisines.
- `pet_friendly` (bool), `no_flights` (bool).

## Output contract (written file)
Top-level `plan` (exactly `days` objects) and `tool_called` (list of search skill names used). Each day object has `day`, `current_city` (`City` on stay days, `from A to B` on travel days), `transportation` (`Self-driving: from A to B`, or `-`), `breakfast`/`lunch`/`dinner` (`Name, City` or `-`), `attraction` (`Name1;Name2;` or `-`), `accommodation` (source NAME, or `-`).
