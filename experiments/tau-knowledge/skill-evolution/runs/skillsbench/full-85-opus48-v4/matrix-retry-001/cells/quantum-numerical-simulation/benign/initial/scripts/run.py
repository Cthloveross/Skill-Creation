#!/usr/bin/env python3
"""Open Dicke steady-state cavity Wigner computation.

Reads a JSON config on stdin, writes <name>.csv per case into outdir, and
prints a JSON report on stdout. See SKILL.md for the schema.
"""
import sys
import os
import json
import math

import numpy as np


def load_qutip():
    import qutip
    syms = {}
    from qutip import (destroy, tensor, identity, liouvillian, spre, spost,
                       to_super, super_tensor, steadystate, wigner,
                       operator_to_vector)
    syms.update(dict(destroy=destroy, tensor=tensor, identity=identity,
                     liouvillian=liouvillian, spre=spre, spost=spost,
                     to_super=to_super, super_tensor=super_tensor,
                     steadystate=steadystate, wigner=wigner,
                     operator_to_vector=operator_to_vector))
    piqs = None
    last = None
    for modname in ("qutip.piqs", "qutip.piqs.piqs", "qutip_piqs"):
        try:
            mod = __import__(modname, fromlist=["Dicke", "jspin",
                                               "num_dicke_states"])
            if hasattr(mod, "Dicke"):
                piqs = mod
                break
        except Exception as exc:  # pragma: no cover - import probing
            last = exc
            continue
    if piqs is None:
        raise ImportError("Cannot import QuTiP PIQS (Dicke): %r" % (last,))
    syms["Dicke"] = piqs.Dicke
    syms["jspin"] = piqs.jspin
    syms["num_dicke_states"] = piqs.num_dicke_states
    return qutip, syms


RATE_KEYS = (
    "dephasing", "pumping", "emission",
    "collective_pumping", "collective_emission", "collective_dephasing",
)


def build_total_liouvillian(Q, params, case):
    """Return (L_tot, rho_ss, rho_cav, nphot, nds) for one dissipation case.

    Follows the frozen PIQS tutorial convention:
      a = destroy(nphot); h_int = g*tensor(a+a.dag(), jx) with g=2/sqrt(N),
      cavity = subsystem 0, spin Hamiltonian included once.
    """
    N = int(params["N"])
    w0 = float(params["w0"])
    wc = float(params["wc"])
    kappa = float(params["kappa"])
    nphot = int(params["nphot"])
    g = params.get("g")
    g = (2.0 / math.sqrt(N)) if g in (None, "") else float(g)

    jx, jy, jz = Q["jspin"](N)
    nds = int(Q["num_dicke_states"](N))

    # Spin Liouvillian with PIQS Dicke rate interface, spin H included once.
    ens = Q["Dicke"](N=N)
    ens.hamiltonian = w0 * jz
    for key in RATE_KEYS:
        if key in case and case[key] not in (None, ""):
            setattr(ens, key, float(case[key]))
    L_spin = ens.liouvillian()

    # Cavity Hamiltonian and cavity-loss Liouvillian in photon space.
    a = Q["destroy"](nphot)
    h_c = wc * a.dag() * a
    L_cav = Q["liouvillian"](h_c, [math.sqrt(kappa) * a])

    # Promote identities to superoperators, combine with super_tensor
    # (cavity = subsystem 0), add interaction commutator once.
    id_cav = Q["to_super"](Q["identity"](nphot))
    id_spin = Q["to_super"](Q["identity"](nds))
    L_tot = Q["super_tensor"](L_cav, id_spin) + Q["super_tensor"](id_cav, L_spin)
    h_int = g * Q["tensor"](a + a.dag(), jx)
    L_tot = L_tot - 1j * (Q["spre"](h_int) - Q["spost"](h_int))

    rho_ss = Q["steadystate"](L_tot)
    rho_cav = rho_ss.ptrace(0)
    return L_tot, rho_ss, rho_cav, nphot, nds


def state_diagnostics(Q, L_tot, rho_ss, nphot, nds):
    trace_err = abs(complex(rho_ss.tr()) - 1.0)
    herm_err = (rho_ss - rho_ss.dag()).norm()
    try:
        residual = (L_tot * Q["operator_to_vector"](rho_ss)).norm()
    except Exception:
        residual = float("nan")
    dims0 = rho_ss.dims[0]
    return {
        "dims": [int(dims0[0]), int(dims0[1])],
        "subsystem0_is_cavity": int(dims0[0]) == int(nphot),
        "trace_err": float(trace_err),
        "herm_err": float(herm_err),
        "residual": float(residual),
    }


def wigner_grid(Q, rho_cav, xmin, xmax, ngrid):
    xvec = np.linspace(xmin, xmax, ngrid)
    # symmetrize + renormalize for a clean Hermitian, unit-trace input
    r = 0.5 * (rho_cav + rho_cav.dag())
    tr = complex(r.tr())
    if abs(tr) > 0:
        r = r / tr
    W = Q["wigner"](r, xvec, xvec)
    W = np.asarray(W, dtype=float)
    dx = (xmax - xmin) / (ngrid - 1)
    norm = float(np.sum(W) * dx * dx)
    return xvec, W, norm


