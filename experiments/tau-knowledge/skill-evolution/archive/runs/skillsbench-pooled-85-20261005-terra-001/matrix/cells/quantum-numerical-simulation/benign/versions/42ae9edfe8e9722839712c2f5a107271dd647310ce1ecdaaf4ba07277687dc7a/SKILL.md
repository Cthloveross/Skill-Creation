---
name: open-dicke-steady-state-wigner
version: 1.0.0
description: Solve PIQS open-Dicke steady states for dissipative-rate cases, reduce to the cavity subsystem, and serialize validated cavity Wigner grids as CSV files. Use when QuTiP with the PIQS module is available and the cavity must be subsystem zero.
---

# Open-Dicke steady-state Wigner grids

Use `scripts/open_dicke_wigner.py` to generate the four requested cavity Wigner-function CSV files. The script requires Python, NumPy, and a QuTiP installation that includes `qutip.piqs`.

## Model convention

This Skill uses one coherent PIQS tutorial convention:

- `nmax` is passed **directly** as `destroy(nmax)`, so `nmax=16` means a 16-dimensional photon Hilbert space, not states zero through 16.
- The collective spin operators are PIQS `jspin(N, ...)` operators in the PIQS Dicke basis.
- The spin Hamiltonian `omega0 * Jz` is supplied once to `Dicke`.
- Cavity loss is represented by the collapse operator `sqrt(kappa) * a` in the cavity Liouvillian.
- The cavity is subsystem zero. The full Liouvillian is assembled with `super_tensor`, then the interaction commutator is added once.
- The interaction is exactly `g * tensor(a + a.dag(), jx)`. Do not add a factor of two when using `Jx`; the supplied `g=2/sqrt(N)` is used as the coefficient in this `Jx` convention.

The default cases correspond to local dephasing plus, respectively, local pumping; local emission; local emission plus collective pumping; and local emission plus collective emission.

## Input and execution

The script receives one JSON object on standard input and emits a compact JSON result on standard output. Omit fields to use the requested defaults.

```json
{
  "output_dir": "./wigner_output",
  "N": 4,
  "omega0": 1.0,
  "omegac": 1.0,
  "g": 1.0,
  "kappa": 1.0,
  "nmax": 16,
  "grid_min": -6.0,
  "grid_max": 6.0,
  "grid_points": 1000,
  "preflight": true,
  "normalization_tolerance": 0.1
}
```

For example, an executor may run:

```bash
python scripts/open_dicke_wigner.py <<'JSON'
{"output_dir":"./wigner_output"}
JSON
```

`g` defaults to `2/sqrt(N)` if omitted. `nphot` is accepted as an alias for `nmax`; both mean the dimension supplied to `destroy`. To replace the rate schedule, provide `cases` as a nonempty array of objects with a CSV `filename` and any of `dephasing`, `pumping`, `emission`, `collective_pumping`, and `collective_emission`. For the requested deliverable, leave `cases` omitted, which produces `1.csv`, `2.csv`, `3.csv`, and `4.csv`.

## Outputs

Each CSV is a headerless numeric matrix with exactly 1000 rows and 1000 columns under the default configuration. Rows are increasing momentum `p`; columns are increasing position/quadrature `x`. Both axes are inclusive `linspace(grid_min, grid_max, grid_points)` axes. Thus the CSV holds values `W[p_index, x_index]`, without embedded coordinate labels.

The script also writes `wigner_manifest.json` in `output_dir`. It records the file names, axis definition, model parameters, rate cases, numerical Wigner integrals, and validation diagnostics, so that the headerless CSV coordinate convention remains unambiguous.

The stdout success schema is:

```json
{
  "ok": true,
  "output_dir": "...",
  "files": [
    {"filename": "1.csv", "path": "...", "shape": [1000, 1000], "integral": 1.0}
  ],
  "manifest": "...",
  "preflight": {"passed": true}
}
```

On an unavailable PIQS/QuTiP installation, unsupported input, solver failure, invalid state, or failed grid validation, stdout is instead a JSON object with `ok: false` and an explanatory `error`; the process exits nonzero.

## Validation performed

Before the costly production grids, the default preflight solves a smaller PIQS instance and checks operator dimensions, unit trace, Hermiticity, steady-state residual, cavity-at-index-zero partial tracing, and a small Wigner normalization calculation. For every production case the script checks the reduced state and the in-memory Wigner grid, then reloads every serialized CSV and checks shape, finite values, round-trip agreement, Wigner normalization over the specified rectangular grid, and the declared row/column axis convention. It also rejects grids that are numerically indistinguishable between different loss cases. The finite-window Wigner integral is compared to one using `normalization_tolerance`; increase that value only when intentionally using a window too narrow to capture the state.
