# DC-OPF with reserve co-optimization: model and conventions

## MATPOWER columns (0-indexed JSON arrays)

- **bus**: 0 BUS_I, 1 BUS_TYPE (1=PQ,2=PV,3=slack), 2 PD (MW), 3 QD, 4 GS, 5 BS,
  7 VM, 8 VA (deg).
- **gen**: 0 GEN_BUS, 1 PG, 7 GEN_STATUS, 8 PMAX (MW), 9 PMIN (MW).
- **branch**: 0 F_BUS, 1 T_BUS, 3 BR_X (pu), 5 RATE_A (MVA thermal limit),
  8 TAP (0 means 1.0), 9 SHIFT (deg), 10 BR_STATUS, 11 ANGMIN, 12 ANGMAX.
- **gencost**: 0 MODEL (2=polynomial), 3 NCOST, 4.. coefficients highest-order first
  (for NCOST=3: c2,c1,c0). Cost uses Pg in **MW**, cost in **$/hr**.

Bus numbers are labels; build an explicit id->index map. Generators/branches reference
buses by MATPOWER number, not array position. Treat TAP=0 as 1.0; convert SHIFT and angle
limits from degrees to radians.

## Decision variables

- `theta[b]` bus voltage angles (rad); `theta[ref]=0` at the slack bus.
- `Pg[g]` generator energy (MW), `Pmin <= Pg <= Pmax` (in-service gens only).
- `R[g]` spinning reserve (MW), `R >= 0`, optional `R <= qty`.

## Constraints

1. **DC power balance** at every bus (equality):
   `sum_{g at b} Pg - Pd[b] == net_outflow[b]`, where branch flow
   `f_l = (baseMVA/(x_l*tap_l))*(theta_from - theta_to - shift_l)` in MW and
   `net_outflow = A^T f` with incidence `A[l,from]=+1, A[l,to]=-1`.
   The dual of this equality is the **LMP** ($/MWh).
2. **Thermal limits**: `-rateA_l <= f_l <= rateA_l` for branches with `rateA_l > 0`
   (rateA in MVA; in the lossless DC model MVA == MW magnitude).
3. **Generator limits**: `Pmin <= Pg <= Pmax`.
4. **Spinning reserve, standard capacity coupling**: `Pg + R <= Pmax`.
5. **Zone reserve requirement**: `sum_{g in zone} R >= req`. Its dual is the
   **reserve MCP**.

## Objective

Minimize `sum_g (c2 Pg^2 + c1 Pg + c0) + sum_g rcost*R`. This is a convex QP (LP when all
c2=0). Use a QP solver that returns duals (CLARABEL preferred; ECOS/OSQP/SCS fallback).

## Reserve data (MATPOWER `reserves` extension, if present)

- `req`: scalar or per-zone requirement (MW).
- `cost`: per-generator reserve price ($/MW); length may equal n_gen or the number of
  reserve-eligible gens (mapped by order).
- `qty`: per-generator max reserve (MW); default unbounded (coupling still limits it).
- `zones`: zone x gen 0/1 matrix; default a single zone over all gens.

If the case has **no** reserve block and no `reserve_requirement` override, reserve is
inactive: `R=0` and reserve MCP = 0.0. Inspect `network.json` for a reserves object before
accepting a zero MCP; pass `reserve_requirement` only if the instruction/data supplies one.

## Counterfactual (clone-and-change)

Clone the parsed model, change **only** the target branch's `rateA` (multiply by the
stated factor), and solve both cases with identical conventions. The target branch is
identified by its two MATPOWER bus numbers, orientation-independent.

## Dual sign and validation

- LMP: dual of `gen - outflow == demand`; normalize so the median LMP is non-negative
  (one consistent flip per connected system). Verify by perturbing a bus demand by +1 MW
  and re-solving: the cost change approximates that bus's LMP.
- Reserve MCP: reported as the non-negative dual of the binding zone requirement.
- Always recompute nodal residuals (should be ~0 MW), generator capability, flows, and the
  objective from returned variables. A solver "optimal" status alone is not correctness.
- Keep solver precision until serialization; round only when writing report.json.

## Output contract notes

- `binding_lines`: in-service branches with `rateA>0` and loading `|f|/rateA*100 >= 99`.
- `buses_with_largest_lmp_drop`: the 3 buses with the most negative `cf_lmp - base_lmp`,
  computed on unrounded LMPs, tie-broken by ascending bus id (stable deterministic order).
  The subset size (3) is a contract parameter (`top_k`), not an electrical property.
- `congestion_relieved`: `true` iff the adjusted line is **not** binding in the
  counterfactual.
- `cost_reduction_dollars_per_hour = base_total_cost - cf_total_cost`.
