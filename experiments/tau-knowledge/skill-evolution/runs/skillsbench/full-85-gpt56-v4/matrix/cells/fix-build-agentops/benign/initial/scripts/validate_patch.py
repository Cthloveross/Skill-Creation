#!/usr/bin/env python3
"""Validate unified diff artifacts without modifying the working tree.

Reads JSON from stdin:
  {"repo": "/path/to/repo" (optional), "patches": ["/path/patch.diff", ...]}
Writes JSON findings to stdout and exits nonzero if a patch is invalid.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from typing import Any, Dict, List


def structural_errors(text: str) -> List[str]:
    """Return conservative errors for a normal unified diff containing hunks."""
    errors: List[str] = []
    lines = text.splitlines()
    if not lines:
        return ["patch is empty"]

    file_pairs = 0
    hunks = 0
    in_hunk = False
    expect_new_header = False

    for number, line in enumerate(lines, 1):
        if line.startswith("--- "):
            file_pairs += 1
            expect_new_header = True
            in_hunk = False
            continue
        if expect_new_header:
            if line.startswith("+++ "):
                expect_new_header = False
                continue
            errors.append("line %d: expected +++ header after --- header" % number)
            expect_new_header = False
        if line.startswith("+++ "):
            errors.append("line %d: +++ header has no preceding --- header" % number)
            continue
        if line.startswith("@@ "):
            # Require both old and new ranges. Exact counts are delegated to git.
            if " -" not in line or " +" not in line or " @@" not in line:
                errors.append("line %d: malformed hunk header" % number)
            hunks += 1
            in_hunk = True
            continue
        if in_hunk:
            if line == r"\ No newline at end of file":
                continue
            if line.startswith((" ", "+", "-")):
                continue
            # diff metadata may begin a subsequent file block, which was handled above.
            errors.append("line %d: hunk content lacks space, +, or - prefix" % number)

    if expect_new_header:
        errors.append("patch ends after --- header without +++ header")
    if file_pairs == 0:
        errors.append("no ---/+++ file header pair found")
    if hunks == 0:
        errors.append("no @@ unified-diff hunk found")
    return errors


def validate_one(path: str, repo: str | None) -> Dict[str, Any]:
    result: Dict[str, Any] = {"path": path, "structural_errors": [], "git_apply_check": None}
    if not os.path.isfile(path):
        result["structural_errors"] = ["patch path is not a regular file"]
        return result
    try:
        with open(path, "r", encoding="utf-8", newline="") as handle:
            text = handle.read()
    except (OSError, UnicodeError) as exc:
        result["structural_errors"] = ["cannot read UTF-8 patch: %s" % exc]
        return result

    result["structural_errors"] = structural_errors(text)
    if repo and not result["structural_errors"]:
        git = shutil.which("git")
        if git is None:
            result["git_apply_check"] = {"skipped": "git executable not found"}
        elif not os.path.isdir(repo):
            result["git_apply_check"] = {"skipped": "repo is not a directory"}
        else:
            completed = subprocess.run(
                [git, "apply", "--check", "--", os.path.abspath(path)],
                cwd=repo,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            result["git_apply_check"] = {
                "returncode": completed.returncode,
                "stdout": completed.stdout[-4000:],
                "stderr": completed.stderr[-4000:],
            }
    return result


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "errors": ["invalid input JSON: %s" % exc]}))
        return 2
    if not isinstance(data, dict):
        print(json.dumps({"ok": False, "errors": ["input must be a JSON object"]}))
        return 2
    patches = data.get("patches")
    repo = data.get("repo")
    if not isinstance(patches, list) or not patches or not all(isinstance(p, str) for p in patches):
        print(json.dumps({"ok": False, "errors": ["patches must be a nonempty array of strings"]}))
        return 2
    if repo is not None and not isinstance(repo, str):
        print(json.dumps({"ok": False, "errors": ["repo must be a string when supplied"]}))
        return 2

    results = [validate_one(path, repo) for path in patches]
    errors: List[str] = []
    for item in results:
        for err in item["structural_errors"]:
            errors.append("%s: %s" % (item["path"], err))
        check = item["git_apply_check"]
        if isinstance(check, dict) and check.get("returncode", 0) != 0:
            errors.append("%s: git apply --check failed" % item["path"])
    print(json.dumps({"ok": not errors, "patches": results, "errors": errors}, indent=2, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
