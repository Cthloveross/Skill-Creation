#!/usr/bin/env python3
"""Build a NWS-threshold/USGS-gage-height flood-days CSV.

Reads JSON from stdin (input_path, output_path, start_date, end_date) and emits a
JSON status document on stdout.  Only Python's standard library is required.
"""
import csv
import datetime as dt
import io
import json
import math
import os
import re
import sys
import time
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

NWS_REPORT_URL = "https://water.noaa.gov/resources/downloads/reports/nwps_all_gauges_report.csv"
USGS_IV_URL = "https://waterservices.usgs.gov/nwis/iv/"
ID_TOKEN = re.compile(r"(?<!\d)(\d{8,15})(?!\d)")


def fetch_bytes(url, attempts=3):
    """Fetch URL with bounded retries and an explicit user agent."""
    last_error = None
    for attempt in range(attempts):
        try:
            request = Request(url, headers={"User-Agent": "usgs-nws-flood-days/1.0"})
            with urlopen(request, timeout=90) as response:
                return response.read()
        except Exception as exc:  # Network errors should not create partial CSVs.
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(1 + attempt)
    raise RuntimeError("Unable to retrieve %s: %s" % (url, last_error))


def clean_id(value):
    """Return a digit-only identifier without numeric coercion, or None."""
    text = str(value).strip().strip('"').strip("'")
    if re.fullmatch(r"\d{8,15}", text):
        return text
    # Some CSV producers serialize an otherwise textual ID as 04123456.0.
    match = re.fullmatch(r"(\d{8,15})\.0+", text)
    return match.group(1) if match else None


def read_station_ids(path):
    """Extract ordered, unique USGS-like numeric IDs from a supplied list file."""
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise RuntimeError("Cannot read input_path %r: %s" % (path, exc))
    ids = []
    seen = set()
    # Accept one-ID-per-line, CSV fields, or records containing an ID token.
    for match in ID_TOKEN.finditer(text):
        station_id = match.group(1)
        if station_id not in seen:
            seen.add(station_id)
            ids.append(station_id)
    if not ids:
        raise RuntimeError("No 8- to 15-digit station IDs were found in input_path")
    return ids


def normalized_header(name):
    return " ".join(str(name).replace("_", " ").strip().lower().split())


def numeric_value(value):
    """Convert a finite numeric field to float; invalid values return None."""
    try:
        result = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def load_thresholds(station_ids):
    raw = fetch_bytes(NWS_REPORT_URL)
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise RuntimeError("NWS report has no CSV header")
    fields = {normalized_header(field): field for field in reader.fieldnames}
    id_field = fields.get("usgs id")
    stage_field = fields.get("flood stage")
    if not id_field or not stage_field:
        raise RuntimeError("NWS report does not contain 'usgs id' and 'flood stage' fields")

    wanted = set(station_ids)
    thresholds = {}
    for row in reader:
        station_id = clean_id(row.get(id_field, ""))
        if station_id not in wanted or station_id in thresholds:
            continue
        stage = numeric_value(row.get(stage_field, ""))
        if stage is not None:
            thresholds[station_id] = stage
    return thresholds


def chunks(items, size):
    for offset in range(0, len(items), size):
        yield items[offset:offset + size]


def retrieve_daily_maxima(station_ids, start_date, end_date):
    """Return {station_id: {ISO-date: max_gage_height}} from USGS IV JSON."""
    query_end = end_date + dt.timedelta(days=1)
    maxima = defaultdict(dict)
    for group in chunks(station_ids, 40):
        params = {
            "format": "json",
            "sites": ",".join(group),
            "parameterCd": "00065",
            "startDT": start_date.isoformat(),
            "endDT": query_end.isoformat(),
            "siteStatus": "all",
        }
        payload = fetch_bytes(USGS_IV_URL + "?" + urlencode(params))
        try:
            document = json.loads(payload.decode("utf-8"))
            series_list = document["value"]["timeSeries"]
        except (UnicodeDecodeError, ValueError, KeyError, TypeError) as exc:
            raise RuntimeError("USGS IV response could not be parsed: %s" % exc)
        if not isinstance(series_list, list):
            raise RuntimeError("USGS IV response has an invalid timeSeries field")
        for series in series_list:
            try:
                station_id = clean_id(series["sourceInfo"]["siteCode"][0]["value"])
                value_sets = series["values"]
            except (KeyError, IndexError, TypeError):
                continue
            if station_id not in station_ids:
                continue
            for value_set in value_sets:
                for observation in value_set.get("value", []):
                    timestamp = str(observation.get("dateTime", ""))
                    day_text = timestamp[:10]
                    try:
                        day = dt.date.fromisoformat(day_text)
                    except ValueError:
                        continue
                    if day < start_date or day > end_date:
                        continue
                    height = numeric_value(observation.get("value"))
                    if height is None:
                        continue
                    old = maxima[station_id].get(day_text)
                    if old is None or height > old:
                        maxima[station_id][day_text] = height
    return maxima


def validate_output(path, maximum_days):
    with open(path, "r", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader, None)
        if header != ["station_id", "flood_days"]:
            raise RuntimeError("Output validation failed: incorrect CSV header")
        seen = set()
        rows = 0
        for row in reader:
            if len(row) != 2 or not row[0] or row[0] in seen:
                raise RuntimeError("Output validation failed: invalid or duplicate station row")
            try:
                count = int(row[1])
            except ValueError:
                raise RuntimeError("Output validation failed: non-integer flood_days")
            if count < 1 or count > maximum_days or str(count) != row[1]:
                raise RuntimeError("Output validation failed: out-of-range flood_days")
            seen.add(row[0])
            rows += 1
    return rows


def run(config):
    required = ["input_path", "output_path", "start_date", "end_date"]
    missing = [key for key in required if not isinstance(config.get(key), str) or not config[key].strip()]
    if missing:
        raise RuntimeError("Missing required string input(s): " + ", ".join(missing))
    try:
        start_date = dt.date.fromisoformat(config["start_date"])
        end_date = dt.date.fromisoformat(config["end_date"])
    except ValueError:
        raise RuntimeError("start_date and end_date must be ISO dates (YYYY-MM-DD)")
    if end_date < start_date:
        raise RuntimeError("end_date must be on or after start_date")

    station_ids = read_station_ids(config["input_path"])
    thresholds = load_thresholds(station_ids)
    maxima = retrieve_daily_maxima(list(thresholds), start_date, end_date) if thresholds else {}
    results = []
    for station_id, threshold in thresholds.items():
        flooded = sum(1 for height in maxima.get(station_id, {}).values() if height >= threshold)
        if flooded:
            results.append((station_id, flooded))
    results.sort(key=lambda item: (-item[1], item[0]))

    output_path = Path(config["output_path"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["station_id", "flood_days"])
        writer.writerows(results)
    rows = validate_output(output_path, (end_date - start_date).days + 1)
    return {
        "ok": True,
        "output_path": str(output_path),
        "input_station_count": len(station_ids),
        "threshold_station_count": len(thresholds),
        "result_station_count": rows,
    }


def main():
    try:
        config = json.load(sys.stdin)
        if not isinstance(config, dict):
            raise RuntimeError("stdin JSON must be an object")
        result = run(config)
        print(json.dumps(result, sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
