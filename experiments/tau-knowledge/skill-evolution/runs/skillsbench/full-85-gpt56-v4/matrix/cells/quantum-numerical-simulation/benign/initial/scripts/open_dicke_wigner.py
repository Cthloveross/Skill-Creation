#!/usr/bin/env python3
"""Generate validated PIQS open-Dicke cavity Wigner CSV grids.

Reads a JSON configuration from stdin and writes a JSON result to stdout.
"""
import json
import math
import os
import sys
from pathlib import Path

import numpy as np


DEFAULT_CASES = [
    {"filename": "1.csv", "dephasing": 0.01, "pumping": 0.1},
    {"filename": "2.csv", "dephasing": 0.01, "emission": 0.1},
    {"filename": "3.csv", "dephasing": 0.01, "emission": 0.1,
     "collective_pumping": 0.1},
    {"filename": "4.csv", "dephasing": 0.01, "emission": 0.1,
     "collective_emission": 0.1},
]
RATE_KEYS = {
    "emission", "dephasing", "pumping", "collective_emission",
    "collective_dephasing", "collective_pumping",
}


def read_config():
    """Read a single optional JSON object, returning task-compliant defaults."""
    raw = sys.stdin.read().strip()
    supplied = {} if not raw else json.loads(raw)
    if not isinstance(supplied, dict):
        raise ValueError("stdin JSON must be an object")
    cfg = {
        "output_dir": ".",
        "N": 4,
        "nphotons": 16,
        "omega0": 1.0,
        "omegac": 1.0,
        "g": None,  # derived from N unless explicitly specified
        "kappa": 1.0,
        "x_min": -6.0,
        "x_max": 6.0,
        "grid_points": 1000,
        "cases": [dict(item) for item in DEFAULT_CASES],
    }
    unknown = set(supplied) - set(cfg)
    if unknown:
        raise ValueError("unknown configuration fields: " + ", ".join(sorted(unknown)))
    cfg.update(supplied)
    if cfg["g"] is None:
        cfg["g"] = 2.0 / math.sqrt(float(cfg["N"]))
    return cfg


def validate_config(cfg):
    """Validate dimensions, scalar physics parameters, and requested case naming."""
    for key in ("N", "nphotons", "grid_points"):
        value = cfg[key]
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ValueError(f"{key} must be a positive integer")
    if cfg["N"] < 2:
        raise ValueError("N must be at least 2 for this collective-spin workflow")
    if cfg["grid_points"] < 2:
        raise ValueError("grid_points must be at least 2")
    for key in ("omega0", "omegac", "g", "kappa", "x_min", "x_max"):
        if not np.isfinite(float(cfg[key])):
            raise ValueError(f"{key} must be finite")
    if cfg["kappa"] < 0:
        raise ValueError("kappa cannot be negative")
    if not float(cfg["x_min"]) < float(cfg["x_max"]):
        raise ValueError("x_min must be less than x_max")
    if not isinstance(cfg["cases"], list) or not cfg["cases"]:
        raise ValueError("cases must be a nonempty list")
    seen = set()
    for case in cfg["cases"]:
        if not isinstance(case, dict):
            raise ValueError("each case must be a JSON object")
        if "filename" not in case or not isinstance(case["filename"], str):
            raise ValueError("each case requires a string filename")
        filename = case["filename"]
        if Path(filename).name != filename or filename in ("", ".", ".."):
            raise ValueError("case filenames must be safe basenames")
        if filename in seen:
            raise ValueError("case filenames must be unique")
        seen.add(filename)
        bad = set(case) - RATE_KEYS - {"filename"}
        if bad:
            raise ValueError("unsupported case fields: " + ", ".join(sorted(bad)))
        for rate_key in RATE_KEYS:
            rate = float(case.get(rate_key, 0.0))
            if not np.isfinite(rate) or rate < 0:
                raise ValueError(f"{rate_key} must be a finite nonnegative rate")


def import_qutip():
    """Import the PIQS APIs only when execution actually starts."""
    try:
        from qutip import (destroy, liouvillian, qeye, spre, spost,
                           steadystate, super_tensor, tensor, to_super,
                           wigner, operator_to_vector)
        from qutip.piqs import Dicke, jspin
    except ImportError as exc:
        raise RuntimeError(
            "QuTiP with the PIQS module is required (install qutip with PIQS support)"
        ) from exc
    return {
        "destroy": destroy, "liouvillian": liouvillian, "qeye": qeye,
        "spre": spre, "spost": spost, "steadystate": steadystate,
        "super_tensor": super_tensor, "tensor": tensor, "to_super": to_super,
        "wigner": wigner, "operator_to_vector": operator_to_vector,
        "Dicke": Dicke, "jspin": jspin,
    }


