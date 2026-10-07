"""Source-blind public-trace verification with versioned pytest suites."""

from __future__ import annotations

import ast
import hashlib
import json
import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any

from tau_skill_evolution.core._canonical import freeze_json, thaw_json

from .constants import EXPERIMENT_ROOT
from .container import ContainerUnavailable, ProgramResult, _safe_path
from .generator import parse_model_json
from .journal import UnknownOperation
from .model import ModelClientError, authentication_status, is_credential_error


def _hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            thaw_json(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class TestSuite:
    __test__ = False
    files: Mapping[str, str]
    version: int = 0
    repairs: int = 0
    test_hash: str = ""
    diagnosis: str = ""
    recommendations: tuple[str, ...] = ()
    obligations: tuple[Mapping[str, Any], ...] = ()
    inheritance: tuple[Mapping[str, Any], ...] = ()

    def __post_init__(self) -> None:
        files = dict(self.files)
        if not files:
            raise ValueError("empty_test_suite")
        for path, content in files.items():
            normalized = _safe_path(path)
            if (
                normalized.parts[0] != "tests"
                or not normalized.name.startswith("test_")
                or normalized.suffix != ".py"
                or not isinstance(content, str)
            ):
                raise ValueError("invalid_test_file")
        if self.version < 0 or self.repairs not in (0, 1):
            raise ValueError("invalid_test_version")
        obligations = tuple(freeze_json(item) for item in self.obligations)
        inheritance = tuple(freeze_json(item) for item in self.inheritance)
        observed = (
            _hash({"files": files, "obligations": obligations, "inheritance": inheritance})
            if obligations or inheritance
            else _hash(files)
        )
        if self.test_hash and self.test_hash != observed:
            raise ValueError("test_hash_mismatch")
        object.__setattr__(self, "files", freeze_json(files))
        object.__setattr__(self, "test_hash", observed)
        object.__setattr__(self, "obligations", obligations)
        object.__setattr__(self, "inheritance", inheritance)

    def to_dict(self) -> dict[str, Any]:
        return {
            "files": dict(self.files),
            "version": self.version,
            "repairs": self.repairs,
            "test_hash": self.test_hash,
            "diagnosis": self.diagnosis,
            "recommendations": list(self.recommendations),
            "obligations": thaw_json(self.obligations),
            "inheritance": thaw_json(self.inheritance),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> TestSuite:
        return cls(
            files=value["files"],
            version=value["version"],
            repairs=value.get("repairs", 0),
            test_hash=value["test_hash"],
            diagnosis=value.get("diagnosis", ""),
            recommendations=tuple(value.get("recommendations", [])),
            obligations=tuple(value.get("obligations", [])),
            inheritance=tuple(value.get("inheritance", [])),
        )


@dataclass(frozen=True)
class VerificationReport:
    suite: TestSuite
    passed: bool
    pass_rate: float
    results: tuple[Mapping[str, Any], ...] = ()
    diagnosis: str = ""
    recommendations: tuple[str, ...] = ()
    failure: str | None = None
    program_error: bool = False
    test_runs: tuple[Mapping[str, Any], ...] = ()
    stage_failures: tuple[Mapping[str, Any], ...] = ()

    @property
    def test_version(self) -> int:
        return self.suite.version

    def to_dict(self) -> dict[str, Any]:
        return {
            "suite": self.suite.to_dict(),
            "passed": self.passed,
            "pass_rate": self.pass_rate,
            "results": list(self.results),
            "diagnosis": self.diagnosis,
            "recommendations": list(self.recommendations),
            "failure": self.failure,
            "program_error": self.program_error,
            "test_version": self.suite.version,
            "test_hash": self.suite.test_hash,
            "test_runs": thaw_json(self.test_runs),
            "stage_failures": thaw_json(self.stage_failures),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> VerificationReport:
        return cls(
            suite=TestSuite.from_dict(value["suite"]),
            passed=value["passed"],
            pass_rate=value["pass_rate"],
            results=tuple(value.get("results", [])),
            diagnosis=value.get("diagnosis", ""),
            recommendations=tuple(value.get("recommendations", [])),
            failure=value.get("failure"),
            program_error=value.get("program_error", False),
            test_runs=tuple(value.get("test_runs", ())),
            stage_failures=tuple(value.get("stage_failures", ())),
        )


_PROMPT = (EXPERIMENT_ROOT / "prompts" / "verifier.md").read_text(encoding="utf-8")


def _tool(
    name: str, description: str, properties: Mapping[str, Any], required: list[str]
) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": dict(properties),
                "required": required,
                "additionalProperties": False,
            },
        },
    }


