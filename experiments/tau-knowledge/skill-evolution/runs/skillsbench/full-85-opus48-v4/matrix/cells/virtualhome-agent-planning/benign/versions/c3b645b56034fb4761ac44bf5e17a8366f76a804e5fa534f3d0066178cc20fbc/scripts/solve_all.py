#!/usr/bin/env python3
"""Batch PDDL plan generator for airport ground-traffic tasks.

Stdin  (JSON): {"problem_json": str?, "base_dir": str?,
                "per_task_timeout": int?, "backend": "auto|fd|pyperplan"?}
Stdout (JSON): {"results": [...], "summary": {...}}

Side effect: writes each task's plan to its `plan_output` path in the
required `name(arg1, arg2, ...)` one-action-per-line format.
"""
import json
import os
import subprocess
import sys
import shutil
import tempfile


def eprint(*a):
    print(*a, file=sys.stderr)


def ensure_pyperplan():
    """Return True if pyperplan is importable (installing if needed)."""
    try:
        import pyperplan  # noqa: F401
        return True
    except Exception:
        pass
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet",
             "--disable-pip-version-check", "pyperplan"],
            check=False, timeout=300,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        eprint("pip install pyperplan failed:", e)
    try:
        import pyperplan  # noqa: F401
        return True
    except Exception:
        return False


def find_fd():
    """Return a runnable Fast Downward command prefix list, or None."""
    env = os.environ.get("FAST_DOWNWARD")
    if env and os.path.exists(env):
        return [env]
    for name in ("fast-downward.py", "fast-downward", "downward"):
        p = shutil.which(name)
        if p:
            return [p]
    return None


def parse_grounded_line(line):
    """Parse '(drive truck1 a b)' -> ('drive', ['truck1','a','b']) or None."""
    s = line.strip()
    if not s or not s.startswith("("):
        return None
    if s.endswith(")"):
        s = s[1:-1]
    else:
        s = s[1:]
    s = s.strip()
    if not s:
        return None
    toks = s.split()
    if not toks:
        return None
    return toks[0], toks[1:]


def to_required_format(actions):
    """actions: list of (name, [args]) -> list of 'name(a, b)' strings."""
    out = []
    for name, args in actions:
        out.append("%s(%s)" % (name, ", ".join(args)))
    return out


def read_plan_file(path):
    acts = []
    try:
        with open(path, "r") as f:
            for line in f:
                parsed = parse_grounded_line(line)
                if parsed is not None:
                    acts.append(parsed)
    except Exception:
        return []
    return acts


def solve_with_fd(fd_cmd, domain, problem, timeout):
    tmpdir = tempfile.mkdtemp(prefix="fdplan_")
    out = os.path.join(tmpdir, "plan")
    cmd = list(fd_cmd) + ["--alias", "lama-first",
                          "--plan-file", out, domain, problem]
    try:
        subprocess.run(cmd, timeout=timeout, cwd=tmpdir,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       check=False)
    except Exception:
        pass
    # FD may write out, out.1, out.2 (anytime). Prefer the highest suffix.
    cands = []
    if os.path.exists(out):
        cands.append(out)
    i = 1
    while os.path.exists("%s.%d" % (out, i)):
        cands.append("%s.%d" % (out, i))
        i += 1
    acts = []
    if cands:
        acts = read_plan_file(cands[-1])
    shutil.rmtree(tmpdir, ignore_errors=True)
    return acts


def solve_with_pyperplan(domain, problem, timeout):
    soln = problem + ".soln"
    try:
        if os.path.exists(soln):
            os.remove(soln)
    except Exception:
        pass
    cmd = [sys.executable, "-m", "pyperplan",
           "-H", "hff", "-s", "gbf", domain, problem]
    try:
        subprocess.run(cmd, timeout=timeout,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       check=False)
    except Exception:
        pass
    if os.path.exists(soln):
        return read_plan_file(soln)
    return []


def solve_task(domain, problem, timeout, backend, fd_cmd, have_pyperplan):
    order = []
    if backend == "fd":
        order = ["fd"]
    elif backend == "pyperplan":
        order = ["pyperplan"]
    else:  # auto
        if fd_cmd:
            order.append("fd")
        order.append("pyperplan")
    for b in order:
        if b == "fd" and fd_cmd:
            acts = solve_with_fd(fd_cmd, domain, problem, timeout)
            if acts:
                return acts, "fd"
        elif b == "pyperplan" and have_pyperplan:
            acts = solve_with_pyperplan(domain, problem, timeout)
            if acts:
                return acts, "pyperplan"
    return [], "none"


def resolve(base_dir, p):
    if os.path.isabs(p):
        return p
    return os.path.normpath(os.path.join(base_dir, p))


def main():
    try:
        raw = sys.stdin.read()
        cfg = json.loads(raw) if raw.strip() else {}
    except Exception:
        cfg = {}
    problem_json = cfg.get("problem_json", "/app/problem.json")
    per_task_timeout = int(cfg.get("per_task_timeout", 120))
    backend = cfg.get("backend", "auto")

    if not os.path.exists(problem_json):
        print(json.dumps({"results": [],
                          "summary": {"total": 0, "solved": 0,
                                      "empty": 0, "error": 1},
                          "detail": "manifest not found: " + problem_json}))
        return

    base_dir = cfg.get("base_dir") or os.path.dirname(
        os.path.abspath(problem_json))

    with open(problem_json) as f:
        manifest = json.load(f)
    if isinstance(manifest, dict):
        manifest = [manifest]

    fd_cmd = find_fd() if backend in ("auto", "fd") else None
    have_pyperplan = False
    if backend in ("auto", "pyperplan"):
        have_pyperplan = ensure_pyperplan()

    results = []
    for item in manifest:
        tid = item.get("id")
        dom = item.get("domain")
        prob = item.get("problem")
        out = item.get("plan_output")
        rec = {"id": tid, "plan_output": out, "status": "error",
               "num_actions": 0, "backend": "none", "detail": ""}
        if not (dom and prob and out):
            rec["detail"] = "missing domain/problem/plan_output"
            results.append(rec)
            continue
        dom_p = resolve(base_dir, dom)
        prob_p = resolve(base_dir, prob)
        out_p = resolve(base_dir, out)
        if not os.path.exists(dom_p) or not os.path.exists(prob_p):
            rec["detail"] = "domain or problem file missing"
            # still create the output path
            try:
                os.makedirs(os.path.dirname(out_p) or ".", exist_ok=True)
                open(out_p, "w").close()
            except Exception:
                pass
            results.append(rec)
            continue
        try:
            acts, used = solve_task(dom_p, prob_p, per_task_timeout,
                                    backend, fd_cmd, have_pyperplan)
        except Exception as e:
            acts, used = [], "none"
            rec["detail"] = "exception: %s" % e
        lines = to_required_format(acts)
        try:
            os.makedirs(os.path.dirname(out_p) or ".", exist_ok=True)
            with open(out_p, "w") as f:
                if lines:
                    f.write("\n".join(lines) + "\n")
        except Exception as e:
            rec["detail"] = "write failed: %s" % e
            results.append(rec)
            continue
        rec["backend"] = used
        rec["num_actions"] = len(lines)
        rec["status"] = "solved" if lines else "empty"
        results.append(rec)

    summ = {"total": len(results),
            "solved": sum(1 for r in results if r["status"] == "solved"),
            "empty": sum(1 for r in results if r["status"] == "empty"),
            "error": sum(1 for r in results if r["status"] == "error")}
    print(json.dumps({"results": results, "summary": summ}))


if __name__ == "__main__":
    main()
