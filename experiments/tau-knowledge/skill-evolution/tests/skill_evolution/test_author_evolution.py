"""Released CoEvo branch contracts, without a provider or private grader."""

from collections import deque

import pytest
from tau_skill_evolution.artifacts import EvolutionSubmission, FrozenBase, SkillBundle
from tau_skill_evolution.evolution import EvolutionEngine, EvolutionResult, OracleUnavailable
from tau_skill_evolution.journal import Journal, UnknownOperation
from tau_skill_evolution.verifier import TestSuite, VerificationReport


class Session:
    def __init__(self, unchecked=()):
        self.unchecked = list(unchecked)
        self.rollbacks = []
        self.resets = 0
        self.invalid_schema = False
        self.snapshots = {}
        self.lose_snapshot = False

    def save_best_bundle(self, bundle, *, operation_id):
        self.snapshots[operation_id] = bundle
        return {
            "operation_id": operation_id,
            "bundle_hash": bundle.bundle_hash,
            "parent_hash": bundle.parent_hash,
        }

    def load_best_bundle(self, ref):
        return None if self.lose_snapshot else self.snapshots[ref["operation_id"]]

    def schema_issues(self, bundle):
        return ["name mismatch"] if self.invalid_schema else []

    def read_progress(self):
        return {"text": "public checklist", "unchecked": self.unchecked, "sha256": "fixture"}

    def reset_progress(self):
        self.resets += 1
        return self.read_progress()

    def rollback_bundle(self, bundle, *, operation_id):
        self.rollbacks.append(bundle.bundle_hash)
        return {"status": "ROLLED_BACK", "bundle_hash": bundle.bundle_hash}


class Verifier:
    def __init__(self, outcomes):
        self.outcomes = deque(outcomes)
        self.events = []

    def create_suite(self, inputs, base, trace, previous_tests=None, **kwargs):
        self.events.append(("generate", trace["bundle_hash"]))
        return TestSuite(
            {"tests/test_outputs.py": "def test_output(): assert 1 == 1"},
            version=0 if previous_tests is None else previous_tests.version + 1,
        )

    def verify(self, inputs, base, trace, suite, **kwargs):
        self.events.append(("verify", trace["bundle_hash"]))
        outcome = self.outcomes.popleft() if self.outcomes else False
        if isinstance(outcome, Exception):
            raise outcome
        return VerificationReport(suite, bool(outcome), 1.0 if outcome else 0.0)


def bundle(content="initial", parent=None):
    return SkillBundle({"SKILL.md": content}, parent_hash=parent)


def submission(value, *, initial=False):
    return EvolutionSubmission(value, {"events": []}, "learning", 0, initial)


def run(checks, rewards, *, session=None, journal=None, retries=15, revisions=None):
    first = bundle()
    session = session or Session()
    verifier = Verifier(checks)
    scores = deque(rewards)
    calls = []

    def oracle(value, *, phase):
        calls.append((phase, value.bundle_hash))
        outcome = scores.popleft()
        if isinstance(outcome, Exception):
            raise outcome
        return {
            "status": "MEASURED",
            "phase": phase,
            "passed": outcome == 1,
            "canonical_reward": outcome,
            "resolved_reward": outcome,
            "reward_source": "reward",
            "bundle_hash": value.bundle_hash,
            "parent_hash": value.parent_hash,
        }

    def revise(previous, inputs, base, report, *, feedback_history, **kwargs):
        assert all(
            set(item)
            <= {
                "kind",
                "base_hash",
                "bundle_hash",
                "passed",
                "call",
                "failure_categories",
                "verification_unavailable",
                "unchecked_phases",
                "public_schema_issues",
                "oracle_infrastructure_unavailable",
            }
            for item in feedback_history
        )
        value = (
            revisions(previous)
            if revisions
            else bundle(previous.files["SKILL.md"] + "+", previous.bundle_hash)
        )
        return submission(value)

    engine = EvolutionEngine(
        execute_initial=lambda value, *args, **kwargs: submission(value, initial=True),
        oracle=oracle,
        verifier=verifier,
        revise=revise,
        journal=journal,
        skillsbench_session=session,
        max_surrogate_retries=retries,
        max_revisions=None,
    )
    return engine.run({}, FrozenBase((), {}), first), verifier, session, calls


def test_oracle_rejection_returns_to_generator_before_test_upgrade():
    result, verifier, _, calls = run([True, True], [0.75, 1])
    assert result.revision_attempts == 1
    generations = [value for kind, value in verifier.events if kind == "generate"]
    assert len(generations) == 2 and generations[0] != generations[1]
    assert result.stop_reason == "oracle_success"
    assert [phase for phase, _ in calls] == ["normal", "normal"]


