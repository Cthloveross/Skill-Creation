"""Public subprocess boundary around the pinned official bank runtime."""

from __future__ import annotations

import json
import os
import selectors
import shutil
import subprocess
import time
from collections.abc import Mapping
from contextlib import ExitStack
from pathlib import Path
from typing import Any

from .artifacts import PROTOCOL, EvolutionSubmission, SkillBundle, atomic_json
from .core._canonical import canonical_json_sha256

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

    def __init__(self, message: str, *, response_received: bool = False) -> None:
        super().__init__(message)
        self.response_received = response_received


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
            if kind in {
                "ModelClientError:acquisition_received_invalid",
                "ModelClientError:acquisition_recovery_failed",
            }:
                from .model import ModelClientError

                raise ModelClientError(kind.split(":", 1)[1], "bank acquisition cannot continue")
            if kind == "UnknownOperation":
                from .journal import UnknownOperation

                raise UnknownOperation("bank acquisition request has an unknown result")
            if isinstance(kind, str) and kind in {
                "CredentialError:credential_unavailable",
                "CredentialError:credential_expired",
            }:
                from .model import CredentialError

                raise CredentialError(
                    kind.split(":", 1)[1],
                    "bank credential resolution failed before its model request",
                )
            suffix = f":{kind}" if isinstance(kind, str) and kind else ""
            raise BankWorkerError(f"bank_worker_operation_failed{suffix}", response_received=True)
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
    """An allowlisted simulator conversation with optional host-private recovery."""

    def __init__(
        self,
        bank: Bank,
        *,
        checkpoint: Path | None = None,
        identity: Mapping[str, Any] | None = None,
    ) -> None:
        self.bank = bank
        self.checkpoint, self.identity = checkpoint, dict(identity or {})
        self.channel: _Channel | None = None
        self.public_inputs: dict[str, Any] = {}
        self.tool_schemas: list[dict[str, Any]] = []

    def __enter__(self) -> Acquisition:
        self.channel = _Channel(self.bank)
        try:
            request = self.bank._request("acquire")
            if self.checkpoint is not None:
                request["checkpoint"] = str(self.checkpoint.resolve())
                request["identity"] = self.identity
            result = self.channel.request(request)
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

    def perform(self, operation_id: str, action: Mapping[str, Any]) -> Any:
        """Use the controller's stable action ID for private simulator recovery."""
        if not isinstance(operation_id, str) or not operation_id:
            raise ValueError("acquisition operation ID must be nonempty")
        kind = action.get("kind")
        if kind == "clarify" and set(action) == {"kind", "question"}:
            question = action["question"]
            if not isinstance(question, str) or not question.strip():
                raise ValueError("clarification question must be nonempty text")
            request = {"operation": "clarify", "question": question}
        elif kind == "read_only" and set(action) == {"kind", "tool", "arguments"}:
            if action["tool"] not in READ_ONLY_TOOLS:
                raise PermissionError("acquisition permits only the seven bank reads")
            if not isinstance(action["arguments"], Mapping):
                raise ValueError("tool arguments must be an object")
            request = {
                "operation": "read",
                "name": action["tool"],
                "arguments": action["arguments"],
            }
        else:
            raise PermissionError("unsupported acquisition action")
        return self._request({**request, "operation_id": operation_id})

    def __exit__(self, exc_type: object, *_exc: object) -> None:
        if self.channel is not None:
            try:
                if exc_type is None:
                    self.channel.request({"operation": "close"})
            finally:
                self.channel.close()
                self.channel = None


def _authoring_runner(config: Mapping[str, Any]) -> Any:
    settings = config.get("sandbox")
    if settings is not None:
        from .bubblewrap import BubblewrapRunner, RuntimeLock

        if settings.get("backend") not in {"workspace", "bubblewrap-demo"}:
            raise ValueError("unsupported bank authoring sandbox")
        return BubblewrapRunner(
            RuntimeLock.from_file(Path(settings["runtime_lock"])),
            runtime=settings["backend"],
        )
    from .container import DockerRunner, ImageLock

    lock = config["docker"]
    return DockerRunner(
        ImageLock(
            image=lock["image"],
            digest=lock.get("digest"),
            dependency_hash=lock.get("dependency_hash"),
            dependency_lock=Path(lock["dependency_lock"]) if lock.get("dependency_lock") else None,
            digest_kind=lock.get("digest_kind", "repo_digest"),
        )
    )


