import pytest
from tau_skill_evolution.artifacts import EvolutionSubmission, FrozenBase, SkillBundle
from tau_skill_evolution.container import ProgramResult
from tau_skill_evolution.evolution import EvolutionEngine, EvolutionResult, OracleUnavailable
from tau_skill_evolution.generator import (
    CreationFailure,
    GeneratorContextBudgetExhausted,
    RevisionFailure,
)
from tau_skill_evolution.journal import Journal, UnknownOperation
from tau_skill_evolution.model import ModelClientError
from tau_skill_evolution.verifier import SurrogateVerifier, TestSuite, VerificationReport


class Verifier:
    def __init__(self, outcomes):
        self.outcomes = iter(outcomes)
        self.checks = []
        self.escalations = []

    def create_suite(self, inputs, base, trace, previous_tests=None, **kwargs):
        if previous_tests is None:
            return TestSuite({"tests/test_initial.py": "def test_initial(): assert True"})
        self.escalations.append(previous_tests)
        addition = f"tests/test_upgrade_{previous_tests.version + 1}.py"
        return TestSuite(
            {
                **previous_tests.files,
                addition: "def test_new(): assert True",
            },
            version=previous_tests.version + 1,
        )

    def verify(self, inputs, base, trace, previous_tests, **kwargs):
        self.checks.append((trace["bundle_hash"], previous_tests.test_hash))
        passed = next(self.outcomes)
        return VerificationReport(previous_tests, passed, 1 if passed else 0)


def _submission(bundle, trace=None, *, initial=False, execution_id="learning-episode", cursor=0):
    return EvolutionSubmission(bundle, trace or {"events": []}, execution_id, cursor, initial)


def _initial_submission(bundle, *args, **kwargs):
    return _submission(bundle, initial=True)


def run(outcomes, oracles, revise, **kwargs):
    initial = SkillBundle({"SKILL.md": "initial"})
    traces, oracle_hashes = [], []
    verifier = Verifier(outcomes)
    kwargs.setdefault("max_revisions", 4)
    oracle_values = iter(oracles)

    def execute_initial(bundle, *args, **options):
        assert options["operation_id"] == "evolution-initial-execution"
        traces.append(bundle.bundle_hash)
        return _submission(bundle, initial=True)

    def submit_revision(*args, **options):
        submission = revise(*args, **options)
        assert isinstance(submission, EvolutionSubmission)
        traces.append(submission.bundle.bundle_hash)
        return submission

    def oracle(bundle):
        oracle_hashes.append(bundle.bundle_hash)
        return next(oracle_values)

    result = EvolutionEngine(
        execute_initial=execute_initial,
        oracle=oracle,
        verifier=verifier,
        revise=submit_revision,
        **kwargs,
    ).run({}, FrozenBase((), {}), initial)
    return result, verifier, traces, oracle_hashes


def revised(previous, *args, **kwargs):
    return _submission(
        SkillBundle(
            {"SKILL.md": previous.files["SKILL.md"] + " updated"}, parent_hash=previous.bundle_hash
        ),
        cursor=1,
    )


def test_failure_revises_parent_and_tests_stay_fixed_then_early_stops():
    result, verifier, traces, oracle_hashes = run([False, True], [True], revised)
    assert result.stop_reason == "oracle_success"
    assert result.revision_attempts == 1 and result.oracle_calls == 1
    assert len(result.versions) == 2 and len(traces) == 2 and len(oracle_hashes) == 1
    assert verifier.checks[0][1] == verifier.checks[1][1]
    assert result.versions[1].parent_hash == result.versions[0].bundle_hash
    for report, submission in zip(result.verifications, result.submissions, strict=True):
        assert report["submission_hash"] == submission["submission_hash"]
        assert report["trace_hash"] == submission["trace_hash"]
        assert report["execution_id"] == submission["execution_id"]
        assert report["operation_cursor"] == submission["operation_cursor"]
    assert EvolutionResult.from_dict(result.to_dict()).to_dict() == result.to_dict()


