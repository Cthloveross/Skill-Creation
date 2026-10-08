"""Transport bindings for the unchanged published CoEvoSkills controller."""

from __future__ import annotations

import functools
import hashlib
import json
import shlex
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from .author_verifier import _IMPORT_LOCK, _RUN, _BoundLLM, _Environment, _Run, author_module
from .container import ContainerUnavailable
from .core._canonical import canonical_json_sha256
from .model import ModelClientError


class _ControllerEnvironment(_Environment):
    def __init__(self, run: _Run, environment_dir: Path):
        super().__init__(run)
        self.environment_dir = environment_dir

    async def _copy(self, source: str, target: str, *, upload: bool) -> None:
        from .skillsbench_runtime import _host_environment

        run, owner = self.run, self.run.owner
        run.check()
        operation = f"{run.operation_id}-copy-{run.exec_cursor}"
        run.exec_cursor += 1
        runner = owner.runner
        if not runner.public_open or runner.container_name is None:
            raise ContainerUnavailable("author_environment_closed")
        if upload:
            path = Path(source)
            files = sorted(path.rglob("*")) if path.is_dir() else [path]
            if path.is_symlink() or any(
                p.is_symlink() or not (p.is_dir() or p.is_file()) for p in files
            ):
                raise ValueError("author_upload_special_file")
            source_hash = canonical_json_sha256(
                {
                    str(p.relative_to(path) if path.is_dir() else p.name): hashlib.sha256(
                        p.read_bytes()
                    ).hexdigest()
                    for p in files
                    if p.is_file()
                }
            )
        else:
            source_hash = None

        def copy() -> dict[str, Any]:
            result = runner.transport.run(
                [
                    "docker",
                    "cp",
                    source if upload else runner.container_name + ":" + source,
                    runner.container_name + ":" + target if upload else target,
                ],
                stdin=b"",
                timeout=min(60, runner.phase_remaining()),
                output_limit=runner.output_limit,
                env=_host_environment(),
            )
            return {
                "return_code": result.returncode,
                "failure": result.failure,
                "stdout": result.stdout.decode("utf-8", "replace"),
                "stderr": result.stderr.decode("utf-8", "replace"),
            }

        try:
            value = owner.journal.dispatch(
                operation,
                {"source": source, "target": target, "upload": upload, "source_hash": source_hash},
                copy,
            )
            if value["return_code"] or value["failure"]:
                raise ContainerUnavailable("author_environment_copy_failed")
            if not upload and not Path(target).exists():
                raise ContainerUnavailable("author_environment_download_checkpoint_missing")
        except BaseException as exc:
            run.fatal = exc
            raise

    async def upload_dir(self, source_dir: str | Path, target_dir: str) -> None:
        await self.exec("mkdir -p " + shlex.quote(target_dir))
        await self._copy(str(source_dir) + "/.", target_dir, upload=True)

    async def upload_file(self, source_path: str | Path, target_path: str) -> None:
        await self._copy(str(source_path), target_path, upload=True)

    async def download_dir(self, source_dir: str, target_dir: str | Path) -> None:
        Path(target_dir).mkdir(parents=True, exist_ok=True)
        await self._copy(source_dir, str(target_dir), upload=False)

    async def download_file(self, source_path: str, target_path: str | Path) -> None:
        Path(target_path).parent.mkdir(parents=True, exist_ok=True)
        await self._copy(source_path, str(target_path), upload=False)


