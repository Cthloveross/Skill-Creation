---
name: civ6-district-adjacency-optimizer
description: Read a Civilization VI `.Civ6Map` SQLite map and scenario JSON, select valid city centers and district locations, calculate post-placement adjacency exactly under the supplied Gathering Storm map-only rules, and write the required scenario solution JSON. Use for Civ6 district-adjacency optimization tasks with the specified output schema.
---

# Civ6 District Adjacency Optimizer

Use `scripts/solve.py` to produce a solution from the actual scenario at runtime. The solver reads the map database rather than assuming map dimensions, terrain, resources, rivers, or a particular scenario answer.

## Run

Scripts accept a JSON object on stdin and emit a JSON result on stdout:

```sh
python3 scripts/solve.py <<'EOF'
{"scenario":"/data/scenario_3/scenario.json","output":"/output/scenario_3.json"}
EOF
```

Input fields:

- `scenario` (required): path to the scenario JSON containing `map_file`, `num_cities`, and `population`.
- `output` (optional): path where the task-format solution JSON will be written. The same solution is also printed.
- `solution` (optional): when supplied with `scenario`, validate that existing solution instead of solving it.

The solver supports relative `map_file` paths by resolving them relative to the scenario file. It loads SQLite tables dynamically, handles odd-row hex neighbors and distance, detects river edges on both sides of a shared edge, and treats map-unavailable improvements and wonders as absent.

## Method

The optimizer searches promising valid city-center regions, then greedily builds a compact district layout and applies coordinate-improvement passes. It uses the population specialty cap, includes useful non-specialty adjacency boosters, and reports every placed district including districts whose adjacency is zero. It recalculates the final layout from scratch after feature destruction, independently floors each minor source category, and asserts that the reported per-district sum equals the total.

The search is heuristic rather than exhaustive, because exhaustive district-placement enumeration is infeasible on large maps. If a scenario has unusual map schema or no valid layout, inspect the JSON error rather than inventing coordinates.

## Validation

To validate a produced task file without overwriting it:

```sh
python3 scripts/solve.py <<'EOF'
{"scenario":"/data/scenario_3/scenario.json","solution":"/output/scenario_3.json"}
EOF
```

A successful validation result has `valid: true`, recomputed adjacency values, and a matching total. The validator checks center count, bounds, non-overlap, district placement rules, city range, and all reported adjacency entries.
