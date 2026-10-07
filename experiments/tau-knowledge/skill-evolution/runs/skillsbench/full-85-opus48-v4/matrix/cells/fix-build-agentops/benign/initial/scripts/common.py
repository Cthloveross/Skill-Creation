"""Shared helpers for the fix-python-build-bugswarm Skill scripts.

All scripts read one JSON object from stdin and write one JSON object to
stdout. These helpers are task-independent: they take paths from the input or
fall back to the standard BugSwarm task layout and never hardcode an instance
id, a root cause, or an expected patch.
"""
import json
import os
import subprocess
import sys

DEFAULT_BASE = "/home/github/build/failed"
PROJECT_MARKERS = ("setup.py", "pyproject.toml", "tox.ini", "setup.cfg")


def read_input():
    data = sys.stdin.read().strip()
    if not data:
        return {}
    try:
        obj = json.loads(data)
        return obj if isinstance(obj, dict) else {}
    except json.JSONDecodeError:
        return {}


def emit(obj):
    sys.stdout.write(json.dumps(obj))
    sys.stdout.write("\n")


def run(cmd, cwd=None, timeout=None):
    """Run a command list, return (exit_code, stdout, stderr)."""
    try:
        p = subprocess.run(
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
        return p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode(
            "utf-8", "replace"
        )
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or b"").decode("utf-8", "replace")
        err = (e.stderr or b"").decode("utf-8", "replace")
        return 124, out, err + "\n[timeout]"
    except FileNotFoundError as e:
        return 127, "", str(e)


def is_git_repo(path):
    code, out, _ = run(["git", "-C", path, "rev-parse", "--is-inside-work-tree"])
    return code == 0 and out.strip() == "true"


def find_repo(base=DEFAULT_BASE):
    """Return a list of candidate <repo>/<id> directories under base."""
    results = []
    if not os.path.isdir(base):
        return results
    for repo in sorted(os.listdir(base)):
        rp = os.path.join(base, repo)
        if not os.path.isdir(rp):
            continue
        for idd in sorted(os.listdir(rp)):
            ip = os.path.join(rp, idd)
            if not os.path.isdir(ip):
                continue
            markers = [m for m in PROJECT_MARKERS if os.path.exists(os.path.join(ip, m))]
            git = os.path.isdir(os.path.join(ip, ".git"))
            wf = os.path.isdir(os.path.join(ip, ".github", "workflows"))
            if markers or git or wf:
                results.append(
                    {
                        "path": ip,
                        "repo": repo,
                        "id": idd,
                        "markers": markers,
                        "git": git,
                        "workflows": wf,
                    }
                )
    return results


def resolve_repo(inp):
    """Resolve the target repo path from input or by discovery."""
    repo = inp.get("repo")
    if repo and os.path.isdir(repo):
        return repo, None
    base = inp.get("base", DEFAULT_BASE)
    cands = find_repo(base)
    if len(cands) == 1:
        return cands[0]["path"], None
    if not cands:
        return None, "no candidate repo found under %s" % base
    return None, "multiple candidates; pass {\"repo\": ...}: %s" % [c["path"] for c in cands]
