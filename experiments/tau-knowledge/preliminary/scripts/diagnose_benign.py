#!/usr/bin/env python3
"""Inspect existing benign artifacts without model calls or experiment replay."""

from __future__ import annotations

import argparse
from pathlib import Path

from r2sp_tau_knowledge.diagnostics import write_benign_report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, action="append", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    print(write_benign_report(args.run_root, args.output_root))


if __name__ == "__main__":
    main()
