"""End-to-end lake warming trend analysis + driver attribution.

stdin JSON:
  {
    "data_dir": "/root/data",            # optional
    "output_dir": "/root/output",        # optional
    "category_keywords": {...},            # optional override
    "contribution_mode": "category"       # or "variable"
  }

Writes <output_dir>/trend_result.csv (columns: slope, p-value) and
<output_dir>/dominant_factor.csv (columns: variable, contribution).
Prints a JSON summary to stdout. Nothing is hardcoded; all values come from data.
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy import stats  # noqa: E402
from common import (  # noqa: E402
    load_table, detect_time_key, numeric_columns, annual_mean,
    mann_kendall_pvalue, relative_weights, map_categories, load_keywords,
)

HERE = os.path.dirname(os.path.abspath(__file__))
REF = os.path.join(HERE, "..", "references", "category_mapping.json")


def find_temp_column(df, time_key):
    cands = [c for c in df.columns if c != time_key]
    # prefer a name containing temp
    for c in cands:
        if "temp" in c.lower():
            return c
    # else first numeric non-key column
    for c in cands:
        s = pd.to_numeric(df[c], errors="coerce")
        if s.notna().sum() >= 2:
            return c
    raise ValueError("No temperature value column found in water_temperature table")


def main():
    raw = sys.stdin.read().strip()
    cfg = json.loads(raw) if raw else {}
    data_dir = cfg.get("data_dir", "/root/data")
    out_dir = cfg.get("output_dir", "/root/output")
    contribution_mode = cfg.get("contribution_mode", "category")
    keywords = load_keywords(REF)
    if cfg.get("category_keywords"):
        keywords.update(cfg["category_keywords"])
    warnings = []
    os.makedirs(out_dir, exist_ok=True)

    # ---- load tables ----
    paths = {
        "water": os.path.join(data_dir, "water_temperature.csv"),
        "climate": os.path.join(data_dir, "climate.csv"),
        "hydrology": os.path.join(data_dir, "hydrology.csv"),
        "land_cover": os.path.join(data_dir, "land_cover.csv"),
    }
    water = load_table(paths["water"])
    _, wkey = detect_time_key(water)
    temp_col = find_temp_column(water, wkey)
    water_ann = annual_mean(water, wkey, [temp_col])
    water_ann = water_ann.dropna()
    if len(water_ann) < 3:
        raise ValueError("Fewer than 3 annual temperature values; cannot fit trend")

    # ---- trend analysis (OLS on annual means vs year) ----
    yrs = water_ann.index.values.astype(float)
    temps = water_ann[temp_col].values.astype(float)
    lr = stats.linregress(yrs, temps)
    slope = float(lr.slope)
    pval = float(lr.pvalue)
    mk_p = mann_kendall_pvalue(temps)

    trend_df = pd.DataFrame({"slope": [slope], "p-value": [pval]})
    trend_path = os.path.join(out_dir, "trend_result.csv")
    trend_df.to_csv(trend_path, index=False)

    # ---- build predictor matrix (annual, merged on year) ----
    merged = water_ann.rename(columns={temp_col: "__temp__"})
    col_source = {}
    for src_key in ["climate", "hydrology", "land_cover"]:
        p = paths[src_key]
        if not os.path.exists(p):
            warnings.append("Missing predictor table: %s" % p)
            continue
        df = load_table(p)
        _, k = detect_time_key(df)
        ncols = numeric_columns(df, exclude=[k])
        if not ncols:
            warnings.append("No usable numeric columns in %s" % os.path.basename(p))
            continue
        ann = annual_mean(df, k, ncols)
        # dedupe column names across files
        rename = {}
        for c in ann.columns:
            name = c
            if name in merged.columns or name in col_source:
                name = "%s::%s" % (src_key, c)
            rename[c] = name
            col_source[name] = os.path.basename(p)
        ann = ann.rename(columns=rename)
        merged = merged.join(ann, how="inner")

    predictors = [c for c in merged.columns if c != "__temp__"]
    attribution = {"method": None}
    if len(predictors) >= 1 and len(merged.dropna()) >= max(4, 2):
        m = merged.dropna()
        # drop constant predictors after merge
        keep = [c for c in predictors if m[c].std(ddof=0) > 0]
        dropped = sorted(set(predictors) - set(keep))
        if dropped:
            warnings.append("Dropped constant predictors: %s" % dropped)
        predictors = keep
        X = m[predictors].values
        y = m["__temp__"].values
        raw, r2, method = relative_weights(X, y)
        total = float(np.sum(raw))
        if total <= 0:
            raise ValueError("Attribution produced non-positive total importance")
        pct = {c: float(100.0 * raw[i] / total) for i, c in enumerate(predictors)}
        cats = map_categories({c: col_source[c] for c in predictors}, keywords)
        per_cat = {}
        for c, v in pct.items():
            per_cat[cats[c]] = per_cat.get(cats[c], 0.0) + v
        dom_cat = max(per_cat, key=per_cat.get)
        # top variable within dominant category
        in_cat = {c: pct[c] for c in predictors if cats[c] == dom_cat}
        top_var = max(in_cat, key=in_cat.get)
        top_var_pct = pct[top_var]
        cat_pct = per_cat[dom_cat]

        if contribution_mode == "variable":
            contribution_value = top_var_pct
        else:
            contribution_value = cat_pct
        # strip any src:: prefix for the reported variable name
        reported_var = top_var.split("::")[-1]

        dom_df = pd.DataFrame({
            "variable": [reported_var],
            "contribution": [round(float(contribution_value), 4)],
        })
        dom_path = os.path.join(out_dir, "dominant_factor.csv")
        dom_df.to_csv(dom_path, index=False)

        attribution = {
            "method": method,
            "r_squared": r2,
            "dominant_category": dom_cat,
            "dominant_category_contribution_pct": cat_pct,
            "top_variable": reported_var,
            "top_variable_contribution_pct": top_var_pct,
            "contribution_written": float(contribution_value),
            "contribution_mode": contribution_mode,
            "per_variable_pct": pct,
            "per_category_pct": per_cat,
            "category_of_variable": cats,
            "n_rows": int(len(m)),
        }
    else:
        warnings.append("Insufficient aligned data for attribution")
        dom_path = None

    summary = {
        "trend": {
            "slope": slope,
            "p_value": pval,
            "mann_kendall_p": mk_p,
            "n_years": int(len(water_ann)),
            "temperature_column": temp_col,
            "year_min": int(min(yrs)),
            "year_max": int(max(yrs)),
        },
        "attribution": attribution,
        "files": [trend_path] + ([dom_path] if dom_path else []),
        "warnings": warnings,
    }
    print(json.dumps(summary, indent=2, default=float))


if __name__ == "__main__":
    main()
