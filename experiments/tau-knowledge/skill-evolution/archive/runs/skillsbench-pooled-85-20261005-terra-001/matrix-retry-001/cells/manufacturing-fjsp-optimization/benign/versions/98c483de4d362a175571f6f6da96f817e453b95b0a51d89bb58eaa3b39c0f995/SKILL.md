---
name: fjsp-baseline-repair
summary: Create and validate a policy-constrained, right-shift-only repair of a Flexible Job-Shop baseline schedule with machine downtime.
---

# FJSP baseline repair

Use this Skill when `/app/data/instance.txt`, `baseline_solution.json`, `downtime.csv`, and optional policy/metric files describe a flexible job-shop schedule that must be repaired without advancing baseline starts. It creates the required matching JSON and CSV artifacts.

## Method

1. Parse the standard FJSP instance into eligible `(machine, duration)` choices for every zero-based `(job, op)` key.
2. Read and validate the baseline key set. Operations are placed in precedence-aware order: operation index, baseline start, then original baseline-list position.
3. For each possible eligible assignment, place an operation at its earliest time at or after both its baseline start and predecessor completion. Placement skips existing machine intervals and downtime using half-open interval semantics.
4. Honor freeze fields for operations whose baseline start is before the configured freeze boundary. Track reassigned machines and total right shift, rejecting states above policy caps.
5. Keep a bounded beam of schedules, selecting the final feasible candidate by makespan, total shift, then machine changes. The beam considers alternate eligible machines rather than assuming the baseline machine must be retained.
6. Validate every hard constraint and write identical operation tuples to JSON and CSV.

The solver treats these common policy spellings as aliases: machine-change caps (`max_machine_changes`, `machine_change_budget`), start-shift caps (`max_total_start_shift`, `total_start_shift_budget`), freeze boundaries (`freeze_before`, `freeze_time`, `freeze_horizon`), and locked-field lists (`freeze_fields`, `locked_fields`). A nested policy object is supported. Omitted caps are unlimited. A frozen operation is one with baseline start strictly below the freeze boundary.

## Run

From `/app`, run:

```sh
python3 scripts/solve.py <<'JSON'
{}
JSON
```

The default paths are the task paths and outputs are `/app/output/solution.json` and `/app/output/schedule.csv`. The program reads one JSON object from stdin and emits a concise JSON result on stdout. Supported optional input keys are:

```json
{
  "instance_path": "/app/data/instance.txt",
  "baseline_path": "/app/data/baseline_solution.json",
  "downtime_path": "/app/data/downtime.csv",
  "policy_path": "/app/data/policy.json",
  "metrics_path": "/app/data/baseline_metrics.json",
  "solution_path": "/app/output/solution.json",
  "csv_path": "/app/output/schedule.csv",
  "beam_width": 5000
}
```

`metrics_path` is read only for an optional explicit makespan cap such as `max_makespan`; it is not mistaken for a policy usage value. Set `beam_width` higher for instances with many machine alternatives when runtime permits.

## Output and validation

The JSON artifact has a nonempty `status`, a makespan computed from actual operation ends, and one row for every instance operation. The CSV header is exactly `job,op,machine,start,end,dur`; its rows are generated from the same in-memory schedule. Before either output is written, the solver verifies eligibility/duration, complete key preservation, precedence, machine non-overlap, downtime avoidance, right-shift-only starts, freeze restrictions, budget caps, makespan, and JSON/CSV tuple equality. It exits with an explanatory error instead of emitting a misleading schedule if frozen commitments, budgets, or other constraints make repair infeasible.

The search is deterministic but bounded; `feasible_repaired` means feasible, not a proof of global makespan optimality.
