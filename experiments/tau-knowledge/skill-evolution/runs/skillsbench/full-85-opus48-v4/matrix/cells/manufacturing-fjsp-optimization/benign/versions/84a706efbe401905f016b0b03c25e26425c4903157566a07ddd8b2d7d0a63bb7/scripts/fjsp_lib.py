"""Reusable helpers for FJSP baseline repair.

All indices (job, op, machine) are 0-based. Intervals are half-open [start,end).
This module is task-independent: it reads whatever instance/baseline/downtime/
policy data is supplied at runtime and never hardcodes instance-specific values.
"""
import csv
import io
import json


def overlaps(a_s, a_e, b_s, b_e):
    """Half-open overlap test: True iff [a_s,a_e) and [b_s,b_e) intersect."""
    return a_s < b_e and b_s < a_e


def parse_instance(text):
    """Parse FJSP instance text into eligibility map and (J, M).

    Returns (elig, J, M, ops_per_job) where
      elig[(job, op)] = {machine: dur, ...}
      ops_per_job[job] = number of operations in that job.
    """
    toks = text.split()
    idx = 0

    def nxt():
        nonlocal idx
        v = toks[idx]
        idx += 1
        return v

    J = int(float(nxt()))
    M = int(float(nxt()))
    elig = {}
    ops_per_job = {}
    for j in range(J):
        n_ops = int(float(nxt()))
        ops_per_job[j] = n_ops
        for o in range(n_ops):
            k = int(float(nxt()))
            opts = {}
            for _ in range(k):
                m = int(float(nxt()))
                d = int(float(nxt()))
                opts[m] = d
            elig[(j, o)] = opts
    return elig, J, M, ops_per_job


def load_baseline(obj):
    """Normalize a baseline solution (list or {'schedule': [...]}) to rows.

    Each returned row is a dict with int job, op, machine, start, end, dur and
    an added 'pos' (original list index) for stable tie-breaking.
    """
    if isinstance(obj, dict):
        rows = obj.get("schedule") or obj.get("operations") or obj.get("ops")
        if rows is None:
            # maybe the dict itself maps something; try values that are lists
            for v in obj.values():
                if isinstance(v, list):
                    rows = v
                    break
    else:
        rows = obj
    if rows is None:
        raise ValueError("could not locate schedule rows in baseline")
    out = []
    for pos, r in enumerate(rows):
        out.append({
            "job": int(r["job"]),
            "op": int(r["op"]),
            "machine": int(r["machine"]),
            "start": int(r["start"]),
            "end": int(r["end"]),
            "dur": int(r["dur"]),
            "pos": pos,
        })
    return out


def parse_downtime(text):
    """Parse downtime CSV into {machine: [(start,end), ...]}.

    Columns are detected case-insensitively: one containing 'mach', one
    containing 'start' (or 'begin'/'from'), one containing 'end' (or 'stop'/'to').
    If there is no recognizable header, assumes columns machine,start,end.
    """
    text = text.strip()
    if not text:
        return {}
    reader = csv.reader(io.StringIO(text))
    rows = [r for r in reader if any(c.strip() for c in r)]
    if not rows:
        return {}
    header = [c.strip().lower() for c in rows[0]]
    has_header = not _looks_numeric(rows[0])
    if has_header:
        mi = _find_col(header, ["mach"]) if _find_col(header, ["mach"]) is not None else 0
        si = _find_col(header, ["start", "begin", "from"]) or 1
        ei = _find_col(header, ["end", "stop", "finish", "to"]) or 2
        data = rows[1:]
    else:
        mi, si, ei = 0, 1, 2
        data = rows
    dt = {}
    for r in data:
        if max(mi, si, ei) >= len(r):
            continue
        try:
            m = int(float(r[mi]))
            s = int(float(r[si]))
            e = int(float(r[ei]))
        except (ValueError, TypeError):
            continue
        dt.setdefault(m, []).append((s, e))
    for m in dt:
        dt[m].sort()
    return dt


