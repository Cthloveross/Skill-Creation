#!/usr/bin/env python3
"""Build a validated flood-results CSV from local NWS and USGS text exports."""
import csv, json, math, os, re, sys
from collections import defaultdict
from datetime import date, datetime

ID = re.compile(r"(?<!\d)(\d{8,})(?!\d)")
MISSING = {"", "na", "n/a", "nan", "none", "null", "--", "-"}

def text(v):
    return "" if v is None else str(v).strip()

def nk(v):
    return re.sub(r"[^a-z0-9]+", "", text(v).lower())

def sid(v):
    m = re.fullmatch(r"(?:usgs[-:\s]*)?(\d{8,})(?:\.0+)?", text(v), re.I)
    return m.group(1) if m else ""

def num(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v) if math.isfinite(float(v)) else None
    s = text(v)
    if s.lower() in MISSING:
        return None
    m = re.fullmatch(
        r"\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?)\s*(?:[a-z.]*)\s*",
        s.replace(",", ""), re.I,
    )
    try:
        return float(m.group(1)) if m else None
    except ValueError:
        return None

def field(row, test):
    for k, v in row.items():
        if test(nk(k)):
            return v
    return None

def row_sid(row):
    exact = {
        "stationid", "station", "siteid", "siteno", "usgsid", "usgssite",
        "sitecode", "monitoringlocationidentifier",
    }
    v = field(row, lambda k: k in exact)
    if v is None:
        v = field(row, lambda k: ("station" in k or "site" in k or "usgs" in k)
                  and ("id" in k or "no" in k))
    return sid(v)

def stage(row):
    return num(field(
        row,
        lambda k: k in {"floodstage", "floodstagethreshold", "floodthreshold"}
        or ("flood" in k and "stage" in k),
    ))

def height(row):
    for k, v in row.items():
        key = nk(k)
        if "00065" in key and not key.endswith("cd") and "qualifier" not in key:
            return num(v)
    for k, v in row.items():
        key = nk(k)
        if key.endswith("cd") or "qualifier" in key or "00060" in key:
            continue
        if key in {"stage", "stageft", "stagefeet", "gageheight", "gageht"} or "gageheight" in key:
            return num(v)
    return None

def day(row):
    v = field(
        row,
        lambda k: k in {"datetime", "date", "timestamp", "observationtime", "time"}
        or "datetime" in k or "timestamp" in k or k.endswith("date"),
    )
    s = text(v)
    m = re.match(r"(\d{4})[-/](\d\d)[-/](\d\d)", s)
    if m:
        try:
            return date(*map(int, m.groups()))
        except ValueError:
            return None
    for fmt in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(s.split()[0], fmt).date()
        except (ValueError, IndexError):
            pass
    return None

def table(raw):
    lines = [x for x in raw.splitlines() if x.strip() and not x.lstrip().startswith("#")]
    if len(lines) < 2:
        return []
    try:
        dialect = csv.Sniffer().sniff("\n".join(lines[:30]), delimiters=",\t;|")
        values = list(csv.reader(lines, dialect))
    except csv.Error:
        values = [re.split(r"\s+", x.strip()) for x in lines]
    if len(values) < 2:
        return []
    header = [x.strip() for x in values[0]]
    # USGS RDB has a second line containing type declarations such as 15s/20d.
    start = 2 if values[1] and all(
        re.fullmatch(r"\d+[A-Za-z]+", x.strip()) for x in values[1] if x.strip()
    ) else 1
    return [
        {header[i]: r[i].strip() for i in range(len(header))}
        for r in values[start:] if len(r) >= len(header)
    ]

def flatten(obj, inherited=None):
    inherited = dict(inherited or {})
    out = []
    if isinstance(obj, list):
        for x in obj:
            out.extend(flatten(x, inherited))
    elif isinstance(obj, dict):
        here = dict(inherited)
        if row_sid(obj):
            here["station_id"] = row_sid(obj)
        if stage(obj) is not None:
            here["flood stage"] = stage(obj)
        scalars = {str(k): v for k, v in obj.items() if not isinstance(v, (dict, list))}
        if scalars:
            for k, v in here.items():
                scalars.setdefault(k, v)
            out.append(scalars)
        for v in obj.values():
            if isinstance(v, (dict, list)):
                out.extend(flatten(v, here))
    return out

def load(path):
    with open(path, encoding="utf-8-sig", errors="replace", newline="") as handle:
        raw = handle.read()
    try:
        return raw, flatten(json.loads(raw))
    except json.JSONDecodeError:
        return raw, table(raw)

