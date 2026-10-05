import os, shutil, subprocess, sys, time
from pathlib import Path

def locate(requested=None, home='/app/.fast-downward'):
    choices=(requested, os.environ.get('FAST_DOWNWARD'), 'fast-downward.py',
             'fast-downward', 'downward', str(Path(home)/'fast-downward.py'),
             '/opt/fast-downward/fast-downward.py', '/usr/local/bin/fast-downward.py')
    for item in choices:
        if not item: continue
        p=Path(str(item))
        found=str(p.resolve()) if p.is_file() else shutil.which(str(item))
        if found: return str(Path(found).resolve())
    return None

def build_name(driver):
    root=Path(driver).resolve().parent
    for name in ('release', 'release_no_lp', 'debug'):
        if (root/'builds'/name/'bin'/'downward').is_file(): return name
    return None

def _build(driver, deadline):
    root=Path(driver).resolve().parent
    last=''
    for target in ('release', 'release_no_lp'):
        left=int(deadline-time.monotonic())
        if left < 15: break
        try:
            result=subprocess.run([sys.executable, 'build.py', target], cwd=root,
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
                timeout=left, env=dict(os.environ, CMAKE_BUILD_PARALLEL_LEVEL='1'))
            last=(result.stderr or '')[-1000:]
        except subprocess.TimeoutExpired:
            return None, 'Fast Downward build timed out'
        except Exception as exc:
            return None, 'Fast Downward build failed: %s' % exc
        got=build_name(driver)
        if result.returncode == 0 and got: return got, None
    return None, 'Fast Downward build produced no usable binary' + ((': '+last) if last else '')

def ensure(requested=None, timeout=450, home='/app/.fast-downward'):
    deadline=time.monotonic()+max(1, int(timeout))
    driver=locate(requested, home)
    if driver:
        if not driver.endswith('.py'): return driver, None
        profile=build_name(driver)
        if profile: return driver, profile
        profile, error=_build(driver, deadline)
        return (driver, profile) if profile else (None, error)
    root=Path(home); wrapper=root/'fast-downward.py'
    try:
        root.parent.mkdir(parents=True, exist_ok=True)
        if not wrapper.is_file() or not (root/'build.py').is_file():
            if root.exists(): shutil.rmtree(root)
            left=max(1, int(deadline-time.monotonic()))
            clone=subprocess.run(['git', 'clone', '--depth', '1',
                'https://github.com/aibasel/downward.git', str(root)],
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, timeout=left)
            if clone.returncode:
                return None, 'Fast Downward clone failed: '+(clone.stderr or '')[-1000:]
        profile, error=_build(str(wrapper), deadline)
        return (str(wrapper), profile) if profile else (None, error)
    except subprocess.TimeoutExpired:
        return None, 'Fast Downward setup timed out'
    except Exception as exc:
        return None, 'Fast Downward setup failed: %s' % exc
