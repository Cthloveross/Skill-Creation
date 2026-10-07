#!/usr/bin/env python3
"""Emit a conservative Python AST inventory.
Input JSON: {"source": "/absolute/or/relative/file.py"}
Output JSON: {"ok": bool, "classes": [...], "functions": [...], "imports": [...]}.
"""
import ast
import json
import sys
from pathlib import Path


def args_of(node):
    args = [a.arg for a in node.args.posonlyargs + node.args.args]
    if node.args.vararg:
        args.append("*" + node.args.vararg.arg)
    args += [a.arg for a in node.args.kwonlyargs]
    if node.args.kwarg:
        args.append("**" + node.args.kwarg.arg)
    return args


def function_info(node):
    return {
        "name": node.name,
        "line": node.lineno,
        "args": args_of(node),
        "decorators": [ast.unparse(d) for d in node.decorator_list],
        "returns": ast.unparse(node.returns) if node.returns else None,
    }


def main():
    try:
        request = json.load(sys.stdin)
        path = Path(request["source"])
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        classes, functions, imports = [], [], []
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append(function_info(node))
            elif isinstance(node, ast.ClassDef):
                methods = [function_info(n) for n in node.body
                           if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
                classes.append({
                    "name": node.name,
                    "line": node.lineno,
                    "bases": [ast.unparse(b) for b in node.bases],
                    "decorators": [ast.unparse(d) for d in node.decorator_list],
                    "methods": methods,
                })
            elif isinstance(node, ast.Import):
                imports.extend(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                imports.extend(module + "." + a.name for a in node.names)
        print(json.dumps({"ok": True, "classes": classes, "functions": functions,
                          "imports": imports}, indent=2))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
