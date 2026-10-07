#!/usr/bin/env python3
"""Solve one PDDL instance and write only a replay-valid plan."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from fd_setup import ensure_fast_downward
from pddl_engine import PDDLError, load, parse_plan_text, render, validate


def _command(executable, domain, problem, output):
    prefix = [sys.executable, executable] if executable.lower().endswith(".py") else [executable]
    return prefix + ["--alias", "seq-sat-lama-2011", domain, problem, "--plan-file", output]


def _read_candidate(directory, preferred):
    candidates = [Path(preferred)]
    candidates.extend(sorted(Path(directory).glob("plan.txt.*"), key=lambda path: path.stat().st_mtime, reverse=True))
    for path in candidates:
        if path.is_file() and path.stat().st_size:
            try:
                return parse_plan_text(path.read_text(encoding="utf-8")), None
            except (OSError, PDDLError) as exc:
                return None, "planner output could not be parsed: %s" % exc
    return None, None


def _external(domain, problem, executable, timeout):
    with tempfile.TemporaryDirectory(prefix="airport-plan-") as directory:
        candidate = os.path.join(directory, "plan.txt")
        process = None
        transcript = ""
        try:
            process = subprocess.Popen(_command(executable, domain, problem, candidate), text=True,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                stdout, stderr = process.communicate(timeout=max(1, int(timeout)))
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    stdout, stderr = process.communicate(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    stdout, stderr = process.communicate()
            transcript = (stderr or stdout or "")[-700:]
        except OSError as exc:
            return None, "planner invocation failed: %s" % exc
        plan, parse_error = _read_candidate(directory, candidate)
        if plan is not None:
            return plan, "Fast Downward"
        if parse_error:
            return None, parse_error
        return None, "planner produced no plan: " + transcript.strip()


def _validate_existing(domain, problem, path):
    try:
        plan = parse_plan_text(Path(path).read_text(encoding="utf-8"))
    except (OSError, PDDLError) as exc:
        return False, 0, "plan read failed: %s" % exc
    ok, why, _ = validate(domain, problem, plan)
    return ok, len(plan), why


def solve(spec):
    domain_path, problem_path = spec.get("domain"), spec.get("problem")
    if not isinstance(domain_path, str) or not isinstance(problem_path, str):
        return {"ok": False, "valid": False, "error": "domain and problem paths are required"}
    try:
        domain, problem = load(domain_path, problem_path)
    except (OSError, PDDLError) as exc:
        return {"ok": False, "valid": False, "error": "PDDL load failed: %s" % exc}
    if spec.get("validate_plan"):
        ok, count, why = _validate_existing(domain, problem, spec["validate_plan"])
        return {"ok": ok, "valid": ok, "actions": count, "error": None if ok else why}
    executable = spec.get("fast_downward")
    setup_note = None
    if not executable:
        executable, setup_note = ensure_fast_downward(timeout=int(spec.get("planner_setup_timeout_sec", 150)))
    if not executable:
        return {"ok": False, "valid": False, "error": setup_note or "Fast Downward unavailable"}
    plan, method = _external(domain_path, problem_path, executable, spec.get("timeout_sec", 20))
    if plan is None:
        return {"ok": False, "valid": False, "error": method, "setup": setup_note}
    ok, why, _ = validate(domain, problem, plan)
    if not ok:
        return {"ok": False, "valid": False, "error": "external plan rejected: " + why, "setup": setup_note}
    output = spec.get("plan_output")
    if not isinstance(output, str) or not output:
        return {"ok": False, "valid": False, "error": "plan_output is required when solving"}
    try:
        target = Path(output)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".tmp")
        temporary.write_text(render(plan), encoding="utf-8")
        os.replace(temporary, target)
    except OSError as exc:
        return {"ok": False, "valid": False, "error": "cannot write plan: %s" % exc}
    return {"ok": True, "valid": True, "actions": len(plan), "method": method,
            "plan_output": output, "setup": setup_note}


def main():
    try:
        print(json.dumps(solve(json.load(sys.stdin))))
    except Exception as exc:
        print(json.dumps({"ok": False, "valid": False, "error": "unexpected solver error: %s" % exc}))


if __name__ == "__main__":
    main()
