#!/usr/bin/env python3
"""Apply patch files to the repository (optionally resetting touched files first).

stdin  JSON: {"repo_dir": "<git root>" (required),
              "patches": ["patch_1.diff", ...] (required),
              "reset_first": false (optional)}
stdout JSON: {"applied": [...], "failed": [{patch, msg}], "reset_files": [...]}

Use reset_first=true to prove the patch files alone reproduce the fix: it reverts
the files touched by the patches to HEAD, then applies each patch with `git apply`.
This leaves the source tree in the fixed state (same as the delivered patches).
It never edits the build script.
"""
import json, os, re, subprocess, sys

FILE_HDR = re.compile(r'^\+\+\+ b/(.+)$')


def read_stdin():
    raw = sys.stdin.read().strip()
    return json.loads(raw) if raw else {}


def files_in_patch(path):
    files = []
    try:
        with open(path, 'r', errors='replace') as f:
            for line in f:
                m = FILE_HDR.match(line.rstrip('\n'))
                if m and m.group(1) != '/dev/null':
                    files.append(m.group(1))
    except Exception:
        pass
    return files


def main():
    cfg = read_stdin()
    repo = cfg.get('repo_dir')
    patches = cfg.get('patches') or []
    reset_first = bool(cfg.get('reset_first'))
    if not repo or not patches:
        print(json.dumps({'error': 'repo_dir and patches required'}))
        return

    reset_files = []
    if reset_first:
        targets = []
        for p in patches:
            targets.extend(files_in_patch(p))
        targets = sorted(set(targets))
        for t in targets:
            r = subprocess.run(['git', '-C', repo, 'checkout', '--', t],
                               capture_output=True, text=True, timeout=60)
            if r.returncode == 0:
                reset_files.append(t)

    applied, failed = [], []
    for p in patches:
        r = subprocess.run(['git', '-C', repo, 'apply', p],
                           capture_output=True, text=True, timeout=120)
        if r.returncode == 0:
            applied.append(p)
        else:
            # fallback to GNU patch with path strip
            r2 = subprocess.run(['patch', '-p1', '-i', os.path.abspath(p)],
                                cwd=repo, capture_output=True, text=True, timeout=120)
            if r2.returncode == 0:
                applied.append(p)
            else:
                failed.append({'patch': p,
                               'msg': (r.stderr.strip() or r.stdout.strip() or
                                       r2.stderr.strip() or r2.stdout.strip())})

    print(json.dumps({'applied': applied, 'failed': failed, 'reset_files': reset_files}))


if __name__ == '__main__':
    main()
