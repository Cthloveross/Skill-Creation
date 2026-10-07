#!/usr/bin/env python3
"""Reopen a saved PDF and report stored field values.

stdin:  {"pdf_path":"...","expect":{name:value,...}}  (expect optional)
stdout: {"fields":{name:value},"checks":[{name,expected,actual,match}]}
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _pdf_common import read_fields  # noqa: E402


def _norm(v):
    if v is None:
        return ''
    return str(v).lstrip('/').strip()


def main():
    data = json.load(sys.stdin)
    pdf_path = data['pdf_path']
    expect = data.get('expect', {}) or {}

    fields = read_fields(pdf_path)
    values = {f['name']: f['value'] for f in fields}

    checks = []
    for name, exp in expect.items():
        actual = values.get(name)
        checks.append({
            'name': name,
            'expected': exp,
            'actual': actual,
            'match': _norm(actual) == _norm(exp),
        })

    json.dump({'fields': values, 'checks': checks}, sys.stdout, indent=2)
    sys.stdout.write('\n')


if __name__ == '__main__':
    main()
