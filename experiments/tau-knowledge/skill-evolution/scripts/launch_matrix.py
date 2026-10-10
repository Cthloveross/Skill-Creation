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
import fcntl
import hashlib
import json
import os
import signal
import stat
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import Callable
from contextlib import contextmanager, suppress
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

TOKEN_FILE_ENV = "AWS_BEARER_TOKEN_BEDROCK_FILE"
DROPPED_ENV = ("AWS_PROFILE", "AWS_BEARER_TOKEN_BEDROCK")
DEFAULT_R2SP = None
TERMINATE_GRACE_SECONDS = 30.0
TOKEN_EXPIRY_MARGIN = timedelta(seconds=60)
MAX_TOKEN_FILE_BYTES = 1024 * 1024
MAX_CREDENTIAL_LOG_BYTES = 256 * 1024
CREDENTIAL_CODES = {"credential_expired", "credential_unavailable"}


class TokenValidationError(RuntimeError):
    """A local token file failed admission before a child could be started."""

    def __init__(self, code: str, path: Path, detail: str) -> None:
        super().__init__(f"{code}: {detail}: {path}")
        self.code = code
        self.path = Path(path)


class LauncherLockError(RuntimeError):
    """Another launcher already owns this run directory."""


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
    if not cells:
        return {}
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


def _parse_expiry(value: object) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("expires_at must be an ISO-8601 string")
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _validate_token_generation(
    path: Path, *, now: datetime
) -> tuple[dict[str, str] | None, TokenValidationError | None, tuple[int, int]]:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        raise TokenValidationError(
            "credential_unavailable", path, "token file is missing, unreadable, or a symlink"
        ) from None
    error: TokenValidationError | None = None
    value: Any = None
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            error = TokenValidationError(
                "credential_unavailable", path, "token file is not a regular file"
            )
        elif metadata.st_uid != os.geteuid():
            error = TokenValidationError(
                "credential_unavailable", path, "token file is not owned by the current user"
            )
        elif stat.S_IMODE(metadata.st_mode) != 0o600:
            error = TokenValidationError(
                "credential_unavailable", path, "token file permissions must be exactly 0600"
            )
        elif metadata.st_size > MAX_TOKEN_FILE_BYTES:
            error = TokenValidationError(
                "credential_unavailable", path, "token file exceeds the size limit"
            )
        else:
            try:
                raw = os.read(descriptor, MAX_TOKEN_FILE_BYTES + 1)
                value = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                error = TokenValidationError(
                    "credential_unavailable", path, "token file is not valid JSON"
                )
    finally:
        os.close(descriptor)
    if error is None and (
        not isinstance(value, dict)
        or not isinstance(value.get("token"), str)
        or not value["token"]
        or "expires_at" not in value
    ):
        error = TokenValidationError("credential_unavailable", path, "token file is malformed")
    expires_at = None
    if error is None:
        try:
            expires_at = _parse_expiry(value["expires_at"])
        except (TypeError, ValueError):
            error = TokenValidationError(
                "credential_unavailable", path, "token file has an invalid expires_at"
            )
    if error is None and now >= expires_at - TOKEN_EXPIRY_MARGIN:
        error = TokenValidationError(
            "credential_expired", path, "token is expired or expires within 60 seconds"
        )
    result = {"expires_at": expires_at.strftime("%Y-%m-%dT%H:%M:%SZ")} if error is None else None
    return result, error, (metadata.st_dev, metadata.st_ino)


def validate_token_file(path: Path, *, now: datetime | None = None) -> dict[str, str]:
    """Validate one complete atomically published token generation."""

    path = Path(path)
    current = now or datetime.now(timezone.utc)
    for _attempt in range(3):
        result, error, identity = _validate_token_generation(path, now=current)
        try:
            published = os.lstat(path)
        except OSError:
            continue
        if (published.st_dev, published.st_ino) != identity:
            continue
        if error is not None:
            raise error
        assert result is not None
        return result
    raise TokenValidationError(
        "credential_unavailable", path, "token file changed repeatedly during validation"
    )


