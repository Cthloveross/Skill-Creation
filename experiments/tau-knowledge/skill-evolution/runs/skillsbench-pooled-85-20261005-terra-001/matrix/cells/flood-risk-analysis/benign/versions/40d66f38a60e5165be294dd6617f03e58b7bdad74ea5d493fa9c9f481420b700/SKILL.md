---
name: flood-risk-from-local-gage-data
description: Build a flood-results CSV from a supplied USGS station scope together with locally available NWS flood-stage metadata and USGS instantaneous gage-height exports. Use when flood days must be calculated from daily maxima of parameter 00065 over an inclusive date interval.
---

# Flood risk from local gage data

Run `scripts/build_flood_results.py` to create the required CSV. It preserves station IDs as strings, restricts results to IDs present in the supplied station-scope file, and writes exactly `station_id,flood_days`. Only positive findings are written.

A flood day is calculated from the maximum **instantaneous gage height** (`00065`, stage, or gage-height field) observed on a calendar date. A daily maximum is a flood day when it is **greater than or equal to** (`>=`) a valid numeric NWS flood stage. Streamflow/discharge (`00060`) is not interchangeable with gage height and is never used as a threshold comparison.

## Evidence prerequisites

A completed finding needs both of these independent local sources:

1. NWS All Gauges Report data containing a USGS station-ID field (such as `usgs id`) and a numeric `flood stage` field.
2. USGS instantaneous-value data containing station ID, timestamp, and parameter `00065`/gage-height/stage values for every calendar date in the requested interval.

The supplied station file establishes output scope only. It does not establish an NWS flood threshold, and a streamflow record does not establish a gage height. The declared runtime has no network access, so do not claim that NWS or USGS data was downloaded. Do not invent thresholds, station findings, or flood-day counts merely to make a nonempty CSV.

Stage the required public source exports under `/root/data`, or pass their paths explicitly. The helper can parse CSV, TSV, RDB, simple JSON records, and USGS NWIS JSON; it can also discover supported local files beneath `/root/data` without relying on a fixed filename.

When prerequisite evidence is absent, the helper still creates the requested header-only artifact and reports `analysis_complete: false` plus warnings on stdout. That is a diagnostic artifact, not a completed analysis. A nonempty result is justified only by valid threshold and instantaneous-gage-height evidence.

## Run

```bash
python3 scripts/build_flood_results.py <<'JSON'
{
  "input_path": "/root/data/michigan_stations.txt",
  "output_path": "/root/output/flood_results.csv",
  "start_date": "2025-04-01",
  "end_date": "2025-04-07",
  "discover_local_data": true
}
JSON
```

For deterministic source selection, pass staged source files explicitly:

```json
{
  "input_path": "/root/data/michigan_stations.txt",
  "output_path": "/root/output/flood_results.csv",
  "threshold_path": "/root/data/nwps_all_gauges_report.csv",
  "observation_paths": ["/root/data/usgs_iv_apr_2025.rdb"],
  "discover_local_data": false
}
```

## JSON interface and validation

The script receives one JSON object on stdin:

- `input_path` and `output_path` are required strings.
- `threshold_path` is an optional local NWS export path.
- `observation_paths` is an optional array of local USGS export paths.
- `discover_local_data` is an optional boolean and defaults to `true`.
- `start_date` and `end_date` are optional inclusive ISO dates and default to `2025-04-01` and `2025-04-07`.

It emits a JSON summary on stdout and writes a UTF-8 CSV at `output_path`. `ok` indicates that the emitted CSV passed structural validation. `analysis_complete` is true only when at least one thresholded station has usable gage-height coverage for every requested date. `incomplete_observation_stations` identifies thresholded stations excluded because not all dates had a gage-height reading.

Before reporting success, the script rereads the CSV and validates the exact header, unique in-scope IDs, positive integer counts, count upper bound, and deterministic ordering. Results are sorted by descending flood-day count and then station ID.
