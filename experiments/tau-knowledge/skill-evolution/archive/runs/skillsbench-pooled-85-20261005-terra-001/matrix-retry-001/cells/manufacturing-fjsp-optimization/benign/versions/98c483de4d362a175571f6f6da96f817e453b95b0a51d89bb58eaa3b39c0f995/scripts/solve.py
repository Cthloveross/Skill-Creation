#!/usr/bin/env python3
"""Dependency-free FJSP baseline-repair solver.

Reads a JSON configuration on stdin, writes declared artifacts, and prints either
{"status":"ok",...} or raises a descriptive error.  See SKILL.md for schema.
"""
import csv
import json
import os
import sys
from collections import defaultdict


def norm(x):
    return ''.join(c for c in str(x).lower() if c.isalnum())


def read_json(path, required=True):
    if not path or not os.path.exists(path):
        if required:
            raise ValueError('required file is missing: %s' % path)
        return {}
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def parse_instance(path):
    with open(path, encoding='utf-8') as f:
        toks = f.read().split()
    try:
        vals = [int(x) for x in toks]
    except ValueError:
        raise ValueError('instance.txt must contain integer tokens')
    if len(vals) < 2:
        raise ValueError('instance lacks job and machine counts')
    jobs, machines, p = vals[0], vals[1], 2
    data = {}
    for j in range(jobs):
        if p >= len(vals):
            raise ValueError('truncated instance at job %d' % j)
        nops = vals[p]; p += 1
        for o in range(nops):
            if p >= len(vals):
                raise ValueError('truncated instance at (%d,%d)' % (j, o))
            n = vals[p]; p += 1
            if n <= 0 or p + 2*n > len(vals):
                raise ValueError('invalid machine-choice count at (%d,%d)' % (j, o))
            choices = {}
            for _ in range(n):
                m, d = vals[p], vals[p+1]; p += 2
                if m < 0 or m >= machines or d < 0:
                    raise ValueError('invalid machine or duration at (%d,%d)' % (j, o))
                choices[m] = d
            data[(j, o)] = choices
    if p != len(vals):
        raise ValueError('unexpected trailing instance tokens')
    return data


