---
name: fjsp-baseline-repair
summary: Create and validate a policy-compliant flexible job-shop repair from instance, downtime, policy, and baseline files.
description: Use this skill for FJSP production-planning tasks that require solution.json and a matching schedule.csv while preserving a baseline under right-shift, freeze, downtime, and change-budget constraints.
---

# FJSP baseline-repair skill

This skill reads the task inputs at runtime; it does not contain instance-specific schedules or IDs. It produces a complete schedule whose operation keys are exactly the baseline keys.

## Method

1. Parse the flexible-job-shop instance into eligible `(machine, duration)` alternatives for every `(job, op)`.
2. Load baseline rows, machine downtime intervals, and policy limits.
3. Process operations in precedence-aware order: operation index, baseline start, then original baseline-row order.
4. For each partial schedule, place an operation at the earliest half-open interval `[start, start+duration)` at or after both its baseline start and predecessor end. It cannot overlap already placed work or downtime. Machine alternatives are explored with a bounded deterministic beam search, so alternate eligible machines can improve makespan while respecting budgets.
5. Enforce frozen fields for rows whose baseline start precedes the configured freeze boundary, maximum machine changes, maximum aggregate start shift, eligibility, duration, precedence, and non-overlap.
6. Select the feasible candidate with lowest makespan (then lower machine changes and shift), require a makespan strictly lower than the baseline makespan when a baseline makespan exists, and write the two required artifacts.

The solver assumes the documented zero-based instance convention and integral time values. It intentionally treats intervals as half-open, so back-to-back work is allowed.

## Run

The script accepts one JSON object on stdin and emits a JSON result object on stdout.

```sh
printf '%s' '{"action":"solve","instance":"/app/data/instance.txt","baseline":"/app/data/baseline_solution.json","downtime":"/app/data/downtime.csv","policy":"/app/data/policy.json","output_dir":"/app/output"}' | python3 /app/environment/skills/current/scripts/fjsp_repair.py
```

All path fields are optional for `solve`; the defaults are the `/app/data/...` inputs and `/app/output`. The output JSON has `ok`, `solution`, `csv`, `makespan`, `machine_changes`, and `total_start_shift` on success. If constraints are inconsistent or no strictly improved repair is found, it exits nonzero rather than silently writing an invalid answer.

## Validate generated artifacts

```sh
printf '%s' '{"action":"validate","instance":"/app/data/instance.txt","baseline":"/app/data/baseline_solution.json","downtime":"/app/data/downtime.csv","policy":"/app/data/policy.json","solution":"/app/output/solution.json","csv":"/app/output/schedule.csv"}' | python3 /app/environment/skills/current/scripts/fjsp_repair.py
```

Validation checks JSON/CSV tuple equality, the reported makespan, row completeness, eligibility and duration, right-shift, freeze locks, policy budgets, precedence, machine non-overlap, and downtime. Review an error instead of submitting outputs if validation fails.

Policy parsing supports common names such as `max_machine_changes`, `max_total_start_shift`, `freeze_before`/`freeze_until`, and `frozen_fields`/`locked_fields`; nested policy objects are also searched. A threshold with no explicit lock list conservatively locks machine, start, and end.
