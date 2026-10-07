#!/usr/bin/env python3
"""Generate unified-diff patch files from the current (real) git working tree.

stdin  JSON: {
  "repo_dir": "<git root or repo dir>" (required),
  "files": ["rel/path/A.java", ...] (optional; empty -> diff whole tree),
  "out_dir": "<dir to write patch files>" (required),
  "prefix": "patch" (optional),
  "start_index": 1 (optional),
  "combined": false (optional; true -> single patch_<i>.diff with all files)
}
stdout JSON: {"written": [paths], "empty": [files with no diff], "errors": [...]}

Edit the source files FIRST, then call this. Diffs are produced with
`git diff` so they reflect the exact original->modified change (git-style
a/ b/ headers, correct @@ hunks). Paths in "files" must be relative to repo_dir
(the git root).
"""
import json, os, subprocess, sys


def read_stdin():
    raw = sys.stdin.read().strip()
    return json.loads(raw) if raw else {}


def git_diff(repo, path=None):
    args = ['git', '-C', repo, 'diff', '--no-color']
    if path:
        args += ['--', path]
    out = subprocess.run(args, capture_output=True, text=True, timeout=120)
    return out.stdout


def main():
    cfg = read_stdin()
    repo = cfg.get('repo_dir')
    out_dir = cfg.get('out_dir')
    if not repo or not out_dir:
        print(json.dumps({'error': 'repo_dir and out_dir required'}))
        return
    files = cfg.get('files') or []
    prefix = cfg.get('prefix') or 'patch'
    idx = int(cfg.get('start_index') or 1)
    combined = bool(cfg.get('combined'))

    os.makedirs(out_dir, exist_ok=True)
    written, empty, errors = [], [], []

    try:
        if combined or not files:
            text = git_diff(repo, None) if not files else ''
            if files:
                parts = []
                for fp in files:
                    d = git_diff(repo, fp)
                    if d.strip():
                        parts.append(d)
                    else:
                        empty.append(fp)
                text = ''.join(parts)
            if text.strip():
                p = os.path.join(out_dir, '%s_%d.diff' % (prefix, idx))
                with open(p, 'w') as f:
                    f.write(text)
                written.append(p)
            else:
                errors.append('no changes detected; did you edit the files?')
        else:
            for fp in files:
                d = git_diff(repo, fp)
                if not d.strip():
                    empty.append(fp)
                    continue
                p = os.path.join(out_dir, '%s_%d.diff' % (prefix, idx))
                with open(p, 'w') as f:
                    f.write(d)
                written.append(p)
                idx += 1
    except Exception as e:
        errors.append(str(e))

    print(json.dumps({'written': written, 'empty': empty, 'errors': errors}))


if __name__ == '__main__':
    main()
