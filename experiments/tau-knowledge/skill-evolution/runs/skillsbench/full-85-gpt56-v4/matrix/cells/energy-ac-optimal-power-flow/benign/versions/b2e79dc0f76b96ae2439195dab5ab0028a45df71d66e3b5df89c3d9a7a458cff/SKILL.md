---
name: acopf-matpower-report
description: Solve a MATPOWER-style AC optimal power flow and write the required report.json with independently recomputed AC feasibility metrics and the exactly requested ranked branch subset. Use for peak-hour AC-feasibility and least-cost dispatch tasks that supply a standard network.json and a model consistent with pi-model ACOPF.
---

# ACOPF MATPOWER report

## Applicability and prerequisites

Use this Skill when the supplied case contains `baseMVA`, `bus`, `gen`, `branch`, and `gencost` arrays in the standard MATPOWER column convention. It supports in-service generators and branches, polynomial (`model == 2`) generator costs, shunts, non-contiguous bus identifiers, transformer taps and shifts, voltage bounds, generator P/Q bounds, active branch MVA limits, and active branch angle-difference bounds.

First read the supplied mathematical model. Confirm that it uses the same AC pi-model sign convention and that polynomial costs are the intended cost model. This Skill deliberately fails rather than silently solving a different formulation (for example, piecewise-linear costs, discrete controls, contingency constraints, or reserve products that are not encoded in the standard arrays).

The executable requires Python 3 and CasADi with its IPOPT backend. If `import casadi` fails, install a compatible wheel in the execution environment (for example, `python -m pip install casadi`) before running it. Do not alter the input case.

## Run

From the directory containing the task files, invoke the packaged program with a JSON request on standard input:

```sh
python /app/environment/skills/current/scripts/acopf_report.py <<'JSON'
{"network_path":"/root/network.json","output_path":"/root/report.json"}
JSON
```

Input schema:

```json
{"network_path": "path to network JSON", "output_path": "path to create report.json"}
```

The program emits a small JSON completion record on stdout and writes the complete report to `output_path`. Paths are supplied at runtime; no case-specific identifier, dispatch, ranking, or expected result is embedded in this Skill.

## Method

The script maps external bus labels to dense internal indices, converts all power quantities to per-unit for constraints, and uses physical MW for polynomial costs. It creates one nonlinear program containing voltage magnitudes and angles plus each generator's P and Q output. It applies:

- active and reactive nodal balance with the stated MATPOWER shunt signs;
- one zero reference angle at the sole type-3 bus;
- voltage and generator bounds;
- both-end squared apparent-power limits for active branches with positive `rateA`; and
- active branch angle bounds in degrees converted to radians.

A stored zero transformer tap is interpreted as one. The from-end and to-end pi-model equations are evaluated separately, retaining transformer asymmetry. Offline generators are fixed at zero; offline branches do not enter balance or flow constraints.

After IPOPT reports success, the script independently recomputes every branch flow, bus mismatch, bound violation, branch overload, totals, cost, and ranking numerically from the returned state. It refuses to serialize a report if residuals or constraint violations exceed conservative numerical tolerances. The report retains numeric precision rather than display-rounding values that are subsequently used for validation. `most_loaded_branches` is deterministically sorted by descending unrounded loading followed by bus labels and branch row, and must have exactly ten eligible branches.

## Review before delivery

Check that `report.json` exists and is valid JSON, has all five top-level fields, and has exactly ten branch entries. Confirm the solver status is `optimal`, totals are sourced from the reported generator and bus arrays, and feasibility metrics are small. If the script raises an error, address the stated unsupported data or solver issue; do not fabricate a report or label an unsuccessful solve as optimal.
