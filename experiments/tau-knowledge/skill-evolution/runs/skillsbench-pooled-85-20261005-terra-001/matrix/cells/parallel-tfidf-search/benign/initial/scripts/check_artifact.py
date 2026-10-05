#!/usr/bin/env python3
"""Import a completed artifact and verify its required public call signatures.

stdin JSON:
  {"solution_path": "/root/workspace/parallel_solution.py",
   "sequential_path": "/root/workspace/sequential.py"}
stdout JSON includes ok, errors, and the discovered signatures.  This deliberately
checks only importability and interface shape; semantic comparison needs task data.
"""
import importlib.util
import inspect
import json
import sys
from pathlib import Path

EXPECTED = {
    "build_tfidf_index_parallel": ["documents", "num_workers", "chunk_size"],
    "batch_search_parallel": ["queries", "index", "top_k", "num_workers", "documents"],
}


def load_module(module_name, path):
    spec = importlib.util.spec_from_file_location(module_name, str(path))
    if spec is None or spec.loader is None:
        raise ImportError("could not create import specification for " + str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def main():
    errors = []
    discovered = {}
    try:
        request = json.load(sys.stdin)
        solution_path = Path(request["solution_path"]).resolve()
        sequential_path = Path(request["sequential_path"]).resolve()
        if not solution_path.is_file():
            raise FileNotFoundError(str(solution_path))
        if not sequential_path.is_file():
            raise FileNotFoundError(str(sequential_path))
        for parent in (str(sequential_path.parent), str(solution_path.parent)):
            if parent not in sys.path:
                sys.path.insert(0, parent)
        # Register under the conventional name so a normal `import sequential` in
        # the artifact receives the exact checked module.
        load_module("sequential", sequential_path)
        module = load_module("parallel_solution_checked", solution_path)
        for name, expected_names in EXPECTED.items():
            value = getattr(module, name, None)
            if not callable(value):
                errors.append(name + " is missing or not callable")
                continue
            signature = inspect.signature(value)
            names = [param.name for param in signature.parameters.values()]
            discovered[name] = str(signature)
            if names != expected_names:
                errors.append(name + " parameters are " + repr(names) +
                              ", expected " + repr(expected_names))
    except Exception as exc:
        errors.append(type(exc).__name__ + ": " + str(exc))
    print(json.dumps({"ok": not errors, "errors": errors, "signatures": discovered},
                     sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
