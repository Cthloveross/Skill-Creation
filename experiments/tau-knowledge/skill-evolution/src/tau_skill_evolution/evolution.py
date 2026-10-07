"""Fixed-base Skill/test co-evolution; independent evaluation is never an input."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from typing import Any

from tau_skill_evolution.core._canonical import freeze_json, thaw_json

from .artifacts import EvolutionSubmission, SkillBundle
from .generator import GeneratorContextBudgetExhausted, public_feedback_history
from .model import ModelClientError, authentication_status, is_credential_error
from .verifier import TestSuite, VerificationReport, _stage_failure


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

    def __post_init__(self) -> None:
        object.__setattr__(self, "stage_failures", freeze_json(self.stage_failures))
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
                or parent == self.final_bundle_hash
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
        )


class EvolutionEngine:
    def __init__(
        self,
        *,
        execute_initial: Callable[..., EvolutionSubmission],
        oracle: Callable[[SkillBundle], bool],
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
            or isinstance(max_oracles, bool)
            or not isinstance(max_oracles, int)
            or not 0 <= max_revisions <= 15
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
        # A derived result can still be sealed; no subsequent external operation may start.
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
        versions = [initial_bundle]
        current = initial_bundle
        attempts: list[Mapping[str, Any]] = []
        verifications: list[Mapping[str, Any]] = []
        oracle_results: list[bool] = []
        oracle_failures: list[Mapping[str, Any]] = []
        feedback_history: list[Mapping[str, Any]] = []
        revision_attempts = 0
        suite: TestSuite | None = None
        turn = 0
        stop_reason = ""
        submissions: list[Mapping[str, Any]] = []
        stage_failures: list[Mapping[str, Any]] = []

        def retain_submission(submission: EvolutionSubmission) -> None:
            submissions.append(
                {
                    "submission_hash": submission.submission_hash,
                    "trace_hash": submission.trace_hash,
                    "bundle_hash": submission.bundle.bundle_hash,
                    "parent_hash": submission.bundle.parent_hash,
                    "execution_id": submission.execution_id,
                    "operation_cursor": submission.operation_cursor,
                    "initial": submission.initial,
                }
            )

        try:
            authentication = self._authentication_status()
            if authentication is not None:
                raise ModelClientError(
                    "authentication_failed",
                    "evolution authentication failed",
                    status=authentication,
                )
            submission = self.execute_initial(
                initial_bundle,
                public_inputs,
                frozen_base,
                operation_id=f"{operation_prefix}-initial-execution",
            )
            submission = EvolutionSubmission.from_dict(submission.to_dict())
            if not submission.initial or submission.bundle.to_dict() != initial_bundle.to_dict():
                raise ValueError("initial_execution_modified_bundle")
            trace = thaw_json(submission.public_trace)
            retain_submission(submission)
        except Exception as exc:
            if is_credential_error(exc):
                raise
            stage_failures.append(
                _stage_failure("initial_execution", f"{operation_prefix}-initial-execution", exc)
            )
            stop_reason = getattr(exc, "reason", None) or _failure("initial_execution", exc)
            trace = {}
        # Deterministic operation IDs permit replay of sealed phase results after interruption.
        while not stop_reason:
            if self._authentication_status() is not None:
                stop_reason = "authentication_failed"
                break
            prefix = f"{operation_prefix}-turn-{turn}"
            if self._authentication_status() is not None:
                stop_reason = "authentication_failed"
                break
            if suite is None:
                try:
                    suite = self.verifier.create_suite(
                        public_inputs, frozen_base, trace, operation_id=f"{prefix}-suite"
                    )
                except Exception as exc:
                    stage_failures.append(
                        _stage_failure("verifier_initialization", f"{prefix}-suite", exc)
                    )
                    stop_reason = _failure("verifier_initialization", exc)
                    break
            if self._authentication_status() is not None:
                stop_reason = "authentication_failed"
                break
            try:
                report: VerificationReport = self.verifier.verify(
                    public_inputs, frozen_base, trace, suite, operation_id=f"{prefix}-verify"
                )
            except Exception as exc:
                stage_failures.append(_stage_failure("verification", f"{prefix}-verify", exc))
                stop_reason = _failure("verification", exc)
                break
            suite = report.suite
            stage_failures.extend(report.stage_failures)
            verifications.append(
                {
                    **submissions[-1],
                    **report.to_dict(),
                }
            )
            feedback_history.extend(
                public_feedback_history(
                    [
                        {
                            "kind": "verification",
                            "base_hash": frozen_base.base_hash,
                            "bundle_hash": current.bundle_hash,
                            **report.to_dict(),
                        }
                    ],
                    frozen_base.base_hash,
                )
            )
            if self._authentication_status() is not None:
                stop_reason = "authentication_failed"
                break
            if report.program_error:
                stop_reason = "verification_program_error_exhausted"
                break
            if report.passed:
                if len(oracle_results) >= self.max_oracles:
                    stop_reason = "oracle_budget_exhausted"
                    break

                def call_oracle(current: SkillBundle = current) -> dict[str, Any]:
                    try:
                        passed = self.oracle(current)
                    except Exception as exc:
                        if isinstance(exc, OracleUnavailable) or getattr(
                            exc, "response_received", False
                        ):
                            return {"status": "NOT_MEASURED", "reason": type(exc).__name__}
                        raise
                    if not isinstance(passed, bool):
                        raise TypeError("oracle_must_return_pass_fail_only")
                    return {"status": "MEASURED", "passed": passed}

                while True:
                    oracle_id = f"{prefix}-oracle"
                    if oracle_failures:
                        oracle_id += f"-infrastructure-{len(oracle_failures)}"
                    try:
                        outcome = self._dispatch(
                            oracle_id, {"bundle_hash": current.bundle_hash}, call_oracle
                        )
                    except Exception as exc:
                        stage_failures.append(_stage_failure("oracle", oracle_id, exc))
                        stop_reason = _failure("oracle", exc)
                        break
                    if outcome["status"] == "MEASURED":
                        oracle_pass = outcome["passed"]
                        break
                    oracle_failures.append({"operation_id": oracle_id, **outcome})
                    if len(oracle_failures) >= self.max_oracle_errors:
                        stop_reason = "oracle_infrastructure_unavailable"
                        break
                if stop_reason:
                    break
                if self._authentication_status() is not None:
                    stop_reason = "authentication_failed"
                    break
                oracle_results.append(oracle_pass)
                feedback_history.append(
                    {
                        "kind": "oracle",
                        "base_hash": frozen_base.base_hash,
                        "bundle_hash": current.bundle_hash,
                        "passed": oracle_pass,
                        "call": len(oracle_results),
                    }
                )
                if oracle_pass:
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
                    stage_failures.append(
                        _stage_failure("test_escalation", f"{prefix}-escalate", exc)
                    )
                    stop_reason = _failure("test_escalation", exc)
                    break
                # Upgraded checks examine the same immutable submitted observation.
                turn += 1
                continue
            if revision_attempts >= self.max_revisions:
                stop_reason = "revision_budget_exhausted"
                break
            revision_attempts += 1
            operation_id = f"{operation_prefix}-revision-{revision_attempts}"
            attempt: dict[str, Any] = {
                "attempt": revision_attempts,
                "parent_hash": current.bundle_hash,
                "test_version": suite.version,
                "test_hash": suite.test_hash,
            }
            try:
                # Generator owns its raw model journal, so recovering a received response
                # still seals the same package without making another generation request.
                submission = self.revise(
                    current,
                    public_inputs,
                    frozen_base,
                    report,
                    operation_id=operation_id,
                    public_trace=trace,
                    feedback_history=tuple(
                        public_feedback_history(feedback_history, frozen_base.base_hash)
                    ),
                )
                submission = EvolutionSubmission.from_dict(submission.to_dict())
                if submission.initial:
                    raise ValueError("revision_submission_has_initial_phase")
                candidate = submission.bundle
                if candidate.parent_hash != current.bundle_hash:
                    raise ValueError("revision_parent_mismatch")
                attempt["bundle_hash"] = candidate.bundle_hash
                attempt["submission_hash"] = submission.submission_hash
                trace = thaw_json(submission.public_trace)
                retain_submission(submission)
                if candidate.bundle_hash == current.bundle_hash:
                    attempt["status"] = "unchanged"
                else:
                    attempt["status"] = "changed"
                    current = candidate
                    if all(item.bundle_hash != candidate.bundle_hash for item in versions):
                        versions.append(candidate)
            except GeneratorContextBudgetExhausted as exc:
                stage_failures.append(_stage_failure("revision", operation_id, exc))
                # Admission rejected before a model dispatch: no invalid package or retry.
                revision_attempts -= 1
                stop_reason = "context_budget_exhausted"
                break
            except Exception as exc:
                if is_credential_error(exc):
                    # Nothing was dispatched; abort without consuming an attempt.
                    raise
                stage_failures.append(_stage_failure("revision", operation_id, exc))
                attempt["status"] = "invalid"
                attempt["failure"] = type(exc).__name__
                if getattr(exc, "dispatched", True) is False:
                    revision_attempts -= 1
                    attempt["status"] = "not_sent"
                    stop_reason = getattr(exc, "reason", "revision_unavailable")
                elif getattr(exc, "reason", None) in {
                    "generator_turn_budget_exhausted",
                    "generator_context_budget_exhausted",
                    "generator_output_budget_exhausted",
                    "revision_timeout",
                    "cleanup_failed",
                }:
                    stop_reason = exc.reason
                if (
                    authentication_status(exc) is not None
                    or self._authentication_status() is not None
                ):
                    attempt["status"] = "authentication_failed"
                    stop_reason = "authentication_failed"
                elif (
                    type(exc).__name__ == "UnknownOperation"
                    or getattr(exc, "reason", None) == "generation_result_unknown"
                ):
                    attempt["status"] = "result_unknown"
                    stop_reason = "revision_result_unknown"
            attempts.append(attempt)
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
                result_id,
                result_identity,
                result.to_dict,
                allow_after_auth=True,
            )
            self.journal.record_result(result_id, sealed)
        return result


def _failure(stage: str, exc: Exception) -> str:
    if authentication_status(exc) is not None:
        return "authentication_failed"
    return (
        f"{stage}_result_unknown" if type(exc).__name__ == "UnknownOperation" else f"{stage}_failed"
    )
