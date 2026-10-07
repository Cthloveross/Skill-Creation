#!/usr/bin/env python3
"""Emit a JSON inventory of a Python module for translation planning.

Input:  {"source_path": "/path/to/module.py"}
Output: {"ok": bool, "classes": [...], "functions": [...], "imports": [...]}.
"""
import ast
import json
import sys
from pathlib import Path


def expr_text(node):
    try:
        return ast.unparse(node)
    except Exception:
        return type(node).__name__


def arguments(node):
    positional = list(node.args.posonlyargs) + list(node.args.args)
    defaults = [None] * (len(positional) - len(node.args.defaults)) + list(node.args.defaults)
    result = []
    for arg, default in zip(positional, defaults):
        result.append({
            "name": arg.arg,
            "annotation": expr_text(arg.annotation) if arg.annotation else None,
            "default": expr_text(default) if default is not None else None,
        })
    if node.args.vararg:
        result.append({"name": "*" + node.args.vararg.arg,
                       "annotation": expr_text(node.args.vararg.annotation) if node.args.vararg.annotation else None,
                       "default": None})
    for arg, default in zip(node.args.kwonlyargs, node.args.kw_defaults):
        result.append({
            "name": arg.arg,
            "annotation": expr_text(arg.annotation) if arg.annotation else None,
            "default": expr_text(default) if default is not None else None,
        })
    if node.args.kwarg:
        result.append({"name": "**" + node.args.kwarg.arg,
                       "annotation": expr_text(node.args.kwarg.annotation) if node.args.kwarg.annotation else None,
                       "default": None})
    return result


def callable_info(node):
    return {
        "name": node.name,
        "line": node.lineno,
        "async": isinstance(node, ast.AsyncFunctionDef),
        "decorators": [expr_text(item) for item in node.decorator_list],
        "parameters": arguments(node),
        "returns": expr_text(node.returns) if node.returns else None,
        "docstring": ast.get_docstring(node),
    }


def assigned_self_attributes(function_node):
    attributes = set()
    for node in ast.walk(function_node):
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                for child in ast.walk(target):
                    if (isinstance(child, ast.Attribute) and isinstance(child.value, ast.Name)
                            and child.value.id == "self"):
                        attributes.add(child.attr)
    return sorted(attributes)


def inspect(path):
    text = Path(path).read_text(encoding="utf-8")
    tree = ast.parse(text, filename=path)
    classes, functions, imports = [], [], []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            else:
                imports.append("%s:%s" % (node.module or "", ",".join(a.name for a in node.names)))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(callable_info(node))
        elif isinstance(node, ast.ClassDef):
            methods = []
            attributes = set()
            for member in node.body:
                if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    methods.append(callable_info(member))
                    attributes.update(assigned_self_attributes(member))
            classes.append({
                "name": node.name,
                "line": node.lineno,
                "bases": [expr_text(base) for base in node.bases],
                "decorators": [expr_text(item) for item in node.decorator_list],
                "docstring": ast.get_docstring(node),
                "methods": methods,
                "instance_attributes": sorted(attributes),
            })
    return {"ok": True, "source_path": str(path), "imports": imports,
            "classes": classes, "functions": functions}


def main():
    try:
        request = json.load(sys.stdin)
        path = request["source_path"]
        print(json.dumps(inspect(path), indent=2, sort_keys=True))
    except (KeyError, OSError, SyntaxError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
