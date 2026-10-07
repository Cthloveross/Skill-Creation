import json
import subprocess
import sys
from contextlib import contextmanager

import pytest
from tau_skill_evolution.artifacts import FrozenBase
from tau_skill_evolution.constants import EXPERIMENT_ROOT
from tau_skill_evolution.container import (
    _PYTEST_HARNESS,
    ContainerUnavailable,
    ProcessResult,
    ProgramResult,
    _program_result,
    _public_workspace,
)
from tau_skill_evolution.journal import Journal, UnknownOperation
from tau_skill_evolution.model import ModelClientError, authentication_status
from tau_skill_evolution.verifier import (
    SurrogateVerifier,
    TestSuite,
    VerificationReport,
    _inheritance,
    _report,
    _suite_structure,
    _validate_test_source,
)

SOURCE = "def test_public(trace): assert trace['ok']"


def suite():
    return TestSuite({"tests/test_public.py": SOURCE})


def program(outcome="passed", *, ids=None, **extra):
    ids = ids or ["tests/test_public.py::test_public"]
    exit_code = int(outcome == "failed")
    items = []
    for identifier in ids:
        item = {
            "nodeid": identifier,
            "stage": "call",
            "outcome": outcome,
            "exception": "AssertionError" if outcome == "failed" else None,
            "requirement_failure": outcome == "failed",
            "xfail": False,
        }
        item.update(extra)
        items.append(item)
    return ProgramResult(
        exit_code,
        {
            "collected": len(ids),
            "collected_nodeids": ids,
            "collection_errors": 0,
            "exit_code": exit_code,
            "results": items,
        },
        failure="nonzero_exit" if exit_code else None,
    )


def test_nonempty_actual_pass_required():
    assert _report(suite(), program()).passed
    failure = _report(suite(), program("failed"))
    assert not failure.passed and not failure.program_error
    for invalid in (program("skipped"), program(xfail=True)):
        report = _report(suite(), invalid)
        assert not report.passed and report.program_error
        assert report.failure == "skip_or_xfail"
    assert _report(suite(), ProgramResult(0, {"collected": 0, "results": []})).program_error
    assert _report(suite(), ProgramResult(1, failure="nonzero_exit")).program_error
    assert _report(
        suite(), program("failed", exception="NameError", requirement_failure=False)
    ).program_error


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_ids",
        "duplicate_ids",
        "unknown_id",
        "duplicate_call",
        "passed_exception",
        "passed_xfail",
        "failed_exit_zero",
        "passed_exit_one",
        "bool_exit_code",
        "failure_with_zero_exit",
    ],
)
def test_report_identity_and_outcome_contradictions_are_rejected(mutation):
    result = program()
    if mutation == "missing_ids":
        del result.output["collected_nodeids"]
    elif mutation == "duplicate_ids":
        result.output["collected"] = 2
        result.output["collected_nodeids"] *= 2
    elif mutation == "unknown_id":
        result.output["results"][0]["nodeid"] = "tests/test_other.py::test_unknown"
    elif mutation == "duplicate_call":
        result.output["results"] *= 2
    elif mutation == "passed_exception":
        result.output["results"][0]["exception"] = "Skipped"
    elif mutation == "passed_xfail":
        result.output["results"][0]["xfail"] = True
    elif mutation == "failed_exit_zero":
        result = program("failed")
        result.output["exit_code"] = 0
    elif mutation == "passed_exit_one":
        result.output["exit_code"] = 1
    elif mutation == "bool_exit_code":
        result.output["exit_code"] = False
    elif mutation == "failure_with_zero_exit":
        result = ProgramResult(0, result.output, failure="nonzero_exit")
    report = _report(suite(), result)
    assert not report.passed and report.program_error


@pytest.mark.parametrize("process_exit, report_exit", [(0, 1), (1, 0), (None, 0), (False, 0)])
def test_process_exit_is_authoritative_for_pytest_reports(process_exit, report_exit):
    output = program().output
    output["exit_code"] = report_exit
    report = _report(suite(), ProgramResult(process_exit, output))
    assert report.program_error and report.failure == "inconsistent_test_exit_code"


def test_matching_pytest_failure_exit_is_an_assertion_failure_not_a_script_error():
    measured = program("failed")
    assert measured.exit_code == 1 and measured.failure == "nonzero_exit"
    report = _report(suite(), measured)
    assert not report.passed and not report.program_error
    assert _report(suite(), ProgramResult(1, failure="nonzero_exit")).program_error


@pytest.mark.parametrize("status", [401, 403])
@pytest.mark.parametrize("test_error", [False, True])
def test_auth_failure_propagates_without_another_model_request(tmp_path, status, test_error):
    calls, executions = [], []

    class Runner:
        def run_verifier(self, *args):
            executions.append(args)
            return program(
                "failed",
                exception="NameError" if test_error else "AssertionError",
                requirement_failure=not test_error,
            )

    def model(payload):
        calls.append(payload["action"])
        raise ModelClientError("authentication_failed", "offline denied", status=status)

    journal = Journal(tmp_path)
    verifier = SurrogateVerifier(model, Runner(), journal=journal)
    with pytest.raises(UnknownOperation) as raised:
        verifier.verify({}, FrozenBase((), {}), {}, suite())
    assert authentication_status(raised.value) == status
    assert calls == ["repair" if test_error else "diagnosis"]
    assert len(executions) == 1 and journal.authentication_failure() == status
    with pytest.raises(ModelClientError):
        verifier.create_suite({}, FrozenBase((), {}), {})
    assert len(calls) == 1


