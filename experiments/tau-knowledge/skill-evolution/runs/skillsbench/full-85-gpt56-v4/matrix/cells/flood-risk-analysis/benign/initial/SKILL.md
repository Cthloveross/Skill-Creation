---
name: usgs-nws-flood-days
description: Create a CSV of USGS stations that reached NWS flood stage during an inclusive date range, using daily maximum instantaneous gage height. Use when supplied with a station-ID list and an internet-enabled runtime.
---

# USGS/NWS Flood-Day Analysis

This Skill joins the NWS All Gauges Report's station-specific `flood stage` with USGS NWIS instantaneous gage-height observations (`00065`). A flood day is a local calendar day whose maximum reported gage height is greater than or equal to the station's flood stage. It does not use streamflow/discharge values.

## Inputs and output

`scripts/flood_days.py` reads one JSON object from standard input and writes one JSON status object to standard output.

Input schema:

- `input_path` (string, required): text or CSV-like station list. It may contain station IDs as standalone numeric fields/tokens. IDs are retained as strings.
- `output_path` (string, required): CSV path to create.
- `start_date` (string, required): inclusive ISO date (`YYYY-MM-DD`).
- `end_date` (string, required): inclusive ISO date.

The output CSV always has exactly these columns:

```csv
station_id,flood_days
```

Only stations with valid numeric NWS flood stages and one or more flood days are written. Rows are ordered by descending `flood_days`, then station ID. A valid no-flood result is a header-only CSV.

## Run for the requested analysis

```sh
mkdir -p /root/output
printf '%s' '{"input_path":"/root/data/michigan_stations.txt","output_path":"/root/output/flood_results.csv","start_date":"2025-04-01","end_date":"2025-04-07"}' | python3 /app/environment/skills/current/scripts/flood_days.py
```

The script downloads the current NWS All Gauges Report, selects valid thresholds for supplied IDs, then calls the USGS instantaneous-values service in small batches with parameter `00065`. It requests through the day after `end_date` and filters observation timestamps back to the requested inclusive local calendar dates, so the final day is included.

## Validation and failure handling

Before reporting success, the script re-reads its CSV and verifies the exact header, unique nonempty string IDs, positive integer counts, and counts no greater than the number of requested calendar days. Its JSON success response includes station and result counts.

It fails rather than writing a silently partial analysis when the input has no recognizable station IDs, the NWS report is unavailable or lacks expected fields, or a required USGS query cannot be retrieved or parsed. Blank, nonnumeric, or non-finite NWS flood-stage entries are excluded. Network use requires the runtime's normal internet permission; no bank or other external side-effecting actions are involved.
