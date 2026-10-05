#!/usr/bin/env python3
"""Create a flood-day CSV from local data using only the Python standard library."""
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
ID_RE = re.compile(r"(?<![0-9])[0-9]{8,}(?![0-9])")


def norm(value):
    return re.sub(r"[^a-z0-9]+", "", str(value).strip().lower())


def text(value):
    return "" if value is None else str(value).strip()


def numeric(value):
    """Convert finite numeric text, allowing commas and a trailing ordinary unit."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        answer = float(value)
        return answer if math.isfinite(answer) else None
    value = text(value)
    if value.lower() in MISSING:
        return None
    match = re.match(r"^[+ -]?\s*(\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", value.replace(",", ""))
    if not match:
        return None
    try:
        answer = float(match.group(0).replace(" ", ""))
    except ValueError:
        return None
    return answer if math.isfinite(answer) else None


def lookup(row, predicate):
    for key, value in row.items():
        if predicate(norm(key)):
            return value
    return None


def station_from(row):
    exact = {"stationid", "station", "siteid", "siteno", "usgsid", "usgssite", "sitecode", "monitoringlocationidentifier"}
    value = lookup(row, lambda key: key in exact)
    if value is None:
        value = lookup(row, lambda key: ("station" in key or "site" in key or "usgs" in key) and ("id" in key or "no" in key))
    candidate = text(value)
    # A station identifier is an identifier, not a number to normalize.
    return candidate if re.fullmatch(r"[0-9]{8,}", candidate) else ""


def threshold_from(row):
    value = lookup(row, lambda key: key in {"floodstage", "floodstagethreshold", "floodthreshold"} or ("flood" in key and "stage" in key))
    return numeric(value)


def timestamp_from(row):
    value = lookup(row, lambda key: key in {"datetime", "date", "timestamp", "observationtime", "time"} or "datetime" in key or "timestamp" in key or key.endswith("date"))
    return text(value)


def gage_from(row):
    # 00065_cd and other qualifier fields must never be read as observations.
    for key, value in row.items():
        key = norm(key)
        if "00060" in key or key.endswith("cd") or "qualifier" in key:
            continue
        if "00065" in key:
            return numeric(value)
    for key, value in row.items():
        key = norm(key)
        if key.endswith("cd") or "qualifier" in key:
            continue
        if "gageheight" in key or "gageht" in key or key in {"stage", "stageft", "stagefeet"}:
            return numeric(value)
    return None


def parse_date(value):
    value = text(value)
    match = re.match(r"(\d{4})[-/](\d{2})[-/](\d{2})", value)
    if match:
        try:
            return date(*map(int, match.groups()))
        except ValueError:
            return None
    for form in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(value.split()[0], form).date()
        except (ValueError, IndexError):
            pass
    return None


def delimited_rows(raw):
    lines = [line for line in raw.splitlines() if line.strip() and not line.lstrip().startswith("#")]
    if len(lines) < 2:
        return []
    try:
        dialect = csv.Sniffer().sniff("\n".join(lines[:20]), delimiters=",\t;|")
        table = list(csv.reader(lines, dialect))
    except csv.Error:
        table = [re.split(r"\s+", line.strip()) for line in lines]
    if len(table) < 2 or not table[0]:
        return []
    header = [cell.strip() for cell in table[0]]
    start = 1
    # USGS RDB commonly has a type/width row after its column names.
    if len(table) > 1 and table[1] and all(re.fullmatch(r"\d+[A-Za-z]+", cell.strip()) for cell in table[1] if cell.strip()):
        start = 2
    return [{header[i]: values[i].strip() for i in range(len(header))}
            for values in table[start:] if len(values) >= len(header)]


def json_rows(value, inherited=None):
    """Flatten JSON records while carrying parent station/threshold metadata down."""
    inherited = dict(inherited or {})
    out = []
    if isinstance(value, dict):
        context = dict(inherited)
        station, threshold = station_from(value), threshold_from(value)
        if station:
            context["station_id"] = station
        if threshold is not None:
            context["flood stage"] = threshold
        row = dict(value)
        if not station and "station_id" in context:
            row["station_id"] = context["station_id"]
        if threshold is None and "flood stage" in context:
            row["flood stage"] = context["flood stage"]
        out.append(row)
        for child in value.values():
            if isinstance(child, (dict, list)):
                out.extend(json_rows(child, context))
    elif isinstance(value, list):
        for child in value:
            out.extend(json_rows(child, inherited))
    return out


def load(path):
    with open(path, "r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        raw = handle.read()
    try:
        return raw, json_rows(json.loads(raw))
    except json.JSONDecodeError:
        return raw, delimited_rows(raw)


def analyze(primary_rows, threshold_rows, allowed, start, end):
    thresholds, conflicts = {}, set()
    for row in list(primary_rows) + list(threshold_rows):
        station, threshold = station_from(row), threshold_from(row)
        if station not in allowed or threshold is None:
            continue
        if station in thresholds and not math.isclose(thresholds[station], threshold, rel_tol=0, abs_tol=1e-12):
            conflicts.add(station)
        else:
            thresholds[station] = threshold
    for station in conflicts:
        thresholds.pop(station, None)

    daily_max = {}
    observation_count = 0
    for row in primary_rows:
        station, day, level = station_from(row), parse_date(timestamp_from(row)), gage_from(row)
        if station and day and level is not None:
            observation_count += 1
            if station in allowed and station in thresholds and start <= day <= end:
                key = (station, day)
                daily_max[key] = max(level, daily_max.get(key, -math.inf))

    counts = defaultdict(int)
    for (station, _day), maximum in daily_max.items():
        if maximum >= thresholds[station]:
            counts[station] += 1
    results = sorted(((station, count) for station, count in counts.items() if count > 0), key=lambda item: (-item[1], item[0]))
    return results, observation_count, len(thresholds), len(conflicts)


def write_and_validate(path, rows, allowed, max_days):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["station_id", "flood_days"])
        writer.writerows(rows)
    with open(path, "r", encoding="utf-8", newline="") as handle:
        table = list(csv.reader(handle))
    if not table or table[0] != ["station_id", "flood_days"]:
        raise ValueError("output validation failed: incorrect CSV header")
    seen = set()
    checked = []
    for row in table[1:]:
        if len(row) != 2 or row[0] not in allowed or not re.fullmatch(r"[1-9]\d*", row[1]):
            raise ValueError("output validation failed: invalid or out-of-scope result row")
        if row[0] in seen or int(row[1]) > max_days:
            raise ValueError("output validation failed: duplicate station or impossible day count")
        seen.add(row[0])
        checked.append((row[0], int(row[1])))
    if checked != sorted(checked, key=lambda item: (-item[1], item[0])):
        raise ValueError("output validation failed: rows are not consistently ordered")


def main():
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise ValueError("stdin must be a JSON object")
        input_path, output_path = request.get("input_path"), request.get("output_path")
        if not isinstance(input_path, str) or not isinstance(output_path, str):
            raise ValueError("input_path and output_path must be strings")
        start = parse_date(request.get("start_date", "2025-04-01"))
        end = parse_date(request.get("end_date", "2025-04-07"))
        if not start or not end or start > end:
            raise ValueError("start_date and end_date must be valid dates with start_date <= end_date")
        raw, primary = load(input_path)
        allowed = set(ID_RE.findall(raw))
        if not allowed:
            raise ValueError("No numeric USGS-style station IDs were found in input_path")
        threshold_path = request.get("threshold_path")
        if threshold_path is not None and not isinstance(threshold_path, str):
            raise ValueError("threshold_path must be a string when supplied")
        threshold_rows = load(threshold_path)[1] if threshold_path else []
        results, observations, thresholds, conflicts = analyze(primary, threshold_rows, allowed, start, end)
        days = (end - start).days + 1
        write_and_validate(output_path, results, allowed, days)
        warnings = []
        if not observations:
            warnings.append("No usable dated gage-height observations (00065) were available; CSV contains no unsupported flood claims.")
        if not thresholds:
            warnings.append("No valid in-scope numeric flood-stage thresholds were available; CSV contains no unsupported flood claims.")
        if conflicts:
            warnings.append("Stations with conflicting flood-stage thresholds were excluded.")
        print(json.dumps({
            "ok": True, "output_path": output_path, "output_rows": len(results),
            "station_scope_count": len(allowed), "observations_found": observations,
            "valid_thresholds_found": thresholds, "analysis_complete": bool(observations and thresholds),
            "warnings": warnings
        }, sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        sys.exit(2)


if __name__ == "__main__":
    main()
