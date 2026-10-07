"""Locate or bootstrap a Fast Downward wrapper using only standard-library Python."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

def _usable(value):
    if not value:
        return None
    candidate = Path(value)
    if candidate.is_file():
        return str(candidate.resolve())
    found = shutil.which(value)
    return found if found and Path(found).is_file() else None

def find_fast_downward(requested=None, home="/app/.fast-downward"):
    choices = [requested, os.environ.get("FAST_DOWNWARD"), "fast-downward.py", "fast-downward",
               str(Path(home) / "fast-downward.py"), "/opt/fast-downward/fast-downward.py",
               "/root/fast-downward/fast-downward.py", "/app/fast-downward/fast-downward.py"]
    for choice in choices:
        result = _usable(choice)
        if result:
            return result
    return None

def _run(command, cwd, timeout):
    try:
        return subprocess.run(command, cwd=str(cwd), text=True, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return exc

def ensure_fast_downward(requested=None, home="/app/.fast-downward", timeout=300):
    existing = find_fast_downward(requested, home)
    if existing:
        return existing, "existing Fast Downward"
    root = Path(home)
    wrapper = root / "fast-downward.py"
    root.parent.mkdir(parents=True, exist_ok=True)
    if not root.exists():
        clone = _run(["git", "clone", "--depth", "1", "https://github.com/aibasel/downward.git", str(root)], root.parent, timeout)
        if isinstance(clone, Exception) or clone.returncode != 0:
            detail = str(clone) if isinstance(clone, Exception) else clone.stderr[-800:]
            return None, "could not clone Fast Downward: " + detail.strip()
    if not wrapper.is_file():
        return None, "Fast Downward checkout has no fast-downward.py wrapper"
    marker = root / "builds" / "release" / "bin" / "downward"
    if not marker.is_file():
        built = _run([sys.executable, "build.py", "release"], root, timeout)
        if isinstance(built, Exception) or built.returncode != 0:
            detail = str(built) if isinstance(built, Exception) else built.stderr[-1200:]
            return None, "could not build Fast Downward release configuration: " + detail.strip()
    return str(wrapper), "bootstrapped Fast Downward"
