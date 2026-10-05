"""Locate or bootstrap a usable Fast Downward driver and build profile."""
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


def _path(value):
    if not value:
        return None
    candidate = Path(str(value))
    if candidate.is_file():
        return str(candidate.resolve())
    found = shutil.which(str(value))
    return str(Path(found).resolve()) if found and Path(found).is_file() else None


def find_fast_downward(requested=None, home="/app/.fast-downward"):
    for value in (requested, os.environ.get("FAST_DOWNWARD"), "fast-downward.py",
                  "fast-downward", str(Path(home) / "fast-downward.py"),
                  "/opt/fast-downward/fast-downward.py", "/root/fast-downward/fast-downward.py"):
        found = _path(value)
        if found:
            return found
    return None


def build_for(wrapper):
    if not wrapper:
        return None
    builds = Path(wrapper).resolve().parent / "builds"
    for name in ("release_no_lp", "release"):
        if (builds / name / "bin" / "downward").is_file():
            return name
    return None


def _tail(result):
    if isinstance(result, Exception):
        return str(result)
    return ((result.stderr or "") + "\n" + (result.stdout or "")).strip()[-1600:]


def _build(wrapper, deadline):
    root = Path(wrapper).resolve().parent
    left = int(deadline - time.monotonic())
    if left <= 0:
        return None, "Fast Downward setup deadline expired before build"
    env = dict(os.environ)
    env.setdefault("CMAKE_BUILD_PARALLEL_LEVEL", "1")
    try:
        result = subprocess.run([sys.executable, "build.py", "release_no_lp"], cwd=str(root),
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                timeout=left, env=env, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, "Fast Downward build failed: " + str(exc)
    profile = build_for(wrapper)
    if result.returncode or not profile:
        return None, "Fast Downward build failed: " + _tail(result)
    return profile, None


def ensure_fast_downward(requested=None, home="/app/.fast-downward", timeout=360):
    """Return (driver, profile_or_diagnostic). A returned driver is build-ready."""
    deadline = time.monotonic() + max(1, int(timeout))
    wrapper = find_fast_downward(requested, home)
    if wrapper and build_for(wrapper):
        return wrapper, build_for(wrapper)
    if wrapper:
        profile, error = _build(wrapper, deadline)
        return (wrapper, profile) if profile else (None, error)

    root = Path(home)
    wrapper_path = root / "fast-downward.py"
    root.parent.mkdir(parents=True, exist_ok=True)
    if root.exists() and not wrapper_path.is_file():
        shutil.rmtree(root, ignore_errors=True)
    if not root.exists():
        try:
            result = subprocess.run(
                ["git", "clone", "--depth", "1", "https://github.com/aibasel/downward.git", str(root)],
                cwd=str(root.parent), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                timeout=max(1, int(deadline - time.monotonic())), check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return None, "Fast Downward clone failed: " + str(exc)
        if result.returncode:
            return None, "Fast Downward clone failed: " + _tail(result)
    if not wrapper_path.is_file():
        return None, "Fast Downward checkout has no fast-downward.py"
    profile, error = _build(str(wrapper_path), deadline)
    return (str(wrapper_path), profile) if profile else (None, error)
