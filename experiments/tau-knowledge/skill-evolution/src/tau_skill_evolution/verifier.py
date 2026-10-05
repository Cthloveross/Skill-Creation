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
from .container import ProgramResult, _safe_path
from .generator import parse_model_json
from .model import ModelClientError, authentication_status, is_credential_error


def _hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
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
        observed = _hash(files)
        if self.test_hash and self.test_hash != observed:
            raise ValueError("test_hash_mismatch")
        object.__setattr__(self, "files", freeze_json(files))
        object.__setattr__(self, "test_hash", observed)

    def to_dict(self) -> dict[str, Any]:
        return {
            "files": dict(self.files),
            "version": self.version,
            "repairs": self.repairs,
            "test_hash": self.test_hash,
            "diagnosis": self.diagnosis,
            "recommendations": list(self.recommendations),
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
        )


_PROMPT = (EXPERIMENT_ROOT / "prompts" / "verifier.md").read_text(encoding="utf-8")


class SurrogateVerifier:
    def __init__(
        self,
        model: Any,
        runner: Any,
        *,
        journal: Any | None = None,
        max_output_tokens: int = 8192,
        seed: int | None = None,
        system_prompt: str | None = None,
    ) -> None:
        self.model = model
        self.runner = runner
        self.journal = journal
        self.max_output_tokens = max_output_tokens
        self.seed = seed
        self.system_prompt = _PROMPT if system_prompt is None else system_prompt

    def _call(self, payload: Mapping[str, Any], operation_id: str) -> Mapping[str, Any]:
        status = self.journal.authentication_failure() if self.journal is not None else None
        if status is not None:
            raise ModelClientError(
                "authentication_failed", "verifier authentication failed", status=status
            )

        def request() -> Any:
            if hasattr(self.model, "complete"):
                return self.model.complete(
                    [
                        {"role": "system", "content": self.system_prompt},
                        {
                            "role": "user",
                            "content": json.dumps(payload, ensure_ascii=False, allow_nan=False),
                        },
                    ],
                    tools=None,
                    seed=self.seed,
                    max_output_tokens=self.max_output_tokens,
                )
            return self.model(payload)

        raw = (
            self.journal.dispatch(
                operation_id,
                {
                    "inputs": payload,
                    "system_prompt": self.system_prompt,
                    "seed": self.seed,
                    "max_output_tokens": self.max_output_tokens,
                },
                request,
            )
            if self.journal is not None
            else request()
        )
        if isinstance(raw, Mapping) and "content" in raw:
            if raw.get("tool_calls") or raw.get("finish_reason") == "length":
                raise ValueError("invalid_verifier_response")
            raw = raw["content"]
        return parse_model_json(raw)

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
        raw = self._call(payload, operation_id)
        files = _parse_files(raw)
        if previous_tests is not None:
            for path, source in previous_tests.files.items():
                if path in files and files[path] != source:
                    raise ValueError("escalation_changed_existing_test")
            additions = {
                path: content for path, content in files.items() if path not in previous_tests.files
            }
            if not additions:
                raise ValueError("escalation_added_no_checks")
            files = {**previous_tests.files, **additions}
        return TestSuite(
            files,
            version=0 if previous_tests is None else previous_tests.version + 1,
            diagnosis=str(raw.get("diagnosis", "")),
            recommendations=_recommendations(raw),
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
        def execute(suite: TestSuite, suffix: str) -> tuple[VerificationReport, int]:
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
            collected = (
                program.output.get("collected", 0) if isinstance(program.output, Mapping) else 0
            )
            count = (
                collected if isinstance(collected, int) and not isinstance(collected, bool) else 0
            )
            return _report(suite, program), count

        suite = previous_tests
        report, collected = execute(suite, "tests")
        if not report.passed and not report.program_error:
            payload = self._payload(public_inputs, frozen_base, trace, suite, "diagnosis")
            payload["test_results"] = report.to_dict()
            try:
                raw = self._call(payload, f"{operation_id}-diagnosis")
                program_error = raw.get("test_program_error") is True
                report = replace(
                    report,
                    diagnosis=str(raw.get("diagnosis", report.diagnosis)),
                    recommendations=_recommendations(raw),
                    failure="verifier_reported_test_program_error"
                    if program_error
                    else report.failure,
                    program_error=program_error,
                )
            except Exception as exc:
                if (
                    authentication_status(exc) is not None
                    or is_credential_error(exc)
                    or (
                        self.journal is not None
                        and self.journal.authentication_failure() is not None
                    )
                ):
                    raise
                # Optional diagnosis cannot erase an actual measured failure.
                pass
        if report.program_error and suite.repairs == 0:
            original = suite
            payload = self._payload(public_inputs, frozen_base, trace, suite, "repair")
            payload["test_results"] = report.to_dict()
            try:
                raw = self._call(payload, f"{operation_id}-repair")
                files = _parse_files(raw)
                _validate_repair_files(original.files, files)
                suite = TestSuite(
                    files,
                    version=original.version,
                    repairs=1,
                    diagnosis=str(raw.get("diagnosis", "")),
                    recommendations=_recommendations(raw),
                )
                repaired, repaired_count = execute(suite, "repaired-tests")
                old_checks, new_checks = _observed_checks(report), _observed_checks(repaired)
                if repaired_count < collected or any(
                    count > new_checks[check] for check, count in old_checks.items()
                ):
                    raise ValueError("repair_removed_collected_checks")
                # Both measured runs remain sealed in separate journal responses.
                # Use repair advice for any remaining Skill failure, without another
                # diagnosis/repair cycle on this same public trace.
                return repaired
            except Exception as exc:
                if (
                    authentication_status(exc) is not None
                    or is_credential_error(exc)
                    or (
                        self.journal is not None
                        and self.journal.authentication_failure() is not None
                    )
                ):
                    raise
                return replace(
                    report,
                    suite=replace(original, repairs=1),
                    passed=False,
                    diagnosis=f"test repair failed: {type(exc).__name__}: {exc}",
                    failure="test_repair_failed",
                    program_error=True,
                )
        return report


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
    if program.failure or not isinstance(program.output, Mapping):
        return VerificationReport(
            suite,
            False,
            0,
            diagnosis=program.stderr[:4000],
            failure=program.failure or "invalid_test_report",
            program_error=True,
        )
    result = program.output
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
    calls = [item for item in items if item.get("stage") == "call"]
    forbidden = any(item.get("outcome") == "skipped" or item.get("xfail") for item in items)
    errors = (
        forbidden
        or result.get("collection_errors", 0) != 0
        or result.get("exit_code") not in (0, 1)
        or any(item.get("stage") != "call" and item.get("outcome") == "failed" for item in items)
        or any(
            item.get("outcome") == "failed" and item.get("exception") != "AssertionError"
            for item in calls
        )
    )
    passed_count = sum(item.get("outcome") == "passed" and not item.get("xfail") for item in calls)
    passed = (
        not errors
        and not forbidden
        and result.get("exit_code") == 0
        and len(calls) == collected
        and passed_count == collected
    )
    failure = "skip_or_xfail" if forbidden else "test_program_error" if errors else None
    if len(calls) != collected and not forbidden:
        errors, failure = True, "incomplete_test_report"
    return VerificationReport(
        suite,
        passed,
        passed_count / collected,
        tuple(items),
        suite.diagnosis,
        suite.recommendations,
        failure,
        errors,
    )
