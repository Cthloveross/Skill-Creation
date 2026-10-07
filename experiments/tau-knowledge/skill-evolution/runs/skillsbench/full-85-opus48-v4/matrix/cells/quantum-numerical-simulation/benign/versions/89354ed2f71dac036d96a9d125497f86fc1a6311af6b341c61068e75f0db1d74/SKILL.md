---
name: open-dicke-wigner-piqs
description: >
  Simulate an open Dicke model (N two-level systems + one cavity mode) in its
  steady state with QuTiP/PIQS, trace out the spins, and compute the cavity
  field Wigner function on a grid, saving each dissipation case to a CSV file.
  Use this when a task asks to reproduce the QuTiP PIQS "Superradiance: Open
  Dicke Model" steady-state Wigner calculation for several loss configurations
  (local dephasing, local pumping/emission, collective pumping/emission).
---

# Open Dicke steady-state cavity Wigner function (QuTiP PIQS)

## What this Skill produces

For each requested dissipation case it:
1. builds the full open-Dicke Liouvillian (cavity + spin + coupling),
2. solves for the steady state,
3. partial-traces out the spins to get the reduced cavity density matrix,
4. evaluates the cavity Wigner function on an `x,p` grid, and
5. writes the grid to `<case>.csv` (e.g. `1.csv` .. `4.csv`).

## Physical model and parameters

Hamiltonian (open Dicke):

    H = w0 * Jz + wc * a.dag()*a + g*(a + a.dag())*(J+ + J-)

Defaults taken from the public task (read actual values at runtime; do not
hardcode answers):
- `N = 4` two-level systems
- `w0 = wc = 1`
- `g = 2/sqrt(N)`
- `kappa = 1` (cavity loss)
- `n_max = 16` photon cutoff
- Wigner grid: `x, p in [-6, 6]`, `1000 x 1000`

Four loss cases (PIQS `Dicke` rate names in parentheses):
1. local dephasing `dephasing=0.01` + local pumping `pumping=0.1`
2. local dephasing `dephasing=0.01` + local emission `emission=0.1`
3. case 2 + collective pumping `collective_pumping=0.1`
4. case 2 + collective emission `collective_emission=0.1`

In PIQS `Dicke`: `emission`=local emission (gamma_down), `pumping`=local
pumping (gamma_up), `dephasing`=local dephasing (gamma_phi),
`collective_emission`=gamma_Down, `collective_pumping`=gamma_Up.

## Critical convention (frozen background requirement)

Follow the QuTiP PIQS "Superradiance: Open Dicke Model" tutorial convention
exactly (this is the convention the reference solution enforces):
- Pass the photon cutoff directly as the dimension of `destroy`
  (`a = destroy(n_max)`, dimension `n_max`).
- Use the PIQS collective operator `jx` from `jspin(N)`.
- Implement the interaction as `h_int = g * tensor(a + a.dag(), jx)` using the
  task's coefficient `g = 2/sqrt(N)` directly on `jx`.
- **Do NOT multiply this coefficient by an extra factor of two.** Although
  `J+ + J- = 2*Jx`, the required tutorial form keeps `g` as the coefficient of
  the `jx` operator. Writing `g*(jp + jm)` (i.e. `2*g*jx`) doubles the coupling
  and is the "semantic selection" mistake the frozen background warns against.
- Keep the **cavity as subsystem 0** so that `ptrace(0)` yields the cavity.

Construction procedure (frozen background):
- Build the spin Liouvillian with the PIQS `Dicke` rate interface, including
  the spin Hamiltonian `w0*Jz` exactly once.
- Build the cavity Hamiltonian `wc*a.dag()*a` and the cavity-loss collapse
  operator `sqrt(kappa)*a` in photon space.
- Promote identities to superoperators (`to_super(qeye(...))`), combine the
  cavity and spin Liouvillians with `super_tensor`, and add the interaction
  commutator once as `-1j*(spre(h_int) - spost(h_int))`.

## Steady-state solver (performance)

