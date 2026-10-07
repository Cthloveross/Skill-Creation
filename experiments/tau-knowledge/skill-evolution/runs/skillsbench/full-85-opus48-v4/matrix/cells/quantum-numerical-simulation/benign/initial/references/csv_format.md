# Output CSV format

Each case `k` is saved as `k.csv` (`1.csv`, `2.csv`, `3.csv`, `4.csv`) in the
chosen `output_dir`.

- Content: the cavity-field Wigner function `W(x, p)` evaluated on a square
  grid. Default grid is `1000 x 1000` with `x, p` linearly spaced over
  `[-6, 6]` (`numpy.linspace(-6, 6, 1000)` for both axes).
- Layout: a plain comma-separated matrix of shape `(grid, grid)` exactly as
  returned by `qutip.wigner(rho_cavity, xvec, xvec)`. Row index runs over the
  `p` axis values, column index over the `x` axis values (QuTiP convention).
- No header row, no index column. Values are real doubles written with the
  `fmt` format string (default `%.12e`).

## Validation expectations (no reference values used)

- Shape equals the requested grid (`1000 x 1000`).
- All entries finite (no NaN/Inf).
- Normalization `sum(W) * dx * dp` is close to 1 (a finite grid truncates the
  Wigner tails, so a few percent deviation is acceptable; grossly wrong values
  indicate a convention or dimension bug).
- The reduced cavity state has unit trace and the full steady state is
  Hermitian with a small Liouvillian residual `||L vec(rho)||`.
- The four cases must be pairwise distinct Wigner grids.

These checks detect convention drift (wrong photon cutoff, doubled coupling,
wrong subsystem order for the partial trace) without comparing to any stored
reference output.
