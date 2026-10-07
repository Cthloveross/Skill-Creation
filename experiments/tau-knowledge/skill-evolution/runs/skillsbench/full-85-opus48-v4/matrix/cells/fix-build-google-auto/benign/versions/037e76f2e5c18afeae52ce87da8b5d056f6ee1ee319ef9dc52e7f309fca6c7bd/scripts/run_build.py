#!/usr/bin/env python3
"""Run the CI/Maven build command, log to a file, and extract key errors.

stdin  JSON: {
  "cmd": "<shell command>" (required),
  "cwd": "<dir>" (optional),
  "log_path": "/tmp/build.log" (optional),
  "timeout": 600 (optional, seconds)
}
stdout JSON: {"exit_code", "success", "timed_out", "log_path",
              "tail" (last ~60 lines), "errors" (matched diagnostic lines)}

The full output is written to log_path; read it in sections for the earliest
root error. This runner does not modify any build script.
"""
import json, os, subprocess, sys, re

ERROR_PAT = re.compile(
    r'(\[ERROR\]|BUILD FAILURE|cannot find symbol|error:|COMPILATION ERROR|'
    r'Failed to execute goal|package .* does not exist|incompatible types|'
    r'symbol:|Tests run:.*Failures|BUILD SUCCESS)')


def read_stdin():
    raw = sys.stdin.read().strip()
    return json.loads(raw) if raw else {}


def main():
    cfg = read_stdin()
    cmd = cfg.get('cmd')
    if not cmd:
        print(json.dumps({'error': 'missing cmd'}))
        return
    cwd = cfg.get('cwd') or None
    log_path = cfg.get('log_path') or '/tmp/build.log'
    timeout = int(cfg.get('timeout') or 600)

    timed_out = False
    with open(log_path, 'w', errors='replace') as logf:
        try:
            proc = subprocess.run(cmd, shell=True, cwd=cwd, stdout=logf,
                                  stderr=subprocess.STDOUT, timeout=timeout)
            code = proc.returncode
        except subprocess.TimeoutExpired:
            timed_out = True
            code = 124

    tail, errors = [], []
    try:
        with open(log_path, 'r', errors='replace') as f:
            lines = f.readlines()
        tail = [l.rstrip('\n') for l in lines[-60:]]
        for i, l in enumerate(lines):
            if ERROR_PAT.search(l):
                errors.append({'line_no': i + 1, 'text': l.rstrip('\n')})
            if len(errors) >= 120:
                break
    except Exception as e:
        errors.append({'line_no': 0, 'text': 'log read failed: %s' % e})

    success = (code == 0) and not timed_out
    print(json.dumps({
        'exit_code': code, 'success': success, 'timed_out': timed_out,
        'log_path': log_path, 'tail': tail, 'errors': errors,
    }))


if __name__ == '__main__':
    main()
