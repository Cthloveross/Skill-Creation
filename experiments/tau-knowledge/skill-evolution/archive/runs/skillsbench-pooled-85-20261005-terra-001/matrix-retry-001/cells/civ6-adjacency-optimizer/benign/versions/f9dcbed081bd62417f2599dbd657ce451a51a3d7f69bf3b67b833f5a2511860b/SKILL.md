---
name: civ6-district-adjacency-optimizer
description: Create and validate a Civ6 district-adjacency placement JSON from a scenario JSON and its SQLite .Civ6Map. Use this for Civilization VI map placement tasks requiring legal city centers, district placements, and map-derived post-destruction adjacency totals.
---

# Civ6 district adjacency optimizer

Use `scripts/solve.py`. It reads the supplied scenario and map at runtime using only the Python standard library. The solver follows the task output contract and writes the exact JSON object that it prints.

## Runtime interface

The script accepts one JSON object on stdin and emits JSON on stdout.

### Solve and write the required artifact

```json
{"action":"solve","scenario_path":"/data/scenario_3/scenario.json","output_path":"/output/scenario_3.json"}
```

`scenario_path` must name a JSON object with `map_file`, `num_cities`, and `population`. A relative `map_file` is resolved relative to the scenario file. `output_path` is optional, but must be supplied for artifact tasks.

For one city, solve output has `city_center`; for multiple cities, it has a `cities` list with exactly the requested number of `{"center":[x,y]}` objects. All solutions contain:

- `placements`: object mapping district type to coordinate;
- `adjacency_bonuses`: one integer entry for every placement key, including zeroes;
- `total_adjacency`: the exact integer sum of those entries.

### Validate an existing solution

```json
{"action":"validate","scenario_path":"/data/scenario_3/scenario.json","solution_path":"/output/scenario_3.json"}
```

Alternatively, pass the parsed solution as `solution`. Validation returns:

```json
{"valid":true,"errors":[],"computed_adjacency_bonuses":{},"computed_total_adjacency":0}
```

The executor must leave the artifact only after validation reports `valid: true`. The validator intentionally recalculates the final JSON rather than trusting optimization-time scores.

## Method

1. Read `Map`, `Plots`, `PlotFeatures`, `PlotResources`, and `PlotRivers` from the `.Civ6Map` SQLite database. Decode each plot with `x = ID % Width`, `y = ID // Width`.
2. Apply the supplied odd-r neighbor geometry and unwrapped cube distance used for city-range checks. Wrapped map edges are respected only for neighboring tiles where map metadata says they wrap.
3. Enforce city, universal district, water-district, flat-land, Encampment/Preserve, Aqueduct, and Dam restrictions before a coordinate can be emitted. The solver uses only known district names.
4. Search high-value legal city sites, then greedily construct and locally improve a district cluster. Specialty selections never exceed `num_cities * (1 + floor((population - 1) / 3))`; legal non-specialty districts are also considered as generic-adjacency support.
5. Score the complete layout after all placements. A feature on any non-city-center district tile is removed before adjacency scoring. Major bonuses and each independently floored district minor bonus are recomputed from the final map state.
6. Read back and validate the exact object written to `output_path`. If the map or schema is unsupported, return an error rather than inventing a placement.

The implementation mirrors the declared evaluator conventions for river recognition and Harbor resource adjacency, so the reported values are based on the final serialized coordinates rather than assumptions about unavailable improvements or built wonders.
