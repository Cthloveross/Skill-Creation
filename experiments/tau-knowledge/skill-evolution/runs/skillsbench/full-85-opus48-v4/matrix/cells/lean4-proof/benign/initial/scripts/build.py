#!/usr/bin/env python3
"""Compile a Lean file in its lake project and report errors/warnings.

stdin  JSON: {"file": str, "warnings_as_errors": bool (default true),
              "workdir": str (default dir of file), "timeout": int (default 600)}
stdout JSON: {"ok", "returncode", "has_error", "has_warning",
              "stdout", "stderr", "cmd"}

`ok` is true iff returncode==0 and no 'warning:' and no 'error:' appears in the
combined output (warnings are treated as errors).
"""
import json
import os
import subprocess
import sys


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        data = {}
    f = data.get("file", "/app/workspace/solution.lean")
    wae = data.get("warnings_as_errors", True)
    workdir = data.get("workdir") or os.path.dirname(os.path.abspath(f))
    timeout = int(data.get("timeout", 600))

    cmd = ["lake", "env", "lean", f]
    try:
        p = subprocess.run(
            cmd, cwd=workdir, capture_output=True, text=True, timeout=timeout
        )
        out, err, rc = p.stdout, p.stderr, p.returncode
    except FileNotFoundError as e:
        print(json.dumps({"ok": False, "error": "command_not_found",
                          "detail": str(e), "cmd": " ".join(cmd)}))
        return
    except subprocess.TimeoutExpired as e:
        print(json.dumps({"ok": False, "error": "timeout",
                          "stdout": e.stdout or "", "stderr": e.stderr or "",
                          "cmd": " ".join(cmd)}))
        return

    combined = (out or "") + "\n" + (err or "")
    low = combined.lower()
    has_error = "error:" in low
    has_warning = "warning:" in low
    if wae:
        ok = rc == 0 and not has_warning and not has_error
    else:
        ok = rc == 0 and not has_error
    print(json.dumps({
        "ok": ok,
        "returncode": rc,
        "has_error": has_error,
        "has_warning": has_warning,
        "stdout": out,
        "stderr": err,
        "cmd": " ".join(cmd),
    }))


if __name__ == "__main__":
    main()
