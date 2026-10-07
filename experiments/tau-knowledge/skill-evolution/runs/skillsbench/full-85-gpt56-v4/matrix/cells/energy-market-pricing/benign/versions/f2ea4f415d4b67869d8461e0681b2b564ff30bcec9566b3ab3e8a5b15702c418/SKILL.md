---
name: dcopf-reserve-counterfactual-market-report
description: Solve a MATPOWER-style lossless DC energy-and-spinning-reserve co-optimization twice, increase the rating of a named line, validate both solutions, and write the required market-impact report.json. Use for transmission-counterfactual market-clearing tasks with bus LMPs, a system reserve MCP, and binding-line reporting.
---

# DC-OPF reserve counterfactual market report

Run `scripts/run_market.py` against the supplied MATPOWER JSON.  The script uses a sparse LP formulation with a convex piecewise-linear representation of declared polynomial energy costs. It retains the original polynomial cost for reported total cost, calculates LMPs and the reserve MCP from the solved LP duals, and solves the base and counterfactual models independently.

## Runtime interface

The script reads one JSON object from standard input and writes a small JSON status object to standard output.

```json
{
  "network_path": "/root/network.json",
  "output_path": "/root/report.json",
  "target_from_bus": 64,
  "target_to_bus": 1501,
  "rating_multiplier": 1.2,
  "segments": 48
}
```

All fields are optional except that a network must be available. Defaults are `/root/network.json`, `report.json`, buses `64` and `1501`, multiplier `1.2`, and 48 cost segments. `segments` may be raised when very accurate quadratic-cost price approximation is required, subject to available memory.

Example:

```sh
printf '%s\n' '{"network_path":"/root/network.json","output_path":"report.json"}' | python3 scripts/run_market.py
```

The successful status output is `{"ok": true, "report_path": "..."}`. The requested deliverable is the file named by `output_path`, not the status object.

## Model and data handling

* The parser uses explicit MATPOWER bus-ID mappings; it never treats external bus labels as array positions.
* Only in-service generators and branches are modeled. Generator active bounds, branch RATE_A limits, tap ratios (zero means one), phase shifts, branch angle bounds, and the declared `gencost` model are respected.
* DC flows are `baseMVA/(x*tap) * (theta_from-theta_to-shift)`. RATE_A equal to zero has no thermal constraint.
* Each online generator has energy plus upward reserve bounded by PMAX. The reserve requirement and optional reserve offers/eligibility are read only when actually supplied in the input data or explicit runtime configuration. In the absence of a supplied system requirement, the requirement is zero rather than an invented percentage of load.
* Recognized reserve requirement keys include `reserve_requirement`, `spinning_reserve_requirement`, and their camel-case variants. Per-generator reserve offer arrays may be supplied as `reserve_offers`, `reserve_offer`, `reserve_costs`, or `reserve_cost`; explicit configuration takes precedence. An explicit `reserve_eligible` Boolean array or bus/generator-ID map can restrict eligibility.
* MATPOWER polynomial (`MODEL=2`) and piecewise-linear (`MODEL=1`) active-energy cost rows are handled. Costs must be convex over the declared generator range. Unsupported or nonconvex cost data produces a clear failure instead of silently changing the economics.

## Validation and interpretation

Before serializing a result, the script recomputes nodal balance, flows, flow limits, energy/reserve capability coupling, reserve total, generator bounds, and objective reconstruction. A failed validation aborts report creation. LMPs are the objective derivatives with respect to MW demand from the balance-row duals. The reserve MCP is the independently signed derivative with respect to the system reserve requirement. Binding lines have `abs(flow) / limit >= 0.99`.

`cost_reduction_dollars_per_hour` is base cost minus counterfactual cost. The largest LMP drops are the three smallest `counterfactual_lmp - base_lmp` values, with bus ID as a deterministic tie-breaker. `congestion_relieved` is true exactly when no modified target branch is binding in the counterfactual.

If no active branch connects the requested buses, the script fails explicitly; do not fabricate a counterfactual. If multiple parallel active branches connect the pair, each is changed and the relief flag applies to all of them.