_TERMINAL = _tool(
    "terminal",
    "Read public files and work only in the allowed writable directories.",
    {"command": {"type": "string"}},
    ["command"],
)
_RUN_TESTS = _tool(
    "run_tests",
    "Run current tests with the host-owned pytest harness; failures are diagnostic evidence.",
    {},
    [],
)
_SUBMIT = _tool(
    "submit_tests",
    "Seal the current tests. Explain each public obligation and any inherited file changes.",
    {
        "diagnosis": {"type": "string"},
        "recommendations": {"type": "array", "items": {"type": "string"}},
        "obligations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "requirement": {
                        "type": "string",
                        "description": (
                            "Actual public obligation, including its scope and qualifications."
                        ),
                    },
                    "checks": {"type": "array", "items": {"type": "string"}},
                    "evidence": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Exact supporting public quotes and source IDs. Preserve qualifiers; "
                            "do not turn heuristics into necessary conditions."
                        ),
                    },
                },
                "required": ["id", "requirement", "checks", "evidence"],
                "additionalProperties": False,
            },
        },
        "change_notes": {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string"},
                    "evidence": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["reason", "evidence"],
                "additionalProperties": False,
            },
        },
    },
    ["diagnosis", "recommendations", "obligations"],
)
_DIAGNOSE = _tool(
    "submit_diagnosis",
    "Return a host-only diagnosis. Requirement failures cannot be reclassified by this response.",
    {
        "diagnosis": {"type": "string"},
        "recommendations": {"type": "array", "items": {"type": "string"}},
    },
    ["diagnosis", "recommendations"],
)


