#!/usr/bin/env python3
"""Build flood_results.csv from local NWS and USGS exports using stdlib only."""
import csv
import json
import math
import os
import re
import sys
from collections import defaultdict
from datetime import date, datetime

ID_RE = re.compile(r"(?<!\d)(\d{8,})(?!\d)")
MISSING = {"", "na", "n/a", "nan", "none", "null", "--", "-"}


def clean(value):
    return "" if value is None else str(value).strip()


def key(value):
    return re.sub(r"[^a-z0-9]+", "", clean(value).lower())


def station(value):
    """Return a numeric station identifier without numeric coercion."""
    value = clean(value)
    match = re.fullmatch(r"(?:USGS[-:\s]*)?(\d{8,})", value, re.I)
    return match.group(1) if match else ""


def number(value):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        result = float(value)
        return result if math.isfinite(result) else None
    value = clean(value)
    if value.lower() in MISSING:
        return None
    # Accept a numeric value followed by an ordinary unit, but not arbitrary text.
    match = re.match(r"^[+]?\s*(-?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*(?:[A-Za-z.]*)$", value.replace(",", ""))
    if not match:
        return None
    try:
        result = float(match.group(1))
    except ValueError:
        return None
    return result if math.isfinite(result) else None


def value_for(row, predicate):
    for name, value in row.items():
        if predicate(key(name)):
            return value
    return None


def row_station(row):
    exact = {"stationid", "station", "siteid", "siteno", "usgsid", "usgssite", "sitecode", "monitoringlocationidentifier"}
    value = value_for(row, lambda name: name in exact)
    if value is None:
        value = value_for(row, lambda name: ("station" in name or "site" in name or "usgs" in name) and ("id" in name or "no" in name))
    return station(value)


def flood_stage(row):
    value = value_for(row, lambda name: name in {"floodstage", "floodstagethreshold", "floodthreshold"} or ("flood" in name and "stage" in name))
    return number(value)


def gage_height(row):
    # Parameter-code fields take precedence. Never use qualifiers or discharge.
    for name, value in row.items():
        name = key(name)
        if "00065" in name and not name.endswith("cd") and "qualifier" not in name:
            return number(value)
    for name, value in row.items():
        name = key(name)
        if name.endswith("cd") or "qualifier" in name or "00060" in name:
            continue
        if name in {"stage", "stageft", "stagefeet", "gageheight", "gageht"} or "gageheight" in name:
            return number(value)
    return None


def row_day(row):
    value = value_for(row, lambda name: name in {"datetime", "date", "timestamp", "observationtime", "time"} or "datetime" in name or "timestamp" in name or name.endswith("date"))
    text = clean(value)
    match = re.match(r"(\d{4})[-/](\d{2})[-/](\d{2})", text)
    if match:
        try:
            return date(*map(int, match.groups()))
        except ValueError:
            return None
    for fmt in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(text.split()[0], fmt).date()
        except (ValueError, IndexError):
            pass
    return None


def delimited_rows(raw):
    lines = [line for line in raw.splitlines() if line.strip() and not line.lstrip().startswith("#")]
    if len(lines) < 2:
        return []
    try:
        dialect = csv.Sniffer().sniff("\n".join(lines[:30]), delimiters=",\t;|")
        table = list(csv.reader(lines, dialect))
    except csv.Error:
        table = [re.split(r"\s+", line.strip()) for line in lines]
    if len(table) < 2 or not table[0]:
        return []
    header = [x.strip() for x in table[0]]
    start = 1
    # USGS RDB has a type/width row such as 5s, 15s, 20d after the header.
    if len(table) > 1 and table[1] and all(re.fullmatch(r"\d+[A-Za-z]+", x.strip()) for x in table[1] if x.strip()):
        start = 2
    return [{header[i]: row[i].strip() for i in range(len(header))}
            for row in table[start:] if len(row) >= len(header)]


def json_rows(value, context=None):
    """Flatten ordinary JSON record arrays, inheriting station/threshold metadata."""
    context = dict(context or {})
    out = []
    if isinstance(value, list):
        for item in value:
            out.extend(json_rows(item, context))
    elif isinstance(value, dict):
        here = dict(context)
        own_station, own_threshold = row_station(value), flood_stage(value)
        if own_station:
            here["station_id"] = own_station
        if own_threshold is not None:
            here["flood stage"] = own_threshold
        scalar = {str(k): v for k, v in value.items() if not isinstance(v, (dict, list))}
        if scalar:
            scalar = dict(scalar)
            scalar.setdefault("station_id", here.get("station_id", ""))
            if "flood stage" in here:
                scalar.setdefault("flood stage", here["flood stage"])
            out.append(scalar)
        for child in value.values():
            if isinstance(child, (dict, list)):
                out.extend(json_rows(child, here))
    return out


