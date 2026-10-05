#!/usr/bin/env python3
"""Perform conservative structural checks on a directly authored Scala translation."""
import ast
import json
import re
import sys
from pathlib import Path


def camel_case(name):
    if name.startswith("__") and name.endswith("__"):
        return name
    prefix = "_" if name.startswith("_") else ""
    parts = name.lstrip("_").split("_")
    return prefix + parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])


def python_symbols(text):
    tree = ast.parse(text)
    symbols = set()
    details = {"classes": [], "module_functions": [], "methods": {}}
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            symbols.add(node.name)
            details["classes"].append(node.name)
            method_names = []
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and not (child.name.startswith("__") and child.name.endswith("__")):
                    translated = camel_case(child.name)
                    symbols.add(translated)
                    method_names.append(translated)
            details["methods"][node.name] = method_names
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not (node.name.startswith("__") and node.name.endswith("__")):
                translated = camel_case(node.name)
                symbols.add(translated)
                details["module_functions"].append(translated)
    return symbols, details


def main():
    try:
        request = json.load(sys.stdin)
        python_path = Path(request["python_path"])
        scala_path = Path(request["scala_path"])
        required_package = request.get("required_package", "tokenizer")
        extra = set(request.get("expected_symbols", []))
        errors = []
        warnings = []
        if not python_path.is_file():
            errors.append("Python source does not exist: " + str(python_path))
        if not scala_path.is_file():
            errors.append("Scala artifact does not exist: " + str(scala_path))
        if errors:
            print(json.dumps({"ok": False, "errors": errors, "warnings": warnings}, indent=2))
            return
        python_text = python_path.read_text(encoding="utf-8")
        scala_text = scala_path.read_text(encoding="utf-8")
        source_symbols, source_details = python_symbols(python_text)
        expected = source_symbols | extra
        package_pattern = r"(?m)^\s*package\s+" + re.escape(required_package) + r"\s*(?:$|//)"
        if not re.search(package_pattern, scala_text):
            errors.append("Missing required package declaration: package " + required_package)
        declared_types = set(re.findall(r"(?m)^\s*(?:sealed\s+|final\s+|abstract\s+)*(?:case\s+)?(?:class|trait|object)\s+([A-Za-z_]\w*)", scala_text))
        declared_methods = set(re.findall(r"\bdef\s+([A-Za-z_]\w*)", scala_text))
        declared = declared_types | declared_methods
        missing = sorted(expected - declared)
        if missing:
            errors.append("Expected source-derived or requested Scala symbols not found: " + ", ".join(missing))
        if "null" in scala_text:
            warnings.append("The Scala source contains 'null'; review whether Option can represent absence instead.")
        if re.search(r"scala\.collection\.mutable", scala_text):
            warnings.append("Mutable Scala collections are used; verify they are internal and behaviorally necessary.")
        if re.search(r"\bvar\s+", scala_text):
            warnings.append("Mutable bindings are used; review whether immutable vals are practical.")
        if not re.search(r"\bsealed\s+trait\s+TokenType\b", scala_text):
            warnings.append("TokenType is not visibly a sealed trait; verify enum exhaustiveness and requirement compliance.")
        print(json.dumps({
            "ok": not errors,
            "errors": errors,
            "warnings": warnings,
            "python_derived_symbols": sorted(source_symbols),
            "python_structure": source_details,
            "expected_symbols": sorted(expected),
            "declared_scala_types": sorted(declared_types),
            "declared_scala_methods": sorted(declared_methods),
        }, indent=2))
    except Exception as exc:
        print(json.dumps({"ok": False, "errors": [type(exc).__name__ + ": " + str(exc)], "warnings": []}))


if __name__ == "__main__":
    main()