def first(obj, names, default=None):
    wanted = {norm(x) for x in names}
    def visit(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if norm(k) in wanted:
                    return v, True
            for v in x.values():
                z, found = visit(v)
                if found:
                    return z, True
        elif isinstance(x, list):
            for v in x:
                z, found = visit(v)
                if found:
                    return z, True
        return None, False
    value, found = visit(obj)
    return value if found else default


def number(obj, names, default=None):
    v = first(obj, names, default)
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        raise ValueError('policy value for %s must be numeric' % names[0])


def row_value(row, names, required=True):
    keys = {norm(k): v for k, v in row.items()}
    for name in names:
        if norm(name) in keys:
            return keys[norm(name)]
    if required:
        raise ValueError('schedule row lacks %s' % names[0])
    return None


def normalize_baseline(doc, expected):
    rows = doc.get('schedule') if isinstance(doc, dict) else None
    if not isinstance(rows, list):
        raise ValueError('baseline_solution.json must contain a schedule list')
    result, positions = {}, {}
    for pos, r in enumerate(rows):
        if not isinstance(r, dict):
            raise ValueError('baseline schedule row is not an object')
        try:
            j = int(row_value(r, ['job', 'job_id']))
            o = int(row_value(r, ['op', 'operation', 'operation_id']))
            m = int(row_value(r, ['machine', 'machine_id']))
            s = int(row_value(r, ['start', 'start_time']))
            e = int(row_value(r, ['end', 'end_time']))
            d = int(row_value(r, ['dur', 'duration', 'processing_time'], False) or (e-s))
        except (TypeError, ValueError):
            raise ValueError('baseline row contains a non-integer core field')
        key = (j, o)
        if key in result:
            raise ValueError('duplicate baseline operation %r' % (key,))
        result[key] = {'job':j, 'op':o, 'machine':m, 'start':s, 'end':e, 'dur':d}
        positions[key] = pos
    if set(result) != set(expected):
        missing, extra = set(expected)-set(result), set(result)-set(expected)
        raise ValueError('baseline keys differ from instance (missing=%s, extra=%s)' % (sorted(missing), sorted(extra)))
    return result, positions


def parse_downtime(path):
    if not path or not os.path.exists(path):
        return defaultdict(list)
    with open(path, newline='', encoding='utf-8-sig') as f:
        raw = list(csv.reader(f))
    out = defaultdict(list)
    if not raw:
        return out
    headers = [norm(x) for x in raw[0]]
    has_header = any(x in ('machine','machineid','start','starttime','end','endtime') for x in headers)
    if has_header:
        def col(names):
            for name in names:
                if norm(name) in headers:
                    return headers.index(norm(name))
            raise ValueError('downtime CSV lacks %s column' % names[0])
        mi, si, ei = col(['machine','machine_id']), col(['start','start_time']), col(['end','end_time'])
        records = raw[1:]
    else:
        mi, si, ei, records = 0, 1, 2, raw
    for r in records:
        if not r or all(not x.strip() for x in r):
            continue
        try:
            m, s, e = int(r[mi]), int(r[si]), int(r[ei])
        except (IndexError, ValueError):
            raise ValueError('invalid downtime CSV row: %r' % r)
        if e < s:
            raise ValueError('downtime end precedes start')
        if e > s:
            out[m].append((s, e))
    for m in out:
        out[m].sort()
    return out


def overlaps(a, b, c, d):
    return a < d and c < b


def policy_settings(policy, metrics):
    # Only explicit cap names are read from metrics; historical usage is not a cap.
    machine_cap = number(policy, ['max_machine_changes','machine_change_budget','maximum_machine_changes'])
    shift_cap = number(policy, ['max_total_start_shift','total_start_shift_budget','max_start_shift','start_shift_budget'])
    make_cap = number(policy, ['max_makespan','makespan_limit'])
    if make_cap is None:
        make_cap = number(metrics, ['max_makespan','makespan_limit'])
    boundary = number(policy, ['freeze_before','freeze_time','freeze_horizon','freeze_boundary'])
    fields = first(policy, ['freeze_fields','locked_fields','freeze_locked_fields'], [])
    if isinstance(fields, str):
        fields = [x.strip() for x in fields.split(',') if x.strip()]
    if not isinstance(fields, list):
        fields = []
    mapped = set()
    for f in fields:
        n = norm(f)
        if n in ('machine','machineid','assignment'): mapped.add('machine')
        elif n in ('start','starttime'): mapped.add('start')
        elif n in ('end','endtime'): mapped.add('end')
        elif n in ('dur','duration','processingtime'): mapped.add('dur')
    # A boundary with no supplied field list conventionally freezes all core fields.
    if boundary is not None and not mapped:
        mapped = {'machine','start','end','dur'}
    for label, cap in [('machine-change', machine_cap), ('start-shift', shift_cap)]:
        if cap is not None and cap < 0:
            raise ValueError('%s budget may not be negative' % label)
    return machine_cap, shift_cap, make_cap, boundary, mapped


def earliest(anchor, dur, machine, occupied, downtime):
    """Earliest [start,start+dur) at/after anchor avoiding half-open intervals."""
    s = anchor
    blockers = [(a,b) for a,b,_ in occupied.get(machine, [])] + list(downtime.get(machine, []))
    blockers.sort()
    while True:
        e = s + dur
        hit_end = None
        for a, b in blockers:
            if overlaps(s, e, a, b):
                hit_end = b if hit_end is None else max(hit_end, b)
        if hit_end is None:
            return s
        s = hit_end


def build_schedule(instance, base, positions, downtime, settings, beam_width):
    mcap, scap, _, boundary, locked = settings
    order = sorted(instance, key=lambda k: (k[1], base[k]['start'], positions[k]))
    frozen = {k for k in instance if boundary is not None and base[k]['start'] < boundary}
    # Fully time-and-machine frozen rows are permanent blockers even if their order is later.
    static = defaultdict(list)
    for k in frozen:
        b = base[k]
        if {'machine','start','end'} <= locked:
            static[b['machine']].append((b['start'], b['end'], k))

    states = [( {}, {m:list(v) for m,v in static.items()}, 0, 0 )] # rows, intervals, changes, L1 shift
    for key in order:
        j, o = key
        next_states = []
        b = base[key]
        for rows, intervals, changes, shift in states:
            pred_end = rows[(j,o-1)]['end'] if o else None
            anchor = max(b['start'], pred_end if pred_end is not None else b['start'])
            candidates = [b['machine']] if key in frozen and 'machine' in locked else sorted(instance[key])
            for machine in candidates:
                if machine not in instance[key]:
                    continue
                dur = instance[key][machine]
                if key in frozen and 'dur' in locked and dur != b['dur']:
                    continue
                occ = intervals.get(machine, [])
                # Ignore this operation's own permanent static reservation while checking it.
                occ_other = {machine:[x for x in occ if x[2] != key]}
                forced_start = b['start'] if key in frozen and 'start' in locked else None
                forced_end = b['end'] if key in frozen and 'end' in locked else None
                if forced_start is not None:
                    s = forced_start
                elif forced_end is not None:
                    s = forced_end - dur
                else:
                    s = earliest(anchor, dur, machine, occ_other, downtime)
                e = s + dur
                if s < anchor or (forced_end is not None and e != forced_end):
                    continue
                if any(overlaps(s,e,a,z) for a,z,_ in occ_other[machine]):
                    continue
                if any(overlaps(s,e,a,z) for a,z in downtime.get(machine, [])):
                    continue
                new_changes = changes + (machine != b['machine'])
                new_shift = shift + (s - b['start'])
                if new_changes < 0 or new_shift < 0:
                    continue
                if mcap is not None and new_changes > mcap:
                    continue
                if scap is not None and new_shift > scap:
                    continue
                row = {'job':j, 'op':o, 'machine':machine, 'start':s, 'end':e, 'dur':dur}
                nr = dict(rows); nr[key] = row
                ni = {m:list(v) for m,v in intervals.items()}
                if not any(x[2] == key for x in ni.get(machine, [])):
                    ni.setdefault(machine, []).append((s,e,key))
                next_states.append((nr, ni, new_changes, new_shift))
        if not next_states:
            raise ValueError('no policy-feasible placement exists for operation %r' % (key,))
        # Deterministic bounded beam. Current maximum completion is a valid primary lower bound.
        next_states.sort(key=lambda x: (max(r['end'] for r in x[0].values()), x[3], x[2],
                                        tuple((k, x[0][k]['machine'], x[0][k]['start']) for k in sorted(x[0]))))
        states = next_states[:beam_width]
    return min(states, key=lambda x: (max(r['end'] for r in x[0].values()), x[3], x[2]))[0]


def validate(rows, instance, base, downtime, settings):
    mcap, scap, make_cap, boundary, locked = settings
    if set(rows) != set(instance):
        raise ValueError('produced schedule does not preserve operation key set')
    changes = shift = 0
    machine_rows = defaultdict(list)
    for k, r in rows.items():
        b = base[k]
        if r['end'] != r['start'] + r['dur'] or r['start'] < b['start']:
            raise ValueError('right-shift or duration invariant fails at %r' % (k,))
        if r['machine'] not in instance[k] or instance[k][r['machine']] != r['dur']:
            raise ValueError('ineligible machine/duration at %r' % (k,))
        if boundary is not None and b['start'] < boundary:
            for f in locked:
                if r[f] != b[f]:
                    raise ValueError('freeze violation at %r field %s' % (k, f))
        changes += int(r['machine'] != b['machine'])
        shift += r['start'] - b['start']
        machine_rows[r['machine']].append((r['start'], r['end'], k))
        if any(overlaps(r['start'],r['end'],a,z) for a,z in downtime.get(r['machine'], [])):
            raise ValueError('downtime violation at %r' % (k,))
    for (j,o), r in rows.items():
        if o and rows[(j,o-1)]['end'] > r['start']:
            raise ValueError('precedence violation at %r' % ((j,o),))
    for m, vals in machine_rows.items():
        vals.sort()
        for (_, e, k1), (s, _, k2) in zip(vals, vals[1:]):
            if e > s:
                raise ValueError('machine overlap between %r and %r' % (k1,k2))
    if mcap is not None and changes > mcap or scap is not None and shift > scap:
        raise ValueError('policy budget violation')
    makespan = max((r['end'] for r in rows.values()), default=0)
    if make_cap is not None and makespan > make_cap:
        raise ValueError('makespan exceeds explicit cap')
    return makespan, changes, shift


def main():
    cfg = json.load(sys.stdin) if not sys.stdin.isatty() else {}
    if not isinstance(cfg, dict):
        raise ValueError('stdin configuration must be a JSON object')
    root = '/app'
    instance = parse_instance(cfg.get('instance_path', root+'/data/instance.txt'))
    baseline_doc = read_json(cfg.get('baseline_path', root+'/data/baseline_solution.json'))
    base, positions = normalize_baseline(baseline_doc, instance)
    downtime = parse_downtime(cfg.get('downtime_path', root+'/data/downtime.csv'))
    policy = read_json(cfg.get('policy_path', root+'/data/policy.json'), required=False)
    metrics = read_json(cfg.get('metrics_path', root+'/data/baseline_metrics.json'), required=False)
    settings = policy_settings(policy, metrics)
    beam = int(cfg.get('beam_width', 5000))
    if beam < 1:
        raise ValueError('beam_width must be at least one')
    rows = build_schedule(instance, base, positions, downtime, settings, beam)
    makespan, changes, shift = validate(rows, instance, base, downtime, settings)
    ordered = [rows[k] for k in sorted(rows)]
    solution = {'status':'feasible_repaired', 'makespan':makespan, 'schedule':ordered}
    spath = cfg.get('solution_path', root+'/output/solution.json')
    cpath = cfg.get('csv_path', root+'/output/schedule.csv')
    os.makedirs(os.path.dirname(spath) or '.', exist_ok=True)
    os.makedirs(os.path.dirname(cpath) or '.', exist_ok=True)
    with open(spath, 'w', encoding='utf-8') as f:
        json.dump(solution, f, indent=2)
        f.write('\n')
    with open(cpath, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=['job','op','machine','start','end','dur'])
        w.writeheader(); w.writerows(ordered)
    # Re-check the tuple identity that the task observes across artifacts.
    with open(cpath, newline='', encoding='utf-8') as f:
        csv_rows = [{k:int(v) for k,v in r.items()} for r in csv.DictReader(f)]
    if {tuple(r[k] for k in ('job','op','machine','start','end','dur')) for r in csv_rows} != {tuple(r[k] for k in ('job','op','machine','start','end','dur')) for r in ordered}:
        raise RuntimeError('internal JSON/CSV consistency check failed')
    print(json.dumps({'status':'ok','makespan':makespan,'machine_changes':changes,'total_start_shift':shift}))

if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(json.dumps({'status':'error','error':str(exc)}))
        sys.exit(1)
