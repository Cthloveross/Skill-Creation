# ACOPF formula sheet (condensed from frozen background)

## Per-unit conversions (divide by baseMVA)
- Bus loads Pd, Qd (MW, MVAr) -> pu.
- Shunts Gs, Bs (MW, MVAr at 1 pu V) -> pu; **Bs enters reactive balance with +**.
- Generator Pg/Qg and bounds (MW/MVAr) -> pu.
- Branch rateA (MVA) -> pu for the squared flow limit.
- Branch r, x, b are already pu. Cost uses Pg in MW (pu*baseMVA).

## Branch series values
`g = r/(r^2+x^2)`, `b = -x/(r^2+x^2)`, `bc = BR_B`.
`t = TAP` with `TAP==0 -> 1.0`. `shift = radians(SHIFT)`.

## Pi-model flows (pu)
`delta  = Va_i - Va_j - shift`
`delta' = Va_j - Va_i + shift`
- `P_ij = g*Vm_i^2/t^2 - (Vm_i*Vm_j/t)*(g*cos d + b*sin d)`
- `Q_ij = -(b+bc/2)*Vm_i^2/t^2 - (Vm_i*Vm_j/t)*(g*sin d - b*cos d)`
- `P_ji = g*Vm_j^2 - (Vm_i*Vm_j/t)*(g*cos d' + b*sin d')`
- `Q_ji = -(b+bc/2)*Vm_j^2 - (Vm_i*Vm_j/t)*(g*sin d' - b*cos d')`
The to-side self term has **no 1/t^2** (transformer asymmetry).
`S_ij = sqrt(P_ij^2+Q_ij^2)*baseMVA`, `S_ji` likewise.
`loading_pct = max(S_ij,S_ji)/rateA*100` (rateA>0, BR_STATUS=1 only).

## Nodal balance (pu), residual = 0 at every bus
- Active:   `sum(Pg) - Pd - Gs*Vm^2 - sum(flows_out_P) = 0`
- Reactive: `sum(Qg) - Qd + Bs*Vm^2 - sum(flows_out_Q) = 0`

## Variables / bounds
- Vm in [Vmin,Vmax]; Va in [-pi,pi] with slack (BUS_TYPE 3) angle fixed to 0.
- Pg in [Pmin,Pmax], Qg in [Qmin,Qmax] (pu). Out-of-service gens fixed to 0.

## Constraints
- 2*n_bus balance equalities.
- Branch limits `P_ij^2+Q_ij^2 <= (rateA/baseMVA)^2` and same for ji (rateA>0).
- Angle diff `angmin <= Va_from - Va_to <= angmax` (deg->rad);
  `angmin==angmax==0` means unconstrained.

## Objective
`sum_k polycost_k(Pg_k_MW)`, coefficients highest-order first
(gencost columns: model, startup, shutdown, ncost, c2, c1, c0).

## MATPOWER column indices (0-based)
- bus:    0 BUS_I, 1 BUS_TYPE, 2 PD, 3 QD, 4 GS, 5 BS, 7 VM, 8 VA, 11 VMAX, 12 VMIN.
- gen:    0 GEN_BUS, 1 PG, 2 QG, 3 QMAX, 4 QMIN, 7 GEN_STATUS, 8 PMAX, 9 PMIN.
- branch: 0 F_BUS, 1 T_BUS, 2 BR_R, 3 BR_X, 4 BR_B, 5 RATE_A, 8 TAP, 9 SHIFT,
          10 BR_STATUS, 11 ANGMIN, 12 ANGMAX.

## Self-consistency / reporting
- Bus numbers are labels -> build id->index map.
- Generators reported 1..n_gen (gen-array order); `bus` is the MATPOWER number.
- Totals derived from reported (rounded) generator values; cost recomputed from
  reported pg_MW. Losses = total_gen_MW - total_load_MW (positive, ~1-5%).
- most_loaded_branches: full eligible population, stable descending sort by
  loading_pct with branch index as secondary key, then take exactly top_n.
- Round only at serialization; keep solver precision for checks.
