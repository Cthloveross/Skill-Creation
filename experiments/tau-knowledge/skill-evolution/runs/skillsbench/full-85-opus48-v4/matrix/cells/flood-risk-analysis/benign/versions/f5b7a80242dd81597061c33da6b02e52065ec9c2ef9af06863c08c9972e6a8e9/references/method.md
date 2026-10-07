# Flood-risk analysis: method and failure modes

## Pipeline
1. Parse USGS station IDs from the input file as strings (preserve leading
   zeros). Header text is ignored by extracting 8+ digit tokens.
2. Download the NWS All Gauges Report CSV and build a map `usgs id -> flood
   stage` keeping only numeric stages. Blank / non-numeric stages are missing
   data and those stations are excluded.
3. Keep only input stations that have a valid NWS threshold.
4. For each such station, retrieve USGS NWIS instantaneous values for parameter
   code `00065` (gage height, feet) over the date range using
   `dataretrieval.nwis.get_iv`.
5. Select gage-height columns (containing `00065`, excluding `_cd` qualifier
   columns), coerce to numeric, resample to daily **maximum**.
6. Count calendar days within the requested inclusive range where
   `daily_max >= flood_stage`.
7. Output stations with `flood_days >= 1`, sorted by `flood_days` descending.

## Critical correctness points (easy to get wrong)
- **Gage height, not discharge.** Parameter `00065` (feet), never `00060`
  (cfs). Discharge values are in incompatible units.
- **Daily maximum**, not mean and not per-reading comparison. Flooding is a
  peak condition.
- **`>=` comparison**, not strict `>`. A daily max equal to flood stage is a
  flood day; strict `>` undercounts.
- **String station IDs** throughout so leading zeros match the NWS `usgs id`
  and the input list.
- **Scope to stations with valid thresholds.** Never assume a default flood
  stage for stations absent from the NWS report.
- **Full date range.** Query the whole window and restrict the daily series to
  the requested inclusive days before counting, so partial boundary days from
  the API do not add or drop days.

## Resilience
- A station with no returned data contributes 0 flood days and is excluded.
- Per-station retrieval exceptions are recorded in the stdout `errors` list and
  do not abort the run; re-running retries them (network is available).
- If `dataretrieval` is not importable, install it:
  `pip install dataretrieval pandas requests`.

## Output contract
CSV at the output path with exactly `station_id,flood_days`, string IDs with
leading zeros preserved, integer counts, only stations with at least one flood
day, sorted by flood_days descending.