def test_r15_failure_cap_still_runs_terminal_oracle():
    result, _, _, calls = run([False] * 15, [0.25, 0.20])
    assert result.author_counters["surrogate_retries"] == 15
    assert [phase for phase, _ in calls] == ["cap_final", "post_final"]
    assert result.best_oracle_ref is not None
    assert result.author_terminal_result["resolved_reward"] == 0.25
    assert result.oracle_history[-1]["resolved_reward"] == 0.20


def test_four_normal_rejections_and_r15_can_run_six_physical_gt_checks():
    result, _, _, calls = run([True] * 4 + [False] * 15, [0.4, 0.3, 0.2, 0.1, 0.35, 0.3])
    assert [phase for phase, _ in calls] == ["normal"] * 4 + ["cap_final", "post_final"]
    assert result.author_counters["normal_oracle_interventions"] == 4
    assert result.oracle_calls == 6
    assert result.final_bundle_hash == result.versions[0].bundle_hash


def test_five_normal_gt_results_reuse_best_without_terminal_request():
    result, _, session, calls = run([True] * 5, [0.25, 0.75, 0.42, 0.75, 0.2])
    assert len(calls) == 5 and all(phase == "normal" for phase, _ in calls)
    assert result.final_bundle_hash == result.versions[1].bundle_hash
    assert session.rollbacks == [result.final_bundle_hash]
    assert result.best_oracle_ref["bundle_hash"] == result.final_bundle_hash
    assert result.selection_reason == "recorded_best_terminal"


def test_first_checklist_failure_counts_once_then_allows_gt():
    result, _, _, calls = run([True, True], [1], session=Session(["P6"]))
    assert result.author_counters["surrogate_retries"] == 1
    assert result.revision_attempts == 1 and len(calls) == 1
    assert result.author_counters["normal_oracle_interventions"] == 1


def test_program_errors_consume_r15_instead_of_local_one_repair_stop():
    result, _, _, calls = run([RuntimeError("locked run")] * 3, [1], retries=3)
    assert result.author_counters["surrogate_retries"] == 3
    assert result.stop_reason == "oracle_success"
    assert [phase for phase, _ in calls] == ["cap_final"]


def test_more_than_fifteen_revisions_are_not_a_local_m15_limit():
    result, _, _, _ = run([True] + [False] * 14, [0.25, 0.2, 0.1], retries=15)
    assert result.revision_attempts == 16  # One GT rejection plus fifteen surrogate interventions.
    assert result.author_counters["surrogate_retries"] == 15


def test_unknown_oracle_does_not_trigger_finalization_or_resend():
    result, _, _, calls = run([True], [UnknownOperation("sent")])
    assert len(calls) == 1 and result.oracle_calls == 0
    assert result.stop_reason == "oracle_result_unknown"
    assert result.best_oracle_ref is None


def test_consecutive_oracle_error_counter_resets_on_valid_outcome():
    result, _, _, calls = run(
        [True] * 4, [OracleUnavailable("infra"), 0.5, OracleUnavailable("infra"), 1]
    )
    assert len(calls) == 4
    assert result.author_counters["normal_oracle_interventions"] == 2
    assert result.author_counters["oracle_infrastructure_failures"] == 0
    assert len(result.oracle_failures) == 2


def test_schema_gate_precedes_best_rollback():
    session = Session()

    def revise(previous):
        session.invalid_schema = True
        return bundle("invalid schema", previous.bundle_hash)

    result, _, _, calls = run([True], [0.75], session=session, revisions=revise)
    assert len(calls) == 1 and not session.rollbacks
    assert result.best_oracle_ref is not None
    assert result.stop_reason == "skill_schema_invalid"
    assert result.selection_reason == "skill_schema_gate"


def test_sealed_best_selection_resumes_without_any_external_call(tmp_path):
    journal = Journal(tmp_path / "journal")
    result, _, _, calls = run([True] * 5, [0.7, 0.2, 0.1, 0.3, 0.4], journal=journal)
    assert len(calls) == 5
    restored = EvolutionEngine(
        execute_initial=lambda *a, **k: pytest.fail("sealed initial"),
        oracle=lambda *a, **k: pytest.fail("sealed oracle"),
        verifier=None,
        revise=lambda *a, **k: pytest.fail("sealed revision"),
        skillsbench_session=Session(),
        max_surrogate_retries=15,
        max_revisions=None,
        journal=journal,
    ).run({}, FrozenBase((), {}), result.versions[0])
    assert EvolutionResult.from_dict(restored.to_dict()).to_dict() == result.to_dict()


