#!/usr/bin/env python3
"""Build a flood-day CSV from local records; uses Python standard library only."""
import csv
import io
import json
import math
import os
import re
import sys
from collections import defaultdict
from datetime import date, datetime

MISSING = {"", "na", "n/a", "nan", "none", "null", "--", "-"}


def norm(value):
    return re.sub(r"[^a-z0-9]+", "", str(value).strip().lower())


def string_value(value):
    if value is None:
        return ""
    return str(value).strip()


def number(value):
    """Return a finite float, accepting a value with ordinary units/commas."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        result = float(value)
        return result if math.isfinite(result) else None
    text = str(value).strip()
    if text.lower() in MISSING:
        return None
    text = text.replace(",", "")
    match = re.match(r"^[+ -]?\s*(\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", text)
    if not match:
        return None
    try:
        result = float(match.group(0).replace(" ", ""))
    except ValueError:
        return None
    return result if math.isfinite(result) else None


def field_lookup(row, predicate):
    for key, value in row.items():
        if predicate(norm(key)):
            return value
    return None


def station_from(row):
    exact = {"stationid", "station", "siteid", "siteno", "usgsid", "usgssite", "sitecode", "monitoringlocationidentifier"}
    value = field_lookup(row, lambda k: k in exact)
    if value is not None:
        return string_value(value)
    value = field_lookup(row, lambda k: ("station" in k or "site" in k or "usgs" in k) and ("id" in k or "no" in k or k == "usgs"))
    return string_value(value) if value is not None else ""


def threshold_from(row):
    value = field_lookup(row, lambda k: k in {"floodstage", "floodstagethreshold", "floodthreshold"} or ("flood" in k and "stage" in k))
    return number(value)


def timestamp_from(row):
    value = field_lookup(row, lambda k: k in {"datetime", "date", "timestamp", "date time", "observationtime", "time"} or "datetime" in k or "timestamp" in k or k.endswith("date"))
    return string_value(value) if value is not None else ""


def gage_from(row):
    # Qualifier columns such as 00065_cd must never be measurements.
    for key, value in row.items():
        key_norm = norm(key)
        if "00060" in key_norm or key_norm.endswith("cd") or "qualifier" in key_norm:
            continue
        if "00065" in key_norm:
            return number(value)
    for key, value in row.items():
        key_norm = norm(key)
        if key_norm.endswith("cd") or "qualifier" in key_norm:
            continue
        if "gageheight" in key_norm or "gageht" in key_norm:
            return number(value)
        # Plain stage is acceptable, but flood stage is a threshold, not observation.
        if key_norm in {"stage", "stageft", "stagefeet"}:
            return number(value)
    return None


def parse_date(value):
    text = string_value(value)
    if not text:
        return None
    # USGS timestamps ordinarily begin with a local ISO calendar date.  Keeping
    # that component maintains the source station's calendar-day convention.
    match = re.match(r"(\d{4})-(\d{2})-(\d{2})", text)
    if not match:
        match = re.match(r"(\d{4})/(\d{2})/(\d{2})", text)
    if match:
        try:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            return None
    for fmt in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(text.split()[0], fmt).date()
        except ValueError:
            pass
    return None


def delimiter_rows(text):
    """Parse CSV/TSV/RDB-like content into dictionaries without third-party code."""
    raw = [line for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]
    if not raw:
        return []
    sample = "\n".join(raw[:20])
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
        parsed = list(csv.reader(raw, dialect))
    except csv.Error:
        parsed = [re.split(r"\s+", line.strip()) for line in raw]
    if len(parsed) < 2:
        return []
    header = [cell.strip() for cell in parsed[0]]
    # NWIS RDB places a datatype/width line immediately below the header.
    start = 1
    if len(parsed) > 1 and parsed[1] and all(re.fullmatch(r"\d+[a-zA-Z]+", c.strip()) for c in parsed[1] if c.strip()):
        start = 2
    rows = []
    for values in parsed[start:]:
        if len(values) < len(header):
            continue
        rows.append({header[i]: values[i].strip() for i in range(len(header))})
    return rows


def json_rows(value, inherited=None):
    """Collect dict records, passing a containing station/threshold to nested rows."""
    inherited = dict(inherited or {})
    result = []
    if isinstance(value, dict):
        local = dict(inherited)
        station = station_from(value)
        threshold = threshold_from(value)
        if station:
            local["__inherited_station_id"] = station
        if threshold is not None:
            local["__inherited_flood_stage"] = threshold
        result.append(value)
        for child in value.values():
            if isinstance(child, (dict, list)):
                result.extend(json_rows(child, local))
    elif isinstance(value, list):
        for child in value:
            result.extend(json_rows(child, inherited))
    # Materialize inherited values only where child did not provide them.
    materialized = []
    for row in result:
        merged = dict(row)
        if not station_from(merged) and "__inherited_station_id" in inherited:
            merged["station_id"] = inherited["__inherited_station_id"]
        if threshold_from(merged) is None and "__inherited_flood_stage" in inherited:
            merged["flood stage"] = inherited["__inherited_flood_stage"]
        materialized.append(merged)
    return materialized


def load_rows(path):
    with open(path, "r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        text = handle.read()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return delimiter_rows(text)
    return json_rows(parsed)


def analyze(primary_rows, threshold_rows, start, end):
    thresholds = {}
    threshold_conflicts = set()
    observations = []
    skipped = 0

    for row in list(primary_rows) + list(threshold_rows):
        station = station_from(row)
        threshold = threshold_from(row)
        if station and threshold is not None:
            if station in thresholds and not math.isclose(thresholds[station], threshold, rel_tol=0, abs_tol=1e-12):
                threshold_conflicts.add(station)
            else:
                thresholds[station] = threshold

    # Contradictory source thresholds cannot be silently selected.
    for station in threshold_conflicts:
        thresholds.pop(station, None)

    for row in primary_rows:
        station = station_from(row)
        day = parse_date(timestamp_from(row))
        gage = gage_from(row)
        if station and day and gage is not None:
            observations.append((station, day, gage))
        elif station and (timestamp_from(row) or gage_from(row) is not None):
            skipped += 1

    if not observations:
        raise ValueError("No usable dated gage-height observations were found. Require parameter 00065 (or a gage-height/stage field), station ID, and timestamp; discharge 00060 is not usable.")
    if not thresholds:
        raise ValueError("No valid numeric flood-stage thresholds were found. Supply flood stage metadata in the input or threshold_path.")

    daily_max = {}
    for station, day, gage in observations:
        if start <= day <= end and station in thresholds:
            key = (station, day)
            daily_max[key] = max(gage, daily_max.get(key, -math.inf))
    counts = defaultdict(int)
    for (station, _day), maximum in daily_max.items():
        if maximum >= thresholds[station]:
            counts[station] += 1
    result = sorted(((station, count) for station, count in counts.items() if count > 0), key=lambda item: (-item[1], item[0]))
    return result, {"observations": len(observations), "thresholds": len(thresholds), "skipped_candidate_rows": skipped, "conflicting_threshold_stations_excluded": len(threshold_conflicts)}


def write_and_validate(path, rows):
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["station_id", "flood_days"])
        writer.writerows(rows)
    with open(path, "r", encoding="utf-8", newline="") as handle:
        read_rows = list(csv.reader(handle))
    if not read_rows or read_rows[0] != ["station_id", "flood_days"]:
        raise ValueError("Output validation failed: CSV header is incorrect")
    checked = []
    for row in read_rows[1:]:
        if len(row) != 2 or not row[0] or not re.fullmatch(r"[1-9]\d*", row[1]):
            raise ValueError("Output validation failed: invalid result row")
        checked.append((row[0], int(row[1])))
    if len({station for station, _ in checked}) != len(checked) or checked != sorted(checked, key=lambda item: (-item[1], item[0])):
        raise ValueError("Output validation failed: duplicate or improperly ordered stations")


def main():
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise ValueError("stdin must be a JSON object")
        input_path = request.get("input_path")
        output_path = request.get("output_path")
        if not isinstance(input_path, str) or not isinstance(output_path, str):
            raise ValueError("input_path and output_path must be strings")
        start = parse_date(request.get("start_date", "2025-04-01"))
        end = parse_date(request.get("end_date", "2025-04-07"))
        if not start or not end or start > end:
            raise ValueError("start_date and end_date must be valid ISO-like dates with start_date <= end_date")
        primary = load_rows(input_path)
        threshold_path = request.get("threshold_path")
        if threshold_path is not None and not isinstance(threshold_path, str):
            raise ValueError("threshold_path must be a string when supplied")
        thresholds = load_rows(threshold_path) if threshold_path else []
        results, statistics = analyze(primary, thresholds, start, end)
        write_and_validate(output_path, results)
        print(json.dumps({"ok": True, "output_path": output_path, "start_date": start.isoformat(), "end_date": end.isoformat(), "output_rows": len(results), **statistics}, sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        sys.exit(2)


if __name__ == "__main__":
    main()
