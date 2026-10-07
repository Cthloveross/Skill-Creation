#!/usr/bin/env python3
"""Inventory a Maven Spring migration without modifying the project.

Input JSON: {"root": absolute_or_relative_project_path,
             "target_boot": optional expected major.minor string,
             "target_java": optional expected Java version string}
Output JSON: {"root", "pom", "matches", "summary", "errors"}.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

PATTERNS = {
    "legacy_javax_ee": r"\bjavax\.(?:persistence|validation|servlet|annotation|transaction|ws\.rs)\.",
    "rest_template": r"\bRestTemplate\b",
    "web_security_configurer_adapter": r"\bWebSecurityConfigurerAdapter\b",
    "legacy_ant_matchers": r"\.antMatchers\s*\(",
    "legacy_authorize_requests": r"\.authorizeRequests\s*\(",
    "legacy_security_and": r"\.and\s*\(\s*\)",
    "legacy_boot_namespace": r"org\.springframework\.boot\.2\.",
}

SKIP_DIRS = {"target", ".git", ".idea", ".gradle", "node_modules"}
TEXT_SUFFIXES = {".java", ".xml", ".properties", ".yml", ".yaml"}


def read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def pom_inventory(pom: Path, target_boot: str | None, target_java: str | None) -> dict[str, Any]:
    result: dict[str, Any] = {"exists": pom.is_file(), "properties": {}, "parent": {}, "dependencies": [], "warnings": []}
    if not pom.is_file():
        result["warnings"].append("No pom.xml found at root")
        return result
    text = read_text(pom) or ""
    for name in ("java.version", "maven.compiler.release", "maven.compiler.source", "maven.compiler.target"):
        found = re.search(r"<" + re.escape(name) + r">\s*([^<]+?)\s*</" + re.escape(name) + r">", text)
        if found:
            result["properties"][name] = found.group(1).strip()
    parent = re.search(r"<parent>(.*?)</parent>", text, re.DOTALL)
    if parent:
        parent_text = parent.group(1)
        for name in ("groupId", "artifactId", "version"):
            found = re.search(r"<" + name + r">\s*([^<]+?)\s*</" + name + r">", parent_text)
            if found:
                result["parent"][name] = found.group(1).strip()
    for block in re.findall(r"<dependency>(.*?)</dependency>", text, re.DOTALL):
        item: dict[str, str] = {}
        for name in ("groupId", "artifactId", "version", "scope"):
            found = re.search(r"<" + name + r">\s*([^<]+?)\s*</" + name + r">", block)
            if found:
                item[name] = found.group(1).strip()
        if item:
            result["dependencies"].append(item)
    boot_version = result["parent"].get("version", "")
    if target_boot and "spring-boot" in result["parent"].get("artifactId", "") and not boot_version.startswith(target_boot + "."):
        result["warnings"].append("Spring Boot parent is not in requested " + target_boot + ".x line: " + boot_version)
    if target_java:
        java_values = set(result["properties"].values())
        if java_values and target_java not in java_values:
            result["warnings"].append("Java compiler properties do not contain requested version " + target_java)
        if not java_values:
            result["warnings"].append("No standard Java compiler property found; inspect compiler plugin configuration")
    return result


def main() -> int:
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict) or not isinstance(request.get("root"), str):
            raise ValueError("input must be an object with string field 'root'")
        root = Path(request["root"]).expanduser().resolve()
        if not root.is_dir():
            raise ValueError("root is not a directory: " + str(root))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"errors": [str(exc)]}))
        return 2

    matches: dict[str, list[dict[str, Any]]] = {key: [] for key in PATTERNS}
    compiled = {key: re.compile(pattern) for key, pattern in PATTERNS.items()}
    errors: list[str] = []
    for path in root.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        text = read_text(path)
        if text is None:
            errors.append("could not read " + str(path.relative_to(root)))
            continue
        relative = str(path.relative_to(root))
        for key, pattern in compiled.items():
            lines = []
            for number, line in enumerate(text.splitlines(), start=1):
                if pattern.search(line):
                    lines.append(number)
            if lines:
                matches[key].append({"path": relative, "lines": lines})

    nonempty = {key: value for key, value in matches.items() if value}
    output = {
        "root": str(root),
        "pom": pom_inventory(root / "pom.xml", request.get("target_boot"), request.get("target_java")),
        "matches": nonempty,
        "summary": {key: sum(len(item["lines"]) for item in value) for key, value in nonempty.items()},
        "errors": errors,
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
