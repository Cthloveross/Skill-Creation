"""Find or build a Fast Downward PDDL driver once for the batch."""
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


def _driver(value):
    if not value:
        return None
    p = Path(str(value))
    if p.is_file():
        return str(p.resolve())
    found = shutil.which(str(value))
    return str(Path(found).resolve()) if found and Path(found).is_file() else None


def build_for(driver):
    if not driver:
        return None
    builds = Path(driver).resolve().parent / "builds"
    for profile in ("release_no_lp", "release"):
        if (builds / profile / "bin" / "downward").is_file():
            return profile
    return None


def find_fast_downward(requested=None, home="/app/.fast-downward"):
    choices = (requested, os.environ.get("FAST_DOWNWARD"), "fast-downward.py",
               "fast-downward", str(Path(home) / "fast-downward.py"),
               "/opt/fast-downward/fast-downward.py",
               "/root/fast-downward/fast-downward.py")
    for choice in choices:
        found = _driver(choice)
        if found:
            return found
    return None


def _tail(result):
    return ((getattr(result, "stderr", "") or "") + "\n" +
            (getattr(result, "stdout", "") or ""))[-1800:].strip()


def _build(driver, deadline):
    root = Path(driver).resolve().parent
    seconds = int(deadline - time.monotonic())
    if seconds < 1:
        return None, "Fast Downward setup deadline expired before build"
    env = dict(os.environ)
    env.setdefault("CMAKE_BUILD_PARALLEL_LEVEL", "1")
    try:
        result = subprocess.run([sys.executable, "build.py", "release_no_lp"],
                                cwd=str(root), env=env, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                timeout=seconds, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, "Fast Downward build failed: %s" % exc
    profile = build_for(driver)
    if result.returncode or not profile:
        return None, "Fast Downward build failed: " + _tail(result)
    return profile, None


def ensure_fast_downward(requested=None, home="/app/.fast-downward", timeout=240):
    """Return ``(driver, build_profile_or_error)``; driver is ready for PDDL."""
    deadline = time.monotonic() + max(1, int(timeout))
    driver = find_fast_downward(requested, home)
    if driver and build_for(driver):
        return driver, build_for(driver)
    if driver:
        profile, error = _build(driver, deadline)
        return (driver, profile) if profile else (None, error)

    root = Path(home)
    wrapper = root / "fast-downward.py"
    root.parent.mkdir(parents=True, exist_ok=True)
    if root.exists() and not wrapper.is_file():
        shutil.rmtree(root, ignore_errors=True)
    if not root.exists():
        try:
            result = subprocess.run(
                ["git", "clone", "--depth", "1", "https://github.com/aibasel/downward.git", str(root)],
                cwd=str(root.parent), text=True, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=max(1, int(deadline - time.monotonic())), check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return None, "Fast Downward clone failed: %s" % exc
        if result.returncode:
            return None, "Fast Downward clone failed: " + _tail(result)
    if not wrapper.is_file():
        return None, "Fast Downward checkout has no fast-downward.py"
    profile, error = _build(str(wrapper), deadline)
    return (str(wrapper), profile) if profile else (None, error)
