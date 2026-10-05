#!/usr/bin/env python3
"""Validate a generated Wyckoff solution against a supplied CIF.

Input JSON:
  {"solution_path": "/root/workspace/solution.py", "cif_path": "/path/input.cif"}
Output JSON:
  {"valid": true, "site_count": N, "output": {...}}
  or {"valid": false, "error": "..."}
"""

import importlib.util
import json
import os
import sys
from fractions import Fraction
from pathlib import Path
from typing import Any


def _load_module(solution_path: str) -> Any:
    spec = importlib.util.spec_from_file_location("wyckoff_solution_under_test", solution_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot import solution module at {solution_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _check_rational(text: Any) -> None:
    if not isinstance(text, str) or not text:
        raise AssertionError("Each coordinate must be a non-empty rational string")
    value = Fraction(text)
    if value.denominator > 12:
        raise AssertionError(f"Coordinate {text!r} exceeds denominator bound 12")


def validate(solution_path: str, cif_path: str) -> dict:
    if not os.path.isfile(solution_path):
        raise FileNotFoundError(solution_path)
    if not os.path.isfile(cif_path):
        raise FileNotFoundError(cif_path)

    module = _load_module(solution_path)
    function = getattr(module, "analyze_wyckoff_position_multiplicities_and_coordinates", None)
    if not callable(function):
        raise AssertionError("Required entrypoint is missing or not callable")
    result = function(cif_path)

    if not isinstance(result, dict):
        raise AssertionError("Entrypoint must return a dictionary")
    required = {"wyckoff_multiplicity_dict", "wyckoff_coordinates_dict"}
    if set(result) != required:
        raise AssertionError("Result must contain exactly the two required dictionaries")
    multiplicities = result["wyckoff_multiplicity_dict"]
    coordinates = result["wyckoff_coordinates_dict"]
    if not isinstance(multiplicities, dict) or not isinstance(coordinates, dict):
        raise AssertionError("Both required result values must be dictionaries")
    if set(multiplicities) != set(coordinates):
        raise AssertionError("Multiplicity and coordinate Wyckoff keys must match")
    if not multiplicities:
        raise AssertionError("A nonempty CIF must produce at least one Wyckoff key")

    for letter, multiplicity in multiplicities.items():
        if not isinstance(letter, str) or not letter.isalpha():
            raise AssertionError("Wyckoff keys must be letter strings")
        if isinstance(multiplicity, bool) or not isinstance(multiplicity, int) or multiplicity <= 0:
            raise AssertionError("Each multiplicity must be a positive integer")
        coordinate = coordinates[letter]
        if not isinstance(coordinate, list) or len(coordinate) != 3:
            raise AssertionError("Each Wyckoff coordinate must be a three-item list")
        for component in coordinate:
            _check_rational(component)

    from pymatgen.core import Structure
    source_structure = Structure.from_file(cif_path, primitive=False)
    site_count = len(source_structure)
    if sum(multiplicities.values()) != site_count:
        raise AssertionError("Reported multiplicities do not reconcile with parsed source sites")

    return {"valid": True, "site_count": site_count, "output": result}


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("Input must be a JSON object")
        solution_path = payload.get("solution_path", "/root/workspace/solution.py")
        cif_path = payload["cif_path"]
        if not isinstance(solution_path, str) or not isinstance(cif_path, str):
            raise ValueError("solution_path and cif_path must be strings")
        print(json.dumps(validate(solution_path, cif_path), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"valid": False, "error": f"{type(exc).__name__}: {exc}"}, sort_keys=True))


if __name__ == "__main__":
    main()
