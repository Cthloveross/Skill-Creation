"""Locate a usable Fast Downward driver, building a local checkout when needed."""
import os, shutil, subprocess, sys, time
from pathlib import Path

def find(requested=None, home='/app/.fast-downward'):
    for x in (requested, os.getenv('FAST_DOWNWARD'), 'fast-downward.py', 'fast-downward', str(Path(home)/'fast-downward.py'), '/opt/fast-downward/fast-downward.py'):
        if not x: continue
        p=Path(str(x)); q=str(p.resolve()) if p.is_file() else shutil.which(str(x))
        if q: return str(Path(q).resolve())
    return None

def profile(driver):
    b=Path(driver).resolve().parent/'builds'
    for x in ('release_no_lp','release'):
        if (b/x/'bin'/'downward').is_file(): return x
    return None

def build(driver, deadline):
    root=Path(driver).resolve().parent; left=max(1,int(deadline-time.monotonic()))
    try:
        r=subprocess.run([sys.executable,'build.py','release_no_lp'],cwd=root,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=left,env=dict(os.environ,CMAKE_BUILD_PARALLEL_LEVEL='1'))
    except Exception as e: return None,'Fast Downward build failed: %s'%e
    p=profile(driver)
    return (p,None) if not r.returncode and p else (None,'Fast Downward build failed: '+(r.stderr or r.stdout)[-1200:])

def ensure(requested=None, timeout=360, home='/app/.fast-downward'):
    end=time.monotonic()+max(1,int(timeout)); d=find(requested,home)
    if d:
        # A PATH-installed executable may not have a builds/ directory.
        if not d.endswith('.py'): return d,None
        p=profile(d)
        if p: return d,p
        p,e=build(d,end); return (d,p) if p else (None,e)
    root=Path(home); wrapper=root/'fast-downward.py'; root.parent.mkdir(parents=True,exist_ok=True)
    try:
        if not wrapper.is_file():
            if root.exists(): shutil.rmtree(root)
            r=subprocess.run(['git','clone','--depth','1','https://github.com/aibasel/downward.git',str(root)],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=max(1,int(end-time.monotonic())))
            if r.returncode: return None,'Fast Downward clone failed: '+(r.stderr or r.stdout)[-1200:]
        p,e=build(str(wrapper),end)
        return (str(wrapper),p) if p else (None,e)
    except Exception as e: return None,'Fast Downward setup failed: %s'%e