def test_revision_receives_current_public_execution_without_verifier_evidence():
    observations = []

    def revise(previous, *args, public_trace, feedback_history, **kwargs):
        observations.append(public_trace)
        assert public_trace["bundle_hash"] == previous.bundle_hash
        assert all("diagnosis" not in item and "suite" not in item for item in feedback_history)
        return revised(previous)

    result, _, traces, _ = run([False, False, True], [True], revise)
    assert [trace["bundle_hash"] for trace in observations] == traces[:2]
    assert len(result.versions) == 3 and result.oracle_calls == 1


def test_oracle_fail_upgrades_checks_against_same_submitted_observation_before_revision():
    result, verifier, traces, oracle_hashes = run([True, False, True], [False, True], revised)
    assert result.stop_reason == "oracle_success"
    assert result.revision_attempts == 1 and result.oracle_calls == 2
    assert len(traces) == 2 and traces[0] != traces[1]
    assert verifier.checks[0][0] == verifier.checks[1][0] == traces[0]
    assert verifier.checks[0][1] != verifier.checks[1][1] == verifier.checks[2][1]
    assert len(verifier.escalations) == 1
    assert result.verifications[0]["submission_hash"] == result.verifications[1]["submission_hash"]
    assert result.verifications[0]["trace_hash"] == result.verifications[1]["trace_hash"]
    assert result.verifications[2]["submission_hash"] != result.verifications[1]["submission_hash"]


def test_fourth_revised_package_is_checked_before_budget_stop():
    result, verifier, traces, _ = run([False] * 5, [], revised)
    assert result.stop_reason == "revision_budget_exhausted"
    assert result.revision_attempts == 4 and len(result.versions) == 5
    assert len(verifier.checks) == 5 and len(traces) == 5
    assert result.final_bundle.bundle_hash == result.versions[-1].bundle_hash


def test_five_oracle_calls_stop_without_creating_unused_revision():
    result, verifier, traces, oracle_hashes = run([True] * 5, [False] * 5, revised)
    assert result.stop_reason == "oracle_budget_exhausted"
    assert result.oracle_calls == 5 and result.revision_attempts == 0
    assert len(verifier.escalations) == 4 and len(traces) == 1
    assert len(set(oracle_hashes)) == 1
    assert len(result.submissions) == 1 and result.submissions[0]["initial"]
    assert result.to_dict()["submitted_learning_executions"] == 1


@pytest.mark.parametrize("violation", ["modified_bundle", "wrong_phase"])
def test_initial_execution_cannot_modify_s0_or_submit_as_a_revision(violation):
    initial = SkillBundle({"SKILL.md": "initial"})

    def execute_initial(bundle, *args, **kwargs):
        candidate = (
            SkillBundle({"SKILL.md": "changed"}) if violation == "modified_bundle" else bundle
        )
        return _submission(candidate, initial=violation != "wrong_phase")

    result = EvolutionEngine(
        execute_initial=execute_initial,
        oracle=lambda _: pytest.fail("invalid S0 execution cannot score"),
        verifier=None,
        revise=lambda *a, **k: pytest.fail("invalid S0 execution cannot evolve"),
    ).run({}, FrozenBase((), {}), initial)
    assert result.stop_reason == "initial_execution_failed"
    assert result.versions == (initial,) and result.final_bundle == initial
    assert result.submissions == result.verifications == result.attempts == ()
    assert result.oracle_calls == result.revision_attempts == 0


@pytest.mark.parametrize("kind", ["invalid", "unchanged"])
def test_invalid_and_unchanged_attempts_consume_budget(kind):
    def revise(previous, *args, **kwargs):
        if kind == "invalid":
            raise CreationFailure("invalid_package")
        return _submission(SkillBundle(previous.files, parent_hash=previous.bundle_hash))

    result, _, traces, _ = run([False] * 5, [], revise)
    assert result.revision_attempts == 4 and len(result.versions) == 1
    assert len(traces) == (1 if kind == "invalid" else 5)
    assert all(item["status"] == kind for item in result.attempts)