@pytest.mark.parametrize("flag", [True, False, None, 1, "true", [], {}])
def test_diagnosis_cannot_reclassify_assertion_or_unlock_tests(tmp_path, flag):
    calls, executions = [], []

    class Runner:
        def run_verifier(self, *args):
            executions.append(args)
            return program("failed")

    def model(payload):
        calls.append(payload["action"])
        return {"test_program_error": flag, "diagnosis": "public obligation failed"}

    original = suite()
    journal = Journal(tmp_path / "journal")
    report = SurrogateVerifier(model, Runner(), journal=journal).verify(
        {}, FrozenBase((), {}), {}, original
    )
    assert not report.passed and not report.program_error and report.suite == original
    assert report.results[0]["outcome"] == "failed"
    assert calls == ["diagnosis"] and len(executions) == 1
    replay = SurrogateVerifier(model, Runner(), journal=journal).verify(
        {}, FrozenBase((), {}), {}, original
    )
    assert replay.to_dict() == report.to_dict() and len(executions) == 1


@pytest.mark.parametrize(
    "source, reason",
    [
        ("# comments only", "empty_test_suite"),
        ("def test_public(): pass", "vacuous_test_check"),
        ("def test_public(): assert True", "vacuous_test_check"),
        ("def test_public(): assert 1 == 1", "vacuous_test_check"),
        ("def test_public(): assert not False", "vacuous_test_check"),
        ("def pytest_runtest_logreport(report): report.outcome='passed'", "pytest_hook_tampering"),
        ("import pytest\n@pytest.mark.skip\ndef test_public(trace): assert trace", "skip_or_xfail"),
        (
            "import pytest\n@pytest.mark.xfail\ndef test_public(trace): assert trace",
            "skip_or_xfail",
        ),
        (
            "def test_public(request): request.config.pluginmanager.register(object())",
            "vacuous_test_check",
        ),
        (
            "from _pytest.runner import CallInfo\ndef test_public(trace): assert trace",
            "pytest_hook_tampering",
        ),
    ],
)
def test_generated_source_integrity_guard(source, reason):
    with pytest.raises(ValueError, match=reason):
        _validate_test_source({"tests/test_public.py": source})


def test_integrity_guard_accepts_substantive_helper_assertions():
    _validate_test_source(
        {
            "tests/test_public.py": "def check_public(trace): assert trace['ok']\n"
            "def test_public(trace): check_public(trace)"
        }
    )
    _validate_test_source(
        {
            "tests/test_public.py": "import numpy as np\ndef test_public(trace):\n"
            "    np.testing.assert_allclose(trace['actual'], trace['expected'])"
        }
    )


def test_real_model_requires_public_terminal_session():
    model = ToolModel([])
    with pytest.raises(ValueError, match="public_verifier_session_required"):
        SurrogateVerifier(model, object()).create_suite({}, FrozenBase((), {}), {})
    assert model.requests == []


def test_escalation_preserves_checks_and_adds_checks_in_same_file_with_evidence():
    original = suite()
    source = SOURCE + "\ndef test_complete(trace): assert trace.get('complete')"
    raw = {
        "files": [{"path": "tests/test_public.py", "content": source}],
        "change_notes": {
            "tests/test_public.py": {
                "reason": "add the public completion requirement",
                "evidence": ["complete the action"],
            }
        },
    }
    updated = SurrogateVerifier(lambda _: raw, None).create_suite(
        {"request": "complete the action"}, FrozenBase((), {}), {}, original
    )
    assert updated.version == 1 and "test_complete" in updated.files["tests/test_public.py"]
    assert len(updated.inheritance) == 1 and updated.inheritance[0]["previous_checks"] == (
        "tests/test_public.py::test_public",
    )
    assert TestSuite.from_dict(updated.to_dict()).to_dict() == updated.to_dict()


def test_escalation_changed_file_requires_grounded_justification():
    raw = {
        "files": [
            {
                "path": "tests/test_public.py",
                "content": SOURCE + "\ndef test_more(trace): assert trace",
            }
        ]
    }
    with pytest.raises(ValueError, match="test_change_without_justification"):
        SurrogateVerifier(lambda _: raw, None).create_suite({}, FrozenBase((), {}), {}, suite())


def test_escalation_comment_only_file_is_not_new_coverage():
    raw = {"files": [{"path": "tests/test_more.py", "content": "# a new filename"}]}
    with pytest.raises(ValueError, match="empty_test_suite"):
        SurrogateVerifier(lambda _: raw, None).create_suite({}, FrozenBase((), {}), {}, suite())


@pytest.mark.parametrize(
    "old_source,new_source,new_path",
    [
        (SOURCE, SOURCE.replace("test_public", "test_renamed"), "tests/test_public.py"),
        (SOURCE, SOURCE, "tests/test_moved.py"),
        (
            SOURCE,
            '"""new documentation"""\n# renamed check\n'
            + SOURCE.replace("test_public", "test_renamed"),
            "tests/test_public.py",
        ),
        (
            "class TestPublic:\n def test_public(self, trace): assert trace['ok']",
            "class TestRenamed:\n def test_renamed(self, trace): assert trace['ok']",
            "tests/test_public.py",
        ),
    ],
)
def test_escalation_rejects_exact_rename_only_changes(old_source, new_source, new_path):
    old_class = "::TestPublic" if old_source.startswith("class") else ""
    new_class = "::TestRenamed" if new_source.startswith("class") else ""
    new_name = "test_renamed" if "test_renamed" in new_source else "test_public"
    original = TestSuite(
        {"tests/test_public.py": old_source},
        obligations=(
            {
                "id": "action",
                "requirement": "complete action",
                "checks": [f"tests/test_public.py{old_class}::test_public"],
                "evidence": ["complete action"],
            },
        ),
    )
    raw = {
        "files": [{"path": new_path, "content": new_source}],
        "obligations": [
            {
                "id": "action",
                "requirement": "complete action",
                "checks": [f"{new_path}{new_class}::{new_name}"],
                "evidence": ["complete action"],
            }
        ],
        "change_notes": {
            "tests/test_public.py": {"reason": "rename only", "evidence": ["complete action"]}
        },
    }
    with pytest.raises(ValueError, match="escalation_only_renamed_checks"):
        _inheritance(
            original,
            {new_path: new_source},
            tuple(raw["obligations"]),
            raw,
            {"public_inputs": {"request": "complete action"}},
        )


