#!/usr/bin/env python3
"""Validate the patch_*.diff files in the repo.

Input (stdin JSON): {"repo": "...", "base": "..."}  (both optional)
Output (stdout JSON): {
  "repo": str|null,
  "patches": [ {"path","nonempty","has_headers","has_hunk","reverse_applies"} ],
  "ok": bool,
  "note": str
}

Checks structural validity (---/+++ headers and at least one @@ hunk) and, in a
git repo, that the patch is consistent with the current tree via reverse apply.
"""
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import emit, is_git_repo, read_input, resolve_repo, run  # noqa: E402


def structural_check(text):
    has_minus = any(l.startswith("--- ") for l in text.splitlines())
    has_plus = any(l.startswith("+++ ") for l in text.splitlines())
    has_hunk = any(l.startswith("@@") for l in text.splitlines())
    return (has_minus and has_plus), has_hunk


def main():
    inp = read_input()
    repo, err = resolve_repo(inp)
    if err:
        emit({"repo": None, "patches": [], "ok": False, "note": err})
        return
    git = is_git_repo(repo)
    patch_files = sorted(glob.glob(os.path.join(repo, "patch_*.diff")))
    results = []
    ok = bool(patch_files)
    for p in patch_files:
        try:
            with open(p, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError:
            results.append({"path": p, "nonempty": False, "has_headers": False,
                            "has_hunk": False, "reverse_applies": None})
            ok = False
            continue
        nonempty = bool(text.strip())
        has_headers, has_hunk = structural_check(text)
        rev = None
        if git:
            code, _, _ = run(["git", "-C", repo, "apply", "--check", "-R", p])
            rev = code == 0
        results.append({"path": p, "nonempty": nonempty, "has_headers": has_headers,
                        "has_hunk": has_hunk, "reverse_applies": rev})
        if not (nonempty and has_headers and has_hunk):
            ok = False
        if git and rev is False:
            ok = False
    note = "ok" if ok else ("no patch_*.diff found" if not patch_files else "one or more patches invalid")
    emit({"repo": repo, "patches": results, "ok": ok, "note": note})


if __name__ == "__main__":
    main()
