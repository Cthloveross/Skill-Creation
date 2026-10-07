---
name: acopf-matpower-report
description: Solve a single-period AC Optimal Power Flow (ACOPF) for a MATPOWER-style network (network.json + math-model.md) and emit the required report.json. Use when the task asks for a least-cost, AC-feasible operating point, a voltage profile, generator dispatch, the most-loaded branches, and feasibility metrics for a MATPOWER-format grid. Builds the nonconvex NLP with CasADi + IPOPT, verifies the solution independently against the pi-model branch equations, and writes a self-consistent report.
---

# ACOPF -> report.json

## When to use
The task supplies a MATPOWER-format network (`/root/network.json`) and a model
description (`/root/math-model.md`), and asks for a least-cost AC-feasible
operating point written to `report.json` with a fixed schema (summary,
generators, buses, most_loaded_branches, feasibility_check). This Skill parses
the case, formulates and solves the ACOPF, verifies it, and serializes the
report.

## Method (grounded in the frozen background)
- Per-unit system: divide bus loads (Pd,Qd), shunts (Gs,Bs), generator
  outputs/bounds and branch rateA by `baseMVA`. Branch r,x,b are already pu.
  The **cost function uses Pg in MW** (pu*baseMVA), cost in $/hr.
- Pi-model branch flows (forward i->j, reverse j->i), with the tap asymmetry:
  `g=r/(r^2+x^2)`, `b=-x/(r^2+x^2)`, `t=TAP (0 -> 1.0)`, shift in radians,
  `delta = Va_i-Va_j-shift`, `delta' = Va_j-Va_i+shift`.
  - `P_ij = g*Vm_i^2/t^2 - (Vm_i*Vm_j/t)*(g*cos(delta)+b*sin(delta))`
  - `Q_ij = -(b+bc/2)*Vm_i^2/t^2 - (Vm_i*Vm_j/t)*(g*sin(delta)-b*cos(delta))`
  - `P_ji = g*Vm_j^2 - (Vm_i*Vm_j/t)*(g*cos(delta')+b*sin(delta'))`
  - `Q_ji = -(b+bc/2)*Vm_j^2 - (Vm_i*Vm_j/t)*(g*sin(delta')-b*cos(delta'))`
  The j-side self term has **no** 1/t^2 scaling (critical).
- Apparent power (MVA): `S_ij=sqrt(P_ij^2+Q_ij^2)*baseMVA`, likewise S_ji.
  `loading_pct = max(S_ij,S_ji)/rateA*100` (rateA in MVA). Only branches with
  `rateA>0` and `BR_STATUS=1` are eligible.
- Nodal balance per bus (pu): active residual
  `sum(Pg) - Pd - Gs*Vm^2 - sum(flows out) = 0`; reactive residual
  `sum(Qg) - Qd + Bs*Vm^2 - sum(flows out) = 0` (Bs enters with + sign).
- Variables: Vm in [Vmin,Vmax], Va in [-pi,pi] with slack (BUS_TYPE 3) angle
  fixed to 0, Pg in [Pmin,Pmax], Qg in [Qmin,Qmax] (all pu for Pg/Qg).
  Out-of-service generators are fixed to 0. Only in-service branches
  (BR_STATUS=1) and generators (GEN_STATUS=1) participate.
- Constraints: 2*n_bus balance equalities; branch limits `S_ij^2<=rateA^2` and
  `S_ji^2<=rateA^2` (squared form, pu) for rateA>0; angle-difference bounds
  `angmin<=Va_from-Va_to<=angmax` (degrees->radians; angmin==angmax==0 means
  unconstrained).
- Solver: CasADi symbolic model + IPOPT (tol 1e-6, mu_strategy adaptive). Solve
  from a flat start (Vm=1, Va=0, gens at midpoint) and a data-based start (bus
  VM/VA, gen PG/QG clipped to bounds); keep the feasible solution with lowest
  cost.
- Bus-ID mapping: MATPOWER bus numbers are labels; build an external-id ->
  contiguous-index map. Generators are reported 1..n_gen (gen-array order) with
  the MATPOWER bus number in `bus`.

## Entry point
`scripts/solve_acopf.py` reads a JSON object on **stdin** and writes a JSON
summary to **stdout**; it also writes the full report file.

Input schema (all optional; sensible defaults shown):
```json
{"network_path": "/root/network.json",
 "output_path": "/root/report.json",
 "top_n": 10}
```
`top_n` is the most_loaded_branches cardinality required by the output contract
(the current task fixes it at 10). It is a parameter, not an electrical
property; read it from the instruction.

Stdout schema:
```json
{"status": "optimal",
 "output_path": "/root/report.json",
 "total_cost_per_hour": 123.4,
 "feasibility_check": {"max_p_mismatch_MW": 0.0, "max_q_mismatch_MVAr": 0.0,
                        "max_voltage_violation_pu": 0.0, "max_branch_overload_MVA": 0.0}}
```

### Run example
```bash
# ensure casadi is available (internet is allowed in this task)
python -c "import casadi" 2>/dev/null || pip install --quiet casadi

echo '{"network_path":"/root/network.json","output_path":"/root/report.json","top_n":10}' \
  | python /app/environment/skills/current/scripts/solve_acopf.py
```
The skill directory is given by the environment (`skill_directory`). If invoked
from elsewhere, adjust the path to `scripts/solve_acopf.py` accordingly.

## How the executor uses the result
1. Confirm `python -c "import casadi"` works; if not, `pip install casadi`.
2. Run the entry point as above against the supplied `/root/network.json`.
3. Inspect stdout: `status` should be `optimal` and every `feasibility_check`
   value should be near zero (background: nodal residuals well below 1 MW;
   losses 1-5% of load, never above ~10%).
4. Open `/root/report.json` and confirm the schema is complete: `summary`
   (with `solver_status`), `generators`, `buses`, exactly `top_n`
   `most_loaded_branches` ordered highest->lowest `loading_pct`, and
   `feasibility_check`.
5. Self-consistency checks (also performed by the script):
   - `summary.total_generation_MW` equals the sum of reported `generators[*].pg_MW`.
   - `summary.total_cost_per_hour` equals the cost recomputed from the reported
     `pg_MW` and the gencost coefficients.
   - `summary.total_losses_MW = total_generation_MW - total_load_MW` and is positive.

## Failure handling
- If IPOPT does not reach `Solve_Succeeded` from any start, the script reports
  the best returned point and sets `solver_status` to the IPOPT status string;
  the executor should treat large feasibility residuals as a failure to
  investigate (e.g., re-run, which retries both starts).
- If `casadi` cannot be imported and cannot be installed, the task cannot be
  solved with this method; report the blocker rather than fabricating a report.
- If `network.json` lacks `gencost`, costs default to 0 and the objective
  minimizes generation (documented, not fabricated).
- The script makes no assumption about contiguous bus numbering and treats
  TAP==0 as 1.0.

See `references/acopf_notes.md` for the condensed formula sheet and column
conventions used by the script.
