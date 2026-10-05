"""Public subprocess boundary around the pinned official bank runtime."""

from __future__ import annotations

import json
import os
import selectors
import subprocess
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .artifacts import PROTOCOL, SkillBundle

READ_ONLY_TOOLS = frozenset(
    {
        "get_current_time",
        "get_user_information_by_id",
        "get_user_information_by_name",
        "get_user_information_by_email",
        "get_referrals_by_user",
        "get_credit_card_transactions_by_user",
        "get_credit_card_accounts_by_user",
    }
)


class BankWorkerError(RuntimeError):
    """The official worker failed without exposing private runtime state."""


class _Channel:
    def __init__(self, bank: Bank) -> None:
        env = os.environ.copy()
        env["R2SP_TAU_UPSTREAM_ROOT"] = str(bank.upstream_root)
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
        # Worker stderr (official runtime logs, retry events, tracebacks) is private
        # run-local diagnostics; it never enters the journal or any role input.
        self.stderr_log = None
        log_dir = bank.config.get("worker_log_dir")
        stderr: Any = subprocess.DEVNULL
        if isinstance(log_dir, str) and log_dir:
            directory = Path(log_dir)
            directory.mkdir(parents=True, exist_ok=True)
            self.stderr_log = (directory / f"worker-{bank.task_id}-{os.getpid()}.log").open("ab")
            stderr = self.stderr_log
        self.process = subprocess.Popen(
            [str(bank.python), "-m", "tau_skill_evolution.worker"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=stderr,
            env=env,
            cwd=bank.upstream_root,
        )
        self.timeout = float(bank.config.get("episode_timeout_seconds", 3600))
        self.buffer = bytearray()

    def request(self, value: Mapping[str, Any]) -> Any:
        process = self.process
        if process.poll() is not None or process.stdin is None or process.stdout is None:
            raise BankWorkerError("bank_worker_exited")
        request = json.dumps({"protocol": PROTOCOL, **value}, ensure_ascii=False, allow_nan=False)
        try:
            process.stdin.write((request + "\n").encode())
            process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise BankWorkerError("bank_worker_transport_failed") from exc
        deadline = time.monotonic() + self.timeout
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while b"\n" not in self.buffer:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not selector.select(remaining):
                    raise BankWorkerError("bank_worker_timeout")
                data = os.read(process.stdout.fileno(), 65536)
                if not data:
                    raise BankWorkerError("bank_worker_exited")
                self.buffer.extend(data)
                if len(self.buffer) > 16 * 1024 * 1024:
                    raise BankWorkerError("bank_worker_output_limit")
        line, _, rest = self.buffer.partition(b"\n")
        self.buffer = bytearray(rest)
        try:
            response = json.loads(line)
        except (UnicodeError, ValueError) as exc:
            raise BankWorkerError("bank_worker_invalid_json") from exc
        if not isinstance(response, dict) or response.get("protocol") != PROTOCOL:
            raise BankWorkerError("bank_worker_incompatible_response")
        if response.get("ok") is not True:
            if response.get("error_status") in (401, 403):
                from .model import ModelClientError

                raise ModelClientError(
                    "authentication_failed",
                    "bank model authentication failed",
                    status=response["error_status"],
                )
            kind = response.get("error_kind")
            suffix = f":{kind}" if isinstance(kind, str) and kind else ""
            raise BankWorkerError(f"bank_worker_operation_failed{suffix}")
        return response["result"]

    def close(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        for pipe in (self.process.stdin, self.process.stdout):
            if pipe is not None:
                pipe.close()
        if self.stderr_log is not None:
            self.stderr_log.close()


class Acquisition:
    """A fresh simulator conversation with a hard bank-read allowlist."""

    def __init__(self, bank: Bank) -> None:
        self.bank = bank
        self.channel: _Channel | None = None
        self.public_inputs: dict[str, Any] = {}
        self.tool_schemas: list[dict[str, Any]] = []

    def __enter__(self) -> Acquisition:
        self.channel = _Channel(self.bank)
        try:
            result = self.channel.request(self.bank._request("acquire"))
            self.public_inputs = result["public_inputs"]
            self.tool_schemas = result["tool_schemas"]
        except BaseException:
            self.channel.close()
            self.channel = None
            raise
        return self

    def _request(self, value: dict[str, Any]) -> Any:
        if self.channel is None:
            raise BankWorkerError("acquisition_closed")
        return self.channel.request(value)

    def clarify(self, question: str) -> str:
        if not isinstance(question, str) or not question.strip():
            raise ValueError("clarification question must be nonempty text")
        return self._request({"operation": "clarify", "question": question})

    def read(self, name: str, arguments: Mapping[str, Any]) -> Any:
        if name not in READ_ONLY_TOOLS:
            raise PermissionError("acquisition permits only the seven bank reads")
        if not isinstance(arguments, Mapping):
            raise ValueError("tool arguments must be an object")
        return self._request({"operation": "read", "name": name, "arguments": dict(arguments)})

    def __exit__(self, exc_type: object, *_exc: object) -> None:
        if self.channel is not None:
            try:
                if exc_type is None:
                    self.channel.request({"operation": "close"})
            finally:
                self.channel.close()
                self.channel = None


class Bank:
    def __init__(
        self,
        python: Path,
        upstream_root: Path,
        task_id: str,
        config: Mapping[str, Any],
    ) -> None:
        self.python = Path(python)
        self.upstream_root = Path(upstream_root).resolve()
        self.task_id = task_id
        self.config = dict(config)
        self._schemas: list[dict[str, Any]] | None = None

    def _request(self, operation: str, bundle: SkillBundle | None = None) -> dict[str, Any]:
        result: dict[str, Any] = {
            "operation": operation,
            "task_id": self.task_id,
            "config": self.config,
        }
        if bundle is not None:
            result["bundle"] = bundle.to_dict()
        return result

    def _call(self, operation: str, bundle: SkillBundle | None = None) -> Any:
        channel = _Channel(self)
        try:
            return channel.request(self._request(operation, bundle))
        finally:
            channel.close()

    @property
    def tool_schemas(self) -> list[dict[str, Any]]:
        if self._schemas is None:
            self._schemas = self._call("schemas")
        return list(self._schemas)

    def acquisition(self) -> Acquisition:
        return Acquisition(self)

    def rollout(self, bundle: SkillBundle) -> dict[str, Any]:
        return self._call("rollout", bundle)

    def oracle(self, bundle: SkillBundle) -> bool:
        result = self._call("oracle", bundle)
        if type(result) is not bool:
            raise BankWorkerError("oracle_response_must_be_boolean")
        return result

    def evaluate(self, bundle: SkillBundle) -> dict[str, Any]:
        return self._call("evaluate", bundle)
