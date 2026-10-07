---
name: dcopf-spinning-reserve-report
description: Solve a MATPOWER-format lossless DC economic dispatch with spinning-reserve co-optimization and create the required report.json. Use when a task supplies bus, gen, branch, gencost, and an explicit reserve requirement.
---

# DC OPF with spinning reserve

Use `scripts/solve_dcopf_reserve.py` to parse the supplied network at runtime, solve the optimization, independently validate it, and write the report artifact.

## Prerequisites and supported input

The executor needs Python 3 with `numpy` and `scipy` (including HiGHS through `scipy.optimize.linprog`; convex quadratic cases additionally use SciPy's `trust-constr`). The network JSON must be a MATPOWER-style object, either at the root or under `mpc`, with `baseMVA`, `bus`, `gen`, `branch`, and `gencost` arrays.

The solver recognizes an explicit reserve requirement in MW under one of:

- `reserve_requirement_MW`, `reserve_requirement`
- `spinning_reserve_requirement_MW`, `spinning_reserve_requirement`
- `reserve.requirement_MW`, `reserve.requirement`, or `reserve.required_MW`

It deliberately does not invent a percentage reserve rule if this field is absent. Optional reserve offer costs can be an `ngen`-length array (or scalar) at `reserve_cost_per_MW`, `reserve_costs`, `reserve_cost`, or the equivalent key inside `reserve`. Optional `reserve_eligible` may be an `ngen`-length boolean/numeric array; absent eligibility means every in-service generator is eligible.

Polynomial MATPOWER costs through quadratic degree and convex MATPOWER piecewise-linear (`model=1`) costs are supported. Nonconvex or higher-order costs are rejected rather than silently approximated. The active-power `gencost` rows are the first `ngen` rows.

## Execute

Provide paths explicitly through JSON stdin. For the normal task sandbox:

```sh
python scripts/solve_dcopf_reserve.py <<'JSON'
{"network_path":"/root/network.json","report_path":"/root/report.json"}
JSON
```

The script emits a JSON execution summary to stdout and atomically creates `report_path` only after optimization and validation succeed. Its stdin schema is:

```json
{"network_path":"path to input JSON", "report_path":"path to output JSON", "tolerance": 0.000001}
```

`network_path` and `report_path` are required. `tolerance` is optional and must be positive.

## Method

The implementation maps external bus labels to contiguous internal indices, excludes out-of-service generators and branches, interprets zero taps as one, and uses the DC flow
`baseMVA * (theta_from - theta_to - shift) / (x * tap)`.
It fixes every declared reference bus and refuses an island without a reference. It includes bus PD and active Gs as fixed active withdrawal. Positive RATE_A limits and declared branch angle limits are enforced.

Decision variables are generator energy, generator reserve, angles, and any piecewise-linear cost epigraphs. It minimizes energy cost plus declared reserve offers subject to nodal balance, energy bounds, positive branch ratings, angle bounds, reserve requirement, and `Pg + reserve <= Pmax`. Reserve is scheduled exactly at the stated requirement: with nonnegative standard offers this is equivalent to the usual `>=` requirement and avoids arbitrary excess reserve when offers are absent.

Before writing the report, the script recomputes nodal residuals, generator bounds, reserve coupling and total, flows and ratings, total generation, operating margin, and cost. Validation failure, malformed data, unsupported models, an infeasible model, or an unsuccessful solver produces a JSON error on stdout and a nonzero exit rather than an unverified report.

The generated report follows the requested fields. Generator IDs are one-indexed gen-array positions and bus values are MATPOWER bus IDs. Line loading is `abs(DC MW flow)/RATE_A*100`; only in-service positive-rated branches qualify. Lines are sorted by unrounded loading descending, then from bus, to bus, and original branch position, and at most three are emitted. `load_MW` is the modeled fixed active withdrawal (PD plus any active shunt Gs), ensuring it reconciles with lossless DC generation.
