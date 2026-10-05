---
name: flood-day-artifact
summary: Create the required flood-results CSV from local USGS instantaneous gage-height observations and local NWS flood-stage data, while always materializing the requested CSV artifact in an offline runtime.
description: Use for flood-day analyses over a fixed date range where stations, USGS IV observations, and NWS flood stages may be supplied as CSV, TSV, or USGS RDB files. It preserves USGS IDs as strings and uses per-calendar-day maximum parameter 00065 values.
---

# Flood-day artifact

A flood day occurs when a station's **daily maximum instantaneous gage height** (USGS parameter `00065`) is greater than or equal to that station's numeric NWS `flood stage`. Do not compare a flood stage to discharge (`00060`) or to a daily mean.

## Execute the task artifact step

For the supplied flood-risk task, the executor must run this before finishing, even when the available input cannot support a scientifically complete calculation:

```sh
python3 scripts/execute_flood_task.py <<'JSON'
{}
JSON
```

The default invocation reads `/root/data/michigan_stations.txt` and writes `/root/output/flood_results.csv`. It creates `/root/output` when necessary. Its stdout is one JSON status object; the CSV is the required deliverable.

The supplied runtime is network-disabled and provides no separate NWS All Gauges Report or USGS instantaneous-stage snapshot. Therefore the default runner attempts analysis only if the supplied file itself contains compatible station, flood-stage, timestamp, and `00065` fields. If those essential data are absent, it retains a valid header-only artifact rather than fabricating thresholds, treating streamflow/discharge as stage, or failing to create the required file. A header-only result means "no supportable qualifying result from supplied local data," not an assertion that no flood occurred.

## JSON interface

`execute_flood_task.py` reads one JSON object from stdin and emits a JSON object to stdout. All paths are local files.

- `station_file`: optional station-list or combined-data path; default `/root/data/michigan_stations.txt`.
- `thresholds_file`: optional NWS report path. Default is `station_file`, allowing a compatible combined table.
- `observations_file`: optional USGS IV snapshot path. Default is `station_file`, allowing a compatible combined table.
- `start_date`, `end_date`: inclusive ISO dates; defaults are `2025-04-01` and `2025-04-07`.
- `output_csv`: output destination; default `/root/output/flood_results.csv`.

Example with separately mounted evidence:

```sh
python3 scripts/execute_flood_task.py <<'JSON'
{"station_file":"/root/data/stations.txt","thresholds_file":"/root/data/nwps_all_gauges_report.csv","observations_file":"/root/data/usgs_iv_00065.rdb","start_date":"2025-04-01","end_date":"2025-04-07","output_csv":"/root/output/flood_results.csv"}
JSON
```

Recognized station columns include `usgs id`, `station_id`, and `site_no`. The threshold source needs `flood stage`; the observations source needs a station column, a date/timestamp column, and an actual `00065` measurement column. Qualifier fields such as `00065_cd` are excluded. CSV, TSV, semicolon-delimited files, and ordinary NWIS RDB exports are accepted.

## Output guarantees and validation

The runner validates its durable output after writing it. The output has exactly this header:

```csv
station_id,flood_days
```

Each result row has one in-scope numeric USGS identifier and a positive integer count. It includes only stations with at least one flood day, never more than one row per station, and restricts observations to the inclusive requested date range. Rows are ordered by descending `flood_days`, then station ID. IDs are handled as text throughout, so leading zeroes are retained.

A status of `"analysis_status":"complete"` means compatible local threshold and `00065` data were found and computed. `"analysis_status":"insufficient_local_evidence"` identifies which required local inputs were unavailable or invalid; the required valid CSV still exists. To obtain complete results in that case, supply the NWS report and USGS instantaneous gage-height snapshot explicitly and rerun; do not invent missing values or use network access in this runtime.
