"""Reusable, task-independent helpers for earthquake/plate geospatial analysis.

All functions assume the PB2002 model (EPSG:4326 inputs) and a USGS-style
GeoJSON earthquake catalog. Keep durable fixes here so they survive into fresh
evaluation of the Skill.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone


def load_geojson(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def ms_to_iso(timestamp_ms):
    """USGS catalog times are Unix milliseconds. Return 'YYYY-MM-DDTHH:MM:SSZ'."""
    if timestamp_ms is None:
        return None
    seconds = float(timestamp_ms) / 1000.0
    dt = datetime.fromtimestamp(seconds, tz=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


_SEP = re.compile(r"[-/\\]+")


def name_tokens(name):
    """Split a boundary Name like 'PA-NA' or 'NA/PA' into plate-code tokens."""
    if not name:
        return []
    return [t.strip() for t in _SEP.split(str(name)) if t.strip()]


def boundary_involves_plate(name, plate_code):
    """True if the two-letter plate_code is one of the Name's tokens.

    Falls back to substring containment if tokenization yields nothing useful,
    matching the background guidance that the code may appear anywhere.
    """
    code = plate_code.upper()
    toks = [t.upper() for t in name_tokens(name)]
    if toks:
        if code in toks:
            return True
        # Also accept token that embeds the code (defensive) only if same length
        return any(code == t for t in toks)
    return code in str(name or "").upper()


def select_plate_geometry(plates_gdf, plate_code="PA", plate_name="Pacific"):
    """Return a unified Shapely geometry for the target plate.

    Prefers an exact two-letter Code match; falls back to a PlateName match.
    Unions every matching row so MultiPolygon (antimeridian) plates are whole.
    """
    cols = {c.lower(): c for c in plates_gdf.columns}
    code_col = cols.get("code")
    name_col = cols.get("platename") or cols.get("name")

    subset = None
    if code_col is not None:
        subset = plates_gdf[plates_gdf[code_col].astype(str).str.upper()
                             == plate_code.upper()]
    if (subset is None or len(subset) == 0) and name_col is not None:
        subset = plates_gdf[plates_gdf[name_col].astype(str).str.lower()
                            == plate_name.lower()]
    if subset is None or len(subset) == 0:
        raise ValueError(
            f"Could not locate plate code={plate_code!r} name={plate_name!r} "
            f"in columns {list(plates_gdf.columns)}")

    try:
        return subset.geometry.unary_union
    except Exception:
        from shapely.ops import unary_union
        return unary_union(list(subset.geometry.values))


def select_boundary_geometry(boundaries_gdf, plate_code="PA"):
    """Return a single merged geometry of all boundary segments for the plate."""
    cols = {c.lower(): c for c in boundaries_gdf.columns}
    name_col = cols.get("name")
    if name_col is None:
        raise ValueError(
            f"Boundary dataset has no Name field; columns={list(boundaries_gdf.columns)}")
    mask = boundaries_gdf[name_col].apply(
        lambda n: boundary_involves_plate(n, plate_code))
    subset = boundaries_gdf[mask]
    if len(subset) == 0:
        raise ValueError(f"No boundary segments contained code {plate_code!r}")
    try:
        geom = subset.geometry.unary_union
    except Exception:
        from shapely.ops import unary_union
        geom = unary_union(list(subset.geometry.values))
    return geom, int(len(subset))


def earthquake_records(eq_geojson):
    """Yield dicts with id/place/time_ms/mag/lon/lat from a USGS FeatureCollection.

    Honors GeoJSON [longitude, latitude, depth] ordering.
    """
    feats = eq_geojson.get("features", []) if isinstance(eq_geojson, dict) else []
    for f in feats:
        geom = (f or {}).get("geometry") or {}
        if geom.get("type") != "Point":
            continue
        coords = geom.get("coordinates") or []
        if len(coords) < 2:
            continue
        lon, lat = float(coords[0]), float(coords[1])
        props = f.get("properties") or {}
        yield {
            "id": f.get("id"),
            "place": props.get("place"),
            "time_ms": props.get("time"),
            "magnitude": props.get("mag"),
            "longitude": lon,
            "latitude": lat,
        }