@pytest.mark.parametrize("extra_source", [None, "", "# comment", '"""documentation"""'])
def test_create_suite_rejects_the_reproduced_rename_only_upgrade(extra_source):
    original = TestSuite(
        {"tests/test_public.py": SOURCE},
        obligations=(
            {
                "id": "action",
                "requirement": "complete action",
                "checks": ["tests/test_public.py::test_public"],
                "evidence": ["complete action"],
            },
        ),
    )
    raw = {
        "files": [
            {
                "path": "tests/test_public.py",
                "content": SOURCE.replace("test_public", "test_renamed"),
            }
        ],
        "obligations": [
            {
                **dict(original.obligations[0]),
                "checks": ["tests/test_public.py::test_renamed"],
                "evidence": ["complete action"],
            }
        ],
        "change_notes": {
            "tests/test_public.py": {"reason": "rename only", "evidence": ["complete action"]}
        },
    }
    if extra_source is not None:
        raw["files"].append({"path": "tests/test_empty.py", "content": extra_source})
    with pytest.raises(ValueError, match="escalation_only_renamed_checks"):
        SurrogateVerifier(lambda _: raw, None).create_suite(
            {"request": "complete action"}, FrozenBase((), {}), {}, original
        )


def test_upgrade_structure_preserves_helper_logic_and_parameter_values():
    old_source = (
        "import pytest\ndef parse(trace): return trace['old']\n"
        "@pytest.mark.parametrize('expected', [1])\n"
        "def test_public(trace, expected): assert parse(trace) == expected"
    )
    new_source = old_source.replace("['old']", "['actual']").replace("[1]", "[2]")
    new_source += "\ndef test_complete(trace): assert trace['complete']"
    raw = {
        "files": [{"path": "tests/test_public.py", "content": new_source}],
        "change_notes": {
            "tests/test_public.py": {
                "reason": "correct parsing and add completion check",
                "evidence": ["complete action"],
            }
        },
    }
    updated = SurrogateVerifier(lambda _: raw, None).create_suite(
        {"request": "complete action"},
        FrozenBase((), {}),
        {},
        TestSuite({"tests/test_public.py": old_source}),
    )
    assert updated.version == 1 and updated.files["tests/test_public.py"] == new_source


@pytest.mark.parametrize("split", [False, True])
@pytest.mark.parametrize("new_assertion", [False, True])
def test_upgrade_file_regrouping_requires_more_than_renamed_checks(split, new_assertion):
    old_first = "def test_one(trace): assert trace['one']"
    old_second = "def test_two(trace): assert trace['two']"
    new_first = old_first.replace("test_one", "test_renamed_one")
    if new_assertion:
        new_first += " and trace['complete']"
    new_second = old_second.replace("test_two", "test_renamed_two")
    joined_old = {"tests/test_public.py": old_first + "\n" + old_second}
    split_old = {"tests/test_first.py": old_first, "tests/test_second.py": old_second}
    joined_new = {"tests/test_public.py": new_first + "\n" + new_second}
    split_new = {"tests/test_first.py": new_first, "tests/test_second.py": new_second}
    old, new = (joined_old, split_new) if split else (split_old, joined_new)
    old_checks = (
        ["tests/test_public.py::test_one", "tests/test_public.py::test_two"]
        if split
        else ["tests/test_first.py::test_one", "tests/test_second.py::test_two"]
    )
    new_checks = (
        ["tests/test_first.py::test_renamed_one", "tests/test_second.py::test_renamed_two"]
        if split
        else ["tests/test_public.py::test_renamed_one", "tests/test_public.py::test_renamed_two"]
    )
    obligation = {
        "id": "action",
        "requirement": "complete action",
        "checks": old_checks,
        "evidence": ["complete action"],
    }
    previous = TestSuite(old, obligations=(obligation,))
    obligations = ({**obligation, "checks": new_checks},)
    raw = {
        "change_notes": {
            path: {"reason": "regroup public checks", "evidence": ["complete action"]}
            for path in old
        }
    }
    payload = {
        "public_inputs": {"request": "complete action"},
        "frozen_base": {},
        "public_trace": {},
    }
    if new_assertion:
        assert _inheritance(previous, new, obligations, raw, payload)
    else:
        with pytest.raises(ValueError, match="escalation_only_renamed_checks"):
            _inheritance(previous, new, obligations, raw, payload)


@pytest.mark.parametrize(
    "old_source,new_source",
    [
        (
            "VALUE = 1\n" + SOURCE,
            "VALUE = 2\n" + SOURCE.replace("test_public", "test_renamed"),
        ),
        (
            "def parse(trace): return trace['old']\ndef test_public(trace): assert parse(trace)",
            "def parse(trace): return trace['actual']\n"
            "def test_renamed(trace): assert parse(trace)",
        ),
        (
            "import pytest\n@pytest.mark.parametrize('value', [1])\n"
            "def test_public(value): assert value",
            "import pytest\n@pytest.mark.parametrize('value', [2])\n"
            "def test_renamed(value): assert value",
        ),
    ],
)
def test_upgrade_structure_keeps_executable_context(old_source, new_source):
    assert _suite_structure({"tests/test_public.py": old_source}) != _suite_structure(
        {"tests/test_moved.py": new_source}
    )


