#!/usr/bin/env python3
"""Inspect the BugSwarm build environment.

stdin  JSON: {"base": "/home/travis/build/failed" (optional)}
stdout JSON: {
  "base", "repo_dir", "git_root", "pom_files", "travis_yml_path",
  "travis_script_lines", "reproduction_scripts", "suggested_commands", "notes"
}

The repo_dir is the editable repository: the directory under
<base>/<repo>/<id> that contains pom.xml and/or a .git directory. Nothing is
assumed about the fix; this only reports evidence.
"""
import json, os, subprocess, sys, re


def read_stdin():
    try:
        raw = sys.stdin.read().strip()
        return json.loads(raw) if raw else {}
    except Exception:
        return {}


def find_repo_dir(base):
    # Expect base/<repo>/<id>. Prefer deepest dir containing pom.xml or .git.
    best = None
    if not os.path.isdir(base):
        return None
    for root, dirs, files in os.walk(base):
        depth = root[len(base):].count(os.sep)
        if depth > 4:
            dirs[:] = []
            continue
        if 'pom.xml' in files or '.git' in dirs:
            # choose the shallowest repo root (the one that owns the .git)
            if '.git' in dirs:
                return root
            if best is None:
                best = root
    return best


def git_root(path):
    try:
        out = subprocess.run(['git', '-C', path, 'rev-parse', '--show-toplevel'],
                             capture_output=True, text=True, timeout=30)
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception:
        pass
    return None


def parse_travis(path):
    lines = []
    try:
        with open(path, 'r', errors='replace') as f:
            content = f.read()
    except Exception:
        return lines
    # grab items under a 'script:' block (simple heuristic)
    in_script = False
    base_indent = None
    for ln in content.splitlines():
        stripped = ln.strip()
        if re.match(r'^script\s*:', stripped):
            in_script = True
            base_indent = len(ln) - len(ln.lstrip())
            # inline form: script: mvn ...
            inline = stripped.split(':', 1)[1].strip()
            if inline:
                lines.append(inline.strip('"\''))
                in_script = False
            continue
        if in_script:
            if not stripped:
                continue
            indent = len(ln) - len(ln.lstrip())
            if indent <= (base_indent or 0) and not stripped.startswith('-'):
                in_script = False
                continue
            item = stripped.lstrip('- ').strip().strip('"\'')
            if item:
                lines.append(item)
    return lines


def find_scripts(base):
    found = []
    search_dirs = [base, os.path.expanduser('~'), '/usr/local/bin', '/home/travis']
    seen = set()
    for d in search_dirs:
        if not d or not os.path.isdir(d) or d in seen:
            continue
        seen.add(d)
        try:
            for name in os.listdir(d):
                if name.endswith('.sh') or name.startswith('run'):
                    p = os.path.join(d, name)
                    if os.path.isfile(p):
                        found.append(p)
        except Exception:
            pass
    return sorted(set(found))


def main():
    cfg = read_stdin()
    base = cfg.get('base') or '/home/travis/build/failed'
    out = {'base': base, 'notes': []}

    repo = find_repo_dir(base)
    out['repo_dir'] = repo
    if repo is None:
        out['notes'].append('No repo dir found under base; pass {"base": ...} or inspect manually.')
        print(json.dumps(out))
        return

    out['git_root'] = git_root(repo) or repo

    poms = []
    for root, dirs, files in os.walk(repo):
        if '.git' in dirs:
            dirs.remove('.git')
        if root.count(os.sep) - repo.count(os.sep) > 3:
            dirs[:] = []
        if 'pom.xml' in files:
            poms.append(os.path.join(root, 'pom.xml'))
    out['pom_files'] = sorted(poms)[:200]

    travis = os.path.join(repo, '.travis.yml')
    out['travis_yml_path'] = travis if os.path.isfile(travis) else None
    out['travis_script_lines'] = parse_travis(travis) if out['travis_yml_path'] else []

    out['reproduction_scripts'] = find_scripts(base)

    suggestions = []
    for s in out['travis_script_lines']:
        suggestions.append(s)
    if os.path.isfile(os.path.join(repo, 'pom.xml')):
        suggestions.append('mvn -B -fae install  # fallback; verify against the real CI script')
    out['suggested_commands'] = suggestions
    out['notes'].append('Prefer an existing reproduction script or the .travis.yml script lines over the fallback.')
    out['notes'].append('Always redirect Maven output to a log file (run_build.py does this).')
    print(json.dumps(out))


if __name__ == '__main__':
    main()
