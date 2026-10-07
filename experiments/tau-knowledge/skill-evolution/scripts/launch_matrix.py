#!/usr/bin/env python3
"""Run many (task, arm) cells concurrently in ONE shared run directory.

Each cell is a separate ``r2sp run --task T --arm A --no-interim-report``
subprocess bound to one AWS account via ``AWS_BEARER_TOKEN_BEDROCK_FILE``
(a token file maintained by ``bedrock_token_daemon.py``). Cells lock only
``<run-dir>/locks/<task>__<arm>.lock`` so they do not contend for the run-dir
lock; the shared ``journal/identity.json`` is created once up front by
``r2sp report`` and the final ``report.json`` is written once at the end.

Runs with the experiment virtualenv Python (``.venv/bin/python``).
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TOKEN_FILE_ENV = "AWS_BEARER_TOKEN_BEDROCK_FILE"
DROPPED_ENV = ("AWS_PROFILE", "AWS_BEARER_TOKEN_BEDROCK")
# Per-cell stage order. "no-skill" is the SkillsBench control (`evaluate --no-skill`),
# which the handoff runs before any Skill is created; "run" is create/evolve/evaluate.
STAGES = ("no-skill", "run")
DEFAULT_R2SP = None
TERMINATE_GRACE_SECONDS = 30.0


# ----------------------------------------------------------------------------
# pure helpers (imported by tests)
# ----------------------------------------------------------------------------


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def filter_cells(
    cells: tuple[tuple[str, str], ...] | list[tuple[str, str]],
    tasks: list[str] | None,
    arms: list[str] | None,
) -> list[tuple[str, str]]:
    """Keep the spec's cell order; empty/None filters keep everything."""
    return [
        (task, arm)
        for task, arm in cells
        if (not tasks or task in tasks) and (not arms or arm in arms)
    ]


def assign_accounts(cells: list[tuple[str, str]], accounts: list[str]) -> dict[str, str]:
    """Round-robin ``"task|arm" -> account``."""
    if not accounts:
        raise ValueError("at least one account is required")
    return {
        cell_key(task, arm): accounts[index % len(accounts)]
        for index, (task, arm) in enumerate(cells)
    }


def cell_key(task: str, arm: str) -> str:
    return f"{task}|{arm}"


def token_path(token_dir: Path, account: str) -> Path:
    return Path(token_dir) / f"{account}.json"


def discover_accounts(token_dir: Path) -> list[str]:
    return sorted(
        path.stem
        for path in Path(token_dir).glob("*.json")
        if path.stem != "status" and path.stem.isdigit()
    )


def entrypoint(r2sp: str | None) -> list[str]:
    return [r2sp] if r2sp else [sys.executable, "-m", "tau_skill_evolution.cli"]


def parse_stages(value: str) -> tuple[str, ...]:
    stages = tuple(item.strip() for item in value.split(",") if item.strip())
    if (
        not stages
        or any(stage not in STAGES for stage in stages)
        or len(set(stages)) != len(stages)
    ):
        raise ValueError("--stages must be a comma-separated subset of " + ",".join(STAGES))
    if list(stages) != [stage for stage in STAGES if stage in stages]:
        raise ValueError("--stages must keep the order " + ",".join(STAGES))
    return stages


def build_command(
    r2sp: str | None,
    experiment: str,
    config: Path,
    run_dir: Path,
    task: str,
    arm: str,
    runtime: str = "docker",
    stage: str = "run",
) -> list[str]:
    if stage not in STAGES:
        raise ValueError(f"unknown stage {stage!r}")
    command = [
        *entrypoint(r2sp),
        "evaluate" if stage == "no-skill" else "run",
        "--runtime",
        runtime,
        "--experiment",
        experiment,
        "--config",
        str(config),
        "--task",
        task,
        "--arm",
        arm,
        "--run-dir",
        str(run_dir),
        "--no-interim-report",
    ]
    if stage == "no-skill":
        command.append("--no-skill")
    return command


def build_env(base: dict[str, str], token_file: Path) -> dict[str, str]:
    env = {key: value for key, value in base.items() if key not in DROPPED_ENV}
    env[TOKEN_FILE_ENV] = str(token_file)
    return env


def report_command(
    r2sp: str | None, experiment: str, config: Path, run_dir: Path, runtime: str = "docker"
) -> list[str]:
    return [
        *entrypoint(r2sp),
        "report",
        "--runtime",
        runtime,
        "--experiment",
        experiment,
        "--config",
        str(config),
        "--run-dir",
        str(run_dir),
    ]


def executable(path: str) -> bool:
    return os.path.isfile(path) and os.access(path, os.X_OK)


def log_path(run_dir: Path, task: str, arm: str) -> Path:
    return Path(run_dir) / "logs" / f"{task}__{arm}.log"


