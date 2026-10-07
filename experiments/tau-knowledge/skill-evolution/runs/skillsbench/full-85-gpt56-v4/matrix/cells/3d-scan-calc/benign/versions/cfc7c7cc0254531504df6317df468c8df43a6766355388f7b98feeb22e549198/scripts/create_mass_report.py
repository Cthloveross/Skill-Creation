#!/usr/bin/env python3
"""JSON-stdin entrypoint for binary STL main-part mass reports.

Input: {"stl_path": str, "density_table_path": str, "output_path": str,
        optional "tolerance": positive number}
Output on stdout and at output_path: {"main_part_mass": number, "material_id": int}
"""
import json
import math
import os
import sys

from stl_mass import MassInputError, calculate


def validate_report(value):
    if not isinstance(value, dict) or set(value) != {"main_part_mass", "material_id"}:
        raise MassInputError("report schema is not exactly main_part_mass and material_id")
    mass, material = value["main_part_mass"], value["material_id"]
    if isinstance(mass, bool) or not isinstance(mass, (int, float)) or not math.isfinite(mass) or mass < 0:
        raise MassInputError("main_part_mass must be a finite nonnegative JSON number")
    if isinstance(material, bool) or not isinstance(material, int):
        raise MassInputError("material_id must be an integer")


def main():
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise MassInputError("stdin must contain a JSON object")
        required = {"stl_path", "density_table_path", "output_path"}
        missing = required - set(request)
        if missing:
            raise MassInputError("missing required input keys: " + ", ".join(sorted(missing)))
        if not all(isinstance(request[key], str) and request[key] for key in required):
            raise MassInputError("input paths must be nonempty strings")
        result = calculate(request["stl_path"], request["density_table_path"], request.get("tolerance"))
        validate_report(result)
        output_path = request["output_path"]
        parent = os.path.dirname(os.path.abspath(output_path))
        if not os.path.isdir(parent):
            raise MassInputError("output directory does not exist: " + parent)
        with open(output_path, "w", encoding="utf-8") as handle:
            json.dump(result, handle, allow_nan=False, indent=2)
            handle.write("\n")
        # Reopen rather than trusting the in-memory object.
        with open(output_path, "r", encoding="utf-8") as handle:
            persisted = json.load(handle)
        validate_report(persisted)
        json.dump(persisted, sys.stdout, allow_nan=False)
        sys.stdout.write("\n")
    except (OSError, ValueError, TypeError, json.JSONDecodeError, MassInputError) as exc:
        sys.stderr.write("mass report error: " + str(exc) + "\n")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
