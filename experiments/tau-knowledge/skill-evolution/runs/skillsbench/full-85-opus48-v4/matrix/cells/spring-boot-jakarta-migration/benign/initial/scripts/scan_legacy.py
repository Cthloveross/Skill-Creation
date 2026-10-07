#!/usr/bin/env python3
"""Scan a Java/Maven source tree for legacy namespaces and deprecated/removed
APIs that must change for a Spring Boot 2.7 -> 3.2 / Java 8 -> 21 migration.

stdin  JSON: {"root": "/workspace", "patterns_file": "<optional>"}
stdout JSON: {"root","total","findings":[{pattern,category,suggestion,file,line,text}],"by_pattern"}

Findings are candidate edits. javax.* findings include a concrete jakarta
suggestion; security/RestTemplate findings carry a migration note.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PATTERNS = os.path.join(HERE, "..", "references", "legacy_patterns.json")

SCAN_EXTS = (".java", ".xml", ".properties", ".yml", ".yaml", ".kt")
SKIP_DIRS = {".git", "target", "build", ".idea", "node_modules", ".mvn"}


def load_patterns(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def iter_files(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if name.endswith(SCAN_EXTS):
                yield os.path.join(dirpath, name)


def main():
    try:
        req = json.load(sys.stdin)
    except Exception:
        req = {}
    root = req.get("root") or os.getcwd()
    patterns_file = req.get("patterns_file") or DEFAULT_PATTERNS

    try:
        patterns = load_patterns(patterns_file)
    except Exception as e:
        print(json.dumps({"error": "cannot load patterns", "detail": str(e),
                          "patterns_file": patterns_file}))
        return

    compiled = []
    for p in patterns:
        try:
            rx = re.compile(p["regex"])
        except re.error as e:
            rx = None
            p = dict(p, _compile_error=str(e))
        compiled.append((rx, p))

    findings = []
    by_pattern = {}
    if not os.path.isdir(root):
        print(json.dumps({"error": "root not found", "root": root}))
        return

    for fpath in iter_files(root):
        try:
            with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except Exception:
            continue
        for lineno, line in enumerate(lines, 1):
            for rx, p in compiled:
                if rx is None:
                    continue
                if rx.search(line):
                    suggestion = p.get("suggestion", "")
                    repl = p.get("replace")
                    if repl is not None:
                        try:
                            suggestion = rx.sub(repl, line.strip())
                        except re.error:
                            pass
                    findings.append({
                        "pattern": p["name"],
                        "category": p.get("category", ""),
                        "suggestion": suggestion,
                        "file": fpath,
                        "line": lineno,
                        "text": line.rstrip("\n"),
                    })
                    by_pattern[p["name"]] = by_pattern.get(p["name"], 0) + 1

    out = {
        "root": root,
        "total": len(findings),
        "findings": findings,
        "by_pattern": by_pattern,
    }
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
