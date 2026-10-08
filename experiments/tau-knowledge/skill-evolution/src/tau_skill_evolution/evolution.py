"""Fixed-base Skill/test co-evolution; independent evaluation is never an input."""

from __future__ import annotations

import math
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
        max_revisions: int | None = 15,
        max_oracles: int = 5,
        max_oracle_errors: int = 5,
        skillsbench_session: Any | None = None,
        max_surrogate_retries: int = 15,
    ) -> None:
        if (
            (
                max_revisions is not None
                and (
                    isinstance(max_revisions, bool)
                    or not isinstance(max_revisions, int)
                    or not 0 <= max_revisions <= 15
                )
            )
            or (skillsbench_session is None and max_revisions is None)
            or isinstance(max_oracles, bool)
            or not isinstance(max_oracles, int)
            or not 0 <= max_oracles <= 5
            or isinstance(max_oracle_errors, bool)
            or not isinstance(max_oracle_errors, int)
            or not 0 <= max_oracle_errors <= 5
            or isinstance(max_surrogate_retries, bool)
            or not isinstance(max_surrogate_retries, int)
            or not 0 <= max_surrogate_retries <= 15
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
        self.skillsbench_session = skillsbench_session
        self.max_surrogate_retries = max_surrogate_retries

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
        author = self.skillsbench_session is not None
        result_id = f"{operation_prefix}-result"
        result_identity = {
            "result_format": 4 if author else 3,
            "initial_bundle_hash": initial_bundle.bundle_hash,
            "base_hash": frozen_base.base_hash,
            "max_revisions": self.max_revisions,
            "max_oracles": self.max_oracles,
            "max_oracle_errors": self.max_oracle_errors,
            **({"max_surrogate_retries": self.max_surrogate_retries} if author else {}),
        }
        if self.journal is not None and self.journal.completed(result_id):
            return EvolutionResult.from_dict(
                self._dispatch(result_id, result_identity, lambda: None, allow_after_auth=True)
            )
        versions, current = [initial_bundle], initial_bundle
        attempts, verifications, oracle_results, oracle_failures = [], [], [], []
        feedback_history, submissions, stage_failures = [], [], []
        oracle_history, interventions = [], []
        counters = {
            "surrogate_retries": 0,
            "normal_oracle_interventions": 0,
            "oracle_infrastructure_failures": 0,
            "checklist_fail_count": 0,
        }
        best = None
        snapshot_ref = None
        snapshot_available = None
        rollback_result = None
        terminal_result = None
        selection_reason = "last_safe_bundle"
        revision_attempts = turn = schema_fixes = 0
        suite = None
        suite_locked = False
        regenerate = False
        stop_reason = ""

        def control(operation_id, payload, callback):
            return self._dispatch(operation_id, payload, callback, external=False)

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
            remaining = getattr(self.skillsbench_session, "phase_remaining", None)
            if remaining is not None and remaining() <= 0:
                return "learning_timeout"
            return None

        def intervention(trigger, *, retry=False):
            if retry:
                counters["surrogate_retries"] += 1
            event = {
                "trigger": trigger,
                "counters": dict(counters),
                "submission_hash": submissions[-1]["submission_hash"],
                "bundle_hash": current.bundle_hash,
                "test_hash": suite.test_hash if suite is not None else None,
            }
            operation = f"{operation_prefix}-intervention-{len(interventions)}"
            interventions.append(control(operation, event, lambda: event))

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
            if not author and revision_attempts >= self.max_revisions:
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
                    if author:
                        current = candidate
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
                elif author:
                    # Parser and safe-submit corrections happen inside the Generator.
                    # A failed call does not synthesize another task_complete event.
                    stop_reason = getattr(exc, "reason", None) or "revision_failed"
            attempts.append(attempt)
            turn += 1

        def official(value, phase, operation):
            nonlocal best, stop_reason, snapshot_ref, snapshot_available
            if guard():
                stop_reason = guard()
                return None

            def call():
                try:
                    outcome = self.oracle(value, phase=phase) if author else self.oracle(value)
                except Exception as exc:
                    if _fatal_reason("oracle", exc):
                        raise
                    if isinstance(exc, OracleUnavailable) or getattr(
                        exc, "response_received", False
                    ):
                        return {"status": "NOT_MEASURED", "reason": type(exc).__name__}
                    raise
                if not author:
                    if not isinstance(outcome, bool):
                        raise TypeError("oracle_must_return_pass_fail_only")
                    return {"status": "MEASURED", "passed": outcome}
                return _validate_author_oracle(outcome, value, phase)

            try:
                outcome = self._dispatch(
                    operation,
                    {
                        "bundle_hash": value.bundle_hash,
                        **({"parent_hash": value.parent_hash, "phase": phase} if author else {}),
                    },
                    call,
                )
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
            if author:
                oracle_history.append(entry)
            if outcome["status"] != "MEASURED":
                oracle_failures.append(entry)
                return outcome
            oracle_results.append(outcome["passed"])
            if (
                author
                and phase != "post_final"
                and outcome["resolved_reward"] > (best[1]["resolved_reward"] if best else -1)
            ):
                best = (value, entry)
                snapshot_ref, snapshot_available = None, False
                try:
                    snapshot_ref = control(
                        operation + "-best-snapshot",
                        {
                            "bundle_hash": value.bundle_hash,
                            "parent_hash": value.parent_hash,
                        },
                        lambda: self.skillsbench_session.save_best_bundle(
                            value, operation_id=operation + "-snapshot-package"
                        ),
                    )
                    snapshot_available = True
                except Exception as exc:
                    stage_failures.append(_stage_failure("best_snapshot", operation, exc))
                    fatal = _fatal_reason("best_snapshot", exc)
                    if fatal:
                        stop_reason = fatal
            if phase == "normal":
                feedback_history.append(
                    {
                        "kind": "oracle",
                        "base_hash": frozen_base.base_hash,
                        "bundle_hash": value.bundle_hash,
                        "passed": outcome["passed"],
                        "call": counters["normal_oracle_interventions"]
                        if author
                        else len(oracle_results),
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
            if author:
                issues = self.skillsbench_session.schema_issues(current)
                if issues:
                    schema_fixes += 1
                    intervention("skill_schema_invalid")
                    if schema_fixes > 2:
                        stop_reason = "skill_schema_invalid"
                        break
                    report = {
                        "passed": False,
                        "failure_categories": ["artifact/interface compliance"],
                        "public_schema_issues": issues,
                    }
                    feedback(report)
                    revise_current(report)
                    continue
                schema_fixes = 0
                cap_hit = counters["normal_oracle_interventions"] >= self.max_oracles
                retry_hit = counters["surrogate_retries"] >= self.max_surrogate_retries
                if cap_hit or retry_hit:
                    stop_reason = "max_interventions" if cap_hit else "max_surrogate_retries"
                    intervention("max_interventions")
                    if not (cap_hit and best is not None):
                        reason = stop_reason
                        stop_reason = ""
                        outcome = official(current, "cap_final", f"{prefix}-cap-final")
                        terminal_result = outcome
                        stop_reason = stop_reason or (
                            "oracle_success"
                            if outcome and outcome.get("passed") is True
                            else reason
                        )
                    break

            if suite is None or regenerate or (author and not suite_locked):
                operation = f"{prefix}-escalate" if regenerate else f"{prefix}-suite"
                try:
                    suite = self.verifier.create_suite(
                        public_inputs,
                        frozen_base,
                        trace,
                        **({"previous_tests": suite} if suite is not None else {}),
                        **({"adversarial_recheck": regenerate} if author else {}),
                        operation_id=operation,
                    )
                    regenerate = False
                    suite_locked = True
                except Exception as exc:
                    stage_failures.append(_stage_failure("verifier_initialization", operation, exc))
                    fatal = _fatal_reason("verification", exc)
                    if author and not fatal:
                        suite_locked = False
                        if getattr(exc, "author_result", None) is not None:
                            regenerate = False
                        source = getattr(exc, "source", "verifier_generation_error")
                        intervention(
                            "verifier_" + source
                            if source in {"no_script", "script_error"}
                            else "verifier_exception",
                            retry=True,
                        )
                        report = {
                            "passed": False,
                            "verification_unavailable": source
                            if source in {"no_script", "script_error"}
                            else "verifier_generation_error",
                        }
                        feedback(report)
                        revise_current(report)
                        continue
                    stop_reason = fatal or _failure("verifier_initialization", exc)
                    break
            try:
                report = self.verifier.verify(
                    public_inputs, frozen_base, trace, suite, operation_id=f"{prefix}-verify"
                )
            except Exception as exc:
                stage_failures.append(_stage_failure("verification", f"{prefix}-verify", exc))
                fatal = _fatal_reason("verification", exc)
                if author and not fatal:
                    intervention("locked_rerun_exception", retry=True)
                    report = {"passed": False, "verification_unavailable": "verifier_runtime_error"}
                    feedback(report)
                    revise_current(report)
                    continue
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
                if not author:
                    stop_reason = "verification_program_error_exhausted"
                    break
                source = (getattr(report, "author_result", None) or {}).get(
                    "source", "script_error"
                )
                intervention("locked_" + source, retry=True)
                revise_current(
                    {
                        "passed": False,
                        "verification_unavailable": source
                        if source in {"script_error", "no_script"}
                        else "verifier_runtime_error",
                    }
                )
                continue
            if not report.passed:
                if author:
                    intervention(
                        "surrogate_fail"
                        if (report.author_result or {}).get("tests_failed", 0) > 0
                        or any(
                            str(item.get("outcome", item.get("status", ""))).upper() == "FAILED"
                            for item in report.results
                        )
                        else "surrogate_incomplete",
                        retry=True,
                    )
                    control(
                        f"{prefix}-reset-progress",
                        {"bundle_hash": current.bundle_hash},
                        self.skillsbench_session.reset_progress,
                    )
                revise_current(report)
                continue

            if author:
                progress = control(
                    f"{prefix}-progress",
                    {"bundle_hash": current.bundle_hash},
                    self.skillsbench_session.read_progress,
                )
                if progress["unchecked"]:
                    counters["checklist_fail_count"] += 1
                    if counters["checklist_fail_count"] == 1:
                        intervention("surrogate_pass_checklist_fail", retry=True)
                        revise_current({"passed": True, "unchecked_phases": progress["unchecked"]})
                        continue
                else:
                    counters["checklist_fail_count"] = 0
                counters["normal_oracle_interventions"] += 1
                intervention(
                    "surrogate_pass_checklist_incomplete"
                    if progress["unchecked"]
                    else "surrogate_pass"
                )
            elif len(oracle_results) >= self.max_oracles:
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
                if author:
                    counters["normal_oracle_interventions"] -= 1
                    counters["oracle_infrastructure_failures"] += 1
                    if counters["oracle_infrastructure_failures"] >= self.max_oracle_errors:
                        stop_reason = "gt_infrastructure_unavailable"
                    else:
                        revise_current({"passed": True, "oracle_infrastructure_unavailable": True})
                    break
                if len(oracle_failures) >= self.max_oracle_errors:
                    stop_reason = "oracle_infrastructure_unavailable"
                    break
            if stop_reason:
                break
            if outcome["status"] != "MEASURED":
                continue
            if author:
                counters["oracle_infrastructure_failures"] = 0
                terminal_result = outcome
            if outcome["passed"]:
                stop_reason = "oracle_success"
                break
            if author:
                counters["checklist_fail_count"] = 0
                regenerate = True
                suite_locked = False
                revise_current(report)
            else:
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

        # Released post-execution priority: schema gate, exhausted K, last success,
        # then fresh best-snapshot/current oracle. Actual results are never overwritten.
        if author and submissions and _can_finalize(stop_reason) and not guard():
            issues = self.skillsbench_session.schema_issues(current)
            selected_best = None
            snapshot_failure = None
            if not issues and snapshot_ref is not None:
                try:
                    loaded = control(
                        f"{operation_prefix}-load-best",
                        snapshot_ref,
                        lambda: (
                            value.to_dict()
                            if (value := self.skillsbench_session.load_best_bundle(snapshot_ref))
                            is not None
                            else None
                        ),
                    )
                    selected_best = SkillBundle.from_dict(loaded) if loaded is not None else None
                    snapshot_available = selected_best is not None
                except Exception as exc:
                    snapshot_available = False
                    snapshot_failure = failed("best_snapshot", f"{operation_prefix}-load-best", exc)
            if issues:
                stop_reason = "skill_schema_invalid"
                selection_reason = "skill_schema_gate"
                terminal_result = {
                    "status": "NOT_MEASURED",
                    "source": "skill_schema_gate",
                    "passed": False,
                    "schema_issues": issues,
                }
            elif snapshot_failure:
                stop_reason = snapshot_failure
                selection_reason = "best_snapshot_invalid"
            elif counters["normal_oracle_interventions"] >= self.max_oracles and best is not None:
                if selected_best is not None:
                    current = selected_best
                terminal_result = {**best[1], "source": "recorded_best_terminal"}
                selection_reason = "recorded_best_terminal"
            elif terminal_result and terminal_result.get("passed") is True:
                selection_reason = "oracle_success"
            else:
                selected = selected_best if selected_best is not None else current
                fresh = official(selected, "post_final", f"{operation_prefix}-post-final")
                if fresh is not None:
                    terminal_result = fresh
                if selected_best is not None:
                    current = selected_best
                    selection_reason = "best_snapshot"
                    if (
                        fresh is None
                        or fresh.get("status") != "MEASURED"
                        or (fresh["resolved_reward"] < best[1]["resolved_reward"])
                    ):
                        terminal_result = {**best[1], "source": "best_snapshot"}
                elif fresh is not None and fresh.get("status") == "MEASURED":
                    selection_reason = "final_current"
                elif fresh is not None and best is not None:
                    terminal_result = {**best[1], "source": "recorded_best_without_snapshot"}
                if fresh is not None and fresh.get("passed") is True:
                    stop_reason = "oracle_success"
            if (
                selection_reason in {"best_snapshot", "recorded_best_terminal"}
                and selected_best is not None
                and _can_finalize(stop_reason)
                and not guard()
            ):
                try:
                    rollback_result = control(
                        f"{operation_prefix}-rollback",
                        {
                            "bundle_hash": current.bundle_hash,
                            "parent_hash": current.parent_hash,
                        },
                        lambda: self.skillsbench_session.rollback_bundle(
                            current, operation_id=f"{operation_prefix}-rollback-package"
                        ),
                    )
                except Exception as exc:
                    stop_reason = failed("rollback", f"{operation_prefix}-rollback", exc)
                    selection_reason = "rollback_failed"
                    rollback_result = {"status": "FAILED", "reason": stop_reason}

        if author:
            conversation = getattr(self.skillsbench_session, "generator_conversation", None)
            if conversation is not None:
                counters.update(
                    generator_episodes=conversation.episodes,
                    generator_model_responses=conversation.turns,
                )
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
            dict(counters) if author else None,
            tuple(oracle_history),
            {key: best[1][key] for key in ("operation_id", "bundle_hash", "parent_hash")}
            if best is not None
            else None,
            terminal_result,
            selection_reason if author else None,
            tuple(interventions),
            {
                "record_available": best is not None,
                "snapshot_available": snapshot_available,
                "reference": snapshot_ref,
                "rollback": rollback_result,
            }
            if author
            else None,
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


def _can_finalize(reason: str) -> bool:
    return not (
        reason.endswith("result_unknown")
        or reason in {"authentication_failed", "cleanup_failed", "learning_timeout"}
        or reason.startswith("initial_execution")
    )


def _validate_author_oracle(outcome: Any, bundle: SkillBundle, phase: str) -> dict[str, Any]:
    if not isinstance(outcome, Mapping) or outcome.get("status") not in {
        "MEASURED",
        "NOT_MEASURED",
    }:
        raise TypeError("invalid_author_oracle_result")
    value = thaw_json(outcome)
    if value["status"] == "MEASURED":
        reward = value.get("resolved_reward")
        if (
            isinstance(reward, bool)
            or not isinstance(reward, (int, float))
            or not math.isfinite(reward)
            or type(value.get("passed")) is not bool
            or value["passed"] != (reward == 1.0)
            or value.get("bundle_hash") != bundle.bundle_hash
            or value.get("parent_hash") != bundle.parent_hash
            or value.get("phase") != phase
        ):
            raise ValueError("inconsistent_author_oracle_result")
    return value
