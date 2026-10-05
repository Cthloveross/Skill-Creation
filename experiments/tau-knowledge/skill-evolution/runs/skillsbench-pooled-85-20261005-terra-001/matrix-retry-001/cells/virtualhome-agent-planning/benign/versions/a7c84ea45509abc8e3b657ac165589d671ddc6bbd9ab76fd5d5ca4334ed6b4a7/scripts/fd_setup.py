"""Find or make one Fast Downward wrapper without repeated setup attempts."""
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


def _usable(value):
    if not value:
        return None
    p = Path(str(value))
    if p.is_file():
        return str(p.resolve())
    found = shutil.which(str(value))
    return found if found and Path(found).is_file() else None


def find_fast_downward(requested=None, home="/app/.fast-downward"):
    for item in (requested, os.environ.get("FAST_DOWNWARD"), "fast-downward.py",
                 "fast-downward", str(Path(home) / "fast-downward.py"),
                 "/opt/fast-downward/fast-downward.py", "/root/fast-downward/fast-downward.py",
                 "/app/fast-downward/fast-downward.py"):
        found = _usable(item)
        if found:
            return found
    return None


def _run(args, cwd, seconds):
    try:
        return subprocess.run(args, cwd=str(cwd), text=True, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, timeout=max(1, seconds), check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return exc


def _message(result):
    if isinstance(result, Exception):
        return str(result)
    return ((result.stderr or "") + "\n" + (result.stdout or "")).strip()[-1200:]


def ensure_fast_downward(requested=None, home="/app/.fast-downward", timeout=330):
    """Return (wrapper, note), never exceeding the total setup budget."""
    found = find_fast_downward(requested, home)
    if found:
        return found, "existing Fast Downward"
    deadline = time.monotonic() + max(1, int(timeout))
    root = Path(home)
    wrapper = root / "fast-downward.py"
    root.parent.mkdir(parents=True, exist_ok=True)
    if not root.exists():
        remaining = int(deadline - time.monotonic())
        result = _run(["git", "clone", "--depth", "1", "https://github.com/aibasel/downward.git", str(root)],
                      root.parent, remaining)
        if isinstance(result, Exception) or result.returncode:
            return None, "Fast Downward clone failed: " + _message(result)
    if not wrapper.is_file():
        return None, "Fast Downward checkout has no fast-downward.py"
    binary = root / "builds" / "release" / "bin" / "downward"
    if not binary.is_file():
        remaining = int(deadline - time.monotonic())
        if remaining <= 0:
            return None, "Fast Downward setup deadline expired before build"
        result = _run([sys.executable, "build.py", "release"], root, remaining)
        if isinstance(result, Exception) or result.returncode:
            return None, "Fast Downward build failed: " + _message(result)
    return str(wrapper), "bootstrapped Fast Downward"
