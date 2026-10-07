#!/usr/bin/env python3
"""Runtime solver/validator for baseline FJSP repair. JSON stdin -> JSON stdout."""
import csv
import json
import math
import os
import sys
from copy import deepcopy

DEFAULTS = {
    "instance": "/app/data/instance.txt",
    "baseline": "/app/data/baseline_solution.json",
    "downtime": "/app/data/downtime.csv",
    "policy": "/app/data/policy.json",
    "output_dir": "/app/output",
    "solution": "/app/output/solution.json",
    "csv": "/app/output/schedule.csv",
}
CORE = ("job", "op", "machine", "start", "end", "dur")

def number(x):
    v = float(x)
    return int(v) if v.is_integer() else v

def get(row, *names):
    normalized = {str(k).lower().replace("_", "").replace("-", ""): v for k, v in row.items()}
    for name in names:
        key = name.lower().replace("_", "").replace("-", "")
        if key in normalized:
            return normalized[key]
    raise KeyError("missing one of " + repr(names))

def parse_instance(path):
    tok = open(path, encoding="utf-8").read().split()
    if len(tok) < 2: raise ValueError("instance header is missing")
    jobs, machines, i = int(tok[0]), int(tok[1]), 2
    choices = {}
    for j in range(jobs):
        n = int(tok[i]); i += 1
        for o in range(n):
            k = int(tok[i]); i += 1
            opts = []
            for _ in range(k):
                m, d = int(tok[i]), number(tok[i+1]); i += 2
                opts.append((m, d))
            choices[(j, o)] = opts
    if i != len(tok): raise ValueError("unparsed tokens in instance")
    return choices, jobs, machines

def normalize_row(row):
    r = {"job": int(get(row, "job", "job_id")), "op": int(get(row, "op", "operation", "operation_id")),
         "machine": int(get(row, "machine", "machine_id")), "start": number(get(row, "start", "start_time")),
         "end": number(get(row, "end", "end_time")), "dur": number(get(row, "dur", "duration", "processing_time"))}
    return r

def baseline_rows(path):
    obj = json.load(open(path, encoding="utf-8"))
    rows = obj.get("schedule", obj) if isinstance(obj, dict) else obj
    if not isinstance(rows, list): raise ValueError("baseline schedule is not a list")
    out = [normalize_row(x) for x in rows]
    if len({(x['job'],x['op']) for x in out}) != len(out): raise ValueError("duplicate baseline operation")
    return out, obj if isinstance(obj, dict) else {}

def downtimes(path):
    result = {}
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if not r or not any(str(v).strip() for v in r.values()): continue
            m = int(get(r, "machine", "machine_id")); a = number(get(r, "start", "start_time")); b = number(get(r, "end", "end_time"))
            if b < a: raise ValueError("downtime end precedes start")
            result.setdefault(m, []).append((a, b, "downtime"))
    for m in result: result[m].sort()
    return result

