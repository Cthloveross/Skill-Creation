---
name: fjsp-baseline-repair
description: >-
  Repair an infeasible Flexible Job-Shop (FJSP) baseline schedule so it avoids
  machine downtime windows while obeying right-shift-only, local minimality,
  precedence, no-overlap and policy-budget (machine-change / L1 start-shift /
  freeze-window) constraints. Reads instance.txt, downtime.csv, policy.json and
  a baseline_solution.json, then writes a consistent solution.json + schedule.csv
  with a correctly computed makespan. Use for the manufacturing-fjsp-optimization
  task or any "repair this baseline FJSP schedule" request.
---

# FJSP Baseline Repair

## When to use
Use this Skill whenever you are given an FJSP **baseline** schedule plus newly
introduced machine **downtime windows** and must produce a feasible repaired
schedule under organizational **policy budgets**. The deliverables are
`/app/output/solution.json` and `/app/output/schedule.csv` carrying identical
operation data.

## Inputs (default directory `/app/data/`)
- `instance.txt` — FJSP instance. First line `J M`. Each job block starts with
  its operation count; each operation lists `k` followed by `k` `(machine dur)`
  pairs. All indices 0-based.
- `baseline_solution.json` — the baseline schedule. May be a list of rows or an
  object with a `schedule` list. Each row has `job, op, machine, start, end, dur`.
- `downtime.csv` — half-open `[start,end)` unavailable windows per machine.
  Columns are detected case-insensitively (a machine column, a start column, an
  end column).
- `policy.json` — budget/freeze policy. Key names vary; the parser searches for
  a max machine-change count, a max total (L1) start-shift, and a freeze config
  (a time threshold + optionally locked fields).
- `baseline_metrics.json` — reference metrics (makespan etc.), used only for the
  final "no worse" sanity report.

## Required outputs
`/app/output/solution.json`:
```
{ "status": "", "makespan": <int>, "schedule": [ {job,op,machine,start,end,dur}, ... ] }
```
`/app/output/schedule.csv` with header `job,op,machine,start,end,dur` and the
**exact same set** of operation tuples (order-independent).

## Method (what the script does)
Right-shift-only, locally-minimal repair that keeps every operation on its
baseline machine (so machine-change count stays 0 and the machine-change budget
is never exceeded), and delays operations only as needed:

1. Parse instance eligibility `{(job,op): {machine: dur}}`.
2. Load baseline rows; preserve the complete `(job,op)` key set exactly.
3. Process operations in **precedence-aware** order: op-index ascending, then
   baseline start ascending, then original list position.
4. For each operation:
   - If its baseline start is inside the **freeze horizon**, keep the baseline
     machine/start/end/dur unchanged (freeze takes precedence) and reserve its
     interval.
   - Otherwise keep the baseline machine, set `dur` from eligibility, compute the
     **anchor** = max(baseline_start, end of previous op of same job), then pick
     the earliest start `>= anchor` whose half-open interval `[s, s+dur)` neither
     overlaps any **downtime window** on that machine nor any already-placed
     interval on that machine. Overlap: `a < d and c < b` (back-to-back `end==start`
     is allowed).
   - Pushing right re-triggers the scan until stable (ripple propagation).
5. Makespan = max `end` across all placed operations (computed from the schedule).
6. Write `solution.json` and `schedule.csv` with identical data, plus a metrics
   report (machine changes, L1 start shift, downtime violations, budget checks).

This yields zero downtime violations, satisfies right-shift-only and local
minimality, keeps machine-change count at 0, and minimizes aggregate L1 shift
(hence the smallest makespan achievable under right-shift-only).

## Running it
The script reads an optional JSON config on stdin and prints a JSON report on
stdout. With no stdin it uses the task defaults.

```
# default paths (/app/data -> /app/output)
echo '{}' | python3 /app/environment/skills/current/scripts/run_repair.py

# or explicit
echo '{"data_dir":"/app/data","output_dir":"/app/output"}' | \
  python3 /app/environment/skills/current/scripts/run_repair.py
```

Stdin schema (all optional):
```
{"data_dir": str, "output_dir": str,
 "instance": str, "baseline": str, "downtime": str, "policy": str,
 "baseline_metrics": str, "status": str}
```
Stdout schema:
```
{"ok": bool, "makespan": int, "baseline_makespan": int|null,
 "machine_changes": int, "total_start_shift": int,
 "downtime_violations": int, "num_ops": int,
 "budget": {"max_machine_changes": .., "max_total_start_shift": ..,
            "machine_changes_ok": bool, "shift_ok": bool},
 "freeze": {...}, "warnings": [..],
 "solution_path": str, "schedule_csv_path": str}
```

## Validation after running
Re-run the entrypoint to regenerate outputs, then confirm from the report and
the files:
- `ok` is true, `downtime_violations` == 0.
- `machine_changes_ok` and `shift_ok` are true (budgets respected).
- Each row satisfies `end == start + dur`; every operation is on an eligible
  machine with the matching duration; precedence holds; no same-machine overlap.
- `new_start >= baseline_start` for every operation (right-shift-only).
- `makespan` equals the max `end`, and is not worse than `baseline_makespan`.
- `solution.json` and `schedule.csv` contain the identical set of
  `(job,op,machine,start,end,dur)` tuples and the full baseline `(job,op)` set.

You can run the packaged checker:
```
echo '{"data_dir":"/app/data","output_dir":"/app/output"}' | \
  python3 /app/environment/skills/current/scripts/validate.py
```

## Handling missing / unsupported data
- If `policy.json` lacks a budget key, that budget is treated as unbounded and a
  warning is emitted (the 0-machine-change strategy keeps machine budgets safe).
- If no freeze config is found, no operations are frozen.
- If a baseline machine is not listed as eligible for an operation, the baseline
  `dur` is used and a warning is recorded.
- If an output cannot be written, the error is reported and `ok` is false.

See `references/notes.md` for format details.