def test_upgrade_can_deduplicate_checks_but_must_inherit_every_obligation():
    old_files = {"tests/test_public.py": SOURCE + "\ndef test_duplicate(trace): assert trace['ok']"}
    original = TestSuite(
        old_files,
        obligations=(
            {
                "id": "action",
                "requirement": "complete action",
                "checks": [
                    "tests/test_public.py::test_public",
                    "tests/test_public.py::test_duplicate",
                ],
                "evidence": ["complete action"],
            },
        ),
    )
    raw = {
        "files": [
            {
                "path": "tests/test_public.py",
                "content": SOURCE + "\ndef test_complete(trace): assert trace['complete']",
            }
        ],
        "obligations": [
            {
                "id": "action",
                "requirement": "complete action",
                "checks": ["tests/test_public.py::test_public"],
                "evidence": ["complete action"],
            },
            {
                "id": "complete",
                "requirement": "report completion",
                "checks": ["tests/test_public.py::test_complete"],
                "evidence": ["report completion"],
            },
        ],
        "change_notes": {
            "tests/test_public.py": {
                "reason": "merge duplicate assertion and add completion coverage",
                "evidence": ["complete action", "report completion"],
            }
        },
    }
    verifier = SurrogateVerifier(lambda _: raw, None)
    updated = verifier.create_suite(
        {"request": "complete action and report completion"}, FrozenBase((), {}), {}, original
    )
    assert (
        updated.obligations[0]["id"] == "action"
        and updated.inheritance[0]["obligation_id"] == "action"
    )
    raw["obligations"][0]["id"] = "replacement"
    with pytest.raises(ValueError, match="removed_or_changed_test_obligation"):
        verifier.create_suite(
            {"request": "complete action and report completion"}, FrozenBase((), {}), {}, original
        )


@pytest.mark.parametrize("grounded", [True, False])
def test_upgrade_corrects_check_scope_but_preserves_public_obligation(grounded):
    requirement = "Every item score is between 0 and 100."
    total_requirement = "Report the total as the sum of item scores."
    old_source = "def test_range(trace): assert 0 <= trace['total'] <= 100"
    original = TestSuite(
        {"tests/test_public.py": old_source},
        obligations=(
            {
                "id": "item-range",
                "requirement": requirement,
                "checks": ["tests/test_public.py::test_range"],
                "evidence": [requirement],
            },
        ),
    )
    raw = {
        "files": [
            {
                "path": "tests/test_public.py",
                "content": "def test_range(trace):\n"
                "    assert all(0 <= score <= 100 for score in trace['scores'])\n"
                "def test_total(trace):\n"
                "    assert trace['total'] == sum(trace['scores'])",
            }
        ],
        "obligations": [
            {
                **dict(original.obligations[0]),
                "checks": ["tests/test_public.py::test_range"],
                "evidence": ["public-scores", requirement],
            },
            {
                "id": "total",
                "requirement": total_requirement,
                "checks": ["tests/test_public.py::test_total"],
                "evidence": [total_requirement],
            },
        ],
        "change_notes": {
            "tests/test_public.py": {
                "reason": "Apply the range to individual items, not their aggregate.",
                "evidence": [requirement if grounded else "The total is limited to 100."],
            }
        },
    }
    inputs = {"document_id": "public-scores", "request": requirement + " " + total_requirement}
    verifier = SurrogateVerifier(lambda _: raw, None)
    if not grounded:
        with pytest.raises(ValueError, match="ungrounded_test_evidence"):
            verifier.create_suite(inputs, FrozenBase((), {}), {}, original)
        return
    updated = verifier.create_suite(inputs, FrozenBase((), {}), {}, original)
    assert updated.version == 1
    assert updated.obligations[0]["requirement"] == requirement
    assert updated.inheritance[0]["obligation_id"] == "item-range"
    assert "test_total" in updated.files["tests/test_public.py"]
    assert original.files["tests/test_public.py"] == old_source


def test_program_error_gets_one_repair_and_keeps_same_public_trace(tmp_path):
    calls, executions = [], []
    host_snapshot = str(tmp_path / "host-only-snapshot")
    trace = {"events": [], "public_artifacts_dir": host_snapshot}

    class Runner:
        def run_verifier(self, inputs, base, public_trace, files):
            executions.append((public_trace, dict(files)))
            return program("failed", exception="NameError", requirement_failure=False)

    def model(payload):
        calls.append(payload)
        return {"files": [{"path": "tests/test_public.py", "content": SOURCE}]}

    verifier = SurrogateVerifier(model, Runner(), journal=Journal(tmp_path / "journal"))
    report = verifier.verify({}, FrozenBase((), {}), trace, suite())
    assert report.program_error and report.suite.repairs == 1
    assert len(executions) == 2 and len(calls) == 1
    assert all(item[0] == trace for item in executions)
    assert host_snapshot not in str(calls)
    verifier.verify({}, FrozenBase((), {}), trace, report.suite, operation_id="next")
    assert len(calls) == 1 and len(executions) == 3


@pytest.mark.parametrize(
    "repair", ["def test_public(): assert True", "def test_renamed(trace): assert trace"]
)
def test_repair_cannot_turn_error_into_vacuous_or_renamed_check(repair):
    executions = []

    class Runner:
        def run_verifier(self, *args):
            executions.append(args)
            return program("failed", exception="NameError", requirement_failure=False)

    report = SurrogateVerifier(
        lambda _: {"files": [{"path": "tests/test_public.py", "content": repair}]}, Runner()
    ).verify({}, FrozenBase((), {}), {}, suite())
    assert report.program_error and report.failure == "test_repair_failed"
    assert (
        report.suite.files == suite().files and report.suite.repairs == 1 and len(executions) == 1
    )


