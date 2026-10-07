#!/usr/bin/env python3
"""Runtime lake trend and categorical driver-attribution analysis.

stdin JSON schema:
  {"data_dir": str, "output_dir": str, "category_map": {str: str}?}
stdout JSON schema:
  success: {"ok":true, "trend_result":str, "dominant_factor":str,
            "target_column":str, "date_columns":object, "aligned_rows":int,
            "dominant_category":str, "contribution":number}
  failure: {"ok":false, "error":str}
"""
import csv
import datetime as dt
import json
import math
import os
import re
import sys
from collections import defaultdict

CATEGORIES = {"Heat", "Flow", "Wind", "Human"}
FILES = ("water_temperature.csv", "climate.csv", "land_cover.csv", "hydrology.csv")
DATE_NAMES = ("date", "datetime", "timestamp", "time", "year", "month")


def norm(s):
    return re.sub(r"[^a-z0-9]+", "", str(s).lower())


def num(v):
    if v is None:
        return None
    s = str(v).strip().replace(",", "")
    if not s or s.lower() in {"na", "nan", "null", "none", "n/a", "-999", "-9999"}:
        return None
    try:
        x = float(s)
        return x if math.isfinite(x) else None
    except ValueError:
        return None


def canonical_time(value):
    s = str(value).strip()
    x = num(s)
    if x is not None:
        return str(int(x)) if x == int(x) else format(x, ".12g")
    z = s.replace("Z", "+00:00")
    for parser in (dt.datetime.fromisoformat, dt.date.fromisoformat):
        try:
            return parser(z).date().isoformat()
        except (ValueError, TypeError):
            pass
    # A nonempty, shared textual key remains usable for a join, but not a slope.
    return s


def decimal_year(key):
    x = num(key)
    if x is not None:
        return x
    try:
        d = dt.date.fromisoformat(key[:10])
        start = dt.date(d.year, 1, 1)
        return d.year + (d - start).days / (366.0 if _leap(d.year) else 365.0)
    except ValueError:
        raise ValueError("temporal keys must be numeric years or ISO-like dates for trend analysis")


