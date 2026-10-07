#!/usr/bin/env python3
"""Perform conservative structural validation for a Python-to-Scala translation.

Input JSON:
{"python_path":"...", "scala_path":"...", "required_package":"tokenizer",
 "required_symbols":["..."]}
Output JSON includes `ok`, missing required symbols, and Python source callables not
found textually in the Scala source. This is not a compiler or semantic verifier.
"""
import ast
import json
import re
import sys
from pathlib import Path


def python_callable_names(path):
    tree = ast.parse(Path(path).read_text(encoding="utf-8"), filename=path)
    names = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        if isinstance(node, ast.ClassDef):
            for member in node.body:
                if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    names.add(member.name)
    return sorted(names)


def has_symbol(scala, symbol):
    # A word boundary avoids accepting a required API merely as part of another name.
    return re.search(r"(?<![A-Za-z0-9_$])" + re.escape(symbol) + r"(?![A-Za-z0-9_$])", scala) is not None


def main():
    try:
        request = json.load(sys.stdin)
        python_path = request["python_path"]
        scala_path = request["scala_path"]
        package = request.get("required_package")
        required = request.get("required_symbols", [])
        scala = Path(scala_path).read_text(encoding="utf-8")
        source_names = python_callable_names(python_path)
        missing_required = [name for name in required if not has_symbol(scala, name)]
        missing_source = [name for name in source_names if not has_symbol(scala, name)]
        package_ok = (package is None or re.search(
            r"(?m)^\s*package\s+" + re.escape(package) + r"\s*$", scala) is not None)
        result = {
            "ok": package_ok and not missing_required,
            "scala_path": scala_path,
            "package_ok": package_ok,
            "missing_required_symbols": missing_required,
            "python_callable_names_not_found_in_scala": missing_source,
            "notes": [
                "This validator is structural only; compile and behavior-test the result.",
                "Inherited methods or intentionally renamed private helpers may require manual review."
            ]
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        if not result["ok"]:
            sys.exit(1)
    except (KeyError, OSError, SyntaxError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
