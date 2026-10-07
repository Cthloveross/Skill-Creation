#!/usr/bin/env python3
"""Confirm all three required deliverables exist before finishing.

Input (stdin JSON): {
  "repo": "/home/github/build/failed/<repo>/<id>",   # optional; discovered
  "base": "/home/github/build/failed",
  "reasons": "/home/github/build/failed/failed_reasons.txt"
}
Output (stdout JSON): {
  "repo": str|null,
  "analysis_present": bool,
  "patch_files": [str],
  "patches_present": bool,
  "source_modified": bool,
  "ok": bool,
  "missing": [str],
  "note": str
}

source_modified is detected via `git diff --name-only` when the repo is a git
checkout; otherwise it is reported as null and you must confirm manually that
your edits are applied.
"""
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DEFAULT_BASE, emit, is_git_repo, read_input, resolve_repo, run  # noqa: E402


def main():
    inp = read_input()
    repo, err = resolve_repo(inp)
    if err:
        emit({"repo": None, "analysis_present": False, "patch_files": [],
              "patches_present": False, "source_modified": None, "ok": False,
              "missing": ["repo"], "note": err})
        return
    base = inp.get("base", DEFAULT_BASE)
    reasons = inp.get("reasons", os.path.join(base, "failed_reasons.txt"))
    analysis_present = os.path.isfile(reasons) and os.path.getsize(reasons) > 0
    patch_files = sorted(glob.glob(os.path.join(repo, "patch_*.diff")))
    patches_present = False
    for p in patch_files:
        try:
            with open(p, "r", encoding="utf-8", errors="replace") as fh:
                if fh.read().strip():
                    patches_present = True
                    break
        except OSError:
            pass
    source_modified = None
    if is_git_repo(repo):
        code, out, _ = run(["git", "-C", repo, "diff", "--name-only"])
        if code == 0:
            # ignore the patch files themselves if git tracks them
            changed = [f for f in out.splitlines() if f.strip()
                       and not os.path.basename(f).startswith("patch_")]
            source_modified = len(changed) > 0
    missing = []
    if not analysis_present:
        missing.append("failed_reasons.txt")
    if not patches_present:
        missing.append("patch_*.diff")
    if source_modified is False:
        missing.append("applied source changes")
    ok = analysis_present and patches_present and source_modified is not False
    note = "all deliverables present" if ok else "missing: %s" % ", ".join(missing)
    if source_modified is None and ok:
        note += " (confirm applied edits manually: non-git repo)"
    emit({
        "repo": repo,
        "analysis_present": analysis_present,
        "patch_files": patch_files,
        "patches_present": patches_present,
        "source_modified": source_modified,
        "ok": ok,
        "missing": missing,
        "note": note,
    })


if __name__ == "__main__":
    main()
