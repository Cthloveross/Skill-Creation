---
name: pacific-plate-furthest-earthquake
description: Find the catalog earthquake inside a specified PB2002 tectonic plate that is farthest from any of that plate's PB2002 boundary segments, using GeoPandas containment and EPSG:4087 metric projection. Applies to USGS GeoJSON earthquake catalogs and PB2002-style plate and boundary GeoJSON files.
---

# Furthest in-plate earthquake from a plate boundary

Use `scripts/find_furthest_earthquake.py` to create the requested answer artifact. The script keeps containment and distance operations distinct:

1. It selects and unions every plate polygon whose `Code` equals `plate_code` (default `PA`), so all MultiPolygon components, including antimeridian parts, participate in the point-in-polygon test.
2. It reads USGS GeoJSON features directly so the GeoJSON feature `id` and the original longitude/latitude ordering are retained. Only points strictly `within` the unified plate geometry in EPSG:4326 are candidates.
3. It selects every boundary feature whose `Name` contains the plate code, irrespective of separator or code position, merges those line geometries, and projects both candidates and boundaries to EPSG:4087.
4. It computes each candidate's minimum geometric distance to the merged boundary, chooses the maximum, converts meters to kilometers, rounds it to two decimals, converts the millisecond epoch timestamp to UTC ISO 8601, and writes the exact answer fields.

## Runtime interface

The script receives one JSON object on stdin and emits a JSON status object on stdout.

Input fields are optional unless noted:

```json
{
  "earthquakes_path": "/root/earthquakes_2024.json",
  "plates_path": "/root/PB2002_plates.json",
  "boundaries_path": "/root/PB2002_boundaries.json",
  "output_path": "/root/answer.json",
  "plate_code": "PA"
}
```

All four path fields default to the paths shown above; `plate_code` defaults to `PA`. A normal execution can therefore receive `{}`. For example, the executor runs the packaged script with JSON stdin equivalent to `{}`. It must then ensure `/root/answer.json` exists and use that file as the task artifact.

On success stdout has `{"ok": true, "output_path": "...", "answer": {...}}`; `answer` is also serialized to `output_path`. On invalid source data, missing required columns/features, no in-plate earthquakes, or no matching boundaries, the script emits `{"ok": false, "error": "..."}` and exits nonzero rather than fabricating an answer.

## Output validation

Before writing, the script validates that the selected feature has an ID, place, numeric millisecond timestamp, magnitude, and finite original coordinates; it also checks that the computed metric distance is finite. The output contains exactly:

- `id`
- `place`
- `time` as `YYYY-MM-DDTHH:MM:SSZ`
- `magnitude`
- `latitude`
- `longitude`
- `distance_km` rounded to two decimal places

Do not calculate distance in geographic degrees, do not restrict boundaries to a single neighboring plate, and do not substitute polygon outlines for the dedicated PB2002 boundary dataset.
