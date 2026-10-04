import pytest
from tau_skill_evolution.artifacts import FrozenBase, SkillBundle
from tau_skill_evolution.container import ProgramResult
from tau_skill_evolution.evolution import EvolutionEngine, EvolutionResult
from tau_skill_evolution.generator import CreationFailure, GeneratorContextBudgetExhausted
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


def run(outcomes, oracles, revise, **kwargs):
    initial = SkillBundle({"SKILL.md": "initial"})
    traces, oracle_hashes = [], []
    verifier = Verifier(outcomes)
    kwargs.setdefault("max_revisions", 4)
    oracle_values = iter(oracles)

    def rollout(bundle):
        traces.append(bundle.bundle_hash)
        return {"bundle_hash": bundle.bundle_hash, "events": []}

    def oracle(bundle):
        oracle_hashes.append(bundle.bundle_hash)
        return next(oracle_values)

    result = EvolutionEngine(
        rollout=rollout, oracle=oracle, verifier=verifier, revise=revise, **kwargs
    ).run({}, FrozenBase((), {}), initial)
    return result, verifier, traces, oracle_hashes


def revised(previous, *args, **kwargs):
    return SkillBundle(
        {"SKILL.md": previous.files["SKILL.md"] + " updated"}, parent_hash=previous.bundle_hash
    )


def test_failure_revises_parent_and_tests_stay_fixed_then_early_stops():
    result, verifier, traces, oracle_hashes = run([False, True], [True], revised)
    assert result.stop_reason == "oracle_success"
    assert result.revision_attempts == 1 and result.oracle_calls == 1
    assert len(result.versions) == 2 and len(traces) == 2 and len(oracle_hashes) == 1
    assert verifier.checks[0][1] == verifier.checks[1][1]
    assert result.versions[1].parent_hash == result.versions[0].bundle_hash
    assert EvolutionResult.from_dict(result.to_dict()).to_dict() == result.to_dict()


def test_oracle_fail_escalates_then_fresh_same_bundle_before_revision():
    result, verifier, traces, oracle_hashes = run([True, False, True], [False, True], revised)
    assert result.stop_reason == "oracle_success"
    assert result.revision_attempts == 1 and result.oracle_calls == 2
    assert traces[0] == traces[1] and traces[2] != traces[1]
    assert verifier.checks[0][1] != verifier.checks[1][1] == verifier.checks[2][1]
    assert len(verifier.escalations) == 1


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
    assert len(verifier.escalations) == 4 and len(traces) == 5
    assert len(set(oracle_hashes)) == 1


@pytest.mark.parametrize("kind", ["invalid", "unchanged"])
def test_invalid_and_unchanged_attempts_consume_budget(kind):
    def revise(previous, *args, **kwargs):
        if kind == "invalid":
            raise CreationFailure("invalid_package")
        return SkillBundle(previous.files, parent_hash=previous.bundle_hash)

    result, _, traces, _ = run([False] * 5, [], revise)
    assert result.revision_attempts == 4 and len(result.versions) == 1 and len(traces) == 5
    assert all(item["status"] == kind for item in result.attempts)


def test_unknown_revision_is_never_reissued():
    calls = []

    def revise(*args, **kwargs):
        calls.append(kwargs["operation_id"])
        raise CreationFailure("generation_result_unknown")

    result, _, _, _ = run([False], [], revise)
    assert result.stop_reason == "revision_result_unknown" and result.revision_attempts == 1
    assert result.attempts[0]["status"] == "result_unknown" and len(calls) == 1


def test_resume_uses_sealed_evolution_result(tmp_path):
    journal = Journal(tmp_path / "journal")
    initial = SkillBundle({"SKILL.md": "initial"})
    engine = EvolutionEngine(
        rollout=lambda b: {"bundle_hash": b.bundle_hash},
        oracle=lambda b: True,
        verifier=Verifier([True]),
        revise=revised,
        journal=journal,
    )
    result = engine.run({}, FrozenBase((), {}), initial)

    def forbidden(*args):
        raise AssertionError("a sealed execution must not run again")

    resumed = EvolutionEngine(
        rollout=forbidden, oracle=forbidden, verifier=None, revise=forbidden, journal=journal
    ).run({}, FrozenBase((), {}), initial)
    assert resumed.to_dict() == result.to_dict()


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
        return SkillBundle(previous.files, parent_hash=previous.bundle_hash)

    result, _, traces, _ = run([False] * 16, [], revise, max_revisions=15)
    assert result.stop_reason == "revision_budget_exhausted"
    assert result.revision_attempts == 15 and len(result.versions) == 1
    assert len(traces) == 16 and all(item["status"] == kind for item in result.attempts)


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
        rollout=lambda _: pytest.fail("sealed context stop cannot execute again"),
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
            rollout=None,
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
    source = (
        f"import pytest\n@pytest.mark.{kind}(reason='invalid generated check')\n"
        "def test_public(trace): assert trace['ok']"
    )
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
        rollout=lambda _: {"ok": True},
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
                0,
                {
                    "collected": 1,
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
        rollout=lambda _: {"events": []},
        oracle=lambda _: pytest.fail("diagnosis auth failure cannot call oracle"),
        verifier=SurrogateVerifier(model, Runner(), journal=journal),
        revise=lambda *a, **k: pytest.fail("diagnosis auth failure cannot revise Skill"),
        journal=journal,
    )
    result = engine.run({}, base, initial)
    assert result.stop_reason == "authentication_failed"
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
        rollout=lambda _: pytest.fail("known auth failure cannot start rollout"),
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
        rollout=lambda bundle: {"bundle_hash": bundle.bundle_hash, "events": []},
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
        rollout=lambda bundle: {"bundle_hash": bundle.bundle_hash},
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
