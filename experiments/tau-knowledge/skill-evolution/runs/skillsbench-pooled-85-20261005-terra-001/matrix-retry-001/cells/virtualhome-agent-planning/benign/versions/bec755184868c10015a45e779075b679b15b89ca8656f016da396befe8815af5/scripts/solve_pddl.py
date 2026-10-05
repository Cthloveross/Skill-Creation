#!/usr/bin/env python3
"""Solve one instance with Fast Downward and write only a replay-valid plan."""
import json
import os
import signal
import subprocess
import sys
import tempfile
from pathlib import Path
from fd_setup import ensure_fast_downward
from pddl_engine import PDDLError, load, parse_plan_text, render, validate


def _cmd(exe, domain, problem, out):
    prefix = [sys.executable, exe] if exe.lower().endswith(".py") else [exe]
    return prefix + ["--alias", "lama-first", domain, problem, "--plan-file", out]


def _candidate(folder, preferred):
    paths = [Path(preferred)] + sorted(Path(folder).glob("plan.*"), key=lambda p: p.stat().st_mtime, reverse=True)
    seen = set()
    for path in paths:
        if str(path) in seen:
            continue
        seen.add(str(path))
        if path.is_file() and path.stat().st_size:
            try:
                return parse_plan_text(path.read_text(encoding="utf-8")), None
            except (OSError, PDDLError) as exc:
                return None, "planner plan parse failure: %s" % exc
    return None, None


def _stop(process):
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        process.terminate()


def _kill(process):
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        process.kill()


def _run(domain, problem, exe, seconds):
    with tempfile.TemporaryDirectory(prefix="airport-plan-") as folder:
        output = str(Path(folder) / "plan")
        try:
            process = subprocess.Popen(_cmd(exe, domain, problem, output), stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, text=True, start_new_session=True)
            try:
                out, err = process.communicate(timeout=max(1, int(seconds)))
            except subprocess.TimeoutExpired:
                _stop(process)
                try:
                    out, err = process.communicate(timeout=4)
                except subprocess.TimeoutExpired:
                    _kill(process)
                    out, err = process.communicate()
        except OSError as exc:
            return None, "planner invocation failed: %s" % exc
        plan, why = _candidate(folder, output)
        if plan is not None:
            return plan, "Fast Downward lama-first"
        return None, why or "planner produced no plan: " + ((err or out or "").strip()[-700:])


def solve(spec):
    if not isinstance(spec.get("domain"), str) or not isinstance(spec.get("problem"), str):
        return {"ok": False, "valid": False, "error": "domain and problem are required"}
    try:
        domain, problem = load(spec["domain"], spec["problem"])
    except (OSError, PDDLError) as exc:
        return {"ok": False, "valid": False, "error": "PDDL load failed: %s" % exc}

    if spec.get("validate_plan"):
        try:
            plan = parse_plan_text(Path(spec["validate_plan"]).read_text(encoding="utf-8"))
        except (OSError, PDDLError) as exc:
            return {"ok": False, "valid": False, "error": "plan read failed: %s" % exc}
        ok, why, _ = validate(domain, problem, plan)
        return {"ok": ok, "valid": ok, "actions": len(plan), "error": None if ok else why}

    exe = spec.get("fast_downward")
    note = None
    if not exe and not spec.get("no_setup"):
        exe, note = ensure_fast_downward(timeout=int(spec.get("planner_setup_timeout_sec", 250)))
    if not exe:
        return {"ok": False, "valid": False, "error": note or "Fast Downward unavailable"}
    plan, method = _run(spec["domain"], spec["problem"], exe, spec.get("timeout_sec", 20))
    if plan is None:
        return {"ok": False, "valid": False, "error": method}
    ok, why, _ = validate(domain, problem, plan)
    if not ok:
        return {"ok": False, "valid": False, "error": "external plan rejected: " + why}

    output = spec.get("plan_output")
    if not isinstance(output, str) or not output:
        return {"ok": False, "valid": False, "error": "plan_output is required"}
    try:
        target = Path(output)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".tmp")
        temporary.write_text(render(plan), encoding="utf-8")
        os.replace(temporary, target)
    except OSError as exc:
        return {"ok": False, "valid": False, "error": "cannot write plan: %s" % exc}
    return {"ok": True, "valid": True, "actions": len(plan), "method": method, "plan_output": output}


def main():
    try:
        print(json.dumps(solve(json.load(sys.stdin))))
    except Exception as exc:
        print(json.dumps({"ok": False, "valid": False, "error": "unexpected solver error: %s" % exc}))

if __name__ == "__main__":
    main()
