---
name: flood-risk-from-local-gage-data
description: Create a flood-results CSV from a supplied USGS station scope plus locally staged NWS flood-stage metadata and USGS instantaneous gage-height exports. Apply when flood days must be counted from daily maximum parameter 00065 observations over an inclusive date range.
---

# Flood risk from local gage data

Use `scripts/build_flood_results.py` to produce the requested result. The script treats station IDs as strings, limits output to IDs found in the supplied station-scope file, and writes `station_id,flood_days` with only positive findings.

For every in-scope station with a valid numeric NWS flood stage, it takes the maximum **gage height** for each calendar date in the requested inclusive window and counts a flood day when that maximum is **greater than or equal to** (`>=`) the flood stage. It uses USGS parameter `00065`/gage-height/stage fields only; it never compares flood stage with streamflow or discharge (`00060`). Qualifier columns such as `00065_cd` are ignored.

## Required local evidence

Flood findings require both of these sources:

1. NWS All Gauges Report data with a USGS station-ID field (for example, `usgs id`) and a numeric `flood stage` field.
2. USGS instantaneous observation data with station ID, a timestamp, and a numeric `00065`, `gage height`, or `stage` field for April 1 through April 7, 2025.

The declared runtime has no network access. Do not claim a download succeeded and do not invent a threshold, observation, qualifying station, or flood-day count from a station list alone. Stage public source exports under `/root/data` before running the analysis, or pass their local paths explicitly. The helper supports CSV, TSV, USGS RDB, and simple JSON records and can discover supported files below `/root/data` without assuming a filename.

When the only available file is a station list, the helper still creates a structurally valid CSV for the requested destination and emits `analysis_complete: false` with warnings. That header-only artifact is a prerequisite diagnostic, **not a completed flood analysis**. Obtain the two required local sources and rerun; never add an arbitrary positive row merely to make an incomplete analysis nonempty.

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

For deterministic source selection, specify staged files explicitly:

```json
{
  "input_path": "/root/data/michigan_stations.txt",
  "output_path": "/root/output/flood_results.csv",
  "threshold_path": "/root/data/nwps_all_gauges_report.csv",
  "observation_paths": ["/root/data/usgs_iv_apr_2025.rdb"],
  "discover_local_data": false
}
```

## Input and output contract

The script receives one JSON object on stdin:

- `input_path` and `output_path` are required strings.
- `threshold_path` is an optional local NWS export path.
- `observation_paths` is an optional array of local USGS export paths.
- `discover_local_data` is an optional boolean, defaulting to `true`.
- `start_date` and `end_date` are optional inclusive ISO dates, defaulting to `2025-04-01` and `2025-04-07`.

It writes the UTF-8 CSV and emits a JSON summary on stdout. `ok` means the CSV passed structural validation. `analysis_complete` is true only when usable in-scope thresholds and in-window gage-height observations were found; inspect warnings before treating an empty result as meaningful.

The helper rereads its output and validates the exact header, unique in-scope station IDs, positive integer counts, and the date-window upper bound. Results are ordered by descending flood-day count and then station ID.