def _leap(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def read_csv(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        rd = csv.DictReader(f)
        if not rd.fieldnames:
            raise ValueError("CSV has no header: " + path)
        fields = [h.strip() for h in rd.fieldnames if h and h.strip()]
        rows = [{k.strip(): v for k, v in row.items() if k is not None} for row in rd]
    if not rows:
        raise ValueError("CSV has no data rows: " + path)
    return fields, rows


def find_date(fields):
    ranked = []
    for field in fields:
        n = norm(field)
        score = 0
        if n in DATE_NAMES: score = 100
        elif "date" in n or "time" in n: score = 90
        elif n.endswith("year") or n.startswith("year"): score = 80
        if score: ranked.append((score, field))
    if not ranked:
        raise ValueError("could not identify a temporal key; use a date/year/time-named column")
    return sorted(ranked, reverse=True)[0][1]


def numeric_fields(fields, rows, exclude):
    ans = []
    for h in fields:
        if h == exclude:
            continue
        nonblank = [num(r.get(h)) for r in rows if str(r.get(h, "")).strip()]
        good = sum(v is not None for v in nonblank)
        # Avoid treating identifiers as drivers; require a substantial numeric share.
        if good >= 2 and good / max(1, len(nonblank)) >= 0.80:
            ans.append(h)
    return ans


def choose_target(fields, rows, date_field):
    candidates = numeric_fields(fields, rows, date_field)
    temps = [h for h in candidates if "temp" in norm(h) or "temperature" in norm(h)]
    if not temps:
        raise ValueError("water_temperature.csv has no numeric temperature-named column")
    def score(h):
        n = norm(h)
        return (20 if "water" in n else 0) + (15 if "lake" in n else 0) + (10 if "surface" in n else 0) + (5 if "0to5" in n or "05m" in n else 0)
    return max(temps, key=score)


def aggregate(rows, date_field, fields):
    buckets = defaultdict(lambda: defaultdict(list))
    for r in rows:
        raw = r.get(date_field)
        if raw is None or not str(raw).strip():
            continue
        key = canonical_time(raw)
        for h in fields:
            v = num(r.get(h))
            if v is not None:
                buckets[key][h].append(v)
    out = {}
    for key, cols in buckets.items():
        out[key] = {h: sum(vs) / len(vs) for h, vs in cols.items() if vs}
    return out


def category(source, header, overrides):
    qualified = source + "." + header
    value = overrides.get(qualified, overrides.get(header))
    if value is not None:
        if value not in CATEGORIES:
            raise ValueError("category_map value for %s is not one of %s" % (qualified, sorted(CATEGORIES)))
        return value
    label = norm(header)
    if "wind" in label or "gust" in label:
        return "Wind"
    if any(w in label for w in ("discharge", "inflow", "outflow", "runoff", "streamflow", "riverflow", "precip", "rain", "waterlevel", "hydro")):
        return "Flow"
    if any(w in label for w in ("urban", "impervious", "built", "population", "agric", "crop", "farmland", "human")):
        return "Human"
    if source == "hydrology.csv": return "Flow"
    if source == "land_cover.csv": return "Human"
    if source == "climate.csv": return "Heat"
    raise ValueError("cannot classify driver " + qualified)


def mean(xs): return sum(xs) / len(xs)

def median(xs):
    xs = sorted(xs)
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2.0


def solve(a, b):
    """Gauss-Jordan solution of a square system."""
    n = len(b)
    m = [list(a[i]) + [b[i]] for i in range(n)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[pivot][col]) < 1e-12:
            raise ValueError("driver design matrix is singular")
        m[col], m[pivot] = m[pivot], m[col]
        scale = m[col][col]
        m[col] = [x / scale for x in m[col]]
        for r in range(n):
            if r != col:
                fac = m[r][col]
                if fac:
                    m[r] = [m[r][j] - fac * m[col][j] for j in range(n + 1)]
    return [m[i][-1] for i in range(n)]


def betacf(a, b, x):
    # Continued fraction for regularized incomplete beta, Numerical Recipes form.
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d, h = 1.0, 1.0 - qab * x / qap, 1.0
    if abs(d) < 3e-30: d = 3e-30
    d = 1.0 / d; h = d
    for m in range(1, 201):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < 3e-30: d = 3e-30
        c = 1.0 + aa / c
        if abs(c) < 3e-30: c = 3e-30
        d = 1.0 / d; h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < 3e-30: d = 3e-30
        c = 1.0 + aa / c
        if abs(c) < 3e-30: c = 3e-30
        d = 1.0 / d; delta = d * c; h *= delta
        if abs(delta - 1.0) < 3e-12: break
    return h


def ibeta(x, a, b):
    if x <= 0: return 0.0
    if x >= 1: return 1.0
    front = math.exp(math.lgamma(a+b) - math.lgamma(a) - math.lgamma(b) + a*math.log(x) + b*math.log(1-x))
    if x < (a + 1) / (a + b + 2): return front * betacf(a, b, x) / a
    return 1.0 - front * betacf(b, a, 1-x) / b


def trend_pvalue(x, y):
    n = len(x)
    if n < 3: raise ValueError("at least three dated temperature observations are required")
    xb, yb = mean(x), mean(y)
    sxx = sum((v-xb)**2 for v in x)
    if sxx <= 0: raise ValueError("temporal key has no variation")
    slope = sum((x[i]-xb)*(y[i]-yb) for i in range(n)) / sxx
    intercept = yb - slope * xb
    if n == 3:
        # still defined with one residual degree of freedom
        pass
    rss = sum((y[i] - intercept - slope*x[i])**2 for i in range(n))
    se = math.sqrt((rss / (n-2)) / sxx)
    if se == 0:
        p = 0.0 if slope != 0 else 1.0
    else:
        t = abs(slope / se)
        p = ibeta((n-2) / ((n-2) + t*t), (n-2)/2.0, 0.5)
    return slope, min(1.0, max(0.0, p))


def write_and_validate(path, fields, row):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temp = path + ".tmp"
    with open(temp, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader(); w.writerow(row)
    with open(temp, "r", encoding="utf-8", newline="") as f:
        check = list(csv.DictReader(f))
    if len(check) != 1 or list(check[0].keys()) != fields:
        raise ValueError("output validation failed for " + path)
    for field in fields:
        if field != "variable" and not math.isfinite(float(check[0][field])):
            raise ValueError("non-finite output value")
    os.replace(temp, path)


def run(cfg):
    data_dir = cfg.get("data_dir", "/root/data")
    output_dir = cfg.get("output_dir", "/root/output")
    overrides = cfg.get("category_map", {})
    if not isinstance(overrides, dict): raise ValueError("category_map must be an object")
    loaded = {}
    for filename in FILES:
        path = os.path.join(data_dir, filename)
        if not os.path.isfile(path): raise ValueError("required input is missing: " + path)
        fields, rows = read_csv(path)
        date_field = find_date(fields)
        loaded[filename] = (fields, rows, date_field)
    tf, tr, tdate = loaded["water_temperature.csv"]
    target = choose_target(tf, tr, tdate)
    target_table = aggregate(tr, tdate, [target])
    observations = {k: v[target] for k, v in target_table.items() if target in v}
    if len(observations) < 3: raise ValueError("fewer than three usable temperature observations")
    dates = sorted(observations, key=decimal_year)
    slope, pval = trend_pvalue([decimal_year(k) for k in dates], [observations[k] for k in dates])

    features, feature_categories = {}, {}
    for source in ("climate.csv", "land_cover.csv", "hydrology.csv"):
        fields, rows, dfield = loaded[source]
        cols = numeric_fields(fields, rows, dfield)
        table = aggregate(rows, dfield, cols)
        for h in cols:
            fname = source + "." + h
            features[fname] = {k: vals[h] for k, vals in table.items() if h in vals}
            feature_categories[fname] = category(source, h, overrides)
    if not features: raise ValueError("no numeric driver variables were discovered")

    # Retain temperature dates represented in at least one source. Median imputation is then
    # calculated only over this aligned analysis population.
    keys = [k for k in dates if any(k in col for col in features.values())]
    if len(keys) < 3: raise ValueError("fewer than three temperature dates overlap any driver table")
    usable = {}
    for f, values in features.items():
        present = [values[k] for k in keys if k in values]
        if len(present) >= 2:
            fill = median(present)
            usable[f] = [values.get(k, fill) for k in keys]
    if not usable: raise ValueError("no driver has at least two aligned numeric values")
    # Standardize predictors and remove constants.
    X, kept = [], []
    for f, vals in usable.items():
        mu = mean(vals); sd = math.sqrt(sum((v-mu)**2 for v in vals) / len(vals))
        if sd > 1e-12:
            kept.append(f); X.append([(v-mu)/sd for v in vals])
    if not kept: raise ValueError("all aligned driver variables are constant")
    yraw = [observations[k] for k in keys]
    ym = mean(yraw); ys = math.sqrt(sum((v-ym)**2 for v in yraw) / len(yraw))
    if ys <= 1e-12: raise ValueError("water temperature is constant over driver-aligned records")
    y = [(v-ym)/ys for v in yraw]
    p = len(kept); n = len(keys)
    a = [[sum(X[i][r]*X[j][r] for r in range(n)) for j in range(p)] for i in range(p)]
    b = [sum(X[i][r]*y[r] for r in range(n)) for i in range(p)]
    # A negligible ridge makes exact duplicate/correlated environmental series deterministic.
    scale = max(1.0, max(a[i][i] for i in range(p)))
    for i in range(p): a[i][i] += scale * 1e-8
    beta = solve(a, b)
    grouped = defaultdict(float)
    for f, coef in zip(kept, beta): grouped[feature_categories[f]] += coef * coef
    total = sum(grouped.values())
    if not math.isfinite(total) or total <= 0: raise ValueError("driver model has no attributable standardized signal")
    winner = max(sorted(grouped), key=lambda c: grouped[c])
    contribution = 100.0 * grouped[winner] / total
    if not (math.isfinite(slope) and math.isfinite(pval) and math.isfinite(contribution)):
        raise ValueError("non-finite analysis result")
    trend_path = os.path.join(output_dir, "trend_result.csv")
    factor_path = os.path.join(output_dir, "dominant_factor.csv")
    write_and_validate(trend_path, ["slope", "p-value"], {"slope": repr(slope), "p-value": repr(pval)})
    write_and_validate(factor_path, ["variable", "contribution"], {"variable": winner, "contribution": repr(contribution)})
    return {"ok": True, "trend_result": trend_path, "dominant_factor": factor_path,
            "target_column": target, "date_columns": {f: loaded[f][2] for f in FILES},
            "aligned_rows": n, "dominant_category": winner, "contribution": contribution}


def main():
    try:
        cfg = json.load(sys.stdin)
        if not isinstance(cfg, dict): raise ValueError("stdin must contain a JSON object")
        print(json.dumps(run(cfg), allow_nan=False))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))

if __name__ == "__main__":
    main()
