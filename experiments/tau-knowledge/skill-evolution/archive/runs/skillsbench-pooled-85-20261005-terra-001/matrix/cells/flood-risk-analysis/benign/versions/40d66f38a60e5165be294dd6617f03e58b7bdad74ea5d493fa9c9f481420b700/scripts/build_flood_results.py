#!/usr/bin/env python3
"""Build a validated flood-results CSV from locally staged NWS and USGS exports."""
import csv
import json
import math
import os
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta

ID_RE = re.compile(r"(?<!\d)(\d{8,})(?!\d)")
MISSING = {"", "na", "n/a", "nan", "none", "null", "--", "-"}
SUPPORTED_SUFFIXES = {".csv", ".tsv", ".txt", ".rdb", ".json"}


def text(value):
    return "" if value is None else str(value).strip()


def norm_key(value):
    return re.sub(r"[^a-z0-9]+", "", text(value).lower())


def station_id(value):
    match = re.fullmatch(r"(?:usgs[-:\s]*)?(\d{8,})(?:\.0+)?", text(value), re.I)
    return match.group(1) if match else ""


def number(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        value = float(value)
        return value if math.isfinite(value) else None
    value = text(value)
    if value.lower() in MISSING:
        return None
    match = re.fullmatch(
        r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?)\s*(?:[a-z.]*)",
        value.replace(",", ""), re.I,
    )
    try:
        result = float(match.group(1)) if match else None
    except ValueError:
        result = None
    return result if result is not None and math.isfinite(result) else None


def field_value(row, predicate):
    for key, value in row.items():
        if predicate(norm_key(key)):
            return value
    return None


def row_station_id(row):
    exact = {
        "stationid", "station", "siteid", "siteno", "usgsid", "usgssite",
        "sitecode", "monitoringlocationidentifier",
    }
    value = field_value(row, lambda key: key in exact)
    if value is None:
        value = field_value(
            row,
            lambda key: ("station" in key or "site" in key or "usgs" in key)
            and ("id" in key or "no" in key),
        )
    return station_id(value)


def flood_stage(row):
    # Prefer the exact NWS field rather than another possible flood-related stage.
    value = field_value(row, lambda key: key == "floodstage")
    if value is None:
        value = field_value(
            row,
            lambda key: key in {"floodstagethreshold", "floodthreshold"}
            or ("flood" in key and "stage" in key),
        )
    return number(value)


def gage_height(row):
    for key, value in row.items():
        normalized = norm_key(key)
        if "00065" in normalized and not normalized.endswith("cd") and "qualifier" not in normalized:
            return number(value)
    for key, value in row.items():
        normalized = norm_key(key)
        if normalized.endswith("cd") or "qualifier" in normalized or "00060" in normalized:
            continue
        if normalized in {"stage", "stageft", "stagefeet", "gageheight", "gageht"} or "gageheight" in normalized:
            return number(value)
    return None


def calendar_day(value):
    value = text(value)
    match = re.match(r"(\d{4})[-/](\d\d)[-/](\d\d)", value)
    if match:
        try:
            return date(*map(int, match.groups()))
        except ValueError:
            return None
    for fmt in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(value.split()[0], fmt).date()
        except (ValueError, IndexError):
            pass
    return None


def row_day(row):
    value = field_value(
        row,
        lambda key: key in {"datetime", "date", "timestamp", "observationtime", "time"}
        or "datetime" in key or "timestamp" in key or key.endswith("date"),
    )
    return calendar_day(value)


def parse_table(raw):
    lines = [line for line in raw.splitlines() if line.strip() and not line.lstrip().startswith("#")]
    if len(lines) < 2:
        return []
    try:
        dialect = csv.Sniffer().sniff("\n".join(lines[:30]), delimiters=",\t;|")
        values = list(csv.reader(lines, dialect))
    except csv.Error:
        values = [re.split(r"\s+", line.strip()) for line in lines]
    if len(values) < 2:
        return []
    header = [value.strip() for value in values[0]]
    # RDB's second line contains field type declarations, e.g. 15s and 20d.
    begin = 2 if values[1] and all(
        re.fullmatch(r"\d+[A-Za-z]+", value.strip()) for value in values[1] if value.strip()
    ) else 1
    return [
        {header[index]: row[index].strip() for index in range(len(header))}
        for row in values[begin:] if len(row) >= len(header)
    ]


