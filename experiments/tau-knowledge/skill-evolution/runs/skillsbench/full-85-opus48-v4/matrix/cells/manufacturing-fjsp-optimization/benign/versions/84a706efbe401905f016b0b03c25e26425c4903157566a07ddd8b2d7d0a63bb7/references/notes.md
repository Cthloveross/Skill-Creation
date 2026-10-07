# FJSP repair reference notes

## Instance format (instance.txt)
- Line 1: `J M` (job count, machine count).
- For each job: an operation count, then for each operation `k` followed by `k`
  `(machine duration)` pairs. All indices 0-based.
- The chosen machine's duration must match the pair; using the wrong duration or
  an ineligible machine makes the schedule invalid.

## Downtime (downtime.csv)
- Half-open windows `[start, end)` per machine. Columns detected
  case-insensitively (machine / start / end). No overlap allowed between an
  operation interval and any downtime window on its machine.

## Policy (policy.json)
- Max machine changes: number of ops reassigned to a different machine than
  baseline. Our repair keeps baseline machines (0 changes) to stay safe.
- Max total start shift: L1 sum of |new_start - baseline_start|; minimized by
  the locally-minimal right-shift.
- Freeze: operations whose baseline start < freeze threshold keep their frozen
  fields (machine/start/end) unchanged. Key names vary; parser is flexible.

## Core invariants checked
- `end == start + dur` per row.
- Eligibility + matching duration.
- Precedence: `end(j,o) <= start(j,o+1)`.
- No same-machine overlap (half-open: back-to-back allowed).
- Right-shift-only: `new_start >= baseline_start`.
- Zero downtime violations.
- Full `(job,op)` key set preserved, no dupes/omissions.
- `makespan == max(end)`; aim for not worse than baseline makespan.
- solution.json and schedule.csv carry identical tuple sets.

## Repair ordering
Process ops by (op index asc, baseline start asc, original position asc) so a
predecessor is always placed before its successor; greedily pick the earliest
feasible start >= anchor = max(baseline_start, prev_op_end), pushing right past
any conflicting placed interval or downtime window until stable.