def test_unknown_revision_is_never_reissued():
    calls = []

    def revise(*args, **kwargs):
        calls.append(kwargs["operation_id"])
        raise CreationFailure("generation_result_unknown")

    result, _, _, _ = run([False], [], revise)
    assert result.stop_reason == "revision_result_unknown" and result.revision_attempts == 1
    assert result.attempts[0]["status"] == "result_unknown" and len(calls) == 1


def test_known_revision_cleanup_failure_stops_without_another_attempt(tmp_path):
    calls = []

    def revise(*args, **kwargs):
        calls.append(kwargs["operation_id"])
        raise RevisionFailure("cleanup_failed", dispatched=True)

    journal = Journal(tmp_path / "journal")
    result, _, traces, oracles = run([False], [], revise, journal=journal)
    assert result.stop_reason == "cleanup_failed"
    assert result.revision_attempts == 1 and len(result.versions) == 1
    assert len(traces) == 1 and oracles == [] and calls == ["evolution-revision-1"]
    assert result.attempts[0]["status"] == "invalid"
    assert result.attempts[0]["status"] != "result_unknown"
    assert journal.completed("evolution-result")
    restored = EvolutionEngine(
        execute_initial=lambda *a, **k: pytest.fail("sealed cleanup stop cannot execute again"),
        oracle=lambda _: pytest.fail("sealed cleanup stop cannot score"),
        verifier=None,
        revise=lambda *a, **k: pytest.fail("sealed cleanup stop cannot revise"),
        journal=journal,
        max_revisions=4,
    ).run({}, FrozenBase((), {}), result.versions[0])
    assert restored.to_dict() == result.to_dict()


def test_resume_uses_sealed_evolution_result(tmp_path):
    journal = Journal(tmp_path / "journal")
    initial = SkillBundle({"SKILL.md": "initial"})
    engine = EvolutionEngine(
        execute_initial=_initial_submission,
        oracle=lambda b: True,
        verifier=Verifier([True]),
        revise=revised,
        journal=journal,
    )
    result = engine.run({}, FrozenBase((), {}), initial)

    def forbidden(*args, **kwargs):
        raise AssertionError("a sealed execution must not run again")

    resumed = EvolutionEngine(
        execute_initial=forbidden,
        oracle=forbidden,
        verifier=None,
        revise=forbidden,
        journal=journal,
    ).run({}, FrozenBase((), {}), initial)
    assert resumed.to_dict() == result.to_dict()


@pytest.mark.parametrize("contents", [("middle", "initial"), ("middle", "later", "middle")])
@pytest.mark.parametrize("oracle_success", [False, True])
def test_revisited_content_keeps_actual_final_parent_and_resumes(
    tmp_path, contents, oracle_success
):
    values = iter(contents)

    def revisit(previous, *args, **kwargs):
        return _submission(
            SkillBundle({"SKILL.md": next(values)}, parent_hash=previous.bundle_hash)
        )

    journal = Journal(tmp_path)
    result, _, _, oracle_hashes = run(
        [False] * len(contents) + [oracle_success],
        [True] if oracle_success else [],
        revisit,
        journal=journal,
        max_revisions=len(contents),
    )
    assert result.final_bundle.files["SKILL.md"] == contents[-1]
    assert result.final_bundle.parent_hash == result.attempts[-1]["parent_hash"]
    assert result.final_bundle_ref == {
        "bundle_hash": result.final_bundle_hash,
        "parent_hash": result.attempts[-1]["parent_hash"],
    }
    assert len(result.versions) == len(set(("initial", *contents)))
    assert result.versions[0].parent_hash is None
    assert result.stop_reason == (
        "oracle_success" if oracle_success else "revision_budget_exhausted"
    )
    assert oracle_hashes == ([result.final_bundle_hash] if oracle_success else [])
    assert EvolutionResult.from_dict(result.to_dict()).final_bundle == result.final_bundle
    restored = EvolutionEngine(
        execute_initial=lambda *a, **k: pytest.fail("sealed result must not execute"),
        oracle=lambda _: pytest.fail("sealed result must not score"),
        verifier=None,
        revise=lambda *a, **k: pytest.fail("sealed result must not revise"),
        journal=journal,
        max_revisions=len(contents),
    ).run({}, FrozenBase((), {}), result.versions[0])
    assert restored.to_dict() == result.to_dict() and restored.final_bundle == result.final_bundle


