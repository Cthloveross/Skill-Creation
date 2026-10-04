#!/usr/bin/env python3
"""Prepare only pinned SkillsBench source/public pool and task runtimes."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


def main() -> None:
    from tau_skill_evolution.skillsbench import prepare_pool, prepare_skillsbench

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", action="store_true")
    parser.add_argument("--pool", action="store_true")
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--docker", action="store_true")
    parser.add_argument("--task", default="3d-scan-calc")
    parser.add_argument("--index-settings")
    args = parser.parse_args()
    if args.source:
        print(json.dumps(prepare_skillsbench(ROOT)), flush=True)
    if args.pool:
        from tokenizers import Tokenizer

        cache = Path(os.environ.get("HF_HOME", str(Path.home() / ".cache/huggingface")))
        snapshot = cache / "hub/models--Qwen--Qwen3-Embedding-4B/snapshots"
        tokenizer = Tokenizer.from_file(
            str(snapshot / "5cf2132abc99cad020ac570b19d031efec650f2b/tokenizer.json")
        )
        print(json.dumps(prepare_pool(ROOT, tokenizer)), flush=True)
    if args.demo or args.docker:
        from tau_skill_evolution.skillsbench_runtime import prepare_demo_runtime, prepare_docker

        function = prepare_demo_runtime if args.demo else prepare_docker
        print(json.dumps(function(ROOT, args.task)), flush=True)
    if args.index_settings:
        from tau_skill_evolution.skillsbench import prepare_dense

        print(json.dumps(prepare_dense(ROOT, json.loads(args.index_settings))), flush=True)
    if not any((args.source, args.pool, args.demo, args.docker, args.index_settings)):
        parser.error("select --source, --pool, --demo or --docker")


if __name__ == "__main__":
    main()
