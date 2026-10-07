#!/usr/bin/env python3
"""End-to-end entrypoint for the econ-detrending-correlation Skill.

Stdin (optional) JSON overrides:
  pce_file, pfi_file, cpi_file : paths to the two ERP .xls tables and CPI.xlsx
  start_year, end_year         : inclusive year range (default 1973..2024)
  lam                          : HP smoothing parameter (default 100)
  output                       : answer file path (default /root/answer.txt)
  pce_year_col/pce_total_col, pfi_year_col/pfi_total_col : optional manual
      column overrides if auto-detection picks the wrong column.

Stdout: JSON with the correlation, the rounded string, the years used, and
debug info. Also writes the rounded coefficient to `output`.
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import econ_utils as eu  # noqa: E402


def main():
    raw = ""
    try:
        raw = sys.stdin.read()
    except Exception:
        raw = ""
    cfg = {}
    if raw and raw.strip():
        try:
            cfg = json.loads(raw)
        except Exception:
            cfg = {}

    pce_file = cfg.get("pce_file", "/root/ERP-2025-table10.xls")
    pfi_file = cfg.get("pfi_file", "/root/ERP-2025-table12.xls")
    cpi_file = cfg.get("cpi_file", "/root/CPI.xlsx")
    start_year = int(cfg.get("start_year", 1973))
    end_year = int(cfg.get("end_year", 2024))
    lam = float(cfg.get("lam", 100))
    output = cfg.get("output", "/root/answer.txt")

    pce, pce_dbg = eu.extract_erp_totals(
        pce_file, cfg.get("pce_year_col"), cfg.get("pce_total_col"))
    pfi, pfi_dbg = eu.extract_erp_totals(
        pfi_file, cfg.get("pfi_year_col"), cfg.get("pfi_total_col"))
    cpi = eu.extract_cpi_annual(cpi_file)

    years = list(range(start_year, end_year + 1))
    missing = {
        "pce": [y for y in years if y not in pce],
        "pfi": [y for y in years if y not in pfi],
        "cpi": [y for y in years if y not in cpi],
    }
    if any(missing.values()):
        print(json.dumps({"error": "missing years", "missing": missing,
                          "pce_debug": pce_dbg, "pfi_debug": pfi_dbg,
                          "cpi_years": sorted(cpi.keys())}, default=str))
        sys.exit(2)

    real_pce = [pce[y] / cpi[y] for y in years]
    real_pfi = [pfi[y] / cpi[y] for y in years]
    log_pce = [math.log(v) for v in real_pce]
    log_pfi = [math.log(v) for v in real_pfi]

    _, cyc_pce = eu.hp_filter(log_pce, lam)
    _, cyc_pfi = eu.hp_filter(log_pfi, lam)

    corr = eu.pearson(cyc_pce, cyc_pfi)
    rounded = "%.5f" % round(corr, 5)

    with open(output, "w") as fh:
        fh.write(rounded + "\n")

    print(json.dumps({
        "correlation": corr,
        "rounded": rounded,
        "years": years,
        "n": len(years),
        "output_path": output,
        "debug": {
            "pce": pce_dbg,
            "pfi": pfi_dbg,
            "cpi_years": len(cpi),
            "pce_end_source": pce_dbg["source"].get(end_year),
            "pfi_end_source": pfi_dbg["source"].get(end_year),
        },
    }, default=str))


if __name__ == "__main__":
    main()