class SurrogateVerifier:
    def __init__(
        self,
        model: Any,
        runner: Any,
        *,
        journal: Any | None = None,
        max_output_tokens: int | None = 8192,
        seed: int | None = None,
        system_prompt: str | None = None,
        max_episodes: int = 30,
        diagnosis_episodes: int = 8,
    ) -> None:
        self.model = model
        self.runner = runner
        self.journal = journal
        self.max_output_tokens = max_output_tokens
        self.seed = seed
        self.system_prompt = _PROMPT if system_prompt is None else system_prompt
        if not 0 < max_episodes <= 30 or not 0 < diagnosis_episodes <= 8:
            raise ValueError("invalid_verifier_episode_budget")
        self.max_episodes = max_episodes
        self.diagnosis_episodes = diagnosis_episodes

    def _request(
        self,
        payload: Mapping[str, Any],
        operation_id: str,
        messages: list[dict[str, Any]],
        tools: Any = None,
    ) -> Any:
        status = self.journal.authentication_failure() if self.journal is not None else None
        if status is not None:
            raise ModelClientError(
                "authentication_failed", "verifier authentication failed", status=status
            )

        def request() -> Any:
            if hasattr(self.model, "complete"):
                return self.model.complete(
                    messages,
                    tools=tools,
                    seed=self.seed,
                    max_output_tokens=self.max_output_tokens,
                )
            return self.model(payload)

        request_payload = {
            "inputs": payload,
            "messages": messages,
            "tools": tools,
            "seed": self.seed,
            "max_output_tokens": self.max_output_tokens,
        }
        if self.journal is not None and hasattr(self.model, "complete_journaled"):
            return self.model.complete_journaled(
                self.journal,
                operation_id,
                request_payload,
                messages,
                tools=tools,
                seed=self.seed,
                max_output_tokens=self.max_output_tokens,
            )
        return (
            self.journal.dispatch(
                operation_id,
                request_payload,
                request,
            )
            if self.journal is not None
            else request()
        )

    def _call(
        self, payload: Mapping[str, Any], operation_id: str, *, host_trace: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        messages = [
            {"role": "system", "content": self.system_prompt},
            {
                "role": "user",
                "content": json.dumps(payload, ensure_ascii=False, allow_nan=False, sort_keys=True),
            },
        ]
        if hasattr(self.model, "complete"):
            if not hasattr(self.runner, "public_verifier_session"):
                raise ValueError("public_verifier_session_required")
            return self._interactive(payload, host_trace, operation_id, messages)
        raw = self._request(payload, operation_id, messages)
        if isinstance(raw, Mapping) and "content" in raw:
            if raw.get("tool_calls") or raw.get("finish_reason") not in (None, "stop"):
                raise ValueError("invalid_verifier_response")
            raw = raw["content"]
        return parse_model_json(raw)

    def _interactive(
        self,
        payload: Mapping[str, Any],
        host_trace: Mapping[str, Any],
        operation_id: str,
        messages: list[dict[str, Any]],
    ) -> Mapping[str, Any]:
        diagnosis = payload["action"] == "diagnosis"
        previous = payload.get("previous_tests")
        files = None if previous is None else previous["files"]
        workspace = (
            None
            if self.journal is None
            else self.journal.root.parent / "verifier" / _hash(operation_id)
        )
        tools = [_TERMINAL, _DIAGNOSE] if diagnosis else [_TERMINAL, _RUN_TESTS, _SUBMIT]
        limit = self.diagnosis_episodes if diagnosis else self.max_episodes
        rejections: list[Mapping[str, Any]] = []
        kwargs = {} if workspace is None else {"workspace": workspace}
        with self.runner.public_verifier_session(
            payload["public_inputs"],
            payload["frozen_base"],
            host_trace,
            files,
            readonly_tests=diagnosis,
            **kwargs,
        ) as session:
            self._validate_resume(session, operation_id)
            for episode in range(limit):
                raw = self._request(payload, f"{operation_id}-turn-{episode}", messages, tools)
                if not isinstance(raw, Mapping) or raw.get("finish_reason") not in (
                    None,
                    "stop",
                    "tool_calls",
                ):
                    raise ValueError("invalid_verifier_response")
                calls = raw.get("tool_calls") or []
                messages.append(
                    {
                        "role": "assistant",
                        "content": raw.get("content") or "",
                        "tool_calls": calls,
                        **{
                            key: thaw_json(raw[key])
                            for key in ("_bedrock_output_items", "response_id", "usage")
                            if key in raw
                        },
                    }
                )
                if not calls:
                    value = parse_model_json(raw.get("content"))
                    if diagnosis:
                        return value
                    calls = [
                        {
                            "id": f"submit-{episode}",
                            "function": {
                                "name": "submit_tests",
                                "arguments": json.dumps(value, ensure_ascii=False, allow_nan=False),
                            },
                        }
                    ]
                    messages[-1]["tool_calls"] = calls
                for index, call in enumerate(calls):
                    name = call.get("function", {}).get("name")
                    try:
                        args = parse_model_json(call.get("function", {}).get("arguments"))
                        if name == "submit_diagnosis" and diagnosis:
                            return args
                        if name == "submit_tests" and not diagnosis:
                            current = session.files()
                            candidate = _validate_submission(
                                args, payload, files=current, require_obligations=True
                            )
                            # Collect and execute actual checks before sealing: a comments-only
                            # upgrade or empty parametrization cannot count as new coverage.
                            measured = self._session_operation(
                                session, operation_id, episode, index, "run_tests", {}
                            )
                            probe = _report(candidate, ProgramResult(**measured))
                            if probe.program_error:
                                raise ValueError(probe.failure or "test_program_error")
                            _validate_submission(
                                args,
                                payload,
                                files=current,
                                require_obligations=True,
                                observed=probe,
                            )
                            return dict(
                                args,
                                files=[
                                    {"path": path, "content": source}
                                    for path, source in current.items()
                                ],
                            )
                        if name not in {"terminal", "run_tests"} or (
                            diagnosis and name != "terminal"
                        ):
                            raise ValueError("forbidden_verifier_tool")
                        result = self._session_operation(
                            session, operation_id, episode, index, name, args
                        )
                    except Exception as exc:
                        if (
                            isinstance(exc, (UnknownOperation, ContainerUnavailable))
                            or authentication_status(exc) is not None
                            or is_credential_error(exc)
                        ):
                            raise
                        rejections.append(
                            _stage_failure(
                                "test_submission" if name == "submit_tests" else "verifier_tool",
                                f"{operation_id}-turn-{episode}-tool-{index}",
                                exc,
                            )
                        )
                        result = {"failure": type(exc).__name__, "detail": str(exc)[:2000]}
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.get("id"),
                            "content": json.dumps(
                                result, ensure_ascii=False, allow_nan=False, sort_keys=True
                            ),
                        }
                    )
        error = ValueError("verifier_episode_budget_exhausted")
        error.rejections = tuple(rejections)
        raise error

    def _session_operation(
        self,
        session: Any,
        operation_id: str,
        episode: int,
        index: int,
        name: str,
        args: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        tool_id = f"{operation_id}-turn-{episode}-tool-{index}"
        if name == "terminal":
            if (
                set(args) != {"command"}
                or not isinstance(args["command"], str)
                or not args["command"]
                or "\x00" in args["command"]
            ):
                raise ValueError("invalid_terminal_arguments")
        else:
            if args:
                raise ValueError("invalid_run_tests_arguments")
            _validate_test_source(session.files())

        def execute() -> dict[str, Any]:
            if name == "terminal":
                if set(args) != {"command"}:
                    raise ValueError("invalid_terminal_arguments")
                result = session.terminal(args["command"])
            else:
                if args:
                    raise ValueError("invalid_run_tests_arguments")
                result = session.run_tests()
            return {"program": result.to_dict(), "snapshot": session.snapshot()}

        recorded = (
            self.journal.dispatch(tool_id, {"name": name, "arguments": args}, execute)
            if self.journal is not None
            else execute()
        )
        if recorded["program"]["failure"] == "cleanup_failed":
            session.cleanup_failed = True
            raise ContainerUnavailable("verifier_cleanup_failed")
        return recorded["program"]

    def _validate_resume(self, session: Any, operation_id: str) -> None:
        if self.journal is None:
            return
        latest = None
        for request in self.journal.root.glob("*/request.json"):
            value = json.loads(request.read_text())
            identifier = value.get("operation_id", "")
            match = re.fullmatch(re.escape(operation_id) + r"-turn-(\d+)-tool-(\d+)", identifier)
            if match is None:
                continue
            if not self.journal.completed(identifier):
                if self.journal.dispatched(identifier):
                    raise UnknownOperation("verifier_tool_result_unknown")
                continue
            recorded = self.journal.response(identifier)
            if recorded["program"]["failure"] == "cleanup_failed":
                session.cleanup_failed = True
                raise ContainerUnavailable("verifier_cleanup_failed")
            order = tuple(map(int, match.groups()))
            if latest is None or order > latest[0]:
                latest = (order, recorded)
        if (
            latest is not None
            and session.snapshot()["workspace_hash"] != latest[1]["snapshot"]["workspace_hash"]
        ):
            raise ValueError("verifier_workspace_snapshot_mismatch")

    @staticmethod
    def _payload(
        public_inputs: Mapping[str, Any],
        frozen_base: Any,
        trace: Mapping[str, Any],
        previous_tests: TestSuite | None,
        action: str,
    ) -> dict[str, Any]:
        base = frozen_base.to_dict() if hasattr(frozen_base, "to_dict") else dict(frozen_base)
        public_trace = thaw_json(trace)
        # A sealed artifact snapshot is a host runner capability, never model input.
        public_trace.pop("public_artifacts_dir", None)
        return {
            "action": action,
            "public_inputs": thaw_json(public_inputs),
            "frozen_base": base,
            "public_trace": public_trace,
            "previous_tests": None if previous_tests is None else previous_tests.to_dict(),
        }

    def create_suite(
        self,
        public_inputs: Mapping[str, Any],
        frozen_base: Any,
        trace: Mapping[str, Any],
        previous_tests: TestSuite | None = None,
        *,
        operation_id: str = "verifier-initial",
    ) -> TestSuite:
        action = "initial" if previous_tests is None else "escalation"
        payload = self._payload(public_inputs, frozen_base, trace, previous_tests, action)
        if previous_tests is not None:
            payload["oracle_pass"] = False
        raw = self._call(payload, operation_id, host_trace=trace)
        return _validate_submission(
            raw, payload, merge_previous=not hasattr(self.model, "complete")
        )

    def verify(
        self,
        public_inputs: Mapping[str, Any],
        frozen_base: Any,
        trace: Mapping[str, Any],
        previous_tests: TestSuite,
        *,
        operation_id: str = "verification",
    ) -> VerificationReport:
        test_runs: list[Mapping[str, Any]] = []

        def execute(suite: TestSuite, suffix: str) -> VerificationReport:
            payload = self._payload(public_inputs, frozen_base, trace, suite, "execute_tests")
            if "public_artifacts_dir" in trace:
                # Bind the actual snapshot in the host journal without passing its host
                # path to any initial/escalation/diagnosis/repair model request.
                payload["public_artifacts_dir"] = trace["public_artifacts_dir"]

            def run() -> dict[str, Any]:
                base = payload["frozen_base"]
                return self.runner.run_verifier(
                    payload["public_inputs"], base, thaw_json(trace), suite.files
                ).to_dict()

            result = (
                self.journal.dispatch(f"{operation_id}-{suffix}", payload, run)
                if self.journal is not None
                else run()
            )
            program = ProgramResult(**result)
            test_runs.append(
                {
                    "operation_id": f"{operation_id}-{suffix}",
                    "test_hash": suite.test_hash,
                    "test_version": suite.version,
                    "program": program.to_dict(),
                }
            )
            if program.failure == "cleanup_failed":
                error = ContainerUnavailable("verifier_cleanup_failed")
                error.test_runs = tuple(test_runs)
                raise error
            return replace(
                _report(suite, program),
                test_runs=(test_runs[-1],),
            )

        suite = previous_tests
        report = execute(suite, "tests")
        if not report.passed and not report.program_error:
            payload = self._payload(public_inputs, frozen_base, trace, suite, "diagnosis")
            payload["test_results"] = report.to_dict()
            try:
                raw = self._call(payload, f"{operation_id}-diagnosis", host_trace=trace)
                report = replace(
                    report,
                    diagnosis=str(raw.get("diagnosis", report.diagnosis)),
                    recommendations=_recommendations(raw),
                )
            except Exception as exc:
                if (
                    isinstance(exc, (UnknownOperation, ContainerUnavailable))
                    or authentication_status(exc) is not None
                    or is_credential_error(exc)
                    or (
                        self.journal is not None
                        and self.journal.authentication_failure() is not None
                    )
                ):
                    exc.test_runs = tuple(test_runs)
                    raise
                # Optional diagnosis cannot erase an actual measured failure.
                report = replace(
                    report,
                    stage_failures=(_stage_failure("diagnosis", f"{operation_id}-diagnosis", exc),),
                )
        if report.program_error and suite.repairs == 0:
            original = suite
            payload = self._payload(public_inputs, frozen_base, trace, suite, "repair")
            payload["test_results"] = report.to_dict()
            repaired = None
            repair_operation = f"{operation_id}-repair"
            try:
                raw = self._call(payload, repair_operation, host_trace=trace)
                suite = _validate_submission(raw, payload)
                repair_operation = f"{operation_id}-repaired-tests"
                repaired = execute(suite, "repaired-tests")
                _validate_submission(raw, payload, observed=repaired)
                # Both measured runs remain sealed in separate journal responses.
                # Use repair advice for any remaining Skill failure, without another
                # diagnosis/repair cycle on this same public trace.
                return replace(repaired, test_runs=report.test_runs + repaired.test_runs)
            except Exception as exc:
                if (
                    isinstance(exc, (UnknownOperation, ContainerUnavailable))
                    or authentication_status(exc) is not None
                    or is_credential_error(exc)
                    or (
                        self.journal is not None
                        and self.journal.authentication_failure() is not None
                    )
                ):
                    exc.test_runs = tuple(test_runs)
                    raise
                return replace(
                    report,
                    suite=replace(original, repairs=1),
                    passed=False,
                    diagnosis=f"test repair failed: {type(exc).__name__}: {exc}",
                    failure="test_repair_failed",
                    program_error=True,
                    test_runs=report.test_runs + (() if repaired is None else repaired.test_runs),
                    stage_failures=report.stage_failures
                    + (_stage_failure("repair", repair_operation, exc),),
                )
        return report


def _validate_submission(
    raw: Mapping[str, Any],
    payload: Mapping[str, Any],
    *,
    files: Mapping[str, str] | None = None,
    require_obligations: bool = False,
    merge_previous: bool = False,
    observed: VerificationReport | None = None,
) -> TestSuite:
    """Apply the same seal rules inside the tool loop and after model return."""
    if require_obligations and not {"diagnosis", "recommendations"} <= raw.keys():
        raise ValueError("missing_test_submission_metadata")
    if not isinstance(raw.get("diagnosis", ""), str):
        raise ValueError("invalid_test_diagnosis")
    recommendations = raw.get("recommendations", [])
    if not isinstance(recommendations, list) or any(
        not isinstance(value, str) for value in recommendations
    ):
        raise ValueError("invalid_test_recommendations")
    current = dict(files) if files is not None else _parse_files(raw)
    previous_value = payload.get("previous_tests")
    previous = None if previous_value is None else TestSuite.from_dict(previous_value)
    action = payload["action"]
    if action == "repair":
        if previous is None:
            raise ValueError("repair_requires_previous_tests")
        _validate_repair_files(previous.files, current)
    _validate_test_source(current)
    # Callable offline fixtures may return additions; tool sessions return the full tree.
    if merge_previous and previous is not None and action == "escalation":
        current = {**previous.files, **current}
    obligations = _obligations(raw, current, payload, require=require_obligations)
    inheritance = ()
    if action == "escalation":
        if previous is None:
            raise ValueError("escalation_requires_previous_tests")
        inheritance = _inheritance(previous, current, obligations, raw, payload)
        if observed is not None and not set(_observed_checks(observed)) - _declared_checks(
            previous.files, tolerate_syntax_error=True
        ):
            raise ValueError("escalation_added_no_collected_checks")
    elif action == "repair":
        _preserve_obligations(previous, obligations)
        inheritance = previous.inheritance
        if observed is not None:
            original = VerificationReport.from_dict(payload["test_results"])
            old_checks, new_checks = _observed_checks(original), _observed_checks(observed)

            def collected(report: VerificationReport) -> int:
                if report.test_runs:
                    output = report.test_runs[-1]["program"].get("output")
                    if isinstance(output, Mapping):
                        count = output.get("collected")
                        if isinstance(count, int) and not isinstance(count, bool):
                            return count
                return sum(_observed_checks(report).values())

            if collected(observed) < collected(original) or any(
                count > new_checks[check] for check, count in old_checks.items()
            ):
                raise ValueError("repair_removed_collected_checks")
    return TestSuite(
        current,
        version=0 if previous is None else previous.version + int(action == "escalation"),
        repairs=int(action == "repair"),
        diagnosis=str(raw.get("diagnosis", "")),
        recommendations=_recommendations(raw),
        obligations=obligations,
        inheritance=inheritance,
    )


def _stage_failure(stage: str, operation_id: str, exc: Exception) -> dict[str, Any]:
    """Keep a bounded exception audit without changing phase control or retry rules."""
    reason = "authentication_failed" if authentication_status(exc) is not None else None
    details = []
    seen = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        message = str(current)
        if reason is None:
            candidate = getattr(current, "reason", None) or getattr(current, "code", None)
            if candidate is None and isinstance(current, ValueError):
                candidate = message.partition(":")[0]
            if isinstance(candidate, str) and re.fullmatch(r"[a-z][a-z0-9_]*", candidate):
                reason = candidate
        details.append(f"{type(current).__name__}: {message}")
        current = current.__cause__ or current.__context__
    failure = {
        "stage": stage,
        "operation_id": operation_id,
        "exception_type": type(exc).__name__,
        "reason": reason or f"{stage}_failed",
        "detail": "\n".join(details)[:2000],
    }
    runs = getattr(exc, "test_runs", ())
    if runs:
        failure["test_runs"] = thaw_json(runs)
    rejections = getattr(exc, "rejections", ())
    if rejections:
        failure["rejections"] = thaw_json(rejections)
    return failure


def _declared_checks(files: Mapping[str, str], *, tolerate_syntax_error: bool) -> set[str]:
    checks: set[str] = set()

    def visit(nodes: list[ast.stmt], prefix: str) -> None:
        for node in nodes:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith(
                "test"
            ):
                checks.add(f"{prefix}::{node.name}")
            elif isinstance(node, ast.ClassDef):
                visit(node.body, f"{prefix}::{node.name}")

    for path, source in files.items():
        try:
            parsed = ast.parse(source)
        except SyntaxError:
            if not tolerate_syntax_error:
                raise
            # A collection error may leave no recoverable identities in this file.
            # Preserve all identities available from other files and actual results.
            continue
        visit(parsed.body, path)
    return checks


def _validate_test_source(files: Mapping[str, str]) -> None:
    """Reject obvious vacuous checks and pytest reporting/configuration tampering.

    This is an integrity guard for generated checks, not a proof of test semantics.
    Arbitrary tests still execute only in the isolated public sandbox.
    """
    TestSuite(files)  # validate paths independently of generated Python
    checks = 0
    for source in files.values():
        tree = ast.parse(source)
        helpers = {
            node.name: node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }

        def meaningful(
            node: ast.AST, visited: frozenset[str], helpers: Mapping[str, ast.AST] = helpers
        ) -> bool:
            for child in ast.walk(node):
                if isinstance(child, ast.Assert) and not _constant_true(child.test):
                    return True
                if isinstance(child, ast.Raise) and child.exc is not None:
                    return True
                if isinstance(child, ast.Call):
                    if isinstance(child.func, ast.Attribute) and (
                        child.func.attr in {"fail", "raises"}
                        or child.func.attr.startswith("assert")
                    ):
                        return True
                    if isinstance(child.func, ast.Name):
                        name = child.func.id
                        if (
                            name in helpers
                            and name not in visited
                            and meaningful(helpers[name], visited | {name})
                        ):
                            return True
                    if isinstance(child.func, ast.Attribute):
                        name = child.func.attr
                        if (
                            name in helpers
                            and name not in visited
                            and meaningful(helpers[name], visited | {name})
                        ):
                            return True
            return False

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("pytest_"):
                    raise ValueError("pytest_hook_tampering")
                if node.name.startswith("test"):
                    checks += 1
                    if not meaningful(node, frozenset({node.name})):
                        raise ValueError("vacuous_test_check")
            if isinstance(node, ast.Name) and node.id in {"pytest_plugins", "pytestmark"}:
                raise ValueError("pytest_configuration_tampering")
            if isinstance(node, ast.Attribute) and node.attr in {
                "hookimpl",
                "pluginmanager",
                "_pytest",
                "tau_exception",
                "tau_requirement_failure",
                "wasxfail",
            }:
                raise ValueError("pytest_hook_tampering")
            if isinstance(node, ast.Attribute) and node.attr in {
                "skip",
                "skipif",
                "xfail",
                "importorskip",
            }:
                raise ValueError("skip_or_xfail")
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                modules = (
                    [alias.name for alias in node.names]
                    if isinstance(node, ast.Import)
                    else [node.module or ""]
                )
                if any(
                    module == "_pytest" or module.startswith("_pytest.") or module == "conftest"
                    for module in modules
                ):
                    raise ValueError("pytest_hook_tampering")
    if not checks:
        raise ValueError("empty_test_suite")


def _constant_true(node: ast.AST) -> bool:
    # Tiny literal expressions only: never eval generated Python or function calls.
    try:
        return bool(ast.literal_eval(node))
    except (ValueError, TypeError):
        pass
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        try:
            return not bool(ast.literal_eval(node.operand))
        except (ValueError, TypeError):
            return False
    if isinstance(node, ast.Compare) and len(node.ops) == len(node.comparators) == 1:
        try:
            left, right = ast.literal_eval(node.left), ast.literal_eval(node.comparators[0])
        except (ValueError, TypeError):
            return False
        if isinstance(node.ops[0], ast.Eq):
            return left == right
        if isinstance(node.ops[0], ast.NotEq):
            return left != right
    return False


def _evidence(values: Any, payload: Mapping[str, Any]) -> tuple[str, ...]:
    """Check that citations occur in public evidence, without proving entailment."""
    corpus = []

    def strings(value: Any) -> None:
        if isinstance(value, str):
            corpus.append(value)
        elif isinstance(value, Mapping):
            for key, item in value.items():
                strings(key)
                strings(item)
        elif isinstance(value, (tuple, list)):
            for item in value:
                strings(item)

    for key in ("public_inputs", "frozen_base", "public_trace"):
        strings(payload[key])
    if (
        not isinstance(values, list)
        or not values
        or any(
            not isinstance(value, str)
            or not value.strip()
            or not any(value in text for text in corpus)
            for value in values
        )
    ):
        raise ValueError("ungrounded_test_evidence")
    return tuple(values)


def _obligations(
    raw: Mapping[str, Any],
    files: Mapping[str, str],
    payload: Mapping[str, Any],
    *,
    require: bool = False,
) -> tuple[Mapping[str, Any], ...]:
    checks = _declared_checks(files, tolerate_syntax_error=False)
    values = raw.get("obligations")
    if values is None and not require:
        # Old offline fixtures have no semantic metadata; retain explicit check IDs.
        return tuple(
            {"id": check, "requirement": check, "checks": [check], "evidence": []}
            for check in sorted(checks)
        )
    if not isinstance(values, list) or not values:
        raise ValueError("missing_test_obligations")
    identifiers = set()
    covered = set()
    obligations = []
    for value in values:
        if not isinstance(value, Mapping) or set(value) != {
            "id",
            "requirement",
            "checks",
            "evidence",
        }:
            raise ValueError("invalid_test_obligation")
        identifier, requirement, selected = value["id"], value["requirement"], value["checks"]
        if (
            not isinstance(identifier, str)
            or not identifier.strip()
            or identifier in identifiers
            or not isinstance(requirement, str)
            or not requirement.strip()
            or not isinstance(selected, list)
            or not selected
            or any(check not in checks for check in selected)
        ):
            raise ValueError("invalid_test_obligation")
        evidence = _evidence(value["evidence"], payload)
        identifiers.add(identifier)
        covered.update(selected)
        obligations.append(
            {
                "id": identifier,
                "requirement": requirement,
                "checks": list(selected),
                "evidence": list(evidence),
            }
        )
    if covered != checks:
        raise ValueError("checks_without_obligations")
    return tuple(obligations)


def _preserve_obligations(previous: TestSuite, obligations: tuple[Mapping[str, Any], ...]) -> None:
    new = {value["id"]: value for value in obligations}
    for value in previous.obligations:
        if value["id"] not in new or new[value["id"]]["requirement"] != value["requirement"]:
            raise ValueError("removed_or_changed_test_obligation")


def _inheritance(
    previous: TestSuite,
    files: Mapping[str, str],
    obligations: tuple[Mapping[str, Any], ...],
    raw: Mapping[str, Any],
    payload: Mapping[str, Any],
) -> tuple[Mapping[str, Any], ...]:
    old_checks = _declared_checks(previous.files, tolerate_syntax_error=True)
    new_checks = _declared_checks(files, tolerate_syntax_error=False)
    if not new_checks - old_checks:
        raise ValueError("escalation_added_no_checks")
    if _suite_structure(previous.files) == _suite_structure(files):
        raise ValueError("escalation_only_renamed_checks")
    _preserve_obligations(previous, obligations)
    notes = raw.get("change_notes", {})
    if not isinstance(notes, Mapping):
        raise ValueError("invalid_test_change_notes")
    for path, source in previous.files.items():
        if files.get(path) == source:
            continue
        note = notes.get(path)
        if (
            not isinstance(note, Mapping)
            or not isinstance(note.get("reason"), str)
            or not note["reason"].strip()
        ):
            raise ValueError("test_change_without_justification")
        _evidence(note.get("evidence"), payload)
    if not old_checks <= new_checks and not previous.obligations:
        raise ValueError("escalation_removed_untracked_checks")
    mapping = {value["id"]: value for value in obligations}
    original = previous.obligations or tuple(
        {"id": check, "requirement": check, "checks": [check]} for check in sorted(old_checks)
    )
    return tuple(
        {
            "obligation_id": value["id"],
            "previous_checks": list(value["checks"]),
            "checks": list(mapping[value["id"]]["checks"]),
            "change_notes": thaw_json(notes),
        }
        for value in original
    )


def _suite_structure(files: Mapping[str, str]) -> Counter[str]:
    """Ignore check names/file grouping, preserving normalized executable nodes.

    This rejects exact rename-only upgrades; it does not prove semantic novelty.
    Repairs intentionally do not use this comparison.
    """

    class Normalize(ast.NodeTransformer):
        def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
            if node.name.startswith("test"):
                node.name = "test_check"
            return self._body(node)

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_ClassDef(self, node: ast.ClassDef) -> ast.ClassDef:
            if node.name.startswith("Test"):
                node.name = "TestChecks"
            return self._body(node)

        def visit_Module(self, node: ast.Module) -> ast.Module:
            return self._body(node)

        def _body(self, node: Any) -> Any:
            if (
                node.body
                and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)
            ):
                node.body = node.body[1:]
            return self.generic_visit(node)

    structures = []
    for source in files.values():
        normalized = Normalize().visit(ast.parse(source))
        structures.extend(ast.dump(node, include_attributes=False) for node in normalized.body)
    return Counter(structures)


