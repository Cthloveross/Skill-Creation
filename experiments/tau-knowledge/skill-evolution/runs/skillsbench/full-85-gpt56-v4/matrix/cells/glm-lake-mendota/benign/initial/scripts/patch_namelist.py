#!/usr/bin/env python3
"""Patch only existing scalar namelist assignments. JSON stdin -> JSON stdout."""
import json, re, sys
from pathlib import Path


def main():
    try:
        spec = json.load(sys.stdin)
        path = Path(spec["path"])
        updates = spec["updates"]
        if not isinstance(updates, dict) or not updates:
            raise ValueError("updates must be a nonempty object")
        text = path.read_text(encoding="utf-8")
        changed, missing = [], []
        # Values are deliberately raw Fortran fragments; only replace a single-line RHS.
        for key, value in updates.items():
            if not re.match(r"^[A-Za-z][A-Za-z0-9_]*$", key):
                raise ValueError(f"unsafe namelist key: {key}")
            pattern = re.compile(r"(?im)^(\s*" + re.escape(key) + r"\s*=\s*)([^!,\n]*)(\s*,?\s*(?:!.*)?$)")
            if not pattern.search(text):
                missing.append(key)
                continue
            text, count = pattern.subn(lambda m: m.group(1) + str(value) + m.group(3), text, count=1)
            if count:
                changed.append(key)
        if missing:
            print(json.dumps({"ok": False, "path": str(path), "changed": changed,
                              "missing": missing, "error": "No changes written; requested keys must already exist."}))
            return
        backup = spec.get("backup")
        if backup:
            Path(backup).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        path.write_text(text, encoding="utf-8")
        print(json.dumps({"ok": True, "path": str(path), "changed": changed, "backup": backup}))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}))

if __name__ == "__main__":
    main()
