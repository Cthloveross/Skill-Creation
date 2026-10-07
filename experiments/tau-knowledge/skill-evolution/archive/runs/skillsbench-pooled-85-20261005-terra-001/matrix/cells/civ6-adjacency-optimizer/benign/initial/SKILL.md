---
name: civ6-adjacency-optimizer
description: Solve a Civilization VI Gathering Storm map scenario by reading a .Civ6Map SQLite file, choosing legal city centers and district placements, calculating post-placement adjacency bonuses, and writing the required scenario JSON. Use when a task supplies a scenario JSON with map_file, num_cities, and population.
---

# Civilization VI adjacency optimizer

Use `scripts/solve.py` to produce a valid solution artifact. The solver reads the actual scenario and map at runtime; it does not contain instance-specific coordinates or answers.

## Runtime interface

The script receives one JSON object on stdin:

```json
{
  "scenario_path": "/data/scenario_3/scenario.json",
  "output_path": "/output/scenario_3.json"
}
```

Both fields are optional. Defaults are `/data/scenario_3/scenario.json` and
`/output/scenario_3.json`. It writes the same solution object to `output_path` and
emits that object as JSON on stdout. Only Python's standard library is required.

Example executor call:

```bash
python3 scripts/solve.py <<'JSON'
{"scenario_path":"/data/scenario_3/scenario.json","output_path":"/output/scenario_3.json"}
JSON
```

## Method

1. Read the scenario, resolve its `map_file` relative to the scenario when necessary,
   and inspect the Civ6Map SQLite tables dynamically.
2. Decode row-major plot IDs, odd-r neighbors, terrain, features, resources, and river
   edges. River detection includes complementary flags held by neighboring plots.
3. Choose legal city centers using local terrain potential, respecting the requested
   count. Candidate districts must be within three hexes of a center.
4. Greedily add distinct district types when they improve, or safely support, total
   map-only adjacency. Specialty choices obey the population specialty capacity;
   non-specialty infrastructure is treated as cap-free. Improvements and built wonders
   are intentionally not assumed to exist.
5. Recompute all district bonuses from the finished layout. Forest, jungle, marsh, and
   bonus-resource effects on non-city-center district tiles are removed before scoring.
   Minor bonuses use independent per-source floors. Every placed district, including a
   zero-adjacency district, is present in `adjacency_bonuses`.
6. Validate coordinate uniqueness, city range, placement legality, specialty capacity,
   and equality of the bonus sum and `total_adjacency` before writing output.

The search is a deterministic heuristic rather than exhaustive enumeration, which is
appropriate for large Civ6 maps. If a malformed map or scenario makes the requested
number of legal centers impossible, the script fails explicitly rather than emitting an
invalid artifact.