def _validate_repair_files(previous: Mapping[str, str], repaired: Mapping[str, str]) -> None:
    if set(repaired) != set(previous):
        raise ValueError("repair_changed_file_set")
    old = _declared_checks(previous, tolerate_syntax_error=True)
    new = _declared_checks(repaired, tolerate_syntax_error=False)
    if not old <= new:
        raise ValueError("repair_removed_declared_checks")


def _observed_checks(report: VerificationReport) -> Counter[str]:
    # Count each actual case once, including setup failures. Parameter labels may
    # change during a repair, but cases cannot be shifted from one check to another.
    nodeids = {item["nodeid"] for item in report.results if isinstance(item.get("nodeid"), str)}
    return Counter(re.sub(r"(::test\w*)\[.*\]$", r"\1", nodeid) for nodeid in nodeids)


def _parse_files(raw: Mapping[str, Any]) -> dict[str, str]:
    values = raw.get("files")
    if not isinstance(values, list) or not values:
        raise ValueError("empty_test_suite")
    files: dict[str, str] = {}
    for item in values:
        if not isinstance(item, Mapping) or set(item) != {"path", "content"}:
            raise ValueError("invalid_test_file")
        path, content = item["path"], item["content"]
        if not isinstance(path, str) or path in files or not isinstance(content, str):
            raise ValueError("invalid_test_file")
        files[path] = content
    return files


