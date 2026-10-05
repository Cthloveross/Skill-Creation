"""Locate or bootstrap a Fast Downward wrapper with standard-library Python."""
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


def _usable(value):
    if not value:
        return None
    candidate = Path(value)
    if candidate.is_file():
        return str(candidate.resolve())
    found = shutil.which(str(value))
    return found if found and Path(found).is_file() else None


def find_fast_downward(requested=None, home="/app/.fast-downward"):
    choices = [
        requested, os.environ.get("FAST_DOWNWARD"), "fast-downward.py", "fast-downward",
        str(Path(home) / "fast-downward.py"), "/opt/fast-downward/fast-downward.py",
        "/root/fast-downward/fast-downward.py", "/app/fast-downward/fast-downward.py",
    ]
    for choice in choices:
        found = _usable(choice)
        if found:
            return found
    return None


def _run(command, cwd, timeout):
    try:
        return subprocess.run(command, cwd=str(cwd), text=True, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, timeout=max(1, timeout), check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return exc


def _detail(result):
    if isinstance(result, Exception):
        return str(result)
    return (result.stderr or result.stdout or "").strip()[-1000:]


def ensure_fast_downward(requested=None, home="/app/.fast-downward", timeout=150):
    """Return (wrapper, note), consuming no more than the supplied setup budget."""
    existing = find_fast_downward(requested, home)
    if existing:
        return existing, "existing Fast Downward"
    deadline = time.monotonic() + max(1, int(timeout))
    root = Path(home)
    wrapper = root / "fast-downward.py"
    root.parent.mkdir(parents=True, exist_ok=True)
    if not root.exists():
        # A shallow clone is normally brief; reserve most setup time for compilation.
        clone_limit = max(1, min(45, int(deadline - time.monotonic())))
        clone = _run(["git", "clone", "--depth", "1", "https://github.com/aibasel/downward.git", str(root)],
                     root.parent, clone_limit)
        if isinstance(clone, Exception) or clone.returncode != 0:
            return None, "could not clone Fast Downward: " + _detail(clone)
    if not wrapper.is_file():
        return None, "Fast Downward checkout has no fast-downward.py wrapper"
    marker = root / "builds" / "release" / "bin" / "downward"
    if not marker.is_file():
        remaining = int(deadline - time.monotonic())
        if remaining <= 0:
            return None, "Fast Downward setup time expired before compilation"
        built = _run([sys.executable, "build.py", "release"], root, remaining)
        if isinstance(built, Exception) or built.returncode != 0:
            return None, "could not build Fast Downward release configuration: " + _detail(built)
    return str(wrapper), "bootstrapped Fast Downward"
