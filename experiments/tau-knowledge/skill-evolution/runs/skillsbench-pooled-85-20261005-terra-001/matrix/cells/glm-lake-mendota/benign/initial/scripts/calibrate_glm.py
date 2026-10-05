#!/usr/bin/env python3
"""Run bounded, reproducible GLM temperature calibration from JSON stdin."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

from glm_common import parse_datetime, validate_output


# GLM namelist assignments are scalar in the fields this script changes.
_ASSIGNMENT = r"(?im)^(\s*{key}\s*=\s*)([^,!\n/]+)"


def numeric_value(text: str, key: str) -> float | None:
    match = re.search(_ASSIGNMENT.format(key=re.escape(key)), text)
    if not match:
        return None
    raw = match.group(2).strip().strip("'\"").replace("D", "E").replace("d", "e")
    try:
        return float(raw)
    except ValueError:
        return None


def format_namelist_value(value: Any) -> str:
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    return format(float(value), ".10g")


def replace_or_insert(text: str, key: str, value: Any, group: str | None = None) -> str:
    pattern = re.compile(_ASSIGNMENT.format(key=re.escape(key)))
    replacement = r"\1" + format_namelist_value(value)
    if pattern.search(text):
        return pattern.sub(replacement, text, count=1)
    if group:
        group_match = re.search(r"(?im)^\s*&" + re.escape(group) + r"\b[^\n]*", text)
        if group_match:
            pos = group_match.end()
            return text[:pos] + "\n  " + key + " = " + format_namelist_value(value) + "," + text[pos:]
    raise ValueError("namelist has no %s assignment%s" % (key, " in &" + group if group else ""))


def patch_config(base: str, updates: Dict[str, Any]) -> str:
    text = base
    for key, value in updates.items():
        group = "output" if key in ("out_dir", "out_fn") else None
        text = replace_or_insert(text, key, value, group)
    return text


def clean_output_directory(output_path: Path) -> None:
    directory = output_path.parent.resolve()
    if str(directory) in ("/", ".") or len(directory.parts) < 2:
        raise ValueError("refusing to clean unsafe output directory: %s" % directory)
    if directory.exists():
        shutil.rmtree(directory)
    directory.mkdir(parents=True, exist_ok=True)


def run_one(executable: str, config_path: Path, output_path: Path, text: str, request: Dict[str, Any], log_dir: Path, label: str) -> Dict[str, Any]:
    config_path.write_text(text, encoding="utf-8")
    clean_output_directory(output_path)
    started = time.monotonic()
    try:
        completed = subprocess.run(
            [executable], cwd=str(config_path.parent), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=float(request.get("timeout_sec", 500)), check=False,
        )
        returncode = completed.returncode
        stdout, stderr = completed.stdout, completed.stderr
    except subprocess.TimeoutExpired as exc:
        returncode = None
        stdout = exc.stdout or ""
        stderr = (exc.stderr or "") + "\nGLM timed out"
    duration = time.monotonic() - started
    (log_dir / (label + ".stdout.txt")).write_text(stdout, encoding="utf-8", errors="replace")
    (log_dir / (label + ".stderr.txt")).write_text(stderr, encoding="utf-8", errors="replace")
    status: Dict[str, Any] = {"label": label, "returncode": returncode, "duration_sec": round(duration, 3), "output_exists": output_path.is_file()}
    if returncode == 0 and output_path.is_file():
        status["validation"] = validate_output(str(output_path), request["observation_csv"], request["start"], request["stop"])
    else:
        status["validation"] = {"ok": False, "error": "GLM failed or did not create requested output"}
    return status


def candidate_groups(base: str, max_runs: int) -> List[Tuple[str, List[Dict[str, float]]]]:
    """Build bounded candidates only for physically meaningful existing parameters."""
    groups: List[Tuple[str, List[Dict[str, float]]]] = []
    at = numeric_value(base, "at_offset")
    if at is not None:
        groups.append(("air_temperature_offset", [{"at_offset": at + d} for d in (-2.0, -1.0, 1.0, 2.0)]))
    for key, label, factors in (
        ("sw_factor", "shortwave_factor", (0.80, 0.90, 1.10, 1.20)),
        ("wind_factor", "wind_factor", (0.65, 0.80, 1.20, 1.40)),
    ):
        value = numeric_value(base, key)
        if value is not None:
            groups.append((label, [{key: value * factor} for factor in factors]))
    mixing_keys = [k for k in ("coef_mix_conv", "coef_wind_stir", "coef_mix_shear", "coef_mix_turb", "coef_mix_KH", "coef_mix_hyp") if numeric_value(base, k) is not None]
    if mixing_keys:
        current = {k: numeric_value(base, k) for k in mixing_keys}
        groups.append(("mixing_coefficients", [{k: float(current[k]) * factor for k in mixing_keys} for factor in (0.65, 0.80, 1.20, 1.40)]))
    # max_runs is enforced by the caller; this routine intentionally has no hidden model runs.
    return groups


def main() -> None:
    try:
        request = json.load(sys.stdin)
        required = ("executable", "config_path", "observation_csv", "output_path", "start", "stop")
        missing = [k for k in required if not request.get(k)]
        if missing:
            raise ValueError("missing required keys: " + ", ".join(missing))
        config_path = Path(request["config_path"]).resolve()
        output_path = Path(request["output_path"]).resolve()
        executable = str(Path(request["executable"]).resolve())
        if config_path.name != "glm3.nml":
            raise ValueError("config_path must be named glm3.nml because GLM is invoked using its standard namelist lookup")
        if not config_path.is_file() or not Path(request["observation_csv"]).is_file() or not Path(executable).is_file():
            raise ValueError("executable, config_path, and observation_csv must all be existing files")
        parse_datetime(request["start"])
        parse_datetime(request["stop"])
        if parse_datetime(request["stop"]) < parse_datetime(request["start"]):
            raise ValueError("stop precedes start")
        max_runs = int(request.get("max_runs", 24))
        if max_runs < 1:
            raise ValueError("max_runs must be at least one")
        base = config_path.read_text(encoding="utf-8")
        # Make the required period and output location part of every candidate configuration.
        fixed: Dict[str, Any] = {
            "start": str(request["start"]), "stop": str(request["stop"]),
            "out_dir": str(output_path.parent), "out_fn": output_path.stem,
        }
        base_with_fixed = patch_config(base, fixed)
        log_dir = config_path.parent / "glm_calibration_runs"
        log_dir.mkdir(parents=True, exist_ok=True)
        runs: List[Dict[str, Any]] = []
        best_changes: Dict[str, float] = {}
        best_rmse: float | None = None

        baseline = run_one(executable, config_path, output_path, base_with_fixed, request, log_dir, "run_000_baseline")
        runs.append(baseline)
        valid = baseline["validation"]
        if valid.get("ok") and valid["coverage"].get("contains_requested_bounds"):
            best_rmse = float(valid["rmse_celsius"])
        run_number = 1

        # Coordinate search: each group is changed while earlier accepted groups remain fixed.
        for group_name, candidates in candidate_groups(base_with_fixed, max_runs):
            if run_number >= max_runs:
                break
            group_best_changes = None
            group_best_rmse = best_rmse
            for candidate in candidates:
                if run_number >= max_runs:
                    break
                changes = dict(best_changes)
                changes.update(candidate)
                text = patch_config(base_with_fixed, changes)
                label = "run_%03d_%s" % (run_number, group_name)
                status = run_one(executable, config_path, output_path, text, request, log_dir, label)
                status["parameter_changes"] = changes
                runs.append(status)
                run_number += 1
                validation = status["validation"]
                if validation.get("ok") and validation.get("coverage", {}).get("contains_requested_bounds"):
                    score = float(validation["rmse_celsius"])
                    if group_best_rmse is None or score < group_best_rmse:
                        group_best_rmse, group_best_changes = score, changes
            if group_best_changes is not None:
                best_changes, best_rmse = group_best_changes, group_best_rmse

        # A clean reproduction run is mandatory: it is the only output retained for delivery.
        final_text = patch_config(base_with_fixed, best_changes)
        final_status = run_one(executable, config_path, output_path, final_text, request, log_dir, "final_reproduction")
        final_validation = final_status["validation"]
        target = float(request.get("rmse_target", 2.0))
        success = bool(final_status["returncode"] == 0 and final_validation.get("ok") and final_validation.get("coverage", {}).get("contains_requested_bounds") and float(final_validation.get("rmse_celsius", float("inf"))) < target)
        report = {
            "ok": success,
            "success": success,
            "rmse_target_celsius": target,
            "selected_parameter_changes": best_changes,
            "best_candidate_rmse_celsius": best_rmse,
            "final_run": final_status,
            "final_validation": final_validation,
            "runs": runs,
            "config_path": str(config_path),
            "output_path": str(output_path),
            "log_directory": str(log_dir),
        }
        report_path = config_path.parent / "glm_calibration_report.json"
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False), encoding="utf-8")
        report["report_path"] = str(report_path)
    except Exception as exc:
        report = {"ok": False, "success": False, "error": str(exc)}
    print(json.dumps(report, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
