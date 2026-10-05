"""Locate or bootstrap a Fast Downward wrapper in the task runtime."""
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
    return str(Path(found).resolve()) if found and Path(found).is_file() else None


def find_fast_downward(requested=None, home="/app/.fast-downward"):
    candidates = (
        requested, os.environ.get("FAST_DOWNWARD"), "fast-downward.py", "fast-downward",
        str(Path(home) / "fast-downward.py"), "/opt/fast-downward/fast-downward.py",
        "/root/fast-downward/fast-downward.py", "/app/fast-downward/fast-downward.py",
    )
    for candidate in candidates:
        result = _usable(candidate)
        if result:
            return result
    return None


def build_for(wrapper):
    if not wrapper:
        return None
    builds = Path(wrapper).resolve().parent / "builds"
    for profile in ("release_no_lp", "release"):
        if (builds / profile / "bin" / "downward").is_file():
            return profile
    return None


def _detail(result):
    if isinstance(result, Exception):
        return str(result)
    return ((result.stderr or "") + "\n" + (result.stdout or "")).strip()[-1200:]


def ensure_fast_downward(requested=None, home="/app/.fast-downward", timeout=180):
    found = find_fast_downward(requested, home)
    if found:
        return found, "existing Fast Downward"
    deadline = time.monotonic() + max(1, int(timeout))
    root = Path(home)
    wrapper = root / "fast-downward.py"
    root.parent.mkdir(parents=True, exist_ok=True)
    if root.exists() and not wrapper.is_file():
        shutil.rmtree(root, ignore_errors=True)
    if not root.exists():
        try:
            result = subprocess.run(
                ["git", "clone", "--depth", "1", "https://github.com/aibasel/downward.git", str(root)],
                cwd=str(root.parent), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=max(1, int(deadline - time.monotonic())), check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return None, "Fast Downward clone failed: " + str(exc)
        if result.returncode:
            return None, "Fast Downward clone failed: " + _detail(result)
    if not wrapper.is_file():
        return None, "Fast Downward checkout has no fast-downward.py"
    if build_for(str(wrapper)):
        return str(wrapper), "bootstrapped Fast Downward"
    remaining = int(deadline - time.monotonic())
    if remaining <= 0:
        return None, "Fast Downward setup deadline expired before build"
    environment = dict(os.environ)
    environment.setdefault("CMAKE_BUILD_PARALLEL_LEVEL", "1")
    try:
        result = subprocess.run([sys.executable, "build.py", "release_no_lp"], cwd=str(root), text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=remaining,
                                check=False, env=environment)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, "Fast Downward build failed: " + str(exc)
    if result.returncode or not build_for(str(wrapper)):
        return None, "Fast Downward build failed: " + _detail(result)
    return str(wrapper), "bootstrapped Fast Downward (release_no_lp)"
