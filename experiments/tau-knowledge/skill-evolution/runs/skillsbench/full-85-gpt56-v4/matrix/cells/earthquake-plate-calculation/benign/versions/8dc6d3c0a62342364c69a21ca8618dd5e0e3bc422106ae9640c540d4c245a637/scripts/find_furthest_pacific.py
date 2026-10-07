#!/usr/bin/env python3
"""Select the earthquake deepest inside the Pacific plate by EPSG:4087 distance.

Input (stdin):
  {"earthquakes_path": str, "plates_path": str,
   "boundaries_path": str, "output_path": str}
Output (stdout): {"ok": true, "output_path": str, "id": ...} on success,
                  or {"ok": false, "error": str} on failure.
"""
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
from shapely.geometry import shape
from shapely.ops import unary_union

REQUIRED_INPUTS = {"earthquakes_path", "plates_path", "boundaries_path", "output_path"}
OUTPUT_KEYS = {"id", "place", "time", "magnitude", "latitude", "longitude", "distance_km"}


def union_geometries(geometries):
    """Return a union while accepting GeoPandas versions with or without union_all."""
    valid = [geom for geom in geometries if geom is not None and not geom.is_empty]
    if not valid:
        raise ValueError("No usable geometries were available for union")
    return unary_union(valid)


def load_earthquakes(path):
    """Read GeoJSON features without losing top-level GeoJSON feature IDs."""
    with open(path, "r", encoding="utf-8") as source:
        collection = json.load(source)
    if collection.get("type") != "FeatureCollection" or not isinstance(collection.get("features"), list):
        raise ValueError("earthquakes_path must contain a GeoJSON FeatureCollection")

    rows = []
    for position, feature in enumerate(collection["features"]):
        geometry = feature.get("geometry")
        props = feature.get("properties") or {}
        if not isinstance(geometry, dict) or geometry.get("type") != "Point":
            continue
        coordinates = geometry.get("coordinates")
        if not isinstance(coordinates, list) or len(coordinates) < 2:
            continue
        if feature.get("id") is None:
            raise ValueError("Each usable earthquake feature must have a GeoJSON feature id")
        for key in ("place", "time", "mag"):
            if key not in props:
                raise ValueError(f"Earthquake feature {position} lacks properties.{key}")
        rows.append({
            "event_id": feature["id"],
            "place": props["place"],
            "event_time": props["time"],
            "magnitude": props["mag"],
            "longitude": coordinates[0],
            "latitude": coordinates[1],
            "catalog_order": position,
            "geometry": shape(geometry),
        })
    if not rows:
        raise ValueError("No usable Point earthquake features were found")
    return gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")


def get_pacific_geometry(plates):
    required = {"PlateName", "Code"}
    missing = required - set(plates.columns)
    if missing:
        raise ValueError("Plate data lacks required fields: " + ", ".join(sorted(missing)))
    names = plates["PlateName"].fillna("").astype(str).str.casefold()
    codes = plates["Code"].fillna("").astype(str).str.upper()
    pacific_rows = plates[(names == "pacific") | (codes == "PA")]
    if pacific_rows.empty:
        raise ValueError("Could not find the Pacific plate by PlateName or Code")
    codes_found = [str(code).upper() for code in pacific_rows["Code"].dropna() if str(code).strip()]
    if not codes_found:
        raise ValueError("Pacific plate has no usable Code")
    # PB2002 identifies the Pacific plate as PA. Retain the data-provided code for filtering.
    return union_geometries(pacific_rows.geometry), codes_found[0]


def iso_utc_from_milliseconds(value):
    try:
        milliseconds = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Earthquake time is not a Unix-millisecond number") from exc
    if not math.isfinite(milliseconds):
        raise ValueError("Earthquake time is not finite")
    return datetime.fromtimestamp(milliseconds / 1000.0, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def validate_output(result):
    if set(result) != OUTPUT_KEYS:
        raise ValueError("Result does not have exactly the required output fields")
    for field in ("latitude", "longitude", "distance_km"):
        if not isinstance(result[field], (int, float)) or isinstance(result[field], bool) or not math.isfinite(result[field]):
            raise ValueError(f"Result field {field} must be a finite number")
    if round(result["distance_km"], 2) != result["distance_km"]:
        raise ValueError("distance_km was not rounded to two decimal places")


def run(config):
    if not isinstance(config, dict):
        raise ValueError("stdin must be one JSON object")
    missing = REQUIRED_INPUTS - set(config)
    if missing:
        raise ValueError("Missing input keys: " + ", ".join(sorted(missing)))
    for key in REQUIRED_INPUTS:
        if not isinstance(config[key], str) or not config[key]:
            raise ValueError(f"Input {key} must be a nonempty string")

    earthquakes = load_earthquakes(config["earthquakes_path"])
    plates = gpd.read_file(config["plates_path"])
    boundaries = gpd.read_file(config["boundaries_path"])
    if plates.crs is None or boundaries.crs is None:
        raise ValueError("Plate and boundary layers must declare a CRS")
    # PB2002 is geographic WGS84. Normalize source layers before spatial operations.
    plates = plates.to_crs("EPSG:4326")
    boundaries = boundaries.to_crs("EPSG:4326")

    pacific_geometry, pacific_code = get_pacific_geometry(plates)
    inside = earthquakes[earthquakes.geometry.within(pacific_geometry)].copy()
    if inside.empty:
        raise ValueError("No earthquake points lie strictly within the Pacific plate")

    if "Name" not in boundaries.columns:
        raise ValueError("Boundary data lacks required Name field")
    involved = boundaries[boundaries["Name"].fillna("").astype(str).str.contains(pacific_code, regex=False)]
    if involved.empty:
        raise ValueError(f"No boundaries contain Pacific plate code {pacific_code}")
    boundary_geometry = union_geometries(involved.geometry)

    # GeoPandas projection is intentionally applied to both geometries before distance.
    inside_metric = inside.to_crs("EPSG:4087")
    boundary_metric = gpd.GeoSeries([boundary_geometry], crs="EPSG:4326").to_crs("EPSG:4087").iloc[0]
    inside_metric["distance_km_raw"] = inside_metric.geometry.distance(boundary_metric) / 1000.0
    if inside_metric["distance_km_raw"].isna().any() or not all(math.isfinite(float(v)) for v in inside_metric["distance_km_raw"]):
        raise ValueError("Projected boundary distance was not finite")

    # Stable catalog order resolves an otherwise exact numeric tie reproducibly.
    winner = inside_metric.sort_values(["distance_km_raw", "catalog_order"], ascending=[False, True], kind="mergesort").iloc[0]
    result = {
        "id": winner["event_id"],
        "place": winner["place"],
        "time": iso_utc_from_milliseconds(winner["event_time"]),
        "magnitude": winner["magnitude"],
        "latitude": float(winner["latitude"]),
        "longitude": float(winner["longitude"]),
        "distance_km": round(float(winner["distance_km_raw"]), 2),
    }
    if not isinstance(result["magnitude"], (int, float)) or isinstance(result["magnitude"], bool):
        raise ValueError("Earthquake magnitude must be numeric")
    validate_output(result)

    output_path = Path(config["output_path"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as target:
        json.dump(result, target, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        target.write("\n")
    return result, str(output_path)


def main():
    try:
        config = json.load(sys.stdin)
        result, output_path = run(config)
        print(json.dumps({"ok": True, "output_path": output_path, "id": result["id"]}, ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()
