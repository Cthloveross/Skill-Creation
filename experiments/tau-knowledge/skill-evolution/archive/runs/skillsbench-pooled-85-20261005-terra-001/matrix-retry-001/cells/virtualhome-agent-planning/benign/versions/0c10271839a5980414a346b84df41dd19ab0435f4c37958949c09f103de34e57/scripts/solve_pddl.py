#!/usr/bin/env python3
"""JSON stdin -> JSON stdout: solve or validate one PDDL task."""
import json, os, shutil, subprocess, sys, tempfile
from pathlib import Path
from pddl_engine import PDDLError, fallback_search, load, parse_plan_text, render, validate

def candidates(requested):
    values = [requested, os.environ.get("FAST_DOWNWARD"), shutil.which("fast-downward.py"), shutil.which("fast-downward")]
    values += ["/opt/fast-downward/fast-downward.py", "/root/fast-downward/fast-downward.py", "/app/fast-downward/fast-downward.py"]
    seen = set()
    return [x for x in values if x and os.path.exists(x) and not (x in seen or seen.add(x))]

def external(domain_path, problem_path, executable, timeout):
    with tempfile.TemporaryDirectory(prefix="airport-plan-") as td:
        output = os.path.join(td, "plan.txt")
        command = [executable, "--alias", "seq-sat-lama-2011", domain_path, problem_path, "--plan-file", output]
        try:
            done = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc: return None, "planner unavailable: %s" % exc
        if not os.path.isfile(output): return None, "planner produced no plan (exit %s)" % done.returncode
        try: return parse_plan_text(Path(output).read_text(encoding="utf-8")), "Fast Downward"
        except PDDLError as exc: return None, "planner plan parse failed: %s" % exc

def solve(spec):
    domain_path, problem_path = spec.get("domain"), spec.get("problem")
    if not isinstance(domain_path, str) or not isinstance(problem_path, str): return {"ok": False, "error": "domain and problem paths are required"}
    try: domain, problem = load(domain_path, problem_path)
    except (OSError, PDDLError) as exc: return {"ok": False, "error": "PDDL load failed: %s" % exc}
    if spec.get("validate_plan"):
        try: plan = parse_plan_text(Path(spec["validate_plan"]).read_text(encoding="utf-8"))
        except (OSError, PDDLError) as exc: return {"ok": False, "error": "plan read failed: %s" % exc}
        ok, why, _ = validate(domain, problem, plan)
        return {"ok": ok, "valid": ok, "actions": len(plan), "error": None if ok else why}
    notes, plan, method = [], None, None
    if spec.get("use_external", True):
        for fd in candidates(spec.get("fast_downward")):
            candidate, note = external(domain_path, problem_path, fd, int(spec.get("timeout_sec", 300)))
            if candidate is None: notes.append(note); continue
            ok, why, _ = validate(domain, problem, candidate)
            if ok: plan, method = candidate, note; break
            notes.append("external candidate rejected: " + why)
    if plan is None:
        try: plan, method = fallback_search(domain, problem, int(spec.get("max_states", 250000))), "bounded fallback"
        except PDDLError as exc: return {"ok": False, "error": str(exc), "notes": notes}
    ok, why, _ = validate(domain, problem, plan)
    if not ok: return {"ok": False, "error": "internal replay failed: " + why, "notes": notes}
    output, text = spec.get("plan_output"), render(plan)
    if output:
        try:
            target = Path(output); target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(target.name + ".tmp")
            temporary.write_text(text, encoding="utf-8"); os.replace(temporary, target)
        except OSError as exc: return {"ok": False, "error": "cannot write plan: %s" % exc, "notes": notes}
    return {"ok": True, "valid": True, "actions": len(plan), "method": method, "plan_output": output, "notes": notes}

def main():
    try: print(json.dumps(solve(json.load(sys.stdin))))
    except Exception as exc: print(json.dumps({"ok": False, "error": "unexpected solver error: %s" % exc}))
if __name__ == "__main__": main()