def _looks_numeric(row):
    try:
        for c in row:
            float(c)
        return True
    except (ValueError, TypeError):
        return False


def _find_col(header, keys):
    for i, h in enumerate(header):
        for k in keys:
            if k in h:
                return i
    return None


def _walk_items(policy):
    """Yield (key, value) over a possibly nested policy dict."""
    if isinstance(policy, dict):
        for k, v in policy.items():
            yield k, v
            if isinstance(v, dict):
                for kk, vv in _walk_items(v):
                    yield kk, vv


def parse_policy(policy):
    """Extract budgets and freeze config from a policy dict with flexible keys.

    Returns dict:
      max_machine_changes: int|None
      max_total_start_shift: int|None
      freeze_threshold: int|None  (operations with baseline start < threshold are frozen)
      freeze_fields: list[str]
    """
    max_mc = None
    max_shift = None
    freeze_threshold = None
    freeze_fields = None

    for k, v in _walk_items(policy):
        kl = str(k).lower()
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            if "mach" in kl and ("change" in kl or "reassign" in kl or "swap" in kl):
                max_mc = int(v)
            elif ("shift" in kl or "l1" in kl or "disrupt" in kl) and "max" in kl:
                max_shift = int(v)
            elif "shift" in kl or "l1" in kl:
                if max_shift is None:
                    max_shift = int(v)
            if "freeze" in kl and ("horizon" in kl or "threshold" in kl or
                                   "time" in kl or "boundary" in kl or
                                   "before" in kl or "until" in kl or "window" in kl):
                freeze_threshold = int(v)

    # Freeze may be nested object: find dict whose key contains 'freeze'.
    for k, v in _walk_items(policy):
        kl = str(k).lower()
        if "freeze" in kl and isinstance(v, dict):
            for kk, vv in v.items():
                kkl = str(kk).lower()
                if isinstance(vv, (int, float)) and not isinstance(vv, bool) and (
                        "horizon" in kkl or "threshold" in kkl or "time" in kkl or
                        "boundary" in kkl or "before" in kkl or "until" in kkl or
                        kkl in ("t", "h")):
                    freeze_threshold = int(vv)
                if isinstance(vv, list) and ("field" in kkl or "lock" in kkl):
                    freeze_fields = [str(x).lower() for x in vv]
        if ("freeze" in kl) and isinstance(v, list) and ("field" in kl or "lock" in kl):
            freeze_fields = [str(x).lower() for x in v]

    if freeze_fields is None:
        freeze_fields = ["machine", "start", "end"]
    return {
        "max_machine_changes": max_mc,
        "max_total_start_shift": max_shift,
        "freeze_threshold": freeze_threshold,
        "freeze_fields": freeze_fields,
    }


def earliest_feasible_start(anchor, dur, placed, downtimes):
    """Smallest start >= anchor whose [start,start+dur) avoids all placed
    intervals and downtime windows (both lists of (s,e)). Ripple until stable."""
    s = anchor
    windows = list(placed) + list(downtimes)
    while True:
        moved = False
        for (ws, we) in windows:
            if overlaps(s, s + dur, ws, we):
                s = we
                moved = True
        if not moved:
            return s


