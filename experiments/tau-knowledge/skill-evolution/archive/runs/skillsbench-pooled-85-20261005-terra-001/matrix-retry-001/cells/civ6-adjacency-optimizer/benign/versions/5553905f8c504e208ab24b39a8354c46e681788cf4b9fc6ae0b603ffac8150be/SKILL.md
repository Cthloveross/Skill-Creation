---
name: civ6-district-adjacency-optimizer
description: Read a Civilization VI .Civ6Map SQLite file and scenario JSON, choose legal city centers and a high-adjacency district layout, calculate post-destruction adjacency exactly under the supplied Gathering Storm map-only rules, validate the result, and write the task-required JSON solution. Use for Civ6 district-placement optimization tasks with map files.
---

# Civilization VI district adjacency optimizer

Use `scripts/solve.py` for both optimization and independent solution validation. It uses only Python's standard library, including `sqlite3`.

## Runtime interface

The script receives one JSON object on stdin and emits one JSON object on stdout.

### Solve

```json
{"action":"solve","scenario_path":"/data/scenario_3/scenario.json","output_path":"/output/scenario_3.json"}
```

`scenario_path` points to a scenario JSON containing `map_file`, `num_cities`, and `population`. `output_path` is optional; when supplied, the exact solution object emitted on stdout is also written there. Relative `map_file` values are resolved relative to the scenario file.

The emitted object is directly suitable as the task output:

- One city: `city_center`, `placements`, `adjacency_bonuses`, `total_adjacency`.
- More than one city: `cities`, `placements`, `adjacency_bonuses`, `total_adjacency`.

Every placed district, including zero-adjacency infrastructure, has an `adjacency_bonuses` entry. The sum is recalculated from those entries.

### Validate

```json
{"action":"validate","scenario_path":"/data/scenario_3/scenario.json","solution_path":"/output/scenario_3.json"}
```

Alternatively supply a parsed object as `solution`. Validation reports `valid`, a list of `errors`, `computed_adjacency_bonuses`, and `computed_total_adjacency`. The executor should correct or reject a solution if `valid` is false or if computed values differ from the reported values.

## Method and assumptions

1. The map reader loads `Map`, `Plots`, `PlotFeatures`, `PlotResources`, and `PlotRivers` from the SQLite map. Plot coordinates are decoded as `x = ID % Width`, `y = ID // Width`.
2. Hex geometry is odd-r horizontal offset. City range and adjacency use cube-coordinate distance / parity-correct neighbors.
3. Legal placement checks enforce the supplied universal rules, water-only Harbor, Aqueduct freshwater/City Center requirements, Dam floodplain/two-river-edge requirements, Encampment/Preserve center separation, and flat-land requirements where relevant. The optimizer uses only district classes whose rules are supported by the supplied reference; it deliberately does not fabricate Canal connectivity.
4. The solver limits scoring specialty districts by the population-based capacity per city. It considers Campus, Holy Site, Commercial Hub, Industrial Zone, Harbor, and Theater Square, then adds legal non-specialty adjacency infrastructure (Aqueduct, Dam, Neighborhood) when useful. Improvements and built Wonders are never assumed because `.Civ6Map` does not contain them.
5. Features and bonus resources on non-City-Center district tiles are removed before scoring. Major adjacency sources and generic district minor bonuses are evaluated separately, with every `+1 per 2` source independently floored.
6. Optimization is deterministic heuristic search rather than infeasible map-wide exhaustive district enumeration. It ranks legal city sites from nearby terrain potential, evaluates candidate city sets, greedily constructs legal layouts, and applies coordinate local search while always rescoring the complete layout. It is designed to produce strong valid solutions on large maps without claiming unsupported global-exhaustive optimality.

## Completion procedure

1. Run solve with the requested scenario path and requested `/output/...json` destination.
2. Run validation on the generated output.
3. If validation is true and computed/report values agree, leave the generated JSON at the requested output path. Do not add prose to that output file.
4. If the map schema or scenario is unsupported, the script returns a JSON error rather than inventing coordinates. Resolve only errors supported by the available task inputs.

River detection includes a plot's stored NE/W/NW edges and the complementary E/SE/SW edges recorded by adjacent plots. This prevents treating a merely nearby river as a Commercial Hub self-tile river bonus.
