---
name: dcopf-reserve-market-counterfactual
description: >
  Clear a DC optimal power flow market with spinning-reserve co-optimization on a
  MATPOWER-format network.json, run a base case and a transmission counterfactual that
  scales one named branch's thermal rating, and emit the required report.json with per-bus
  LMPs (balance duals), the reserve clearing price (reserve-requirement dual), binding
  lines, cost reduction, the buses with the largest LMP drop, and a congestion-relieved
  flag. Use when a task gives a MATPOWER case and asks for a DC-OPF "what if we relax a
  line" price/congestion analysis.
---

# DC-OPF reserve market counterfactual

## What this Skill does

Given a MATPOWER-style `network.json` and an instruction to compare a base dispatch
against a counterfactual in which one transmission line's thermal rating is increased by a
stated factor, this Skill:

1. Parses the case (baseMVA, bus, gen, branch, gencost, optional reserves) using the
   MATPOWER column conventions, building an explicit **external-bus-id -> internal-index**
   map (bus numbers are labels, not row positions).
2. Formulates a lossless **DC-OPF with reserve co-optimization**:
   - power balance at every bus (equality; its dual is the **LMP** in $/MWh),
   - DC branch flows `f = (baseMVA/(x*tap))*(theta_from - theta_to - shift)` with thermal
     limits `-rateA <= f <= rateA` (MW) for branches with `rateA > 0`,
   - generator energy bounds `Pmin <= Pg <= Pmax`,
   - spinning reserve `R >= 0`, optional `R <= qty`, **standard capacity coupling**
     `Pg + R <= Pmax`, and a **zone reserve requirement** `sum R >= req` (its dual is the
     **reserve MCP**),
   - objective = quadratic energy cost (coefficients applied to Pg in MW) + reserve cost.
3. Solves the **base** rating vector and a **counterfactual** vector that multiplies only
   the target line's `rateA` by the factor, using identical conventions (clone-and-change).
4. Assembles `report.json` exactly in the required schema and rounds **only at
   serialization**.

## Running it

The runtime has `network.json` at `/root/network.json`. The entrypoint reads a small JSON
config from stdin and writes `report.json`.

```bash
# ensure dependencies (internet is allowed in this task)
python3 -c "import cvxpy, scipy, numpy" 2>/dev/null || pip install cvxpy scipy numpy

# run with the values stated in THIS instruction (confirm them in the opening text)
echo '{"network_path":"/root/network.json","target_from":64,"target_to":1501,"cf_factor":1.2,"output_path":"/root/report.json"}' \
  | python3 scripts/market_report.py
```

If you run `echo '{}' | python3 scripts/market_report.py`, the defaults match the current
instruction (`/root/network.json`, line 64->1501, factor 1.2, output `/root/report.json`).
**Always re-read the instruction** and pass `target_from`, `target_to`, `cf_factor`
explicitly if any differ; these are task parameters, not electrical constants.

### Config keys (all optional)

- `network_path` (default `/root/network.json`)
- `target_from`, `target_to`: MATPOWER bus numbers of the line to relax (default 64, 1501).
  Matching is orientation-independent, so a branch stored as 1501->64 is also found.
- `cf_factor`: multiplier on the target line's `rateA` in the counterfactual (default 1.2).
- `output_path` (default `/root/report.json`)
- `binding_pct`: loading percent that counts as binding (default 99.0, per the contract).
- `top_k`: size of `buses_with_largest_lmp_drop` (default 3, per the contract).
- `reserve_requirement`: numeric override of the zone requirement if the data omits it.
- `round_price`, `round_cost`, `round_flow`: serialization rounding (defaults 4, 2, 4).

## Output schema (produced exactly)

`base_case` and `counterfactual` each contain `total_cost_dollars_per_hour`,
`lmp_by_bus` (one `{bus, lmp_dollars_per_MWh}` per bus in case order),
`reserve_mcp_dollars_per_MWh`, and `binding_lines` (`{from,to,flow_MW,limit_MW}` for every
in-service branch with `rateA>0` whose loading `|f|/rateA*100 >= binding_pct`).
`impact_analysis` contains `cost_reduction_dollars_per_hour = base_cost - cf_cost`,
`buses_with_largest_lmp_drop` (the `top_k` buses with the most negative
`delta = cf_lmp - base_lmp`, tie-broken by ascending bus id), and `congestion_relieved`
(`true` iff the adjusted line is **not** binding in the counterfactual).

## How to interpret and verify the results

- **LMP sign**: the dual of `gen - outflow == demand` is the marginal cost of load; the
  script normalizes so the median LMP is non-negative (one consistent flip for the whole
  connected system). Spot-check that uncongested LMPs equal the marginal unit's
  `c1 + 2*c2*Pg`; if the data uses an unusual convention, perturb a bus demand by +1 MW,
  re-solve, and confirm `d(cost) ~= LMP`.
- **Reserve MCP**: reported as the (non-negative) dual of the binding zone requirement. If
  the case has no reserve block and no `reserve_requirement` override, reserve is inactive
  and the MCP is `0.0`; check `network.json` for a `reserves` object before accepting that.
- The script prints to **stderr** the max nodal power-balance residual (MW) and an
  independent cost recomputation for each case. Residuals should be ~0 and the recomputed
  cost should match `total_cost_dollars_per_hour`. Treat a non-optimal solver status or a
  large residual as a failure to investigate, not success.
- `congestion_relieved` depends only on the adjusted line's counterfactual loading.

See `references/formulation.md` for the full model, conventions, and failure handling.

## Validate the produced report

```bash
python3 - <<'PY'
import json
r=json.load(open('/root/report.json'))
for c in ('base_case','counterfactual'):
    b=r[c]
    assert isinstance(b['total_cost_dollars_per_hour'],(int,float))
    assert isinstance(b['lmp_by_bus'],list) and b['lmp_by_bus']
    assert all({'bus','lmp_dollars_per_MWh'}<=set(x) for x in b['lmp_by_bus'])
    assert isinstance(b['reserve_mcp_dollars_per_MWh'],(int,float))
    for bl in b['binding_lines']:
        assert {'from','to','flow_MW','limit_MW'}<=set(bl)
ia=r['impact_analysis']
assert abs(ia['cost_reduction_dollars_per_hour']-(r['base_case']['total_cost_dollars_per_hour']-r['counterfactual']['total_cost_dollars_per_hour']))<1e-2
d=ia['buses_with_largest_lmp_drop']
assert all(d[i]['delta']<=d[i+1]['delta']+1e-9 for i in range(len(d)-1))
assert isinstance(ia['congestion_relieved'],bool)
print('report.json structurally valid; cases:',len(r['base_case']['lmp_by_bus']),'buses')
PY
```