def test_content_reversion_retains_selected_observation_parent():
    sequence = deque(["middle", "initial", "later", "last"])
    result, _, _, _ = run(
        [True] * 5,
        [0.1, 0.2, 0.8, 0.3, 0.4],
        revisions=lambda prev: bundle(sequence.popleft(), prev.bundle_hash),
    )
    assert len(result.versions) == 4
    assert result.final_bundle_hash == result.versions[0].bundle_hash
    assert result.final_bundle.parent_hash == result.versions[1].bundle_hash
    assert result.versions[0].parent_hash is None


def test_unchanged_submission_records_actual_parent_without_new_content_version():
    result, _, _, _ = run(
        [False, True], [1], revisions=lambda prev: bundle(prev.files["SKILL.md"], prev.bundle_hash)
    )
    assert len(result.versions) == 1
    assert result.attempts[0]["status"] == "unchanged"
    assert result.final_bundle.parent_hash == result.versions[0].bundle_hash
    assert result.versions[0].parent_hash is None


def test_unknown_post_final_does_not_dispatch_rollback_or_another_gt():
    result, _, session, calls = run([False] * 3, [0.75, UnknownOperation("sent")], retries=3)
    assert len(calls) == 2
    assert result.stop_reason == "oracle_result_unknown"
    assert not session.rollbacks
    assert result.oracle_calls == 1


def test_missing_best_snapshot_keeps_score_but_does_not_claim_rollback():
    session = Session()
    session.lose_snapshot = True
    result, _, _, calls = run([True] * 5, [0.7, 0.2, 0.1, 0.3, 0.4], session=session)
    assert len(calls) == 5
    assert result.author_terminal_result["resolved_reward"] == 0.7
    assert result.final_bundle_hash == result.versions[-1].bundle_hash
    assert result.best_snapshot["record_available"] is True
    assert result.best_snapshot["snapshot_available"] is False
    assert result.best_snapshot["rollback"] is None and not session.rollbacks


def test_corrupted_best_snapshot_stops_without_scoring_or_claiming_rollback():
    session = Session()

    def broken(ref):
        raise ValueError("snapshot hash mismatch")

    session.load_best_bundle = broken
    result, _, _, calls = run([False] * 3, [0.75], session=session, retries=3)
    assert len(calls) == 1 and not session.rollbacks
    assert result.stop_reason == "best_snapshot_failed"
    assert result.best_snapshot["snapshot_available"] is False
    assert result.selection_reason == "best_snapshot_invalid"


def test_author_initial_minus_one_score_sentinel_does_not_create_best():
    result, _, session, calls = run([False] * 3, [-1, -2], session=Session(), retries=3)
    assert len(calls) == 2
    assert result.best_oracle_ref is None and not session.rollbacks
    assert result.author_terminal_result["resolved_reward"] == -2


def test_failed_rollback_preserves_actual_result_and_failure_evidence():
    session = Session()

    def broken(*args, **kwargs):
        raise RuntimeError("rollback failed")

    session.rollback_bundle = broken
    result, _, _, _ = run([True] * 5, [0.75, 0.4, 0.2, 0.1, 0.3], session=session)
    assert result.stop_reason == "rollback_failed"
    assert result.best_snapshot["rollback"]["status"] == "FAILED"
    assert result.author_terminal_result["resolved_reward"] == 0.75


def test_unknown_snapshot_save_does_not_start_another_gt_or_revision():
    session = Session()

    def unknown(*args, **kwargs):
        raise UnknownOperation("snapshot dispatched")

    session.save_best_bundle = unknown
    result, _, _, calls = run([True], [0.75], session=session)
    assert len(calls) == 1 and result.revision_attempts == 0
    assert result.stop_reason == "best_snapshot_result_unknown"


def test_invalid_test_upgrade_returns_to_unlocked_generation_without_repeat_adversarial_flag(
    monkeypatch,
):
    original = Verifier

    class UnlockedVerifier(original):
        generated = []

        def create_suite(self, *args, **kwargs):
            self.generated.append(kwargs.get("adversarial_recheck"))
            if len(self.generated) == 2:
                error = RuntimeError("nonempty invalid test script")
                error.source = "script_error"
                error.author_result = {"source": "script_error"}
                raise error
            return super().create_suite(*args, **kwargs)

    monkeypatch.setitem(run.__globals__, "Verifier", UnlockedVerifier)
    result, _, _, calls = run([True, True], [0.75, 1])
    assert UnlockedVerifier.generated == [False, True, False]
    assert len(calls) == 2 and result.revision_attempts == 2
    assert result.author_counters["surrogate_retries"] == 1
    assert any(item["trigger"] == "verifier_script_error" for item in result.interventions)
