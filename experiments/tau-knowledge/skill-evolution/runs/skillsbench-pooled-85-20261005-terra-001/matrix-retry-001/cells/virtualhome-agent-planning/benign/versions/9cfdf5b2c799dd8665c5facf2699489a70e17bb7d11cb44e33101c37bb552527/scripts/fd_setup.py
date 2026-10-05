import os, shutil, subprocess, sys, time
from pathlib import Path


def locate(requested=None, home='/app/.fast-downward'):
    choices = (
        requested, os.environ.get('FAST_DOWNWARD'),
        str(Path(home) / 'fast-downward.py'),
        '/opt/fast-downward/fast-downward.py',
        '/usr/local/bin/fast-downward.py', '/usr/bin/fast-downward.py',
        'fast-downward.py', 'fast-downward',
    )
    for item in choices:
        if not item:
            continue
        p = Path(str(item)).expanduser()
        found = str(p.resolve()) if p.is_file() else shutil.which(str(item))
        if found:
            return str(Path(found).resolve())
    return None


def build_name(driver):
    root = Path(driver).resolve().parent
    for name in ('release', 'release_no_lp', 'debug'):
        if (root / 'builds' / name / 'bin' / 'downward').is_file():
            return name
    return None


def build(driver, deadline):
    root = Path(driver).resolve().parent
    detail = ''
    for profile in ('release', 'release_no_lp'):
        remaining = int(deadline - time.monotonic())
        if remaining < 20:
            break
        try:
            result = subprocess.run(
                [sys.executable, 'build.py', profile], cwd=str(root),
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
                timeout=remaining,
                env=dict(os.environ, CMAKE_BUILD_PARALLEL_LEVEL='1'),
            )
            detail = (result.stderr or '')[-1200:]
            got = build_name(driver)
            if result.returncode == 0 and got:
                return got, None
        except subprocess.TimeoutExpired:
            return None, 'Fast Downward build timed out'
        except Exception as exc:
            return None, 'Fast Downward build failed: %s' % exc
    suffix = ': ' + detail if detail else ''
    return None, 'Fast Downward build produced no usable binary' + suffix


def ensure(requested=None, timeout=240, home='/app/.fast-downward'):
    deadline = time.monotonic() + max(1, int(timeout))
    driver = locate(requested, home)
    if driver:
        # A non-Python executable supplied explicitly is assumed to be a
        # Fast-Downward-compatible driver rather than the low-level search binary.
        if not driver.endswith('.py'):
            return driver, None
        profile = build_name(driver)
        if profile:
            return driver, profile
        profile, error = build(driver, deadline)
        return (driver, profile) if profile else (None, error)
    root = Path(home)
    wrapper = root / 'fast-downward.py'
    try:
        root.parent.mkdir(parents=True, exist_ok=True)
        if not wrapper.is_file() or not (root / 'build.py').is_file():
            if root.exists():
                shutil.rmtree(root)
            remaining = int(deadline - time.monotonic())
            if remaining < 20:
                return None, 'insufficient time to obtain Fast Downward'
            cloned = subprocess.run(
                ['git', 'clone', '--depth', '1',
                 'https://github.com/aibasel/downward.git', str(root)],
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
                timeout=remaining,
            )
            if cloned.returncode:
                return None, 'Fast Downward clone failed: ' + (cloned.stderr or '')[-1200:]
        profile, error = build(str(wrapper), deadline)
        return (str(wrapper), profile) if profile else (None, error)
    except subprocess.TimeoutExpired:
        return None, 'Fast Downward setup timed out'
    except Exception as exc:
        return None, 'Fast Downward setup failed: %s' % exc
