#!/usr/bin/env python3
"""Validate the exact report artifact.

Input stdin: {"path": "/path/to/report.json"}. Output stdout: validated report.
"""
import json
import sys
from pathlib import Path

from build_report import InputError, fail, validate


def main():
    try:
        config = json.load(sys.stdin)
        if not isinstance(config, dict) or set(config) != {"path"} or not isinstance(config["path"], str) or not config["path"]:
            fail("stdin must be exactly an object with nonempty string path")
        path = Path(config["path"])
        if not path.is_file():
            fail(f"required report file does not exist: {path}")
        try:
            with path.open(encoding="utf-8") as handle:
                report = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            fail(f"cannot parse report JSON: {exc}")
        validate(report)
        print(json.dumps(report, ensure_ascii=False, allow_nan=False))
    except (InputError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        sys.exit(2)


if __name__ == "__main__":
    main()
