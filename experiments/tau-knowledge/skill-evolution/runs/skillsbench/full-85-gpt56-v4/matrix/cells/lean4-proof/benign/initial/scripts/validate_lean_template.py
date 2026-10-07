#!/usr/bin/env python3
"""Snapshot and validate a protected-prefix Lean proof template.

Input JSON schemas:
  {"action":"snapshot", "solution": str, "snapshot": str, "prefix_lines": int}
  {"action":"check", "solution": str, "snapshot": str, "prefix_lines": int,
   "cwd": str?, "compile_command": [str, ...]?}

The program emits a JSON report.  It does not modify the Lean solution file.
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


def first_lines(data: bytes, count: int) -> bytes:
    if count < 0:
        raise ValueError("prefix_lines must be nonnegative")
    lines = data.splitlines(keepends=True)
    if len(lines) < count:
        raise ValueError("solution has fewer physical lines than prefix_lines")
    return b"".join(lines[:count])


def read_request() -> dict[str, Any]:
    value = json.load(sys.stdin)
    if not isinstance(value, dict):
        raise ValueError("JSON input must be an object")
    return value


def main() -> int:
    try:
        request = read_request()
        action = request.get("action")
        solution = Path(request["solution"])
        snapshot = Path(request["snapshot"])
        prefix_lines = request["prefix_lines"]
        if not isinstance(prefix_lines, int):
            raise ValueError("prefix_lines must be an integer")
        source_bytes = solution.read_bytes()
        prefix = first_lines(source_bytes, prefix_lines)

        if action == "snapshot":
            snapshot.parent.mkdir(parents=True, exist_ok=True)
            snapshot.write_bytes(prefix)
            print(json.dumps({
                "ok": True,
                "action": "snapshot",
                "snapshot": str(snapshot),
                "prefix_lines": prefix_lines,
                "prefix_bytes": len(prefix),
            }))
            return 0

        if action != "check":
            raise ValueError("action must be 'snapshot' or 'check'")

        expected = snapshot.read_bytes()
        prefix_matches = prefix == expected
        cwd = Path(request.get("cwd", str(solution.parent)))
        command = request.get("compile_command")
        if command is None:
            command = ["lake", "env", "lean", "--Werror", solution.name]
        if not isinstance(command, list) or not all(isinstance(x, str) for x in command):
            raise ValueError("compile_command must be an array of strings")

        if prefix_matches:
            completed = subprocess.run(
                command,
                cwd=str(cwd),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            compile_report = {
                "command": command,
                "cwd": str(cwd),
                "returncode": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
            }
        else:
            compile_report = {
                "skipped": True,
                "reason": "protected prefix differs from snapshot",
            }

        ok = prefix_matches and compile_report.get("returncode") == 0
        print(json.dumps({
            "ok": ok,
            "action": "check",
            "prefix_matches": prefix_matches,
            "expected_prefix_bytes": len(expected),
            "actual_prefix_bytes": len(prefix),
            "compile": compile_report,
        }))
        return 0 if ok else 1
    except Exception as exc:  # provide machine-readable diagnostics to the executor
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
