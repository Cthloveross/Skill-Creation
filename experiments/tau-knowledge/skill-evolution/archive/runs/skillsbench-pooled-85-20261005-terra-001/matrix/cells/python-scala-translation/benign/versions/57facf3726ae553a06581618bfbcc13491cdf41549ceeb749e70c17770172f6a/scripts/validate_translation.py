#!/usr/bin/env python3
"""Perform conservative structural validation of a Python-to-Scala translation.

JSON stdin: {"source_path": str, "scala_path": str, "package": str?}.
JSON stdout: validation report.  This is deliberately not a Scala parser or
compiler; compile using the environment's real build after this check.
"""
import ast
import json
import re
import sys
from pathlib import Path

TASK_TYPES = {
    "TokenType", "Token", "BaseTokenizer", "StringTokenizer", "NumericTokenizer",
    "TemporalTokenizer", "UniversalTokenizer", "WhitespaceTokenizer", "TokenizerBuilder",
}
TASK_OPERATIONS = {"tokenize", "tokenizeBatch", "toToken", "withMetadata"}


def camel_case(name):
    if "_" not in name or (name.startswith("__") and name.endswith("__")):
        return name
    first, *rest = name.split("_")
    return first + "".join(part[:1].upper() + part[1:] for part in rest if part)


def strip_comments_and_strings(text):
    """Mask comments and literals while preserving declaration punctuation."""
    # This intentionally conservative scanner prevents comments/docstrings from
    # satisfying a declaration regex. Scala interpolated strings are also masked.
    result = []
    i = 0
    n = len(text)
    while i < n:
        if text.startswith("//", i):
            end = text.find("\n", i)
            if end < 0:
                end = n
            result.append(" " * (end - i))
            i = end
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            end = n if end < 0 else end + 2
            result.append("".join("\n" if c == "\n" else " " for c in text[i:end]))
            i = end
        elif text.startswith('\"\"\"', i):
            end = text.find('\"\"\"', i + 3)
            end = n if end < 0 else end + 3
            result.append("".join("\n" if c == "\n" else " " for c in text[i:end]))
            i = end
        elif text[i] == '"':
            start = i
            i += 1
            while i < n:
                if text[i] == "\\":
                    i += 2
                elif i < n and text[i] == '"':
                    i += 1
                    break
                else:
                    i += 1
            result.append("".join("\n" if c == "\n" else " " for c in text[start:i]))
        elif text[i] == "'":
            start = i
            i += 1
            while i < n:
                if text[i] == "\\":
                    i += 2
                elif i < n and text[i] == "'":
                    i += 1
                    break
                else:
                    i += 1
            result.append("".join("\n" if c == "\n" else " " for c in text[start:i]))
        else:
            result.append(text[i])
            i += 1
    return "".join(result)


def python_public_symbols(tree):
    classes = []
    functions = []
    for item in tree.body:
        if isinstance(item, ast.ClassDef) and not item.name.startswith("_"):
            classes.append(item.name)
            for child in item.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if not child.name.startswith("_"):
                        functions.append(child.name)
        elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not item.name.startswith("_"):
                functions.append(item.name)
    return sorted(set(classes)), sorted(set(functions))


def main():
    errors = []
    warnings = []
    try:
        request = json.load(sys.stdin)
        source_path = Path(request["source_path"])
        scala_path = Path(request["scala_path"])
        package = request.get("package", "tokenizer")
        tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
        scala = scala_path.read_text(encoding="utf-8")
    except (KeyError, OSError, UnicodeError, SyntaxError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)], "warnings": []}, indent=2))
        return

    classes, functions = python_public_symbols(tree)
    expected = set(classes) | {camel_case(name) for name in functions}
    expected |= TASK_TYPES | TASK_OPERATIONS
    masked = strip_comments_and_strings(scala)

    if not re.search(r"(?m)^\s*package\s+" + re.escape(package) + r"\s*(?:\n|$)", masked):
        errors.append("Missing required package declaration: package " + package)

    declaration_pattern = re.compile(
        r"\b(?:sealed\s+)?(?:abstract\s+)?(?:case\s+)?(?:class|trait|object|def)\s+([A-Za-z_][A-Za-z0-9_]*)\b"
    )
    found = sorted(set(declaration_pattern.findall(masked)))
    missing = sorted(expected - set(found))
    if missing:
        errors.append("Missing Scala declarations: " + ", ".join(missing))

    if "null" in masked:
        warnings.append("Found 'null'; review whether Option can represent absence instead.")
    if "sealed trait TokenType" not in masked:
        warnings.append("TokenType is not visibly declared as a sealed trait; verify exhaustive enum modeling.")
    if not re.search(r"\bcase\s+(?:class|object)\s+Token\b", masked):
        warnings.append("Token is not visibly a case class/object; verify immutable value modeling.")

    report = {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "python_symbols": {"classes": classes, "functions": functions},
        "expected_scala_names": sorted(expected),
        "found_scala_declarations": found,
    }
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