def test_repair_cannot_reduce_parameter_cases():
    responses = iter(
        [
            program(
                "failed",
                ids=[
                    "tests/test_public.py::test_public[a]",
                    "tests/test_public.py::test_public[b]",
                ],
                exception="NameError",
                requirement_failure=False,
            ),
            program(ids=["tests/test_public.py::test_public[a]"]),
        ]
    )

    class Runner:
        def run_verifier(self, *args):
            return next(responses)

    report = SurrogateVerifier(
        lambda _: {"files": [{"path": "tests/test_public.py", "content": SOURCE}]}, Runner()
    ).verify({}, FrozenBase((), {}), {}, suite())
    assert (
        report.failure == "test_repair_failed"
        and "repair_removed_collected_checks" in report.diagnosis
    )
    assert len(report.results) == 2
    assert len(report.test_runs) == 2
    assert report.test_runs[0]["program"]["output"]["collected"] == 2
    assert report.test_runs[1]["program"]["output"]["collected"] == 1
    assert report.stage_failures[0]["reason"] == "repair_removed_collected_checks"
    assert report.stage_failures[0]["operation_id"] == "verification-repaired-tests"


def test_repair_rejection_retains_original_run_and_exact_metadata_error():
    original = TestSuite(suite().files, obligations=(submission()["obligations"][0],))

    class Runner:
        def run_verifier(self, *args):
            return program("failed", exception="NameError", requirement_failure=False)

    raw = submission()
    raw["obligations"][0]["requirement"] = "weakened requirement"
    raw["files"] = [{"path": "tests/test_public.py", "content": SOURCE}]
    report = SurrogateVerifier(lambda _: raw, Runner()).verify(
        {"request": "complete the action"}, FrozenBase((), {}), {}, original
    )
    assert report.failure == "test_repair_failed" and report.suite == TestSuite(
        original.files, repairs=1, obligations=original.obligations
    )
    assert report.results[0]["exception"] == "NameError"
    assert len(report.test_runs) == 1
    assert report.stage_failures == (
        {
            "stage": "repair",
            "operation_id": "verification-repair",
            "exception_type": "ValueError",
            "reason": "removed_or_changed_test_obligation",
            "detail": "ValueError: removed_or_changed_test_obligation",
        },
    )
    assert VerificationReport.from_dict(report.to_dict()).to_dict() == report.to_dict()


@pytest.mark.parametrize("repair", [False, True])
def test_current_pass_does_not_repeat_previous_failure_diagnosis(repair):
    stale = TestSuite(
        suite().files,
        diagnosis="four pass, plaintiff-name fails",
        recommendations=("fill plaintiff-name",),
    )

    class Runner:
        calls = 0

        def run_verifier(self, *args):
            self.calls += 1
            if repair and self.calls == 1:
                return program("failed", exception="NameError", requirement_failure=False)
            return program()

    report = SurrogateVerifier(
        lambda _: {
            "files": [{"path": "tests/test_public.py", "content": SOURCE}],
            "diagnosis": stale.diagnosis,
            "recommendations": list(stale.recommendations),
        },
        Runner(),
    ).verify({}, FrozenBase((), {}), {}, stale)
    assert report.passed and report.diagnosis == "" and report.recommendations == ()
    assert len(report.test_runs) == 1 + int(repair)


def test_verification_report_legacy_audit_fields_default_to_empty():
    value = _report(suite(), program()).to_dict()
    del value["test_runs"]
    del value["stage_failures"]
    report = VerificationReport.from_dict(value)
    assert report.test_runs == report.stage_failures == ()


def _harness_program(tmp_path, source, trace=None):
    root = tmp_path / "public"
    tests = root / "tests"
    tests.mkdir(parents=True)
    for name in ("public_inputs", "base", "trace"):
        (root / f"{name}.json").write_text(json.dumps(trace or {}) if name == "trace" else "{}")
    (tests / "test_public.py").write_text(source)
    harness = tmp_path / "harness.py"
    harness.write_text(
        _PYTEST_HARNESS.replace(
            "ROOT = pathlib.Path('/bundle')", f"ROOT = pathlib.Path({str(root)!r})"
        )
    )
    completed = subprocess.run(
        [sys.executable, "-I", str(harness)],
        capture_output=True,
        timeout=20,
        env={"PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1", "PYTHONDONTWRITEBYTECODE": "1"},
    )
    return _program_result(
        ProcessResult(completed.returncode, completed.stdout, completed.stderr)
    ), tests


@pytest.mark.parametrize("failure_source", ["raise Custom('missing')", "pytest.fail('missing')"])
def test_real_harness_recognizes_requirement_failure_subclasses_and_pytest_fail(
    tmp_path, failure_source
):
    source = (
        "import pytest\nclass Custom(AssertionError): pass\ndef test_public():\n    "
        + failure_source
    )
    output, tests = _harness_program(tmp_path, source)
    assert output.exit_code == 1 and output.failure == "nonzero_exit"
    report = _report(TestSuite({"tests/test_public.py": source}), output)
    assert not report.passed and not report.program_error
    assert report.results[0]["requirement_failure"] is True
    assert not list(tests.rglob("__pycache__"))