def _recommendations(raw: Mapping[str, Any]) -> tuple[str, ...]:
    values = raw.get("recommendations", [])
    return (
        tuple(value for value in values if isinstance(value, str))
        if isinstance(values, list)
        else ()
    )


def _report(suite: TestSuite, program: ProgramResult) -> VerificationReport:
    if program.failure not in {None, "nonzero_exit"} or not isinstance(program.output, Mapping):
        return VerificationReport(
            suite,
            False,
            0,
            diagnosis=program.stderr[:4000],
            failure=program.failure or "invalid_test_report",
            program_error=True,
        )
    result = program.output
    exit_code = result.get("exit_code")
    if (
        isinstance(exit_code, bool)
        or not isinstance(exit_code, int)
        or isinstance(program.exit_code, bool)
        or not isinstance(program.exit_code, int)
        or exit_code != program.exit_code
        or (program.failure == "nonzero_exit" and exit_code == 0)
    ):
        return VerificationReport(
            suite, False, 0, failure="inconsistent_test_exit_code", program_error=True
        )
    collected = result.get("collected")
    items = result.get("results")
    if (
        isinstance(collected, bool)
        or not isinstance(collected, int)
        or collected <= 0
        or not isinstance(items, list)
        or any(not isinstance(item, Mapping) for item in items)
    ):
        return VerificationReport(
            suite, False, 0, failure="empty_or_invalid_tests", program_error=True
        )
    nodeids = result.get("collected_nodeids")
    declared = _declared_checks(suite.files, tolerate_syntax_error=True)
    if (
        not isinstance(nodeids, list)
        or len(nodeids) != collected
        or any(not isinstance(nodeid, str) or not nodeid for nodeid in nodeids)
        or len(set(nodeids)) != collected
        or any(re.sub(r"(::test\w*)\[.*\]$", r"\1", nodeid) not in declared for nodeid in nodeids)
    ):
        return VerificationReport(
            suite, False, 0, failure="invalid_collected_checks", program_error=True
        )
    stages = set()
    for item in items:
        nodeid, stage, outcome = item.get("nodeid"), item.get("stage"), item.get("outcome")
        exception = item.get("exception")
        if (
            nodeid not in nodeids
            or stage not in {"setup", "call", "teardown"}
            or outcome not in {"passed", "failed", "skipped"}
            or not isinstance(item.get("xfail"), bool)
            or not (exception is None or isinstance(exception, str))
            or not isinstance(item.get("requirement_failure", False), bool)
            or (nodeid, stage) in stages
            or (outcome == "passed" and (exception is not None or item.get("requirement_failure")))
        ):
            return VerificationReport(
                suite,
                False,
                0,
                tuple(items),
                failure="inconsistent_test_report",
                program_error=True,
            )
        stages.add((nodeid, stage))
    calls = [item for item in items if item.get("stage") == "call"]
    forbidden = any(item.get("outcome") == "skipped" or item.get("xfail") for item in items)
    errors = (
        forbidden
        or result.get("collection_errors", 0) != 0
        or result.get("exit_code") not in (0, 1)
        or any(item.get("stage") != "call" and item.get("outcome") == "failed" for item in items)
        or any(
            item.get("outcome") == "failed"
            and not (
                item.get("requirement_failure") is True or item.get("exception") == "AssertionError"
            )
            for item in calls
        )
    )
    passed_count = sum(item.get("outcome") == "passed" and not item.get("xfail") for item in calls)
    complete = len(calls) == collected
    measured_success = complete and passed_count == collected
    if (result.get("exit_code") == 0 and not measured_success) or (
        result.get("exit_code") == 1 and measured_success
    ):
        errors = True
    passed = not errors and measured_success and result.get("exit_code") == 0
    failure = "skip_or_xfail" if forbidden else "test_program_error" if errors else None
    if not complete and not forbidden:
        errors, failure = True, "incomplete_test_report"
    return VerificationReport(
        suite,
        passed,
        passed_count / collected,
        tuple(items),
        "" if passed else suite.diagnosis,
        () if passed else suite.recommendations,
        failure,
        errors,
    )