def flatten_json(value, inherited=None):
    """Produce simple scalar rows while carrying recognized parent station metadata."""
    inherited = dict(inherited or {})
    output = []
    if isinstance(value, list):
        for item in value:
            output.extend(flatten_json(item, inherited))
    elif isinstance(value, dict):
        context = dict(inherited)
        found_station = row_station_id(value)
        if found_station:
            context["station_id"] = found_station
        found_stage = flood_stage(value)
        if found_stage is not None:
            context["flood stage"] = found_stage
        scalar = {str(key): item for key, item in value.items() if not isinstance(item, (dict, list))}
        if scalar:
            for key, item in context.items():
                scalar.setdefault(key, item)
            output.append(scalar)
        for item in value.values():
            if isinstance(item, (dict, list)):
                output.extend(flatten_json(item, context))
    return output


def usgs_nwis_json_rows(value):
    """Extract 00065 values from the public NWIS JSON timeSeries representation."""
    try:
        series = value["value"]["timeSeries"]
    except (KeyError, TypeError):
        return []
    output = []
    if not isinstance(series, list):
        return output
    for item in series:
        if not isinstance(item, dict):
            continue
        source = item.get("sourceInfo", {})
        codes = source.get("siteCode", []) if isinstance(source, dict) else []
        site = ""
        if isinstance(codes, list):
            for code in codes:
                if isinstance(code, dict):
                    site = station_id(code.get("value"))
                    if site:
                        break
        variable = item.get("variable", {})
        parameter_codes = variable.get("variableCode", []) if isinstance(variable, dict) else []
        is_00065 = any(
            isinstance(code, dict) and text(code.get("value")) == "00065"
            for code in parameter_codes if isinstance(parameter_codes, list)
        )
        if not site or not is_00065:
            continue
        for group in item.get("values", []):
            observations = group.get("value", []) if isinstance(group, dict) else []
            for observation in observations:
                if isinstance(observation, dict):
                    output.append({
                        "site_no": site,
                        "datetime": observation.get("dateTime"),
                        "00065": observation.get("value"),
                    })
    return output


def load_rows(path):
    with open(path, encoding="utf-8-sig", errors="replace", newline="") as handle:
        raw = handle.read()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return raw, parse_table(raw)
    return raw, usgs_nwis_json_rows(parsed) + flatten_json(parsed)


def discover(root, excluded):
    candidates = []
    if not os.path.isdir(root):
        return candidates
    for directory, _, names in os.walk(root):
        for name in names:
            path = os.path.abspath(os.path.join(directory, name))
            try:
                size = os.path.getsize(path)
            except OSError:
                continue
            if path not in excluded and size <= 100 * 1024 * 1024 and os.path.splitext(name)[1].lower() in SUPPORTED_SUFFIXES:
                candidates.append(path)
    return sorted(candidates)


def expected_days(start, end):
    return {start + timedelta(days=offset) for offset in range((end - start).days + 1)}


