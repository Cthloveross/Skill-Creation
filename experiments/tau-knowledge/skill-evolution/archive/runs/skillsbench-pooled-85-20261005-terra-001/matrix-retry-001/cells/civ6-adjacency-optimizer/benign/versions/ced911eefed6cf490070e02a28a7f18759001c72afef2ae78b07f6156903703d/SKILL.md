---
name: civ6-district-adjacency-optimizer
description: Produce a valid Civilization VI district-adjacency solution from a scenario JSON and its SQLite .Civ6Map. Use for tasks that must write legal city and district coordinates plus post-destruction map-derived adjacency totals.
---

# Civ6 district adjacency optimizer

Use `scripts/solve.py` to inspect the scenario's SQLite map, select legal city centers and district tiles, compute final adjacency, and write the requested artifact. The implementation uses only the Python standard library.

## Runtime interface

The script accepts one JSON object on stdin and emits one JSON object on stdout.

### Solve and write an artifact

```json
{"action":"solve","scenario_path":"/data/scenario_3/scenario.json","output_path":"/output/scenario_3.json"}
```

`scenario_path` names a scenario object containing `map_file`, `num_cities`, and `population`. Relative map paths are resolved relative to the scenario, then against `/data/maps`. Supplying `output_path` causes the exact serialized artifact to be read back and validated before the script succeeds.

### Validate a solution

```json
{"action":"validate","scenario_path":"/data/scenario_3/scenario.json","solution_path":"/output/scenario_3.json"}
```

A parsed solution can be supplied as `solution` instead of `solution_path`. Validation emits:

```json
{"valid":true,"errors":[],"computed_adjacency_bonuses":{},"computed_total_adjacency":0}
```

## Output contract

For one city, the solution has `city_center`; for more cities, it has a `cities` list containing exactly `num_cities` objects of the form `{"center":[x,y]}`. Every solution also has nonempty `placements`, an integer `adjacency_bonuses` entry for exactly every placement key (including zeroes), and integer `total_adjacency` equal to their sum.

## Method and safeguards

1. The solver reads `Map`, `Plots`, `PlotFeatures`, `PlotResources`, and `PlotRivers` directly from the map SQLite database and uses odd-r neighbors and cube distance.
2. It rejects invalid terrain, features, resources, range, overlap, water-district, flat-land, Encampment/Preserve, Aqueduct, and Dam placements before emitting them.
3. Specialty districts are assigned to an individual in-range city while selecting them. Each city independently observes `1 + floor((population - 1) / 3)` specialty slots; capacity is never pooled merely because city ranges overlap.
4. The solver deliberately does not use a Canal as generic Industrial Zone support. If a supplied solution contains one, validation requires it to connect an adjacent city center to water or to bridge two distinct connected water bodies.
5. Adjacency is recomputed after all non-city-center district features are destroyed. Per-source minor bonuses are independently floored, and every placed non-scoring district reports zero.
6. The selected layout is greedily improved over feature-rich candidate regions, then the final written JSON is independently validated. A map/schema error produces an explicit error rather than invented coordinates.
