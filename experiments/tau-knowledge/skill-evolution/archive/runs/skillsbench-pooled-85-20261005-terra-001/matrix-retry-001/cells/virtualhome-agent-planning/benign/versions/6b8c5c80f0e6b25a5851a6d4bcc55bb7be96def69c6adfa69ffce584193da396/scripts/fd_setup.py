"""Locate or prepare a Fast Downward driver without assuming an installed planner."""
import os, shutil, subprocess, sys, time
from pathlib import Path


def find(requested=None, home='/app/.fast-downward'):
    candidates = (
        requested, os.getenv('FAST_DOWNWARD'),
        'fast-downward.py', 'fast-downward', 'downward',
        str(Path(home) / 'fast-downward.py'),
        '/opt/fast-downward/fast-downward.py',
        '/usr/local/bin/fast-downward.py',
    )
    for value in candidates:
        if not value:
            continue
        path = Path(str(value))
        found = str(path.resolve()) if path.is_file() else shutil.which(str(value))
        if found:
            return str(Path(found).resolve())
    return None


def profile(driver):
    builds = Path(driver).resolve().parent / 'builds'
    for name in ('release_no_lp', 'release'):
        if (builds / name / 'bin' / 'downward').is_file():
            return name
    return None


def build(driver, deadline):
    root = Path(driver).resolve().parent
    left = max(1, int(deadline - time.monotonic()))
    try:
        result = subprocess.run(
            [sys.executable, 'build.py', 'release_no_lp'], cwd=root, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=left,
            env=dict(os.environ, CMAKE_BUILD_PARALLEL_LEVEL='1'),
        )
    except Exception as exc:
        return None, 'Fast Downward build failed: %s' % exc
    built = profile(driver)
    if result.returncode == 0 and built:
        return built, None
    detail = (result.stderr or result.stdout or '')[-1600:]
    return None, 'Fast Downward build failed: ' + detail


def ensure(requested=None, timeout=520, home='/app/.fast-downward'):
    """Return (driver, build_profile_or_None), or (None, diagnostic)."""
    deadline = time.monotonic() + max(1, int(timeout))
    driver = find(requested, home)
    if driver:
        # A standalone executable on PATH does not require a local build profile.
        if not driver.endswith('.py'):
            return driver, None
        existing = profile(driver)
        if existing:
            return driver, existing
        built, error = build(driver, deadline)
        return (driver, built) if built else (None, error)

    root = Path(home)
    wrapper = root / 'fast-downward.py'
    root.parent.mkdir(parents=True, exist_ok=True)
    try:
        # A prior interrupted clone is not a usable checkout unless it has both
        # the driver and build script. Replace it rather than failing repeatedly.
        if not wrapper.is_file() or not (root / 'build.py').is_file():
            if root.exists():
                shutil.rmtree(root)
            result = subprocess.run(
                ['git', 'clone', '--depth', '1',
                 'https://github.com/aibasel/downward.git', str(root)],
                text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=max(1, int(deadline - time.monotonic())),
            )
            if result.returncode:
                return None, 'Fast Downward clone failed: ' + (result.stderr or result.stdout or '')[-1600:]
        built, error = build(str(wrapper), deadline)
        return (str(wrapper), built) if built else (None, error)
    except Exception as exc:
        return None, 'Fast Downward setup failed: %s' % exc
