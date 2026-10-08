"""Pinned CoEvoSkills verification with host transport and live MAIN adapters."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import importlib
import json
import sys
import threading
import types
from collections.abc import Mapping
from contextvars import ContextVar
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

from .container import ContainerUnavailable
from .core._canonical import canonical_json_sha256, thaw_json
from .journal import UnknownOperation
from .model import InputTokenBudgetExceeded, authentication_status, is_credential_error
from .verifier import TestSuite, VerificationReport

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
            for suffix in (
                "",
                ".terminus_agent",
                ".terminus_agent.agents",
                ".terminus_agent.agents.terminus_2",
                ".terminus_agent.evolution",
                ".terminus_agent.llms",
                ".terminus_agent.utils",
            ):
                fullname = "libs" + suffix
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
        or str(exc) == "learning_timeout"
    )


@dataclass
class _Run:
    owner: AuthorSkillsBenchVerifier
    operation_id: str
    model_cursor: int = 0
    exec_cursor: int = 0
    fatal: BaseException | None = None

    def check(self) -> None:
        if self.fatal is not None:
            raise self.fatal
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

    def call(self, prompt: str, *, message_history: list[dict] | None = None, **kwargs: Any) -> str:
        run, owner = self.run, self.run.owner
        run.check()
        messages = [*(message_history or []), {"role": "user", "content": prompt}]
        if owner.max_input_tokens is not None:
            count = self.count_tokens(messages)
            if count > owner.max_input_tokens:
                run.fatal = InputTokenBudgetExceeded(count, owner.max_input_tokens)
                raise run.fatal
        operation_id = f"{run.operation_id}-model-{run.model_cursor}"
        run.model_cursor += 1
        payload = {"role": "verifier", "author_operation": run.operation_id}
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
            text = response.get("content")
            if response.get("finish_reason") == "length":
                exception = author_module("llms.base_llm").OutputLengthExceededError
                raise exception("Author verifier output limit reached", truncated_response=text)
            if not isinstance(text, str) or not text.strip() or response.get("tool_calls"):
                raise ValueError("invalid_author_verifier_model_response")
            return text
        except BaseException as exc:
            if _fatal(exc):
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
            if value["failure"]:
                raise (
                    ContainerUnavailable("author_verifier_" + value["failure"])
                    if (value["failure"] == "cleanup_failed")
                    else RuntimeError("author_verifier_" + value["failure"])
                )
            return ExecResult(
                return_code=value["return_code"], stdout=value["stdout"], stderr=value["stderr"]
            )
        except BaseException as exc:
            if _fatal(exc):
                run.fatal = exc
            raise


class AuthorSkillsBenchVerifier:
    """Shared-engine facade; decisions come from the pinned author's verifier."""

    def __init__(
        self,
        model: Any,
        runner: Any,
        *,
        journal: Any = None,
        token_counter: Any,
        max_input_tokens: int | None = None,
        seed: int | None = None,
        logs_dir: Path,
    ):
        if runner.learning_workspace is None or not runner.public_open:
            raise ContainerUnavailable("author_verifier_requires_live_learning_main")
        self.model, self.runner, self.journal = model, runner, journal
        self.token_counter, self.max_input_tokens, self.seed = token_counter, max_input_tokens, seed
        self.logs_dir = Path(logs_dir)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.author = author_module("evolution.independent_verifier").IndependentVerifier(
            model_name=getattr(getattr(model, "config", None), "model", "host-verifier")
        )
        self.pending: dict[str, tuple[dict[str, Any], str | None]] = {}
        if self.journal is not None:
            records, consumed = [], {}
            for path in self.journal.root.glob("*/request.json"):
                request = json.loads(path.read_text())
                identifier = request["operation_id"]
                if identifier.endswith("-author-generation") and self.journal.completed(identifier):
                    records.append((identifier, self.journal.response(identifier)))
                elif identifier.endswith("-author-verification"):
                    generation = request["payload"].get("generation_operation")
                    if generation:
                        consumed[generation] = identifier.removesuffix("-author-verification")
            for identifier, record in sorted(records, key=lambda item: item[1]["generation_count"]):
                self.author._generation_count = record["generation_count"]
                self.author._last_result = self._result(record["author_result"])
                if record["script"] and record["author_result"]["source"] == "script":
                    suite = TestSuite(
                        {"tests/test_outputs.py": record["script"]}, version=record["version"]
                    )
                    record["generation_operation"] = identifier
                    self.pending[self._pending_key(record["trace_hash"], suite)] = (
                        record,
                        consumed.get(identifier),
                    )

    @staticmethod
    def _pending_key(trace_hash: str, suite: TestSuite) -> str:
        return f"{trace_hash}:{suite.version}:{suite.test_hash}"

    @staticmethod
    def _result(value: Mapping[str, Any]) -> Any:
        cls = author_module("evolution.models").VerificationResult
        return cls(
            **{field.name: value[field.name] for field in fields(cls) if field.name in value}
        )

    async def _write(self, environment: _Environment, path: str, text: str) -> None:
        data = base64.b64encode(text.encode("utf-8")).decode("ascii")
        import shlex

        result = await environment.exec(
            "mkdir -p "
            + shlex.quote(str(Path(path).parent))
            + "; printf %s "
            + shlex.quote(data)
            + " | base64 -d > "
            + shlex.quote(path),
            timeout_sec=30,
        )
        if result.return_code:
            raise RuntimeError("author_verifier_file_staging_failed")

    async def _documents(self, environment: _Environment, base: Any) -> None:
        value = base.to_dict() if hasattr(base, "to_dict") else thaw_json(base)
        if hasattr(self.runner, "stage_frozen_documents"):
            environment.run.check()

            def stage() -> dict[str, str]:
                self.runner.stage_frozen_documents(value)
                return {"base_hash": canonical_json_sha256(value)}

            if self.journal is not None:
                self.journal.dispatch(
                    environment.run.operation_id + "-frozen-documents", value, stage
                )
            else:
                stage()
            return
        for document in value.get("documents", ()):
            name = hashlib.sha256(document["document_id"].encode()).hexdigest() + ".md"
            await self._write(environment, "/app/environment/doc/" + name, document["content"])

    def _run(self, operation_id: str, payload: Mapping[str, Any], callback: Any) -> dict[str, Any]:
        bindings = []

        def execute() -> dict[str, Any]:
            binding = _Run(self, operation_id)
            bindings.append(binding)
            token = _RUN.set(binding)
            try:
                binding.check()
                snapshot = getattr(self.runner, "public_environment_manifest", None)
                before = snapshot() if snapshot is not None else None
                result = asyncio.run(callback(binding, _Environment(binding)))
                if binding.fatal is not None:
                    raise binding.fatal
                if before is not None:
                    after = snapshot()
                    result["public_environment_changes"] = {
                        "before_hash": canonical_json_sha256(before),
                        "after_hash": canonical_json_sha256(after),
                        "before": before,
                        "after": after,
                        "changed_paths": sorted(
                            path
                            for path in before.keys() | after.keys()
                            if before.get(path) != after.get(path)
                        ),
                    }
                return result
            finally:
                _RUN.reset(token)

        try:
            return (
                self.journal.dispatch(operation_id, payload, execute)
                if self.journal is not None
                else execute()
            )
        except BaseException:
            if bindings and bindings[-1].fatal is not None:
                raise bindings[-1].fatal from None
            raise

    def create_suite(
        self,
        public_inputs: Mapping[str, Any],
        frozen_base: Any,
        trace: Mapping[str, Any],
        previous_tests: TestSuite | None = None,
        *,
        operation_id: str = "verifier-initial",
        adversarial_recheck: bool | None = None,
    ) -> TestSuite:
        key = canonical_json_sha256(thaw_json(trace))
        version = 0 if previous_tests is None else previous_tests.version + 1

        async def generate(_binding: _Run, environment: _Environment) -> dict[str, Any]:
            await self._documents(environment, frozen_base)
            if previous_tests is not None and previous_tests.files["tests/test_outputs.py"]:
                await self._write(
                    environment,
                    "/root/verifier/test_outputs.py",
                    previous_tests.files["tests/test_outputs.py"],
                )
            result = await self.author.generate_and_run(
                environment,
                public_inputs.get("opening", public_inputs.get("instruction", "")),
                self.logs_dir / operation_id,
                adversarial_recheck=(
                    previous_tests is not None
                    if adversarial_recheck is None
                    else adversarial_recheck
                ),
            )
            script = await environment.exec(
                "cat /root/verifier/test_outputs.py 2>/dev/null || "
                "cat /root/verifier/check_output.py 2>/dev/null",
                timeout_sec=10,
            )
            return {
                "author_result": asdict(result),
                "script": script.stdout if script.return_code == 0 else "",
                "generation_count": self.author._generation_count,
                "trace_hash": key,
                "version": version,
            }

        record = self._run(
            operation_id + "-author-generation",
            {
                "trace": thaw_json(trace),
                "version": version,
                "previous_tests": None if previous_tests is None else previous_tests.to_dict(),
                "adversarial_recheck": adversarial_recheck,
            },
            generate,
        )
        if record["author_result"]["source"] != "script" or not record["script"]:
            error = RuntimeError("author_verifier_" + record["author_result"]["source"])
            error.source = record["author_result"]["source"]
            error.author_result = record["author_result"]
            raise error
        self.author._generation_count = record["generation_count"]
        self.author._last_result = self._result(record["author_result"])
        suite = TestSuite(
            {"tests/test_outputs.py": record["script"]},
            version=version,
            diagnosis=record["author_result"]["diagnosis"],
        )
        record["generation_operation"] = operation_id + "-author-generation"
        existing = self.pending.get(self._pending_key(key, suite))
        self.pending[self._pending_key(key, suite)] = (record, existing[1] if existing else None)
        return suite

    def verify(
        self,
        public_inputs: Mapping[str, Any],
        frozen_base: Any,
        trace: Mapping[str, Any],
        previous_tests: TestSuite,
        *,
        operation_id: str = "verification",
    ) -> VerificationReport:
        key = self._pending_key(canonical_json_sha256(thaw_json(trace)), previous_tests)
        pending = self.pending.get(key)

        async def verify(_binding: _Run, environment: _Environment) -> dict[str, Any]:
            stage_failures = []
            if pending is not None and pending[1] in (None, operation_id):
                result = self._result(pending[0]["author_result"])
            else:
                await self._documents(environment, frozen_base)
                if previous_tests.files["tests/test_outputs.py"]:
                    await self._write(
                        environment,
                        "/root/verifier/test_outputs.py",
                        previous_tests.files["tests/test_outputs.py"],
                    )
                result = (
                    await author_module("evolution.self_verifier")
                    .SelfVerifier()
                    .verify(environment)
                )
            if result.error:
                stage_failures.append(
                    {
                        "stage": "verification",
                        "operation_id": _binding.operation_id,
                        "exception_type": "AuthorAgentError",
                        "reason": "author_agent_error",
                        "detail": result.error,
                    }
                )
            if result.source == "script" and (result.tests_failed > 0 or result.pass_rate < 1):
                try:
                    result.diagnosis = await self.author.diagnose_failures(
                        environment,
                        public_inputs.get("opening", public_inputs.get("instruction", "")),
                        self.logs_dir / operation_id,
                        result,
                    )
                except Exception as exc:
                    if _binding.fatal is not None or _fatal(exc):
                        raise
                    result.diagnosis = ""
                    stage_failures.append(
                        {
                            "stage": "diagnosis",
                            "operation_id": operation_id + "-author-verification",
                            "exception_type": type(exc).__name__,
                            "reason": "author_diagnosis_error",
                            "detail": str(exc),
                        }
                    )
                finally:
                    # Restore the sealed bytes even when diagnosis itself fails.
                    await self._write(
                        environment,
                        "/root/verifier/test_outputs.py",
                        previous_tests.files["tests/test_outputs.py"],
                    )
            return {**asdict(result), "stage_failures": stage_failures}

        raw = self._run(
            operation_id + "-author-verification",
            {
                "trace": thaw_json(trace),
                "suite": previous_tests.to_dict(),
                "generation_operation": pending[0]["generation_operation"]
                if pending is not None and pending[1] in (None, operation_id)
                else None,
            },
            verify,
        )
        if pending is not None:
            self.pending[key] = (pending[0], operation_id)
        pass_rate = self._result(raw).pass_rate
        passed = bool(
            raw["source"] == "script"
            and raw["total_tests"] > 0
            and raw["tests_failed"] == 0
            and pass_rate == 1
        )
        program_error = raw["source"] in {"no_script", "script_error"}
        return VerificationReport(
            previous_tests,
            passed,
            pass_rate,
            results=tuple(
                {
                    "nodeid": item.get("full_name", item["name"]),
                    "outcome": item["status"].lower(),
                    "detail": item.get("message", ""),
                }
                for item in raw["test_details"]
            ),
            diagnosis="" if passed else raw["diagnosis"],
            stage_failures=tuple(raw.get("stage_failures", ())),
            failure=(
                "author_verifier_program_error"
                if program_error
                else "author_verifier_unknown_source"
                if raw["source"] != "script"
                else None
            ),
            program_error=program_error,
            test_runs=(
                {
                    "operation_id": operation_id + "-author-verification",
                    "test_hash": previous_tests.test_hash,
                    "test_version": previous_tests.version,
                    "source": raw["source"],
                    "author_result": raw,
                    "public_environment_changes": raw.get("public_environment_changes"),
                },
            ),
            author_result=raw,
        )
