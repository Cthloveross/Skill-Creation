#!/usr/bin/env python3
"""Solve or replay-check one PDDL problem through a JSON stdin/stdout interface."""
import json
import os
import signal
import subprocess
import sys
import tempfile
from pathlib import Path
from fd_setup import build_for, ensure_fast_downward
from pddl_engine import PDDLError, load, parse_plan_text, render, validate


def command(driver, profile, domain, problem, plan_file):
    head = [sys.executable, driver] if driver.lower().endswith(".py") else [driver]
    if profile:
        head += ["--build", profile]
    return head + ["--plan-file", plan_file, "--alias", "lama-first", domain, problem]


def invoke(domain, problem, driver, profile, seconds):
    with tempfile.TemporaryDirectory(prefix="airport-plan-") as folder:
        plan_file = str(Path(folder) / "sas_plan")
        try:
            proc = subprocess.Popen(command(driver, profile, domain, problem, plan_file), text=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
            try:
                stdout, stderr = proc.communicate(timeout=max(1, int(seconds)))
            except subprocess.TimeoutExpired:
                try: os.killpg(proc.pid, signal.SIGTERM)
                except OSError: proc.terminate()
                try: stdout, stderr = proc.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    try: os.killpg(proc.pid, signal.SIGKILL)
                    except OSError: proc.kill()
                    stdout, stderr = proc.communicate()
        except OSError as exc:
            return None, "planner invocation failed: %s" % exc
        candidates = [Path(plan_file)] + sorted(Path(folder).glob("sas_plan.*"), key=lambda p: p.stat().st_mtime, reverse=True)
        for candidate in candidates:
            if candidate.is_file() and candidate.stat().st_size:
                try:
                    return parse_plan_text(candidate.read_text(encoding="utf8")), "Fast Downward lama-first"
                except PDDLError as exc:
                    return None, "planner emitted an unreadable plan: %s" % exc
        detail = (stderr or stdout or "").strip()[-1000:]
        return None, "planner produced no plan" + (": " + detail if detail else "")


def _commit(output, plan):
    final = Path(output); final.parent.mkdir(parents=True, exist_ok=True)
    temporary = final.with_name(final.name + ".tmp")
    temporary.write_text(render(plan), encoding="utf8")
    os.replace(temporary, final)


def solve(request):
    if not isinstance(request.get("domain"), str) or not isinstance(request.get("problem"), str):
        return {"ok": False, "valid": False, "error": "domain and problem are required"}
    try:
        domain, problem = load(request["domain"], request["problem"])
    except (OSError, PDDLError) as exc:
        return {"ok": False, "valid": False, "error": "PDDL load failed: %s" % exc}
    if request.get("validate_plan"):
        try: plan = parse_plan_text(Path(request["validate_plan"]).read_text(encoding="utf8"))
        except (OSError, PDDLError) as exc: return {"ok": False, "valid": False, "error": "plan read failed: %s" % exc}
        ok, reason, _ = validate(domain, problem, plan)
        return {"ok": ok, "valid": ok, "actions": len(plan), "error": None if ok else reason}
    output = request.get("plan_output")
    if not isinstance(output, str) or not output:
        return {"ok": False, "valid": False, "error": "plan_output is required"}
    # A solved initial state needs no external planner, but still needs its required file.
    ok, _, _ = validate(domain, problem, [])
    if ok:
        try: _commit(output, [])
        except OSError as exc: return {"ok": False, "valid": False, "error": "cannot write plan: %s" % exc}
        return {"ok": True, "valid": True, "actions": 0, "method": "initial goal", "plan_output": output}
    driver = request.get("fast_downward")
    setup_error = None
    if not driver and not request.get("no_setup"):
        driver, profile_or_error = ensure_fast_downward(timeout=request.get("planner_setup_timeout_sec", 360))
        if driver: request["fast_downward_build"] = profile_or_error
        else: setup_error = profile_or_error
    if not driver:
        return {"ok": False, "valid": False, "error": setup_error or "Fast Downward unavailable"}
    plan, method = invoke(request["domain"], request["problem"], driver,
                          request.get("fast_downward_build", build_for(driver)), request.get("timeout_sec", 100))
    if plan is None:
        return {"ok": False, "valid": False, "error": method}
    ok, reason, _ = validate(domain, problem, plan)
    if not ok:
        return {"ok": False, "valid": False, "error": "external plan rejected: " + reason}
    try: _commit(output, plan)
    except OSError as exc: return {"ok": False, "valid": False, "error": "cannot write plan: %s" % exc}
    return {"ok": True, "valid": True, "actions": len(plan), "method": method, "plan_output": output}


def main():
    try: print(json.dumps(solve(json.load(sys.stdin))))
    except Exception as exc: print(json.dumps({"ok": False, "valid": False, "error": "unexpected solver error: %s" % exc}))

if __name__ == "__main__": main()
