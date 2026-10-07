---
name: open-dicke-wigner
description: >
  Simulate the steady state of an open Dicke model (N two-level atoms coupled to
  a lossy cavity) with QuTiP + PIQS, trace out the spins, and compute the cavity
  Wigner function on a user-defined x/p grid for several dissipation cases,
  saving each as a CSV. Use this when a request asks for open-Dicke steady-state
  cavity-field Wigner maps under local/collective dephasing, pumping, and
  emission rates with a photon-number cutoff.
---

# Open Dicke steady-state cavity Wigner function

## When to use
A request gives an open Dicke Hamiltonian

    H = w0*Jz + wc*a^dag a + g*(a^dag + a)*(J+ + J-)

with N two-level systems, a photon-number cutoff `n_max`, cavity loss `kappa`,
and several dissipation cases built from PIQS rates (local dephasing
`gamma_phi`, local pumping `gamma_up`, local emission `gamma_down`, collective
pumping `gamma_coll_up`, collective emission `gamma_coll_down`). For each case
you must solve the steady state, trace out the spins, and save the cavity
Wigner function over a grid as a CSV (`1.csv`, `2.csv`, ...).

## Convention (critical — follow exactly)
This Skill reproduces the QuTiP PIQS "Superradiance: Open Dicke Model"
software convention as one coherent convention (see
`references/conventions.md`):

- The photon cutoff is passed **directly as the dimension of `destroy`**:
  `a = destroy(n_max)` (so `n_max=16` means a 16-dimensional Fock space,
  photon numbers 0..15).
- The collective operator is the PIQS `Jx` from `jspin(N)` and the interaction
  is implemented as `h_int = g * tensor(a + a.dag(), jx)` with `g = 2/sqrt(N)`.
  **Do NOT insert an extra factor of 2.** The identity `J+ + J- = 2*Jx` is
  true, but this tutorial coefficient already belongs with `Jx`; multiplying
  by another 2 (mixing the ladder-operator coefficient with the `Jx` operator)
  changes the physical model. Keep `g = 2/sqrt(N)` and use `Jx`.
- The spin Liouvillian is built with the PIQS `Dicke` rate interface and
  includes the spin Hamiltonian `w0*Jz` **once**.
- The cavity Hamiltonian `wc*a.dag()*a` and the cavity-loss Liouvillian with
  collapse operator `sqrt(kappa)*a` are built in photon space.
- Identities are promoted to superoperators (`to_super(identity(...))`), the
  cavity and spin Liouvillians are combined with `super_tensor`, and the
  interaction commutator `-i[h_int, .]` is added **once** via `spre`/`spost`.
- **Cavity is subsystem 0.** `tensor(a..., jx)` puts the cavity first, so the
  later `ptrace(rho, 0)` keeps the cavity.

## Workflow per case
1. Build the total Liouvillian as above.
2. `steadystate(L_tot)` -> full density matrix (dims `[[n_max, nds], ...]`).
3. `rho_cav = rho.ptrace(0)` to trace out the spins.
4. `wigner(rho_cav, xvec, pvec)` on the requested grid.
5. Save the grid to `<outdir>/<case>.csv` as a plain numeric matrix.

## Validation (does not use reference output values)
Before the expensive 1000x1000 grid the entrypoint runs a **small-instance**
check (small N and cutoff, coarse grid) verifying: tensor dims and subsystem
ordering (cavity index 0), unit trace, Hermiticity, steady-state residual
`||L_tot * vec(rho_ss)|| ~ 0`, and Wigner normalization. For every full grid it
validates shape, finiteness, axis ordering, normalization
(`sum(W)*dx*dp ~ 1`), and that the four cases are **distinct**. These checks
catch convention drift (wrong coupling factor, wrong subsystem order, wrong
cutoff) without any reference numbers.

## Entrypoint
`scripts/run.py` reads a JSON config on stdin and prints a JSON report on
stdout. With no stdin it uses the defaults matching the standard task
(N=4, w0=wc=1, g=2/sqrt(N), kappa=1, n_max=16, grid [-6,6] 1000x1000, and the
four dissipation cases). It writes `1.csv`..`4.csv` into `outdir`.

Example:
```bash
cd /root
python /app/environment/skills/current/scripts/run.py <<'JSON'
{"outdir": "/root"}
JSON
```
Override anything explicitly, e.g. a custom case list or grid:
```bash
python /app/environment/skills/current/scripts/run.py <<'JSON'
{
  "N": 4, "w0": 1, "wc": 1, "kappa": 1, "nphot": 16,
  "xmin": -6, "xmax": 6, "ngrid": 1000,
  "outdir": "/root",
  "cases": [
    {"name": "1", "dephasing": 0.01, "pumping": 0.1},
    {"name": "2", "dephasing": 0.01, "emission": 0.1},
    {"name": "3", "dephasing": 0.01, "emission": 0.1, "collective_pumping": 0.1},
    {"name": "4", "dephasing": 0.01, "emission": 0.1, "collective_emission": 0.1}
  ]
}
JSON
```

### Config schema
- `N` (int), `w0`,`wc`,`kappa` (float), `g` (float|null -> 2/sqrt(N)),
  `nphot` (int, photon-space dimension = n_max),
- `xmin`,`xmax` (float), `ngrid` (int) grid shared by x and p,
- `outdir` (str), `validate_small` (bool, default true), `full` (bool, default true),
- `cases`: list of objects. Each supports `name` plus any of the PIQS rate keys:
  `dephasing` (gamma_phi), `pumping` (gamma_up), `emission` (gamma_down),
  `collective_pumping` (gamma_coll_up), `collective_emission` (gamma_coll_down),
  `collective_dephasing`. Missing rates default to 0. `kappa` is cavity loss and
  is applied to every case.

### Report schema (stdout JSON)
```
{"ok": bool,
 "small": {... validation ...} | null,
 "cases": [{"name":..., "file":..., "dims":[nphot,nds], "trace_err":float,
            "herm_err":float, "residual":float, "wigner_norm":float,
            "shape":[r,c], "finite":bool}],
 "distinct": bool,
 "errors": [..]}
```
If `ok` is false or any `errors` are present, inspect the message, fix the
config/convention, and rerun. Use `scripts/validate.py` to re-check already
written CSVs without recomputing.

## How the executor completes the task
1. Run the entrypoint from the directory where CSVs are required (`/root`),
   or set `outdir` explicitly.
2. Confirm the report has `ok=true`, `distinct=true`, each `trace_err`,
   `herm_err`, `residual` small, and each `wigner_norm` near 1.
3. Confirm `1.csv`..`4.csv` exist with shape `ngrid x ngrid`.
4. If a dependency is missing (`qutip`/PIQS), install it
   (`pip install qutip`) using the available network, then rerun.
