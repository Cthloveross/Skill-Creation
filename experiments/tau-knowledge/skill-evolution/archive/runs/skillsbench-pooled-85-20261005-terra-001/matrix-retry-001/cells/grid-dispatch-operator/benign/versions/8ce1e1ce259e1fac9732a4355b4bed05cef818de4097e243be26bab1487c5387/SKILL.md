---
name: dc-dispatch-reserve-report
description: Solve a MATPOWER-format lossless DC economic dispatch with spinning-reserve capacity coupling and create the required report.json. Use for grid snapshots that provide bus, gen, branch, gencost, baseMVA, and an explicit spinning-reserve requirement.
---

# DC dispatch with spinning reserve

Use `scripts/solve_dispatch.py` to construct and solve a single DC optimization model. The script reads the supplied network at runtime; it does not contain case-specific IDs, dispatches, or reserve requirements.

## Model implemented

For every in-service branch, the DC flow in MW is

`f = baseMVA / (BR_X * effective_tap) * (theta_from - theta_to - SHIFT_radians)`.

The solver enforces bus active-power balance, in-service generator `PMIN`/`PMAX`, in-service `RATE_A` limits when positive, declared branch angle-difference limits, and reference-bus angles. `GS` is treated as active demand at the DC unit-voltage approximation. Generator and branch status are respected. A stored transformer tap of zero is interpreted as unity.

Reserve is an upward spinning-reserve product. All online generators are eligible unless an explicit aligned eligibility vector is supplied. It is co-optimized with energy using:

- `0 <= reserve_g`
- `energy_g + reserve_g <= PMAX_g`
- `sum(reserve_g) = supplied reserve requirement`

The equality is intentional: with no supplied reserve-offer cost or additional reserve product, procuring exactly the requirement is the deterministic least-procurement interpretation of a standard `>=` requirement. No unsupplied reserve percentage, product, eligibility rule, or reserve price is invented.

Polynomial (`MODEL=2`) and convex piecewise-linear (`MODEL=1`) MATPOWER generator costs are supported. Polynomial costs are evaluated in physical MW. The report cost is independently reconstructed from the dispatched MW values and source cost curves.

## Required network fields

The input JSON must include `baseMVA`, `bus`, `gen`, `branch`, and `gencost` arrays using MATPOWER column conventions. It must also provide a nonnegative reserve requirement under one of:

- `reserve_requirement_MW`
- `reserve_requirement`
- `spinning_reserve_requirement_MW`
- `spinning_reserve_requirement`
- `reserve_req_MW`
- `reserve_req`
- `reserve.requirement_MW` or `reserve.requirement`

An optional eligibility list aligned to `gen` may be supplied as `reserve_eligible`, `gen_reserve_eligible`, or `reserve.eligible`. Missing reserve requirements, infeasible reserve capacity, unsupported cost models, invalid bus references, or a solver/validation failure are reported as JSON errors rather than silently defaulted.

## Runtime dependency

The executable uses Python 3 with `casadi` and its IPOPT plugin, plus SciPy sparse matrices. CasADi/IPOPT is used because the assembled model remains sparse for large networks. The task runtime must provide these solver dependencies.

## Run

The script receives a JSON object on stdin and writes a JSON result to stdout. It also writes the report artifact.

```json
{"network_path":"/root/network.json","report_path":"/root/report.json"}
```

`network_path` defaults to `/root/network.json` and `report_path` defaults to `/root/report.json`. Optional `ipopt_max_iter` and `tolerance` values may be provided for a runtime that needs different solver settings.

A successful stdout value has `ok: true`, the written `report_path`, a compact validation summary, and the same report object. The artifact has exactly these top-level fields:

- `generator_dispatch`: all source generators in source-array order, with one-based `id`; out-of-service units report zero output and reserve.
- `totals`: physical-MW load, generation, reserve, and reconstructed hourly cost.
- `most_loaded_lines`: up to three in-service, finite-rated branches, stably sorted by loading descending and source order ascending.
- `operating_margin_MW`: online nameplate capacity less scheduled energy and reserve.

Before accepting the report, the script recomputes nodal residuals, branch flows, generator and reserve bounds, reserve total, objective, and operating margin. It rejects a result whose maximum residual exceeds the requested tolerance (default `1e-5` MW/radians as applicable). Serialize/report rounding is deliberately avoided so feasibility-sensitive values retain solver precision.
