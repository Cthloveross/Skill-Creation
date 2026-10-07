#!/usr/bin/env python3
"""Check required fuzzing artifacts without executing them.
Input JSON: libraries_file, expected_count (optional), require_logs (optional).
Output JSON: {ok, errors, libraries:[{path, errors}]}.
"""
import json
import sys
from pathlib import Path

REQUIRED_DRIVER_SNIPPETS = (
    "import atheris", "atheris.instrument_imports()", "def TestOneInput(data: bytes)",
    "FuzzedDataProvider(data)", "atheris.Setup(sys.argv, TestOneInput)", "atheris.Fuzz()",
)


def main():
    try:
        req = json.load(sys.stdin)
        list_path = Path(req["libraries_file"])
        expected = req.get("expected_count")
        require_logs = bool(req.get("require_logs", False))
        errors, reports = [], []
        if not list_path.is_file():
            raise ValueError(f"missing libraries file: {list_path}")
        lines = [line.strip() for line in list_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if expected is not None and len(lines) != expected:
            errors.append(f"expected {expected} library paths, found {len(lines)}")
        if len(set(lines)) != len(lines):
            errors.append("libraries.txt contains duplicate paths")
        for raw in lines:
            root = Path(raw)
            local = []
            if not root.is_dir():
                local.append("path is not a directory")
            else:
                for name in ("notes_for_testing.txt", "fuzz.py"):
                    if not (root / name).is_file():
                        local.append(f"missing {name}")
                if not (root / ".venv").is_dir():
                    local.append("missing .venv")
                if require_logs and (not (root / "fuzz.log").is_file() or (root / "fuzz.log").stat().st_size == 0):
                    local.append("missing or empty fuzz.log")
                driver = root / "fuzz.py"
                if driver.is_file():
                    text = driver.read_text(encoding="utf-8", errors="replace")
                    for snippet in REQUIRED_DRIVER_SNIPPETS:
                        if snippet not in text:
                            local.append(f"driver lacks {snippet!r}")
            reports.append({"path": raw, "errors": local})
            errors.extend(f"{raw}: {item}" for item in local)
        print(json.dumps({"ok": not errors, "errors": errors, "libraries": reports}, indent=2))
    except Exception as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)], "libraries": []}, indent=2))
        sys.exit(2)

if __name__ == "__main__":
    main()
