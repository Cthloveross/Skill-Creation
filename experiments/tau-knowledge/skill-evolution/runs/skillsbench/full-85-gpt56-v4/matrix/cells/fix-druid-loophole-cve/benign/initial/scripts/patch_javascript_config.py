#!/usr/bin/env python3
"""Protect Druid JavaScriptConfig Jackson injection and write an actual git diff.

Reads one JSON object from stdin and prints one JSON object to stdout.  It deliberately
changes only Java parameter declarations whose declared type is JavaScriptConfig.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

INJECT_RE = re.compile(
    r"(?P<annotation>@JacksonInject(?:\s*\((?P<args>[^)]*)\))?)(?P<gap>\s+)"
    r"(?P<decl>(?:(?:final|@\w+(?:\([^)]*\))?)\s+)*JavaScriptConfig\s+\w+)",
    re.MULTILINE,
)
# A declaration without the annotation is deliberately reported, not transformed.
CONFIG_DECL_RE = re.compile(r"\bJavaScriptConfig\s+([A-Za-z_$][A-Za-z0-9_$]*)\b")
MAPPER_MARKERS = ("AnnotationIntrospector", "findInjectableValueId", "findInjectableValue")


def git(root, *args):
    return subprocess.run(
        ["git", "-C", str(root), *args], text=True, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, check=False
    )


def annotation_with_no_input(annotation):
    """Return equivalent JacksonInject annotation with explicit no-input policy."""
    if "useInput" in annotation:
        return annotation
    if annotation == "@JacksonInject":
        return "@JacksonInject(useInput = OptBoolean.FALSE)"
    body = annotation[annotation.find("(") + 1:-1].strip()
    # Jackson accepts a bare string as the value member. Convert it before adding
    # another named member, because mixed bare/named annotation arguments are invalid.
    if body.startswith('"') and body.endswith('"'):
        body = "value = " + body
    suffix = "useInput = OptBoolean.FALSE"
    return "@JacksonInject(" + (body + ", " if body else "") + suffix + ")"


def add_optboolean_import(text):
    if "com.fasterxml.jackson.annotation.OptBoolean" in text:
        return text
    imports = list(re.finditer(r"^import\s+[^;]+;\s*$", text, re.MULTILINE))
    if not imports:
        raise ValueError("no Java import section found for OptBoolean import")
    jackson = [m for m in imports if "com.fasterxml.jackson.annotation." in m.group(0)]
    where = (jackson[-1] if jackson else imports[-1]).end()
    return text[:where] + "\nimport com.fasterxml.jackson.annotation.OptBoolean;" + text[where:]


def main():
    try:
        request = json.load(sys.stdin)
        root = Path(request["source_root"]).resolve()
        patch_path = Path(request["patch_path"]).resolve()
        write_patch = request.get("write_patch", True)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": "invalid input: %s" % exc}))
        return 2

    if not (root / ".git").exists() or git(root, "rev-parse", "--is-inside-work-tree").returncode:
        print(json.dumps({"ok": False, "error": "source_root is not a git work tree"}))
        return 2

    java_files = sorted(root.rglob("*.java"))
    protected, unprotected, changed, mapper_review = [], [], [], []
    edits = []

    for path in java_files:
        # Do not touch generated output, target trees, or vendored build products.
        if any(part in {"target", ".git"} for part in path.parts):
            continue
        try:
            original = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if "JavaScriptConfig" not in original:
            continue

        covered_spans = []
        needs_import = False

        def replace(match):
            nonlocal needs_import
            annotation = match.group("annotation")
            decl = match.group("decl")
            covered_spans.append((match.start("decl"), match.end("decl")))
            if "useInput" in annotation:
                protected.append(str(path.relative_to(root)) + ":" + decl.strip())
                return match.group(0)
            needs_import = True
            protected.append(str(path.relative_to(root)) + ":" + decl.strip())
            return annotation_with_no_input(annotation) + match.group("gap") + decl

        updated = INJECT_RE.sub(replace, original)
        for decl in CONFIG_DECL_RE.finditer(original):
            if not any(start <= decl.start() < end for start, end in covered_spans):
                unprotected.append(str(path.relative_to(root)) + ":" + decl.group(0))

        if needs_import:
            try:
                updated = add_optboolean_import(updated)
            except ValueError as exc:
                print(json.dumps({"ok": False, "error": "%s: %s" % (path, exc),
                                  "unprotected_parameters": unprotected}))
                return 2
        if updated != original:
            edits.append((path, updated))
            changed.append(str(path.relative_to(root)))

        if any(marker in original for marker in MAPPER_MARKERS) and (
            "AnnotationIntrospector" in original or "findInjectableValue" in original
        ):
            mapper_review.append(str(path.relative_to(root)))

    if unprotected:
        print(json.dumps({
            "ok": False,
            "error": "unrecognized JavaScriptConfig declaration(s); no edits were written",
            "unprotected_parameters": unprotected,
            "mapper_review_files": mapper_review,
        }, sort_keys=True))
        return 2

    for path, updated in edits:
        path.write_text(updated, encoding="utf-8")

    diff = git(root, "diff", "--binary", "--", *changed)
    if diff.returncode:
        print(json.dumps({"ok": False, "error": "git diff failed: " + diff.stderr.strip()}))
        return 2
    if write_patch:
        patch_path.parent.mkdir(parents=True, exist_ok=True)
        patch_path.write_text(diff.stdout, encoding="utf-8")

    # --check detects malformed whitespace introduced by an edit before Maven does.
    check = git(root, "diff", "--check")
    result = {
        "ok": check.returncode == 0,
        "changed_files": changed,
        "protected_parameters": protected,
        "unprotected_parameters": [],
        "mapper_review_files": sorted(set(mapper_review)),
        "patch_path": str(patch_path) if write_patch else None,
        "patch_bytes": len(diff.stdout.encode("utf-8")),
        "error": check.stderr.strip() if check.returncode else None,
    }
    print(json.dumps(result, sort_keys=True))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
