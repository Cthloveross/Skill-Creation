#!/usr/bin/env python3
"""Validate an existing mass_report.json by recomputing from the STL and table.

Reads a JSON object from stdin and emits JSON on stdout. It does not rewrite the
report artifact.
"""

from __future__ import annotations

import json
import math
import os
import sys
import traceback

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from stl_mass_core import calculate_mass  # noqa: E402


def main() -> int:
    try:
        raw = sys.stdin.read().strip()
        config = json.loads(raw) if raw else {}
        if not isinstance(config, dict):
            raise ValueError("stdin JSON must be an object")
        report_path = str(config.get("report_path") or config.get("output_path") or "/root/mass_report.json")
        rel_tol = float(config.get("relative_tolerance", 1.0e-9))
        if rel_tol < 0 or not math.isfinite(rel_tol):
            raise ValueError("relative_tolerance must be a finite non-negative number")

        computed = calculate_mass(config)
        expected = computed["report"]
        with open(report_path, "r", encoding="utf-8") as f:
            observed = json.load(f)

        obs_mass = float(observed["main_part_mass"])
        exp_mass = float(expected["main_part_mass"])
        obs_mid = int(observed["material_id"])
        exp_mid = int(expected["material_id"])
        rel_diff = abs(obs_mass - exp_mass) / max(abs(exp_mass), 1.0)
        ok = obs_mid == exp_mid and math.isfinite(obs_mass) and rel_diff <= rel_tol

        payload = {
            "status": "ok" if ok else "mismatch",
            "report_path": report_path,
            "observed": {"main_part_mass": obs_mass, "material_id": obs_mid},
            "computed": expected,
            "relative_mass_difference": rel_diff,
            "relative_tolerance": rel_tol,
            "material_id_matches": obs_mid == exp_mid,
            "diagnostics": computed["diagnostics"],
        }
        print(json.dumps(payload, indent=2, sort_keys=False))
        return 0 if ok else 1
    except Exception as exc:  # pragma: no cover - entrypoint safety
        payload = {
            "status": "error",
            "error_type": exc.__class__.__name__,
            "error": str(exc),
        }
        if os.environ.get("SKILL_DEBUG_TRACEBACK"):
            payload["traceback"] = traceback.format_exc()
        print(json.dumps(payload, indent=2, sort_keys=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())
