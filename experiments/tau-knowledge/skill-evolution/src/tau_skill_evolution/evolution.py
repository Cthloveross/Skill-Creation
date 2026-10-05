"""Fixed-base Skill/test co-evolution; independent evaluation is never an input."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from .artifacts import SkillBundle
from .generator import GeneratorContextBudgetExhausted, public_feedback_history
from .model import ModelClientError, authentication_status, is_credential_error
from .verifier import TestSuite, VerificationReport


@dataclass(frozen=True)
class EvolutionResult:
    versions: tuple[SkillBundle, ...]
    attempts: tuple[Mapping[str, Any], ...]
    verifications: tuple[Mapping[str, Any], ...]
    oracle_results: tuple[bool, ...]
    revision_attempts: int
    stop_reason: str
    final_bundle_hash: str

    @property
    def oracle_calls(self) -> int:
        return len(self.oracle_results)

    @property
    def final_bundle(self) -> SkillBundle:
        return next(
            bundle for bundle in self.versions if bundle.bundle_hash == self.final_bundle_hash
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
        )


class EvolutionEngine:
    def __init__(
        self,
        *,
        rollout: Callable[[SkillBundle], Mapping[str, Any]],
        oracle: Callable[[SkillBundle], bool],
        verifier: Any,
        revise: Callable[..., SkillBundle],
        journal: Any | None = None,
        max_revisions: int = 15,
        max_oracles: int = 5,
    ) -> None:
        if (
            isinstance(max_revisions, bool)
            or not isinstance(max_revisions, int)
            or isinstance(max_oracles, bool)
            or not isinstance(max_oracles, int)
            or not 0 <= max_revisions <= 15
            or not 0 <= max_oracles <= 5
        ):
            raise ValueError("evolution budgets exceed protocol")
        self.rollout = rollout
        self.oracle = oracle
        self.verifier = verifier
        self.revise = revise
        self.journal = journal
        self.max_revisions = max_revisions
        self.max_oracles = max_oracles

    def _dispatch(
        self,
        operation_id: str,
        payload: Mapping[str, Any],
        callback: Any,
        *,
        allow_after_auth: bool = False,
    ) -> Any:
        # A derived result can still be sealed; no subsequent external operation may start.
        status = self._authentication_status()
        if status is not None and not allow_after_auth:
            raise ModelClientError(
                "authentication_failed", "evolution authentication failed", status=status
            )
        return (
            self.journal.dispatch(operation_id, payload, callback)
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
            "initial_bundle_hash": initial_bundle.bundle_hash,
            "base_hash": frozen_base.base_hash,
            "max_revisions": self.max_revisions,
            "max_oracles": self.max_oracles,
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
        feedback_history: list[Mapping[str, Any]] = []
        revision_attempts = 0
        suite: TestSuite | None = None
        turn = 0
        stop_reason = ""
        # Deterministic operation IDs permit replay of sealed phase results after interruption.
        while not stop_reason:
            if self._authentication_status() is not None:
                stop_reason = "authentication_failed"
                break
            prefix = f"{operation_prefix}-turn-{turn}"
            try:
                trace = self._dispatch(
                    f"{prefix}-rollout",
                    {"bundle_hash": current.bundle_hash},
                    lambda current=current: dict(self.rollout(current)),
                )
            except Exception as exc:
                stop_reason = _failure("rollout", exc)
                break
            if self._authentication_status() is not None:
                stop_reason = "authentication_failed"
                break
            if suite is None:
                try:
                    suite = self.verifier.create_suite(
                        public_inputs, frozen_base, trace, operation_id=f"{prefix}-suite"
                    )
                except Exception as exc:
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
                stop_reason = _failure("verification", exc)
                break
            suite = report.suite
            verifications.append({"bundle_hash": current.bundle_hash, **report.to_dict()})
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
                try:
                    oracle_pass = self._dispatch(
                        f"{prefix}-oracle",
                        {"bundle_hash": current.bundle_hash},
                        lambda current=current: self.oracle(current),
                    )
                    if not isinstance(oracle_pass, bool):
                        raise TypeError("oracle_must_return_pass_fail_only")
                except Exception as exc:
                    stop_reason = _failure("oracle", exc)
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
                    stop_reason = _failure("test_escalation", exc)
                    break
                # New checks receive a fresh execution of the same Skill before any revision.
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
                candidate = self.revise(
                    current,
                    public_inputs,
                    frozen_base,
                    report,
                    operation_id=operation_id,
                    feedback_history=tuple(
                        public_feedback_history(feedback_history, frozen_base.base_hash)
                    ),
                )
                candidate = SkillBundle.from_dict(candidate.to_dict())
                if candidate.parent_hash != current.bundle_hash:
                    raise ValueError("revision_parent_mismatch")
                attempt["bundle_hash"] = candidate.bundle_hash
                if candidate.bundle_hash == current.bundle_hash:
                    attempt["status"] = "unchanged"
                else:
                    attempt["status"] = "changed"
                    current = candidate
                    if all(item.bundle_hash != candidate.bundle_hash for item in versions):
                        versions.append(candidate)
            except GeneratorContextBudgetExhausted:
                # Admission rejected before a model dispatch: no invalid package or retry.
                revision_attempts -= 1
                stop_reason = "context_budget_exhausted"
                break
            except Exception as exc:
                if is_credential_error(exc):
                    # Nothing was dispatched; abort without consuming an attempt.
                    raise
                attempt["status"] = "invalid"
                attempt["failure"] = type(exc).__name__
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
