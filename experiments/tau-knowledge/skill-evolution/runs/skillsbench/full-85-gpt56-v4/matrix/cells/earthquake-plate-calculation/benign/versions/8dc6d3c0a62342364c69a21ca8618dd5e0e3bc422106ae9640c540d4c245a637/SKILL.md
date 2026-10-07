---
name: furthest-earthquake-within-plate
summary: Find the catalog earthquake contained by a named tectonic-plate polygon that has the greatest projected distance to that plate's boundary, and write a required JSON result.
description: Use this Skill for GeoJSON earthquake catalogs and PB2002-style plate and boundary layers when a result must be selected by strict point-in-polygon containment and distance to all boundaries of a plate.
---

# Furthest earthquake within a plate

This Skill uses GeoPandas in the source geographic CRS for containment and EPSG:4087 for the requested Pacific-wide metric distance calculation. It preserves GeoJSON feature IDs by reading the earthquake FeatureCollection directly and building a GeoDataFrame from its features.

## Runtime inputs

Run `scripts/find_furthest_pacific.py` with one JSON object on standard input:

```json
{
  "earthquakes_path": "/path/to/earthquakes.geojson",
  "plates_path": "/path/to/plates.geojson",
  "boundaries_path": "/path/to/boundaries.geojson",
  "output_path": "/path/to/answer.json"
}
```

All four keys are required strings. The output file is a single JSON object with exactly these fields:

- `id`
- `place`
- `time`
- `magnitude`
- `latitude`
- `longitude`
- `distance_km`

Example invocation for the supplied runtime files:

```sh
python3 /app/environment/skills/current/scripts/find_furthest_pacific.py <<'JSON'
{"earthquakes_path":"/root/earthquakes_2024.json","plates_path":"/root/PB2002_plates.json","boundaries_path":"/root/PB2002_boundaries.json","output_path":"/root/answer.json"}
JSON
```

## Method

1. Locate the Pacific plate with `PlateName == "Pacific"` (case-insensitive) or `Code == "PA"`, and union all its geometry parts. This retains MultiPolygon parts around the antimeridian.
2. Strictly select earthquake points `within` that union in EPSG:4326. Boundary-touching points are not treated as inside.
3. Get the Pacific code from the selected plate data and select **every** boundary whose `Name` contains that code, regardless of separator or position. Union the selected lines.
4. Reproject selected points and the merged boundary geometry to EPSG:4087. Compute each point's minimum planar distance to the complete merged boundary and convert meters to kilometers.
5. Select the largest distance, convert the catalog timestamp from Unix milliseconds to UTC `YYYY-MM-DDTHH:MM:SSZ`, and round `distance_km` to two decimals.

The script validates required source fields, usable geometries, a nonempty containment result, finite distance, and the final output schema. It writes a JSON status object to stdout. On failure it writes a JSON error object to stdout and exits nonzero; do not treat an error status as a result.

The executor should inspect the status, then parse the `output_path` file and confirm it is a JSON object with exactly the seven required fields and a numeric `distance_km` rounded to two decimal places.
