#!/usr/bin/env python3
"""Write the standalone solution to the deliverable path and ensure pymatgen.

stdin : {} or {"path": "/root/workspace/solution.py"}
stdout: {"written": <path>, "pymatgen": <bool>, "error": <optional str>}
"""
import json
import os
import subprocess
import sys


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:
        payload = {}
    dest = payload.get("path", "/root/workspace/solution.py")

    here = os.path.dirname(os.path.abspath(__file__))
    template = os.path.join(here, "..", "references", "solution_template.py")
    template = os.path.normpath(template)
    with open(template, "r", encoding="utf-8") as fh:
        content = fh.read()

    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "w", encoding="utf-8") as fh:
        fh.write(content)

    pymatgen_ok = True
    err = None
    try:
        import pymatgen  # noqa: F401
    except Exception:
        pymatgen_ok = False
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "--quiet", "pymatgen"]
            )
            import importlib
            importlib.invalidate_caches()
            import pymatgen  # noqa: F401
            pymatgen_ok = True
        except Exception as exc:  # pragma: no cover
            err = str(exc)

    out = {"written": dest, "pymatgen": pymatgen_ok}
    if err:
        out["error"] = err
    print(json.dumps(out))


if __name__ == "__main__":
    main()
