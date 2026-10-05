"""Locate or bootstrap a local Fast Downward wrapper once per batch."""
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


def _usable(value):
    if not value:
        return None
    path = Path(str(value))
    if path.is_file():
        return str(path.resolve())
    found = shutil.which(str(value))
    return found if found and Path(found).is_file() else None


def find_fast_downward(requested=None, home="/app/.fast-downward"):
    candidates = (
        requested, os.environ.get("FAST_DOWNWARD"), "fast-downward.py", "fast-downward",
        str(Path(home) / "fast-downward.py"),
        "/opt/fast-downward/fast-downward.py", "/root/fast-downward/fast-downward.py",
        "/app/fast-downward/fast-downward.py",
    )
    for candidate in candidates:
        found = _usable(candidate)
        if found:
            return found
    return None


def _run(args, cwd, seconds):
    try:
        return subprocess.run(args, cwd=str(cwd), text=True, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, timeout=max(1, int(seconds)), check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return exc


def _message(result):
    if isinstance(result, Exception):
        return str(result)
    return ((result.stderr or "") + "\n" + (result.stdout or "")).strip()[-1400:]


def _binary(root, profile):
    return root / "builds" / profile / "bin" / "downward"


def ensure_fast_downward(requested=None, home="/app/.fast-downward", timeout=250):
    """Return ``(wrapper, explanation)`` within the given total setup budget."""
    found = find_fast_downward(requested, home)
    if found:
        return found, "existing Fast Downward"
    deadline = time.monotonic() + max(1, int(timeout))
    root = Path(home)
    wrapper = root / "fast-downward.py"
    root.parent.mkdir(parents=True, exist_ok=True)

    if not root.exists():
        result = _run(
            ["git", "clone", "--depth", "1", "https://github.com/aibasel/downward.git", str(root)],
            root.parent, deadline - time.monotonic(),
        )
        if isinstance(result, Exception) or result.returncode:
            return None, "Fast Downward clone failed: " + _message(result)
    if not wrapper.is_file():
        return None, "Fast Downward checkout has no fast-downward.py"

    # Airport is propositional classical planning. no_lp builds substantially faster
    # and avoid a needless optional LP dependency.
    for profile in ("release_no_lp", "release"):
        if _binary(root, profile).is_file():
            return str(wrapper), "bootstrapped Fast Downward (%s)" % profile
        remaining = int(deadline - time.monotonic())
        if remaining <= 0:
            break
        result = _run([sys.executable, "build.py", profile], root, remaining)
        if not isinstance(result, Exception) and not result.returncode and _binary(root, profile).is_file():
            return str(wrapper), "bootstrapped Fast Downward (%s)" % profile
    return None, "Fast Downward build failed or setup deadline expired"
