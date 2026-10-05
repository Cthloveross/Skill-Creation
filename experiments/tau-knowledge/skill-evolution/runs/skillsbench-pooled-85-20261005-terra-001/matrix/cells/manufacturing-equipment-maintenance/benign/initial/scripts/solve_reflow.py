from __future__ import annotations
import csv, datetime as dt, json, math, os, re, sys
from collections import defaultdict

ALIASES = {
 "run_id": ["run_id", "run", "runid", "profile_id", "batch_id"],
 "board_family": ["board_family", "family", "board_type", "product_family"],
 "material": ["solder_material", "solder_alloy", "alloy", "material"],
 "actual_speed": ["actual_speed_cm_min", "conveyor_speed_cm_min", "conveyor_speed", "speed_cm_min", "speed"],
 "thermo_run_id": ["run_id", "run", "runid", "profile_id", "batch_id"],
 "tc_id": ["tc_id", "thermocouple_id", "sensor_id", "tc", "channel"],
 "time": ["time_s", "elapsed_s", "timestamp_s", "time", "timestamp", "seconds"],
 "temperature": ["temperature_c", "temp_c", "temperature", "temp"],
 "defects_run_id": ["run_id", "run", "runid", "profile_id", "batch_id"],
}

def nk(x): return re.sub(r"[^a-z0-9]+", "", str(x).lower())
def num(x):
    if x is None or str(x).strip() == "": return None
    s = re.sub(r"[^0-9.+\-eE]", "", str(x).replace(",", ""))
    try:
        v = float(s)
        return v if math.isfinite(v) else None
    except ValueError: return None

def value_keyed(v, key):
    if isinstance(v, dict): return v.get(str(key), v.get("default"))
    return v

def rnd(v): return None if v is None or not math.isfinite(v) else round(v + 0.0, 2)
def read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as f: return list(csv.DictReader(f))
def choose(rows, role, policy):
    exact = policy.get("columns", {}).get(role)
    heads = list(rows[0]) if rows else []
    if exact:
        if exact not in heads: raise ValueError(f"Configured column {exact!r} for {role} is absent")
        return exact
    normalized = {nk(h): h for h in heads}
    for candidate in ALIASES[role]:
        if nk(candidate) in normalized: return normalized[nk(candidate)]
    raise ValueError(f"Cannot discover {role}; available columns: {heads}. Set policy.columns.{role}.")

def parse_time(x):
    n = num(x)
    if n is not None: return n
    s = str(x).strip().replace("Z", "+00:00")
    try: return dt.datetime.fromisoformat(s).timestamp()
    except ValueError: raise ValueError(f"Unparseable thermocouple time {x!r}")

def required(policy, *path):
    cur = policy
    for p in path:
        if not isinstance(cur, dict) or p not in cur: raise ValueError("Missing handbook policy: " + ".".join(path))
        cur = cur[p]
    if cur is None: raise ValueError("Missing handbook policy value: " + ".".join(path))
    return cur

def trace_samples(rows, tcol, tempcol):
    vals = []
    for r in rows:
        t, temp = parse_time(r.get(tcol)), num(r.get(tempcol))
        if temp is not None: vals.append((t, temp))
    vals.sort()
    # A duplicate timestamp has no physical segment. Retain the final recorded sample.
    out = []
    for p in vals:
        if out and p[0] == out[-1][0]: out[-1] = p
        else: out.append(p)
    return out

def ramp_for_trace(samples, lo, hi, mode, statistic):
    best = None
    for (t1, a), (t2, b) in zip(samples, samples[1:]):
        if t2 <= t1: continue
        slope = (b-a)/(t2-t1)
        if mode == "fully_within":
            include = lo <= a <= hi and lo <= b <= hi
        elif mode == "clip_to_region":
            include = max(min(a,b), lo) <= min(max(a,b), hi)
        else: raise ValueError("ramp.segment_rule must be fully_within or clip_to_region")
        if include:
            candidate = abs(slope) if statistic == "absolute" else slope
            if best is None or candidate > best: best = candidate
    return best

