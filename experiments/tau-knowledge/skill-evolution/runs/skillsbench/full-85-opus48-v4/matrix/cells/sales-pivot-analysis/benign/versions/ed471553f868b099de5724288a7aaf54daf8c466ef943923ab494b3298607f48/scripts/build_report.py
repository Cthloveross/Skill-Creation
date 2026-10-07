#!/usr/bin/env python3
"""End-to-end builder for the demographic pivot-table report.

stdin  (optional JSON): income_path, population_pdf, output_path, quartile_method
stdout (JSON): ok, output, sheets, rows, quartile_method, columns, warnings
"""
import json
import os
import sys
import subprocess


def _ensure(pkg, imp=None):
    imp = imp or pkg
    try:
        __import__(imp)
        return True, None
    except Exception:
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "--quiet", pkg])
            __import__(imp)
            return True, None
        except Exception as e:  # pragma: no cover
            return False, "%s: %s" % (pkg, e)


def main():
    try:
        raw = sys.stdin.read()
    except Exception:
        raw = ""
    cfg = {}
    if raw.strip():
        try:
            cfg = json.loads(raw)
        except Exception as e:
            print(json.dumps({"ok": False, "error": "bad config json: %s" % e}))
            return 1

    income_path = cfg.get("income_path", "/root/income.xlsx")
    population_pdf = cfg.get("population_pdf", "/root/population.pdf")
    output_path = cfg.get("output_path", "/root/demographic_analysis.xlsx")
    quartile_method = cfg.get("quartile_method", "range")
    warnings = []

    for pkg, imp in (("pandas", "pandas"), ("openpyxl", "openpyxl"),
                     ("pdfplumber", "pdfplumber")):
        ok, err = _ensure(pkg, imp)
        if not ok:
            print(json.dumps({"ok": False, "error": "missing dependency %s" % err}))
            return 1

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import pandas as pd
    import openpyxl
    from data_io import prepare_dataframes
    import pivot_utils as pv

    for p in (income_path, population_pdf):
        if not os.path.exists(p):
            print(json.dumps({"ok": False, "error": "input not found: %s" % p}))
            return 1

    pop, inc = prepare_dataframes(income_path, population_pdf)

    for col in ("STATE", "POPULATION_2023", "SA2_CODE"):
        if col not in pop.columns:
            warnings.append("population missing expected column %s" % col)
    for col in ("EARNERS", "MEDIAN_INCOME", "SA2_CODE"):
        if col not in inc.columns:
            warnings.append("income missing expected column %s" % col)

    if "SA2_CODE" not in pop.columns or "SA2_CODE" not in inc.columns:
        print(json.dumps({"ok": False,
                          "error": "SA2_CODE join key not found in both sources",
                          "warnings": warnings,
                          "pop_columns": list(map(str, pop.columns)),
                          "inc_columns": list(map(str, inc.columns))}))
        return 1

    # normalized string join key
    def _key(series):
        return series.map(lambda v: "" if pd.isna(v) else str(int(v))
                          if float(v).is_integer() else str(v))
    pop = pop.copy()
    inc = inc.copy()
    pop["_key"] = _key(pop["SA2_CODE"])
    inc["_key"] = _key(inc["SA2_CODE"])

    pop_keys = set(pop["_key"]) - {""}
    inc_keys = set(inc["_key"]) - {""}
    warnings.append("population-only keys: %d" % len(pop_keys - inc_keys))
    warnings.append("income-only keys: %d" % len(inc_keys - pop_keys))

    # columns to carry from each side
    pop_cols = [c for c in ("SA2_CODE", "SA2_NAME", "STATE", "POPULATION_2023")
                if c in pop.columns] + ["_key"]
    inc_extra = [c for c in inc.columns
                 if c not in ("SA2_CODE", "SA2_NAME", "STATE", "_key")]
    inc_cols = ["_key"] + inc_extra

    merged = pop[pop_cols].merge(inc[inc_cols], on="_key", how="inner")
    merged = merged.drop(columns=["_key"])

    if "MEDIAN_INCOME" not in merged.columns or "EARNERS" not in merged.columns:
        print(json.dumps({"ok": False,
                          "error": "merged data lacks EARNERS/MEDIAN_INCOME",
                          "warnings": warnings,
                          "columns": list(map(str, merged.columns))}))
        return 1

    # ---- derived columns ----
    mi = pd.to_numeric(merged["MEDIAN_INCOME"], errors="coerce")
    ea = pd.to_numeric(merged["EARNERS"], errors="coerce")
    vals = mi.dropna()

    if quartile_method == "quantile":
        q1, q2, q3 = vals.quantile([0.25, 0.5, 0.75])
        bnds = [q1, q2, q3]

        def label(v):
            if pd.isna(v):
                return None
            if v <= bnds[0]:
                return "Q1"
            if v <= bnds[1]:
                return "Q2"
            if v <= bnds[2]:
                return "Q3"
            return "Q4"
    else:  # range / equal-width (default)
        mn = float(vals.min())
        mx = float(vals.max())
        width = (mx - mn) / 4.0 if mx > mn else 0.0

        def label(v):
            if pd.isna(v):
                return None
            if width == 0:
                return "Q1"
            idx = int((float(v) - mn) // width)
            if idx > 3:
                idx = 3
            if idx < 0:
                idx = 0
            return "Q%d" % (idx + 1)

    merged["Quarter"] = mi.map(label)
    total = ea * mi
    merged["Total"] = total.where(ea.notna() & mi.notna())

    # keep numeric columns numeric (NaN -> blank cell later)
    merged["MEDIAN_INCOME"] = mi
    merged["EARNERS"] = ea
    if "POPULATION_2023" in merged.columns:
        merged["POPULATION_2023"] = pd.to_numeric(merged["POPULATION_2023"],
                                                   errors="coerce")

    columns = list(map(str, merged.columns))
    nrows = len(merged)

    # ---- write workbook ----
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    sheet_names = ["Population by State", "Earners by State",
                   "Regions by State", "State Income Quartile", "SourceData"]
    sheets = {name: wb.create_sheet(title=name) for name in sheet_names}

    sd = sheets["SourceData"]
    sd.append(columns)
    import math
    for _, rec in merged.iterrows():
        out = []
        for col in columns:
            v = rec[col]
            if v is None or (isinstance(v, float) and math.isnan(v)):
                out.append(None)
            elif pd.isna(v):
                out.append(None)
            else:
                out.append(v)
        sd.append(out)

    ref = pv.data_ref(len(columns), nrows)
    cache = pv.build_shared_cache(columns, "SourceData", ref)

    count_field = "SA2_CODE" if "SA2_CODE" in columns else "STATE"
    pv.add_pivot(sheets["Population by State"], cache, columns,
                 row_col="STATE", data_col="POPULATION_2023", agg="sum",
                 display_name="Sum of POPULATION_2023", name="PivotPop")
    pv.add_pivot(sheets["Earners by State"], cache, columns,
                 row_col="STATE", data_col="EARNERS", agg="sum",
                 display_name="Sum of EARNERS", name="PivotEarn")
    pv.add_pivot(sheets["Regions by State"], cache, columns,
                 row_col="STATE", data_col=count_field, agg="count",
                 display_name="Count of regions", name="PivotRegions")
    pv.add_pivot(sheets["State Income Quartile"], cache, columns,
                 row_col="STATE", data_col="EARNERS", agg="sum",
                 display_name="Sum of EARNERS", col_col="Quarter",
                 name="PivotQuartile")

    wb.save(output_path)

    print(json.dumps({
        "ok": True,
        "output": output_path,
        "sheets": sheet_names,
        "rows": nrows,
        "quartile_method": quartile_method,
        "columns": columns,
        "warnings": warnings,
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
