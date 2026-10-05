#!/usr/bin/env python3
"""Validate ordinary text unified diffs; optionally ask git to check applicability.

Input and output are JSON as documented in SKILL.md.  This intentionally does
not apply patches or alter the repository.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

HUNK_RE = re.compile(
    r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(?:.*)$"
)
METADATA_PREFIXES = (
    "diff --git ", "index ", "old mode ", "new mode ", "new file mode ",
    "deleted file mode ", "similarity index ", "dissimilarity index ",
    "rename from ", "rename to ", "copy from ", "copy to ",
    "Binary files ",
)


def header_path(header: str, marker: str) -> str:
    """Extract the path portion of a ---/+++ header, ignoring a tab timestamp."""
    value = header[len(marker):]
    return value.split("\t", 1)[0].strip()


def safe_diff_path(path: str) -> bool:
    if path == "/dev/null":
        return True
    # Standard git headers are a/foo and b/foo. Plain relative headers are also
    # legal, but absolute paths and traversal components are not safe artifacts.
    if not path or path.startswith("/"):
        return False
    normalized = path[2:] if path.startswith(("a/", "b/")) else path
    return bool(normalized) and all(part not in ("", ".", "..")
                                  for part in normalized.split("/"))


def validate_one(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {"path": str(path), "files": 0, "hunks": 0,
                              "errors": []}
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        result["errors"].append("cannot read UTF-8 patch: %s" % exc)
        return result

    lines = raw.splitlines()
    i = 0
    seen_pair = False
    while i < len(lines):
        line = lines[i]
        if line.startswith("--- "):
            if i + 1 >= len(lines) or not lines[i + 1].startswith("+++ "):
                result["errors"].append("line %d: --- header lacks following +++ header" % (i + 1))
                return result
            old_path = header_path(line, "--- ")
            new_path = header_path(lines[i + 1], "+++ ")
            if not safe_diff_path(old_path) or not safe_diff_path(new_path):
                result["errors"].append("line %d: unsafe or empty diff header path" % (i + 1))
                return result
            result["files"] += 1
            seen_pair = True
            i += 2
            file_hunks = 0
            while i < len(lines) and not lines[i].startswith("--- "):
                current = lines[i]
                if current.startswith("diff --git "):
                    # A new git file section must eventually have ---/+++.
                    break
                match = HUNK_RE.match(current)
                if not match:
                    result["errors"].append("line %d: expected @@ hunk header" % (i + 1))
                    return result
                old_count = int(match.group(2) or "1")
                new_count = int(match.group(4) or "1")
                i += 1
                got_old = got_new = 0
                while i < len(lines):
                    content = lines[i]
                    if content.startswith("\\ No newline at end of file"):
                        i += 1
                        continue
                    if content.startswith(" "):
                        got_old += 1
                        got_new += 1
                    elif content.startswith("-"):
                        got_old += 1
                    elif content.startswith("+"):
                        got_new += 1
                    else:
                        break
                    i += 1
                    if got_old == old_count and got_new == new_count:
                        # Permit only the optional no-newline marker before the
                        # next hunk/header; surplus prefixed lines are caught by
                        # count mismatch on the next loop iteration.
                        while i < len(lines) and lines[i].startswith("\\ No newline at end of file"):
                            i += 1
                        break
                if got_old != old_count or got_new != new_count:
                    result["errors"].append(
                        "line %d: hunk counts are -%d/+%d, expected -%d/+%d" %
                        (i + 1, got_old, got_new, old_count, new_count)
                    )
                    return result
                file_hunks += 1
                result["hunks"] += 1
            if file_hunks == 0:
                result["errors"].append("file section ending near line %d has no text hunk" % (i + 1))
                return result
            continue
        if line.startswith(METADATA_PREFIXES):
            i += 1
            continue
        if not line and not seen_pair:
            i += 1
            continue
        result["errors"].append("line %d: unexpected content outside a file patch" % (i + 1))
        return result

    if not seen_pair:
        result["errors"].append("patch contains no ---/+++ file header pair")
    return result


def main() -> int:
    try:
        request = json.load(sys.stdin)
        patches = request["patches"]
        if not isinstance(patches, list) or not patches or not all(isinstance(p, str) for p in patches):
            raise ValueError("patches must be a nonempty list of path strings")
        check_apply = bool(request.get("check_apply", False))
        repo_root = request.get("repo_root")
        if check_apply and (not isinstance(repo_root, str) or not repo_root):
            raise ValueError("repo_root is required when check_apply is true")
    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        print(json.dumps({"ok": False, "patches": [], "errors": ["invalid input: %s" % exc]}))
        return 2

    summaries = [validate_one(Path(p)) for p in patches]
    errors = [err for summary in summaries for err in summary["errors"]]
    if not errors and check_apply:
        try:
            completed = subprocess.run(
                ["git", "-C", os.path.abspath(repo_root), "apply", "--check", "--", *patches],
                text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
            )
            if completed.returncode:
                errors.append("git apply --check failed: " + (completed.stderr or completed.stdout).strip())
        except OSError as exc:
            errors.append("could not execute git apply --check: %s" % exc)

    print(json.dumps({"ok": not errors, "patches": summaries, "errors": errors}, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
