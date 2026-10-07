#!/usr/bin/env python3
"""Generate unified-diff patch files from the real applied source changes.

Precondition: you have already edited the source files in the repo (the fix is
applied). This produces diffs that reflect the actual file state, as the
background requires, and leaves your changes in place.

Input (stdin JSON): {
  "repo": "/home/github/build/failed/<repo>/<id>",   # optional; auto-discovered
  "base": "/home/github/build/failed",               # used for discovery
  "originals": null,   # non-git fallback: dir with untouched original files,
                       # mirroring the repo layout, used with difflib
  "combined": false    # true => single patch_1.diff for all files
}
Output (stdout JSON): {
  "repo": str|null,
  "mode": "git"|"difflib"|null,
  "patches": [ {"path","file","applies"} ],
  "changed_files": [str],
  "note": str
}

Validation: each git-mode patch is checked with `git apply --check -R` against
the current (modified) tree; applies==true means the forward patch applies
cleanly to HEAD and matches your applied changes.
"""
import difflib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import emit, is_git_repo, read_input, resolve_repo, run  # noqa: E402


def git_changed_files(repo):
    code, out, _ = run(["git", "-C", repo, "diff", "--name-only"])
    if code != 0:
        return []
    return [f for f in out.splitlines() if f.strip()]


def write_patch(path, text):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def check_reverse(repo, patch_path):
    code, _, _ = run(["git", "-C", repo, "apply", "--check", "-R", patch_path])
    return code == 0


def gen_git(repo, combined):
    files = git_changed_files(repo)
    patches = []
    if not files:
        return patches, files
    if combined:
        code, out, _ = run(["git", "-C", repo, "diff"])
        if out.strip():
            p = os.path.join(repo, "patch_1.diff")
            write_patch(p, out)
            patches.append({"path": p, "file": "<combined>", "applies": check_reverse(repo, p)})
        return patches, files
    for i, f in enumerate(files, start=1):
        code, out, _ = run(["git", "-C", repo, "diff", "--", f])
        if not out.strip():
            continue
        p = os.path.join(repo, "patch_%d.diff" % i)
        write_patch(p, out)
        patches.append({"path": p, "file": f, "applies": check_reverse(repo, p)})
    return patches, files


def gen_difflib(repo, originals, combined):
    patches = []
    changed = []
    blocks = []
    for root, _dirs, names in os.walk(originals):
        for name in names:
            orig = os.path.join(root, name)
            rel = os.path.relpath(orig, originals)
            cur = os.path.join(repo, rel)
            if not os.path.isfile(cur):
                continue
            with open(orig, "r", encoding="utf-8", errors="replace") as fh:
                a = fh.readlines()
            with open(cur, "r", encoding="utf-8", errors="replace") as fh:
                b = fh.readlines()
            if a == b:
                continue
            diff = list(
                difflib.unified_diff(a, b, fromfile="a/" + rel, tofile="b/" + rel)
            )
            if not diff:
                continue
            changed.append(rel)
            text = "".join(diff)
            if not text.endswith("\n"):
                text += "\n"
            blocks.append((rel, text))
    if combined and blocks:
        p = os.path.join(repo, "patch_1.diff")
        write_patch(p, "".join(t for _, t in blocks))
        patches.append({"path": p, "file": "<combined>", "applies": None})
    else:
        for i, (rel, text) in enumerate(blocks, start=1):
            p = os.path.join(repo, "patch_%d.diff" % i)
            write_patch(p, text)
            patches.append({"path": p, "file": rel, "applies": None})
    return patches, changed


def main():
    inp = read_input()
    repo, err = resolve_repo(inp)
    if err:
        emit({"repo": None, "mode": None, "patches": [], "changed_files": [], "note": err})
        return
    combined = bool(inp.get("combined"))
    originals = inp.get("originals")
    if originals:
        patches, changed = gen_difflib(repo, originals, combined)
        mode = "difflib"
        note = "diffs built with difflib against originals; validate with validate_patches.py"
    elif is_git_repo(repo):
        patches, changed = gen_git(repo, combined)
        mode = "git"
        bad = [p for p in patches if p["applies"] is False]
        if not changed:
            note = "no changes detected; apply your source fix before generating patches"
        elif bad:
            note = "some patches failed reverse-apply check; regenerate after re-applying edits"
        else:
            note = "patches generated and validated against the applied tree"
    else:
        emit({"repo": repo, "mode": None, "patches": [], "changed_files": [],
              "note": "not a git repo; pass {\"originals\": <backup_dir>}"})
        return
    emit({"repo": repo, "mode": mode, "patches": patches,
          "changed_files": changed, "note": note})


if __name__ == "__main__":
    main()