def write_and_validate(path, results, scope, maximum_count):
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["station_id", "flood_days"])
        writer.writerows(results)
    with open(path, encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    if not rows or rows[0] != ["station_id", "flood_days"]:
        raise ValueError("output header validation failed")
    seen = set()
    for row in rows[1:]:
        if len(row) != 2 or row[0] not in scope or not re.fullmatch(r"[1-9]\d*", row[1]):
            raise ValueError("invalid output result row")
        if int(row[1]) > maximum_count or row[0] in seen:
            raise ValueError("invalid output result row")
        seen.add(row[0])
    if results != sorted(results, key=lambda item: (-item[1], item[0])):
        raise ValueError("output ordering validation failed")


def main():
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise ValueError("stdin must be a JSON object")
        input_path, output_path = request.get("input_path"), request.get("output_path")
        if not isinstance(input_path, str) or not isinstance(output_path, str):
            raise ValueError("input_path and output_path are required strings")
        start = calendar_day(request.get("start_date", "2025-04-01"))
        end = calendar_day(request.get("end_date", "2025-04-07"))
        if start is None or end is None or start > end:
            raise ValueError("start_date and end_date must be ordered ISO dates")

        input_path = os.path.abspath(input_path)
        output_path = os.path.abspath(output_path)
        raw_scope, rows = load_rows(input_path)
        scope = set(ID_RE.findall(raw_scope))
        if not scope:
            raise ValueError("input_path contains no USGS-style station IDs")

        supplied_paths = []
        threshold_path = request.get("threshold_path")
        if threshold_path is not None:
            if not isinstance(threshold_path, str):
                raise ValueError("threshold_path must be a string")
            supplied_paths.append(os.path.abspath(threshold_path))
        observation_paths = request.get("observation_paths", [])
        if not isinstance(observation_paths, list) or not all(isinstance(item, str) for item in observation_paths):
            raise ValueError("observation_paths must be an array of strings")
        supplied_paths.extend(os.path.abspath(item) for item in observation_paths)
        discover_local = request.get("discover_local_data", True)
        if not isinstance(discover_local, bool):
            raise ValueError("discover_local_data must be boolean")
        if discover_local:
            supplied_paths.extend(discover("/root/data", {input_path, output_path}))
        source_paths = list(dict.fromkeys(supplied_paths))

        unread = []
        for path in source_paths:
            try:
                rows.extend(load_rows(path)[1])
            except (OSError, UnicodeError) as exc:
                unread.append(path + ": " + str(exc))

        thresholds = {}
        conflicting_thresholds = set()
        for row in rows:
            site, threshold = row_station_id(row), flood_stage(row)
            if site not in scope or threshold is None:
                continue
            if site in thresholds and not math.isclose(threshold, thresholds[site], abs_tol=1e-12):
                conflicting_thresholds.add(site)
            else:
                thresholds[site] = threshold
        for site in conflicting_thresholds:
            thresholds.pop(site, None)

        maxima = {}
        usable_observations = 0
        for row in rows:
            site, observed, height = row_station_id(row), row_day(row), gage_height(row)
            if site in thresholds and observed is not None and height is not None and start <= observed <= end:
                usable_observations += 1
                key = (site, observed)
                maxima[key] = max(height, maxima.get(key, -math.inf))

        required_dates = expected_days(start, end)
        observed_dates = defaultdict(set)
        for site, observed in maxima:
            observed_dates[site].add(observed)
        incomplete = sorted(site for site in thresholds if observed_dates[site] != required_dates)
        complete_sites = set(thresholds) - set(incomplete)

        counts = defaultdict(int)
        for (site, _), maximum in maxima.items():
            if site in complete_sites and maximum >= thresholds[site]:
                counts[site] += 1
        results = sorted(
            ((site, count) for site, count in counts.items() if count > 0),
            key=lambda item: (-item[1], item[0]),
        )
        write_and_validate(output_path, results, scope, len(required_dates))

        warnings = []
        if not thresholds:
            warnings.append("No valid in-scope numeric NWS flood-stage threshold was found in local data.")
        if thresholds and not usable_observations:
            warnings.append("No in-window dated gage-height observations (00065/stage) were found for thresholded stations.")
        if incomplete:
            warnings.append("Thresholded stations lacking gage-height coverage for every requested date were excluded.")
        if complete_sites and not results:
            warnings.append("No complete station had a daily maximum meeting its valid flood stage.")
        if conflicting_thresholds:
            warnings.append("Stations with conflicting flood-stage values were excluded.")
        if unread:
            warnings.append("Unreadable supplied paths: " + "; ".join(unread))
        print(json.dumps({
            "ok": True,
            "output_path": output_path,
            "output_rows": len(results),
            "station_scope_count": len(scope),
            "valid_thresholds_found": len(thresholds),
            "in_window_observations_found": usable_observations,
            "complete_station_coverage_count": len(complete_sites),
            "incomplete_observation_stations": incomplete,
            "analysis_complete": bool(complete_sites),
            "warnings": warnings,
        }, sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        sys.exit(2)


if __name__ == "__main__":
    main()
