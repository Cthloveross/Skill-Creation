#!/usr/bin/env python3
"""Summarize likely Maven/Java build diagnostics from a supplied log file.

Input JSON: {"log_path": str, "context_lines"?: int, "max_diagnostics"?: int}
Output JSON: {"ok": bool, "error_lines": [...], "failure_markers": [...],
              "diagnostics": [{"line": int, "text": str, "context": [...] }],
              "tail": [...], "error"?: str}
"""
import json
import re
import sys
from pathlib import Path


def positive_int(value, default, maximum):
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("must be a positive integer")
    return min(value, maximum)


def main():
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict) or not isinstance(request.get("log_path"), str):
            raise ValueError("log_path must be a string")
        context_size = positive_int(request.get("context_lines"), 3, 30)
        maximum = positive_int(request.get("max_diagnostics"), 12, 100)
        path = Path(request["log_path"])
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()

        diagnostic_patterns = [
            re.compile(r"\[ERROR\].*(?:COMPILATION ERROR|Failed to execute goal|Failed to read project|Could not resolve|There are test failures)", re.I),
            re.compile(r"(?:^|\s)(?:error:|Exception in thread|Caused by:|cannot find symbol|package .* does not exist|unsupported (?:major|source|target)|No such file|not found)", re.I),
            re.compile(r"\[ERROR\]\s+.+:\[\d+,\d+\]"),
        ]
        marker_pattern = re.compile(r"\[INFO\] BUILD (?:FAILURE|SUCCESS)|\[ERROR\] (?:BUILD FAILURE|Reactor Summary)", re.I)
        selected = []
        marker_lines = []
        error_lines = []
        seen = set()
        for index, line in enumerate(lines):
            number = index + 1
            if "[ERROR]" in line:
                error_lines.append({"line": number, "text": line})
            if marker_pattern.search(line):
                marker_lines.append({"line": number, "text": line})
            if len(selected) < maximum and any(pattern.search(line) for pattern in diagnostic_patterns):
                if number not in seen:
                    seen.add(number)
                    lo = max(0, index - context_size)
                    hi = min(len(lines), index + context_size + 1)
                    selected.append({
                        "line": number,
                        "text": line,
                        "context": [{"line": j + 1, "text": lines[j]} for j in range(lo, hi)],
                    })
        result = {
            "ok": True,
            "error_lines": error_lines[:maximum],
            "failure_markers": marker_lines,
            "diagnostics": selected,
            "tail": [{"line": j + 1, "text": lines[j]} for j in range(max(0, len(lines) - 30), len(lines))],
        }
    except Exception as exc:
        result = {"ok": False, "error": str(exc), "error_lines": [], "failure_markers": [], "diagnostics": [], "tail": []}
    json.dump(result, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
