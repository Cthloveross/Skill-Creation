"""Locate or bootstrap a Fast Downward wrapper for the current runtime."""
import os, shutil, subprocess, sys, time
from pathlib import Path

def _usable(value):
    if not value:
        return None
    p = Path(str(value))
    if p.is_file():
        return str(p.resolve())
    found = shutil.which(str(value))
    return str(Path(found).resolve()) if found and Path(found).is_file() else None

def find_fast_downward(requested=None, home="/app/.fast-downward"):
    candidates = (
        requested, os.environ.get("FAST_DOWNWARD"),
        "fast-downward.py", "fast-downward",
        str(Path(home) / "fast-downward.py"),
        "/opt/fast-downward/fast-downward.py",
        "/root/fast-downward/fast-downward.py",
        "/app/fast-downward/fast-downward.py",
    )
    for candidate in candidates:
        usable = _usable(candidate)
        if usable:
            return usable
    return None

def build_for(wrapper):
    """Return an available local build profile, otherwise let the wrapper decide."""
    if not wrapper:
        return None
    builds = Path(wrapper).resolve().parent / "builds"
    for profile in ("release_no_lp", "release"):
        if (builds / profile / "bin" / "downward").is_file():
            return profile
    return None

def _run(args, cwd, seconds):
    try:
        return subprocess.run(args, cwd=str(cwd), text=True, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, timeout=max(1, int(seconds)), check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return exc

def _detail(result):
    if isinstance(result, Exception):
        return str(result)
    return ((result.stderr or "") + "\n" + (result.stdout or "")).strip()[-1200:]

def ensure_fast_downward(requested=None, home="/app/.fast-downward", timeout=300):
    found = find_fast_downward(requested, home)
    if found:
        return found, "existing Fast Downward"
    deadline = time.monotonic() + max(1, int(timeout))
    root = Path(home)
    wrapper = root / "fast-downward.py"
    root.parent.mkdir(parents=True, exist_ok=True)

    # Interrupted clones occasionally leave a .git directory but no usable wrapper.
    if root.exists() and not wrapper.is_file():
        shutil.rmtree(root, ignore_errors=True)
    if not root.exists():
        result = _run(["git", "clone", "--depth", "1", "https://github.com/aibasel/downward.git", str(root)],
                      root.parent, deadline - time.monotonic())
        if isinstance(result, Exception) or result.returncode:
            return None, "Fast Downward clone failed: " + _detail(result)
    if not wrapper.is_file():
        return None, "Fast Downward checkout has no fast-downward.py"

    profile = "release_no_lp"
    binary = root / "builds" / profile / "bin" / "downward"
    if binary.is_file():
        return str(wrapper), "bootstrapped Fast Downward (release_no_lp)"
    remaining = int(deadline - time.monotonic())
    if remaining <= 0:
        return None, "Fast Downward setup deadline expired before build"
    env = dict(os.environ)
    env.setdefault("CMAKE_BUILD_PARALLEL_LEVEL", "1")
    try:
        result = subprocess.run([sys.executable, "build.py", profile], cwd=str(root), text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=remaining,
                                check=False, env=env)
    except (OSError, subprocess.TimeoutExpired) as exc:
        result = exc
    if not isinstance(result, Exception) and result.returncode == 0 and binary.is_file():
        return str(wrapper), "bootstrapped Fast Downward (release_no_lp)"
    return None, "Fast Downward build failed: " + _detail(result)