def build_liouvillian(api, cfg, case):
    """Build the tutorial-convention total Liouvillian with cavity subsystem zero."""
    n_spin = cfg["N"]
    n_photons = cfg["nphotons"]
    a = api["destroy"](n_photons)
    jx = api["jspin"](n_spin, "x")
    jz = api["jspin"](n_spin, "z")
    h_spin = float(cfg["omega0"]) * jz
    rates = {key: float(case.get(key, 0.0)) for key in RATE_KEYS}
    system = api["Dicke"](N=n_spin, hamiltonian=h_spin, **rates)
    spin_l = system.liouvillian()
    spin_dim = jx.shape[0]

    h_cavity = float(cfg["omegac"]) * a.dag() * a
    c_ops = [] if float(cfg["kappa"]) == 0 else [math.sqrt(float(cfg["kappa"])) * a]
    cavity_l = api["liouvillian"](h_cavity, c_ops)

    # PIQS convention: g accompanies Jx directly, not J+ + J- with an extra 2.
    h_int = float(cfg["g"]) * api["tensor"](a + a.dag(), jx)
    total_l = (
        api["super_tensor"](cavity_l, api["to_super"](api["qeye"](spin_dim)))
        + api["super_tensor"](api["to_super"](api["qeye"](n_photons)), spin_l)
        - 1j * (api["spre"](h_int) - api["spost"](h_int))
    )
    return total_l


def validate_steady_state(api, total_l, rho, nphotons):
    """Check generic physical and numerical invariants before Wigner evaluation."""
    trace_error = abs(complex(rho.tr()) - 1.0)
    herm_error = float(np.linalg.norm((rho - rho.dag()).full()))
    residual = float((total_l * api["operator_to_vector"](rho)).norm())
    scale = max(1.0, float(total_l.norm()))
    if trace_error > 1e-8:
        raise RuntimeError(f"steady-state trace check failed: {trace_error:g}")
    if herm_error > 1e-7:
        raise RuntimeError(f"steady-state Hermiticity check failed: {herm_error:g}")
    if residual > 1e-7 * scale:
        raise RuntimeError(f"steady-state residual check failed: {residual:g}")
    cavity = rho.ptrace(0)
    if cavity.shape != (nphotons, nphotons):
        raise RuntimeError("partial trace did not retain cavity subsystem zero")
    if abs(complex(cavity.tr()) - 1.0) > 1e-8:
        raise RuntimeError("reduced cavity state does not have unit trace")
    return cavity, {"trace_error": float(trace_error), "hermiticity_error": herm_error,
                    "residual": residual}


def validate_wigner(w, xvec, pvec):
    """Validate serialized-grid semantics; rows are p and columns are x."""
    expected = (len(pvec), len(xvec))
    if w.shape != expected:
        raise RuntimeError(f"Wigner shape {w.shape} does not match expected {expected}")
    if not np.isfinite(w).all():
        raise RuntimeError("Wigner grid contains non-finite values")
    if not (np.all(np.diff(xvec) > 0) and np.all(np.diff(pvec) > 0)):
        raise RuntimeError("Wigner coordinate axes are not strictly ascending")
    integral = float(np.trapz(np.trapz(w, xvec, axis=1), pvec, axis=0))
    # The finite requested domain should contain essentially all normalized weight.
    if not np.isfinite(integral) or abs(integral - 1.0) > 2e-2:
        raise RuntimeError(f"Wigner normalization over configured grid failed: {integral:g}")
    return integral


def run(cfg):
    validate_config(cfg)
    api = import_qutip()
    output_dir = Path(cfg["output_dir"]).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    xvec = np.linspace(float(cfg["x_min"]), float(cfg["x_max"]), cfg["grid_points"])
    pvec = np.linspace(float(cfg["x_min"]), float(cfg["x_max"]), cfg["grid_points"])
    temporary = []
    grids = []
    report_cases = []
    try:
        for case in cfg["cases"]:
            total_l = build_liouvillian(api, cfg, case)
            rho = api["steadystate"](total_l, method="direct")
            cavity, state_checks = validate_steady_state(api, total_l, rho, cfg["nphotons"])
            w = np.asarray(api["wigner"](cavity, xvec, pvec), dtype=float)
            integral = validate_wigner(w, xvec, pvec)
            target = output_dir / case["filename"]
            tmp = output_dir / (case["filename"] + ".tmp")
            np.savetxt(tmp, w, delimiter=",", fmt="%.18e")
            temporary.append((tmp, target))
            grids.append(w)
            report_cases.append({
                "file": str(target), "shape": [int(w.shape[0]), int(w.shape[1])],
                "row_axis": "p ascending", "column_axis": "x ascending",
                "wigner_integral": integral, "steady_state": state_checks,
            })
        for i in range(len(grids)):
            for j in range(i):
                if np.array_equal(grids[i], grids[j]):
                    raise RuntimeError("distinct loss cases produced identical Wigner grids")
        for tmp, target in temporary:
            os.replace(tmp, target)
    except Exception:
        for tmp, _ in temporary:
            try:
                tmp.unlink()
            except FileNotFoundError:
                pass
        raise
    return {
        "ok": True,
        "cases": report_cases,
        "x_range": [float(xvec[0]), float(xvec[-1])],
        "p_range": [float(pvec[0]), float(pvec[-1])],
        "grid_points": int(cfg["grid_points"]),
    }


def main():
    try:
        print(json.dumps(run(read_config()), allow_nan=False))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, allow_nan=False))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