def load(path):
    with open(path, "r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        raw = handle.read()
    try:
        return raw, json_rows(json.loads(raw))
    except json.JSONDecodeError:
        return raw, delimited_rows(raw)


def discover(root, excluded):
    found = []
    if not os.path.isdir(root):
        return found
    for directory, _dirs, names in os.walk(root):
        for name in names:
            path = os.path.abspath(os.path.join(directory, name))
            if path in excluded or os.path.getsize(path) > 100 * 1024 * 1024:
                continue
            if os.path.splitext(name)[1].lower() in {".csv", ".tsv", ".txt", ".rdb", ".json"}:
                found.append(path)
    return sorted(found)


def write_and_check(path, results, allowed, day_limit):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["station_id", "flood_days"])
        writer.writerows(results)
    with open(path, "r", encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))
    if not rows or rows[0] != ["station_id", "flood_days"]:
        raise ValueError("output header validation failed")
    seen = set()
    checked = []
    for row in rows[1:]:
        if len(row) != 2 or row[0] not in allowed or not re.fullmatch(r"[1-9]\d*", row[1]):
            raise ValueError("output contains an invalid result row")
        if row[0] in seen or int(row[1]) > day_limit:
            raise ValueError("output has duplicate station or invalid day count")
        seen.add(row[0])
        checked.append((row[0], int(row[1])))
    if checked != sorted(checked, key=lambda item: (-item[1], item[0])):
        raise ValueError("output ordering validation failed")


def main():
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise ValueError("stdin must contain a JSON object")
        input_path, output_path = request.get("input_path"), request.get("output_path")
        if not isinstance(input_path, str) or not isinstance(output_path, str):
            raise ValueError("input_path and output_path are required strings")
        start = row_day({"date": request.get("start_date", "2025-04-01")})
        end = row_day({"date": request.get("end_date", "2025-04-07")})
        if not start or not end or start > end:
            raise ValueError("start_date and end_date must be ordered ISO dates")
        primary_raw, primary_rows = load(input_path)
        allowed = set(ID_RE.findall(primary_raw))
        if not allowed:
            raise ValueError("input_path has no numeric USGS-style station IDs")

        paths = [input_path]
        threshold_path = request.get("threshold_path")
        if threshold_path is not None:
            if not isinstance(threshold_path, str):
                raise ValueError("threshold_path must be a string")
            paths.append(threshold_path)
        observation_paths = request.get("observation_paths", [])
        if not isinstance(observation_paths, list) or not all(isinstance(p, str) for p in observation_paths):
            raise ValueError("observation_paths must be an array of strings")
        paths.extend(observation_paths)
        if request.get("discover_local_data", True) is not True and request.get("discover_local_data", True) is not False:
            raise ValueError("discover_local_data must be boolean")
        if request.get("discover_local_data", True):
            paths.extend(discover("/root/data", {os.path.abspath(output_path)}))
        paths = list(dict.fromkeys(os.path.abspath(p) for p in paths))

        all_rows, unreadable = list(primary_rows), []
        for path in paths[1:]:
            try:
                all_rows.extend(load(path)[1])
            except (OSError, UnicodeError) as exc:
                unreadable.append(path + ": " + str(exc))

        thresholds, conflicting = {}, set()
        for row in all_rows:
            sid, threshold = row_station(row), flood_stage(row)
            if sid not in allowed or threshold is None:
                continue
            if sid in thresholds and not math.isclose(thresholds[sid], threshold, rel_tol=0, abs_tol=1e-12):
                conflicting.add(sid)
            else:
                thresholds[sid] = threshold
        for sid in conflicting:
            thresholds.pop(sid, None)

        maxima, usable_observations = {}, 0
        for row in all_rows:
            sid, day, level = row_station(row), row_day(row), gage_height(row)
            if sid and day and level is not None:
                usable_observations += 1
            if sid in thresholds and day is not None and level is not None and start <= day <= end:
                maxima[(sid, day)] = max(level, maxima.get((sid, day), -math.inf))
        counts = defaultdict(int)
        for (sid, _day), maximum in maxima.items():
            if maximum >= thresholds[sid]:
                counts[sid] += 1
        results = sorted(((sid, count) for sid, count in counts.items() if count), key=lambda item: (-item[1], item[0]))
        write_and_check(output_path, results, allowed, (end - start).days + 1)

        warnings = []
        if not thresholds:
            warnings.append("No valid in-scope numeric NWS flood-stage threshold was found in local data.")
        if not usable_observations:
            warnings.append("No dated gage-height observations (parameter 00065/stage) were found in local data.")
        if conflicting:
            warnings.append("Stations with conflicting flood-stage values were excluded.")
        if unreadable:
            warnings.append("Some supplied local paths were unreadable: " + "; ".join(unreadable))
        print(json.dumps({"ok": True, "output_path": output_path, "output_rows": len(results),
                          "station_scope_count": len(allowed), "valid_thresholds_found": len(thresholds),
                          "observations_found": usable_observations,
                          "analysis_complete": bool(thresholds and usable_observations),
                          "warnings": warnings}, sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        sys.exit(2)

if __name__ == "__main__":
    main()
