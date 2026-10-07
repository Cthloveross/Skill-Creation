#!/usr/bin/env python3
"""Run Maven verification goals for the migration and summarize the result.

stdin  JSON: {"workdir":"/workspace","goals":["clean","compile"],
              "args":["-B"],"timeout_sec":600,"mvn":"mvn"}
stdout JSON: {command, exit_code, success, build_result, tests, error_lines, tail, timed_out}

`success` is true only when Maven exits 0 and prints BUILD SUCCESS. A nonzero
exit, BUILD FAILURE, or timeout is a real failure to inspect.
"""
import json
import os
import re
import subprocess
import sys


def main():
    try:
        req = json.load(sys.stdin)
    except Exception:
        req = {}
    workdir = req.get("workdir") or os.getcwd()
    goals = req.get("goals") or ["clean", "test"]
    args = req.get("args") or ["-B"]
    mvn = req.get("mvn") or "mvn"
    timeout = int(req.get("timeout_sec") or 600)

    cmd = [mvn] + list(args) + list(goals)
    timed_out = False
    try:
        proc = subprocess.run(cmd, cwd=workdir, capture_output=True, text=True,
                              timeout=timeout)
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        exit_code = proc.returncode
    except subprocess.TimeoutExpired as e:
        stdout = (e.stdout or "") if isinstance(e.stdout, str) else ""
        stderr = (e.stderr or "") if isinstance(e.stderr, str) else ""
        exit_code = -1
        timed_out = True
    except FileNotFoundError as e:
        print(json.dumps({"error": "maven not found", "detail": str(e),
                          "command": cmd}))
        return

    combined = stdout + "\n" + stderr

    if "BUILD SUCCESS" in combined:
        build_result = "SUCCESS"
    elif "BUILD FAILURE" in combined:
        build_result = "FAILURE"
    else:
        build_result = "UNKNOWN"

    tests = {"run": None, "failures": None, "errors": None, "skipped": None}
    m = re.search(r"Tests run:\s*(\d+),\s*Failures:\s*(\d+),\s*Errors:\s*(\d+),\s*Skipped:\s*(\d+)",
                  combined[::-1])  # placeholder; real search below
    # Find the last "Tests run" summary (the overall one).
    matches = re.findall(
        r"Tests run:\s*(\d+),\s*Failures:\s*(\d+),\s*Errors:\s*(\d+),\s*Skipped:\s*(\d+)",
        combined)
    if matches:
        r, fcount, ecount, scount = matches[-1]
        tests = {"run": int(r), "failures": int(fcount),
                 "errors": int(ecount), "skipped": int(scount)}

    error_lines = [ln for ln in combined.splitlines() if "[ERROR]" in ln][:60]
    tail = combined[-4000:]

    success = (exit_code == 0) and (build_result == "SUCCESS") and not timed_out

    out = {
        "command": cmd,
        "workdir": workdir,
        "exit_code": exit_code,
        "success": success,
        "build_result": build_result,
        "tests": tests,
        "error_lines": error_lines,
        "tail": tail,
        "timed_out": timed_out,
    }
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
