#!/usr/bin/env python3
"""Create an answer.json for the furthest earthquake inside a PB2002 plate.

Reads one JSON object from stdin. See SKILL.md for its schema. Requires geopandas,
shapely, and pandas supplied by the execution runtime.
"""

import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import shape
from shapely.ops import unary_union

DEFAULTS = {
    "earthquakes_path": "/root/earthquakes_2024.json",
    "plates_path": "/root/PB2002_plates.json",
    "boundaries_path": "/root/PB2002_boundaries.json",
    "output_path": "/root/answer.json",
    "plate_code": "PA",
}
REQUIRED_OUTPUT_KEYS = {
    "id", "place", "time", "magnitude", "latitude", "longitude", "distance_km"
}


def fail(message):
    """Raise a clear failure that the main wrapper reports as JSON."""
    raise ValueError(message)


def require_file(value, label):
    path = Path(value)
    if not path.is_file():
        fail(f"{label} does not exist or is not a file: {path}")
    return path


def load_earthquake_features(path):
    """Load GeoJSON directly to reliably retain Feature.id and point coordinates."""
    with open(path, "r", encoding="utf-8") as source:
        document = json.load(source)
    if document.get("type") != "FeatureCollection":
        fail("earthquake input must be a GeoJSON FeatureCollection")
    features = document.get("features")
    if not isinstance(features, list) or not features:
        fail("earthquake FeatureCollection has no features")

    rows = []
    geometries = []
    for feature_number, feature in enumerate(features):
        if not isinstance(feature, dict):
            fail(f"earthquake feature {feature_number} is not an object")
        geometry_data = feature.get("geometry")
        if not isinstance(geometry_data, dict) or geometry_data.get("type") != "Point":
            fail(f"earthquake feature {feature_number} is not a GeoJSON Point")
        coordinates = geometry_data.get("coordinates")
        if not isinstance(coordinates, list) or len(coordinates) < 2:
            fail(f"earthquake feature {feature_number} lacks longitude/latitude coordinates")
        try:
            longitude, latitude = float(coordinates[0]), float(coordinates[1])
        except (TypeError, ValueError):
            fail(f"earthquake feature {feature_number} has nonnumeric coordinates")
        if not math.isfinite(longitude) or not math.isfinite(latitude):
            fail(f"earthquake feature {feature_number} has non-finite coordinates")

        properties = feature.get("properties")
        if not isinstance(properties, dict):
            fail(f"earthquake feature {feature_number} has invalid properties")
        row = dict(properties)
        row["_feature_id"] = feature.get("id")
        row["_original_longitude"] = longitude
        row["_original_latitude"] = latitude
        rows.append(row)
        geometries.append(shape(geometry_data))

    return gpd.GeoDataFrame(rows, geometry=geometries, crs="EPSG:4326")


def merged_geometry(geometries, label):
    usable = [geom for geom in geometries if geom is not None and not geom.is_empty]
    if not usable:
        fail(f"no usable geometries found for {label}")
    result = unary_union(usable)
    if result is None or result.is_empty:
        fail(f"merged geometry for {label} is empty")
    return result


def nonmissing(value, label):
    if value is None or pd.isna(value) or (isinstance(value, str) and not value.strip()):
        fail(f"selected earthquake is missing required {label}")
    return value


