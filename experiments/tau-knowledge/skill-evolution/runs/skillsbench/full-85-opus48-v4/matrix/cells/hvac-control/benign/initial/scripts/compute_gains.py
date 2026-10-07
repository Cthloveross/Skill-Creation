#!/usr/bin/env python3
"""CLI: stdin JSON {K,tau,[lambda],[settling_target]} -> stdout gains JSON."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hvac_lib import compute_gains  # noqa: E402


def main():
    raw = sys.stdin.read().strip() or '{}'
    cfg = json.loads(raw)
    out = compute_gains(cfg['K'], cfg['tau'], lam=cfg.get('lambda'),
                        settling_target=cfg.get('settling_target', 120.0))
    print(json.dumps(out))


if __name__ == '__main__':
    main()