def test_harness_report_survives_known_serializer_monkeypatch(tmp_path):
    spoof = json.dumps(program().output)
    source = (
        "import json\ndef test_public(trace):\n"
        f" json.dumps = lambda *args, **kwargs: {spoof!r}\n"
        f" json.JSONEncoder.encode = lambda *args, **kwargs: {spoof!r}\n"
        " assert trace['ok']"
    )
    _validate_test_source({"tests/test_public.py": source})
    measured, _ = _harness_program(tmp_path, source, {"ok": False})
    assert measured.exit_code == measured.output["exit_code"] == 1
    assert measured.failure == "nonzero_exit"
    assert measured.output["results"][0]["outcome"] == "failed"
    assert "AssertionError" in measured.stderr
    report = _report(TestSuite({"tests/test_public.py": source}), measured)
    assert not report.passed and not report.program_error


class PublicRunner:
    def __init__(self):
        self.commands = []
        self.sessions = []
        self.results = []

    @contextmanager
    def public_verifier_session(
        self, inputs, base, trace, files=None, readonly_tests=False, **kwargs
    ):
        with _public_workspace(
            self,
            inputs,
            base,
            trace=trace,
            test_files=files,
            readonly_tests=readonly_tests,
            **kwargs,
        ) as session:
            self.sessions.append((session, readonly_tests))
            yield session

    def _terminal(self, package, work, command):
        self.commands.append(command)
        if command == "write checks":
            (work / "tests/test_public.py").write_text(SOURCE)
        elif command == "inspect public":
            assert (package / "public_inputs.json").is_file() and not (
                package / "SKILL.md"
            ).exists()
        elif command == "scratch":
            (work / "scratch/note").write_text("debug state")
        return ProgramResult(0, {"stdout": "public file inspected", "stderr": ""})

    def _run(self, package, work, args):
        return self.results.pop(0) if self.results else program()

    def run_verifier(self, *args):
        return program("failed")


def call(name, arguments, identifier="tool-1"):
    return {
        "content": "",
        "tool_calls": [
            {
                "id": identifier,
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(arguments)},
            }
        ],
        "finish_reason": "tool_calls",
    }


def submission():
    return {
        "diagnosis": "checked public action",
        "recommendations": [],
        "obligations": [
            {
                "id": "action",
                "requirement": "complete the action",
                "checks": ["tests/test_public.py::test_public"],
                "evidence": ["complete the action"],
            }
        ],
    }


class ToolModel:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []

    def complete(self, messages, **kwargs):
        self.requests.append((json.loads(json.dumps(messages)), kwargs))
        return next(self.responses)


@pytest.mark.parametrize("tool", ["terminal", "run_tests", "submit_tests"])
def test_known_cleanup_failure_aborts_interactive_verifier_and_replay(tmp_path, tool):
    failure = ProgramResult(1, stderr="trusted cleanup failure", failure="cleanup_failed")

    class Runner(PublicRunner):
        def _terminal(self, package, work, command):
            if tool == "terminal":
                self.commands.append(command)
                return failure
            return super()._terminal(package, work, command)

    runner = Runner()
    if tool == "terminal":
        calls = [call("terminal", {"command": "inspect public"})["tool_calls"][0]]
    else:
        runner.results = [failure]
        calls = [call("terminal", {"command": "write checks"})["tool_calls"][0]]
        calls += [
            call(tool, submission() if tool == "submit_tests" else {}, "test-1")["tool_calls"][0]
        ]
    calls += [call("terminal", {"command": "must not execute"}, "later")["tool_calls"][0]]
    model = ToolModel([{"content": "", "tool_calls": calls}])
    journal = Journal(tmp_path / "journal")
    verifier = SurrogateVerifier(model, runner, journal=journal)
    tool_index = 0 if tool == "terminal" else 1
    identifier = f"verifier-initial-turn-0-tool-{tool_index}"
    for _ in range(2):
        with pytest.raises(ContainerUnavailable, match="verifier_cleanup_failed"):
            verifier.create_suite({"request": "complete the action"}, FrozenBase((), {}), {})
        assert journal.status(identifier) == "COMPLETED"
        assert journal.response(identifier)["program"]["failure"] == "cleanup_failed"
        assert runner.sessions[-1][0].cleanup_failed
        assert runner.sessions[-1][0].package.parent.exists()
    assert len(model.requests) == 1
    assert runner.commands == ["inspect public" if tool == "terminal" else "write checks"]


@pytest.mark.parametrize("phase", ["diagnosis", "repair"])
def test_cleanup_failure_cannot_be_swallowed_by_diagnosis_or_repair(tmp_path, phase):
    class Runner(PublicRunner):
        def _terminal(self, package, work, command):
            self.commands.append(command)
            return ProgramResult(1, stderr="trusted cleanup failure", failure="cleanup_failed")

        def run_verifier(self, *args):
            return program(
                "failed",
                exception="NameError" if phase == "repair" else "AssertionError",
                requirement_failure=phase != "repair",
            )

    runner = Runner()
    model = ToolModel([call("terminal", {"command": "inspect public"})])
    journal = Journal(tmp_path / "journal")
    verifier = SurrogateVerifier(model, runner, journal=journal)
    for _ in range(2):
        with pytest.raises(ContainerUnavailable, match="verifier_cleanup_failed"):
            verifier.verify({}, FrozenBase((), {}), {}, suite())
        assert journal.completed(f"verification-{phase}-turn-0-tool-0")
        assert runner.sessions[-1][0].cleanup_failed
    assert len(model.requests) == 1 and runner.commands == ["inspect public"]


