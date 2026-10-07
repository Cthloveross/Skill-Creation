#!/usr/bin/env python3
"""Generate GNU unified text patches from a snapshot and optionally apply them.

The caller snapshots files, edits the working tree, then invokes this program.
For apply=true, proposed files are preserved temporarily, restored to their
snapshot state, checked with git apply, and applied from the generated patch.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def safe_relative(value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or str(path) in ("", "."):
        raise ValueError("path must be a nonempty repository-relative path: %r" % value)
    return path


def run(args, cwd):
    return subprocess.run(args, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


def restore_entries(root: Path, baseline: Path, entries):
    for entry in entries:
        rel = Path(entry["path"])
        target = root / rel
        if entry["existed"]:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(baseline / rel, target)
        elif target.exists() or target.is_symlink():
            if target.is_dir() and not target.is_symlink():
                raise ValueError("refusing to remove directory for new-file target: %s" % rel)
            target.unlink()


def copy_proposed(root: Path, entries, holding: Path):
    states = []
    for entry in entries:
        rel = Path(entry["path"])
        target = root / rel
        exists = target.exists()
        if exists and (target.is_symlink() or not target.is_file()):
            raise ValueError("only regular proposed files are supported: %s" % rel)
        states.append({"path": entry["path"], "existed": exists})
        if exists:
            out = holding / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, out)
    return states


def restore_proposed(root: Path, holding: Path, states):
    restore_entries(root, holding, states)


def main() -> int:
    try:
        request = json.load(sys.stdin)
        root = Path(request["root"]).expanduser().resolve()
        baseline = Path(request["baseline"]).expanduser().resolve()
        patch = Path(request["patch"]).expanduser().resolve()
        wanted = [safe_relative(x).as_posix() for x in request["paths"]]
        apply_patch = bool(request.get("apply", False))
        if not root.is_dir() or not (root / ".git").exists():
            raise ValueError("root must be an existing Git checkout")
        manifest_path = baseline / "manifest.json"
        if not manifest_path.is_file():
            raise ValueError("baseline manifest not found: %s" % manifest_path)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if Path(manifest.get("root", "")).resolve() != root:
            raise ValueError("baseline was created for a different repository root")
        by_path = {entry["path"]: entry for entry in manifest.get("entries", [])}
        if not wanted or len(set(wanted)) != len(wanted) or set(wanted) != set(by_path):
            raise ValueError("paths must exactly match the snapshot manifest")
        try:
            patch.relative_to(root)
        except ValueError:
            raise ValueError("patch must be located inside the repository root")
        entries = [by_path[name] for name in wanted]
        chunks = []
        for entry in entries:
            rel = entry["path"]
            old = baseline / rel if entry["existed"] else Path("/dev/null")
            new_target = root / rel
            new = new_target if new_target.exists() else Path("/dev/null")
            if new != Path("/dev/null") and (new_target.is_symlink() or not new_target.is_file()):
                raise ValueError("only regular text files are supported: %s" % rel)
            old_label = "a/" + rel if old != Path("/dev/null") else "/dev/null"
            new_label = "b/" + rel if new != Path("/dev/null") else "/dev/null"
            result = run(["diff", "-u", "--label", old_label, "--label", new_label, str(old), str(new)], root)
            if result.returncode not in (0, 1):
                raise ValueError("diff failed for %s: %s" % (rel, result.stderr.decode("utf-8", "replace").strip()))
            if result.returncode == 1:
                chunks.append(result.stdout)
        if not chunks:
            raise ValueError("no changes from the snapshot; no patch was created")
        patch.parent.mkdir(parents=True, exist_ok=True)
        patch.write_bytes(b"".join(chunks))
        result_data = {"ok": True, "patch": str(patch), "bytes": patch.stat().st_size, "applied": False}
        if not apply_patch:
            print(json.dumps(result_data, sort_keys=True))
            return 0
        with tempfile.TemporaryDirectory(prefix="proposed-java-build-fix-") as temp:
            holding = Path(temp)
            proposed_states = copy_proposed(root, entries, holding)
            restore_entries(root, baseline, entries)
            checked = run(["git", "apply", "--check", str(patch)], root)
            if checked.returncode != 0:
                restore_proposed(root, holding, proposed_states)
                raise ValueError("git apply --check failed: " + checked.stderr.decode("utf-8", "replace").strip())
            applied = run(["git", "apply", str(patch)], root)
            if applied.returncode != 0:
                restore_proposed(root, holding, proposed_states)
                raise ValueError("git apply failed: " + applied.stderr.decode("utf-8", "replace").strip())
        result_data["applied"] = True
        print(json.dumps(result_data, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