def test_legacy_final_result_can_be_read_without_fabricating_lineage():
    result, _, _, _ = run([True], [True], revised)
    legacy = result.to_dict()
    del legacy["final_bundle_ref"]
    restored = EvolutionResult.from_dict(legacy)
    assert restored.final_bundle_ref is None and restored.final_bundle == result.versions[0]


@pytest.mark.parametrize(
    "stage,operation,reason,stop",
    [
        (
            "initial_execution",
            "evolution-initial-execution",
            "invalid_initial",
            "initial_execution_failed",
        ),
        (
            "verifier_initialization",
            "evolution-turn-0-suite",
            "missing_test_obligations",
            "verifier_initialization_failed",
        ),
        ("verification", "evolution-turn-0-verify", "invalid_test_report", "verification_failed"),
        (
            "test_escalation",
            "evolution-turn-0-escalate",
            "escalation_only_renamed_checks",
            "test_escalation_failed",
        ),
    ],
)
def test_phase_exception_retains_exact_failure_audit(stage, operation, reason, stop):
    class BrokenVerifier(Verifier):
        def create_suite(self, *args, previous_tests=None, **kwargs):
            if stage == "verifier_initialization" or (
                stage == "test_escalation" and previous_tests is not None
            ):
                raise ValueError(reason)
            return super().create_suite(*args, previous_tests=previous_tests, **kwargs)

        def verify(self, *args, **kwargs):
            if stage == "verification":
                raise ValueError(reason)
            return super().verify(*args, **kwargs)

    def execute_initial(*args, **kwargs):
        if stage == "initial_execution":
            raise ValueError(reason)
        return _initial_submission(*args, **kwargs)

    result = EvolutionEngine(
        execute_initial=execute_initial,
        oracle=lambda _: False,
        verifier=BrokenVerifier([True]),
        revise=lambda *a, **k: pytest.fail("phase failure cannot revise"),
    ).run({}, FrozenBase((), {}), SkillBundle({"SKILL.md": "initial"}))
    assert result.stop_reason == stop
    assert result.stage_failures == (
        {
            "stage": stage,
            "operation_id": operation,
            "exception_type": "ValueError",
            "reason": reason,
            "detail": f"ValueError: {reason}",
        },
    )
    assert EvolutionResult.from_dict(result.to_dict()).to_dict() == result.to_dict()
    legacy = result.to_dict()
    del legacy["stage_failures"]
    assert EvolutionResult.from_dict(legacy).stage_failures == ()


@pytest.mark.parametrize(
    "reason,detail",
    [
        ("test_change_without_justification", "test_change_without_justification"),
        ("non_utf8_package_file", "non_utf8_package_file: tests/test_public.py"),
    ],
)
def test_wrapped_verifier_exception_keeps_stable_underlying_reason(reason, detail):
    class BrokenVerifier:
        def create_suite(self, *args, **kwargs):
            try:
                raise ValueError(detail)
            except ValueError as exc:
                raise RuntimeError("authoring rejected after submission") from exc

    result = EvolutionEngine(
        execute_initial=_initial_submission,
        oracle=None,
        verifier=BrokenVerifier(),
        revise=None,
    ).run({}, FrozenBase((), {}), SkillBundle({"SKILL.md": "initial"}))
    failure = result.stage_failures[0]
    assert failure["exception_type"] == "RuntimeError"
    assert failure["reason"] == reason
    assert f"ValueError: {detail}" in failure["detail"]


