---
name: dcopf-reserve-congestion-counterfactual
description: Solve a MATPOWER-style lossless DC-OPF with spinning-reserve co-optimization, then compare a base case with a specified transmission-rating counterfactual. Use when a task requires system cost, bus LMPs, reserve MCP, binding lines, and congestion-impact reporting.
---

# DC-OPF reserve congestion counterfactual

This Skill reads a MATPOWER-style JSON case at runtime, solves a convex DC market-clearing model twice, and writes the required market report. It explicitly maps MATPOWER bus identifiers to contiguous internal indices and does not assume bus IDs are array positions.

The model uses active/in-service generators and branches only. For each in-service generator it optimizes energy `Pg` and upward spinning reserve `R` subject to:

- `Pmin <= Pg <= Pmax`
- `R >= 0`
- `Pg + R <= Pmax` (standard capacity coupling)
- `sum(R) >= reserve_requirement_MW`

It enforces lossless DC nodal balance, DC branch flows, positive `RATE_A` limits, reference-angle constraints, and finite MATPOWER angle-difference limits. A zero transformer tap is interpreted as one, and phase shifts and angle limits are converted from degrees to radians. Energy cost uses MATPOWER polynomial `gencost` entries (linear or convex quadratic); a separately supplied reserve offer vector is included when available.

The source case must supply a spinning-reserve requirement, either through a recognized JSON field or explicitly in the script request. The task statement alone does not define a numerical requirement, so the script deliberately refuses to invent one. A missing reserve offer is interpreted as a zero reserve offer, which still permits an opportunity-cost reserve MCP through the capacity coupling.

## Runtime dependencies

The executor needs Python with `numpy`, `scipy`, and `cvxpy`. The script selects OSQP when available and otherwise tries CLARABEL. These are used only to solve the market model; no banking or external actions occur.

## Input and execution

Save a JSON request and pass it on standard input:

```json
{
  "network_path": "/root/network.json",
  "output_path": "/root/report.json",
  "reserve_requirement_mw": 250.0,
  "binding_fraction": 0.99
}
```

Run:

```bash
python scripts/run_market_analysis.py < request.json
```

`network_path` defaults to `/root/network.json`, `output_path` defaults to `report.json`, and `binding_fraction` defaults to `0.99`. `reserve_requirement_mw` is optional only when the case itself contains a recognized spinning-reserve requirement. The script finds the unique in-service branch joining buses 64 and 1501 (in either orientation) and multiplies its `RATE_A` by 1.20 in a cloned counterfactual model.

Supported case reserve fields include `reserve_requirement_mw`, `reserve_requirement`, `spinning_reserve_requirement_mw`, `spinning_reserve_requirement`, and `reserve_req`, including these fields in a nested `reserve` or `market` object. Supported optional reserve-offer fields include `reserve_cost`, `reserve_costs`, `reserve_offer`, and `reserve_offers`. An offer may be a scalar or one value per generator. An eligibility vector may be supplied as `reserve_eligible` or `spinning_reserve_eligible`.

The script writes `report.json` in the requested contract and emits a JSON execution summary on stdout containing the report path and independent validation metrics. It fails clearly for absent/ambiguous target branches, missing reserve requirement, unsupported cost models, invalid bus references, non-convex polynomial costs, or an infeasible/failed market solve.

## Interpretation and validation

LMPs are the negative of the DC nodal-balance duals under the script's `generation - demand - net_outflow = 0` convention. The reserve MCP is the dual of `sum(R) >= requirement`. The report uses the unrounded solver values as its source of truth and rounds only JSON serialization.

The script independently recomputes flows, nodal residuals, energy/reserve capacity coupling, reserve total, generator bounds, line-limit excess, and objective value after each solve. `binding_lines` contains every active positive-rated branch at or above the requested loading fraction. The three LMP drops are selected by ascending `counterfactual_lmp - base_lmp`, with bus ID as a deterministic tie-breaker. `congestion_relieved` is true exactly when the changed branch is not binding in the counterfactual.
