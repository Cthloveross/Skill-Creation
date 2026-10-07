#!/usr/bin/env python3
"""Build the exfil signature and optionally write it to a rules file.

Stdin JSON schema:
  {
    "params": { ... see rule_lib.build_rule ... },
    "write_to": "/root/local.rules"   # optional; if present, file is written
    "keep_existing": false             # optional; if true, append instead of
                                         # overwriting the whole file
  }

Stdout JSON:
  {"rule": "<rule string>", "written": "<path or null>"}
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rule_lib import build_rule  # noqa: E402


def main():
    data = json.load(sys.stdin)
    params = data.get('params', {})
    rule = build_rule(params)
    written = None
    target = data.get('write_to')
    if target:
        if data.get('keep_existing') and os.path.exists(target):
            with open(target, 'r') as fh:
                existing = fh.read().rstrip('\n')
            content = existing + '\n' + rule + '\n'
        else:
            content = rule + '\n'
        with open(target, 'w') as fh:
            fh.write(content)
        written = target
    json.dump({'rule': rule, 'written': written}, sys.stdout)
    sys.stdout.write('\n')


if __name__ == '__main__':
    main()
