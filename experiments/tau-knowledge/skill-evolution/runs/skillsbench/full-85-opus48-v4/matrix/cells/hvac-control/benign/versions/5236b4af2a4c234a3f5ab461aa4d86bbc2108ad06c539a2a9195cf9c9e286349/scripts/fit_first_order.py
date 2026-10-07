#!/usr/bin/env python3
"""CLI: stdin JSON {data,[power],[ambient]} -> stdout JSON model params."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hvac_lib import fit_first_order  # noqa: E402


def main():
    raw = sys.stdin.read().strip() or '{}'
    cfg = json.loads(raw)
    data = cfg['data']
    out = fit_first_order(data, power=cfg.get('power'), ambient=cfg.get('ambient'))
    print(json.dumps(out))


if __name__ == '__main__':
    main()
