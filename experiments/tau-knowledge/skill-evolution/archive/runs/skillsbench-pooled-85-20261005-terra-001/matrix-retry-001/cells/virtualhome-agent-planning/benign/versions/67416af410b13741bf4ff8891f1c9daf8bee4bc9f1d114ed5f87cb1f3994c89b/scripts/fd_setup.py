import os, shutil, subprocess, sys, time
from pathlib import Path

def find(requested=None, home='/app/.fast-downward'):
    for x in (requested, os.getenv('FAST_DOWNWARD'), 'fast-downward.py', 'fast-downward', 'downward', str(Path(home)/'fast-downward.py'), '/opt/fast-downward/fast-downward.py', '/usr/local/bin/fast-downward.py'):
        if not x: continue
        p=Path(str(x)); q=str(p.resolve()) if p.is_file() else shutil.which(str(x))
        if q: return str(Path(q).resolve())
    return None

def profile(driver):
    b=Path(driver).resolve().parent/'builds'
    for n in ('release','release_no_lp'):
        if (b/n/'bin'/'downward').is_file(): return n
    return None

def build(driver, deadline):
    root=Path(driver).resolve().parent
    for target in ('release','release_no_lp'):
        left=int(deadline-time.monotonic())
        if left<10: break
        try:
            r=subprocess.run([sys.executable,'build.py',target],cwd=root,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=left,env=dict(os.environ,CMAKE_BUILD_PARALLEL_LEVEL='1'))
        except Exception as e:
            return None, 'Fast Downward build failed: %s' % e
        got=profile(driver)
        if r.returncode==0 and got: return got,None
    return None,'Fast Downward build did not produce a release binary'

def ensure(requested=None, timeout=300, home='/app/.fast-downward'):
    deadline=time.monotonic()+max(1,int(timeout)); driver=find(requested,home)
    if driver:
        if not driver.endswith('.py'): return driver,None
        got=profile(driver)
        if got: return driver,got
        got,err=build(driver,deadline)
        return (driver,got) if got else (None,err)
    root=Path(home); wrapper=root/'fast-downward.py'; root.parent.mkdir(parents=True,exist_ok=True)
    try:
        if not wrapper.is_file() or not (root/'build.py').is_file():
            if root.exists(): shutil.rmtree(root)
            left=max(1,int(deadline-time.monotonic()))
            r=subprocess.run(['git','clone','--depth','1','https://github.com/aibasel/downward.git',str(root)],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=left)
            if r.returncode: return None,'Fast Downward clone failed: '+(r.stderr or r.stdout or '')[-1200:]
        got,err=build(str(wrapper),deadline)
        return (str(wrapper),got) if got else (None,err)
    except Exception as e: return None,'Fast Downward setup failed: %s' % e
