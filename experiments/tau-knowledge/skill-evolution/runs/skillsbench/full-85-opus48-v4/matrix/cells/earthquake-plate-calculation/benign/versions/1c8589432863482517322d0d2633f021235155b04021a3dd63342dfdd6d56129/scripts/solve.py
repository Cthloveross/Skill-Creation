#!/usr/bin/env python3
"""Entrypoint: find the earthquake within a tectonic plate that is farthest
from that plate's boundary, and write the answer JSON.

Stdin: JSON config (all keys optional). See SKILL.md for schema and defaults.
Stdout: the answer object (also written to the output file).
Stderr: diagnostic meta (counts).
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo_utils as gu  # noqa: E402

DEFAULTS = {
    "earthquakes": "/root/earthquakes_2024.json",
    "plates": "/root/PB2002_plates.json",
    "boundaries": "/root/PB2002_boundaries.json",
    "output": "/root/answer.json",
    "plate_code": "PA",
    "plate_name": "Pacific",
    "metric_epsg": 4087,
}


def main():
    raw = sys.stdin.read().strip()
    cfg = dict(DEFAULTS)
    if raw:
        try:
            user = json.loads(raw)
            if isinstance(user, dict):
                cfg.update({k: v for k, v in user.items() if v is not None})
        except json.JSONDecodeError:
            pass

    import geopandas as gpd
    from shapely.geometry import Point

    # --- Load plate polygons and boundaries as GeoDataFrames ---
    plates = gpd.read_file(cfg["plates"])
    boundaries = gpd.read_file(cfg["boundaries"])
    if plates.crs is None:
        plates = plates.set_crs(epsg=4326)
    if boundaries.crs is None:
        boundaries = boundaries.set_crs(epsg=4326)

    plate_geom = gu.select_plate_geometry(
        plates, cfg["plate_code"], cfg["plate_name"])
    boundary_geom, n_segments = gu.select_boundary_geometry(
        boundaries, cfg["plate_code"])

    # --- Earthquake points (EPSG:4326) ---
    eq_json = gu.load_geojson(cfg["earthquakes"])
    records = list(gu.earthquake_records(eq_json))
    if not records:
        raise ValueError("No point earthquakes found in catalog")

    geoms = [Point(r["longitude"], r["latitude"]) for r in records]
    eq_gdf = gpd.GeoDataFrame(records, geometry=geoms, crs="EPSG:4326")

    # --- Containment filter in native EPSG:4326 ---
    inside_mask = eq_gdf.geometry.within(plate_geom)
    inside = eq_gdf[inside_mask].copy()
    sys.stderr.write(json.dumps({
        "total_eq": int(len(eq_gdf)),
        "inside_plate": int(len(inside)),
        "boundary_segments": n_segments,
    }) + "\n")
    if len(inside) == 0:
        raise ValueError("No earthquakes fall within the selected plate")

    # --- Project to metric CRS and compute distance to boundary ---
    metric = int(cfg["metric_epsg"])
    inside_m = inside.to_crs(epsg=metric)
    boundary_m = gpd.GeoSeries([boundary_geom], crs="EPSG:4326").to_crs(
        epsg=metric).iloc[0]

    inside = inside.assign(
        distance_km=inside_m.geometry.distance(boundary_m) / 1000.0)

    winner_idx = inside["distance_km"].idxmax()
    w = inside.loc[winner_idx]

    answer = {
        "id": w["id"],
        "place": w["place"],
        "time": gu.ms_to_iso(w["time_ms"]),
        "magnitude": (float(w["magnitude"]) if w["magnitude"] is not None else None),
        "latitude": round(float(w["latitude"]), 6),
        "longitude": round(float(w["longitude"]), 6),
        "distance_km": round(float(w["distance_km"]), 2),
    }

    with open(cfg["output"], "w", encoding="utf-8") as fh:
        json.dump(answer, fh, indent=2)
        fh.write("\n")

    sys.stdout.write(json.dumps(answer) + "\n")


if __name__ == "__main__":
    main()
