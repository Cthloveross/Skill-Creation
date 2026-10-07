#!/usr/bin/env python3
"""Inventory Python project files and plausible fuzzable functions.
Input JSON: {"library_dir": "/absolute/path"}; output JSON with candidates.
"""
import ast
import json
import sys
from pathlib import Path

KEYWORDS = ("parse", "load", "decode", "deserialize", "from_", "format", "convert")


def main():
    try:
        request = json.load(sys.stdin)
        root = Path(request["library_dir"]).resolve()
        if not root.is_dir():
            raise ValueError("library_dir is not a directory")
        packaging = [p.name for p in root.iterdir() if p.name in {"pyproject.toml", "setup.py", "setup.cfg", "requirements.txt", "Pipfile"} or p.name.startswith("requirements")]
        files, candidates, errors = [], [], []
        ignored = {".venv", ".git", "build", "dist", "__pycache__", ".tox"}
        for path in root.rglob("*.py"):
            if any(part in ignored for part in path.parts):
                continue
            rel = str(path.relative_to(root))
            files.append(rel)
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
            except (OSError, UnicodeDecodeError, SyntaxError) as exc:
                errors.append(f"{rel}: {exc}")
                continue
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    name = node.name.lower()
                    positional = [a.arg for a in node.args.args]
                    if any(word in name for word in KEYWORDS):
                        candidates.append({"file": rel, "function": node.name, "line": node.lineno,
                                           "arguments": positional, "reason": "name suggests parsing/conversion"})
        print(json.dumps({"library_dir": str(root), "packaging_files": packaging,
                          "python_files": files, "candidates": candidates, "errors": errors}, indent=2))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(2)

if __name__ == "__main__":
    main()
