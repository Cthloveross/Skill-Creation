#!/usr/bin/env python3
"""CLI: stdin JSON {data,setpoint,[band],[ss_frac]} -> stdout metrics JSON."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hvac_lib import compute_metrics  # noqa: E402


def main():
    raw = sys.stdin.read().strip() or '{}'
    cfg = json.loads(raw)
    out = compute_metrics(cfg['data'], cfg['setpoint'],
                          band=cfg.get('band', 0.5),
                          ss_frac=cfg.get('ss_frac', 0.2))
    print(json.dumps(out))


if __name__ == '__main__':
    main()
