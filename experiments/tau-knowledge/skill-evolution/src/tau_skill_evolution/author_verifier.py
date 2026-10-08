"""Source registration and host transports for the unchanged author components."""

from __future__ import annotations

import hashlib
import importlib
import json
import sys
import threading
import types
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .container import ContainerUnavailable
from .journal import UnknownOperation
from .model import InputTokenBudgetExceeded, authentication_status, is_credential_error

_ROOT = Path(__file__).with_name("author")
_RUN: ContextVar[_Run | None] = ContextVar("author_verifier_run", default=None)
_IMPORT_LOCK = threading.Lock()
_REGISTERED = False


def author_source() -> dict[str, Any]:
    source = json.loads((_ROOT / "VERIFIER_SOURCE.json").read_text())
    for relative, entry in source["files"].items():
        path = _ROOT / relative
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
            raise ContainerUnavailable("author_verifier_source_hash_mismatch")
    return source


def author_module(name: str) -> Any:
    """Register only namespaces, avoiding upstream's eager controller imports."""
    global _REGISTERED
    with _IMPORT_LOCK:
        if not _REGISTERED:
            author_source()
            packages = [
                "libs" + suffix
                for suffix in (
                    "",
                    ".terminus_agent",
                    ".terminus_agent.agents",
                    ".terminus_agent.agents.terminus_2",
                    ".terminus_agent.evolution",
                    ".terminus_agent.llms",
                    ".terminus_agent.utils",
                )
            ] + ["scripts"]
            for fullname in packages:
                path = _ROOT / "coevo" / Path(fullname.replace(".", "/"))
                previous = sys.modules.get(fullname)
                if previous is not None and list(getattr(previous, "__path__", ())) != [str(path)]:
                    raise ContainerUnavailable("author_verifier_namespace_conflict")
                module = previous or types.ModuleType(fullname)
                module.__path__ = [str(path)]
                sys.modules[fullname] = module
            agent = importlib.import_module(
                "libs.terminus_agent.agents.terminus_2.harbor_terminus_2_skills"
            )
            # One immutable factory registration; clients never occupy module globals.
            agent.LiteLLM = _BoundLLM
            _REGISTERED = True
    return importlib.import_module("libs.terminus_agent." + name)


def _fatal(exc: BaseException) -> bool:
    return isinstance(exc, (UnknownOperation, ContainerUnavailable, InputTokenBudgetExceeded)) or (
        authentication_status(exc) is not None
        or is_credential_error(exc)
        or getattr(exc, "code", None) == "learning_timeout"
        or str(getattr(exc, "code", "")).startswith("codex_plan_")
        or str(exc) == "learning_timeout"
    )


@dataclass
class _Run:
    owner: Any
    operation_id: str
    model_cursor: int = 0
    exec_cursor: int = 0
    fatal: BaseException | None = None
    input_budget_stop: InputTokenBudgetExceeded | None = None

    def check(self) -> None:
        bridge = getattr(self.owner, "controller_bridge", None)
        if bridge is not None:
            bridge.check()
        if self.fatal is not None:
            raise self.fatal
        if self.input_budget_stop is not None:
            raise self.input_budget_stop
        if self.owner.runner.phase_remaining() <= 0:
            self.fatal = TimeoutError("learning_timeout")
            raise self.fatal
        if self.owner.journal is not None:
            status = self.owner.journal.authentication_failure()
            if status is not None:
                from .model import ModelClientError

                error = ModelClientError(
                    "authentication_failed", "earlier authentication failed", status=status
                )
                self.fatal = error
                raise error


