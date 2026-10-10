#!/usr/bin/env python3
"""Prepare only pinned SkillsBench source/public pool and task runtimes."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


def _ensure_dense_runtime(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    """Re-exec the narrow dense worker in the pinned embedding environment."""
    if not args.index_settings:
        return
    if importlib.util.find_spec("transformers") is not None:
        return
    try:
        embedding = json.loads(args.index_settings)
    except json.JSONDecodeError as exc:
        parser.error(f"--index-settings is not valid JSON: {exc}")
    vllm = embedding.get("vllm") if isinstance(embedding, dict) else None
    if not isinstance(vllm, str) or not vllm:
        parser.error("dense preparation requires embedding.vllm")
    target = (ROOT / vllm).absolute().parent / "python"
    if target.absolute() == Path(sys.executable).absolute() or not target.is_file():
        parser.error(f"pinned embedding Python is unavailable: {target}")
    os.execve(str(target), [str(target), str(Path(__file__).resolve()), *sys.argv[1:]], os.environ)


def _prepare_dense_in_pinned_runtime(
    embedding: dict[str, object], directory: Path | None
) -> dict[str, object]:
    """Run only the embedding worker in its pinned Python environment."""
    target = (ROOT / str(embedding["vllm"])).absolute().parent / "python"
    if not target.is_file():
        raise RuntimeError(f"pinned embedding Python is unavailable: {target}")
    command = [
        str(target),
        str(Path(__file__).resolve()),
        "--index-settings",
        json.dumps(embedding, sort_keys=True),
    ]
    if directory is not None:
        command.extend(("--pool-directory", str(directory)))
    completed = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        timeout=3600,
    )
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    if len(lines) != 1:
        raise RuntimeError("dense preparation returned an invalid result")
    result = json.loads(lines[0])
    if not isinstance(result, dict) or result.get("ready") is not True:
        raise RuntimeError("dense preparation did not seal a ready index")
    return result


def main() -> None:
    from tau_skill_evolution.skillsbench import prepare_pool, prepare_skillsbench

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "configs/skillsbench.yaml",
        help="Pinned experiment configuration; defaults to the current SkillsBench method.",
    )
    parser.add_argument("--source", action="store_true")
    parser.add_argument("--pool", action="store_true")
    parser.add_argument("--injected-pools", action="store_true")
    parser.add_argument("--all-indices", action="store_true")
    parser.add_argument("--freeze-matrix", action="store_true")
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
    parser.add_argument(
        "--pool-directory",
        type=Path,
        help="Prepared pool used by --index-settings; defaults to the benign pool.",
    )
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
    _ensure_dense_runtime(args, parser)
    if args.source:
        print(json.dumps(prepare_skillsbench(ROOT)), flush=True)
    if args.pool or args.injected_pools or args.all_indices or args.freeze_matrix:
        from tokenizers import Tokenizer

        cache = Path(os.environ.get("HF_HOME", str(Path.home() / ".cache/huggingface")))
        snapshot = cache / "hub/models--Qwen--Qwen3-Embedding-4B/snapshots"
        tokenizer = Tokenizer.from_file(
            str(snapshot / "5cf2132abc99cad020ac570b19d031efec650f2b/tokenizer.json")
        )
        if args.pool:
            print(json.dumps(prepare_pool(ROOT, tokenizer)), flush=True)
    if args.injected_pools or args.all_indices or args.freeze_matrix:
        from tau_skill_evolution.skillsbench import selected_pool
        from tau_skill_evolution.skillsbench_attack import prepare_injected_pool
        from tau_skill_evolution.spec import load_spec

        spec = load_spec(args.config)
        if spec.namespace != "skillsbench.skill-evolution.v8":
            parser.error("condition preparation requires a SkillsBench v8 config")
        prepared = {
            arm: (
                selected_pool(spec, arm)
                if arm == "benign"
                else prepare_injected_pool(spec, arm, tokenizer)
            )
            for arm in spec.arms
        }
        print(
            json.dumps({arm: str(path.relative_to(ROOT)) for arm, path in prepared.items()}),
            flush=True,
        )
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

        print(
            json.dumps(
                prepare_dense(
                    ROOT,
                    json.loads(args.index_settings),
                    directory=args.pool_directory,
                )
            ),
            flush=True,
        )
    if args.all_indices or args.freeze_matrix:
        for arm, directory in prepared.items():
            result = _prepare_dense_in_pinned_runtime(
                spec.values["embedding"],
                None if arm == "benign" else directory,
            )
            print(json.dumps({"condition_id": arm, **result}), flush=True)
    if args.freeze_matrix:
        from tau_skill_evolution.skillsbench_attack import freeze_matrix_manifest

        print(json.dumps(freeze_matrix_manifest(spec, prepared)), flush=True)
    if not any(
        (
            args.source,
            args.pool,
            args.injected_pools,
            args.all_indices,
            args.freeze_matrix,
            args.demo,
            args.docker,
            args.workspace,
            args.index_settings,
        )
    ):
        parser.error("select a source, pool/index, runtime, or matrix preparation operation")


if __name__ == "__main__":
    main()
