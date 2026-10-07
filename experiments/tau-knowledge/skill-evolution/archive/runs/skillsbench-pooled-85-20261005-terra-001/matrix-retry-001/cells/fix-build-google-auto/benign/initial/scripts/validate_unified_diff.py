#!/usr/bin/env python3
"""Validate unified diffs and optionally ask git whether they apply cleanly.

Input JSON:
  {"patches": ["patch_1.diff"], "repository": "/path/to/repository"}
The repository field is optional. Output JSON has a result for each patch. This
program does not modify repository files; git is invoked only as `git apply --check`.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(?: .*)?$")


def header_path(line):
    # Diffutils can append a timestamp separated by a tab. Git-style paths with
    # spaces are normally quoted and are left to git apply for definitive parsing.
    payload = line[4:].rstrip("\n")
    return payload.split("\t", 1)[0].split(" ", 1)[0]


def unsafe_path(path):
    if path == "/dev/null":
        return False
    normalized = path[2:] if path.startswith(("a/", "b/")) else path
    return (not normalized or normalized.startswith("/") or
            any(component == ".." for component in normalized.split("/")))


def parse_patch(text):
    errors = []
    lines = text.splitlines(keepends=True)
    file_count = 0
    i = 0
    pending_old = None
    saw_hunk_for_file = False
    while i < len(lines):
        raw = lines[i]
        line = raw.rstrip("\n")
        if line.startswith("--- "):
            if pending_old is not None:
                errors.append("line %d: previous --- header lacks +++ header" % (i + 1))
            pending_old = (i + 1, header_path(line))
            saw_hunk_for_file = False
            if unsafe_path(pending_old[1]):
                errors.append("line %d: unsafe old path %r" % (i + 1, pending_old[1]))
            i += 1
            continue
        if line.startswith("+++ "):
            if pending_old is None:
                errors.append("line %d: +++ header lacks preceding --- header" % (i + 1))
            else:
                new_path = header_path(line)
                if unsafe_path(new_path):
                    errors.append("line %d: unsafe new path %r" % (i + 1, new_path))
                if pending_old[1] == "/dev/null" and new_path == "/dev/null":
                    errors.append("line %d: both file paths are /dev/null" % (i + 1))
                file_count += 1
                pending_old = None
            i += 1
            continue
        match = HUNK.match(line)
        if match:
            if file_count == 0 or pending_old is not None:
                errors.append("line %d: hunk appears before complete file headers" % (i + 1))
            old_need = int(match.group(2) or "1")
            new_need = int(match.group(4) or "1")
            old_seen = new_seen = 0
            i += 1
            while i < len(lines):
                body = lines[i]
                stripped = body.rstrip("\n")
                if HUNK.match(stripped) or stripped.startswith("--- ") or stripped.startswith("diff --git "):
                    break
                if stripped.startswith("\\ No newline at end of file"):
                    i += 1
                    continue
                if not body or body[0] not in " +-":
                    errors.append("line %d: invalid hunk content prefix" % (i + 1))
                    i += 1
                    continue
                if body[0] in " -":
                    old_seen += 1
                if body[0] in " +":
                    new_seen += 1
                i += 1
            if old_seen != old_need or new_seen != new_need:
                errors.append("line %d: hunk count mismatch (header old/new %d/%d, content %d/%d)" %
                              (i + 1, old_need, new_need, old_seen, new_seen))
            saw_hunk_for_file = True
            continue
        i += 1
    if pending_old is not None:
        errors.append("line %d: --- header lacks +++ header" % pending_old[0])
    if file_count == 0:
        errors.append("no ---/+++ file header pair found")
    return errors, file_count


def git_check(patch, repository):
    if not repository:
        return None
    repo = Path(repository)
    if not repo.is_dir():
        return {"ok": False, "detail": "repository is not a directory"}
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo), "apply", "--check", str(patch)],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60,
            check=False,
        )
        return {"ok": completed.returncode == 0,
                "returncode": completed.returncode,
                "stdout": completed.stdout[-4000:], "stderr": completed.stderr[-4000:]}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "detail": str(exc)}


def main():
    try:
        request = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "results": [], "errors": ["invalid JSON: " + str(exc)]}))
        return
    patches = request.get("patches")
    if not isinstance(patches, list) or not all(isinstance(x, str) for x in patches):
        print(json.dumps({"ok": False, "results": [], "errors": ["patches must be an array of strings"]}))
        return
    results = []
    for name in patches:
        path = Path(name)
        result = {"patch": str(path), "errors": [], "file_count": 0}
        try:
            text = path.read_text(encoding="utf-8")
            result["errors"], result["file_count"] = parse_patch(text)
        except (OSError, UnicodeDecodeError) as exc:
            result["errors"] = ["cannot read UTF-8 patch: " + str(exc)]
        result["git_apply_check"] = git_check(path, request.get("repository"))
        results.append(result)
    ok = all(not r["errors"] and (r["git_apply_check"] is None or r["git_apply_check"].get("ok")) for r in results)
    print(json.dumps({"ok": ok, "results": results, "errors": []}, indent=2))


if __name__ == "__main__":
    main()
