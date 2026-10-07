---
name: dc-dispatch-reserve-report
description: Solve a MATPOWER-style lossless DC economic dispatch with co-optimized spinning reserve, then write the required report.json. Use when a network JSON supplies buses, generators, branches, polynomial energy costs, and a system spinning-reserve requirement.
---

# DC Dispatch and Reserve Report

Run the packaged entrypoint from the task workspace. It reads the current case at runtime, builds explicit maps for externally numbered buses and source-order generators, solves energy and reserve together, validates the unrounded solution, and writes the requested JSON report.

```bash
python /app/environment/skills/current/scripts/solve_dispatch.py <<'JSON'
{"network_path":"/root/network.json","report_path":"/root/report.json"}
JSON
```

With no stdin, the same script defaults to `/root/network.json` and `/root/report.json`. The script emits a small JSON execution record to stdout; the deliverable is the file named by `report_path`.

## Input assumptions and supported fields

The network is a JSON object containing MATPOWER arrays `baseMVA`, `bus`, `gen`, `branch`, and `gencost`. It honors MATPOWER in-service flags, PMIN/PMAX, branch RATE_A, tap (zero means one), phase shift, and branch angle limits. Only in-service branches with positive RATE_A receive thermal constraints. Energy costs must be convex polynomial MATPOWER model-2 costs of degree at most two.

A reserve requirement is required. The entrypoint recognizes direct numeric fields `reserve_requirement_MW`, `spinning_reserve_requirement_MW`, `spinning_reserve_requirement`, `reserve_requirement`, or `reserve_req`; it also recognizes those names inside `reserve` or `reserves`. A percent field ending in `_pct` is interpreted as a percent of total load. Optional reserve offer vectors/scalars may be supplied as `reserve_cost_per_MW`, `reserve_cost`, `reserve_costs`, or as `cost_per_MW`/`cost` inside `reserve` or `reserves`. Optional per-generator eligibility and capability vectors are accepted as `reserve_eligible`/`reserve_eligibility` and `reserve_max_MW`/`reserve_max` (also inside the reserve object). In their absence, every online generator is reserve eligible and has no reserve limit beyond `Pg + R <= Pmax`.

The solver requires CVXPY with a suitable installed QP solver (it tries OSQP, then CLARABEL, then SCIPY). This is intentional: it solves the dispatch monolithically rather than choosing energy and reserve sequentially. Unsupported cost models, missing reserve requirements, infeasible cases, unavailable solvers, and post-solve feasibility failures result in a nonzero exit and a JSON error record; no misleading report is written.

## Model and checks

For active branch `k`, the model uses `f_k = baseMVA/(x_k*tap_k) * (theta_from - theta_to - shift_k)`. At each bus it enforces generation minus demand equal to net outgoing flow. It fixes a declared MATPOWER reference-bus angle to zero, enforces generator energy bounds, line ratings, angle bounds where supplied, nonnegative reserve, energy-plus-reserve capacity coupling, and total reserve at least the input requirement. The objective is energy polynomial cost plus explicitly supplied reserve offers only.

Before producing the report, the script independently recomputes bus residuals, line flows, ratings, generator bounds, capacity coupling, reserve total, objective, totals, and remaining online capacity. Values are retained at solver precision during these checks and rounded only while serializing report fields. `most_loaded_lines` contains up to three active, rated branches ranked by descending absolute DC-flow loading, then deterministic endpoint/source-order tie breakers.

The stdout `validation` object should show violations no larger than the stated numerical tolerance. Inspect it and confirm that `report.json` exists before returning the completed task.
