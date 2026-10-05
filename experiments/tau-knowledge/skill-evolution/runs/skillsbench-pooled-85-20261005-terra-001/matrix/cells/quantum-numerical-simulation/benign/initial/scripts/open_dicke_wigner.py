#!/usr/bin/env python3
"""Generate validated steady-state cavity Wigner CSVs for PIQS open-Dicke models.

Input: one JSON object on stdin (documented in SKILL.md).
Output: one JSON result object on stdout. Diagnostics and Python tracebacks are sent
only to stderr by the runtime; expected operational errors are returned as JSON.
"""

from __future__ import annotations

import json
import math
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np


DEFAULT_CASES = [
    {"filename": "1.csv", "dephasing": 0.01, "pumping": 0.1},
    {"filename": "2.csv", "dephasing": 0.01, "emission": 0.1},
    {
        "filename": "3.csv",
        "dephasing": 0.01,
        "emission": 0.1,
        "collective_pumping": 0.1,
    },
    {
        "filename": "4.csv",
        "dephasing": 0.01,
        "emission": 0.1,
        "collective_emission": 0.1,
    },
]
RATE_KEYS = (
    "dephasing",
    "pumping",
    "emission",
    "collective_pumping",
    "collective_emission",
)


def _require_qutip() -> Dict[str, Any]:
    """Import the public QuTiP interfaces needed by this Skill."""
    try:
        from qutip import (  # type: ignore
            destroy,
            liouvillian,
            operator_to_vector,
            qeye,
            spost,
            spre,
            steadystate,
            super_tensor,
            tensor,
            to_super,
            wigner,
        )
        from qutip.piqs import Dicke, jspin  # type: ignore
    except Exception as exc:  # ImportError differs across QuTiP versions.
        raise RuntimeError(
            "QuTiP with the PIQS module is required (imports qutip.piqs.Dicke and jspin)."
        ) from exc
    return {
        "destroy": destroy,
        "liouvillian": liouvillian,
        "operator_to_vector": operator_to_vector,
        "qeye": qeye,
        "spost": spost,
        "spre": spre,
        "steadystate": steadystate,
        "super_tensor": super_tensor,
        "tensor": tensor,
        "to_super": to_super,
        "wigner": wigner,
        "Dicke": Dicke,
        "jspin": jspin,
    }


def _number(value: Any, name: str, nonnegative: bool = False) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    if nonnegative and result < 0:
        raise ValueError(f"{name} must be nonnegative")
    return result


def _positive_int(value: Any, name: str, minimum: int = 1) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be an integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if result != value and not (isinstance(value, str) and value.strip() == str(result)):
        raise ValueError(f"{name} must be an integer")
    if result < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return result


def _normalise_cases(raw_cases: Any) -> List[Dict[str, Any]]:
    source = DEFAULT_CASES if raw_cases is None else raw_cases
    if not isinstance(source, list) or not source:
        raise ValueError("cases must be a nonempty array")
    cases: List[Dict[str, Any]] = []
    names = set()
    for index, item in enumerate(source):
        if not isinstance(item, dict):
            raise ValueError(f"cases[{index}] must be an object")
        filename = item.get("filename")
        if not isinstance(filename, str) or not filename.endswith(".csv"):
            raise ValueError(f"cases[{index}].filename must be a .csv filename")
        if Path(filename).name != filename or filename in ("", ".", ".."):
            raise ValueError(f"cases[{index}].filename must be a simple relative filename")
        if filename in names:
            raise ValueError("case filenames must be unique")
        names.add(filename)
        case: Dict[str, Any] = {"filename": filename}
        for key in RATE_KEYS:
            case[key] = _number(item.get(key, 0.0), f"cases[{index}].{key}", True)
        cases.append(case)
    return cases