class _BoundLLM:
    """Author BaseLLM interface; a run-bound host client replaces HTTP plumbing."""

    def __init__(self, model_name: str, **_kwargs: Any):
        del model_name
        self.run = _RUN.get()
        if self.run is None:
            raise RuntimeError("author_verifier_provider_not_bound")

    def count_tokens(self, messages: list[dict]) -> int:
        return self.run.owner.token_counter(json.dumps(messages, ensure_ascii=False))

    def _stop_input(self, error: InputTokenBudgetExceeded) -> None:
        callback = getattr(self.run.owner, "on_input_budget_stop", None)
        if callback is not None:
            self.run.input_budget_stop = error
            callback(error)
        else:
            self.run.fatal = error

    def call(self, prompt: str, *, message_history: list[dict] | None = None, **kwargs: Any) -> str:
        run, owner = self.run, self.run.owner
        run.check()
        messages = [*(message_history or []), {"role": "user", "content": prompt}]
        if owner.max_input_tokens is not None:
            count = self.count_tokens(messages)
            if count > owner.max_input_tokens:
                error = InputTokenBudgetExceeded(count, owner.max_input_tokens)
                self._stop_input(error)
                raise error
        operation_id = f"{run.operation_id}-model-{run.model_cursor}"
        run.model_cursor += 1
        payload = {
            "role": getattr(owner, "role", "verifier"),
            "author_operation": run.operation_id,
        }
        options = {"seed": owner.seed, "max_output_tokens": None}
        original_timeout = getattr(owner.model, "timeout_seconds", None)
        if original_timeout is not None:
            owner.model.timeout_seconds = min(original_timeout, owner.runner.phase_remaining())
        try:
            if owner.journal is not None and hasattr(owner.model, "complete_journaled"):
                response = owner.model.complete_journaled(
                    owner.journal, operation_id, payload, messages, **options
                )
            else:

                def request() -> Any:
                    return owner.model.complete(messages, **options)

                response = (
                    owner.journal.dispatch(
                        operation_id, {**payload, "messages": messages, **options}, request
                    )
                    if owner.journal is not None
                    else request()
                )
            self.last_usage = dict(response.get("usage") or {})
            self.last_context_budget = dict(response.get("context_budget") or {})
            text = response.get("content")
            if response.get("finish_reason") == "length":
                exception = author_module("llms.base_llm").OutputLengthExceededError
                raise exception("Author verifier output limit reached", truncated_response=text)
            if not isinstance(text, str) or not text.strip() or response.get("tool_calls"):
                raise ValueError("invalid_author_verifier_model_response")
            return text
        except BaseException as exc:
            if (
                isinstance(exc, InputTokenBudgetExceeded)
                and owner.journal is not None
                and owner.journal.status(operation_id) == "NOT_SENT"
            ):
                self._stop_input(exc)
            elif _fatal(exc):
                run.fatal = exc
                if authentication_status(exc) is not None or is_credential_error(exc):
                    while run.fatal.__cause__ is not None:
                        run.fatal = run.fatal.__cause__
            raise
        finally:
            if original_timeout is not None:
                owner.model.timeout_seconds = original_timeout


class _Environment:
    def __init__(self, run: _Run):
        self.run = run
        self.environment_dir = run.owner.runner.task_directory / "environment"

    async def exec(
        self,
        command: str,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout_sec: int | None = None,
    ) -> Any:
        from harbor.environments.base import ExecResult

        run, owner = self.run, self.run.owner
        run.check()
        operation_id = f"{run.operation_id}-exec-{run.exec_cursor}"
        run.exec_cursor += 1

        def execute() -> dict[str, Any]:
            result = owner.runner.author_exec(command, cwd=cwd, env=env, timeout_sec=timeout_sec)
            return {
                "return_code": result.returncode,
                "stdout": result.stdout.decode("utf-8", "replace"),
                "stderr": result.stderr.decode("utf-8", "replace"),
                "failure": result.failure,
            }

        try:
            value = (
                owner.journal.dispatch(
                    operation_id,
                    {"command": command, "cwd": cwd, "env": env, "timeout_sec": timeout_sec},
                    execute,
                )
                if owner.journal is not None
                else execute()
            )
            if value["failure"] not in {None, "timeout", "output_limit"}:
                raise ContainerUnavailable("author_verifier_" + value["failure"])
            bridge = getattr(owner, "controller_bridge", None)
            if bridge is not None:
                bridge.record_terminal(operation_id, value)
            if value["failure"]:
                value = {
                    **value,
                    "stderr": value["stderr"]
                    + "\n[terminal limit: "
                    + value["failure"]
                    + "; the captured output is preserved]\n",
                }
            return ExecResult(
                return_code=value["return_code"], stdout=value["stdout"], stderr=value["stderr"]
            )
        except BaseException as exc:
            if _fatal(exc):
                run.fatal = exc
            raise