The combined Liouvillian is a ~`(n_max*ndicke)^2` sparse superoperator (e.g.
`20736 x 20736` for `N=4, n_max=16`).  A plain sparse `direct` LU suffers
catastrophic fill-in and does **not** finish in reasonable time (a single case
ran >14 minutes without completing, which makes the whole task time out and
produce no CSVs).  `solve_steadystate` therefore defaults to
`qt.steadystate(L, method="direct", use_rcm=True)`, which reorders the matrix
(Reverse-Cuthill-McKee) and solves one case in ~1.5-3 min; the full four-case
`1000x1000` run finishes in ~15 min, well within the build timeout.  Do not
revert to the un-reordered default.

## Files

- `scripts/dicke_lib.py` — reusable builders/solvers/validators.
- `scripts/run_dicke.py` — end-to-end entrypoint (JSON in, JSON out, writes CSVs).
- `scripts/validate_outputs.py` — re-validates CSVs already on disk.
- `references/csv_format.md` — CSV layout and validation notes.

## Running the entrypoint

`run_dicke.py` reads a JSON config from stdin and writes `1.csv`..`4.csv` into
`output_dir`. All keys are optional; omit them to use the task defaults above.

Example (produce the four required CSVs in /root):

    echo '{"output_dir": "/root"}' | \
      python3 /app/environment/skills/current/scripts/run_dicke.py

Override parameters (same shape as the task, if the instance differs):

    echo '{"output_dir":"/root","N":4,"n_max":16,"w0":1,"wc":1,
           "kappa":1,"grid":1000,"xmin":-6,"xmax":6}' | \
      python3 scripts/run_dicke.py

Fast pre-grid sanity check (small cavity cutoff + small grid), as recommended by
the frozen background, without touching the real CSVs:

    echo '{"validate_only": true}' | python3 scripts/run_dicke.py

### Input JSON schema (run_dicke.py)

- `output_dir` (str, default `.`): where to write `<case>.csv`.
- `N`, `n_max`, `w0`, `wc`, `kappa`, `g` (numbers): model params. `g` defaults
  to `2/sqrt(N)`.
- `grid` (int, default 1000), `xmin`, `xmax` (default -6, 6): Wigner grid.
- `cases` (list of ints, default `[1,2,3,4]`): which cases to run.
- `validate_only` (bool, default false): run a small-cutoff validation instead
  of writing CSVs.
- `steadystate_method` (str, optional): forwarded to `qutip.steadystate`.
- `fmt` (str, default `%.12e`): numpy savetxt format.

### Output JSON schema (run_dicke.py)

    {
      "status": "ok" | "error",
      "results": {
        "1": {"path":..., "wigner_shape":[1000,1000], "finite":true,
              "norm":<~1.0>, "trace_rho_cav":<~1.0>,
              "hermiticity":<~0>, "ss_residual":<~0>}, ...
      },
      "distinct": {"1-2": <maxabsdiff>, ...},
      "all_distinct": true
    }

The executor should: run the entrypoint with `{"output_dir": "<workspace>"}`,
confirm `status==ok`, confirm each `wigner_shape` equals the requested grid,
each `finite` is true, each `norm` is close to 1 (within a few percent, since a
finite grid truncates the tails), each `trace_rho_cav` ~ 1, `ss_residual` and
`hermiticity` are near 0, and `all_distinct` is true (the four cases must give
different Wigner functions). Then confirm the four CSV files exist with shape
`grid x grid`. Re-run `validate_outputs.py` to independently check the written
files.

## Interpreting failures

- Import errors: the Skill tries `qutip.piqs`, `qutip.solve.piqs`, then
  `qutip` for `Dicke`, `jspin`, `num_dicke_states`. If none resolve, QuTiP/PIQS
  is unavailable and the task cannot be completed in this runtime; report that.
- `steadystate` failure: `solve_steadystate` retries `direct`+RCM, plain
  `direct`, `iterative-gmres`+RCM, then `eigen`. If all fail, inspect the
  Liouvillian dims. Avoid the un-reordered default as the primary method.
- `norm` far from 1 or non-finite Wigner: likely a convention/dim bug (e.g.
  wrong subsystem order, a coupling off by a factor of 2, or wrong photon
  cutoff). Re-read the convention section; do not patch by rescaling the output.
- Two cases identical (`all_distinct` false): a rate was not applied; check the
  `cases` mapping in `dicke_lib.CASES`.

Do not copy any numeric Wigner values or per-instance CSV contents into the
Skill; always regenerate from the current task's parameters.
