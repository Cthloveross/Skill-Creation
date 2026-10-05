#!/usr/bin/env python3
"""Create flood-day results from locally supplied NWS and USGS snapshots.

Input and output are JSON on stdin/stdout; the requested CSV is the artifact.
This module intentionally uses only the Python standard library.
"""
import csv
import datetime as dt
import json
import math
import os
import re
import sys
import tempfile


class AnalysisError(Exception):
    pass


def canon(value):
    return re.sub(r"[^a-z0-9]", "", str(value).strip().lower())


STATION_NAMES = {"stationid", "usgsid", "siteno", "siteid", "site"}
TIME_NAMES = {"datetime", "date", "timestamp", "time", "date time"}
STAGE_NAMES = {"floodstage"}
GAGE_NAMES = {"gageheight", "stage", "gageht"}


def read_table(path):
    """Return (headers, rows), retaining every field as text.

    Supports normal comma/tab/semicolon tables, USGS RDB files, and one-ID-per-line
    station files. Comment lines in RDB exports are ignored.
    """
    try:
        with open(path, "r", encoding="utf-8-sig", newline="") as handle:
            raw_lines = handle.readlines()
    except OSError as exc:
        raise AnalysisError("cannot read %s: %s" % (path, exc))

    lines = [line.rstrip("\r\n") for line in raw_lines if line.strip() and not line.lstrip().startswith("#")]
    if not lines:
        raise AnalysisError("input file is empty: %s" % path)

    first = lines[0]
    if "\t" in first:
        delimiter = "\t"
    elif "," in first:
        delimiter = ","
    elif ";" in first:
        delimiter = ";"
    else:
        # A common station-list form is a header followed by one ID per line.
        first_name = canon(first)
        if first_name in STATION_NAMES:
            return [first.strip()], [{first.strip(): line.strip()} for line in lines[1:]]
        return ["station_id"], [{"station_id": line.strip()} for line in lines]

    parsed = list(csv.reader(lines, delimiter=delimiter))
    if not parsed or not parsed[0]:
        raise AnalysisError("could not find a header in %s" % path)
    headers = [cell.strip() for cell in parsed[0]]
    if not any(headers):
        raise AnalysisError("table header is blank in %s" % path)

    data_start = 1
    # In NWIS RDB, the second non-comment row describes field widths, e.g. 5s.
    if len(parsed) > 1 and parsed[1] and all(re.fullmatch(r"\d+[a-zA-Z]", cell.strip() or "") for cell in parsed[1]):
        data_start = 2

    rows = []
    for values in parsed[data_start:]:
        if not any(cell.strip() for cell in values):
            continue
        padded = values + [""] * max(0, len(headers) - len(values))
        rows.append({headers[i]: padded[i].strip() for i in range(len(headers))})
    return headers, rows


def find_column(headers, accepted, purpose, required=True):
    for header in headers:
        if canon(header) in accepted:
            return header
    if required:
        raise AnalysisError("no %s column found (headers: %s)" % (purpose, ", ".join(headers)))
    return None


def find_gage_column(headers):
    for header in headers:
        name = canon(header)
        # Qualifier columns such as 00065_cd are never measurements.
        if "00065" in name and not name.endswith("cd") and "qual" not in name:
            return header
    for header in headers:
        if canon(header) in GAGE_NAMES:
            return header
    raise AnalysisError(
        "no instantaneous gage-height column found; require parameter 00065 or gage_height, not discharge 00060"
    )


def numeric(value):
    try:
        answer = float(str(value).strip())
    except (ValueError, TypeError):
        return None
    return answer if math.isfinite(answer) else None


def local_day(value):
    """Extract the displayed local calendar date without converting timezone."""
    text = str(value).strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", text):
        try:
            return dt.date.fromisoformat(text[:10])
        except ValueError:
            return None
    for pattern in ("%m/%d/%Y", "%m/%d/%Y %H:%M", "%Y/%m/%d"):
        try:
            return dt.datetime.strptime(text, pattern).date()
        except ValueError:
            pass
    return None


def station_ids_from_file(path):
    headers, rows = read_table(path)
    station_col = find_column(headers, STATION_NAMES, "station ID")
    ids = set()
    for row in rows:
        value = row.get(station_col, "").strip()
        if value:
            ids.add(value)
    if not ids:
        raise AnalysisError("station file contains no nonblank station IDs: %s" % path)
    return ids


