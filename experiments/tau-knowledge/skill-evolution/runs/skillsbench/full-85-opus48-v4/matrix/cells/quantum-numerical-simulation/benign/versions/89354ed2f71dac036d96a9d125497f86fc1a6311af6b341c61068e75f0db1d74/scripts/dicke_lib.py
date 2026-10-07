"""Reusable builders/solvers for the open-Dicke steady-state Wigner task.

Numerics follow the QuTiP PIQS "Superradiance: Open Dicke Model" tutorial
convention (frozen background requirement): photon cutoff passed directly as
the destroy dimension, PIQS jx used as the collective operator, interaction
    h_int = g * tensor(a + a.dag(), jx)    (NO extra factor of two),
and the cavity kept as subsystem 0 for the partial trace.
The steady state is solved with method="direct", use_rcm=True (RCM reordering)
because the un-reordered sparse LU does not finish in reasonable time.
"""
import importlib
import numpy as np
import qutip as qt


def _load_piqs():
    last = None
    for modpath in ("qutip.piqs", "qutip.solve.piqs", "qutip"):
        try:
            mod = importlib.import_module(modpath)
            return mod.Dicke, mod.jspin, mod.num_dicke_states
        except Exception as exc:  # pragma: no cover - environment dependent
            last = exc
            continue
    raise ImportError(
        "QuTiP PIQS (Dicke/jspin/num_dicke_states) is unavailable: %r" % (last,)
    )


Dicke, jspin, num_dicke_states = _load_piqs()

# Case -> PIQS Dicke rate keyword arguments (see SKILL.md for the physics).
CASES = {
    1: {"dephasing": 0.01, "pumping": 0.1},
    2: {"dephasing": 0.01, "emission": 0.1},
    3: {"dephasing": 0.01, "emission": 0.1, "collective_pumping": 0.1},
    4: {"dephasing": 0.01, "emission": 0.1, "collective_emission": 0.1},
}


def build_operators(N, nphot):
    jx, jy, jz = jspin(N)
    jp = jspin(N, "+")
    jm = jspin(N, "-")
    a = qt.destroy(nphot)
    return {"jx": jx, "jy": jy, "jz": jz, "jp": jp, "jm": jm, "a": a}


def build_liouvillian(N, nphot, w0, wc, g, kappa, rates):
    """Full open-Dicke Liouvillian with the cavity as subsystem 0."""
    ops = build_operators(N, nphot)
    jx, jz, a = ops["jx"], ops["jz"], ops["a"]

    # Spin Liouvillian via the PIQS Dicke rate interface; spin Hamiltonian once.
    ensemble = Dicke(N=N, hamiltonian=w0 * jz, **rates)
    L_spin = ensemble.liouvillian()

    # Cavity Hamiltonian and loss in photon space.
    h_cav = wc * a.dag() * a
    L_cav = qt.liouvillian(h_cav, [np.sqrt(kappa) * a])

    # Promote identities to superoperators and combine (cavity = subsystem 0).
    I_cav = qt.qeye(nphot)
    I_spin = qt.qeye(jx.dims[0])
    L_cav_full = qt.super_tensor(L_cav, qt.to_super(I_spin))
    L_spin_full = qt.super_tensor(qt.to_super(I_cav), L_spin)

    # Interaction in the QuTiP PIQS "Superradiance: Open Dicke Model" tutorial
    # convention (frozen background / task requirement): the coefficient g from
    # the task multiplies the PIQS collective operator jx directly.  Do NOT add
    # an extra factor of two (jp + jm == 2*jx): the required form is exactly
    #     h_int = g * tensor(a + a.dag(), jx).
    # Added once.
    h_int = g * qt.tensor(a + a.dag(), jx)
    L_int = -1j * (qt.spre(h_int) - qt.spost(h_int))

    return L_cav_full + L_spin_full + L_int


def solve_steadystate(L, method=None):
    """Solve for the steady state of a Liouvillian.

    The plain sparse ``direct`` LU of this tensor-structured open-Dicke
    Liouvillian suffers catastrophic fill-in (a single n_max=16 case did not
    finish after >14 minutes).  Reverse-Cuthill-McKee reordering
    (``use_rcm=True``) collapses that to ~90 s, so it is the default.  An
    explicit ``method`` is honoured verbatim; otherwise a robustness chain is
    tried, each entry still using RCM where the method supports it.
    """
    if method:
        return qt.steadystate(L, method=method)
    attempts = [
        {"method": "direct", "use_rcm": True},
        {"method": "direct"},
        {"method": "iterative-gmres", "use_rcm": True},
        {"method": "eigen"},
    ]
    last = None
    for kw in attempts:
        try:
            return qt.steadystate(L, **kw)
        except Exception as exc:
            last = exc
            continue
    raise RuntimeError("steadystate failed for all methods: %r" % (last,))


def reduced_cavity_state(rho):
    """Trace out the spins; cavity is subsystem 0."""
    return rho.ptrace(0)


def compute_wigner(rho_cav, grid, xmin, xmax):
    xvec = np.linspace(xmin, xmax, grid)
    W = qt.wigner(rho_cav, xvec, xvec)
    return xvec, np.asarray(W)


def steadystate_residual(L, rho):
    v = qt.operator_to_vector(rho)
    r = L * v
    return float(r.norm())


def hermiticity_error(rho):
    return float((rho - rho.dag()).norm())


def wigner_norm(W, grid, xmin, xmax):
    dx = (xmax - xmin) / (grid - 1)
    return float(np.sum(W) * dx * dx)


def run_case(idx, N, nphot, w0, wc, g, kappa, grid, xmin, xmax,
             steadystate_method=None):
    """Solve one case, returning (W, metrics dict)."""
    rates = CASES[idx]
    L = build_liouvillian(N, nphot, w0, wc, g, kappa, rates)
    rho = solve_steadystate(L, method=steadystate_method)
    rho_cav = reduced_cavity_state(rho)
    _, W = compute_wigner(rho_cav, grid, xmin, xmax)
    metrics = {
        "wigner_shape": list(W.shape),
        "finite": bool(np.all(np.isfinite(W))),
        "norm": wigner_norm(W, grid, xmin, xmax),
        "trace_rho_cav": float(rho_cav.tr().real),
        "hermiticity": hermiticity_error(rho),
        "ss_residual": steadystate_residual(L, rho),
        "cavity_subsystem_dim": int(rho_cav.shape[0]),
    }
    return W, metrics
