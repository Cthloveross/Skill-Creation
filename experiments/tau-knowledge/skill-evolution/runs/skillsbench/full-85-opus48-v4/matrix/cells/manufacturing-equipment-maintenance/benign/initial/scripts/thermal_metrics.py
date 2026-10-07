#!/usr/bin/env python3
"""Compute per-run, per-thermocouple reflow metrics from thermocouples.csv.

stdin config:
{
  "thermo_csv": "/app/data/thermocouples.csv",
  "columns": {"run_id":..,"tc_id":..,"time":..,"temp":..},   # optional overrides
  "preheat": {"temp_low": 50, "temp_high": 150, "boundary": "both_in_band"},
  "liquidus": 217,
  "tal_inclusive": true
}
stdout:
{
  "columns_used": {...},
  "runs": {run_id: {tc_id: {"max_preheat_ramp":float|null,
                             "tal":float, "peak":float, "n":int}}}
}
All raw (unrounded) so the caller applies the handbook rounding/selection rules.
"""
import json
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from helpers import (  # noqa: E402
    read_csv,
    detect_thermo_columns,
    group_traces,
    max_preheat_ramp,
    time_above,
    peak_temp,
)


def main():
    cfg = json.load(sys.stdin)
    header, rows = read_csv(cfg["thermo_csv"])
    cols = detect_thermo_columns(header, cfg.get("columns"))
    if any(v is None for v in cols.values()):
        print(json.dumps({"error": "could not map all columns", "detected": cols,
                          "header": header}))
        return
    traces = group_traces(rows, cols)
    ph = cfg.get("preheat", {})
    low, high = ph.get("temp_low"), ph.get("temp_high")
    boundary = ph.get("boundary", "both_in_band")
    liq = cfg.get("liquidus")
    inc = cfg.get("tal_inclusive", True)
    out = {}
    for run, tcs in traces.items():
        out[run] = {}
        for tc, samples in tcs.items():
            out[run][tc] = {
                "max_preheat_ramp": max_preheat_ramp(samples, low, high, boundary),
                "tal": time_above(samples, liq, inc) if liq is not None else None,
                "peak": peak_temp(samples),
                "n": len(samples),
            }
    print(json.dumps({"columns_used": cols, "runs": out}))


if __name__ == "__main__":
    main()