def test_verifier_budget_stop_exports_rejection_evidence_without_sending_it_to_generator():
    from test_verifier import PublicRunner, ToolModel, call, submission

    invalid = submission()
    invalid["recommendations"] = [42]
    model = ToolModel([call("submit_tests", invalid)] * 30)
    result = EvolutionEngine(
        execute_initial=_initial_submission,
        oracle=lambda _: pytest.fail("invalid tests cannot call oracle"),
        verifier=SurrogateVerifier(model, PublicRunner()),
        revise=lambda *a, **k: pytest.fail("invalid tests cannot reach generator"),
    ).run(
        {"request": "complete the action"}, FrozenBase((), {}), SkillBundle({"SKILL.md": "initial"})
    )
    failure = result.to_dict()["stage_failures"][0]
    assert failure["reason"] == "verifier_episode_budget_exhausted"
    assert len(failure["rejections"]) == 30
    assert failure["rejections"][-1]["reason"] == "invalid_test_recommendations"
    assert failure["rejections"][-1]["operation_id"] == "evolution-turn-0-suite-turn-29-tool-0"
    assert result.revision_attempts == result.oracle_calls == 0


def test_old_final_result_checkpoint_is_not_resumed(tmp_path):
    initial, base = SkillBundle({"SKILL.md": "initial"}), FrozenBase((), {})
    result, _, _, _ = run([True], [True], revised)
    journal = Journal(tmp_path)
    journal.dispatch(
        "evolution-result",
        {
            "initial_bundle_hash": initial.bundle_hash,
            "base_hash": base.base_hash,
            "max_revisions": 15,
            "max_oracles": 5,
            "max_oracle_errors": 5,
        },
        result.to_dict,
    )
    with pytest.raises(ValueError, match="journal operation payload differs"):
        EvolutionEngine(
            execute_initial=None, oracle=None, verifier=None, revise=None, journal=journal
        ).run({}, base, initial)


@pytest.mark.parametrize("reference", [{}, {"bundle_hash": "0" * 64, "parent_hash": None}])
def test_final_bundle_reference_must_match_selected_sealed_content(reference):
    result, _, _, _ = run([True], [True], revised)
    value = result.to_dict()
    value["final_bundle_ref"] = reference
    with pytest.raises(ValueError, match="invalid_final_bundle_ref"):
        EvolutionResult.from_dict(value)


@pytest.mark.parametrize("parent", [None, "0" * 64, ["invalid"], "self"])
def test_revised_final_reference_requires_a_known_sealed_parent(parent):
    result, _, _, _ = run([False, True], [True], revised)
    value = result.to_dict()
    value["final_bundle_ref"]["parent_hash"] = (
        result.final_bundle_hash if parent == "self" else parent
    )
    with pytest.raises(ValueError, match="invalid_final_bundle_ref"):
        EvolutionResult.from_dict(value)


def test_final_version_does_not_depend_on_evaluation():
    result, _, _, _ = run([False] * 5, [], revised)
    assert result.final_bundle_hash == result.versions[-1].bundle_hash
    assert "utility" not in result.to_dict() and "asr" not in result.to_dict()


def test_fifteenth_revision_is_checked_with_locked_tests_before_budget_stop():
    result, verifier, traces, _ = run([False] * 16, [], revised, max_revisions=15)
    assert result.stop_reason == "revision_budget_exhausted"
    assert result.revision_attempts == 15 and len(result.versions) == 16
    assert len(traces) == 16 and len(verifier.checks) == 16
    assert len({test_hash for _, test_hash in verifier.checks}) == 1
    assert result.final_bundle == result.versions[-1]


@pytest.mark.parametrize("kind", ["invalid", "unchanged"])
def test_fifteen_invalid_or_unchanged_revisions_do_not_fabricate_content_versions(kind):
    def revise(previous, *args, **kwargs):
        if kind == "invalid":
            raise CreationFailure("invalid_package")
        return _submission(SkillBundle(previous.files, parent_hash=previous.bundle_hash))

    result, _, traces, _ = run([False] * 16, [], revise, max_revisions=15)
    assert result.stop_reason == "revision_budget_exhausted"
    assert result.revision_attempts == 15 and len(result.versions) == 1
    assert len(traces) == (1 if kind == "invalid" else 16)
    assert all(item["status"] == kind for item in result.attempts)