def build_status(
    *,
    started_at: str,
    experiment: str,
    config: Path,
    cells: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    finished = [item for item in cells.values() if item.get("finished_at") is not None]
    running = [
        item
        for item in cells.values()
        if item.get("started_at") is not None and item.get("finished_at") is None
    ]
    failed = [item for item in finished if item.get("exit_code") != 0]
    return {
        "started_at": started_at,
        "updated_at": now_iso(),
        "experiment": experiment,
        "config": str(config),
        "cells": cells,
        "running": len(running),
        "finished": len(finished),
        "failed": len(failed),
        "total": len(cells),
    }


def write_atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


# ----------------------------------------------------------------------------
# launcher
# ----------------------------------------------------------------------------


class Launcher:
    def __init__(self, args: argparse.Namespace, cells: list[tuple[str, str]]) -> None:
        self.args = args
        self.cells = cells
        self.accounts = assign_accounts(cells, args.accounts)
        self.stages: tuple[str, ...] = tuple(getattr(args, "stages", None) or ("run",))
        self.started_at = now_iso()
        self.status_cells: dict[str, dict[str, Any]] = {
            cell_key(task, arm): {
                "account": self.accounts[cell_key(task, arm)],
                "pid": None,
                "started_at": None,
                "finished_at": None,
                "exit_code": None,
                "stage": None,
                "stages": {},
            }
            for task, arm in cells
        }
        self.processes: dict[str, tuple[subprocess.Popen[bytes], Any]] = {}
        self.stop = False
        self.authentication_status: int | None = None
        self.runtime = getattr(args, "runtime", "docker")
        # Bounded re-queue of a stage that exited non-zero: `r2sp` resumes from the
        # cell journal, so a repeat never re-dispatches a sealed model request. This
        # absorbs transient admission failures (Docker probes under load).
        self.max_attempts = int(getattr(args, "max_attempts", 3) or 1)
        # Optional live throttle: an integer in this file overrides --max-concurrent
        # on every scheduling pass, so the operator can raise or lower admission
        # without restarting (restarting would kill the running cells).
        self.max_concurrent_file = getattr(args, "max_concurrent_file", None)
        self.retry_delay_seconds = float(getattr(args, "retry_delay_seconds", 60.0) or 0.0)
        self.deferred: list[tuple[float, str, str]] = []

    def max_concurrent(self) -> int:
        limit = int(self.args.max_concurrent)
        path = self.max_concurrent_file
        if path:
            try:
                value = int(Path(path).read_text().strip())
                if value > 0:
                    limit = value
            except (OSError, ValueError):
                pass
        return limit

    def next_stage(self, key: str) -> str | None:
        done = self.status_cells[key]["stages"]
        for stage in self.stages:
            record = done.get(stage)
            if record is None or record.get("requeued"):
                return stage
        return None

    def write_status(self) -> None:
        status = build_status(
            started_at=self.started_at,
            experiment=self.args.experiment,
            config=self.args.config,
            cells=self.status_cells,
        )
        status["authentication_status"] = self.authentication_status
        status["runtime"] = self.runtime
        write_atomic_json(Path(self.args.run_dir) / "launcher-status.json", status)

    def start(self, task: str, arm: str) -> None:
        key = cell_key(task, arm)
        account = self.accounts[key]
        stage = self.next_stage(key)
        if stage is None:
            return
        command = build_command(
            self.args.r2sp,
            self.args.experiment,
            self.args.config,
            self.args.run_dir,
            task,
            arm,
            runtime=self.runtime,
            stage=stage,
        )
        env = build_env(dict(os.environ), token_path(self.args.token_dir, account))
        log_file = log_path(self.args.run_dir, task, arm)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        stream = log_file.open("ab")
        stream.write(f"=== {now_iso()} stage={stage} ===\n".encode())
        stream.flush()
        process = subprocess.Popen(
            command, stdout=stream, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, env=env
        )
        self.processes[key] = (process, stream)
        cell = self.status_cells[key]
        previous = cell["stages"].get(stage) or {}
        cell["stages"][stage] = {
            "pid": process.pid,
            "started_at": now_iso(),
            "finished_at": None,
            "exit_code": None,
            "attempts": int(previous.get("attempts", 0)) + 1,
            "history": list(previous.get("history", [])),
            "requeued": False,
        }
        cell.update(pid=process.pid, stage=stage)
        if cell["started_at"] is None:
            cell["started_at"] = now_iso()
        self.write_status()
        print(f"started {key} stage={stage} account={account} pid={process.pid}", flush=True)

    def reap(self) -> None:
        for key, (process, stream) in list(self.processes.items()):
            code = process.poll()
            if code is None:
                continue
            stream.close()
            del self.processes[key]
            cell = self.status_cells[key]
            stage = cell["stage"] or self.stages[-1]
            record = cell["stages"].setdefault(
                stage,
                {
                    "pid": getattr(process, "pid", None),
                    "started_at": cell["started_at"],
                    "finished_at": None,
                    "exit_code": None,
                },
            )
            record.update(finished_at=now_iso(), exit_code=code)
            task, arm = key.split("|", 1)
            journal = Path(self.args.run_dir) / "cells" / task / arm / "journal"
            for path in journal.glob("*/failure.json"):
                failure = json.loads(path.read_text())
                if failure.get("code") == "authentication_failed" and failure.get("status") in (
                    401,
                    403,
                ):
                    self.authentication_status = failure["status"]
                    self.stop = True
                    break
            print(f"finished {key} stage={stage} exit={code}", flush=True)
            if code and not self.stop and record.get("attempts", 1) < self.max_attempts:
                record["history"] = [*record.get("history", []), {"exit_code": code}]
                record["requeued"] = True
                self.deferred.append((time.monotonic() + self.retry_delay_seconds, task, arm))
                self.write_status()
                print(
                    f"requeue {key} stage={stage} attempt={record['attempts']} "
                    f"in {self.retry_delay_seconds:.0f}s",
                    flush=True,
                )
                continue
            if not self.stop and self.next_stage(key) is not None:
                # A control failure is journaled as NOT_MEASURED; the chain still runs.
                self.start(task, arm)
                continue
            # The cell's exit code is the main chain's when it ran, else the last stage's.
            final = cell["stages"].get("run") or cell["stages"][stage]
            cell.update(finished_at=now_iso(), exit_code=final["exit_code"])
            self.write_status()

    def terminate_children(self) -> None:
        for process, _ in self.processes.values():
            if process.poll() is None:
                process.terminate()
        deadline = time.monotonic() + TERMINATE_GRACE_SECONDS
        while time.monotonic() < deadline and any(
            process.poll() is None for process, _ in self.processes.values()
        ):
            time.sleep(0.2)
        for process, _ in self.processes.values():
            if process.poll() is None:
                process.kill()
        self.reap()

    def run(self) -> int:
        pending = list(self.cells)
        self.write_status()
        try:
            while (pending or self.processes or self.deferred) and not self.stop:
                self.reap()
                if self.stop:
                    break
                now = time.monotonic()
                ready = [item for item in self.deferred if item[0] <= now]
                limit = self.max_concurrent()
                if ready and len(self.processes) < limit:
                    self.deferred.remove(ready[0])
                    self.start(ready[0][1], ready[0][2])
                    time.sleep(max(0.0, self.args.stagger_seconds))
                    continue
                if pending and len(self.processes) < limit:
                    task, arm = pending.pop(0)
                    self.start(task, arm)
                    time.sleep(max(0.0, self.args.stagger_seconds))
                    continue
                time.sleep(1.0)
        except BaseException:
            # A failed Popen or an unexpected error must not orphan running cells.
            self.terminate_children()
            self.write_status()
            raise
        if self.stop:
            self.terminate_children()
            self.write_status()
            return 2 if self.authentication_status is not None else 130
        self.reap()
        return 0


def _dry_run(args: argparse.Namespace, cells: list[tuple[str, str]]) -> None:
    accounts = assign_accounts(cells, args.accounts)
    for task, arm in cells:
        account = accounts[cell_key(task, arm)]
        for stage in args.stages:
            command = build_command(
                args.r2sp,
                args.experiment,
                args.config,
                args.run_dir,
                task,
                arm,
                runtime=args.runtime,
                stage=stage,
            )
            print(
                f"{TOKEN_FILE_ENV}={token_path(args.token_dir, account)} "
                + " ".join(command)
                + f"  # log={log_path(args.run_dir, task, arm)}"
            )
    print(
        f"planned {len(cells)} cells x {len(args.stages)} stage(s) "
        f"over {len(args.accounts)} accounts",
        flush=True,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--experiment", choices=("tau", "skillsbench"), required=True)
    parser.add_argument("--runtime", choices=("workspace", "docker"), default="docker")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--token-dir", type=Path, required=True)
    parser.add_argument("--accounts", help="comma-separated; default: all <ID>.json in token-dir")
    parser.add_argument("--max-concurrent", type=int)
    parser.add_argument("--stagger-seconds", type=float, default=1.0)
    parser.add_argument("--task", action="append")
    parser.add_argument("--arm", action="append")
    parser.add_argument(
        "--cells-file",
        type=Path,
        help='JSON list of exact "task|arm" cells to run (intersected with --task/--arm)',
    )
    parser.add_argument("--r2sp", default=DEFAULT_R2SP)
    parser.add_argument(
        "--stages",
        default="run",
        help='comma-separated per-cell stage order; "no-skill,run" adds the SkillsBench control',
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=3,
        help="re-queue a stage that exits non-zero up to this many starts (journal resume)",
    )
    parser.add_argument("--retry-delay-seconds", type=float, default=60.0)
    parser.add_argument(
        "--max-concurrent-file",
        type=Path,
        help="file holding an integer that overrides --max-concurrent while running",
    )
    parser.add_argument("--skip-final-report", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    args.config = args.config.resolve()
    args.run_dir = args.run_dir.resolve()
    args.token_dir = args.token_dir.resolve()
    try:
        args.stages = parse_stages(args.stages)
    except ValueError as exc:
        parser.error(str(exc))
    if args.max_concurrent is None:
        args.max_concurrent = 1 if args.runtime == "workspace" else 96
    if args.max_concurrent <= 0:
        parser.error("--max-concurrent must be positive")
    if args.max_attempts <= 0 or args.retry_delay_seconds < 0:
        parser.error("--max-attempts must be positive and --retry-delay-seconds non-negative")
    if args.r2sp is not None and not executable(args.r2sp):
        parser.error(f"--r2sp is not an executable file: {args.r2sp}")
    args.accounts = (
        [item.strip() for item in args.accounts.split(",") if item.strip()]
        if args.accounts
        else discover_accounts(args.token_dir)
    )
    if not args.accounts:
        parser.error("no accounts: pass --accounts or populate --token-dir with <ID>.json files")
    missing = [
        account for account in args.accounts if not token_path(args.token_dir, account).is_file()
    ]
    if missing and not args.dry_run:
        parser.error("token files missing for accounts: " + ", ".join(missing))

    from tau_skill_evolution.journal import _create_identity_exclusive
    from tau_skill_evolution.spec import load_spec

    spec = load_spec(args.config)
    if spec.experiment != args.experiment:
        parser.error("--experiment differs from the selected configuration")
    if args.task and set(args.task) - set(spec.tasks):
        parser.error("--task must belong to the frozen experiment task population")
    if args.arm and set(args.arm) - set(spec.arms):
        parser.error("--arm is not supported by this experiment")
    if "no-skill" in args.stages and spec.experiment != "skillsbench":
        parser.error("the no-skill control stage exists only for skillsbench")
    cells = filter_cells(spec.cells, args.task, args.arm)
    if args.cells_file is not None:
        wanted = json.loads(args.cells_file.read_text(encoding="utf-8"))
        if not isinstance(wanted, list) or not all(
            isinstance(item, str) and item.count("|") == 1 for item in wanted
        ):
            parser.error('--cells-file must be a JSON list of "task|arm" strings')
        unknown = set(wanted) - {f"{task}|{arm}" for task, arm in spec.cells}
        if unknown:
            parser.error(
                "--cells-file names cells outside the matrix: " + ", ".join(sorted(unknown))
            )
        cells = [(task, arm) for task, arm in cells if f"{task}|{arm}" in set(wanted)]
    if not cells:
        parser.error("no cells selected")

    if args.dry_run:
        _dry_run(args, cells)
        return 0

    # (1) Initialise the shared run identity once, without credentials or model calls.
    args.run_dir.mkdir(parents=True, exist_ok=True)
    (args.run_dir / "locks").mkdir(exist_ok=True)
    (args.run_dir / "logs").mkdir(exist_ok=True)
    launcher_identity = {"identity": spec.identity, "runtime": args.runtime}
    identity_path = args.run_dir / "launcher-identity.json"
    _create_identity_exclusive(identity_path, launcher_identity)
    if json.loads(identity_path.read_text()) != launcher_identity:
        parser.error("launcher configuration or runtime differs from the existing run")
    report = report_command(
        args.r2sp, args.experiment, args.config, args.run_dir, runtime=args.runtime
    )
    initial = subprocess.run(report, capture_output=True, text=True, check=False)
    if initial.returncode != 0:
        sys.stderr.write(initial.stdout[-2000:] + initial.stderr[-2000:])
        sys.stderr.write("\ninitial r2sp report failed; aborting\n")
        return 2

    launcher = Launcher(args, cells)

    def _stop(signum: int, _frame: Any) -> None:
        launcher.stop = True
        print(f"received signal {signum}; terminating children", flush=True)

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    code = launcher.run()
    if code != 0:
        return code

    status = launcher.status_cells
    total = len(status)
    ok = sum(1 for item in status.values() if item["exit_code"] == 0)
    if not args.skip_final_report:
        final = subprocess.run(report, capture_output=True, text=True, check=False)
        if final.returncode != 0:
            sys.stderr.write(final.stdout[-2000:] + final.stderr[-2000:])
            sys.stderr.write("\nfinal r2sp report failed\n")
            return 2
    print(
        f"cells total={total} exit0={ok} nonzero={total - ok} "
        f"report={args.run_dir / 'report.json'}",
        flush=True,
    )
    return 0 if ok == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
