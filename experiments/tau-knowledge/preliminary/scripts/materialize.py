#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from r2sp_tau_knowledge.materialize import CorpusMaterializer  # noqa: E402


def main() -> int:
    materializer = CorpusMaterializer()
    result = []
    for profile in ("mock-api-call", "delete-sentinel"):
        for arm in ("benign", "poison"):
            result.append(materializer.materialize(profile, arm).to_dict())
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
