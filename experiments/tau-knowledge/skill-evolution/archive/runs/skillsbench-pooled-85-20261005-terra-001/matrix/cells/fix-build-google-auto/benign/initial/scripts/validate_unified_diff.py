#!/usr/bin/env python3
"""Validate the structure of a unified diff without applying it.

Input JSON: {"path"?: str, "content"?: str, "repo_root"?: str}
Exactly one of path/content is required. Output JSON has valid, errors, warnings,
files, and hunks. Header path checking is lexical only; use git apply --check too.
"""
import json
import re
import sys
from pathlib import PurePosixPath, Path

HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(?:.*)$")


def parse_header_path(line, prefix):
    value = line[len(prefix):]
    # GNU diff may append a tab-delimited timestamp. Git labels do not.
    return value.split("\t", 1)[0].strip()


def safe_relative(path):
    if path == "/dev/null":
        return True
    normalized = path
    if normalized.startswith("a/") or normalized.startswith("b/"):
        normalized = normalized[2:]
    candidate = PurePosixPath(normalized)
    return bool(normalized) and not candidate.is_absolute() and ".." not in candidate.parts


def main():
    errors = []
    warnings = []
    files = []
    hunks = []
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise ValueError("input must be a JSON object")
        has_path = isinstance(request.get("path"), str)
        has_content = isinstance(request.get("content"), str)
        if has_path == has_content:
            raise ValueError("provide exactly one string field: path or content")
        if has_path:
            text = Path(request["path"]).read_text(encoding="utf-8", errors="replace")
        else:
            text = request["content"]
        if "\r\n" in text:
            warnings.append("diff uses CRLF line endings; verify target tooling accepts it")
        lines = text.splitlines()
        current = None
        active_hunk = None
        saw_hunk = False
        check_paths = "repo_root" in request
        if check_paths and not isinstance(request["repo_root"], str):
            raise ValueError("repo_root must be a string when supplied")

        for lineno, line in enumerate(lines, 1):
            if line.startswith("--- "):
                if active_hunk is not None:
                    errors.append(f"line {lineno}: new file header starts before prior hunk ended")
                    active_hunk = None
                if current is not None and current.get("new") is None:
                    errors.append(f"line {lineno}: previous --- header has no matching +++ header")
                current = {"old": parse_header_path(line, "--- "), "new": None, "line": lineno, "hunks": 0}
                files.append(current)
                continue
            if line.startswith("+++ "):
                if current is None or current.get("new") is not None:
                    errors.append(f"line {lineno}: +++ header lacks a matching --- header")
                else:
                    current["new"] = parse_header_path(line, "+++ ")
                continue
            match = HUNK_RE.match(line)
            if match:
                if current is None or current.get("new") is None:
                    errors.append(f"line {lineno}: hunk lacks completed ---/+++ headers")
                if active_hunk is not None:
                    errors.append(f"line {lineno}: prior hunk count does not match its header")
                old_count = int(match.group(2) or "1")
                new_count = int(match.group(4) or "1")
                active_hunk = {"line": lineno, "old_expected": old_count, "new_expected": new_count, "old_seen": 0, "new_seen": 0}
                hunks.append(active_hunk)
                saw_hunk = True
                if current is not None:
                    current["hunks"] += 1
                continue
            if active_hunk is not None:
                if line.startswith("\\ No newline at end of file"):
                    continue
                if not line:
                    errors.append(f"line {lineno}: empty hunk line is missing its required prefix")
                    continue
                marker = line[0]
                if marker == " ":
                    active_hunk["old_seen"] += 1
                    active_hunk["new_seen"] += 1
                elif marker == "-":
                    active_hunk["old_seen"] += 1
                elif marker == "+":
                    active_hunk["new_seen"] += 1
                else:
                    errors.append(f"line {lineno}: invalid hunk-line prefix {marker!r}")
                if active_hunk["old_seen"] == active_hunk["old_expected"] and active_hunk["new_seen"] == active_hunk["new_expected"]:
                    active_hunk = None
                elif active_hunk["old_seen"] > active_hunk["old_expected"] or active_hunk["new_seen"] > active_hunk["new_expected"]:
                    errors.append(f"line {lineno}: hunk content exceeds header counts")
                    active_hunk = None

        if current is not None and current.get("new") is None:
            errors.append(f"line {current['line']}: --- header has no matching +++ header")
        if active_hunk is not None:
            errors.append(f"line {active_hunk['line']}: hunk content does not match header counts")
        if not files:
            errors.append("no ---/+++ file header pair found")
        if files and not saw_hunk:
            errors.append("no unified-diff hunks found")
        for entry in files:
            if entry.get("new") is None:
                continue
            if check_paths:
                for label, name in (("old", entry["old"]), ("new", entry["new"])):
                    if not safe_relative(name):
                        errors.append(f"line {entry['line']}: {label} header path is not a safe repository-relative path: {name!r}")
            if entry["old"] == entry["new"] and entry["old"] != "/dev/null":
                warnings.append(f"line {entry['line']}: old and new header paths are identical (acceptable for modifications)")
        output = {
            "valid": not errors,
            "errors": errors,
            "warnings": warnings,
            "files": [{"old": f["old"], "new": f.get("new"), "line": f["line"], "hunks": f["hunks"]} for f in files],
            "hunks": hunks,
        }
    except Exception as exc:
        output = {"valid": False, "errors": [str(exc)], "warnings": warnings, "files": files, "hunks": hunks}
    json.dump(output, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