def tal_for_trace(samples, threshold):
    total = 0.0
    for (t1, a), (t2, b) in zip(samples, samples[1:]):
        if t2 <= t1: continue
        if a == b:
            if a > threshold: total += t2-t1
            continue
        # Linear segment fraction for which T > threshold.
        x = (threshold-a)/(b-a)
        if a > threshold and b > threshold: frac = 1.0
        elif a <= threshold and b <= threshold: frac = 0.0
        elif a > threshold: frac = max(0.0, min(1.0, x))
        else: frac = 1.0-max(0.0, min(1.0, x))
        total += (t2-t1)*frac
    return total

def material_value(section, material, field):
    mapping = section.get(field + "_by_material", {})
    if material in mapping: return mapping[material]
    val = section.get("default_" + field)
    if val is not None: return val
    raise ValueError(f"No handbook {field} for material {material!r}")

def speed_cm_min(v, unit):
    factors = {"cm_min":1, "mm_s":6, "mm_min":.1, "m_min":100, "cm_s":60}
    if unit not in factors: raise ValueError("Unsupported conveyor actual_speed_unit")
    return v*factors[unit]

def metric(rows, field, aggregate):
    vs = [num(r.get(field)) for r in rows]; vs = [x for x in vs if x is not None]
    if not vs: return None
    if aggregate == "sum": return sum(vs)
    if aggregate == "mean": return sum(vs)/len(vs)
    if aggregate == "min": return min(vs)
    if aggregate == "max": return max(vs)
    raise ValueError("ranking aggregate must be sum, mean, min, or max")

