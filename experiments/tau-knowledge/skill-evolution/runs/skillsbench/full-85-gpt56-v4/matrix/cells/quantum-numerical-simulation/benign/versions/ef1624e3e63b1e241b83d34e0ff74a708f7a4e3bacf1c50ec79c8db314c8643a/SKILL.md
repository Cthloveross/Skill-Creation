---
name: open-dicke-steady-state-wigner
version: 1.0.0
description: Compute steady states of the QuTiP PIQS open-Dicke model, reduce them to the cavity, and serialize validated cavity Wigner grids for multiple dissipative cases. Use for open-Dicke tasks requiring CSV Wigner-function artifacts.
---

# Open-Dicke steady-state Wigner grids

This Skill uses the PIQS open-Dicke tutorial convention:

- The photon cutoff is the Hilbert-space dimension passed directly to `destroy`.
- The matter interaction is exactly `g * tensor(a + a.dag(), jx)`, with PIQS `Jx`; it does **not** apply a second factor of two.
- The spin and cavity Liouvillians are built separately, then joined with `super_tensor`.
- The cavity is subsystem zero, so `rho_ss.ptrace(0)` is the cavity state.

The packaged entry point defaults to the requested four cases, with `N=4`, cavity dimension 16, unit frequencies and cavity loss, `g=2/sqrt(N)`, and a 1000 by 1000 grid over both axes from -6 to 6.

## Prerequisite

The execution environment needs Python with `numpy`, `scipy`, and a QuTiP installation that includes `qutip.piqs` (PIQS). The solver may be computationally intensive; do not reduce the default grid or cavity dimension when the required deliverable calls for the stated values.

## Run

The script reads one JSON object from standard input and emits a JSON report on standard output. To generate the required `1.csv` through `4.csv` in the current directory:

```bash
printf '{"output_dir":"."}' | python scripts/open_dicke_wigner.py
```

Its input schema is:

```json
{
  "output_dir": "directory for CSV files (default: current directory)",
  "N": 4,
  "nphotons": 16,
  "omega0": 1.0,
  "omegac": 1.0,
  "g": 1.0,
  "kappa": 1.0,
  "x_min": -6.0,
  "x_max": 6.0,
  "grid_points": 1000,
  "cases": [
    {"filename": "1.csv", "dephasing": 0.01, "pumping": 0.1}
  ]
}
```

All fields except `output_dir` are optional; unspecified values use the task defaults. `cases`, if supplied, replaces the complete case list and each item must have a safe basename `filename` plus any PIQS rates among `emission`, `dephasing`, `pumping`, `collective_emission`, `collective_dephasing`, and `collective_pumping`.

## Output interpretation and validation

Each CSV is a headerless numeric matrix. Row `i` corresponds to ascending momentum coordinate `p[i]`, and column `j` corresponds to ascending position coordinate `x[j]`. The coordinates are uniformly spaced inclusive endpoints of the configured range. Thus the default output has exactly 1000 rows and 1000 columns per file.

The composite sparse Liouvillian is propagated in time to its stationary residual rather than factored as a dense-fill direct solve. Before committing files, the entry point validates the full steady state (trace, Hermiticity, and Liouvillian residual), the cavity reduction, and every Wigner array (shape, finite values, coordinate ordering, and numerical normalization). It also rejects identical grids across requested cases. Files are first written to temporary sibling paths and atomically renamed only after all validation succeeds. The JSON report includes artifact paths, dimensions, and integrals; `ok: false` and a nonzero process exit indicate a missing prerequisite, invalid input, solver failure, or validation failure.
