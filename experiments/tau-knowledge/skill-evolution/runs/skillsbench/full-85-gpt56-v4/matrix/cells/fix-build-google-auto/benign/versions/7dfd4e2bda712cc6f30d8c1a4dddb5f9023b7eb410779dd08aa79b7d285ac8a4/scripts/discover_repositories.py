#!/usr/bin/env python3
"""Discover candidate Git checkouts below a task's failed-build directory."""
import json
import sys
from pathlib import Path


def main() -> int:
    try:
        request = json.load(sys.stdin)
        base = Path(request.get("base", "/home/travis/build/failed")).expanduser().resolve()
        if not base.is_dir():
            raise ValueError("base is not an existing directory: %s" % base)
        repositories = []
        for marker in sorted(base.rglob(".git")):
            # A .git directory is normal; a .git file can denote a worktree.
            if not (marker.is_dir() or marker.is_file()):
                continue
            root = marker.parent
            # Avoid treating a nested repository twice through a descendant marker.
            if any(root.is_relative_to(Path(item["root"])) for item in repositories):
                continue
            interesting = []
            for name in (".travis.yml", "pom.xml", "mvnw", "gradlew", "README.md"):
                if (root / name).exists():
                    interesting.append(name)
            for child in sorted(root.iterdir()):
                if child.is_file() and (child.suffix == ".sh" or "repro" in child.name.lower()):
                    interesting.append(child.name)
            repositories.append({"root": str(root), "candidate_files": interesting})
        print(json.dumps({"ok": True, "base": str(base), "repositories": repositories}, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
