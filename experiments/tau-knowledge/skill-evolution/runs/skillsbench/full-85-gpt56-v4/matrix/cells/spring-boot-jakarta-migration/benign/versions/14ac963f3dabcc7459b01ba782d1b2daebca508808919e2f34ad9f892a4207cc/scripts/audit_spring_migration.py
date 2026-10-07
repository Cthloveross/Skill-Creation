#!/usr/bin/env python3
"""Emit a deterministic static migration inventory for a Maven Spring service.

stdin JSON:
  {"root": "/path/to/project", "extensions": [".java", ".xml"]}
stdout JSON:
  {"files_scanned": int, "matches": [{"path", "line", "kind", "text"}],
   "summary": {kind: count}}
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

PATTERNS = {
    "legacy_javax_import": "import javax.",
    "rest_template": "RestTemplate",
    "security_adapter": "WebSecurityConfigurerAdapter",
    "deprecated_security_authorize": "authorizeRequests(",
    "deprecated_security_ant_matchers": "antMatchers(",
    "deprecated_security_mvc_matchers": "mvcMatchers(",
    "boot_2_reference": "spring-boot-starter-parent",
    "hibernate_reference": "hibernate",
}
DEFAULT_EXTENSIONS = {".java", ".xml", ".properties", ".yml", ".yaml"}
EXCLUDED_DIRS = {"target", ".git", ".idea", ".mvn"}


def main() -> int:
    try:
        request = json.load(sys.stdin)
        root_value = request["root"]
        extensions = set(request.get("extensions", DEFAULT_EXTENSIONS))
        if not isinstance(root_value, str) or not all(isinstance(x, str) for x in extensions):
            raise ValueError("root and extensions must be strings")
        root = Path(root_value).resolve()
        if not root.is_dir():
            raise ValueError("root is not a directory: " + str(root))
    except (json.JSONDecodeError, KeyError, ValueError, TypeError) as exc:
        print(json.dumps({"error": str(exc)}))
        return 2

    findings = []
    scanned = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file() or any(part in EXCLUDED_DIRS for part in path.parts):
            continue
        if path.suffix not in extensions:
            continue
        scanned += 1
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        rel = str(path.relative_to(root))
        for number, line in enumerate(lines, 1):
            for kind, needle in PATTERNS.items():
                if needle in line:
                    findings.append({"path": rel, "line": number, "kind": kind, "text": line.strip()})

    summary = dict(sorted(Counter(item["kind"] for item in findings).items()))
    print(json.dumps({"files_scanned": scanned, "matches": findings, "summary": summary}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
