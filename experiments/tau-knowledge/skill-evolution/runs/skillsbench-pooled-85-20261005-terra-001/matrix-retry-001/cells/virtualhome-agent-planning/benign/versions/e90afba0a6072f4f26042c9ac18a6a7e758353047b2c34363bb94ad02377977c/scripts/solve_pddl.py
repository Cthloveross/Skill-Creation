#!/usr/bin/env python3
"""Solve or replay-validate a single PDDL instance; JSON stdin/stdout interface."""
import json, os, signal, subprocess, sys, tempfile
from pathlib import Path
from fd_setup import build_for, ensure_fast_downward
from pddl_engine import PDDLError, load, parse_plan_text, render, validate

def planner_command(wrapper, build, domain, problem, plan_path):
    command = [sys.executable, wrapper] if wrapper.lower().endswith(".py") else [wrapper]
    if build:
        command += ["--build", build]
    return command + ["--alias", "lama-first", domain, problem, "--plan-file", plan_path]

def invoke(domain, problem, wrapper, build, seconds):
    with tempfile.TemporaryDirectory(prefix="airport-plan-") as folder:
        target = str(Path(folder) / "plan")
        try:
            proc = subprocess.Popen(planner_command(wrapper, build, domain, problem, target), stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, text=True, start_new_session=True)
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
        candidates = [Path(target)] + sorted(Path(folder).glob("plan.*"), key=lambda p: p.stat().st_mtime, reverse=True)
        for candidate in candidates:
            if candidate.is_file() and candidate.stat().st_size:
                try:
                    return parse_plan_text(candidate.read_text(encoding="utf8")), "Fast Downward lama-first"
                except PDDLError as exc:
                    return None, "planner plan parse failure: %s" % exc
        detail = (stderr or stdout or "").strip()[-700:]
        return None, "planner produced no plan: " + detail

def solve(request):
    if not isinstance(request.get("domain"), str) or not isinstance(request.get("problem"), str):
        return {"ok": False, "valid": False, "error": "domain and problem are required"}
    try:
        domain, problem = load(request["domain"], request["problem"])
    except (OSError, PDDLError) as exc:
        return {"ok": False, "valid": False, "error": "PDDL load failed: %s" % exc}
    if request.get("validate_plan"):
        try:
            plan = parse_plan_text(Path(request["validate_plan"]).read_text(encoding="utf8"))
        except (OSError, PDDLError) as exc:
            return {"ok": False, "valid": False, "error": "plan read failed: %s" % exc}
        ok, reason, _ = validate(domain, problem, plan)
        return {"ok": ok, "valid": ok, "actions": len(plan), "error": None if ok else reason}
    wrapper = request.get("fast_downward")
    setup_note = None
    if not wrapper and not request.get("no_setup"):
        wrapper, setup_note = ensure_fast_downward(timeout=int(request.get("planner_setup_timeout_sec", 300)))
    if not wrapper:
        return {"ok": False, "valid": False, "error": setup_note or "Fast Downward unavailable"}
    plan, method = invoke(request["domain"], request["problem"], wrapper,
                          request.get("fast_downward_build", build_for(wrapper)), request.get("timeout_sec", 30))
    if plan is None:
        return {"ok": False, "valid": False, "error": method}
    ok, reason, _ = validate(domain, problem, plan)
    if not ok:
        return {"ok": False, "valid": False, "error": "external plan rejected: " + reason}
    output = request.get("plan_output")
    if not isinstance(output, str) or not output:
        return {"ok": False, "valid": False, "error": "plan_output is required"}
    try:
        final = Path(output); final.parent.mkdir(parents=True, exist_ok=True)
        temporary = final.with_name(final.name + ".tmp")
        temporary.write_text(render(plan), encoding="utf8")
        os.replace(temporary, final)
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