def load_thresholds(path, scope):
    headers, rows = read_table(path)
    station_col = find_column(headers, STATION_NAMES, "threshold station ID")
    stage_col = find_column(headers, STAGE_NAMES, "flood stage")
    thresholds = {}
    for row in rows:
        station = row.get(station_col, "").strip()
        if station not in scope:
            continue
        stage = numeric(row.get(stage_col, ""))
        if stage is None:
            continue
        if station in thresholds and thresholds[station] != stage:
            raise AnalysisError("conflicting numeric flood stages for station %s" % station)
        thresholds[station] = stage
    return thresholds


def load_daily_maxima(path, scope, start, end):
    headers, rows = read_table(path)
    station_col = find_column(headers, STATION_NAMES, "observation station ID")
    time_col = find_column(headers, TIME_NAMES, "observation timestamp")
    value_col = find_gage_column(headers)
    maxima = {}
    considered = 0
    for row in rows:
        station = row.get(station_col, "").strip()
        if station not in scope:
            continue
        day = local_day(row.get(time_col, ""))
        if day is None or day < start or day > end:
            continue
        value = numeric(row.get(value_col, ""))
        if value is None:
            continue
        considered += 1
        key = (station, day)
        if key not in maxima or value > maxima[key]:
            maxima[key] = value
    return maxima, considered


def validate_results(results, scope, thresholds, maxima):
    seen = set()
    for station, count in results:
        if station in seen or station not in scope or station not in thresholds:
            raise AnalysisError("internal result validation failed for station IDs")
        if not isinstance(count, int) or count < 1:
            raise AnalysisError("internal result validation failed for flood-day count")
        expected = sum(
            1 for (observed_station, _day), level in maxima.items()
            if observed_station == station and level >= thresholds[station]
        )
        if expected != count:
            raise AnalysisError("internal result validation failed for %s" % station)
        seen.add(station)
    if results != sorted(results, key=lambda pair: (-pair[1], pair[0])):
        raise AnalysisError("internal result validation failed for ordering")


def write_csv(path, results):
    directory = os.path.dirname(os.path.abspath(path))
    try:
        os.makedirs(directory, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".flood_results_", suffix=".csv", dir=directory, text=True)
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(["station_id", "flood_days"])
            writer.writerows(results)
        os.replace(temporary, path)
    except OSError as exc:
        try:
            os.unlink(temporary)
        except (OSError, UnboundLocalError):
            pass
        raise AnalysisError("cannot write output CSV %s: %s" % (path, exc))

    # Check the durable artifact, not just the in-memory rows.
    try:
        with open(path, "r", encoding="utf-8", newline="") as handle:
            saved = list(csv.reader(handle))
    except OSError as exc:
        raise AnalysisError("could not re-read output CSV: %s" % exc)
    expected = [["station_id", "flood_days"]] + [[station, str(days)] for station, days in results]
    if saved != expected:
        raise AnalysisError("output CSV validation failed")


def require_string(config, key):
    value = config.get(key)
    if not isinstance(value, str) or not value.strip():
        raise AnalysisError("JSON field %r must be a nonempty string" % key)
    return value


def run(config):
    station_file = require_string(config, "station_file")
    output_csv = require_string(config, "output_csv")
    threshold_file = config.get("thresholds_file", station_file)
    observation_file = config.get("observations_file", station_file)
    if not isinstance(threshold_file, str) or not threshold_file.strip():
        raise AnalysisError("thresholds_file must be a nonempty string when provided")
    if not isinstance(observation_file, str) or not observation_file.strip():
        raise AnalysisError("observations_file must be a nonempty string when provided")

    try:
        start = dt.date.fromisoformat(require_string(config, "start_date"))
        end = dt.date.fromisoformat(require_string(config, "end_date"))
    except ValueError:
        raise AnalysisError("start_date and end_date must be ISO YYYY-MM-DD dates")
    if end < start:
        raise AnalysisError("end_date precedes start_date")

    scope = station_ids_from_file(station_file)
    thresholds = load_thresholds(threshold_file, scope)
    maxima, observation_count = load_daily_maxima(observation_file, set(thresholds), start, end)

    counts = {}
    for (station, _day), level in maxima.items():
        if level >= thresholds[station]:
            counts[station] = counts.get(station, 0) + 1
    results = sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
    validate_results(results, scope, thresholds, maxima)
    write_csv(output_csv, results)
    return {
        "ok": True,
        "output_csv": output_csv,
        "stations_requested": len(scope),
        "stations_with_valid_threshold": len(thresholds),
        "gage_height_observations_used": observation_count,
        "stations_with_flood_days": len(results),
        "rows_written": len(results),
    }


def main():
    try:
        config = json.load(sys.stdin)
        if not isinstance(config, dict):
            raise AnalysisError("stdin must contain one JSON object")
        result = run(config)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (AnalysisError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    sys.exit(main())
