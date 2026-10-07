---
name: earthquake-plate-boundary-distance
description: >
  Finds the earthquake located within a given tectonic plate (default: the
  Pacific plate, PB2002 code "PA") that lies furthest from that plate's
  boundary, using GeoPandas projections. Loads a USGS-style GeoJSON earthquake
  catalog plus the PB2002 plate-polygon and plate-boundary GeoJSON files,
  performs point-in-polygon containment in EPSG:4326, projects to the global
  equidistant CRS EPSG:4087 for metric distance, and writes the winning
  earthquake's attributes to a JSON answer file. Use whenever a task asks to
  relate earthquake epicenters to tectonic-plate geometry (containment and/or
  distance-to-boundary) with the PB2002 model.
---

# Earthquake → Plate Boundary Distance

## What this Skill does

Given three GeoJSON inputs it answers: *which earthquake inside plate X is
farthest from plate X's boundary, and how far (km)?* It is parameterized on the
plate (default Pacific / code `PA`) but the method is general.

Workflow (matches the frozen background knowledge):

1. **Load** the earthquake catalog, the `PB2002_plates` polygons, and the
   `PB2002_boundaries` linestrings with GeoPandas / Shapely.
2. **Select the plate polygon** by its two-letter `Code` (default `PA`), with a
   fallback to a `PlateName` match (default `Pacific`). Combine every matching
   row (the Pacific plate is a MultiPolygon split across the antimeridian) into
   one unified geometry via `unary_union` so no fragment is lost.
3. **Build earthquake points** from GeoJSON Point geometry. GeoJSON orders
   coordinates `[longitude, latitude, depth]` — longitude first. The catalog is
   already EPSG:4326; keep it there for containment.
4. **Containment filter**: keep only earthquakes `within` the unified plate
   polygon, in native EPSG:4326 (no projection for containment).
5. **Collect boundary segments**: keep every boundary feature whose `Name`
   field contains the plate code as a token (split on `-`, `/`, `\`), so all
   neighbours are included, not just one. Merge them into a single geometry.
6. **Project to metric CRS EPSG:4087** (World Equidistant Cylindrical) for both
   the candidate earthquake points and the merged boundary geometry, then
   compute each point's minimum distance to the boundary (meters → km).
7. **Pick the maximum** distance; emit that earthquake's attributes.
8. **Convert time**: the catalog `time` is a Unix timestamp in **milliseconds**
   — divide by 1000 before converting, and format UTC as
   `YYYY-MM-DDTHH:MM:SSZ`.
9. **Round** `distance_km` to 2 decimals and write the answer file.

## Running it

The entrypoint `scripts/solve.py` reads a JSON config on stdin and writes the
answer file, echoing the answer object on stdout.

Input JSON (all keys optional; defaults shown):
```json
{
  "earthquakes": "/root/earthquakes_2024.json",
  "plates": "/root/PB2002_plates.json",
  "boundaries": "/root/PB2002_boundaries.json",
  "output": "/root/answer.json",
  "plate_code": "PA",
  "plate_name": "Pacific",
  "metric_epsg": 4087
}
```

Example call (uses the task's default paths when stdin is empty `{}`):
```bash
echo '{}' | python3 /app/environment/skills/current/scripts/solve.py
cat /root/answer.json
```

Stdout / answer file schema (the public task's required fields):
```json
{
  "id": "<event id>",
  "place": "<description>",
  "time": "YYYY-MM-DDTHH:MM:SSZ",
  "magnitude": <number>,
  "latitude": <number>,
  "longitude": <number>,
  "distance_km": <number rounded to 2 decimals>
}
```

On stdout the script also prints `{"_meta": {...}}` style diagnostics on
stderr only (candidate counts, boundary segment count) to aid debugging; stdout
carries exactly the answer object.

## Executor instructions

- Run the entrypoint with the real task paths (defaults already match the
  copies declared in the environment: `/root/earthquakes_2024.json`,
  `/root/PB2002_plates.json`, `/root/PB2002_boundaries.json`).
- Confirm `/root/answer.json` exists and contains all seven required fields,
  that `time` matches the `...Z` ISO pattern, and that `distance_km` has at most
  two decimals and is a plausible plate-interior distance (hundreds to a few
  thousand km, not a tiny degree-scale number — a value under ~50 usually means
  the metric projection was skipped).
- If GeoPandas/Shapely are missing, install them
  (`pip install geopandas shapely pyproj`); internet is allowed.
- Do not hardcode an answer: always re-read the supplied inputs at runtime.
- `scripts/geo_utils.py` holds the reusable, task-independent helpers; keep
  corrections there so they transfer to fresh evaluation.

## Known pitfalls handled

- MultiPolygon antimeridian plates (union all parts; containment covers all).
- Boundary filtering by token so all neighbouring segments are captured.
- Distances computed only after projecting to EPSG:4087 (never in degrees).
- Millisecond → second timestamp conversion.
- Longitude-first GeoJSON coordinate ordering.
- Rounding of false floating-point precision to 2 decimals.
