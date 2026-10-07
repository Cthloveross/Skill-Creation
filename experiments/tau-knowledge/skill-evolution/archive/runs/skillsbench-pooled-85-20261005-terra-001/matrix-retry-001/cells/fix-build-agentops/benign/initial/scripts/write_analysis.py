#!/usr/bin/env python3
"""Atomically write the required CI-failure analysis document from JSON stdin."""
import json
import os
import sys
import tempfile
from pathlib import Path


def emit(value, code=0):
    sys.stdout.write(json.dumps(value, sort_keys=True) + "\n")
    raise SystemExit(code)


def main():
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be a JSON object")
        path_value = data.get("path")
        text = data.get("text")
        if not isinstance(path_value, str) or not path_value:
            raise ValueError("path must be a nonempty string")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("text must be a nonempty string")
        path = Path(path_value)
        if not path.is_absolute():
            raise ValueError("path must be absolute")
        if not path.parent.is_dir():
            raise ValueError("analysis file parent directory does not exist")
        payload = text if text.endswith("\n") else text + "\n"
        fd, temporary = tempfile.mkstemp(prefix=".failed_reasons.", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        emit({"ok": True, "path": str(path), "bytes": len(payload.encode("utf-8"))})
    except Exception as exc:
        emit({"ok": False, "error": str(exc)}, 2)


if __name__ == "__main__":
    main()
