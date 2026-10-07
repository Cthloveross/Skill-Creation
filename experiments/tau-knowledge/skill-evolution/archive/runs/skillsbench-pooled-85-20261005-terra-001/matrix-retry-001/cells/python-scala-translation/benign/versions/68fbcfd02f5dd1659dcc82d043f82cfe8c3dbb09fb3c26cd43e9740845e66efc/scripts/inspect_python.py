#!/usr/bin/env python3
"""Emit a JSON inventory of a Python module for a source-to-Scala translation."""
import ast
import hashlib
import json
import sys
from pathlib import Path


def camel_case(name):
    if name.startswith("__") and name.endswith("__"):
        return name
    prefix = "_" if name.startswith("_") else ""
    parts = name.lstrip("_").split("_")
    return prefix + parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])


def unparse(node):
    try:
        return ast.unparse(node)
    except Exception:
        return None


def argument_inventory(args):
    positional = list(args.posonlyargs) + list(args.args)
    default_start = len(positional) - len(args.defaults)
    result = []
    for index, arg in enumerate(positional):
        result.append({
            "name": arg.arg,
            "annotation": unparse(arg.annotation) if arg.annotation else None,
            "default": unparse(args.defaults[index - default_start]) if index >= default_start else None,
        })
    return {
        "positional": result,
        "vararg": args.vararg.arg if args.vararg else None,
        "keyword_only": [
            {
                "name": arg.arg,
                "annotation": unparse(arg.annotation) if arg.annotation else None,
                "default": unparse(default) if default is not None else None,
            }
            for arg, default in zip(args.kwonlyargs, args.kw_defaults)
        ],
        "kwarg": args.kwarg.arg if args.kwarg else None,
    }


def function_inventory(node, source):
    segment = ast.get_source_segment(source, node)
    return {
        "name": node.name,
        "scala_expected_name": camel_case(node.name),
        "async": isinstance(node, ast.AsyncFunctionDef),
        "decorators": [unparse(item) for item in node.decorator_list],
        "arguments": argument_inventory(node.args),
        "returns": unparse(node.returns) if node.returns else None,
        "docstring": ast.get_docstring(node),
        "line": node.lineno,
        "end_line": getattr(node, "end_lineno", node.lineno),
        "source": segment,
    }


def class_inventory(node, source):
    methods = [
        function_inventory(child, source)
        for child in node.body
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    assignments = [
        ast.get_source_segment(source, child)
        for child in node.body
        if isinstance(child, (ast.Assign, ast.AnnAssign))
    ]
    return {
        "name": node.name,
        "bases": [unparse(base) for base in node.bases],
        "decorators": [unparse(item) for item in node.decorator_list],
        "docstring": ast.get_docstring(node),
        "line": node.lineno,
        "end_line": getattr(node, "end_lineno", node.lineno),
        "class_assignments": assignments,
        "methods": methods,
    }


def main():
    try:
        request = json.load(sys.stdin)
        source_path = Path(request["source_path"])
        text = source_path.read_text(encoding="utf-8")
        tree = ast.parse(text, filename=str(source_path))
        imports = []
        assignments = []
        functions = []
        classes = []
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                imports.append(unparse(node))
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                assignments.append({"line": node.lineno, "source": ast.get_source_segment(text, node)})
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append(function_inventory(node, text))
            elif isinstance(node, ast.ClassDef):
                classes.append(class_inventory(node, text))
        public_symbols = [item["scala_expected_name"] for item in functions if not item["name"].startswith("_")]
        public_symbols += [item["name"] for item in classes if not item["name"].startswith("_")]
        print(json.dumps({
            "ok": True,
            "source_path": str(source_path),
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "imports": imports,
            "module_assignments": assignments,
            "module_functions": functions,
            "classes": classes,
            "public_scala_symbol_checklist": public_symbols,
        }, indent=2, ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": type(exc).__name__, "message": str(exc)}))


if __name__ == "__main__":
    main()
