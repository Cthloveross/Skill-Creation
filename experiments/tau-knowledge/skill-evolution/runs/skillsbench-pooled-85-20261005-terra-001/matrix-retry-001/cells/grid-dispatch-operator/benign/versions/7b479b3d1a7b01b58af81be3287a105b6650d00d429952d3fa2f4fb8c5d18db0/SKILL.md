---
name: dependency-free-dc-dispatch-reserve-report
description: Create report.json for a MATPOWER network using a lossless DC dispatch, transmission validation, and spinning-reserve capacity coupling without NumPy, SciPy, CasADi, or external solvers.
---

# Lossless DC dispatch and reserve report

Run `scripts/solve_dispatch.py` to read the supplied MATPOWER JSON snapshot and write the requested `report.json` artifact.

```json
{"network_path":"/root/network.json","report_path":"/root/report.json"}
```

The script reads JSON from stdin and emits JSON on stdout. Input fields are:

- `network_path` (optional): source MATPOWER JSON, default `/root/network.json`.
- `report_path` (optional): artifact destination, default `/root/report.json`.
- `tolerance` (optional): feasibility tolerance in MW, default `1e-6`.

Success output is `{ "ok": true, "report_path": ..., "validation": ..., "report": ... }`; failures are explicit `{ "ok": false, "error": ... }` values and no success is claimed.

## Method

The executable supports a top-level MATPOWER case or a case nested under `mpc`. It preserves source generator order and MATPOWER bus identifiers. Out-of-service generators receive zero energy and reserve. A zero transformer tap is interpreted as one.

It uses the lossless DC convention validated by the task:

`flow_ft = baseMVA / (BR_X * effective_tap) * (theta_f - theta_t - SHIFT_radians)`.

Only in-service branches participate. Dispatch balances `PD` exactly in every electrically connected component; it deliberately does **not** add an AC-loss or shunt-conductance allowance to lossless DC energy demand. The dependency-free conjugate-gradient power-flow solver reconstructs angles and flows for every candidate dispatch.

The initial MATPOWER `PG` schedule is used when it is usable, then adjusted within online PMIN/PMAX bounds to meet each component's active demand. Adjustments prefer lower incremental-cost generation for increases and higher incremental-cost generation for reductions. A deterministic transaction-based redispatch repair attempts to relieve RATE_A and declared angle-limit violations. This preserves component energy balance while moving generation between online units. The script rejects a schedule that cannot be independently validated rather than serializing an infeasible report.

Reserve is allocated after feasible energy dispatch. The script detects a supplied nonnegative reserve requirement recursively from commonly named `reserve requirement` / `reserve req` / `spinning reserve requirement` fields; absent data means no numerical reserve product is invented. Eligible online units receive reserve only from remaining `PMAX - PG` headroom, so `PG + reserve <= PMAX`. Explicit aligned eligibility vectors named `reserve_eligible`, `gen_reserve_eligible`, or `reserve.eligible` are honored.

Before serialization the script independently checks component balance, nodal DC residuals, generator limits, reserve coupling, branch RATE_A limits, angle limits, report totals, cost, margin, and top-three rated-line ranking. Costs use the source MATPOWER polynomial or piecewise-linear curve in physical MW. The generated report contains exactly the required report fields and ranks all live branches with positive RATE_A by DC loading, descending with source-order tie breaking.