class BankEvolutionSession:
    """One Generator workspace and an explicitly restarted private bank episode."""

    def __init__(
        self,
        bank: Bank,
        initial_bundle: SkillBundle,
        public_inputs: Mapping[str, Any],
        frozen_base: Any,
        *,
        journal: Any,
        workspace: Path,
    ) -> None:
        self.bank, self.initial_bundle = bank, initial_bundle
        self.public_inputs, self.frozen_base = public_inputs, frozen_base
        self.journal, self.workspace = journal, Path(workspace)
        self.channel: _Channel | None = None
        self._stack = ExitStack()
        self.tool_schemas: list[dict[str, Any]] = []
        self.checkpoint_state: dict[str, Any] = {}
        self.cleanup_failed = False

    def __enter__(self) -> BankEvolutionSession:
        base = (
            self.frozen_base.to_dict() if hasattr(self.frozen_base, "to_dict") else self.frozen_base
        )
        try:
            self.authoring = self._stack.enter_context(
                _authoring_runner(self.bank.config).authoring_session(
                    self.initial_bundle,
                    self.public_inputs,
                    self.frozen_base,
                    workspace=self.workspace,
                )
            )
            self.channel = _Channel(self.bank)
            self._stack.callback(self.channel.close)
            request = self.bank._request("learning")
            request.update(
                checkpoint=str((self.journal.root / "bank-private" / "state.json").resolve()),
                identity={
                    "initial_bundle_hash": self.initial_bundle.bundle_hash,
                    "fixed_inputs_hash": canonical_json_sha256(
                        {"public_inputs": self.public_inputs, "base": base}
                    ),
                    "config_hash": canonical_json_sha256(self.bank.config),
                },
            )
            result = self.channel.request(request)
            self.tool_schemas = result["tool_schemas"]
            self.checkpoint_state = result["state"]
            return self
        except BaseException:
            self._stack.close()
            self.channel = None
            raise

    def _request(self, value: Mapping[str, Any]) -> dict[str, Any]:
        if self.channel is None:
            raise BankWorkerError("learning_session_closed")
        result = self.channel.request(value)
        self.checkpoint_state = result["state"]
        return result

    def files(self) -> dict[str, str]:
        return self.authoring.files()

    def snapshot(self) -> dict[str, Any]:
        snapshot = self.authoring.snapshot()
        # Observations are staged after the outer journal seals tool responses;
        # scratch is deliberately persistent. Neither changes candidate identity.
        manifest = {"public": snapshot["manifest"]["public"], "candidate": snapshot["files"]}
        return {
            "files": snapshot["files"],
            "workspace_hash": canonical_json_sha256(manifest),
            "manifest": manifest,
        }

    def terminal(self, command: str) -> Any:
        result = self.authoring.terminal(command)
        self.cleanup_failed |= self.authoring.cleanup_failed
        return result

    def begin_attempt(
        self, parent: SkillBundle, initial: bool, *, operation_id: str | None = None
    ) -> dict[str, Any]:
        if initial and parent.bundle_hash != self.initial_bundle.bundle_hash:
            raise ValueError("initial learning attempt must use S0")
        operation_id = operation_id or (
            "initial-learning-execution" if initial else f"revision-{parent.bundle_hash}"
        )
        path = self.journal.root / "bank-private" / "authoring-attempt.json"
        attempt = {
            "operation_id": operation_id,
            "parent_hash": parent.bundle_hash,
            "initial": initial,
        }
        previous = json.loads(path.read_text()) if path.exists() else None
        if (
            previous is not None
            and previous["operation_id"] == operation_id
            and any(previous[key] != value for key, value in attempt.items())
        ):
            raise ValueError("bank learning attempt identity changed")
        if (
            previous is None
            or previous["operation_id"] != operation_id
            or (previous["status"] == "PREPARING")
        ):
            atomic_json(path, {**attempt, "status": "PREPARING"})
            # These are disposable host-staged files, never the bank DB. Do not
            # follow candidate links left by a rejected draft during rollback.
            target = self.authoring.target
            if target.is_symlink() or not target.is_dir():
                raise ValueError("unsafe_bank_candidate_root")
            for child in target.iterdir():
                if child.is_dir() and not child.is_symlink():
                    shutil.rmtree(child)
                else:
                    child.unlink()
            for relative, content in parent.files.items():
                destination = target / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(content, encoding="utf-8")
                destination.chmod(0o666)
                for directory in destination.parents:
                    if directory == self.authoring.work:
                        break
                    directory.chmod(0o777)
            atomic_json(path, {**attempt, "status": "READY"})
        if initial:
            return self.execute_tool("start_learning_execution", {}, operation_id)
        return {"state": dict(self.checkpoint_state)}

    def execute_tool(
        self, name: str, arguments: Mapping[str, Any], operation_id: str
    ) -> dict[str, Any]:
        if (
            not isinstance(operation_id, str)
            or not operation_id
            or not isinstance(arguments, Mapping)
        ):
            raise ValueError("learning tool requires a stable ID and JSON arguments")
        return self._request(
            {
                "operation": "learning_action",
                "name": name,
                "arguments": dict(arguments),
                "operation_id": operation_id,
            }
        )

    def record_tool_result(self, operation_id: str, result: Any) -> str:
        payload = {"operation_id": operation_id, "result": result}
        digest = canonical_json_sha256(payload)
        directory = self.authoring.work / "observations" / "tools"
        for path in (directory.parent, directory):
            if path.is_symlink():
                raise ValueError("unsafe_bank_observation_path")
            path.mkdir(exist_ok=True)
            path.chmod(0o755)
        destination = directory / f"{digest}.json"
        if destination.is_symlink():
            raise ValueError("unsafe_bank_observation_path")
        if destination.exists():
            if json.loads(destination.read_text()) != payload:
                raise ValueError("bank_observation_changed")
        else:
            atomic_json(destination, payload)
            destination.chmod(0o444)
        return f"/work/observations/tools/{digest}.json"

    def submit(
        self, parent_bundle: SkillBundle, *, initial: bool = False, operation_id: str
    ) -> EvolutionSubmission:
        bundle = SkillBundle(self.files(), parent_hash=parent_bundle.bundle_hash)
        if initial:
            if bundle.bundle_hash != self.initial_bundle.bundle_hash:
                raise ValueError("initial learning execution changed S0")
            bundle = self.initial_bundle
        elif bundle.bundle_hash == parent_bundle.bundle_hash:
            bundle = parent_bundle
        result = self._request(
            {
                "operation": "learning_snapshot",
                "operation_id": operation_id,
                "bundle_hash": bundle.bundle_hash,
            }
        )
        return EvolutionSubmission(
            bundle,
            result["public_trace"],
            result["state"]["execution_id"],
            result["state"]["operation_cursor"],
            initial,
        )

    def __exit__(self, exc_type: object, *_exc: object) -> None:
        try:
            if exc_type is None and self.channel is not None:
                self.channel.request({"operation": "close"})
        finally:
            self._stack.close()
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

    def acquisition(
        self, *, checkpoint: Path | None = None, identity: Mapping[str, Any] | None = None
    ) -> Acquisition:
        return Acquisition(self, checkpoint=checkpoint, identity=identity)

    def evolution_session(
        self,
        initial_bundle: SkillBundle,
        public_inputs: Mapping[str, Any],
        frozen_base: Any,
        *,
        journal: Any,
        workspace: Path,
    ) -> BankEvolutionSession:
        return BankEvolutionSession(
            self, initial_bundle, public_inputs, frozen_base, journal=journal, workspace=workspace
        )

    def rollout(self, bundle: SkillBundle) -> dict[str, Any]:
        return self._call("rollout", bundle)

    def oracle(self, bundle: SkillBundle) -> bool:
        result = self._call("oracle", bundle)
        if type(result) is not bool:
            raise BankWorkerError("oracle_response_must_be_boolean")
        return result

    def evaluate(self, bundle: SkillBundle) -> dict[str, Any]:
        return self._call("evaluate", bundle)