def test_formal_test_cleanup_failure_is_sealed_without_repair_or_model_request(tmp_path):
    executions = []

    class Runner:
        def run_verifier(self, *args):
            executions.append(args)
            return ProgramResult(1, stderr="trusted cleanup failure", failure="cleanup_failed")

    model = ToolModel([])
    journal = Journal(tmp_path / "journal")
    verifier = SurrogateVerifier(model, Runner(), journal=journal)
    for _ in range(2):
        with pytest.raises(ContainerUnavailable, match="verifier_cleanup_failed"):
            verifier.verify({}, FrozenBase((), {}), {}, suite())
        assert journal.status("verification-tests") == "COMPLETED"
        assert journal.response("verification-tests")["failure"] == "cleanup_failed"
    assert len(executions) == 1 and model.requests == []


def test_interactive_verifier_inspects_actual_public_files_and_seals_tests(tmp_path):
    runner = PublicRunner()
    first = call("terminal", {"command": "inspect public"})
    first["usage"] = {"output_tokens": 12, "output_tokens_details": {"reasoning_tokens": 7}}
    first["_bedrock_output_items"] = [
        {"type": "reasoning", "summary": [], "encrypted_content": "verifier-private-state"}
    ]
    model = ToolModel(
        [
            first,
            call("terminal", {"command": "write checks"}),
            call("run_tests", {}),
            call("submit_tests", submission()),
        ]
    )
    verifier = SurrogateVerifier(model, runner, journal=Journal(tmp_path / "journal"))
    created = verifier.create_suite({"request": "complete the action"}, FrozenBase((), {}), {})
    assert created.files == suite().files and created.obligations[0]["id"] == "action"
    assert len(model.requests) == 4 and runner.commands == ["inspect public", "write checks"]
    assistant = next(item for item in model.requests[1][0] if item["role"] == "assistant")
    assert assistant["usage"]["output_tokens_details"]["reasoning_tokens"] == 7
    assert assistant["_bedrock_output_items"][0]["encrypted_content"] == "verifier-private-state"
    assert "verifier-private-state" not in json.dumps(created.to_dict())
    assert {tool["function"]["name"] for tool in model.requests[0][1]["tools"]} == {
        "terminal",
        "run_tests",
        "submit_tests",
    }
    calls_before = len(model.requests)
    replay = verifier.create_suite({"request": "complete the action"}, FrozenBase((), {}), {})
    assert replay.to_dict() == created.to_dict() and len(model.requests) == calls_before
    assert runner.commands == ["inspect public", "write checks"]


def test_interactive_initial_checks_can_be_debugged_before_sealing():
    runner = PublicRunner()
    runner.results = [
        program("failed", exception="NameError", requirement_failure=False),
        program(),
    ]
    model = ToolModel(
        [
            call("terminal", {"command": "write checks"}),
            call("run_tests", {}),
            call("submit_tests", submission()),
        ]
    )
    created = SurrogateVerifier(model, runner).create_suite(
        {"request": "complete the action"}, FrozenBase((), {}), {}
    )
    assert created.repairs == 0 and created.version == 0
    assert "NameError" in model.requests[-1][0][-1]["content"]


def test_active_skillsbench_prompt_reaches_model_with_corrected_verification_contract():
    prompt = (EXPERIMENT_ROOT / "prompts/verifier-skillsbench.md").read_text()
    model = ToolModel(
        [call("terminal", {"command": "write checks"}), call("submit_tests", submission())]
    )
    SurrogateVerifier(model, PublicRunner(), system_prompt=prompt).create_suite(
        {"request": "complete the action"}, FrozenBase((), {}), {}
    )
    sent = model.requests[0][0][0]
    assert sent == {"role": "system", "content": prompt}
    assert "heuristic unless the task expressly makes it mandatory" in sent["content"]
    assert "multiple reasonable preprocessing, phase, and duration choices" in sent["content"]
    assert "A rejected submission returns the specific reason" in sent["content"]
    assert "Diagnosis and recommendations describe the current measured run" in sent["content"]


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("diagnosis", 42, "invalid_test_diagnosis"),
        ("recommendations", [42], "invalid_test_recommendations"),
        ("diagnosis", None, "missing_test_submission_metadata"),
    ],
)
def test_interactive_submission_metadata_errors_can_be_corrected(field, value, reason):
    invalid = submission()
    if value is None:
        del invalid[field]
    else:
        invalid[field] = value
    model = ToolModel(
        [
            call("terminal", {"command": "write checks"}),
            call("submit_tests", invalid),
            call("submit_tests", submission()),
        ]
    )
    created = SurrogateVerifier(model, PublicRunner()).create_suite(
        {"request": "complete the action"}, FrozenBase((), {}), {}
    )
    assert created.files == suite().files and len(model.requests) == 3
    assert reason in model.requests[-1][0][-1]["content"]


