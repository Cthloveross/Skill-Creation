#!/usr/bin/env python3
"""Solve or validate one classical PDDL task. JSON stdin -> JSON stdout."""
import json, os, shutil, subprocess, sys, tempfile
from pathlib import Path
from pddl_engine import PDDLError, fallback_search, load, parse_plan_text, render, validate

def _fd_candidates(requested):
    if requested: return [requested]
    return [x for x in (os.environ.get("FAST_DOWNWARD"), shutil.which("fast-downward.py"), shutil.which("fast-downward")) if x]

def _external(domain_path, problem_path, fd, timeout):
    with tempfile.TemporaryDirectory(prefix="pddl-plan-") as td:
        plan_path = os.path.join(td, "plan.txt")
        cmd = [fd, "--alias", "seq-sat-lama-2011", domain_path, problem_path, "--plan-file", plan_path]
        try:
            completed = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       timeout=timeout, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return None, "external planner unavailable: %s" % exc
        if not os.path.exists(plan_path):
            return None, "external planner produced no plan (exit %s)" % completed.returncode
        return parse_plan_text(Path(plan_path).read_text(encoding="utf-8")), "external planner"

def solve(spec):
    domain_path, problem_path = spec.get("domain"), spec.get("problem")
    if not isinstance(domain_path, str) or not isinstance(problem_path, str):
        return {"ok": False, "error": "domain and problem string paths are required"}
    try:
        domain, problem = load(domain_path, problem_path)
    except (OSError, PDDLError) as exc:
        return {"ok": False, "error": "PDDL load failed: %s" % exc}
    if spec.get("validate_plan"):
        try: plan = parse_plan_text(Path(spec["validate_plan"]).read_text(encoding="utf-8"))
        except (OSError, PDDLError) as exc: return {"ok": False, "error": "plan read failed: %s" % exc}
        ok, why, _ = validate(domain, problem, plan)
        return {"ok": ok, "valid": ok, "actions": len(plan), "error": None if ok else why}
    plan = None; method = None; notes = []
    if spec.get("use_external", True):
        for fd in _fd_candidates(spec.get("fast_downward")):
            try: candidate, detail = _external(domain_path, problem_path, fd, int(spec.get("timeout_sec", 300)))
            except PDDLError as exc: candidate, detail = None, "bad external plan: %s" % exc
            if candidate is not None:
                ok, why, _ = validate(domain, problem, candidate)
                if ok: plan, method = candidate, detail; break
                notes.append("external plan rejected: " + why)
            else: notes.append(detail)
    if plan is None:
        try:
            plan = fallback_search(domain, problem, int(spec.get("max_states", 250000))); method = "fallback greedy best-first"
        except PDDLError as exc:
            return {"ok": False, "error": str(exc), "notes": notes}
    ok, why, _ = validate(domain, problem, plan)
    if not ok: return {"ok": False, "error": "internal validation failed: " + why, "notes": notes}
    text = render(plan)
    output = spec.get("plan_output")
    if output:
        try:
            Path(output).parent.mkdir(parents=True, exist_ok=True)
            Path(output).write_text(text, encoding="utf-8")
        except OSError as exc: return {"ok": False, "error": "cannot write plan: %s" % exc}
    return {"ok": True, "valid": True, "method": method, "actions": len(plan), "plan_output": output,
            "plan_text": text, "notes": notes}

def main():
    try: print(json.dumps(solve(json.load(sys.stdin))))
    except Exception as exc: print(json.dumps({"ok": False, "error": "unexpected solver error: %s" % exc}))
if __name__ == "__main__": main()
