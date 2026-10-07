---
name: flood-risk-from-gage-records
description: Create the required flood-results CSV from a supplied USGS station list plus local USGS gage-height observations and NWS flood-stage metadata. Use when flood days are determined from daily maximum parameter 00065 stage over an inclusive date range while preserving station IDs as strings.
---

# Flood risk from gage records

Run `scripts/build_flood_results.py` to create `/root/output/flood_results.csv`. The output is always created with the required header when the supplied station-list file can be read, including when the available public data cannot support a flood determination.

## Evidence required for a nonempty result

A defensible flood-day count requires both of the following, joined on station ID:

- dated USGS **gage-height** observations for parameter `00065` (or an explicitly named gage-height/stage field); and
- a valid numeric NWS **flood stage** threshold.

For each station and each calendar day in the requested inclusive range, use the maximum gage-height observation for that day. Count the day if that maximum is `>=` the station's flood stage. Do not use streamflow/discharge parameter `00060`, daily mean stage, an invented threshold, or a strict `>` comparison.

The provided `michigan_stations.txt` is the authoritative station scope: only numeric USGS-style IDs found in that file can be emitted. IDs are handled as strings so leading zeroes are retained. Stations with missing/non-numeric thresholds, no qualifying observations, or zero flood days are omitted.

The task runtime has no network access. Do not attempt to download the NWS All Gauges Report or USGS observations. If they are made available as local files, pass the NWS file with `threshold_path`; observations may be in `input_path` when it is a records export. If the supplied primary file is only a station list and no local observations/thresholds exist, the only supportable output is a header-only CSV. This is an explicit incomplete-analysis state, not evidence that stations had zero flooding.

## Run

Run from the Skill package directory:

```bash
python3 scripts/build_flood_results.py <<'JSON'
{
  "input_path": "/root/data/michigan_stations.txt",
  "output_path": "/root/output/flood_results.csv",
  "start_date": "2025-04-01",
  "end_date": "2025-04-07"
}
JSON
```

When local NWS threshold metadata is available, add `"threshold_path": "/root/data/nws_all_gauges.csv"`. The helper recognizes the NWS report's `usgs id` and `flood stage` fields, as well as common CSV, TSV, USGS RDB, whitespace-table, and JSON record layouts.

### JSON input schema

- `input_path` (string, required): supplied station list or a local gage-record export. This establishes allowed output station IDs.
- `output_path` (string, required): destination CSV; parent directories are created.
- `threshold_path` (string, optional): local threshold metadata, such as the NWS All Gauges Report.
- `start_date` and `end_date` (optional strings): inclusive ISO dates, defaulting to `2025-04-01` and `2025-04-07`.

## Output and validation

The helper emits a JSON summary to stdout. `ok: true` means the CSV was written. Check `analysis_complete`: it is true only if usable observations and valid thresholds were present. Its `warnings` explain unavailable prerequisites.

The created UTF-8 CSV has exactly this header:

```text
station_id,flood_days
```

Every data row has a unique scoped numeric `station_id` and a positive integer `flood_days`. Counts are naturally bounded by the number of inclusive requested days. Results are ordered by descending flood-day count and then station ID. The helper rereads and validates the generated CSV before reporting success.
