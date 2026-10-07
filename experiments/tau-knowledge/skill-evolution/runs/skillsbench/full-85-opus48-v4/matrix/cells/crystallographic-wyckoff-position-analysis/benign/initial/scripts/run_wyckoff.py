#!/usr/bin/env python3
"""Run the written deliverable's entry function for local verification.

stdin one of:
  {"filepath": "/root/cif_files/X.cif"}        -> {"result": {...}}
  {"all": true, "dir": "/root/cif_files"}      -> {"results": {name: {...}}}
optional "solution": path to solution.py (default /root/workspace/solution.py).
Each per-file result adds diagnostics: n_atoms, site_total_ok, letters.
"""
import glob
import importlib.util
import json
import os
import sys


def load_fn(path):
    spec = importlib.util.spec_from_file_location("solution_mod", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.analyze_wyckoff_position_multiplicities_and_coordinates


def _diagnose(result, filepath):
    try:
        from pymatgen.core import Structure
        n = len(Structure.from_file(filepath))
    except Exception:
        n = None
    mult = result.get("wyckoff_multiplicity_dict", {})
    coords = result.get("wyckoff_coordinates_dict", {})
    total = sum(mult.values()) if mult else None
    result = dict(result)
    result["n_atoms"] = n
    result["site_total_ok"] = (n is not None and total == n)
    result["letters_match"] = sorted(mult.keys()) == sorted(coords.keys())
    return result


def main() -> None:
    payload = json.loads(sys.stdin.read() or "{}")
    sol = payload.get("solution", "/root/workspace/solution.py")
    fn = load_fn(sol)

    if payload.get("all"):
        root = payload.get("dir", "/root/cif_files")
        results = {}
        for path in sorted(glob.glob(os.path.join(root, "*.cif"))):
            name = os.path.basename(path)
            try:
                results[name] = _diagnose(fn(path), path)
            except Exception as exc:
                results[name] = {"error": str(exc)}
        print(json.dumps({"results": results}, indent=2))
        return

    filepath = payload["filepath"]
    print(json.dumps({"result": _diagnose(fn(filepath), filepath)}, indent=2))


if __name__ == "__main__":
    main()