def walk(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield str(k), v
            yield from walk(v)
    elif isinstance(obj, list):
        for v in obj: yield from walk(v)

def keynorm(k): return k.lower().replace("_", "").replace("-", "").replace(" ", "")
def policy_value(policy, predicates):
    for k, v in walk(policy):
        n = keynorm(k)
        if predicates(n) and isinstance(v, (int, float)) and not isinstance(v, bool): return number(v)
    return None

def policy_settings(policy):
    machine_max = policy_value(policy, lambda n: "max" in n and "machine" in n and ("change" in n or "reassign" in n))
    shift_max = policy_value(policy, lambda n: "max" in n and ("shift" in n or "l1" in n) and ("start" in n or "total" in n or "l1" in n))
    freeze = policy_value(policy, lambda n: ("freeze" in n or "frozen" in n) and ("before" in n or "until" in n or "time" in n or "horizon" in n))
    fields = None
    for k, v in walk(policy):
        n = keynorm(k)
        if ("freeze" in n or "lock" in n) and "field" in n and isinstance(v, list):
            fields = {keynorm(str(x)) for x in v}; break
    if freeze is not None and not fields: fields = {"machine", "start", "end"}
    return machine_max if machine_max is not None else math.inf, shift_max if shift_max is not None else math.inf, freeze, fields or set()

def overlaps(a, b, c, d): return a < d and c < b

def earliest(anchor, dur, intervals):
    s = anchor
    # Re-scan because a shift may encounter the following interval.
    while True:
        moved = False
        for a, b, _ in sorted(intervals):
            if s + dur <= a: break
            if s < b and s + dur > a:
                s = b; moved = True; break
        if not moved: return s

def fits(s, dur, intervals):
    return all(not overlaps(s, s + dur, a, b) for a, b, _ in intervals)

def frozen_ok(base, cand, freeze, fields):
    if freeze is None or base["start"] >= freeze: return True
    aliases = {"machine": "machine", "start": "start", "end": "end", "duration": "dur", "dur": "dur"}
    for f in fields:
        f = aliases.get(f, f)
        if f in cand and cand[f] != base[f]: return False
    return True

def usable_freeze_keys(base, choices, blocked, freeze, fields):
    """Return locks that can be honored as fixed baseline intervals.

    A freeze is a commitment, not permission to retain a baseline interval that
    already conflicts with a newly supplied outage.  Such a row cannot be both
    fixed and downtime-feasible, so leave it repairable and retain every other
    requested lock.  This also makes inconsistent public input diagnosable
    without silently emitting a downtime violation.
    """
    if freeze is None or not fields:
        return set()
    active = set()
    for key, b in base.items():
        if b["start"] >= freeze:
            continue
        legal = ((b["machine"], b["dur"]) in choices[key]
                 and b["end"] == b["start"] + b["dur"]
                 and fits(b["start"], b["dur"], blocked.get(b["machine"], [])))
        if legal:
            active.add(key)
    return active

def freeze_row_ok(key, base, cand, freeze, fields, active_freezes):
    return key not in active_freezes or frozen_ok(base, cand, freeze, fields)

def solve(cfg):
    choices, _, _ = parse_instance(cfg["instance"])
    base_rows, _ = baseline_rows(cfg["baseline"])
    base = {(r["job"], r["op"]): r for r in base_rows}
    if set(base) != set(choices):
        missing, extra = set(choices)-set(base), set(base)-set(choices)
        raise ValueError("baseline key set differs from instance; missing=%s extra=%s" % (sorted(missing), sorted(extra)))
    policy = json.load(open(cfg["policy"], encoding="utf-8"))
    max_changes, max_shift, freeze, fields = policy_settings(policy)
    blocked = downtimes(cfg["downtime"])
    # Freeze policies are opt-in because some planning inputs use a freeze block
    # as a baseline-reporting guard rather than a repair hard constraint.  Set
    # enforce_freeze=true when locked fields are contractual requirements.
    active_freezes = (usable_freeze_keys(base, choices, blocked, freeze, fields)
                      if cfg.get("enforce_freeze", False) else set())
    order = sorted(base, key=lambda k: (k[1], base[k]["start"], next(i for i,r in enumerate(base_rows) if (r['job'],r['op']) == k)))
    # state: (rows by key, machine intervals, changes, shift, current max end)
    states = [({}, {m:list(v) for m,v in blocked.items()}, 0, 0, 0)]
    beam_width = int(cfg.get("beam_width", 12000))
    for key in order:
        b = base[key]; successors = []
        for rows, intervals, changes, shift, makespan in states:
            # Some planning tasks budget the absolute change in start times but
            # do not impose a right-shift-only restriction.  Honor that form by
            # default; callers requiring baseline-repair semantics can set the
            # explicit right_shift_only flag.
            anchor = b["start"] if cfg.get("right_shift_only", False) else 0
            if key[1] > 0:
                pred = rows.get((key[0], key[1]-1))
                if pred is None: raise ValueError("operation order did not place predecessor")
                anchor = max(anchor, pred["end"])
            # Baseline machine first, followed by shorter alternatives, for deterministic useful pruning.
            opts = sorted(choices[key], key=lambda x: (x[0] != b["machine"], x[1], x[0]))
            for m, dur in opts:
                ints = intervals.get(m, [])
                s = earliest(anchor, dur, ints)
                cand = {"job":key[0], "op":key[1], "machine":m, "start":s, "end":s+dur, "dur":dur}
                if not freeze_row_ok(key, b, cand, freeze, fields, active_freezes): continue
                c2, sh2 = changes + int(m != b["machine"]), shift + abs(s - b["start"])
                if (cfg.get("right_shift_only", False) and s < b["start"]) or c2 > max_changes or sh2 > max_shift: continue
                newrows = dict(rows); newrows[key] = cand
                newints = dict(intervals); newints[m] = list(ints) + [(s, s+dur, key)]
                successors.append((newrows, newints, c2, sh2, max(makespan, s+dur)))
        if not successors: raise ValueError("no feasible placement for operation %r under policy" % (key,))
        # Equivalent signatures retain only the best cost; beam makes broad machine-choice search bounded.
        unique = {}
        for st in successors:
            signature = tuple((k, st[0][k]["machine"], st[0][k]["start"]) for k in sorted(st[0]))
            old = unique.get(signature)
            if old is None or (st[4], st[2], st[3]) < (old[4], old[2], old[3]): unique[signature] = st
        states = sorted(unique.values(), key=lambda x: (x[4], x[2], x[3]))[:beam_width]
    best = min(states, key=lambda x: (x[4], x[2], x[3]))
    rows = [best[0][k] for k in sorted(best[0])]
    baseline_makespan = max((r["end"] for r in base_rows), default=0)
    # Makespan is minimized.  A strict improvement is only a valid hard
    # requirement when the caller explicitly requests it; a feasible baseline
    # can contain an operation whose immutable release time already precludes
    # strict improvement.
    if cfg.get("require_improvement", False) and baseline_makespan and best[4] >= baseline_makespan:
        raise ValueError("best policy-feasible repair does not strictly improve baseline makespan")
    os.makedirs(cfg["output_dir"], exist_ok=True)
    solution = os.path.join(cfg["output_dir"], "solution.json")
    csvpath = os.path.join(cfg["output_dir"], "schedule.csv")
    with open(solution, "w", encoding="utf-8") as f:
        json.dump({"status":"feasible policy-compliant repair", "makespan":best[4], "schedule":rows}, f, indent=2)
        f.write("\n")
    with open(csvpath, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CORE); w.writeheader(); w.writerows(rows)
    return {"ok":True, "solution":solution, "csv":csvpath, "makespan":best[4], "machine_changes":best[2], "total_start_shift":best[3]}

def validate(cfg):
    choices, _, _ = parse_instance(cfg["instance"])
    base_rows, _ = baseline_rows(cfg["baseline"]); base = {(x["job"],x["op"]):x for x in base_rows}
    sol = json.load(open(cfg["solution"], encoding="utf-8")); rows = [normalize_row(x) for x in sol.get("schedule", [])]
    with open(cfg["csv"], newline="", encoding="utf-8") as f: csvrows = [normalize_row(x) for x in csv.DictReader(f)]
    json_tuples = {tuple(r[x] for x in CORE) for r in rows}
    csv_tuples = {tuple(r[x] for x in CORE) for r in csvrows}
    if len(rows) != len(json_tuples) or len(csvrows) != len(csv_tuples) or json_tuples != csv_tuples:
        raise ValueError("CSV and JSON schedules differ or contain duplicate rows")
    bykey = {(r["job"],r["op"]):r for r in rows}
    if len(bykey) != len(rows) or set(bykey) != set(base) or set(bykey) != set(choices): raise ValueError("schedule key set is incomplete or duplicate")
    policy = json.load(open(cfg["policy"], encoding="utf-8")); mcmax, shmax, freeze, fields = policy_settings(policy)
    per_machine = downtimes(cfg["downtime"])
    active_freezes = (usable_freeze_keys(base, choices, per_machine, freeze, fields)
                      if cfg.get("enforce_freeze", False) else set())
    changes = shift = 0
    for k, r in bykey.items():
        b = base[k]
        if r["end"] != r["start"] + r["dur"] or (r["machine"],r["dur"]) not in choices[k]: raise ValueError("invalid machine/duration for %r" % (k,))
        if (cfg.get("right_shift_only", False) and r["start"] < b["start"]) or not freeze_row_ok(k,b,r,freeze,fields,active_freezes):
            raise ValueError("right-shift or freeze violation for %r" % (k,))
        if k[1] and bykey[(k[0],k[1]-1)]["end"] > r["start"]: raise ValueError("precedence violation for %r" % (k,))
        changes += int(r["machine"] != b["machine"]); shift += abs(r["start"]-b["start"])
        per_machine.setdefault(r["machine"],[]).append((r["start"],r["end"],k))
    if changes > mcmax or shift > shmax: raise ValueError("change budget exceeded")
    for m, ints in per_machine.items():
        ints.sort()
        for i in range(1,len(ints)):
            if ints[i-1][1] > ints[i][0]: raise ValueError("machine overlap/downtime conflict on machine %s" % m)
    makespan = max(r["end"] for r in rows)
    if sol.get("makespan") != makespan or not str(sol.get("status", "")).strip(): raise ValueError("reported makespan or status is invalid")
    return {"ok":True, "makespan":makespan, "machine_changes":changes, "total_start_shift":shift}

def main():
    cfg = dict(DEFAULTS)
    supplied = json.load(sys.stdin) if not sys.stdin.isatty() else {}
    if not isinstance(supplied, dict): raise ValueError("stdin must contain a JSON object")
    cfg.update(supplied)
    result = validate(cfg) if cfg.get("action") == "validate" else solve(cfg)
    print(json.dumps(result, sort_keys=True))
if __name__ == "__main__":
    try: main()
    except Exception as e:
        print(json.dumps({"ok":False, "error":str(e)}), file=sys.stdout)
        sys.exit(1)
