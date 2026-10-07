#!/usr/bin/env python3
"""Emit a conservative AST inventory for a supplied Python reference module.

Input JSON: {"path": "/absolute/or/relative/module.py"}
Output JSON: {"path": str, "imports": [str], "classes": [...], "functions": [...]}
"""
import ast
import json
import sys
from pathlib import Path


def annotation_text(node):
    if node is None:
        return None
    try:
        return ast.unparse(node)
    except Exception:
        return "<unparseable>"


def arguments(node):
    positional = list(node.args.posonlyargs) + list(node.args.args)
    defaults = [None] * (len(positional) - len(node.args.defaults)) + list(node.args.defaults)
    items = []
    for arg, default in zip(positional, defaults):
        entry = {"name": arg.arg, "annotation": annotation_text(arg.annotation)}
        if default is not None:
            entry["default"] = annotation_text(default)
        items.append(entry)
    if node.args.vararg:
        items.append({"name": "*" + node.args.vararg.arg, "annotation": annotation_text(node.args.vararg.annotation)})
    for arg, default in zip(node.args.kwonlyargs, node.args.kw_defaults):
        entry = {"name": arg.arg, "annotation": annotation_text(arg.annotation), "keyword_only": True}
        if default is not None:
            entry["default"] = annotation_text(default)
        items.append(entry)
    if node.args.kwarg:
        items.append({"name": "**" + node.args.kwarg.arg, "annotation": annotation_text(node.args.kwarg.annotation)})
    return items


def main():
    request = json.load(sys.stdin)
    path = Path(request["path"])
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(path))
    imports, classes, functions = [], [], []
    for node in tree.body:
        if isinstance(node, ast.Import):
            imports.extend(alias.name if alias.asname is None else alias.name + " as " + alias.asname for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            prefix = "." * node.level + (node.module or "")
            imports.extend("from " + prefix + " import " + alias.name + (" as " + alias.asname if alias.asname else "") for alias in node.names)
        elif isinstance(node, ast.ClassDef):
            fields = []
            methods = []
            for member in node.body:
                if isinstance(member, ast.AnnAssign) and isinstance(member.target, ast.Name):
                    fields.append({"name": member.target.id, "annotation": annotation_text(member.annotation), "default": annotation_text(member.value)})
                elif isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    methods.append({"name": member.name, "args": arguments(member), "returns": annotation_text(member.returns), "line": member.lineno})
            classes.append({"name": node.name, "bases": [annotation_text(x) for x in node.bases], "fields": fields, "methods": methods, "line": node.lineno})
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append({"name": node.name, "args": arguments(node), "returns": annotation_text(node.returns), "line": node.lineno})
    print(json.dumps({"path": str(path), "imports": imports, "classes": classes, "functions": functions}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