class AuthorControllerBridge:
    """Own no loop or container: the author owns decisions, the Runner owns MAIN."""

    def __init__(
        self,
        generator_model: Any,
        verifier_model: Any,
        runner: Any,
        journal: Any,
        *,
        operation_id: str,
        environment_dir: str | Path,
        token_counter: Any,
        deadline: float | None = None,
        max_input_tokens: int | None = None,
        seed: int | None = None,
        record_tool_result: Any = None,
    ):
        self.runner, self.journal, self.deadline = runner, journal, deadline
        self.record_tool_result = record_tool_result
        self.terminal_results: list[dict[str, Any]] = []
        self._command_role: str | None = None
        self.runs = {}
        for role, model in (
            ("generator", generator_model),
            ("verifier", verifier_model),
            ("environment", None),
        ):
            owner = SimpleNamespace(
                controller_bridge=self,
                role=role,
                model=model,
                runner=runner,
                journal=journal,
                token_counter=token_counter,
                max_input_tokens=max_input_tokens,
                seed=seed,
            )
            self.runs[role] = _Run(owner, operation_id + "/" + role)
        self.environment = _ControllerEnvironment(self.runs["environment"], Path(environment_dir))

    def check(self) -> None:
        for run in self.runs.values():
            if run.fatal is not None:
                raise run.fatal
        if self.deadline is not None and time.time() >= self.deadline:
            raise ModelClientError("learning_timeout", "author controller deadline exhausted")

    def record_terminal(self, operation: str, result: dict[str, Any]) -> None:
        self.terminal_results.append(
            {
                "operation_id": operation,
                "actor": self._command_role or "host",
                "return_code": result["return_code"],
                "failure": result["failure"],
                "raw_hash": canonical_json_sha256(result),
                "raw_path": self.record_tool_result(operation, result)
                if self.record_tool_result is not None and self._command_role == "generator"
                else None,
            }
        )

    def _preview_agent(self, agent: Any) -> None:
        original = agent._execute_commands

        async def commands(environment: Any, parsed: Any) -> str:
            cursor = len(self.terminal_results)
            previous_role = self._command_role
            self._command_role = agent._llm.run.owner.role
            try:
                output = await original(environment, parsed)
            finally:
                self._command_role = previous_role
            encoded = output.encode("utf-8")
            if len(encoded) <= 8192:
                return output
            refs = self.terminal_results[cursor:]
            return encoded[:8192].decode("utf-8", "ignore") + (
                "\n[terminal preview truncated; captured results: " + json.dumps(refs) + "]"
            )

        agent._execute_commands = commands

    def _register_preview_hook(self) -> None:
        agent = author_module(
            "agents.terminus_2.harbor_terminus_2_skills"
        ).HarborTerminus2WithSkills
        with _IMPORT_LOCK:
            if getattr(agent.__init__, "_transport_preview", False):
                return
            original = agent.__init__

            @functools.wraps(original)
            def initialize(instance: Any, *args: Any, **kwargs: Any) -> None:
                original(instance, *args, **kwargs)
                run = _RUN.get()
                bridge = getattr(run.owner, "controller_bridge", None) if run is not None else None
                if bridge is not None:
                    bridge._preview_agent(instance)

            initialize._transport_preview = True
            agent.__init__ = initialize

    def build_agent(self, factory: Any, **kwargs: Any) -> Any:
        self._register_preview_hook()
        token = _RUN.set(self.runs["generator"])
        try:
            agent = factory(**kwargs)
            agent._llm = _BoundLLM(kwargs.get("model_name", "host-generator"))
            return agent
        finally:
            _RUN.reset(token)

    async def setup(self, agent: Any) -> None:
        token = _RUN.set(self.runs["verifier"])
        try:
            await agent.setup(self.environment)
            self.check()
        finally:
            _RUN.reset(token)

    async def run(self, agent: Any, instruction: str, context: Any) -> None:
        token = _RUN.set(self.runs["verifier"])
        deadlines = [
            (run.owner.model, getattr(run.owner.model, "request_deadline", None))
            for role, run in self.runs.items()
            if role != "environment"
        ]
        try:
            self.check()
            for model, previous in deadlines:
                if hasattr(model, "request_deadline") and self.deadline is not None:
                    model.request_deadline = (
                        min(previous, self.deadline) if previous is not None else self.deadline
                    )
            await agent.run(instruction, self.environment, context)
            self.check()
        finally:
            for model, previous in deadlines:
                if hasattr(model, "request_deadline"):
                    model.request_deadline = previous
            _RUN.reset(token)
