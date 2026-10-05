#!/usr/bin/env python3
"""Emit the standalone solution artifact.

Input JSON: {"output_path": "/root/workspace/solution.py"}
Output JSON: {"output_path": "...", "required_function": "..."}
"""
import ast
import json
import shutil
import sys
from pathlib import Path


def main() -> None:
    try:
        request = json.load(sys.stdin)
        output_path = Path(request["output_path"])
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise SystemExit("input must be JSON with a nonempty output_path") from exc
    if not str(output_path):
        raise SystemExit("output_path must be nonempty")

    template = Path(__file__).resolve().parent.parent / "references" / "solution_template.py"
    tree = ast.parse(template.read_text(encoding="utf-8"), filename=str(template))
    functions = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
    required = "topk_tanimoto_similarity_molecules"
    if required not in functions:
        raise SystemExit("packaged template lacks the required public function")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(template, output_path)
    print(json.dumps({"output_path": str(output_path), "required_function": required}))


if __name__ == "__main__":
    main()
