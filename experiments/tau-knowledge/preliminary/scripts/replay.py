#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from r2sp_tau_knowledge.replay import replay_run  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay a tau preliminary run from artifacts")
    parser.add_argument("run", type=Path)
    args = parser.parse_args()
    print(json.dumps(replay_run(args.run), ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
