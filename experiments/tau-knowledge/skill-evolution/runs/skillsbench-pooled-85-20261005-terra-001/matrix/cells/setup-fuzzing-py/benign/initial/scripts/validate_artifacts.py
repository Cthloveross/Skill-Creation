#!/usr/bin/env python3
"""Structurally validate fuzzing deliverables without executing them.

Input JSON:
  libraries_file: path to a one-path-per-line inventory (default /app/libraries.txt)
  expected_count: expected number of projects (default 5)
Output JSON has ok, errors, warnings, and per-project checks.
"""
import json
import sys
from pathlib import Path

DRIVER_MARKERS = ("import atheris", "FuzzedDataProvider", "def TestOneInput", "atheris.Setup", "atheris.Fuzz")


def main() -> int:
    try:
        req = json.load(sys.stdin)
        inventory = Path(req.get("libraries_file", "/app/libraries.txt"))
        expected = int(req.get("expected_count", 5))
        errors, warnings, results = [], [], []
        if not inventory.is_file():
            errors.append("missing libraries file: %s" % inventory)
            lines = []
        else:
            lines = [line.strip() for line in inventory.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()]
        if len(lines) != expected:
            errors.append("expected %d library paths, found %d" % (expected, len(lines)))
        if len(set(lines)) != len(lines):
            errors.append("libraries file contains duplicate paths")
        for line in lines:
            root = Path(line)
            item = {"root": line, "errors": [], "warnings": []}
            if not root.is_absolute() or not root.is_dir():
                item["errors"].append("path is not an existing absolute directory")
                results.append(item)
                continue
            notes = root / "notes_for_testing.txt"
            driver = root / "fuzz.py"
            log = root / "fuzz.log"
            vpython = root / ".venv" / "bin" / "python"
            if not notes.is_file() or not notes.read_text(encoding="utf-8", errors="replace").strip():
                item["errors"].append("missing or empty notes_for_testing.txt")
            if not vpython.is_file():
                item["errors"].append("missing .venv/bin/python")
            if not driver.is_file():
                item["errors"].append("missing fuzz.py")
            else:
                source = driver.read_text(encoding="utf-8", errors="replace")
                absent = [marker for marker in DRIVER_MARKERS if marker not in source]
                if absent:
                    item["errors"].append("fuzz.py missing required markers: " + ", ".join(absent))
                if "instrument_imports" not in source and "instrument_all" not in source:
                    item["warnings"].append("no obvious target import instrumentation marker")
            if not log.is_file() or not log.read_text(encoding="utf-8", errors="replace").strip():
                item["errors"].append("missing or empty fuzz.log (stderr capture required)")
            else:
                log_text = log.read_text(encoding="utf-8", errors="replace")
                healthy = ("INITED" in log_text or "NEW" in log_text or "pulse" in log_text or
                           "Done " in log_text or "ERROR: libFuzzer" in log_text or
                           "Test unit written to" in log_text)
                if not healthy:
                    item["warnings"].append("log lacks recognizable libFuzzer progress/completion/crash markers")
            errors.extend("%s: %s" % (line, e) for e in item["errors"])
            warnings.extend("%s: %s" % (line, w) for w in item["warnings"])
            results.append(item)
        print(json.dumps({"ok": not errors, "errors": errors, "warnings": warnings,
                          "projects": results}, indent=2, sort_keys=True))
        return 0 if not errors else 1
    except Exception as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)], "warnings": [], "projects": []}, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
