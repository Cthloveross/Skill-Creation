#!/usr/bin/env python3
"""Validate unified-diff patch files structurally and against git.

stdin  JSON: {"repo_dir": "<git root>" (required),
              "patches": ["path/to/patch_1.diff", ...] (required)}
stdout JSON: {"results": [{"path","parse_ok","reverse_apply_ok","errors"}],
              "all_ok": bool}

parse_ok: headers present, every hunk line prefixed with ' ', '+', '-' (or '\\'),
  and hunk @@ -a,b +c,d @@ line counts match the actual lines.
reverse_apply_ok: `git apply --check --reverse` succeeds, i.e. the patch exactly
  represents the current working tree relative to HEAD (so a clean HEAD + patch
  == current). This confirms the diff is neither stale nor malformed.
"""
import json, os, re, subprocess, sys

HUNK = re.compile(r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@')


def read_stdin():
    raw = sys.stdin.read().strip()
    return json.loads(raw) if raw else {}


def parse_check(text):
    errs = []
    lines = text.splitlines()
    has_minus_hdr = any(l.startswith('--- ') for l in lines)
    has_plus_hdr = any(l.startswith('+++ ') for l in lines)
    if not (has_minus_hdr and has_plus_hdr):
        errs.append('missing --- / +++ header pair')
    i = 0
    n = len(lines)
    saw_hunk = False
    while i < n:
        line = lines[i]
        m = HUNK.match(line)
        if m:
            saw_hunk = True
            ocount = int(m.group(2)) if m.group(2) is not None else 1
            ncount = int(m.group(4)) if m.group(4) is not None else 1
            old_seen = new_seen = 0
            i += 1
            while i < n:
                hl = lines[i]
                if hl.startswith('@@') or hl.startswith('--- ') or \
                   hl.startswith('diff ') or hl.startswith('index '):
                    break
                if hl.startswith('\\'):
                    i += 1
                    continue
                if hl == '' or hl.startswith(' '):
                    old_seen += 1
                    new_seen += 1
                elif hl.startswith('-'):
                    old_seen += 1
                elif hl.startswith('+'):
                    new_seen += 1
                else:
                    errs.append('hunk content line without space/+/- prefix: %r' % hl[:40])
                    break
                i += 1
            if old_seen != ocount:
                errs.append('hunk old count %d != actual %d' % (ocount, old_seen))
            if new_seen != ncount:
                errs.append('hunk new count %d != actual %d' % (ncount, new_seen))
        else:
            i += 1
    if not saw_hunk:
        errs.append('no @@ hunk header found')
    return (len(errs) == 0), errs


def git_reverse_check(repo, patch):
    try:
        out = subprocess.run(['git', '-C', repo, 'apply', '--check', '--reverse', patch],
                             capture_output=True, text=True, timeout=120)
        return out.returncode == 0, (out.stderr.strip() or out.stdout.strip())
    except Exception as e:
        return False, str(e)


def main():
    cfg = read_stdin()
    repo = cfg.get('repo_dir')
    patches = cfg.get('patches') or []
    if not repo or not patches:
        print(json.dumps({'error': 'repo_dir and patches required'}))
        return
    results = []
    all_ok = True
    for p in patches:
        entry = {'path': p, 'parse_ok': False, 'reverse_apply_ok': False, 'errors': []}
        if not os.path.isfile(p):
            entry['errors'].append('file not found')
            results.append(entry)
            all_ok = False
            continue
        with open(p, 'r', errors='replace') as f:
            text = f.read()
        ok, errs = parse_check(text)
        entry['parse_ok'] = ok
        entry['errors'].extend(errs)
        rok, rmsg = git_reverse_check(repo, p)
        entry['reverse_apply_ok'] = rok
        if not rok and rmsg:
            entry['errors'].append('git reverse-check: ' + rmsg)
        if not (ok and rok):
            all_ok = False
        results.append(entry)
    print(json.dumps({'results': results, 'all_ok': all_ok}))


if __name__ == '__main__':
    main()