@pytest.mark.parametrize(
    "violation,reason",
    [
        ("obligation", "removed_or_changed_test_obligation"),
        ("change_notes", "test_change_without_justification"),
        ("rename", "escalation_only_renamed_checks"),
        ("empty_cases", "escalation_added_no_collected_checks"),
    ],
)
def test_interactive_escalation_returns_full_validation_error_then_accepts_correction(
    violation, reason
):
    original = TestSuite(suite().files, obligations=(submission()["obligations"][0],))
    valid_source = SOURCE + "\ndef test_complete(trace): assert trace['complete']"
    if violation == "rename":
        invalid_source = SOURCE.replace("test_public", "test_renamed")
    elif violation == "empty_cases":
        invalid_source = (
            SOURCE + "\nimport pytest\n@pytest.mark.parametrize('value', [])\n"
            "def test_complete(value): assert value"
        )
    else:
        invalid_source = valid_source

    class Runner(PublicRunner):
        def _terminal(self, package, work, command):
            (work / "tests/test_public.py").write_text(
                invalid_source if command == "invalid upgrade" else valid_source
            )
            return ProgramResult(0, {})

        def _run(self, package, work, args):
            source = (work / "tests/test_public.py").read_text()
            ids = ["tests/test_public.py::test_public"]
            if source == valid_source:
                ids.append("tests/test_public.py::test_complete")
            return program(ids=ids)

    valid = submission()
    valid["obligations"][0]["checks"].append("tests/test_public.py::test_complete")
    valid["change_notes"] = {
        "tests/test_public.py": {"reason": "check completion", "evidence": ["complete the action"]}
    }
    invalid = json.loads(json.dumps(valid))
    if violation == "obligation":
        invalid["obligations"][0]["requirement"] = "weakened action"
    elif violation == "change_notes":
        del invalid["change_notes"]
    elif violation == "rename":
        invalid["obligations"][0]["checks"] = ["tests/test_public.py::test_renamed"]
    model = ToolModel(
        [
            call("terminal", {"command": "invalid upgrade"}),
            call("submit_tests", invalid),
            call("terminal", {"command": "valid upgrade"}),
            call("submit_tests", valid),
        ]
    )
    upgraded = SurrogateVerifier(model, Runner()).create_suite(
        {"request": "complete the action"}, FrozenBase((), {}), {}, original
    )
    assert upgraded.version == 1 and upgraded.files["tests/test_public.py"] == valid_source
    rejected = json.loads(model.requests[2][0][-1]["content"])
    assert rejected == {"failure": "ValueError", "detail": reason}
    assert upgraded.obligations[0]["requirement"] == original.obligations[0]["requirement"]
    assert len(model.requests) == 4


def test_interactive_repair_can_correct_obligation_error_before_sealing():
    original = TestSuite(suite().files, obligations=(submission()["obligations"][0],))
    invalid = submission()
    invalid["obligations"][0]["requirement"] = "weakened action"

    class Runner(PublicRunner):
        calls = 0

        def run_verifier(self, *args):
            self.calls += 1
            return (
                program("failed", exception="NameError", requirement_failure=False)
                if self.calls == 1
                else program()
            )

    model = ToolModel([call("submit_tests", invalid), call("submit_tests", submission())])
    report = SurrogateVerifier(model, Runner()).verify(
        {"request": "complete the action"}, FrozenBase((), {}), {}, original
    )
    assert report.passed and report.suite.repairs == 1 and len(report.test_runs) == 2
    assert "removed_or_changed_test_obligation" in model.requests[1][0][-1]["content"]


def test_interactive_diagnosis_uses_readonly_tests_and_eight_turn_budget():
    runner = PublicRunner()
    model = ToolModel([call("terminal", {"command": "inspect public"})] * 8)
    report = SurrogateVerifier(model, runner).verify({}, FrozenBase((), {}), {}, suite())
    assert not report.passed and not report.program_error and report.suite == suite()
    assert len(model.requests) == 8 and runner.sessions[0][1] is True
    assert {tool["function"]["name"] for tool in model.requests[0][1]["tools"]} == {
        "terminal",
        "submit_diagnosis",
    }


def test_interactive_initial_turn_budget_is_thirty():
    runner = PublicRunner()
    model = ToolModel([call("terminal", {"command": "inspect public"})] * 30)
    with pytest.raises(ValueError, match="verifier_episode_budget_exhausted"):
        SurrogateVerifier(model, runner).create_suite({}, FrozenBase((), {}), {})
    assert len(model.requests) == 30


def test_thirty_turn_budget_exception_retains_every_known_submission_rejection():
    invalid = submission()
    invalid["recommendations"] = [42]
    model = ToolModel([call("submit_tests", invalid)] * 30)
    with pytest.raises(ValueError, match="verifier_episode_budget_exhausted") as raised:
        SurrogateVerifier(model, PublicRunner()).create_suite(
            {"request": "complete the action"}, FrozenBase((), {}), {}
        )
    assert len(model.requests) == len(raised.value.rejections) == 30
    rejection = raised.value.rejections[-1]
    assert rejection == {
        "stage": "test_submission",
        "operation_id": "verifier-initial-turn-29-tool-0",
        "exception_type": "ValueError",
        "reason": "invalid_test_recommendations",
        "detail": "ValueError: invalid_test_recommendations",
    }
    assert "rejections" not in model.requests[-1][0][-1]["content"]


def test_persistent_verifier_workspace_tampering_stops_replay(tmp_path):
    runner = PublicRunner()
    model = ToolModel(
        [call("terminal", {"command": "write checks"}), call("submit_tests", submission())]
    )
    verifier = SurrogateVerifier(model, runner, journal=Journal(tmp_path / "journal"))
    verifier.create_suite({"request": "complete the action"}, FrozenBase((), {}), {})
    runner.sessions[-1][0].target.joinpath("test_public.py").write_text("tampered")
    with pytest.raises(ValueError, match="verifier_workspace_snapshot_mismatch"):
        verifier.create_suite({"request": "complete the action"}, FrozenBase((), {}), {})
    assert runner.commands == ["write checks"] and len(model.requests) == 2


def test_test_suite_hash_covers_obligation_and_test_bytes():
    original = suite().to_dict()
    original["files"]["tests/test_public.py"] += "\n#tamper"
    with pytest.raises(ValueError, match="test_hash_mismatch"):
        TestSuite.from_dict(original)
    with_obligation = TestSuite(
        suite().files,
        obligations=(
            {
                "id": "public",
                "requirement": "a",
                "checks": ["tests/test_public.py::test_public"],
                "evidence": ["a"],
            },
        ),
    ).to_dict()
    with_obligation["obligations"][0]["requirement"] = "other"
    with pytest.raises(ValueError, match="test_hash_mismatch"):
        TestSuite.from_dict(with_obligation)
