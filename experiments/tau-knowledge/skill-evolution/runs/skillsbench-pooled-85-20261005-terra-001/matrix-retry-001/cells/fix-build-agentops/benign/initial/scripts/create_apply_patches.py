#!/usr/bin/env python3
"""Generate, validate, persist, and apply unified text patches from JSON stdin.

This utility intentionally accepts complete replacement text for existing files.  It
therefore derives every patch from the checkout's real current preimage rather than
from guessed line numbers or context.
"""
import difflib
import json
import os
import re
import sys
import tempfile
from pathlib import Path, PurePosixPath

HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(?:.*)$")
PATCH_NAME_RE = re.compile(r"^patch_\d+\.diff$")


def fail(message):
    raise ValueError(message)


def safe_relative(value):
    if not isinstance(value, str) or not value:
        fail("change path must be a nonempty relative POSIX path")
    item = PurePosixPath(value)
    if item.is_absolute() or ".." in item.parts or "." in item.parts:
        fail("change path must stay below the repository root")
    if PATCH_NAME_RE.match(item.name):
        fail("source changes may not overwrite numbered patch artifacts")
    return item


def contained_file(repo, relative):
    candidate = (repo / Path(*relative.parts)).resolve()
    try:
        candidate.relative_to(repo)
    except ValueError:
        fail("change path resolves outside repository")
    if not candidate.is_file():
        fail("change path is not an existing regular file: %s" % relative.as_posix())
    return candidate


def require_text_with_final_newline(text, label):
    # Empty files are permitted. Nonempty files without a final newline require
    # standard tools because this compact parser deliberately rejects marker lines.
    if text and not text.endswith("\n"):
        fail("%s lacks a final newline; use standard git/diff tooling for this file" % label)


def render_patch(relative, old_text, new_text):
    old_lines = old_text.splitlines(keepends=True)
    new_lines = new_text.splitlines(keepends=True)
    return "".join(difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile="a/" + relative.as_posix(),
        tofile="b/" + relative.as_posix(),
        n=3,
        lineterm="\n",
    ))


def parse_patch(patch_text):
    """Parse a deliberately small, strict subset of ordinary text unified diff."""
    if not patch_text:
        fail("patch is empty")
    lines = patch_text.splitlines(keepends=True)
    if len(lines) < 3:
        fail("patch lacks headers and hunks")
    if not lines[0].startswith("--- a/") or not lines[1].startswith("+++ b/"):
        fail("patch must begin with --- a/<path> and +++ b/<path> headers")
    old_name = lines[0][6:].rstrip("\r\n")
    new_name = lines[1][6:].rstrip("\r\n")
    if old_name != new_name:
        fail("rename, add, and delete patches are unsupported by this helper")
    relative = safe_relative(old_name)
    hunks = []
    index = 2
    while index < len(lines):
        header = lines[index].rstrip("\r\n")
        match = HUNK_RE.match(header)
        if not match:
            fail("malformed hunk header: %s" % header)
        old_start = int(match.group(1))
        old_count = int(match.group(2) or "1")
        new_start = int(match.group(3))
        new_count = int(match.group(4) or "1")
        index += 1
        body = []
        while index < len(lines) and not lines[index].startswith("@@ "):
            line = lines[index]
            if line.startswith("\\ No newline"):
                fail("no-final-newline markers are unsupported")
            if not line or line[0] not in " +-":
                fail("hunk content lacks required context/addition/deletion prefix")
            body.append(line)
            index += 1
        actual_old = sum(1 for line in body if line[0] in " -")
        actual_new = sum(1 for line in body if line[0] in " +")
        if actual_old != old_count or actual_new != new_count:
            fail("hunk line counts do not match its header")
        hunks.append((old_start, old_count, new_start, new_count, body))
    if not hunks:
        fail("patch has no hunks")
    return relative, hunks


