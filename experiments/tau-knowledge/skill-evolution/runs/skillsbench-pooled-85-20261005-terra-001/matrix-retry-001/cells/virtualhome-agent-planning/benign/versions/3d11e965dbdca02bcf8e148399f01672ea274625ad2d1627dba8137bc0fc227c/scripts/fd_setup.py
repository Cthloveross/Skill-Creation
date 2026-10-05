"""Locate or bootstrap Fast Downward and identify its usable build profile."""
import os, shutil, subprocess, sys, time
from pathlib import Path

def _usable(value):
    if not value: return None
    p=Path(str(value))
    if p.is_file(): return str(p.resolve())
    p=shutil.which(str(value))
    return str(Path(p).resolve()) if p and Path(p).is_file() else None

def find_fast_downward(requested=None, home="/app/.fast-downward"):
    for x in (requested, os.environ.get("FAST_DOWNWARD"), "fast-downward.py", "fast-downward", str(Path(home)/"fast-downward.py"), "/opt/fast-downward/fast-downward.py", "/root/fast-downward/fast-downward.py", "/app/fast-downward/fast-downward.py"):
        x=_usable(x)
        if x: return x
    return None

def build_for(wrapper):
    """Return the profile name for a wrapper when a nondefault local build exists."""
    if not wrapper: return None
    root=Path(wrapper).resolve().parent
    builds=root/"builds"
    for profile in ("release_no_lp", "release"):
        if (builds/profile/"bin"/"downward").is_file(): return profile
    return None

def _run(args,cwd,seconds):
    try:
        return subprocess.run(args,cwd=str(cwd),text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=max(1,int(seconds)),check=False)
    except (OSError,subprocess.TimeoutExpired) as e: return e

def _msg(r):
    if isinstance(r,Exception): return str(r)
    return ((r.stderr or "")+"\n"+(r.stdout or "")).strip()[-1200:]

def ensure_fast_downward(requested=None,home="/app/.fast-downward",timeout=260):
    found=find_fast_downward(requested,home)
    if found: return found,"existing Fast Downward"
    deadline=time.monotonic()+max(1,int(timeout)); root=Path(home); wrapper=root/"fast-downward.py"
    root.parent.mkdir(parents=True,exist_ok=True)
    # A failed interrupted clone must not make all later attempts permanently fail.
    if root.exists() and not (root/".git").exists(): shutil.rmtree(root,ignore_errors=True)
    if not root.exists():
        r=_run(["git","clone","--depth","1","https://github.com/aibasel/downward.git",str(root)],root.parent,deadline-time.monotonic())
        if isinstance(r,Exception) or r.returncode: return None,"Fast Downward clone failed: "+_msg(r)
    if not wrapper.is_file(): return None,"Fast Downward checkout has no fast-downward.py"
    profile="release_no_lp"; binary=root/"builds"/profile/"bin"/"downward"
    if binary.is_file(): return str(wrapper),"bootstrapped Fast Downward (release_no_lp)"
    remain=int(deadline-time.monotonic())
    if remain>0:
        env=dict(os.environ); env.setdefault("CMAKE_BUILD_PARALLEL_LEVEL","1")
        try:
            r=subprocess.run([sys.executable,"build.py",profile],cwd=str(root),text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=remain,check=False,env=env)
        except (OSError,subprocess.TimeoutExpired) as e: r=e
        if not isinstance(r,Exception) and not r.returncode and binary.is_file(): return str(wrapper),"bootstrapped Fast Downward (release_no_lp)"
    return None,"Fast Downward build failed or setup deadline expired"
