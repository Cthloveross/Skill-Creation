#!/usr/bin/env python3
"""Offline flood-day CSV producer. Reads JSON stdin and writes JSON stdout."""
import csv
import datetime as dt
import json
import math
import os
import re
import sys
import tempfile


class DataProblem(Exception):
    pass


def canonical(text):
    return re.sub(r"[^a-z0-9]", "", str(text).lower())


def read_table(path):
    """Read common delimited and NWIS RDB tables without coercing identifiers."""
    try:
        with open(path, encoding="utf-8-sig", newline="") as f:
            lines = [x.rstrip("\r\n") for x in f if x.strip() and not x.lstrip().startswith("#")]
    except OSError as e:
        raise DataProblem("cannot read %s: %s" % (path, e))
    if not lines:
        raise DataProblem("empty input: %s" % path)
    first = lines[0]
    delim = "\t" if "\t" in first else ("," if "," in first else (";" if ";" in first else None))
    if delim is None:
        # A plain list has no declared fields; retain probable identifiers only.
        return ["station_id"], [{"station_id": value} for value in lines]
    parsed = list(csv.reader(lines, delimiter=delim))
    headers = [v.strip() for v in parsed[0]]
    if not headers or not any(headers):
        raise DataProblem("blank table header: %s" % path)
    start = 1
    # The RDB type/width record follows its field-name header.
    if len(parsed) > 1 and parsed[1] and all(re.fullmatch(r"\d+[A-Za-z]", x.strip() or "") for x in parsed[1]):
        start = 2
    rows = []
    for values in parsed[start:]:
        if not any(v.strip() for v in values):
            continue
        values += [""] * max(0, len(headers) - len(values))
        rows.append(dict(zip(headers, (v.strip() for v in values))))
    return headers, rows


def column(headers, allowed):
    for name in headers:
        if canonical(name) in allowed:
            return name
    return None


def station_column(headers):
    return column(headers, {"stationid", "usgsid", "siteid", "siteno", "site"})


def number(value):
    try:
        value = float(str(value).strip())
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def date_from_timestamp(value):
    text = str(value).strip()
    # Preserve the source's displayed local date; do not timezone-convert it.
    if re.match(r"^\d{4}-\d{2}-\d{2}", text):
        try:
            return dt.date.fromisoformat(text[:10])
        except ValueError:
            return None
    for fmt in ("%m/%d/%Y", "%m/%d/%Y %H:%M", "%Y/%m/%d"):
        try:
            return dt.datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    return None


def source_station_ids(path):
    headers, rows = read_table(path)
    key = station_column(headers)
    ids = set()
    if key:
        ids.update(row.get(key, "").strip() for row in rows if row.get(key, "").strip())
    else:
        # Match the public USGS ID convention without converting identifiers to ints.
        for row in rows:
            ids.update(re.findall(r"(?<!\d)(\d{8,15})(?!\d)", " ".join(row.values())))
    if not ids:
        raise DataProblem("no station identifiers found in %s" % path)
    return ids


def load_thresholds(path, scope):
    headers, rows = read_table(path)
    sid = station_column(headers)
    stage = column(headers, {"floodstage"})
    if not sid or not stage:
        raise DataProblem("threshold source requires station ID and flood stage columns")
    result = {}
    for row in rows:
        station = row.get(sid, "").strip()
        value = number(row.get(stage, ""))
        if station in scope and value is not None:
            if station in result and result[station] != value:
                raise DataProblem("conflicting flood stages for station %s" % station)
            result[station] = value
    if not result:
        raise DataProblem("no in-scope numeric flood stages")
    return result


def gage_column(headers):
    for name in headers:
        c = canonical(name)
        if "00065" in c and not c.endswith("cd") and "qual" not in c:
            return name
    for name in headers:
        if canonical(name) in {"gageheight", "gageht"}:
            return name
    return None


def daily_maxima(path, scope, start, end):
    headers, rows = read_table(path)
    sid = station_column(headers)
    time = column(headers, {"datetime", "date", "timestamp", "time", "datetimestamp"})
    value = gage_column(headers)
    if not sid or not time or not value:
        raise DataProblem("observation source requires station ID, timestamp, and gage-height 00065 columns")
    maxima = {}
    for row in rows:
        station = row.get(sid, "").strip()
        day = date_from_timestamp(row.get(time, ""))
        height = number(row.get(value, ""))
        if station not in scope or day is None or height is None or not start <= day <= end:
            continue
        key = (station, day)
        maxima[key] = max(maxima.get(key, height), height)
    return maxima


def write_results(path, results):
    """Atomically write and re-read the exact required two-column CSV."""
    target_dir = os.path.dirname(os.path.abspath(path))
    os.makedirs(target_dir, exist_ok=True)
    temp = None
    try:
        fd, temp = tempfile.mkstemp(prefix=".flood_", suffix=".csv", dir=target_dir, text=True)
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, lineterminator="\n")
            writer.writerow(["station_id", "flood_days"])
            writer.writerows(results)
        os.replace(temp, path)
        temp = None
    finally:
        if temp:
            try:
                os.unlink(temp)
            except OSError:
                pass
    with open(path, encoding="utf-8", newline="") as f:
        saved = list(csv.reader(f))
    expected = [["station_id", "flood_days"]] + [[x, str(y)] for x, y in results]
    if saved != expected:
        raise DataProblem("written CSV failed validation")


def nonempty_string(config, key, default=None):
    value = config.get(key, default)
    if not isinstance(value, str) or not value.strip():
        raise DataProblem("%s must be a nonempty string" % key)
    return value


def run(config):
    station_file = nonempty_string(config, "station_file", "/root/data/michigan_stations.txt")
    output = nonempty_string(config, "output_csv", "/root/output/flood_results.csv")
    threshold_file = nonempty_string(config, "thresholds_file", station_file)
    observation_file = nonempty_string(config, "observations_file", station_file)
    try:
        start = dt.date.fromisoformat(nonempty_string(config, "start_date", "2025-04-01"))
        end = dt.date.fromisoformat(nonempty_string(config, "end_date", "2025-04-07"))
    except ValueError:
        raise DataProblem("dates must use ISO YYYY-MM-DD")
    if end < start:
        raise DataProblem("end_date precedes start_date")

    # Materialize the required artifact first. It remains valid if evidence is insufficient.
    write_results(output, [])
    try:
        scope = source_station_ids(station_file)
        thresholds = load_thresholds(threshold_file, scope)
        maxima = daily_maxima(observation_file, set(thresholds), start, end)
        counts = {}
        for (station, _day), height in maxima.items():
            if height >= thresholds[station]:
                counts[station] = counts.get(station, 0) + 1
        results = sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
        if any(not re.fullmatch(r"\d{8,15}", station) or not 1 <= days <= (end - start).days + 1
               for station, days in results):
            raise DataProblem("computed result violates station-ID or count constraints")
        write_results(output, results)
        return {"ok": True, "analysis_status": "complete", "output_csv": output,
                "rows_written": len(results), "stations_requested": len(scope)}
    except DataProblem as exc:
        return {"ok": True, "analysis_status": "insufficient_local_evidence", "output_csv": output,
                "rows_written": 0, "reason": str(exc)}


def main():
    try:
        config = json.load(sys.stdin)
        if not isinstance(config, dict):
            raise DataProblem("stdin must contain one JSON object")
        print(json.dumps(run(config), sort_keys=True))
        return 0
    except (DataProblem, json.JSONDecodeError, OSError) as exc:
        # Configuration errors before output selection are reported explicitly.
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    sys.exit(main())
