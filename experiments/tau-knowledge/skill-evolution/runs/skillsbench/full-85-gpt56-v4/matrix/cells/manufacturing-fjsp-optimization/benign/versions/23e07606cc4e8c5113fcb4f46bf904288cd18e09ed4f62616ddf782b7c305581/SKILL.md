---
name: fjsp-policy-scheduler
summary: Build and validate a downtime-feasible flexible job-shop schedule subject to machine-change and aggregate start-time-change budgets.
description: Use for FJSP planning tasks that supply an instance, baseline schedule, downtime CSV, and policy data and require matching solution.json and schedule.csv artifacts.
---

# FJSP policy scheduler

Run the packaged entrypoint to load the current task data, construct a complete schedule, and write the requested JSON and CSV.  It never embeds operations or values from a particular instance.

## Scheduling method

The solver parses each operation's eligible `(machine, duration)` options, baseline rows, outage intervals, and common nested policy names for maximum machine changes, total L1 start-time shift, and optional makespan maximum or maximum-to-baseline ratio. It processes operations in precedence-aware `(op, baseline start, input position)` order. For every partial candidate it tries eligible machines and places the operation at the earliest non-overlapping half-open interval after its predecessor. A deterministic beam retains alternatives under both budgets and selects lowest makespan, then lower change counts and shift. On small integral instances, a bounded exact refinement can reduce the machine-change count without worsening the beam makespan bound.

It checks machine eligibility and duration, job precedence, machine and downtime non-overlap, complete operation keys, makespan, and exact JSON/CSV tuple agreement. Starts may move either direction because an L1 start-shift budget measures absolute deviation. Pass `"right_shift_only": true` only where the task explicitly requires baseline-repair right shifts.

Freeze metadata is parsed, but a freeze block is not a change budget by itself. To make it a hard requirement, pass `"enforce_freeze": true`; only baseline freeze rows that are individually compatible with their supplied downtime are locked. This avoids outputting an outage-violating schedule when task inputs contain a frozen baseline operation already inside a new outage. An explicit hard freeze/right-shift request that is infeasible produces a nonzero error rather than invalid artifacts.

## Run

The script reads one JSON object from stdin and writes one result object to stdout. Path fields are optional; their defaults are the standard `/app/data` files and `/app/output`.

```sh
printf '%s' '{"action":"solve","instance":"/app/data/instance.txt","baseline":"/app/data/baseline_solution.json","downtime":"/app/data/downtime.csv","policy":"/app/data/policy.json","output_dir":"/app/output"}' \
 | python3 /app/environment/skills/current/scripts/fjsp_repair.py
```

Successful output fields are `ok`, `solution`, `csv`, `makespan`, `machine_changes`, and `total_start_shift`. It writes `/app/output/solution.json` with nonempty `status`, computed `makespan`, and rows containing `job, op, machine, start, end, dur`; it writes the same rows to `/app/output/schedule.csv` with those headers.

Optional input switches are `beam_width` (positive integer), `right_shift_only` (default `false`), `enforce_freeze` (default `false`), `require_improvement` (default `false`), `exact_refine` (default `true` for at most 14 operations), `exact_max_operations`, `exact_node_limit`, and `exact_shift_slack` (default `1`, limiting extra L1 shift spent to lower reassignments). Set strict switches only if they are express requirements of the task.

## Validate

Validate the generated deliverables before returning them:

```sh
printf '%s' '{"action":"validate","instance":"/app/data/instance.txt","baseline":"/app/data/baseline_solution.json","downtime":"/app/data/downtime.csv","policy":"/app/data/policy.json","solution":"/app/output/solution.json","csv":"/app/output/schedule.csv"}' \
 | python3 /app/environment/skills/current/scripts/fjsp_repair.py
```

A successful validator result has `ok: true`. A failure identifies malformed inputs, missing or duplicate operation keys, mismatched CSV data, infeasible assignment/timing, exceeded budget or makespan guard, or an enabled explicit policy constraint. Do not treat a nonzero result as a valid schedule.