def discover(exclude):
    ans = []
    for root, _, names in os.walk("/root/data"):
        for name in names:
            path = os.path.abspath(os.path.join(root, name))
            try:
                size = os.path.getsize(path)
            except OSError:
                continue
            if (path not in exclude and size <= 100 * 1024 * 1024
                    and os.path.splitext(name)[1].lower() in {".csv", ".tsv", ".txt", ".rdb", ".json"}):
                ans.append(path)
    return sorted(ans)

def write_check(path, results, scope, limit):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["station_id", "flood_days"])
        writer.writerows(results)
    with open(path, encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    if not rows or rows[0] != ["station_id", "flood_days"]:
        raise ValueError("output header validation failed")
    seen = set()
    for row in rows[1:]:
        if (len(row) != 2 or row[0] not in scope or not re.fullmatch(r"[1-9]\d*", row[1])
                or int(row[1]) > limit or row[0] in seen):
            raise ValueError("invalid output result row")
        seen.add(row[0])
    if results != sorted(results, key=lambda x: (-x[1], x[0])):
        raise ValueError("output ordering validation failed")

def main():
    try:
        q = json.load(sys.stdin)
        if not isinstance(q, dict):
            raise ValueError("stdin must be a JSON object")
        ip, op = q.get("input_path"), q.get("output_path")
        if not isinstance(ip, str) or not isinstance(op, str):
            raise ValueError("input_path and output_path are required strings")
        start = day({"date": q.get("start_date", "2025-04-01")})
        end = day({"date": q.get("end_date", "2025-04-07")})
        if not start or not end or start > end:
            raise ValueError("dates must be ordered ISO dates")

        raw, rows = load(ip)
        scope = set(ID.findall(raw))
        if not scope:
            raise ValueError("input_path contains no USGS-style station IDs")

        paths = [os.path.abspath(ip)]
        if q.get("threshold_path") is not None:
            if not isinstance(q["threshold_path"], str):
                raise ValueError("threshold_path must be a string")
            paths.append(os.path.abspath(q["threshold_path"]))
        observations = q.get("observation_paths", [])
        if not isinstance(observations, list) or not all(isinstance(x, str) for x in observations):
            raise ValueError("observation_paths must be an array of strings")
        paths += [os.path.abspath(x) for x in observations]
        discover_flag = q.get("discover_local_data", True)
        if not isinstance(discover_flag, bool):
            raise ValueError("discover_local_data must be boolean")
        if discover_flag:
            paths += discover({os.path.abspath(op)})
        paths = list(dict.fromkeys(paths))

        unread = []
        for path in paths[1:]:
            try:
                rows.extend(load(path)[1])
            except (OSError, UnicodeError) as exc:
                unread.append(path + ": " + str(exc))

        thresholds = {}
        conflict = set()
        for row in rows:
            station, threshold = row_sid(row), stage(row)
            if station not in scope or threshold is None:
                continue
            if station in thresholds and not math.isclose(threshold, thresholds[station], abs_tol=1e-12):
                conflict.add(station)
            else:
                thresholds[station] = threshold
        for station in conflict:
            thresholds.pop(station, None)

        maxima = {}
        usable = 0
        for row in rows:
            station, observed_day, observed_height = row_sid(row), day(row), height(row)
            if (station in thresholds and observed_day is not None and observed_height is not None
                    and start <= observed_day <= end):
                usable += 1
                maxima[(station, observed_day)] = max(
                    observed_height, maxima.get((station, observed_day), -math.inf)
                )

        counts = defaultdict(int)
        for (station, _), maximum in maxima.items():
            if maximum >= thresholds[station]:
                counts[station] += 1
        results = sorted(
            ((station, count) for station, count in counts.items() if count),
            key=lambda x: (-x[1], x[0]),
        )
        write_check(op, results, scope, (end - start).days + 1)

        warnings = []
        if not thresholds:
            warnings.append("No valid in-scope numeric NWS flood-stage threshold was found in local data.")
        if not usable:
            warnings.append("No in-window dated gage-height observations (00065/stage) were found for thresholded stations.")
        if not results and thresholds and usable:
            warnings.append("No observed daily maximum met a valid flood stage.")
        if conflict:
            warnings.append("Stations with conflicting flood stages were excluded.")
        if unread:
            warnings.append("Unreadable supplied paths: " + "; ".join(unread))
        print(json.dumps({
            "ok": True,
            "output_path": op,
            "output_rows": len(results),
            "station_scope_count": len(scope),
            "valid_thresholds_found": len(thresholds),
            "in_window_observations_found": usable,
            "analysis_complete": bool(thresholds and usable),
            "warnings": warnings,
        }, sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        sys.exit(2)

if __name__ == "__main__":
    main()
