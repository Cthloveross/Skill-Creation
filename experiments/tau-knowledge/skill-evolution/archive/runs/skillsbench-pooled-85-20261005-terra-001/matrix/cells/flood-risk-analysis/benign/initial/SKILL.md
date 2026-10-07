---
name: flood-risk-from-gage-records
description: Create the requested flood-results CSV from supplied USGS gage-height records and NWS flood-stage metadata. Use when flood days must be counted from daily maximum stage (USGS parameter 00065) over an inclusive date range, while preserving string station IDs.
---

# Flood risk from gage records

Use `scripts/build_flood_results.py` to produce a CSV of stations whose daily maximum gage height reached or exceeded their valid NWS flood-stage threshold.

## Required evidence and assumptions

The analysis requires both of these data types, joined by station ID:

- instantaneous (or daily) **gage height**, identified by parameter `00065`, `gage height`, or a non-flood `stage` field; and
- a numeric **flood stage** threshold, identified by a `flood stage`-like field.

The supplied primary file may contain both types. If it does not, provide a separate threshold file using `threshold_path`. The script deliberately does not treat streamflow/discharge (`00060`) as gage height, invent a threshold, or query the network. Thus, if the supplied inputs contain only station IDs, only discharge, or no usable flood-stage threshold, execution fails with an actionable error rather than producing unsupported flood results.

The parser discovers common JSON, CSV, TSV, USGS RDB, and whitespace-table schemas at runtime. It recognizes common station, timestamp, stage, and threshold field names rather than assuming a particular export layout. For unconventional text, convert it first to a delimited table with a station-ID column, a timestamp/date column, a `00065` (or gage-height) column, and a `flood stage` column, or put the threshold column in a second file.

## Run

The script accepts one JSON object on standard input and emits a JSON execution summary on standard output. Run it from the Skill package directory, for example:

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

If NWS threshold metadata is supplied separately, add (for example) `"threshold_path": "/root/data/nws_all_gauges.csv"`. The threshold file may be the NWS All Gauges Report; its `usgs id` and `flood stage` columns are recognized.

### JSON input schema

- `input_path` (string, required): primary gage-record input.
- `output_path` (string, required): CSV to create. Its parent directory is created if needed.
- `threshold_path` (string, optional): a separate file containing station IDs and numeric flood stages.
- `start_date` / `end_date` (string, optional): inclusive ISO calendar boundaries. Defaults are `2025-04-01` and `2025-04-07` for this task.

## Result and validation

The created CSV is UTF-8 CSV with exactly these columns, in this order:

```text
station_id,flood_days
```

`station_id` is always serialized as the source string (including leading zeroes), and `flood_days` is an integer. Records are limited to the inclusive requested calendar range. For each station/day the maximum valid numeric `00065` observation is compared using `>=` against that station's numeric flood stage. Only stations with one or more qualifying days are output, ordered by descending count and then station ID.

The script validates required evidence, date bounds, numeric measurements, threshold availability, and the CSV it wrote (header, row shapes, string IDs, positive integer counts, order, and no duplicates). Its JSON summary includes parsed observation and threshold counts, skipped input count, output row count, and output path. Treat a nonzero exit or an `error` summary as a data/prerequisite failure that must be resolved before claiming results.
