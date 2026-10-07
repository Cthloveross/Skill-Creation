---
name: flood-risk-analysis
description: >-
  Determine which USGS stream gage stations experienced flooding over a date
  range by joining NWS flood-stage thresholds with USGS instantaneous gage
  height (parameter 00065) data. Use when given a list of USGS station IDs and a
  date window and asked to count flood days per station and write a results CSV.
---

# Flood Risk Analysis (USGS gage height vs. NWS flood stage)

## When to use
Use this Skill when the task gives a list of USGS station IDs plus a date range
and asks how many days each station flooded (and to output a CSV of stations
with at least one flood day). The default task in this environment:

- Input station list: `/root/data/michigan_stations.txt`
- Date range: 2025-04-01 through 2025-04-07 (inclusive, all 7 days)
- Output: `/root/output/flood_results.csv` with columns `station_id`,`flood_days`
- Keep only stations with at least one flood day.

## Method (the correct, non-obvious decisions)
1. **Join two data sources by station ID (as strings).** NWS All Gauges Report
   gives the `flood stage` (feet) per `usgs id`. USGS NWIS gives actual water
   levels. Station IDs may have leading zeros (e.g. `00123456`) and must be
   kept as strings, never parsed as integers.
2. **Use gage height, parameter code `00065`** (not discharge `00060`). Flood
   stage is defined in feet of gage height; discharge is in cfs and is wrong.
3. **Instantaneous values are sub-daily (~15 min).** Resample to daily
   frequency taking the **daily maximum** per calendar day. Do not use the mean
   or compare individual readings.
4. **Flood day test is `daily_max >= flood_stage`** (greater-than-or-equal). A
   day whose daily max exactly equals the flood stage counts as a flood day.
5. **Only analyze stations that appear in the NWS report with a valid numeric
   flood stage.** Blank / non-numeric flood stages are missing data; exclude
   those stations. Stations in the input list without an NWS threshold are
   excluded (not analyzed with a default).
6. **Filter output to stations with >= 1 flood day** and sort by `flood_days`
   descending (tie-break by `station_id`).
7. **Date range must cover all intended calendar days.** Query NWIS for the
   full window and, after resampling, restrict the daily series to days within
   the requested range before counting.

## Files
- `scripts/flood_analysis.py` — end-to-end entrypoint. Reads JSON config on
  stdin, downloads the NWS report, retrieves USGS IV gage-height data, computes
  flood days, writes the output CSV, and prints a JSON summary on stdout.
- `scripts/helpers.py` — reusable functions (station parsing, column
  detection, NWS threshold loading, daily-max flood counting).
- `references/method.md` — detailed notes and failure modes.

## How to run
The environment allows internet. `dataretrieval` provides USGS access; if it is
not installed, install it first:

```
pip install dataretrieval pandas requests >/dev/null 2>&1 || true
```

Run the pipeline with defaults for this task:

```
echo '{}' | python3 /app/environment/skills/current/scripts/flood_analysis.py
```

Or override any field (all optional; defaults match the task):

```
echo '{"station_file":"/root/data/michigan_stations.txt",\
       "start_date":"2025-04-01","end_date":"2025-04-07",\
       "output_path":"/root/output/flood_results.csv"}' \
  | python3 /app/environment/skills/current/scripts/flood_analysis.py
```

### Input JSON schema (stdin)
All keys optional; defaults shown:
- `station_file` (str): path to the station-ID list. Default
  `/root/data/michigan_stations.txt`.
- `start_date` (str, `YYYY-MM-DD`): default `2025-04-01`.
- `end_date` (str, `YYYY-MM-DD`, inclusive): default `2025-04-07`.
- `output_path` (str): default `/root/output/flood_results.csv`.
- `nws_report_url` (str): default the NWS All Gauges Report URL.

### Output JSON schema (stdout)
- `output_path`: path written.
- `stations_in_list`: count of parsed input stations.
- `stations_with_threshold`: count matched to a valid NWS flood stage.
- `flooded_stations`: count written to the CSV (>=1 flood day).
- `results`: list of `{station_id, flood_days}` (same as CSV rows).
- `errors`: list of per-station retrieval errors (station treated as 0 days).

The CSV at `output_path` has header `station_id,flood_days`, string station
IDs preserving leading zeros, integer counts, sorted by `flood_days`
descending.

## Executor guidance
1. Inspect the input file first: `head /root/data/michigan_stations.txt` to
   confirm it is a list of USGS IDs. The parser extracts 8+ digit tokens and
   keeps them as strings.
2. Run the entrypoint. Read the stdout JSON `errors` list — transient network
   failures for a station can be retried by re-running; a station with no data
   simply contributes 0 flood days and is excluded.
3. Confirm the CSV exists and has the two required columns:
   `cat /root/output/flood_results.csv`.
4. If `dataretrieval` import fails, install it (see above) and re-run. If the
   NWS report download fails, re-run; the URL is the only threshold source.

## Validation (run after producing output)
- `python3 -c "import pandas as pd; d=pd.read_csv('/root/output/flood_results.csv', dtype={'station_id':str}); assert list(d.columns)==['station_id','flood_days']; assert (d['flood_days']>=1).all(); assert d['flood_days'].dtype.kind in 'iu'; print(d)"`
- Verify every output station appeared in the input list and had a numeric NWS
  flood stage (see stdout `stations_with_threshold`).

Do not hardcode station IDs or counts; always derive them from the supplied
input file and live data at runtime.