def parse_config(raw: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("stdin must contain a JSON object")
    n_spin = _positive_int(raw.get("N", 4), "N", 1)
    nphot = _positive_int(raw.get("nphot", raw.get("nmax", 16)), "nmax", 2)
    grid_points = _positive_int(raw.get("grid_points", 1000), "grid_points", 2)
    grid_min = _number(raw.get("grid_min", -6.0), "grid_min")
    grid_max = _number(raw.get("grid_max", 6.0), "grid_max")
    if grid_max <= grid_min:
        raise ValueError("grid_max must be greater than grid_min")
    output_dir_raw = raw.get("output_dir", ".")
    if not isinstance(output_dir_raw, str) or not output_dir_raw:
        raise ValueError("output_dir must be a nonempty path string")
    g_default = 2.0 / math.sqrt(n_spin)
    config = {
        "N": n_spin,
        "nphot": nphot,
        "omega0": _number(raw.get("omega0", 1.0), "omega0"),
        "omegac": _number(raw.get("omegac", raw.get("omega_c", 1.0)), "omegac"),
        "g": _number(raw.get("g", g_default), "g"),
        "kappa": _number(raw.get("kappa", 1.0), "kappa", True),
        "grid_min": grid_min,
        "grid_max": grid_max,
        "grid_points": grid_points,
        "output_dir": output_dir_raw,
        "preflight": bool(raw.get("preflight", True)),
        "normalization_tolerance": _number(
            raw.get("normalization_tolerance", 0.1), "normalization_tolerance", True
        ),
        "cases": _normalise_cases(raw.get("cases")),
    }
    return config


def build_liouvillian(qt: Dict[str, Any], cfg: Dict[str, Any], rates: Dict[str, Any]):
    """Build L with cavity as subsystem zero and the PIQS spin block as one subsystem."""
    a = qt["destroy"](cfg["nphot"])
    jx = qt["jspin"](cfg["N"], "x")
    jz = qt["jspin"](cfg["N"], "z")
    spin_dim = int(jx.shape[0])

    # Dicke owns the spin Hamiltonian and all spin dissipative rates exactly once.
    spin_system = qt["Dicke"](
        N=cfg["N"],
        hamiltonian=cfg["omega0"] * jz,
        emission=rates["emission"],
        dephasing=rates["dephasing"],
        pumping=rates["pumping"],
        collective_emission=rates["collective_emission"],
        collective_pumping=rates["collective_pumping"],
    )
    l_spin = spin_system.liouvillian()
    h_cavity = cfg["omegac"] * a.dag() * a
    c_ops = [math.sqrt(cfg["kappa"]) * a] if cfg["kappa"] > 0 else []
    l_cavity = qt["liouvillian"](h_cavity, c_ops)

    # Identity superoperators preserve ordering [cavity, spin].
    l_total = qt["super_tensor"](l_cavity, qt["to_super"](qt["qeye"](spin_dim)))
    l_total += qt["super_tensor"](qt["to_super"](qt["qeye"](cfg["nphot"])), l_spin)

    # PIQS tutorial convention: g multiplies Jx itself, with no added factor of two.
    h_int = cfg["g"] * qt["tensor"](a + a.dag(), jx)
    l_total += -1j * (qt["spre"](h_int) - qt["spost"](h_int))
    return l_total, spin_dim


def _state_diagnostics(qt: Dict[str, Any], rho: Any, liouvillian_op: Any,
                       nphot: int, spin_dim: int) -> Tuple[Any, Dict[str, float]]:
    trace_error = abs(complex(rho.tr()) - 1.0)
    dense = np.asarray(rho.full())
    hermiticity_error = float(np.linalg.norm(dense - dense.conj().T))
    residual_vec = liouvillian_op * qt["operator_to_vector"](rho)
    residual_error = float(np.linalg.norm(np.asarray(residual_vec.full())))
    dims = list(rho.dims[0])
    if dims != [nphot, spin_dim]:
        raise RuntimeError(
            f"unexpected subsystem dimensions {dims}; expected cavity-first [{nphot}, {spin_dim}]"
        )
    cavity = rho.ptrace(0)
    if list(cavity.dims[0]) != [nphot]:
        raise RuntimeError("partial trace over index 0 did not return the cavity subsystem")
    if trace_error > 1e-8:
        raise RuntimeError(f"steady-state trace validation failed: error={trace_error:.3e}")
    if hermiticity_error > 1e-8:
        raise RuntimeError(f"steady-state Hermiticity validation failed: error={hermiticity_error:.3e}")
    if residual_error > 1e-7:
        raise RuntimeError(f"steady-state residual validation failed: norm={residual_error:.3e}")
    return cavity, {
        "trace_error": float(trace_error),
        "hermiticity_error": hermiticity_error,
        "residual_norm": residual_error,
    }


def _wigner_diagnostics(grid: np.ndarray, x_axis: np.ndarray, p_axis: np.ndarray,
                        tolerance: float, expected_shape: Tuple[int, int]) -> Dict[str, Any]:
    if grid.shape != expected_shape:
        raise RuntimeError(f"Wigner shape {grid.shape} does not match {expected_shape}")
    if not np.isfinite(grid).all():
        raise RuntimeError("Wigner grid contains non-finite values")
    # QuTiP returns rows indexed by its second axis (p/y), columns by first (x).
    integral = float(np.trapz(np.trapz(grid, x_axis, axis=1), p_axis, axis=0))
    error = abs(integral - 1.0)
    if error > tolerance:
        raise RuntimeError(
            "Wigner normalization over the requested finite grid failed: "
            f"integral={integral:.12g}, tolerance={tolerance:.12g}"
        )
    return {
        "shape": [int(grid.shape[0]), int(grid.shape[1])],
        "finite": True,
        "integral": integral,
        "normalization_error": error,
        "axis_order": "rows=p ascending, columns=x ascending",
    }


def _atomic_savetxt(path: Path, grid: np.ndarray) -> None:
    fd, temporary_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            np.savetxt(handle, grid, delimiter=",", fmt="%.17g")
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise


def _serialise_and_validate(path: Path, grid: np.ndarray, x_axis: np.ndarray,
                            p_axis: np.ndarray, tolerance: float) -> Dict[str, Any]:
    _atomic_savetxt(path, grid)
    reloaded = np.loadtxt(path, delimiter=",")
    diag = _wigner_diagnostics(reloaded, x_axis, p_axis, tolerance, grid.shape)
    if not np.allclose(reloaded, grid, rtol=1e-13, atol=1e-14):
        raise RuntimeError(f"CSV round-trip validation failed for {path.name}")
    diag["serialized"] = True
    return diag


def _ensure_distinct(grids: List[np.ndarray], names: List[str]) -> None:
    for left in range(len(grids)):
        for right in range(left + 1, len(grids)):
            largest_difference = float(np.max(np.abs(grids[left] - grids[right])))
            if largest_difference <= 1e-10:
                raise RuntimeError(
                    f"Wigner grids {names[left]} and {names[right]} are not numerically distinct"
                )


def run_preflight(qt: Dict[str, Any], cfg: Dict[str, Any], x_axis: np.ndarray,
                  p_axis: np.ndarray) -> Dict[str, Any]:
    """Perform a fast independent structural/physical check before full grids."""
    small_cfg = dict(cfg)
    small_cfg["N"] = min(cfg["N"], 2)
    small_cfg["nphot"] = min(cfg["nphot"], 4)
    # Retain the requested coefficient unless it was derived from N by default.
    if abs(cfg["g"] - 2.0 / math.sqrt(cfg["N"])) < 1e-15:
        small_cfg["g"] = 2.0 / math.sqrt(small_cfg["N"])
    l_small, spin_dim = build_liouvillian(qt, small_cfg, cfg["cases"][0])
    rho_small = qt["steadystate"](l_small, method="direct")
    cavity, state_diag = _state_diagnostics(qt, rho_small, l_small, small_cfg["nphot"], spin_dim)
    compact_x = np.linspace(cfg["grid_min"], cfg["grid_max"], 81)
    compact_p = np.linspace(cfg["grid_min"], cfg["grid_max"], 81)
    compact_grid = np.asarray(qt["wigner"](cavity, compact_x, compact_p), dtype=float)
    wigner_diag = _wigner_diagnostics(
        compact_grid,
        compact_x,
        compact_p,
        cfg["normalization_tolerance"],
        (len(compact_p), len(compact_x)),
    )
    return {
        "passed": True,
        "small_N": small_cfg["N"],
        "small_nphot": small_cfg["nphot"],
        "state": state_diag,
        "wigner": wigner_diag,
    }


def execute(cfg: Dict[str, Any]) -> Dict[str, Any]:
    qt = _require_qutip()
    output_dir = Path(cfg["output_dir"]).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    x_axis = np.linspace(cfg["grid_min"], cfg["grid_max"], cfg["grid_points"])
    p_axis = np.linspace(cfg["grid_min"], cfg["grid_max"], cfg["grid_points"])

    preflight: Dict[str, Any] = {"passed": False, "skipped": True}
    if cfg["preflight"]:
        preflight = run_preflight(qt, cfg, x_axis, p_axis)

    grids: List[np.ndarray] = []
    in_memory_records: List[Dict[str, Any]] = []
    names: List[str] = []
    for case in cfg["cases"]:
        l_total, spin_dim = build_liouvillian(qt, cfg, case)
        rho_ss = qt["steadystate"](l_total, method="direct")
        cavity, state_diag = _state_diagnostics(qt, rho_ss, l_total, cfg["nphot"], spin_dim)
        grid = np.asarray(qt["wigner"](cavity, x_axis, p_axis), dtype=float)
        grid_diag = _wigner_diagnostics(
            grid,
            x_axis,
            p_axis,
            cfg["normalization_tolerance"],
            (cfg["grid_points"], cfg["grid_points"]),
        )
        grids.append(grid)
        names.append(case["filename"])
        in_memory_records.append({"case": case, "state": state_diag, "grid": grid_diag})

    _ensure_distinct(grids, names)
    file_records: List[Dict[str, Any]] = []
    for grid, record in zip(grids, in_memory_records):
        destination = output_dir / record["case"]["filename"]
        serialized_diag = _serialise_and_validate(
            destination, grid, x_axis, p_axis, cfg["normalization_tolerance"]
        )
        file_records.append(
            {
                "filename": destination.name,
                "path": str(destination),
                "shape": serialized_diag["shape"],
                "integral": serialized_diag["integral"],
                "normalization_error": serialized_diag["normalization_error"],
                "state": record["state"],
            }
        )

    manifest = {
        "format": "headerless CSV W[p_index, x_index]",
        "axis_order": "rows=p ascending, columns=x ascending",
        "x": {"min": cfg["grid_min"], "max": cfg["grid_max"], "points": cfg["grid_points"]},
        "p": {"min": cfg["grid_min"], "max": cfg["grid_max"], "points": cfg["grid_points"]},
        "model": {
            "N": cfg["N"], "nphot_dimension": cfg["nphot"], "omega0": cfg["omega0"],
            "omegac": cfg["omegac"], "g_Jx_convention": cfg["g"], "kappa": cfg["kappa"],
        },
        "cases": in_memory_records,
        "files": file_records,
        "preflight": preflight,
    }
    manifest_path = output_dir / "wigner_manifest.json"
    with manifest_path.open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, allow_nan=False)
        handle.write("\n")

    return {
        "ok": True,
        "output_dir": str(output_dir),
        "files": file_records,
        "manifest": str(manifest_path),
        "preflight": preflight,
    }


def main() -> int:
    try:
        raw_text = sys.stdin.read()
        raw = json.loads(raw_text) if raw_text.strip() else {}
        result = execute(parse_config(raw))
        print(json.dumps(result, allow_nan=False))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