def test_public_feedback_accumulates_same_task_diagnostics_and_opaque_oracle_bit():
    histories = []

    def revise(previous, *args, **kwargs):
        histories.append(kwargs["feedback_history"])
        return revised(previous)

    result, _, _, _ = run([False, True, False, False, True], [False, True], revise)
    assert result.stop_reason == "oracle_success" and result.revision_attempts == 3
    assert [len(history) for history in histories] == [1, 4, 5]
    assert [event["kind"] for event in histories[1]] == [
        "verification",
        "verification",
        "oracle",
        "verification",
    ]
    assert histories[1][2]["passed"] is False and histories[1][2]["call"] == 1
    base_hash = FrozenBase((), {}).base_hash
    assert all(event["base_hash"] == base_hash for history in histories for event in history)
    assert all(
        "suite" not in event and "files" not in event for history in histories for event in history
    )


def test_context_admission_stop_is_not_an_invalid_dispatched_revision(tmp_path):
    calls = []

    def revise(*args, **kwargs):
        calls.append(kwargs["operation_id"])
        raise GeneratorContextBudgetExhausted(157633, 157632)

    journal = Journal(tmp_path)
    result, _, traces, oracles = run([False], [], revise, journal=journal, max_revisions=15)
    assert result.stop_reason == "context_budget_exhausted"
    assert result.revision_attempts == 0 and result.attempts == ()
    assert len(result.versions) == 1 and len(traces) == 1 and oracles == []
    assert calls == ["evolution-revision-1"]
    restored = EvolutionEngine(
        execute_initial=lambda *a, **k: pytest.fail("sealed context stop cannot execute again"),
        oracle=lambda _: pytest.fail("sealed context stop cannot call oracle"),
        verifier=None,
        revise=lambda *a, **k: pytest.fail("sealed stop cannot generate"),
        journal=journal,
        max_revisions=15,
    ).run({}, FrozenBase((), {}), result.versions[0])
    assert restored.to_dict() == result.to_dict()


@pytest.mark.parametrize("revisions,oracles", [(16, 5), (15, 6), (True, 5), (15, 1.5)])
def test_evolution_hardcaps_require_integer_m15_k5(revisions, oracles):
    with pytest.raises(ValueError, match="budgets"):
        EvolutionEngine(
            execute_initial=None,
            oracle=None,
            verifier=None,
            revise=None,
            max_revisions=revisions,
            max_oracles=oracles,
        )


@pytest.mark.parametrize("kind", ["skip", "xfail"])
@pytest.mark.parametrize("repair_succeeds", [False, True])
def test_skip_or_xfail_repairs_tests_once_without_consuming_skill_revisions(
    tmp_path, kind, repair_succeeds
):
    requests, executions, oracle_hashes = [], [], []
    # A safe submitted suite can still receive a runtime skip/xfail report.
    # Statically visible skip/xfail decorators are rejected at submission.
    source = "def test_public(trace): assert trace['ok']"
    repaired_source = "def test_public(trace): assert trace['ok']"
    initial = SkillBundle({"SKILL.md": "initial"})
    base = FrozenBase((), {})
    journal = Journal(tmp_path)

    def model(payload):
        requests.append(payload["action"])
        if payload["action"] == "initial":
            content = source
        else:
            assert payload["action"] == "repair"
            assert payload["test_results"]["failure"] == "skip_or_xfail"
            assert payload["test_results"]["program_error"] is True
            assert payload["previous_tests"]["files"] == {"tests/test_public.py": source}
            content = repaired_source
        return {"files": [{"path": "tests/test_public.py", "content": content}]}

    class Runner:
        def run_verifier(self, inputs, frozen, trace, files):
            executions.append(dict(files))
            passed = len(executions) == 2 and repair_succeeds
            return ProgramResult(
                0,
                {
                    "collected": 1,
                    "collected_nodeids": ["tests/test_public.py::test_public"],
                    "collection_errors": 0,
                    "exit_code": 0,
                    "results": [
                        {
                            "nodeid": "tests/test_public.py::test_public",
                            "stage": "call" if passed or kind == "xfail" else "setup",
                            "outcome": "passed" if passed else "skipped",
                            "exception": None,
                            "xfail": not passed and kind == "xfail",
                        }
                    ],
                },
            )

    result = EvolutionEngine(
        execute_initial=lambda bundle, *a, **k: _submission(bundle, {"ok": True}, initial=True),
        oracle=lambda bundle: oracle_hashes.append(bundle.bundle_hash) or True,
        verifier=SurrogateVerifier(model, Runner(), journal=journal),
        revise=lambda *a, **k: pytest.fail("invalid tests cannot consume Skill revisions"),
        journal=journal,
        max_revisions=15,
        max_oracles=5,
    ).run({}, base, initial)
    assert result.stop_reason == (
        "oracle_success" if repair_succeeds else "verification_program_error_exhausted"
    )
    assert result.revision_attempts == 0 and result.attempts == ()
    assert result.oracle_calls == int(repair_succeeds)
    assert oracle_hashes == ([initial.bundle_hash] if repair_succeeds else [])
    assert requests == ["initial", "repair"]
    assert executions == [
        {"tests/test_public.py": source},
        {"tests/test_public.py": repaired_source},
    ]
    assert result.verifications[0]["suite"]["version"] == 0
    assert result.verifications[0]["suite"]["repairs"] == 1
    assert journal.completed("evolution-result")


