#!/usr/bin/env python3
"""Report declared Python API details without importing the target module.

stdin JSON:  {"path": "/absolute/or/relative/module.py"}
stdout JSON: {"ok": bool, "functions": [...], "classes": [...], "imports": [...]}.
"""
import ast
import json
import sys
from pathlib import Path


def _argument_names(args):
    ordered = list(args.posonlyargs) + list(args.args)
    names = [arg.arg for arg in ordered]
    if args.vararg:
        names.append("*" + args.vararg.arg)
    names.extend(arg.arg for arg in args.kwonlyargs)
    if args.kwarg:
        names.append("**" + args.kwarg.arg)
    return names


def _function(node):
    return {
        "name": node.name,
        "line": node.lineno,
        "arguments": _argument_names(node.args),
        "decorators": [ast.unparse(d) for d in node.decorator_list],
    }


def main():
    try:
        request = json.load(sys.stdin)
        path = Path(request["path"])
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        functions = []
        classes = []
        imports = []
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append(_function(node))
            elif isinstance(node, ast.ClassDef):
                methods = [_function(member) for member in node.body
                           if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef))]
                classes.append({"name": node.name, "line": node.lineno, "methods": methods})
            elif isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                imports.extend(module + "." + alias.name for alias in node.names)
        print(json.dumps({"ok": True, "functions": functions, "classes": classes,
                          "imports": imports}, sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": type(exc).__name__, "message": str(exc)},
                         sort_keys=True))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
