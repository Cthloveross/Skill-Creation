---
name: flood-risk-from-local-gage-data
description: Build a flood-results CSV for a supplied USGS station scope using locally available NWS flood-stage metadata and dated USGS instantaneous gage-height records. Use for inclusive-date flood-day analysis based on daily maximum parameter 00065 gage height.
---

# Flood risk from local gage data

Use `scripts/build_flood_results.py` to create the requested CSV. It preserves USGS station IDs as strings, joins only stations in the supplied station-list scope to valid numeric NWS flood stages, and reports only stations with one or more flood days.

A flood-day finding requires both a valid NWS flood-stage threshold and dated gage-height observations. For every calendar day in the inclusive range, take the maximum instantaneous **gage height** (USGS parameter `00065`) and count the day when that maximum is `>=` the flood stage. Do not compare flood stage to discharge/streamflow (`00060`), use a daily mean, or use a strict greater-than comparison.

The runtime has no network access. Do not try to download data. The helper can use:

- the supplied primary file, when it contains records as well as station IDs;
- explicitly supplied local `threshold_path` and `observation_paths`; and
- other CSV, TSV, RDB, or JSON files below `/root/data` when `discover_local_data` is true.

This discovery allows an executor to use locally staged NWS All Gauges Report and USGS exports without assuming their filenames. A NWS threshold source needs a station-ID field (for example `usgs id`) and a `flood stage` field. Observation records need station ID, date/time, and a `00065`, `gage height`, or `stage` field. Qualifier fields such as `00065_cd` are ignored.

If neither required data source is locally available, the helper still writes a syntactically valid header-only CSV and reports `analysis_complete: false` plus actionable warnings. That state means flooding cannot be determined from the supplied evidence; it must not be interpreted as a zero-flood result. To produce substantive findings, stage the required public local data and rerun rather than inventing thresholds or flood days.

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

If data locations are known, give them explicitly (automatic discovery may remain enabled):

```json
{
  "input_path": "/root/data/michigan_stations.txt",
  "output_path": "/root/output/flood_results.csv",
  "threshold_path": "/root/data/nwps_all_gauges_report.csv",
  "observation_paths": ["/root/data/usgs_iv_2025-04-01_2025-04-07.rdb"]
}
```

## JSON input and result schemas

Input is one JSON object on stdin:

- `input_path` (required string): station-list or record-export path. Numeric USGS-style identifiers in this file establish the only allowed output station IDs.
- `output_path` (required string): CSV destination; its parent directory is created.
- `threshold_path` (optional string): a local NWS threshold export.
- `observation_paths` (optional array of strings): local USGS observation exports.
- `discover_local_data` (optional boolean, default `true`): scan `/root/data` for additional supported text exports.
- `start_date`, `end_date` (optional ISO dates): inclusive bounds, defaulting to 2025-04-01 through 2025-04-07.

The script emits a JSON summary to stdout. `ok` confirms that the CSV was written; `analysis_complete` describes whether both usable observations and thresholds were found. Treat warnings and unreadable supplied paths as prerequisites to resolve, not as flood findings.

## Validation

The helper rereads its output before success. The output is UTF-8 CSV with exactly:

```text
station_id,flood_days
```

Each emitted row is unique, in the station scope, has a positive integer count no greater than the inclusive date count, and is ordered by descending count then station ID.