@pytest.mark.parametrize("status", [401, 403])
def test_verifier_diagnosis_auth_failure_stops_before_skill_revision_or_oracle(tmp_path, status):
    journal, calls = Journal(tmp_path), []
    initial = SkillBundle({"SKILL.md": "initial"})
    base = FrozenBase((), {})

    class Runner:
        def run_verifier(self, *args):
            calls.append("pytest")
            return ProgramResult(
                1,
                {
                    "collected": 1,
                    "collected_nodeids": ["tests/test_public.py::test_public"],
                    "collection_errors": 0,
                    "exit_code": 1,
                    "results": [
                        {
                            "nodeid": "tests/test_public.py::test_public",
                            "stage": "call",
                            "outcome": "failed",
                            "exception": "AssertionError",
                            "xfail": False,
                        }
                    ],
                },
            )

    def model(payload):
        calls.append(payload["action"])
        if payload["action"] == "initial":
            return {
                "files": [
                    {"path": "tests/test_public.py", "content": "def test_public(): assert False"}
                ]
            }
        raise ModelClientError("authentication_failed", "offline denied", status=status)

    engine = EvolutionEngine(
        execute_initial=_initial_submission,
        oracle=lambda _: pytest.fail("diagnosis auth failure cannot call oracle"),
        verifier=SurrogateVerifier(model, Runner(), journal=journal),
        revise=lambda *a, **k: pytest.fail("diagnosis auth failure cannot revise Skill"),
        journal=journal,
    )
    result = engine.run({}, base, initial)
    assert result.stop_reason == "authentication_failed"
    failure = result.stage_failures[0]
    assert failure["stage"] == "verification" and failure["reason"] == "authentication_failed"
    assert failure["test_runs"][0]["operation_id"] == "evolution-turn-0-verify-tests"
    assert failure["test_runs"][0]["program"]["output"]["results"][0]["outcome"] == "failed"
    assert result.revision_attempts == result.oracle_calls == 0
    assert calls == ["initial", "pytest", "diagnosis"]
    assert journal.completed("evolution-result")
    assert journal.response("evolution-result")["stop_reason"] == "authentication_failed"


def test_existing_auth_failure_stops_all_external_operations_and_seals_stop(tmp_path):
    journal = Journal(tmp_path)

    def denied():
        raise ModelClientError("authentication_failed", "offline denied", status=401)

    with pytest.raises(UnknownOperation):
        journal.dispatch("earlier-denied-request", {}, denied)
    initial = SkillBundle({"SKILL.md": "initial"})
    result = EvolutionEngine(
        execute_initial=lambda *a, **k: pytest.fail("known auth failure cannot start rollout"),
        oracle=lambda _: pytest.fail("known auth failure cannot start oracle"),
        verifier=None,
        revise=None,
        journal=journal,
    ).run({}, FrozenBase((), {}), initial)
    assert result.stop_reason == "authentication_failed" and result.verifications == ()
    assert result.oracle_calls == result.revision_attempts == 0
    assert journal.completed("evolution-result")


