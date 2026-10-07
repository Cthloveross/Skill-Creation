#!/usr/bin/env python3
"""Discover immediate local Python project roots and optionally write their list.

Input JSON:
  root: directory to inspect (default /app)
  expected_count: optional exact count
  write_libraries_file: optional output file path
Output JSON includes projects, candidate functions, and errors. Exit status is nonzero
for invalid input or an expected-count mismatch, but JSON is still emitted when possible.
"""
import json
import re
import sys
from pathlib import Path

MARKERS = ("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt", "Pipfile")
SKIP_PARTS = {".git", ".venv", "venv", "env", "node_modules", "build", "dist", "__pycache__"}
NAME_RE = re.compile(r"^\s*def\s+([A-Za-z_]\w*)\s*\(", re.MULTILINE)
INTERESTING = re.compile(r"(?:parse|load|decode|deserialize|format|validate|read|from_)", re.I)


def safe_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def project_summary(root: Path) -> dict:
    sources, tests, candidates = [], [], []
    for path in root.rglob("*.py"):
        if any(part in SKIP_PARTS for part in path.relative_to(root).parts):
            continue
        rel = str(path.relative_to(root))
        if "test" in path.name.lower() or "tests" in path.parts:
            tests.append(rel)
        else:
            sources.append(rel)
        text = safe_text(path)
        for name in NAME_RE.findall(text):
            if INTERESTING.search(name):
                candidates.append({"file": rel, "function": name})
    return {
        "path": str(root.resolve()),
        "markers": [m for m in MARKERS if (root / m).is_file()],
        "source_files": sources[:80],
        "test_files": tests[:80],
        "candidate_functions": candidates[:120],
    }


def main() -> int:
    try:
        request = json.load(sys.stdin)
        root = Path(request.get("root", "/app")).resolve()
        if not root.is_dir():
            raise ValueError("root is not a directory: %s" % root)
        projects = [
            project_summary(child)
            for child in sorted(root.iterdir(), key=lambda p: p.name)
            if child.is_dir() and child.name not in SKIP_PARTS
            and any((child / marker).is_file() for marker in MARKERS)
        ]
        result = {"root": str(root), "projects": projects, "count": len(projects), "errors": []}
        expected = request.get("expected_count")
        if expected is not None and len(projects) != expected:
            result["errors"].append("expected %d projects, found %d" % (expected, len(projects)))
        destination = request.get("write_libraries_file")
        if destination and not result["errors"]:
            out = Path(destination)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text("".join(item["path"] + "\n" for item in projects), encoding="utf-8")
            result["libraries_file"] = str(out)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 1 if result["errors"] else 0
    except Exception as exc:
        print(json.dumps({"projects": [], "count": 0, "errors": [str(exc)]}, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