def apply_to_text(old_text, patch_text):
    relative, hunks = parse_patch(patch_text)
    source = old_text.splitlines(keepends=True)
    result = []
    cursor = 0
    for old_start, old_count, _new_start, _new_count, body in hunks:
        start = old_start - 1
        if old_start < 0 or start < cursor or start > len(source):
            fail("hunks are out of order or outside source for %s" % relative.as_posix())
        old_body = [line[1:] for line in body if line[0] in " -"]
        new_body = [line[1:] for line in body if line[0] in " +"]
        if len(old_body) != old_count:
            fail("internal old hunk count error")
        if source[start:start + old_count] != old_body:
            fail("patch preimage/context does not match current file: %s" % relative.as_posix())
        result.extend(source[cursor:start])
        result.extend(new_body)
        cursor = start + old_count
    result.extend(source[cursor:])
    return relative, "".join(result)


def atomic_write(path, text):
    fd, temporary = tempfile.mkstemp(prefix=".patch-work.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def resolve_repo(value):
    if not isinstance(value, str) or not value:
        fail("repo must be a nonempty absolute path")
    repo = Path(value)
    if not repo.is_absolute() or not repo.is_dir():
        fail("repo must be an existing absolute directory")
    return repo.resolve()


def apply_mode(data):
    repo = resolve_repo(data.get("repo"))
    changes = data.get("changes")
    patch_start = data.get("patch_start", 1)
    if not isinstance(changes, list) or not changes:
        fail("changes must be a nonempty list")
    if not isinstance(patch_start, int) or patch_start < 1:
        fail("patch_start must be a positive integer")

    seen = set()
    plans = []
    for offset, change in enumerate(changes):
        if not isinstance(change, dict):
            fail("each change must be an object")
        relative = safe_relative(change.get("path"))
        key = relative.as_posix()
        if key in seen:
            fail("duplicate changed path: " + key)
        seen.add(key)
        new_text = change.get("new_content")
        if not isinstance(new_text, str):
            fail("new_content must be a string for " + key)
        target = contained_file(repo, relative)
        old_text = target.read_text(encoding="utf-8")
        require_text_with_final_newline(old_text, "existing file " + key)
        require_text_with_final_newline(new_text, "new content " + key)
        if old_text == new_text:
            fail("change does not modify file: " + key)
        patch_path = repo / ("patch_%d.diff" % (patch_start + offset))
        if patch_path.exists():
            fail("refusing to overwrite existing patch artifact: " + str(patch_path))
        patch_text = render_patch(relative, old_text, new_text)
        parsed_relative, applied_text = apply_to_text(old_text, patch_text)
        if parsed_relative != relative or applied_text != new_text:
            fail("generated patch did not reproduce requested content for " + key)
        plans.append((target, patch_path, patch_text, new_text))

    # Persist all standalone artifacts before modifying any source file.
    for _target, patch_path, patch_text, _new_text in plans:
        atomic_write(patch_path, patch_text)
    for target, _patch_path, _patch_text, new_text in plans:
        atomic_write(target, new_text)
    return {
        "ok": True,
        "patches": [str(plan[1]) for plan in plans],
        "applied": [str(plan[0]) for plan in plans],
    }


def validate_mode(data):
    repo = resolve_repo(data.get("repo"))
    value = data.get("patch_path")
    if not isinstance(value, str) or not value:
        fail("patch_path must be a nonempty string")
    patch_path = Path(value).resolve()
    try:
        patch_path.relative_to(repo)
    except ValueError:
        fail("patch_path must be inside repo")
    if not patch_path.is_file():
        fail("patch_path is not an existing file")
    patch_text = patch_path.read_text(encoding="utf-8")
    relative, _hunks = parse_patch(patch_text)
    checked = False
    if data.get("check_preimage", False):
        target = contained_file(repo, relative)
        old_text = target.read_text(encoding="utf-8")
        apply_to_text(old_text, patch_text)
        checked = True
    return {"ok": True, "patch": str(patch_path), "path": relative.as_posix(), "preimage_checked": checked}


def main():
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            fail("input must be a JSON object")
        result = validate_mode(data) if data.get("mode") == "validate" else apply_mode(data)
        sys.stdout.write(json.dumps(result, sort_keys=True) + "\n")
    except Exception as exc:
        sys.stdout.write(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True) + "\n")
        raise SystemExit(2)


if __name__ == "__main__":
    main()
