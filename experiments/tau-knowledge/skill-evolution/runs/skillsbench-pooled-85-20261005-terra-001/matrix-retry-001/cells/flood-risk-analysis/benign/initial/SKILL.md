---
name: flood-day-from-gage-height
description: Produce a CSV of USGS stations with one or more flood days from local NWS flood-stage metadata and USGS instantaneous gage-height (00065) observations. Use when a date range, station IDs, an NWS All Gauges Report snapshot, and IV observations are available locally.
---

# Flood-day-from-gage-height

A flood day is a calendar day whose **maximum instantaneous gage height** is greater than or equal to that station's numeric NWS flood stage. This Skill preserves station IDs as strings, including leading zeroes, and emits only stations with at least one flood day.

## Required runtime inputs

`analyze_flood.py` receives one JSON object on stdin:

- `station_file` (string): a text list or delimited table identifying the in-scope USGS station IDs.
- `thresholds_file` (string, optional): NWS All Gauges Report CSV (or a compatible table). If omitted, `station_file` must itself contain `usgs id`/`station_id` and `flood stage` columns.
- `observations_file` (string, optional): USGS instantaneous-value snapshot. If omitted, `station_file` must itself also contain observations.
- `start_date`, `end_date` (strings): inclusive ISO dates, such as `2025-04-01`.
- `output_csv` (string): destination for the result CSV.

The thresholds table needs a station-ID column (`usgs id`, `station_id`, `site_no`, or equivalent) and `flood stage`. The observations table needs a station-ID column, a timestamp/date column, and a numeric gage-height column named `00065`, containing `00065`, or `gage_height`/`stage`. USGS RDB exports and ordinary CSV/TSV files are supported.

For example, with separately supplied local snapshots:

```sh
python3 scripts/analyze_flood.py <<'JSON'
{"station_file":"/root/data/stations.txt","thresholds_file":"/root/data/nwps_all_gauges_report.csv","observations_file":"/root/data/usgs_iv_00065.csv","start_date":"2025-04-01","end_date":"2025-04-07","output_csv":"/root/output/flood_results.csv"}
JSON
```

The script prints a JSON status object to stdout and writes `output_csv` atomically on success. Its CSV has exactly `station_id,flood_days`, is ordered by descending flood-day count then station ID, and contains only positive integer counts.

## Data and failure handling

Use a local NWS report snapshot and local USGS IV snapshot when the runtime has no network access. A station list, streamflow/discharge (`00060`) data, or a table without a numeric flood stage is insufficient to determine flood status. The script deliberately fails with a JSON error rather than inventing thresholds, treating discharge as stage, or writing an unjustified result. Blank/non-numeric flood stages are excluded. A valid data source with no qualifying flood days produces a header-only CSV.

USGS retrieval, when available outside this network-restricted runtime, must request instantaneous parameter `00065` for the whole inclusive range. Do not substitute daily means or discharge values. The supplied snapshots should retain local timestamps so daily grouping follows the gage's local calendar days.
