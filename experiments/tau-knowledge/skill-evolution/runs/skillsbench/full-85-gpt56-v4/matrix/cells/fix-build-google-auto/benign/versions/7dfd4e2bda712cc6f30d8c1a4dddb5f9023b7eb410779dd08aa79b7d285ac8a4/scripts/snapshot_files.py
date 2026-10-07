#!/usr/bin/env python3
"""Create a safe pre-edit baseline for a specific list of repository files."""
import json
import shutil
import sys
from pathlib import Path


def safe_relative(value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or str(path) in ("", "."):
        raise ValueError("path must be a nonempty repository-relative path: %r" % value)
    return path


def main() -> int:
    try:
        request = json.load(sys.stdin)
        root = Path(request["root"]).expanduser().resolve()
        baseline = Path(request["baseline"]).expanduser().resolve()
        raw_paths = request["paths"]
        if not root.is_dir():
            raise ValueError("root is not a directory: %s" % root)
        if not isinstance(raw_paths, list) or not raw_paths:
            raise ValueError("paths must be a nonempty list")
        if baseline == root or root in baseline.parents:
            raise ValueError("baseline must be outside the repository root")
        if baseline.exists():
            raise ValueError("baseline already exists; choose a new empty baseline path")
        baseline.mkdir(parents=True)
        entries = []
        seen = set()
        for raw in raw_paths:
            rel = safe_relative(raw)
            key = rel.as_posix()
            if key in seen:
                raise ValueError("duplicate path: %s" % key)
            seen.add(key)
            source = root / rel
            exists = source.exists()
            if exists and (source.is_symlink() or not source.is_file()):
                raise ValueError("only regular files may be snapshotted: %s" % key)
            if exists:
                destination = baseline / rel
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
            entries.append({"path": key, "existed": exists})
        manifest = {"root": str(root), "entries": entries}
        manifest_path = baseline / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"ok": True, "baseline": str(baseline), "manifest": str(manifest_path), "entries": entries}, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