@pytest.mark.parametrize("returned_bit", [False, True])
def test_journal_auth_failure_takes_priority_over_returned_oracle_bit(tmp_path, returned_bit):
    journal = Journal(tmp_path)

    def oracle(_bundle):
        def denied():
            raise ModelClientError("authentication_failed", "offline denied", status=401)

        with pytest.raises(UnknownOperation):
            journal.dispatch("private-judge-denied", {}, denied)
        return returned_bit

    result = EvolutionEngine(
        execute_initial=_initial_submission,
        oracle=oracle,
        verifier=Verifier([True]),
        revise=lambda *a, **k: pytest.fail("auth failure cannot revise Skill"),
        journal=journal,
        max_oracles=1,
    ).run({}, FrozenBase((), {}), SkillBundle({"SKILL.md": "initial"}))
    assert result.stop_reason == "authentication_failed" and result.oracle_results == ()
    assert result.revision_attempts == 0 and journal.completed("evolution-result")


@pytest.mark.parametrize("stage", ["oracle", "revision"])
def test_direct_auth_failure_is_not_relabelled_as_invalid_package(stage):
    def denied(*args, **kwargs):
        raise ModelClientError("authentication_failed", "offline denied", status=403)

    initial, base = SkillBundle({"SKILL.md": "initial"}), FrozenBase((), {})
    result = EvolutionEngine(
        execute_initial=_initial_submission,
        oracle=denied,
        verifier=Verifier([stage == "oracle"]),
        revise=denied,
    ).run({}, base, initial)
    assert result.stop_reason == "authentication_failed"
    if stage == "revision":
        assert result.attempts[0]["status"] == "authentication_failed"
        assert result.revision_attempts == 1
    else:
        assert result.attempts == ()


@pytest.mark.parametrize("recover", [False, True])
def test_completed_oracle_infrastructure_errors_have_separate_budget(tmp_path, recover):
    calls = []

    def oracle(bundle):
        calls.append(bundle.bundle_hash)
        if recover and len(calls) == 2:
            return True
        raise OracleUnavailable("official reward file missing")

    verifier = Verifier([True])
    journal = Journal(tmp_path)
    result = EvolutionEngine(
        execute_initial=_initial_submission,
        oracle=oracle,
        verifier=verifier,
        revise=lambda *a, **k: pytest.fail("infrastructure failures must not revise Skill"),
        journal=journal,
        max_oracle_errors=5,
    ).run({}, FrozenBase((), {}), SkillBundle({"SKILL.md": "initial"}))
    assert result.revision_attempts == 0 and verifier.escalations == []
    assert result.oracle_calls == int(recover)
    assert len(result.oracle_failures) == (1 if recover else 5)
    assert len(set(calls)) == 1
    assert result.stop_reason == (
        "oracle_success" if recover else "oracle_infrastructure_unavailable"
    )
    assert all(item["status"] == "NOT_MEASURED" for item in result.oracle_failures)


def test_unknown_oracle_operation_is_not_infrastructure_retry(tmp_path):
    calls = []

    def oracle(bundle):
        calls.append(bundle.bundle_hash)
        raise ConnectionError("response was not received")

    result = EvolutionEngine(
        execute_initial=_initial_submission,
        oracle=oracle,
        verifier=Verifier([True]),
        revise=revised,
        journal=Journal(tmp_path),
    ).run({}, FrozenBase((), {}), SkillBundle({"SKILL.md": "initial"}))
    assert result.stop_reason == "oracle_result_unknown"
    assert result.oracle_calls == result.revision_attempts == len(result.oracle_failures) == 0
    assert len(calls) == 1