def repair(elig, baseline_rows, downtime, policy):
    """Produce a right-shift-only, locally-minimal, downtime-feasible repair.

    Keeps every operation on its baseline machine (0 machine changes).
    Returns (schedule_rows, info) where schedule_rows are dicts with
    job,op,machine,start,end,dur and info holds metrics/warnings.
    """
    warnings = []
    base_by_key = {(r["job"], r["op"]): r for r in baseline_rows}
    freeze_t = policy.get("freeze_threshold")

    # Precedence-aware order: op asc, baseline start asc, original pos asc.
    order = sorted(baseline_rows, key=lambda r: (r["op"], r["start"], r["pos"]))

    machine_intervals = {}   # machine -> list of (start, end) placed
    job_prev_end = {}        # job -> end of last placed op
    result = {}

    for r in order:
        j, o, m0 = r["job"], r["op"], r["machine"]
        base_start = r["start"]
        frozen = (freeze_t is not None and base_start < freeze_t)

        if frozen:
            m = r["machine"]
            dur = r["dur"]
            start = r["start"]
            end = r["end"]
        else:
            m = m0
            opts = elig.get((j, o), {})
            if m in opts:
                dur = opts[m]
            else:
                dur = r["dur"]
                warnings.append(
                    "baseline machine %d not eligible for (%d,%d); kept baseline dur" % (m, j, o))
            prev_end = job_prev_end.get(j, 0)
            anchor = max(base_start, prev_end)
            placed = machine_intervals.get(m, [])
            downs = downtime.get(m, [])
            start = earliest_feasible_start(anchor, dur, placed, downs)
            end = start + dur

        machine_intervals.setdefault(m, []).append((start, end))
        job_prev_end[j] = max(job_prev_end.get(j, 0), end)
        result[(j, o)] = {
            "job": j, "op": o, "machine": m,
            "start": start, "end": end, "dur": dur,
        }

    rows = [result[k] for k in sorted(result.keys())]

    # Metrics
    machine_changes = 0
    total_shift = 0
    for row in rows:
        key = (row["job"], row["op"])
        b = base_by_key.get(key)
        if b is None:
            continue
        if row["machine"] != b["machine"]:
            machine_changes += 1
        total_shift += abs(row["start"] - b["start"])

    makespan = max((row["end"] for row in rows), default=0)

    info = {
        "machine_changes": machine_changes,
        "total_start_shift": total_shift,
        "makespan": makespan,
        "warnings": warnings,
    }
    return rows, info


def count_downtime_violations(rows, downtime):
    v = 0
    for row in rows:
        for (ds, de) in downtime.get(row["machine"], []):
            if overlaps(row["start"], row["end"], ds, de):
                v += 1
                break
    return v


def validate_schedule(rows, elig, baseline_rows, downtime, policy):
    """Return list of problem strings; empty means all core constraints pass."""
    problems = []
    base_by_key = {(r["job"], r["op"]): r for r in baseline_rows}
    seen = set()
    for row in rows:
        key = (row["job"], row["op"])
        if key in seen:
            problems.append("duplicate op %s" % (key,))
        seen.add(key)
        if row["end"] != row["start"] + row["dur"]:
            problems.append("end!=start+dur for %s" % (key,))
        opts = elig.get(key)
        if opts is None:
            problems.append("unknown op %s" % (key,))
        elif row["machine"] not in opts:
            problems.append("ineligible machine for %s" % (key,))
        elif opts[row["machine"]] != row["dur"]:
            problems.append("wrong dur for %s on machine %d" % (key, row["machine"]))
        b = base_by_key.get(key)
        if b is not None and row["start"] < b["start"]:
            problems.append("right-shift violated for %s" % (key,))

    # key set
    if set((r["job"], r["op"]) for r in rows) != set(base_by_key.keys()):
        problems.append("(job,op) key set differs from baseline")

    # precedence
    by_job = {}
    for row in rows:
        by_job.setdefault(row["job"], {})[row["op"]] = row
    for j, ops in by_job.items():
        for o in sorted(ops):
            if o - 1 in ops and ops[o]["start"] < ops[o - 1]["end"]:
                problems.append("precedence violated job %d op %d" % (j, o))

    # machine overlap
    by_m = {}
    for row in rows:
        by_m.setdefault(row["machine"], []).append(row)
    for m, lst in by_m.items():
        lst2 = sorted(lst, key=lambda r: r["start"])
        for i in range(1, len(lst2)):
            if lst2[i]["start"] < lst2[i - 1]["end"]:
                problems.append("machine %d overlap" % m)
                break

    # downtime
    dv = count_downtime_violations(rows, downtime)
    if dv:
        problems.append("%d downtime violations" % dv)

    return problems
