#!/usr/bin/env python3
"""Inventory likely Java CI entry points without executing them.

Input JSON: {"root": "/home/travis/build/failed"} or
            {"repository": "/path/to/artifact"}.
Output JSON: {"ok": bool, "repositories": [...], "errors": [...]}.
"""
import json
import sys
from pathlib import Path

MAX_FILES = 4000
CI_NAMES = {".travis.yml", ".travis.yaml", "pom.xml", "mvnw", "mvnw.cmd",
            "gradlew", "build.gradle", "build.gradle.kts", "settings.xml"}


def is_artifact(path: Path) -> bool:
    return path.is_dir() and (path / ".git").exists() or (
        path.is_dir() and any((path / name).exists() for name in ("pom.xml", ".travis.yml", "mvnw"))
    )


def inspect(repo: Path):
    matches = []
    scanned = 0
    try:
        iterator = repo.rglob("*")
        for item in iterator:
            scanned += 1
            if scanned > MAX_FILES:
                break
            if not item.is_file():
                continue
            rel = item.relative_to(repo)
            # Dependency/build output trees are not useful entry-point evidence.
            if any(part in {".git", "target", ".m2", "node_modules", "build"} for part in rel.parts):
                continue
            name = item.name
            if name in CI_NAMES or name.endswith(".sh") or "travis" in name.lower() or "repro" in name.lower():
                matches.append(str(rel))
    except OSError as exc:
        return {"path": str(repo), "error": str(exc)}
    return {
        "path": str(repo),
        "git_directory_present": (repo / ".git").exists(),
        "candidate_entrypoints": sorted(matches),
        "scan_truncated": scanned > MAX_FILES,
    }


def main():
    try:
        request = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "repositories": [], "errors": ["invalid JSON: " + str(exc)]}))
        return
    errors = []
    repos = []
    if isinstance(request.get("repository"), str):
        candidate = Path(request["repository"]).expanduser()
        if is_artifact(candidate):
            repos.append(inspect(candidate))
        else:
            errors.append("repository is not an identifiable artifact directory: " + str(candidate))
    elif isinstance(request.get("root"), str):
        root = Path(request["root"]).expanduser()
        if not root.is_dir():
            errors.append("root is not a directory: " + str(root))
        else:
            # Expected layout is root/repository-id/artifact-id. Also accept a root
            # that itself is an artifact to keep the helper reusable.
            if is_artifact(root):
                repos.append(inspect(root))
            else:
                for first in sorted(root.iterdir()):
                    if not first.is_dir():
                        continue
                    if is_artifact(first):
                        repos.append(inspect(first))
                    else:
                        for second in sorted(first.iterdir()):
                            if is_artifact(second):
                                repos.append(inspect(second))
    else:
        errors.append("provide string field 'root' or 'repository'")
    print(json.dumps({"ok": not errors, "repositories": repos, "errors": errors}, indent=2))


if __name__ == "__main__":
    main()
