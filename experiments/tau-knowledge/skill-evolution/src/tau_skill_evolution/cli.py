"""Six stages shared by the bank and pooled SkillsBench experiments."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import shlex
from pathlib import Path

from .preflight import preflight
from .spec import ARMS, DEFAULT_CONFIG, load_spec
from .workflow import Workflow


def load_env(path: Path) -> None:
    """Load literal env assignments without executing shell code or logging values."""
    lines = path.read_text(encoding="utf-8").splitlines()
    meaningful = [
        line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#")
    ]
    if len(meaningful) == 1:
        raw = meaningful[0]
        name = raw.partition("=")[0]
        if "=" not in raw or not re.fullmatch(r"(?:export\s+)?[A-Za-z_][A-Za-z0-9_]*", name):
            try:
                parsed = shlex.split(raw, comments=True)
            except ValueError:
                raise ValueError("invalid env value at line 1") from None
            if len(parsed) == 1 and re.fullmatch(r"[A-Za-z0-9_+/=:.\-]{32,}", parsed[0]):
                os.environ.setdefault("AWS_BEARER_TOKEN_BEDROCK", parsed[0])
                return
    for number, line in enumerate(lines, 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        name, separator, value = line.partition("=")
        name = name.strip()
        if not separator or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            raise ValueError(f"invalid env assignment at line {number}")
        try:
            parsed = shlex.split(value, comments=True)
        except ValueError:
            raise ValueError(f"invalid env value at line {number}") from None
        if len(parsed) > 1:
            raise ValueError(f"invalid env value at line {number}")
        os.environ.setdefault(name, parsed[0] if parsed else "")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Frozen retrieval, one-shot Skill creation and CoEvo evolution"
    )
    parser.add_argument(
        "command", choices=("preflight", "create", "evolve", "evaluate", "report", "run")
    )
    parser.add_argument("--experiment", choices=("tau", "skillsbench"))
    parser.add_argument("--config", type=Path)
    parser.add_argument(
        "--env-file", type=Path, help="load literal env values; never execute the file"
    )
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument(
        "--demo",
        action="store_true",
        help="one benign task in Bubblewrap; no aggregate cgroup limits",
    )
    parser.add_argument("--task", action="append", help="restrict to selected task IDs")
    parser.add_argument(
        "--arm", choices=ARMS, action="append", help="restrict to selected conditions"
    )
    args = parser.parse_args(argv)
    try:
        if args.env_file is not None:
            load_env(args.env_file)
        config = args.config or (
            DEFAULT_CONFIG.parent / "skillsbench.yaml"
            if args.experiment == "skillsbench"
            else DEFAULT_CONFIG
        )
        spec = load_spec(config)
        if args.experiment is not None and spec.experiment != args.experiment:
            parser.error("--experiment differs from the selected configuration")
        if args.task and set(args.task) - set(spec.tasks):
            parser.error("--task must belong to the frozen experiment task population")
        if args.arm and set(args.arm) - set(spec.arms):
            parser.error("--arm is not supported by this experiment")
        selected_tasks = tuple(args.task) if args.task else None
        if args.command == "preflight":
            result = preflight(
                spec,
                demo=args.demo,
                authenticate=True,
                task_ids=selected_tasks,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result["ready"] else 2
        if args.run_dir is None:
            parser.error("--run-dir is required for this command")
        if args.demo and (not args.task or len(args.task) != 1 or args.arm != ["benign"]):
            parser.error("--demo requires exactly one --task and --arm benign")
        cells = tuple(
            (task, arm)
            for task, arm in spec.cells
            if (not args.task or task in args.task) and (not args.arm or arm in args.arm)
        )
        if args.command != "report":
            admission = preflight(
                spec,
                demo=args.demo,
                authenticate=True,
                task_ids=selected_tasks,
            )
            if not admission["ready"]:
                print(json.dumps(admission, ensure_ascii=False, indent=2))
                return 2
        args.run_dir.mkdir(parents=True, exist_ok=True)
        with (args.run_dir / ".lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError("another process owns this run directory") from None
            workflow = (
                Workflow(spec, args.run_dir, demo=True, demo_task=args.task[0])
                if args.demo
                else Workflow(spec, args.run_dir)
            )
            if args.command == "run":
                result = workflow.run(cells)
            elif args.command == "report":
                result = workflow.report()
            else:
                getattr(workflow, args.command)(cells)
                result = {
                    "namespace": spec.values["schema_version"],
                    "stage": args.command,
                    "selected_cells": len(cells),
                    "run_dir": str(args.run_dir),
                    "run_mode": "single-task-demo" if args.demo else "formal",
                }
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, RuntimeError, KeyError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
