#!/usr/bin/env python3
"""End-to-end flood-risk analysis entrypoint.

Reads a JSON config on stdin (all keys optional; defaults match the task),
downloads the NWS All Gauges Report for flood-stage thresholds, retrieves USGS
instantaneous gage-height data (parameter 00065) for each station with a valid
threshold, counts flood days (daily max >= flood stage) within the date range,
writes the results CSV (stations with >=1 flood day, sorted descending), and
prints a JSON summary on stdout.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import helpers  # noqa: E402

DEFAULTS = {
    "station_file": "/root/data/michigan_stations.txt",
    "start_date": "2025-04-01",
    "end_date": "2025-04-07",
    "output_path": "/root/output/flood_results.csv",
    "nws_report_url": "https://water.noaa.gov/resources/downloads/reports/nwps_all_gauges_report.csv",
}


def retrieve_iv(station, start_date, end_date):
    """Return an IV DataFrame for one station or None. Raises on hard failure."""
    from dataretrieval import nwis

    res = nwis.get_iv(
        sites=station,
        parameterCd="00065",
        start=start_date,
        end=end_date,
    )
    if isinstance(res, tuple):
        df = res[0]
    else:
        df = res
    return df


def run(config):
    import pandas as pd

    cfg = dict(DEFAULTS)
    cfg.update(config or {})

    stations = helpers.parse_station_ids(cfg["station_file"])
    thresholds = helpers.load_nws_thresholds(cfg["nws_report_url"])

    analyzable = [(s, thresholds[s]) for s in stations if s in thresholds]

    results = []
    errors = []
    for sid, stage in analyzable:
        try:
            df = retrieve_iv(sid, cfg["start_date"], cfg["end_date"])
        except Exception as exc:  # transient / no-data; treat as 0 days
            errors.append({"station_id": sid, "error": str(exc)})
            continue
        series = helpers.gage_height_series(df)
        days = helpers.count_flood_days(
            series, stage, cfg["start_date"], cfg["end_date"]
        )
        if days >= 1:
            results.append({"station_id": sid, "flood_days": int(days)})

    results.sort(key=lambda r: (-r["flood_days"], r["station_id"]))

    out_path = cfg["output_path"]
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    out_df = pd.DataFrame(results, columns=["station_id", "flood_days"])
    out_df["station_id"] = out_df["station_id"].astype(str)
    out_df.to_csv(out_path, index=False)

    return {
        "output_path": out_path,
        "stations_in_list": len(stations),
        "stations_with_threshold": len(analyzable),
        "flooded_stations": len(results),
        "results": results,
        "errors": errors,
    }


def main():
    raw = sys.stdin.read().strip()
    config = json.loads(raw) if raw else {}
    summary = run(config)
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
