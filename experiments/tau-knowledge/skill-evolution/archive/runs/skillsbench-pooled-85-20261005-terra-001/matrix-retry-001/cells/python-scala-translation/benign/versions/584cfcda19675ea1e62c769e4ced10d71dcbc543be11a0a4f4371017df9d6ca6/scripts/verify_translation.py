#!/usr/bin/env python3
"""Conservative structural and lexical checks for a Scala 2.13 translation."""
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


def python_symbols(source):
    tree = ast.parse(source)
    symbols = set()
    structure = {"classes": [], "module_functions": [], "methods": {}}
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            symbols.add(node.name)
            structure["classes"].append(node.name)
            methods = []
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and not (
                    child.name.startswith("__") and child.name.endswith("__")
                ):
                    translated = camel_case(child.name)
                    symbols.add(translated)
                    methods.append(translated)
            structure["methods"][node.name] = methods
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not (
            node.name.startswith("__") and node.name.endswith("__")
        ):
            translated = camel_case(node.name)
            symbols.add(translated)
            structure["module_functions"].append(translated)
    return symbols, structure


def lexical_error(text):
    """Mirror simple source-only delimiter checks while ignoring strings/comments."""
    pairs = {")": "(", "]": "[", "}": "{"}
    opening = set(pairs.values())
    stack = []
    index = 0
    state = "code"
    while index < len(text):
        char = text[index]
        following = text[index:index + 2]
        triple = text[index:index + 3]
        if state == "code":
            if following == "//":
                state, index = "line_comment", index + 2
                continue
            if following == "/*":
                state, index = "block_comment", index + 2
                continue
            if triple == '\"\"\"':
                state, index = "triple_string", index + 3
                continue
            if char == '\"':
                state, index = "string", index + 1
                continue
            if char == "'":
                state, index = "char", index + 1
                continue
            if char in opening:
                stack.append(char)
            elif char in pairs:
                if not stack or stack.pop() != pairs[char]:
                    return "mismatched closing delimiter " + char
            index += 1
        elif state == "line_comment":
            if char in "\r\n":
                state = "code"
            index += 1
        elif state == "block_comment":
            if following == "*/":
                state, index = "code", index + 2
            else:
                index += 1
        elif state == "triple_string":
            if triple == '\"\"\"':
                state, index = "code", index + 3
            else:
                index += 1
        else:
            if char == "\\":
                index += 2
            elif (state == "string" and char == '\"') or (state == "char" and char == "'"):
                state, index = "code", index + 1
            else:
                index += 1
    if state != "code":
        return "unterminated " + state.replace("_", " ")
    if stack:
        return "unclosed delimiter " + stack[-1]
    return None


def apostrophe_locations(text):
    locations = []
    for offset, char in enumerate(text):
        if char == "'":
            line = text.count("\n", 0, offset) + 1
            column = offset - text.rfind("\n", 0, offset)
            locations.append(str(line) + ":" + str(column))
    return locations


def main():
    try:
        request = json.load(sys.stdin)
        python_path = Path(request["python_path"])
        scala_path = Path(request["scala_path"])
        required_package = request.get("required_package", "tokenizer")
        errors, warnings = [], []
        if not python_path.is_file():
            errors.append("Python source does not exist: " + str(python_path))
        if not scala_path.is_file():
            errors.append("Scala artifact does not exist: " + str(scala_path))
        if errors:
            print(json.dumps({"ok": False, "errors": errors, "warnings": warnings}, indent=2))
            return
        python_text = python_path.read_text(encoding="utf-8")
        scala_text = scala_path.read_text(encoding="utf-8")
        source_symbols, structure = python_symbols(python_text)
        expected = source_symbols | set(request.get("expected_symbols", []))
        if not re.search(r"(?m)^\s*package\s+" + re.escape(required_package) + r"\b", scala_text):
            errors.append("Missing required package declaration: package " + required_package)
        lexical = lexical_error(scala_text)
        if lexical:
            errors.append("Scala lexical readiness failure: " + lexical)
        apostrophes = apostrophe_locations(scala_text)
        if apostrophes:
            errors.append("Apostrophes are prohibited for conservative source readiness; found at " + ", ".join(apostrophes[:10]))
        forbidden = re.search(r"\b(?:enum|given|using|extension|opaque\s+type)\b", scala_text)
        if forbidden:
            errors.append("Scala 3-only keyword token found: " + forbidden.group(0))
        types = set(re.findall(r"(?m)^\s*(?:sealed\s+|final\s+|abstract\s+)*(?:case\s+)?(?:class|trait|object)\s+([A-Za-z_]\w*)", scala_text))
        methods = set(re.findall(r"\bdef\s+([A-Za-z_]\w*)", scala_text))
        missing = sorted(expected - types - methods)
        if missing:
            errors.append("Expected source-derived or requested Scala symbols not found: " + ", ".join(missing))
        if "null" in scala_text:
            warnings.append("Source contains null; review whether Option is appropriate.")
        if re.search(r"scala\.collection\.mutable", scala_text):
            warnings.append("Mutable Scala collections are used; verify necessity.")
        if re.search(r"\bvar\s+", scala_text):
            warnings.append("Mutable bindings are used; review whether vals suffice.")
        if not re.search(r"\bsealed\s+trait\s+TokenType\b", scala_text):
            warnings.append("TokenType is not visibly a sealed trait.")
        print(json.dumps({
            "ok": not errors,
            "errors": errors,
            "warnings": warnings,
            "python_derived_symbols": sorted(source_symbols),
            "python_structure": structure,
            "expected_symbols": sorted(expected),
            "declared_scala_types": sorted(types),
            "declared_scala_methods": sorted(methods),
        }, indent=2))
    except Exception as exc:
        print(json.dumps({"ok": False, "errors": [type(exc).__name__ + ": " + str(exc)], "warnings": []}))


if __name__ == "__main__":
    main()
