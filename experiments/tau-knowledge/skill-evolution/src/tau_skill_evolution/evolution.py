"""Fixed-base Skill/test co-evolution; independent evaluation is never an input."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from typing import Any

from tau_skill_evolution.core._canonical import freeze_json, thaw_json

from .artifacts import EvolutionSubmission, SkillBundle
from .generator import GeneratorContextBudgetExhausted, public_feedback_history
from .model import ModelClientError, authentication_status, is_credential_error
from .verifier import _stage_failure


class OracleUnavailable(RuntimeError):
    """A completed episode returned no valid official score; never a task failure."""


@dataclass(frozen=True)
class EvolutionResult:
    versions: tuple[SkillBundle, ...]
    attempts: tuple[Mapping[str, Any], ...]
    verifications: tuple[Mapping[str, Any], ...]
    oracle_results: tuple[bool, ...]
    revision_attempts: int
    stop_reason: str
    final_bundle_hash: str
    oracle_failures: tuple[Mapping[str, Any], ...] = ()
    final_bundle_ref: Mapping[str, str | None] | None = None
    submissions: tuple[Mapping[str, Any], ...] = ()
    stage_failures: tuple[Mapping[str, Any], ...] = ()
    author_counters: Mapping[str, int] | None = None
    oracle_history: tuple[Mapping[str, Any], ...] = ()
    best_oracle_ref: Mapping[str, Any] | None = None
    author_terminal_result: Mapping[str, Any] | None = None
    selection_reason: str | None = None
    interventions: tuple[Mapping[str, Any], ...] = ()
    best_snapshot: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "stage_failures", freeze_json(self.stage_failures))
        for name in (
            "author_counters",
            "oracle_history",
            "best_oracle_ref",
            "author_terminal_result",
            "interventions",
            "best_snapshot",
        ):
            object.__setattr__(self, name, freeze_json(getattr(self, name)))
        if self.final_bundle_ref is not None:
            if (
                not isinstance(self.final_bundle_ref, Mapping)
                or set(self.final_bundle_ref) != {"bundle_hash", "parent_hash"}
                or self.final_bundle_ref["bundle_hash"] != self.final_bundle_hash
            ):
                raise ValueError("invalid_final_bundle_ref")
            parent = self.final_bundle_ref["parent_hash"]
            if (
                not any(bundle.bundle_hash == self.final_bundle_hash for bundle in self.versions)
                or (parent is None and self.final_bundle_hash != self.versions[0].bundle_hash)
                or (
                    parent == self.final_bundle_hash
                    and not (
                        self.author_counters is not None
                        and any(
                            item.get("bundle_hash") == self.final_bundle_hash
                            and item.get("parent_hash") == parent
                            for item in self.submissions
                        )
                    )
                )
                or (
                    parent is not None
                    and not any(bundle.bundle_hash == parent for bundle in self.versions)
                )
            ):
                raise ValueError("invalid_final_bundle_ref")
            _ = self.final_bundle  # Validate against a sealed content version.
            object.__setattr__(self, "final_bundle_ref", freeze_json(self.final_bundle_ref))

    @property
    def oracle_calls(self) -> int:
        return len(self.oracle_results)

    @property
    def final_bundle(self) -> SkillBundle:
        bundle = next(
            bundle for bundle in self.versions if bundle.bundle_hash == self.final_bundle_hash
        )
        return (
            replace(bundle, parent_hash=self.final_bundle_ref["parent_hash"])
            if self.final_bundle_ref is not None
            else bundle
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "versions": [bundle.to_dict() for bundle in self.versions],
            "attempts": list(self.attempts),
            "verifications": list(self.verifications),
            "oracle_results": list(self.oracle_results),
            "oracle_calls": self.oracle_calls,
            "revision_attempts": self.revision_attempts,
            "stop_reason": self.stop_reason,
            "final_bundle_hash": self.final_bundle_hash,
            "oracle_failures": list(self.oracle_failures),
            "oracle_attempts": self.oracle_calls + len(self.oracle_failures),
            "submissions": list(self.submissions),
            "stage_failures": thaw_json(self.stage_failures),
            "submitted_learning_executions": len(
                {item["execution_id"] for item in self.submissions}
            ),
            "final_bundle_ref": dict(self.final_bundle_ref)
            if self.final_bundle_ref is not None
            else None,
            "author_counters": thaw_json(self.author_counters),
            "oracle_history": thaw_json(self.oracle_history),
            "best_oracle_ref": thaw_json(self.best_oracle_ref),
            "author_terminal_result": thaw_json(self.author_terminal_result),
            "selection_reason": self.selection_reason,
            "interventions": thaw_json(self.interventions),
            "best_snapshot": thaw_json(self.best_snapshot),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> EvolutionResult:
        return cls(
            tuple(SkillBundle.from_dict(bundle) for bundle in value["versions"]),
            tuple(value["attempts"]),
            tuple(value["verifications"]),
            tuple(value["oracle_results"]),
            value["revision_attempts"],
            value["stop_reason"],
            value["final_bundle_hash"],
            tuple(value.get("oracle_failures", ())),
            value.get("final_bundle_ref"),
            tuple(value.get("submissions", ())),
            tuple(value.get("stage_failures", ())),
            value.get("author_counters"),
            tuple(value.get("oracle_history", ())),
            value.get("best_oracle_ref"),
            value.get("author_terminal_result"),
            value.get("selection_reason"),
            tuple(value.get("interventions", ())),
            value.get("best_snapshot"),
        )


class EvolutionEngine:
    def __init__(
        self,
        *,
        execute_initial: Callable[..., EvolutionSubmission],
        oracle: Callable[..., Any],
        verifier: Any,
        revise: Callable[..., EvolutionSubmission],
        journal: Any | None = None,
        max_revisions: int = 15,
        max_oracles: int = 5,
        max_oracle_errors: int = 5,
    ) -> None:
        if (
            isinstance(max_revisions, bool)
            or not isinstance(max_revisions, int)
            or not 0 <= max_revisions <= 15
            or isinstance(max_oracles, bool)
            or not isinstance(max_oracles, int)
            or not 0 <= max_oracles <= 5
            or isinstance(max_oracle_errors, bool)
            or not isinstance(max_oracle_errors, int)
            or not 0 <= max_oracle_errors <= 5
        ):
            raise ValueError("evolution budgets exceed protocol")
        self.execute_initial = execute_initial
        self.oracle = oracle
        self.verifier = verifier
        self.revise = revise
        self.journal = journal
        self.max_revisions = max_revisions
        self.max_oracles = max_oracles
        self.max_oracle_errors = max_oracle_errors

    def _dispatch(
        self,
        operation_id: str,
        payload: Mapping[str, Any],
        callback: Any,
        *,
        allow_after_auth: bool = False,
        external: bool = True,
    ) -> Any:
        # A derived result can still be sealed after authentication stops external work.
        status = self._authentication_status()
        if status is not None and not allow_after_auth:
            raise ModelClientError(
                "authentication_failed", "evolution authentication failed", status=status
            )
        return (
            self.journal.dispatch(operation_id, payload, callback, external=external)
            if self.journal is not None
            else callback()
        )

    def _authentication_status(self) -> int | None:
        check = getattr(self.journal, "authentication_failure", None)
        return check() if check is not None else None

    def run(
        self,
        public_inputs: Mapping[str, Any],
        frozen_base: Any,
        initial_bundle: SkillBundle,
        *,
        operation_prefix: str = "evolution",
    ) -> EvolutionResult:
        result_id = f"{operation_prefix}-result"
        result_identity = {
            "result_format": 3,
            "initial_bundle_hash": initial_bundle.bundle_hash,
            "base_hash": frozen_base.base_hash,
            "max_revisions": self.max_revisions,
            "max_oracles": self.max_oracles,
            "max_oracle_errors": self.max_oracle_errors,
        }
        if self.journal is not None and self.journal.completed(result_id):
            return EvolutionResult.from_dict(
                self._dispatch(result_id, result_identity, lambda: None, allow_after_auth=True)
            )
        versions, current = [initial_bundle], initial_bundle
        attempts, verifications, oracle_results, oracle_failures = [], [], [], []
        feedback_history, submissions, stage_failures = [], [], []
        revision_attempts = turn = 0
        suite = None
        stop_reason = ""

        def retain_submission(value):
            submissions.append(
                {
                    "submission_hash": value.submission_hash,
                    "trace_hash": value.trace_hash,
                    "bundle_hash": value.bundle.bundle_hash,
                    "parent_hash": value.bundle.parent_hash,
                    "execution_id": value.execution_id,
                    "operation_cursor": value.operation_cursor,
                    "initial": value.initial,
                }
            )

        def failed(stage, operation_id, exc):
            stage_failures.append(_stage_failure(stage, operation_id, exc))
            return _fatal_reason(stage, exc) or _failure(stage, exc)

        def guard():
            if self._authentication_status() is not None:
                return "authentication_failed"
            return None

        def feedback(value):
            serialized = value.to_dict() if hasattr(value, "to_dict") else value
            feedback_history.extend(
                public_feedback_history(
                    [
                        {
                            "kind": "verification",
                            "base_hash": frozen_base.base_hash,
                            "bundle_hash": current.bundle_hash,
                            **serialized,
                        }
                    ],
                    frozen_base.base_hash,
                )
            )

        def revise_current(report):
            nonlocal current, trace, revision_attempts, turn, stop_reason
            if revision_attempts >= self.max_revisions:
                stop_reason = "revision_budget_exhausted"
                return
            revision_attempts += 1
            operation = f"{operation_prefix}-revision-{revision_attempts}"
            attempt = {
                "attempt": revision_attempts,
                "parent_hash": current.bundle_hash,
                "test_version": suite.version if suite is not None else None,
                "test_hash": suite.test_hash if suite is not None else None,
            }
            try:
                value = self.revise(
                    current,
                    public_inputs,
                    frozen_base,
                    report,
                    operation_id=operation,
                    public_trace=trace,
                    feedback_history=tuple(
                        public_feedback_history(feedback_history, frozen_base.base_hash)
                    ),
                )
                value = EvolutionSubmission.from_dict(value.to_dict())
                if value.initial or value.bundle.parent_hash != current.bundle_hash:
                    raise ValueError("revision_parent_mismatch")
                candidate = value.bundle
                attempt.update(
                    bundle_hash=candidate.bundle_hash, submission_hash=value.submission_hash
                )
                trace = thaw_json(value.public_trace)
                retain_submission(value)
                if candidate.bundle_hash == current.bundle_hash:
                    attempt["status"] = "unchanged"
                else:
                    attempt["status"] = "changed"
                    current = candidate
                    if all(item.bundle_hash != current.bundle_hash for item in versions):
                        versions.append(current)
            except GeneratorContextBudgetExhausted as exc:
                stage_failures.append(_stage_failure("revision", operation, exc))
                revision_attempts -= 1
                stop_reason = "context_budget_exhausted"
                return
            except Exception as exc:
                if is_credential_error(exc):
                    raise
                stage_failures.append(_stage_failure("revision", operation, exc))
                attempt.update(status="invalid", failure=type(exc).__name__)
                if getattr(exc, "dispatched", True) is False:
                    revision_attempts -= 1
                    attempt["status"] = "not_sent"
                    stop_reason = getattr(exc, "reason", "revision_unavailable")
                reason = _fatal_reason("revision", exc)
                if reason:
                    stop_reason = reason
                    if reason.endswith("result_unknown"):
                        attempt["status"] = "result_unknown"
                    elif reason == "authentication_failed":
                        attempt["status"] = reason
            attempts.append(attempt)
            turn += 1

        def official(value, phase, operation):
            nonlocal stop_reason
            if guard():
                stop_reason = guard()
                return None

            def call():
                try:
                    outcome = self.oracle(value)
                except Exception as exc:
                    if _fatal_reason("oracle", exc):
                        raise
                    if isinstance(exc, OracleUnavailable) or getattr(
                        exc, "response_received", False
                    ):
                        return {"status": "NOT_MEASURED", "reason": type(exc).__name__}
                    raise
                if not isinstance(outcome, bool):
                    raise TypeError("oracle_must_return_pass_fail_only")
                return {"status": "MEASURED", "passed": outcome}

            try:
                outcome = self._dispatch(operation, {"bundle_hash": value.bundle_hash}, call)
            except Exception as exc:
                stop_reason = failed("oracle", operation, exc)
                return None
            if self._authentication_status() is not None:
                stop_reason = "authentication_failed"
                return None
            entry = {
                "operation_id": operation,
                "phase": phase,
                "bundle_hash": value.bundle_hash,
                "parent_hash": value.parent_hash,
                **outcome,
            }
            if outcome["status"] != "MEASURED":
                oracle_failures.append(entry)
                return outcome
            oracle_results.append(outcome["passed"])
            if phase == "normal":
                feedback_history.append(
                    {
                        "kind": "oracle",
                        "base_hash": frozen_base.base_hash,
                        "bundle_hash": value.bundle_hash,
                        "passed": outcome["passed"],
                        "call": len(oracle_results),
                    }
                )
            return outcome

        try:
            if guard():
                if self._authentication_status() is not None:
                    raise ModelClientError(
                        "authentication_failed",
                        "evolution authentication failed",
                        status=self._authentication_status(),
                    )
                raise RuntimeError(guard())
            value = self.execute_initial(
                initial_bundle,
                public_inputs,
                frozen_base,
                operation_id=f"{operation_prefix}-initial-execution",
            )
            value = EvolutionSubmission.from_dict(value.to_dict())
            if not value.initial or value.bundle.to_dict() != initial_bundle.to_dict():
                raise ValueError("initial_execution_modified_bundle")
            trace = thaw_json(value.public_trace)
            retain_submission(value)
        except Exception as exc:
            if is_credential_error(exc):
                raise
            stop_reason = failed("initial_execution", f"{operation_prefix}-initial-execution", exc)
            trace = {}
        while not stop_reason:
            stop_reason = guard() or ""
            if stop_reason:
                break
            prefix = f"{operation_prefix}-turn-{turn}"
            if suite is None:
                operation = f"{prefix}-suite"
                try:
                    suite = self.verifier.create_suite(
                        public_inputs,
                        frozen_base,
                        trace,
                        operation_id=operation,
                    )
                except Exception as exc:
                    stage_failures.append(_stage_failure("verifier_initialization", operation, exc))
                    fatal = _fatal_reason("verification", exc)
                    stop_reason = fatal or _failure("verifier_initialization", exc)
                    break
            try:
                report = self.verifier.verify(
                    public_inputs, frozen_base, trace, suite, operation_id=f"{prefix}-verify"
                )
            except Exception as exc:
                stage_failures.append(_stage_failure("verification", f"{prefix}-verify", exc))
                fatal = _fatal_reason("verification", exc)
                stop_reason = fatal or _failure("verification", exc)
                break
            suite = report.suite
            stage_failures.extend(report.stage_failures)
            verifications.append({**submissions[-1], **report.to_dict()})
            feedback(report)
            if guard():
                stop_reason = guard()
                break
            if report.program_error:
                stop_reason = "verification_program_error_exhausted"
                break
            if not report.passed:
                revise_current(report)
                continue
            if len(oracle_results) >= self.max_oracles:
                stop_reason = "oracle_budget_exhausted"
                break
            while True:
                operation = f"{prefix}-oracle"
                if oracle_failures:
                    operation += f"-infrastructure-{len(oracle_failures)}"
                outcome = official(current, "normal", operation)
                if outcome is None:
                    break
                if outcome["status"] == "MEASURED":
                    break
                if len(oracle_failures) >= self.max_oracle_errors:
                    stop_reason = "oracle_infrastructure_unavailable"
                    break
            if stop_reason:
                break
            if outcome["status"] != "MEASURED":
                continue
            if outcome["passed"]:
                stop_reason = "oracle_success"
                break
            if len(oracle_results) >= self.max_oracles:
                stop_reason = "oracle_budget_exhausted"
                break
            try:
                suite = self.verifier.create_suite(
                    public_inputs,
                    frozen_base,
                    trace,
                    previous_tests=suite,
                    operation_id=f"{prefix}-escalate",
                )
            except Exception as exc:
                stop_reason = failed("test_escalation", f"{prefix}-escalate", exc)
                break
            turn += 1
        result = EvolutionResult(
            tuple(versions),
            tuple(attempts),
            tuple(verifications),
            tuple(oracle_results),
            revision_attempts,
            stop_reason,
            current.bundle_hash,
            tuple(oracle_failures),
            {"bundle_hash": current.bundle_hash, "parent_hash": current.parent_hash},
            tuple(submissions),
            tuple(stage_failures),
        )
        if self.journal is not None:
            sealed = self._dispatch(
                result_id, result_identity, result.to_dict, allow_after_auth=True, external=False
            )
            self.journal.record_result(result_id, sealed)
        return result


def _failure(stage: str, exc: Exception) -> str:
    if authentication_status(exc) is not None:
        return "authentication_failed"
    return (
        f"{stage}_result_unknown" if type(exc).__name__ == "UnknownOperation" else f"{stage}_failed"
    )


def _fatal_reason(stage: str, exc: Exception) -> str | None:
    if authentication_status(exc) is not None or is_credential_error(exc):
        return "authentication_failed"
    reason = getattr(exc, "reason", None)
    if (
        getattr(exc, "code", None) == "learning_timeout"
        or str(exc) == "skillsbench_learning_deadline_exhausted"
    ):
        return "learning_timeout"
    if type(exc).__name__ == "UnknownOperation" or reason == "generation_result_unknown":
        return f"{stage}_result_unknown"
    if reason in {
        "generator_turn_budget_exhausted",
        "generator_episode_budget_exhausted",
        "generator_context_budget_exhausted",
        "generator_output_budget_exhausted",
        "revision_timeout",
        "cleanup_failed",
        "learning_timeout",
    }:
        return reason
    if isinstance(exc, GeneratorContextBudgetExhausted):
        return "context_budget_exhausted"
    if str(exc) == "learning_timeout":
        return "learning_timeout"
    if "cleanup_failed" in str(exc):
        return "cleanup_failed"
    return None
