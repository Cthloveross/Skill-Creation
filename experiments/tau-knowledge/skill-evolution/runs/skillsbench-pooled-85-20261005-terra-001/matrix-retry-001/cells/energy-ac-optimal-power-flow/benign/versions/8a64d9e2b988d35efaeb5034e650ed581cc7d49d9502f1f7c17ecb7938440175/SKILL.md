---
name: matpower-acopf-report
description: Solve a MATPOWER-style least-cost AC optimal power flow and create a validated report.json containing dispatch, voltage profile, top-ten thermal loadings, and AC feasibility metrics. Use for ISO planning cases supplied as network.json plus a compatible AC model specification.
---

# MATPOWER ACOPF report

This Skill solves the complete nonlinear ACOPF in the supplied network case. It honors non-contiguous MATPOWER bus identifiers, equipment status, taps (including MATPOWER tap=0 meaning 1), phase shifts, voltage/generator limits, reference angle, angle-difference limits, and two-sided positive `rateA` MVA limits. Generator cost polynomials are evaluated using MW, while all network equations are per-unit.

## Inputs and assumptions

At runtime, first read the supplied mathematical specification (for example `/root/math-model.md`) and confirm it uses the standard MATPOWER arrays documented by the task. The solver accepts a JSON object with `baseMVA`, `bus`, `gen`, `branch`, and `gencost` arrays. It also accepts these arrays inside a top-level `case`, `mpc`, or `network` object.

The implementation supports polynomial (`MODEL=2`) generator costs. It rejects unsupported cost models, malformed rows, zero-impedance in-service branches, unknown bus references, missing/ambiguous reference buses, and cases with fewer than ten eligible branches. Out-of-service generators are fixed at zero output; out-of-service branches do not contribute flows or constraints.

CasADi with IPOPT is the preferred solver because it uses symbolic derivatives for the nonconvex NLP. A SciPy SLSQP fallback is included for small cases when CasADi/IPOPT is unavailable. A fallback result is not presented as optimal unless its solver reports successful convergence and independent checks pass.

## Solve and write the required artifact

Run the packaged script from a directory containing the package:

```bash
python3 scripts/solve_acopf.py <<'JSON'
{"case_path":"/root/network.json","report_path":"/root/report.json","solver":"auto","multistart":true}
JSON
```

The script reads one JSON request from stdin and emits one JSON result to stdout. Request fields:

- `case_path` (required): readable MATPOWER-style network JSON.
- `report_path` (required): destination for the required report artifact.
- `solver` (optional): `auto` (default), `casadi`, or `scipy`.
- `multistart` (optional): use both data and flat starts with CasADi (default `true`).
- `max_iter` and `tol` (optional): NLP iteration limit and solver tolerance.

On success stdout is `{"ok":true,"report_path":"...","solver":"...","validation":{...}}`, and `report_path` contains exactly the required top-level report structure. Numeric values are serialized at solver precision rather than display-rounded, preserving feasibility and cost consistency. The report's `solver_status` is `"optimal"` only after convergence and independent feasibility checks.

The ranking is calculated over every in-service branch with `rateA > 0`, sorted by unrounded loading percentage descending and original branch-row index ascending, then exactly ten entries are selected. Directional MVA values are independently calculated from the pi model.

## Validate the produced artifact

After solving, independently validate the actual serialized report:

```bash
python3 scripts/validate_report.py <<'JSON'
{"case_path":"/root/network.json","report_path":"/root/report.json","tolerance_MW":0.01,"tolerance_MVAr":0.01}
JSON
```

The validator emits JSON with recomputed power mismatches, voltage and thermal violations, generator-bound/angle checks, report cardinality/order checks, and summary consistency differences. Do not claim completion if `ok` is false. If solving fails, inspect the structured error, the input model, and the case feasibility rather than fabricating a report.

## Method notes

The solver uses branch currents/powers with the transformer on the from side: the from-side self term is scaled by `1/t^2`, while the to-side self term is not. It enforces active and reactive balances at every bus, with MATPOWER shunt signs (`-Gs*Vm^2` in active injection and `+Bs*Vm^2` in reactive injection), and fixes the sole slack angle to zero. Total losses are reported as total generation MW minus total load MW, as requested.