def run_case(Q, params, case, xmin, xmax, ngrid, outdir):
    L_tot, rho_ss, rho_cav, nphot, nds = build_total_liouvillian(Q, params, case)
    diag = state_diagnostics(Q, L_tot, rho_ss, nphot, nds)
    _, W, norm = wigner_grid(Q, rho_cav, xmin, xmax, ngrid)
    name = str(case.get("name"))
    fpath = os.path.join(outdir, "%s.csv" % name)
    np.savetxt(fpath, W, delimiter=",")
    rec = {
        "name": name,
        "file": fpath,
        "dims": diag["dims"],
        "subsystem0_is_cavity": diag["subsystem0_is_cavity"],
        "trace_err": diag["trace_err"],
        "herm_err": diag["herm_err"],
        "residual": diag["residual"],
        "wigner_norm": norm,
        "shape": [int(W.shape[0]), int(W.shape[1])],
        "finite": bool(np.all(np.isfinite(W))),
    }
    return rec, W


def validate_small(Q):
    """Cheap convention sanity check; no reference values."""
    params = {"N": 2, "w0": 1.0, "wc": 1.0, "kappa": 1.0, "nphot": 4, "g": None}
    case = {"name": "small", "dephasing": 0.01, "emission": 0.1}
    L_tot, rho_ss, rho_cav, nphot, nds = build_total_liouvillian(Q, params, case)
    diag = state_diagnostics(Q, L_tot, rho_ss, nphot, nds)
    _, W, norm = wigner_grid(Q, rho_cav, -5.0, 5.0, 60)
    diag["wigner_norm"] = norm
    diag["wigner_finite"] = bool(np.all(np.isfinite(W)))
    diag["ok"] = bool(
        diag["subsystem0_is_cavity"]
        and diag["trace_err"] < 1e-5
        and diag["herm_err"] < 1e-5
        and (not np.isnan(diag["residual"]) and diag["residual"] < 1e-5)
        and abs(norm - 1.0) < 0.1
        and diag["wigner_finite"]
    )
    return diag


DEFAULT_CASES = [
    {"name": "1", "dephasing": 0.01, "pumping": 0.1},
    {"name": "2", "dephasing": 0.01, "emission": 0.1},
    {"name": "3", "dephasing": 0.01, "emission": 0.1, "collective_pumping": 0.1},
    {"name": "4", "dephasing": 0.01, "emission": 0.1, "collective_emission": 0.1},
]


def main():
    raw = sys.stdin.read()
    cfg = json.loads(raw) if raw.strip() else {}

    params = {
        "N": cfg.get("N", 4),
        "w0": cfg.get("w0", 1.0),
        "wc": cfg.get("wc", 1.0),
        "kappa": cfg.get("kappa", 1.0),
        "nphot": cfg.get("nphot", cfg.get("n_max", 16)),
        "g": cfg.get("g", None),
    }
    xmin = float(cfg.get("xmin", -6.0))
    xmax = float(cfg.get("xmax", 6.0))
    ngrid = int(cfg.get("ngrid", 1000))
    outdir = cfg.get("outdir", ".")
    os.makedirs(outdir, exist_ok=True)
    cases = cfg.get("cases", DEFAULT_CASES)
    for i, c in enumerate(cases, 1):
        c.setdefault("name", str(i))
    do_small = cfg.get("validate_small", True)
    do_full = cfg.get("full", True)

    report = {"ok": True, "small": None, "cases": [], "distinct": None,
              "errors": []}

    try:
        _, Q = load_qutip()
    except Exception as exc:
        report["ok"] = False
        report["errors"].append("import: %s" % exc)
        print(json.dumps(report))
        return 1

    if do_small:
        try:
            small = validate_small(Q)
            report["small"] = small
            if not small.get("ok"):
                report["ok"] = False
                report["errors"].append("small-instance validation failed")
        except Exception as exc:
            report["ok"] = False
            report["errors"].append("small: %s" % exc)

    if report["ok"] and do_full:
        mats = []
        for case in cases:
            try:
                rec, W = run_case(Q, params, case, xmin, xmax, ngrid, outdir)
                report["cases"].append(rec)
                mats.append(W)
                if (not rec["subsystem0_is_cavity"] or rec["trace_err"] > 1e-4
                        or rec["herm_err"] > 1e-4 or not rec["finite"]
                        or abs(rec["wigner_norm"] - 1.0) > 0.15):
                    report["ok"] = False
                    report["errors"].append(
                        "case %s failed validation" % rec["name"])
            except Exception as exc:
                report["ok"] = False
                report["errors"].append("case %s: %s" %
                                        (case.get("name"), exc))
        # distinctness across cases
        if len(mats) >= 2:
            distinct = True
            for i in range(len(mats)):
                for j in range(i + 1, len(mats)):
                    d = float(np.max(np.abs(mats[i] - mats[j])))
                    if d < 1e-9:
                        distinct = False
            report["distinct"] = distinct
            if not distinct:
                report["ok"] = False
                report["errors"].append("grids are not distinct across cases")

    print(json.dumps(report))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
