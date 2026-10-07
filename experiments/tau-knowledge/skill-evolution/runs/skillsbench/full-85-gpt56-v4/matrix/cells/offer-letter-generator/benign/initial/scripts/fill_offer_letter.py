#!/usr/bin/env python3
"""CLI entrypoint. Reads JSON on stdin and emits one JSON result on stdout."""
import json
import sys
from pathlib import Path

# Allow invocation directly from the packaged scripts directory.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ooxml_fill import FillError, fill_docx


def main() -> int:
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise FillError("stdin JSON must be an object")
        for key in ("template", "data", "output"):
            if not isinstance(request.get(key), str) or not request[key]:
                raise FillError("request requires a nonempty string '" + key + "'")

        with open(request["data"], "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            raise FillError("employee data JSON must be one object keyed by placeholder name")

        summary = fill_docx(request["template"], data, request["output"])
        print(json.dumps({"ok": True, **summary}, ensure_ascii=False))
        return 0
    except (OSError, ValueError, FillError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