def format_millis_utc(value):
    nonmissing(value, "time")
    try:
        milliseconds = float(value)
    except (TypeError, ValueError):
        fail("selected earthquake time is not numeric milliseconds since epoch")
    if not math.isfinite(milliseconds):
        fail("selected earthquake time is not finite")
    try:
        instant = datetime.fromtimestamp(milliseconds / 1000.0, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        fail("selected earthquake time cannot be converted from Unix milliseconds")
    return instant.strftime("%Y-%m-%dT%H:%M:%SZ")


def compute_answer(config):
    plate_code = str(config["plate_code"]).strip()
    if not plate_code:
        fail("plate_code must be a nonempty string")

    earthquake_path = require_file(config["earthquakes_path"], "earthquakes_path")
    plates_path = require_file(config["plates_path"], "plates_path")
    boundaries_path = require_file(config["boundaries_path"], "boundaries_path")

    earthquakes = load_earthquake_features(earthquake_path)
    plates = gpd.read_file(plates_path)
    boundaries = gpd.read_file(boundaries_path)
    for frame, label, column in (
        (plates, "plates", "Code"),
        (boundaries, "boundaries", "Name"),
    ):
        if frame.crs is None:
            fail(f"{label} data has no CRS")
        if column not in frame.columns:
            fail(f"{label} data lacks required {column!r} field")

    # PB2002 source files are geographic. Convert explicitly if their CRS metadata
    # differs, so containment takes place in the earthquakes' EPSG:4326 CRS.
    plates_4326 = plates.to_crs("EPSG:4326")
    boundaries_4326 = boundaries.to_crs("EPSG:4326")
    plate_rows = plates_4326[
        plates_4326["Code"].astype(str).str.upper() == plate_code.upper()
    ]
    plate_geometry = merged_geometry(plate_rows.geometry, f"plate code {plate_code}")

    # strict within intentionally follows normal point-in-polygon semantics.
    candidates = earthquakes[earthquakes.geometry.within(plate_geometry)].copy()
    if candidates.empty:
        fail(f"no earthquake points are within plate code {plate_code}")

    boundary_rows = boundaries_4326[
        boundaries_4326["Name"].fillna("").astype(str).str.contains(plate_code, regex=False)
    ]
    boundary_geometry = merged_geometry(
        boundary_rows.geometry, f"boundary segments containing {plate_code}"
    )

    # EPSG:4087 supplies meter-valued coordinates; distance is consequently meters.
    candidate_metric = candidates.to_crs("EPSG:4087")
    boundary_metric = gpd.GeoSeries([boundary_geometry], crs="EPSG:4326").to_crs(
        "EPSG:4087"
    ).iloc[0]
    distances_m = candidate_metric.geometry.distance(boundary_metric)
    if distances_m.empty or distances_m.isna().all():
        fail("could not compute distances to the merged plate boundary")
    max_index = distances_m.idxmax()
    selected = candidates.loc[max_index]
    distance_m = float(distances_m.loc[max_index])
    if not math.isfinite(distance_m):
        fail("largest computed boundary distance is not finite")

    feature_id = nonmissing(selected.get("_feature_id"), "id")
    place = nonmissing(selected.get("place"), "place")
    magnitude = nonmissing(selected.get("mag"), "magnitude")
    try:
        magnitude = float(magnitude)
    except (TypeError, ValueError):
        fail("selected earthquake magnitude is not numeric")
    if not math.isfinite(magnitude):
        fail("selected earthquake magnitude is not finite")

    longitude = float(selected["_original_longitude"])
    latitude = float(selected["_original_latitude"])
    answer = {
        "id": str(feature_id),
        "place": str(place),
        "time": format_millis_utc(selected.get("time")),
        "magnitude": magnitude,
        "latitude": latitude,
        "longitude": longitude,
        "distance_km": round(distance_m / 1000.0, 2),
    }
    if set(answer) != REQUIRED_OUTPUT_KEYS:
        fail("internal output schema error")
    return answer


def main():
    try:
        raw = sys.stdin.read().strip()
        supplied = {} if not raw else json.loads(raw)
        if not isinstance(supplied, dict):
            fail("stdin JSON must be an object")
        unknown = set(supplied).difference(DEFAULTS)
        if unknown:
            fail("unsupported input fields: " + ", ".join(sorted(unknown)))
        config = dict(DEFAULTS)
        config.update(supplied)
        answer = compute_answer(config)
        output_path = Path(config["output_path"])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as destination:
            json.dump(answer, destination, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
            destination.write("\n")
        print(json.dumps({"ok": True, "output_path": str(output_path), "answer": answer}, allow_nan=False))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