def validate_accounts(token_dir: Path, accounts: list[str]) -> dict[str, dict[str, str]]:
    return {account: validate_token_file(token_path(token_dir, account)) for account in accounts}


def entrypoint(r2sp: str | None) -> list[str]:
    return [r2sp] if r2sp else [sys.executable, "-m", "tau_skill_evolution.cli"]


def build_command(
    r2sp: str | None,
    experiment: str,
    config: Path,
    run_dir: Path,
    task: str,
    arm: str,
    runtime: str = "docker",
) -> list[str]:
    return [
        *entrypoint(r2sp),
        "run",
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


def run_report_process(
    command: list[str], *, stop_requested: Callable[[], bool]
) -> subprocess.CompletedProcess[str]:
    """Run one report in its own process group and make launcher stops bounded."""

    with (
        tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as stdout,
        tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as stderr,
    ):
        process = subprocess.Popen(
            command,
            stdout=stdout,
            stderr=stderr,
            stdin=subprocess.DEVNULL,
            text=True,
            start_new_session=True,
        )
        terminate_deadline: float | None = None
        while True:
            try:
                returncode = process.wait(timeout=0.2)
                break
            except subprocess.TimeoutExpired:
                if not stop_requested():
                    continue
                if terminate_deadline is None:
                    with suppress(ProcessLookupError):
                        os.killpg(process.pid, signal.SIGTERM)
                    terminate_deadline = time.monotonic() + TERMINATE_GRACE_SECONDS
                elif time.monotonic() >= terminate_deadline:
                    with suppress(ProcessLookupError):
                        os.killpg(process.pid, signal.SIGKILL)
                    try:
                        returncode = process.wait(timeout=TERMINATE_GRACE_SECONDS)
                    except subprocess.TimeoutExpired as exc:
                        raise RuntimeError(
                            f"report process group did not terminate: {process.pid}"
                        ) from exc
                    break
        if stop_requested():
            # The leader may have exited after TERM while a descendant remains.
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
        stdout.seek(0)
        stderr.seek(0)
        return subprocess.CompletedProcess(
            command, returncode, stdout=stdout.read(), stderr=stderr.read()
        )


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


@contextmanager
def launcher_lock(run_dir: Path):
    """Hold the run-wide launcher lock without leaking it to child processes."""

    path = Path(run_dir) / ".launcher.lock"
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise LauncherLockError(f"cannot open launcher lock: {path}: {exc}") from exc
    try:
        os.fchmod(descriptor, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise LauncherLockError(f"another launcher is active for this run: {path}") from None
        yield
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _credential_failure_from_value(value: Any, source: str) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    code = value.get("code")
    error_code = value.get("error_code")
    status = value.get("status")
    if code == "authentication_failed" and status in (401, 403):
        return {"code": code, "status": status, "source": source}
    if code in CREDENTIAL_CODES:
        return {"code": code, "source": source}
    if error_code in CREDENTIAL_CODES:
        return {"code": error_code, "source": source}
    return None


def _json_values(text: str) -> list[Any]:
    """Recover JSON values from a bounded child log without assuming clean stdout."""

    values: list[Any] = []
    decoder = json.JSONDecoder()
    offset = 0
    while True:
        start = text.find("{", offset)
        if start < 0:
            break
        try:
            value, end = decoder.raw_decode(text, start)
        except json.JSONDecodeError:
            offset = start + 1
            continue
        values.append(value)
        offset = max(end, start + 1)
    return values


def _credential_code_from_detail(detail: str) -> str | None:
    lowered = detail.lower()
    if "credential_expired" in lowered or "expired or expires within 60" in lowered:
        return "credential_expired"
    unavailable = (
        "credential_unavailable",
        "bearer token file is missing or unreadable",
        "bearer token file is malformed",
        "bearer token file has an invalid expires_at",
    )
    return "credential_unavailable" if any(item in lowered for item in unavailable) else None


def _credential_failure_from_check(check: Any) -> dict[str, Any] | None:
    if not isinstance(check, dict) or check.get("ok") is not False:
        return None
    name = check.get("name")
    detail = str(check.get("detail", ""))
    lowered = detail.lower()
    if name == "credential":
        code = _credential_code_from_detail(detail) or "credential_unavailable"
        return {"code": code, "source": "child_preflight_log"}
    if name == "bedrock_authentication":
        for status in (401, 403):
            if f"http {status}" in lowered:
                return {
                    "code": "authentication_failed",
                    "status": status,
                    "source": "child_preflight_log",
                }
    if name in {"codex_login", "codex_catalog"}:
        return {"code": "credential_unavailable", "source": "child_preflight_log"}
    return None


def _bounded_log_text(descriptor: int, start_offset: int) -> str:
    length = os.fstat(descriptor).st_size
    start_offset = max(0, min(start_offset, length))
    available = length - start_offset
    if available <= MAX_CREDENTIAL_LOG_BYTES:
        raw = os.pread(descriptor, MAX_CREDENTIAL_LOG_BYTES, start_offset)
    else:
        half = MAX_CREDENTIAL_LOG_BYTES // 2
        head = os.pread(descriptor, half, start_offset)
        tail = os.pread(descriptor, half, max(start_offset, length - half))
        raw = head + b"\n" + tail
    return raw.decode("utf-8", errors="replace")


def credential_failure_from_text(
    text: str, *, allow_text_fallback: bool = True
) -> dict[str, Any] | None:
    for value in _json_values(text):
        if not isinstance(value, dict):
            continue
        if isinstance(value.get("error"), str):
            code = _credential_code_from_detail(value["error"])
            if code is not None:
                return {"code": code, "source": "child_cli_log"}
        checks = value.get("checks")
        if isinstance(checks, list):
            for check in checks:
                failure = _credential_failure_from_check(check)
                if failure is not None:
                    return failure
        else:
            failure = _credential_failure_from_check(value)
            if failure is not None:
                return failure
    # Some CLI failures occur before the complete preflight document is emitted.
    if not allow_text_fallback:
        return None
    lowered = text.lower()
    code = _credential_code_from_detail(lowered)
    if code is not None:
        return {"code": code, "source": "child_preflight_log"}
    for status in (401, 403):
        if f"bedrock catalog returned http {status}" in lowered:
            return {
                "code": "authentication_failed",
                "status": status,
                "source": "child_preflight_log",
            }
    return None


def journal_evidence_snapshot(run_dir: Path, task: str, arm: str) -> dict[str, str]:
    """Hash request/failure records so a retry can ignore retained evidence."""

    journal = Path(run_dir) / "cells" / task / arm / "journal"
    snapshot: dict[str, str] = {}
    for name in ("failure.json", "request.json"):
        for path in journal.glob(f"*/{name}"):
            try:
                snapshot[str(path.relative_to(journal))] = hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
            except OSError:
                continue
    return snapshot


def cell_credential_failure(
    run_dir: Path,
    task: str,
    arm: str,
    *,
    journal_baseline: dict[str, str] | None = None,
    log_text: str = "",
) -> dict[str, Any] | None:
    journal = Path(run_dir) / "cells" / task / arm / "journal"
    baseline = journal_baseline or {}
    current = journal_evidence_snapshot(run_dir, task, arm)
    changed = {relative for relative, digest in current.items() if baseline.get(relative) != digest}
    changed_failures = sorted(
        relative for relative in changed if relative.endswith("/failure.json")
    )
    for relative in changed_failures:
        path = journal / relative
        try:
            failure = _credential_failure_from_value(
                json.loads(path.read_text(encoding="utf-8")), "cell_journal"
            )
        except (OSError, json.JSONDecodeError):
            continue
        if failure is not None:
            return failure
    # Structured CLI/preflight JSON is safe to inspect for this attempt. Free
    # text is limited to attempts that created no request or failure evidence.
    changed_requests = any(relative.endswith("/request.json") for relative in changed)
    allow_text_fallback = not changed_failures and not changed_requests
    return (
        credential_failure_from_text(log_text, allow_text_fallback=allow_text_fallback)
        if log_text
        else None
    )


def _normalise_cell_record(value: Any) -> dict[str, Any]:
    record = dict(value) if isinstance(value, dict) else {}
    attempts = record.get("attempts")
    if not isinstance(attempts, list):
        attempts = []
    else:
        attempts = [dict(item) for item in attempts if isinstance(item, dict)]
    closed_at = now_iso()
    if not attempts and (
        record.get("started_at") is not None or record.get("finished_at") is not None
    ):
        attempts.append(
            {
                "attempt": 1,
                "invocation_id": "legacy",
                "account": record.get("account"),
                "pid": record.get("pid"),
                "started_at": record.get("started_at"),
                "finished_at": record.get("finished_at"),
                "exit_code": record.get("exit_code"),
                "outcome": "FINISHED" if record.get("finished_at") else "INTERRUPTED",
                "legacy": True,
            }
        )
    if (
        attempts
        and attempts[-1].get("started_at") is not None
        and attempts[-1].get("finished_at") is None
    ):
        attempts[-1].update(finished_at=closed_at, exit_code=None, outcome="INTERRUPTED")
        if record.get("started_at") is not None and record.get("finished_at") is None:
            record.update(finished_at=closed_at, exit_code=None)
    record["attempts"] = attempts
    for name in ("account", "pid", "started_at", "finished_at", "exit_code"):
        record.setdefault(name, None)
    return record


def load_launcher_status(path: Path, *, experiment: str, config: Path) -> dict[str, Any] | None:
    if not Path(path).exists():
        return None
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise ValueError("existing launcher-status.json is unreadable") from None
    if not isinstance(value, dict) or not isinstance(value.get("cells"), dict):
        raise ValueError("existing launcher-status.json is malformed")
    if value.get("experiment") not in (None, experiment):
        raise ValueError("existing launcher status belongs to another experiment")
    configured = value.get("config")
    if configured is not None and Path(configured).resolve() != Path(config).resolve():
        raise ValueError("existing launcher status uses another configuration")
    return value


# ----------------------------------------------------------------------------
# launcher
# ----------------------------------------------------------------------------


class Launcher:
    def __init__(self, args: argparse.Namespace, cells: list[tuple[str, str]]) -> None:
        self.args = args
        self.cells = cells
        self.selected_keys = [cell_key(task, arm) for task, arm in cells]
        self.accounts = assign_accounts(cells, args.accounts)
        self.status_path = Path(self.args.run_dir) / "launcher-status.json"
        previous = load_launcher_status(
            self.status_path, experiment=args.experiment, config=args.config
        )
        self.status_base = dict(previous or {})
        self.started_at = self.status_base.get("started_at") or now_iso()
        previous_cells = self.status_base.get("cells", {})
        self.status_cells: dict[str, dict[str, Any]] = {
            key: _normalise_cell_record(value) for key, value in previous_cells.items()
        }
        for key in self.selected_keys:
            self.status_cells.setdefault(key, _normalise_cell_record({}))
        previous_launches = self.status_base.get("launches", [])
        self.launches = (
            [dict(item) for item in previous_launches if isinstance(item, dict)]
            if isinstance(previous_launches, list)
            else []
        )
        for launch in self.launches:
            if (
                launch.get("status") in {"RUNNING", "REPORTING"}
                and launch.get("finished_at") is None
            ):
                launch.update(status="INTERRUPTED", exit_code=None, finished_at=now_iso())
        if previous is not None and not self.launches:
            historical_stop = previous.get("credential_failure")
            if historical_stop is None and previous.get("authentication_status") in (401, 403):
                historical_stop = {
                    "code": "authentication_failed",
                    "status": previous["authentication_status"],
                    "source": "legacy_launcher_status",
                }
            self.launches.append(
                {
                    "invocation_id": "legacy",
                    "started_at": previous.get("started_at"),
                    "finished_at": previous.get("updated_at"),
                    "status": "STOPPED" if historical_stop is not None else "UNKNOWN",
                    "exit_code": 2 if historical_stop is not None else None,
                    "selected_cells": list(previous_cells),
                    "accounts": sorted(
                        {
                            str(item.get("account"))
                            for item in previous_cells.values()
                            if isinstance(item, dict) and item.get("account") is not None
                        }
                    ),
                    "global_stop": historical_stop,
                    "legacy": True,
                }
            )
        self.invocation_id = f"launch-{uuid.uuid4().hex}"
        self.launches.append(
            {
                "invocation_id": self.invocation_id,
                "started_at": now_iso(),
                "finished_at": None,
                "status": "RUNNING",
                "exit_code": None,
                "selected_cells": list(self.selected_keys),
                "accounts": list(args.accounts),
                "global_stop": None,
            }
        )
        self.processes: dict[str, tuple[subprocess.Popen[bytes], Any, dict[str, Any]]] = {}
        self.stop = False
        self.authentication_status: int | None = None
        self.credential_failure: dict[str, Any] | None = None
        self.runtime = getattr(args, "runtime", "docker")

    def _launch_record(self) -> dict[str, Any]:
        return self.launches[-1]

    def _finish_launch(self, status: str, exit_code: int) -> None:
        launch = self._launch_record()
        launch.update(status=status, exit_code=exit_code, finished_at=now_iso())
        if self.credential_failure is not None:
            launch["global_stop"] = dict(self.credential_failure)
        self.write_status()

    def write_status(self) -> None:
        status = build_status(
            started_at=self.started_at,
            experiment=self.args.experiment,
            config=self.args.config,
            cells=self.status_cells,
        )
        payload = dict(self.status_base)
        payload.update(status)
        status = payload
        status["authentication_status"] = self.authentication_status
        status["credential_failure"] = self.credential_failure
        status["runtime"] = self.runtime
        status["launches"] = self.launches
        status["active_invocation_id"] = (
            self.invocation_id if self._launch_record().get("finished_at") is None else None
        )
        write_atomic_json(self.status_path, status)

    def _new_attempt(self, key: str, account: str) -> dict[str, Any]:
        record = self.status_cells[key]
        attempt = {
            "attempt": len(record["attempts"]) + 1,
            "invocation_id": self.invocation_id,
            "account": account,
            "pid": None,
            "started_at": now_iso(),
            "finished_at": None,
            "exit_code": None,
            "outcome": "STARTING",
        }
        record["attempts"].append(attempt)
        record.update(
            account=account,
            pid=None,
            started_at=attempt["started_at"],
            finished_at=None,
            exit_code=None,
        )
        return attempt

    def _record_credential_stop(
        self, *, account: str, source: str, code: str, status: int | None = None
    ) -> None:
        if self.credential_failure is not None:
            self.stop = True
            return
        failure: dict[str, Any] = {"account": account, "code": code, "source": source}
        if status in (401, 403):
            failure["status"] = status
            self.authentication_status = status
        self.credential_failure = failure
        self._launch_record()["global_stop"] = dict(failure)
        self.stop = True

    def start(self, task: str, arm: str) -> None:
        key = cell_key(task, arm)
        account = self.accounts[key]
        try:
            validate_token_file(token_path(self.args.token_dir, account))
        except TokenValidationError as exc:
            attempt = self._new_attempt(key, account)
            attempt.update(
                finished_at=now_iso(), exit_code=2, outcome="CREDENTIAL_REJECTED", code=exc.code
            )
            self.status_cells[key].update(finished_at=attempt["finished_at"], exit_code=2)
            self._record_credential_stop(
                account=account, source="local_token_admission", code=exc.code
            )
            self.write_status()
            raise
        command = build_command(
            self.args.r2sp,
            self.args.experiment,
            self.args.config,
            self.args.run_dir,
            task,
            arm,
            runtime=self.runtime,
        )
        env = build_env(dict(os.environ), token_path(self.args.token_dir, account))
        log_file = log_path(self.args.run_dir, task, arm)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        stream = log_file.open("a+b")
        metadata = os.fstat(stream.fileno())
        evidence = {
            "log_start_offset": metadata.st_size,
            "journal_baseline": journal_evidence_snapshot(self.args.run_dir, task, arm),
        }
        attempt = self._new_attempt(key, account)
        attempt["log_start_offset"] = evidence["log_start_offset"]
        try:
            process = subprocess.Popen(
                command,
                stdout=stream,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                env=env,
                start_new_session=True,
            )
        except BaseException:
            stream.close()
            attempt.update(finished_at=now_iso(), outcome="LAUNCH_ERROR")
            self.status_cells[key].update(finished_at=attempt["finished_at"])
            self.write_status()
            raise
        self.processes[key] = (process, stream, evidence)
        attempt.update(pid=process.pid, outcome="RUNNING")
        self.status_cells[key].update(pid=process.pid)
        self.write_status()
        print(f"started {key} account={account} pid={process.pid}", flush=True)

    def reap(self) -> None:
        for key, (process, stream, evidence) in list(self.processes.items()):
            code = process.poll()
            if code is None:
                continue
            try:
                stream.flush()
                log_end_offset = os.fstat(stream.fileno()).st_size
                attempt_log_text = _bounded_log_text(
                    stream.fileno(), int(evidence.get("log_start_offset", 0))
                )
            except (AttributeError, OSError):
                log_end_offset = None
                attempt_log_text = None
            stream.close()
            del self.processes[key]
            self.status_cells[key].update(finished_at=now_iso(), exit_code=code)
            attempts = self.status_cells[key]["attempts"]
            if not attempts or attempts[-1].get("invocation_id") != self.invocation_id:
                raise RuntimeError(f"active process has no bound attempt: {key}")
            attempts[-1].update(
                finished_at=self.status_cells[key]["finished_at"],
                exit_code=code,
                outcome="FINISHED",
                log_end_offset=log_end_offset,
            )
            task, arm = key.split("|", 1)
            failure = (
                cell_credential_failure(
                    self.args.run_dir,
                    task,
                    arm,
                    journal_baseline=evidence.get("journal_baseline"),
                    log_text=attempt_log_text or "",
                )
                if code
                else None
            )
            if failure is not None:
                self._record_credential_stop(
                    account=str(self.status_cells[key].get("account")),
                    source=str(failure["source"]),
                    code=str(failure["code"]),
                    status=failure.get("status"),
                )
            self.write_status()
            print(f"finished {key} exit={code}", flush=True)

    def terminate_children(self) -> None:
        for process, _stream, _evidence in self.processes.values():
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGTERM)
        deadline = time.monotonic() + TERMINATE_GRACE_SECONDS
        for process, _stream, _evidence in self.processes.values():
            if process.poll() is not None:
                continue
            try:
                process.wait(timeout=max(0.0, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                continue
        for process, _stream, _evidence in self.processes.values():
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
        for process, _stream, _evidence in self.processes.values():
            if process.poll() is None:
                try:
                    process.wait(timeout=TERMINATE_GRACE_SECONDS)
                except subprocess.TimeoutExpired as exc:
                    raise RuntimeError(
                        f"child process group did not terminate: {process.pid}"
                    ) from exc
        self.reap()
        if self.processes:
            raise RuntimeError("launcher could not reap every child process")

    def run(self) -> int:
        pending = list(self.cells)
        self.write_status()
        try:
            while (pending or self.processes) and not self.stop:
                self.reap()
                if self.stop:
                    break
                if pending and len(self.processes) < self.args.max_concurrent:
                    task, arm = pending.pop(0)
                    try:
                        self.start(task, arm)
                    except TokenValidationError:
                        break
                    time.sleep(max(0.0, self.args.stagger_seconds))
                    continue
                time.sleep(1.0)
        except BaseException:
            # A failed Popen or an unexpected error must not orphan running cells.
            self.terminate_children()
            self._finish_launch("FAILED", 2)
            raise
        if self.stop:
            self.terminate_children()
            code = 2 if self.credential_failure is not None else 130
            self._finish_launch("STOPPED", code)
            return code
        self.reap()
        failed = any(self.status_cells[key].get("exit_code") != 0 for key in self.selected_keys)
        code = 1 if failed else 0
        self._launch_record().update(status="REPORTING", cell_exit_code=code)
        self.write_status()
        return code


def _dry_run(args: argparse.Namespace, cells: list[tuple[str, str]]) -> None:
    accounts = assign_accounts(cells, args.accounts)
    for task, arm in cells:
        account = accounts[cell_key(task, arm)]
        command = build_command(
            args.r2sp, args.experiment, args.config, args.run_dir, task, arm, runtime=args.runtime
        )
        print(
            f"{TOKEN_FILE_ENV}={token_path(args.token_dir, account)} "
            + " ".join(command)
            + f"  # log={log_path(args.run_dir, task, arm)}"
        )
    print(f"planned {len(cells)} cells over {len(args.accounts)} accounts", flush=True)


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
    parser.add_argument("--skip-final-report", action="store_true")
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="recover an unfinished launcher reporting phase without rerunning cells",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    args.config = args.config.resolve()
    args.run_dir = args.run_dir.resolve()
    args.token_dir = args.token_dir.resolve()
    if args.max_concurrent is None:
        args.max_concurrent = 1 if args.runtime == "workspace" else 96
    if args.max_concurrent <= 0:
        parser.error("--max-concurrent must be positive")
    if args.r2sp is not None and not executable(args.r2sp):
        parser.error(f"--r2sp is not an executable file: {args.r2sp}")
    args.accounts = (
        [item.strip() for item in args.accounts.split(",") if item.strip()]
        if args.accounts
        else discover_accounts(args.token_dir)
    )
    if not args.accounts and not args.report_only:
        parser.error("no accounts: pass --accounts or populate --token-dir with <ID>.json files")
    if args.report_only and (
        args.task
        or args.arm
        or args.cells_file is not None
        or args.dry_run
        or args.skip_final_report
    ):
        parser.error(
            "--report-only cannot accompany cell filters, --dry-run or --skip-final-report"
        )
    from tau_skill_evolution.journal import _create_identity_exclusive
    from tau_skill_evolution.spec import load_spec

    spec = load_spec(args.config)
    if spec.experiment != args.experiment:
        parser.error("--experiment differs from the selected configuration")
    if args.task and set(args.task) - set(spec.tasks):
        parser.error("--task must belong to the frozen experiment task population")
    if args.arm and set(args.arm) - set(spec.arms):
        parser.error("--arm is not supported by this experiment")
    cells = [] if args.report_only else filter_cells(spec.cells, args.task, args.arm)
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
    if not cells and not args.report_only:
        parser.error("no cells selected")

    if args.dry_run:
        _dry_run(args, cells)
        return 0

    # Reject an unusable account set before creating the run identity or
    # launching the initial report subprocess. Each file is checked again at
    # cell admission because the daemon can replace or expire it mid-run.
    if not args.report_only:
        try:
            validate_accounts(args.token_dir, args.accounts)
        except TokenValidationError as exc:
            parser.error(str(exc))

    # The dedicated launcher lock is distinct from the CLI run lock used by
    # child cells. It serialises status admission through final reporting.
    args.run_dir.mkdir(parents=True, exist_ok=True)
    (args.run_dir / "locks").mkdir(exist_ok=True)
    (args.run_dir / "logs").mkdir(exist_ok=True)
    try:
        lock = launcher_lock(args.run_dir)
        lock.__enter__()
    except LauncherLockError as exc:
        parser.error(str(exc))
    previous_signals: tuple[Any, Any] | None = None
    try:
        launcher_identity = {"identity": spec.identity, "runtime": args.runtime}
        identity_path = args.run_dir / "launcher-identity.json"
        _create_identity_exclusive(identity_path, launcher_identity)
        if json.loads(identity_path.read_text()) != launcher_identity:
            parser.error("launcher configuration or runtime differs from the existing run")
        if args.report_only:
            previous = load_launcher_status(
                args.run_dir / "launcher-status.json",
                experiment=args.experiment,
                config=args.config,
            )
            launches = previous.get("launches", []) if previous is not None else []
            latest = launches[-1] if isinstance(launches, list) and launches else {}
            if (
                latest.get("status") not in {"RUNNING", "REPORTING"}
                or latest.get("finished_at") is not None
            ):
                parser.error("--report-only requires an unfinished RUNNING/REPORTING launch")
        try:
            launcher = Launcher(args, cells)
        except ValueError as exc:
            parser.error(str(exc))
        launcher.write_status()

        def _stop(signum: int, _frame: Any) -> None:
            launcher.stop = True
            print(f"received signal {signum}; terminating children", flush=True)

        previous_signals = (signal.getsignal(signal.SIGINT), signal.getsignal(signal.SIGTERM))
        signal.signal(signal.SIGINT, _stop)
        signal.signal(signal.SIGTERM, _stop)
        report = report_command(
            args.r2sp, args.experiment, args.config, args.run_dir, runtime=args.runtime
        )
        try:
            initial = run_report_process(report, stop_requested=lambda: launcher.stop)
        except (OSError, RuntimeError) as exc:
            sys.stderr.write(f"initial r2sp report could not run: {exc}\n")
            launcher._finish_launch("FAILED", 2)
            return 2
        if launcher.stop:
            launcher._finish_launch("STOPPED", 130)
            return 130
        if initial.returncode != 0:
            sys.stderr.write(initial.stdout[-2000:] + initial.stderr[-2000:])
            sys.stderr.write("\ninitial r2sp report failed; aborting\n")
            launcher._finish_launch("FAILED", 2)
            return 2
        if args.report_only:
            launcher._finish_launch("COMPLETED", 0)
            print(f"report-only reconciliation complete: {args.run_dir / 'report.json'}")
            return 0
        code = launcher.run()
        if code not in (0, 1):
            return code

        status = {key: launcher.status_cells[key] for key in launcher.selected_keys}
        total = len(status)
        ok = sum(1 for item in status.values() if item["exit_code"] == 0)
        if not args.skip_final_report:
            try:
                final = run_report_process(report, stop_requested=lambda: launcher.stop)
            except (OSError, RuntimeError) as exc:
                sys.stderr.write(f"final r2sp report could not run: {exc}\n")
                launcher._finish_launch("FAILED", 2)
                return 2
            if launcher.stop:
                launcher._finish_launch("STOPPED", 130)
                return 130
            if final.returncode != 0:
                sys.stderr.write(final.stdout[-2000:] + final.stderr[-2000:])
                sys.stderr.write("\nfinal r2sp report failed\n")
                launcher._finish_launch("FAILED", 2)
                return 2
        if launcher.stop:
            launcher._finish_launch("STOPPED", 130)
            return 130
        launcher._finish_launch("FAILED" if code else "COMPLETED", code)
        print(
            f"cells total={total} exit0={ok} nonzero={total - ok} "
            f"report={args.run_dir / 'report.json'}",
            flush=True,
        )
        return code
    finally:
        if previous_signals is not None:
            signal.signal(signal.SIGINT, previous_signals[0])
            signal.signal(signal.SIGTERM, previous_signals[1])
        lock.__exit__(None, None, None)


if __name__ == "__main__":
    raise SystemExit(main())
