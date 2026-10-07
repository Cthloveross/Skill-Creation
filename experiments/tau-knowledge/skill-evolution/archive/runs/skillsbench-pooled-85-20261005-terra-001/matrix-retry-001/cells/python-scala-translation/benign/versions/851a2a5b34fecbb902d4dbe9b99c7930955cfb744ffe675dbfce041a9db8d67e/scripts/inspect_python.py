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
    return prefix + parts[0] + "".join(p[:1].upper() + p[1:] for p in parts[1:])


def text_of(node):
    try:
        return ast.unparse(node)
    except Exception:
        return None


def arguments(args):
    positional = list(args.posonlyargs) + list(args.args)
    first_default = len(positional) - len(args.defaults)
    return {
        "positional": [
            {"name": arg.arg, "annotation": text_of(arg.annotation) if arg.annotation else None,
             "default": text_of(args.defaults[i - first_default]) if i >= first_default else None}
            for i, arg in enumerate(positional)
        ],
        "vararg": args.vararg.arg if args.vararg else None,
        "keyword_only": [
            {"name": arg.arg, "annotation": text_of(arg.annotation) if arg.annotation else None,
             "default": text_of(default) if default is not None else None}
            for arg, default in zip(args.kwonlyargs, args.kw_defaults)
        ],
        "kwarg": args.kwarg.arg if args.kwarg else None,
    }


def function_info(node, source):
    return {
        "name": node.name,
        "scala_expected_name": camel_case(node.name),
        "async": isinstance(node, ast.AsyncFunctionDef),
        "decorators": [text_of(x) for x in node.decorator_list],
        "arguments": arguments(node.args),
        "returns": text_of(node.returns) if node.returns else None,
        "docstring": ast.get_docstring(node),
        "line": node.lineno,
        "end_line": getattr(node, "end_lineno", node.lineno),
        "source": ast.get_source_segment(source, node),
    }


def class_info(node, source):
    return {
        "name": node.name,
        "bases": [text_of(x) for x in node.bases],
        "decorators": [text_of(x) for x in node.decorator_list],
        "docstring": ast.get_docstring(node),
        "line": node.lineno,
        "end_line": getattr(node, "end_lineno", node.lineno),
        "class_assignments": [ast.get_source_segment(source, x) for x in node.body
                              if isinstance(x, (ast.Assign, ast.AnnAssign))],
        "methods": [function_info(x, source) for x in node.body
                    if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef))],
    }


def main():
    try:
        request = json.load(sys.stdin)
        path = Path(request["source_path"])
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        imports, assignments, functions, classes = [], [], [], []
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                imports.append(text_of(node))
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                assignments.append({"line": node.lineno, "source": ast.get_source_segment(source, node)})
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append(function_info(node, source))
            elif isinstance(node, ast.ClassDef):
                classes.append(class_info(node, source))
        public = [x["scala_expected_name"] for x in functions if not x["name"].startswith("_")]
        public += [x["name"] for x in classes if not x["name"].startswith("_")]
        print(json.dumps({"ok": True, "source_path": str(path),
                          "sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
                          "imports": imports, "module_assignments": assignments,
                          "module_functions": functions, "classes": classes,
                          "public_scala_symbol_checklist": public}, indent=2, ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": type(exc).__name__, "message": str(exc)}))


if __name__ == "__main__":
    main()
