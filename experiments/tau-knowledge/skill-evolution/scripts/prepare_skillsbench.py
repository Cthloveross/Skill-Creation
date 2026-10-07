#!/usr/bin/env python3
"""Prepare only pinned SkillsBench source/public pool and task runtimes."""

from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


def main() -> None:
    from tau_skill_evolution.skillsbench import prepare_pool, prepare_skillsbench

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", action="store_true")
    parser.add_argument("--pool", action="store_true")
    runtime = parser.add_mutually_exclusive_group()
    runtime.add_argument("--demo", action="store_true")
    runtime.add_argument("--docker", action="store_true")
    runtime.add_argument("--workspace", action="store_true")
    parser.add_argument(
        "--all-tasks",
        action="store_true",
        help="Prepare or report every task; --docker or --workspace.",
    )
    parser.add_argument("--task", default="3d-scan-calc")
    parser.add_argument(
        "--jobs",
        type=int,
        default=1,
        help="Parallel offline Docker builds; --docker --all-tasks only.",
    )
    parser.add_argument(
        "--runtime-lock",
        type=Path,
        help="Docker lock output; use {task_id} for --all-tasks. Relative to the experiment.",
    )
    parser.add_argument("--index-settings")
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    if args.jobs != 1 and not (args.docker and args.all_tasks):
        parser.error("parallel --jobs requires --docker --all-tasks")
    if args.all_tasks and not (args.docker or args.workspace):
        parser.error("--all-tasks requires --docker or --workspace")
    if args.runtime_lock is not None:
        if not args.docker:
            parser.error("--runtime-lock requires --docker")
        if args.all_tasks and "{task_id}" not in str(args.runtime_lock):
            parser.error("--all-tasks requires a {task_id} runtime lock template")
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
    if args.demo or args.docker or args.workspace:
        from tau_skill_evolution.skillsbench_runtime import (
            prepare_demo_runtime,
            prepare_docker,
            prepare_workspace_runtime,
        )

        function = (
            prepare_workspace_runtime
            if args.workspace
            else prepare_demo_runtime
            if args.demo
            else prepare_docker
        )
        if args.all_tasks:
            from tau_skill_evolution.skillsbench import SkillsBenchSource

            tasks = SkillsBenchSource(ROOT).manifest["tasks"]
        else:
            tasks = [args.task]
        settings = {"runtime_lock_path": args.runtime_lock} if args.runtime_lock else {}
        failed = False
        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            pending = {pool.submit(function, ROOT, task, **settings): task for task in tasks}
            for future in as_completed(pending):
                task = pending[future]
                try:
                    result = future.result()
                except Exception as exc:
                    failed = True
                    result = {"task_id": task, "prepared": False, "ready": False, "error": str(exc)}
                print(json.dumps({"task_id": task, **result}), flush=True)
        if failed:
            raise SystemExit(1)
    if args.index_settings:
        from tau_skill_evolution.skillsbench import prepare_dense

        print(json.dumps(prepare_dense(ROOT, json.loads(args.index_settings))), flush=True)
    if not any(
        (args.source, args.pool, args.demo, args.docker, args.workspace, args.index_settings)
    ):
        parser.error("select --source, --pool, --demo, --workspace or --docker")


if __name__ == "__main__":
    main()