def main(arg):
    data = arg.get("data_dir", "/app/data"); outdir = arg.get("output_dir", "/app/output")
    policy = dict(arg.get("policy") or {})
    if arg.get("policy_path"):
        with open(arg["policy_path"], encoding="utf-8") as f: policy.update(json.load(f))
    for k in ("ramp", "tal", "peak", "conveyor", "ranking"): required(policy, k)
    mes, defects, tc = (read_csv(os.path.join(data, x)) for x in ("mes_log.csv", "test_defects.csv", "thermocouples.csv"))
    if not mes: raise ValueError("MES log has no runs")
    mrun, family, material, speed = (choose(mes, x, policy) for x in ("run_id","board_family","material","actual_speed"))
    trun, tid, ttime, temp = (choose(tc, x, policy) for x in ("thermo_run_id","tc_id","time","temperature"))
    drun = choose(defects, "defects_run_id", policy) if defects else None
    mes_by_run = {}
    for r in mes:
        if r.get(mrun) in mes_by_run: raise ValueError("MES run IDs must be unique")
        mes_by_run[str(r[mrun])] = r
    runs = sorted(mes_by_run)
    traces = defaultdict(lambda: defaultdict(list))
    for row in tc:
        if row.get(trun) not in (None, "") and row.get(tid) not in (None, ""):
            traces[str(row[trun])][str(row[tid])].append(row)
    samples = {run:{sensor:trace_samples(rows, ttime, temp) for sensor, rows in ss.items()} for run,ss in traces.items()}
    ramp = policy["ramp"]; lo=float(required(ramp,"preheat_min_c")); hi=float(required(ramp,"preheat_max_c")); limit=float(required(ramp,"limit_c_per_s"))
    stat=ramp.get("statistic", "heating"); mode=ramp.get("segment_rule", "fully_within")
    max_by_run={}; violating=[]
    for run in runs:
        candidates=[(ramp_for_trace(s,lo,hi,mode,stat), sid) for sid,s in samples.get(run,{}).items()]
        candidates=[x for x in candidates if x[0] is not None]
        if candidates:
            val,sid=max(candidates, key=lambda x:(x[0], x[1]))
            max_by_run[run]={"tc_id":sid,"max_preheat_ramp_c_per_s":rnd(val)}
            if val > limit: violating.append(run)
        else: max_by_run[run]={"tc_id":None,"max_preheat_ramp_c_per_s":None}
    q01={"ramp_rate_limit_c_per_s":rnd(limit),"violating_runs":sorted(violating),"max_ramp_by_run":max_by_run}
    tal=policy["tal"]; talmin=float(required(tal,"min_s")); talmax=float(required(tal,"max_s")); q02=[]
    for run in runs:
        mat=str(mes_by_run[run].get(material,"")); liquid=float(material_value(tal,mat,"liquidus_c"))
        vals=[]
        for sid,s in samples.get(run,{}).items():
            if len(s)>=2: vals.append((sid,tal_for_trace(s,liquid)))
        if tal.get("scope","each_tc") == "representative" and vals: vals=[max(vals,key=lambda x:(x[1],x[0]))]
        for sid,v in sorted(vals): q02.append({"run_id":run,"tc_id":sid,"tal_s":rnd(v),"required_min_tal_s":rnd(talmin),"required_max_tal_s":rnd(talmax),"status":"compliant" if talmin <= v <= talmax else "non-compliant"})
    peak=policy["peak"]; failing=[]; min_peaks={}
    for run in runs:
        mat=str(mes_by_run[run].get(material,""))
        try: req=float(material_value(peak,mat,"min_c"))
        except ValueError:
            margin=peak.get("liquidus_margin_c")
            if margin is None: raise
            req=float(material_value(tal,mat,"liquidus_c"))+float(margin)
        vals=[(max(s),sid) for sid,s in samples.get(run,{}).items() if s]
        if not vals:
            min_peaks[run]={"tc_id":None,"peak_temp_c":None,"required_min_peak_c":rnd(req)}; failing.append(run)
        else:
            actual,sid=min(vals,key=lambda x:(x[0],x[1]))
            min_peaks[run]={"tc_id":sid,"peak_temp_c":rnd(actual),"required_min_peak_c":rnd(req)}
            if actual < req: failing.append(run)
    q03={"failing_runs":sorted(failing),"min_peak_by_run":min_peaks}
    conv=policy["conveyor"]; dwell=float(required(conv,"max_dwell_s")); unit=conv.get("actual_speed_unit","cm_min"); q04=[]
    for run in runs:
        row=mes_by_run[run]; fam=str(row.get(family,"")); length=value_keyed(conv.get("heated_length_cm_by_family", conv.get("default_heated_length_cm")),fam)
        if length is None: raise ValueError(f"No handbook heated length for family {fam!r}")
        req=max(float(conv.get("allowed_min_speed_cm_min") or 0), float(length)/dwell*60)
        actual_raw=num(row.get(speed)); actual=None if actual_raw is None else speed_cm_min(actual_raw,unit)
        upper=conv.get("allowed_max_speed_cm_min"); meets=actual is not None and actual >= req and (upper is None or actual <= float(upper))
        q04.append({"run_id":run,"required_min_speed_cm_min":rnd(req),"actual_speed_cm_min":rnd(actual),"meets":bool(meets)})
    defect_by_run=defaultdict(list)
    if drun:
        for r in defects:
            if r.get(drun) not in (None,""): defect_by_run[str(r[drun])].append(r)
    criteria=required(policy,"ranking","criteria")
    def rankkey(run):
        keys=[]
        for c in criteria:
            source=c.get("source"); direction=c.get("direction"); field=c.get("field")
            if source not in ("mes","defects") or direction not in ("asc","desc") or not field: raise ValueError("Invalid ranking criterion")
            v=metric([mes_by_run[run]] if source=="mes" else defect_by_run[run],field,c.get("aggregate","sum"))
            # missing values always rank last; negate descending numeric value.
            keys.append((v is None, (v if direction=="asc" else -v) if v is not None else 0))
        return tuple(keys)+(run,)
    q05=[]
    grouped=defaultdict(list)
    for run,row in mes_by_run.items(): grouped[str(row.get(family,""))].append(run)
    for fam, rs in sorted(grouped.items()):
        ordered=sorted(rs,key=rankkey)
        q05.append({"board_family":fam,"best_run_id":ordered[0],"runner_up_run_ids":sorted(ordered[1:])})
    os.makedirs(outdir,exist_ok=True)
    outputs={"q01.json":q01,"q02.json":q02,"q03.json":q03,"q04.json":q04,"q05.json":q05}
    for name,obj in outputs.items():
        with open(os.path.join(outdir,name),"w",encoding="utf-8") as f: json.dump(obj,f,ensure_ascii=False,indent=2,allow_nan=False)
    return {"ok":True,"output_dir":outdir,"files":sorted(outputs),"runs":len(runs),"tal_rows":len(q02)}

if __name__ == "__main__":
    try: print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"ok":False,"error":str(exc)})); raise
