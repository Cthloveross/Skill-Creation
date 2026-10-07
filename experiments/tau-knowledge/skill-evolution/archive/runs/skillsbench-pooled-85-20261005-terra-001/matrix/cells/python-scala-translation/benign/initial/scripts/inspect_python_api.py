#!/usr/bin/env python3
"""Emit a deterministic AST inventory for a Python module.

Reads a JSON request from stdin: {"source_path": str, "include_source": bool?}.
Writes one JSON response to stdout.  This program uses only the Python standard
library and never changes the inspected file.
"""
import ast
import json
import sys
from pathlib import Path


def camel_case(name):
    """Convert a normal snake_case API spelling to Scala camelCase."""
    if "_" not in name or (name.startswith("__") and name.endswith("__")):
        return name
    head, *tail = name.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in tail if part)


def annotation(node):
    if node is None:
        return None
    try:
        return ast.unparse(node)
    except Exception:
        return "<unparseable>"


def signature(node):
    args = node.args
    positional = list(args.posonlyargs) + list(args.args)
    defaults = [None] * (len(positional) - len(args.defaults)) + list(args.defaults)
    rendered = []
    for arg, default in zip(positional, defaults):
        item = arg.arg
        if arg.annotation is not None:
            item += ": " + annotation(arg.annotation)
        if default is not None:
            item += " = " + annotation(default)
        rendered.append(item)
    if args.vararg:
        rendered.append("*" + args.vararg.arg)
    elif args.kwonlyargs:
        rendered.append("*")
    for arg, default in zip(args.kwonlyargs, args.kw_defaults):
        item = arg.arg
        if arg.annotation is not None:
            item += ": " + annotation(arg.annotation)
        if default is not None:
            item += " = " + annotation(default)
        rendered.append(item)
    if args.kwarg:
        rendered.append("**" + args.kwarg.arg)
    result = "(" + ", ".join(rendered) + ")"
    if node.returns is not None:
        result += " -> " + annotation(node.returns)
    return result


def function_info(node, source, include_source):
    info = {
        "name": node.name,
        "scala_name": camel_case(node.name),
        "signature": signature(node),
        "decorators": [annotation(item) for item in node.decorator_list],
        "return_annotation": annotation(node.returns),
        "line": node.lineno,
        "end_line": getattr(node, "end_lineno", node.lineno),
        "docstring": ast.get_docstring(node),
    }
    if include_source:
        info["source"] = ast.get_source_segment(source, node)
    return info


def class_info(node, source, include_source):
    methods = []
    nested = []
    attributes = []
    for item in node.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            methods.append(function_info(item, source, include_source))
        elif isinstance(item, ast.ClassDef):
            nested.append(item.name)
        elif isinstance(item, (ast.Assign, ast.AnnAssign)):
            targets = item.targets if isinstance(item, ast.Assign) else [item.target]
            attributes.extend(
                target.id for target in targets if isinstance(target, ast.Name)
            )
    info = {
        "name": node.name,
        "bases": [annotation(base) for base in node.bases],
        "decorators": [annotation(item) for item in node.decorator_list],
        "line": node.lineno,
        "end_line": getattr(node, "end_lineno", node.lineno),
        "docstring": ast.get_docstring(node),
        "class_attributes": attributes,
        "methods": methods,
        "nested_classes": nested,
    }
    if include_source:
        info["source"] = ast.get_source_segment(source, node)
    return info


def main():
    try:
        request = json.load(sys.stdin)
        source_path = Path(request["source_path"])
        include_source = bool(request.get("include_source", False))
        source = source_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(source_path))
    except (KeyError, OSError, UnicodeError, SyntaxError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return

    imports = []
    assignments = []
    classes = []
    functions = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            prefix = "." * node.level + (node.module or "")
            imports.extend(prefix + ":" + alias.name for alias in node.names)
        elif isinstance(node, ast.ClassDef):
            classes.append(class_info(node, source, include_source))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(function_info(node, source, include_source))
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            assignments.extend(target.id for target in targets if isinstance(target, ast.Name))

    public_functions = [f["name"] for f in functions if not f["name"].startswith("_")]
    public_methods = [
        method["name"]
        for clazz in classes
        for method in clazz["methods"]
        if not method["name"].startswith("_")
    ]
    report = {
        "ok": True,
        "source_path": str(source_path),
        "imports": imports,
        "top_level_assignments": assignments,
        "classes": classes,
        "functions": functions,
        "public_api_mapping": {
            name: camel_case(name)
            for name in sorted(set(public_functions + public_methods))
        },
    }
    print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))


if __name__ == "__main__":
    main()
