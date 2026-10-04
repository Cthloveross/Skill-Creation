import json

import pytest
from tau_skill_evolution.artifacts import FrozenBase
from tau_skill_evolution.container import ProgramResult
from tau_skill_evolution.journal import Journal, UnknownOperation
from tau_skill_evolution.model import ModelClientError, authentication_status
from tau_skill_evolution.verifier import SurrogateVerifier, TestSuite, _report


def suite():
    return TestSuite({"tests/test_public.py": "def test_public(trace): assert trace['ok']"})


def program(outcome="passed", **extra):
    item = {
        "nodeid": "tests/test_public.py::test_public",
        "stage": "call",
        "outcome": outcome,
        "exception": "AssertionError" if outcome == "failed" else None,
        "xfail": False,
    }
    item.update(extra)
    return ProgramResult(
        0,
        {
            "collected": 1,
            "collection_errors": 0,
            "exit_code": 0 if outcome == "passed" else 1,
            "results": [item],
        },
    )


def test_nonempty_actual_pass_required():
    assert _report(suite(), program()).passed
    assert not _report(suite(), program("failed")).passed
    for invalid in (program("skipped"), program(xfail=True)):
        report = _report(suite(), invalid)
        assert not report.passed and report.program_error
        assert report.failure == "skip_or_xfail"
    assert _report(suite(), ProgramResult(0, {"collected": 0, "results": []})).program_error
    assert _report(suite(), ProgramResult(1, failure="nonzero_exit")).program_error
    assert _report(suite(), program("failed", exception="NameError")).program_error


@pytest.mark.parametrize("status", [401, 403])
@pytest.mark.parametrize("test_error", [False, True])
def test_diagnosis_or_repair_auth_failure_propagates_without_another_model_request(
    tmp_path, status, test_error
):
    calls, executions = [], []

    class Runner:
        def run_verifier(self, *args):
            executions.append(args)
            return program("failed", exception="NameError" if test_error else "AssertionError")

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
    assert journal.completed("verification-tests")
    with pytest.raises(ModelClientError):
        verifier.create_suite({}, FrozenBase((), {}), {})
    assert len(calls) == 1


def test_escalation_preserves_checks_and_adds_files():
    original = suite()
    captured = []

    def model(payload):
        captured.append(payload)
        return {
            "files": [{"path": "tests/test_more.py", "content": "def test_more(): assert True"}]
        }

    verifier = SurrogateVerifier(model, None)
    updated = verifier.create_suite(
        {"task": "public"}, FrozenBase((), {}), {"events": []}, original
    )
    assert (
        updated.version == 1
        and updated.files["tests/test_public.py"] == original.files["tests/test_public.py"]
    )
    assert updated.test_hash != original.test_hash
    assert captured[0]["oracle_pass"] is False
    assert set(captured[0]) == {
        "action",
        "public_inputs",
        "frozen_base",
        "public_trace",
        "previous_tests",
        "oracle_pass",
    }


def test_escalation_cannot_replace_previous_checks():
    verifier = SurrogateVerifier(
        lambda _: {
            "files": [
                {"path": "tests/test_public.py", "content": "def test_public(): pass"},
                {"path": "tests/test_more.py", "content": "def test_more(): pass"},
            ]
        },
        None,
    )
    with pytest.raises(ValueError, match="escalation_changed_existing_test"):
        verifier.create_suite({}, FrozenBase((), {}), {}, suite())


def test_test_program_error_gets_one_repair_per_semantic_version():
    class Runner:
        calls = 0

        def run_verifier(self, *args):
            self.calls += 1
            return program("failed", exception="NameError")

    calls = []

    def model(payload):
        calls.append(payload)
        return {
            "files": [
                {"path": "tests/test_public.py", "content": "def test_public(): assert False"}
            ]
        }

    runner = Runner()
    verifier = SurrogateVerifier(model, runner)
    report = verifier.verify({}, FrozenBase((), {}), {}, suite())
    assert report.program_error and report.suite.repairs == 1
    assert runner.calls == 2 and len(calls) == 1
    again = verifier.verify({}, FrozenBase((), {}), {}, report.suite)
    assert again.program_error and runner.calls == 3 and len(calls) == 1


def test_skill_failure_keeps_test_hash_and_generates_public_diagnosis():
    class Runner:
        def run_verifier(self, *args):
            return program("failed")

    captures = []

    def model(payload):
        captures.append(payload)
        return {"diagnosis": "bank action missing", "recommendations": ["use supported tool"]}

    original = suite()
    report = SurrogateVerifier(model, Runner()).verify({}, FrozenBase((), {}), {}, original)
    assert report.suite.test_hash == original.test_hash
    assert report.diagnosis == "bank action missing"
    assert report.recommendations == ("use supported tool",)
    assert captures[0]["action"] == "diagnosis"


def test_test_suite_hash_tampering_rejected():
    value = suite().to_dict()
    value["files"]["tests/test_public.py"] += "\n#tamper"
    with pytest.raises(ValueError, match="test_hash_mismatch"):
        TestSuite.from_dict(value)


def test_artifact_snapshot_is_host_only_and_same_snapshot_is_used_for_one_repair(tmp_path):
    requests, executions = [], []
    host_snapshot = str(tmp_path / "sealed-public-artifacts")
    trace = {
        "events": [
            {"actor": "assistant", "kind": "artifact", "payload": {"path": "mass_report.json"}}
        ],
        "public_artifacts_dir": host_snapshot,
        "public_input_manifest": [{"path": "scan_data.stl", "sha256": "public-input-hash"}],
    }

    class Runner:
        def run_verifier(self, inputs, base, public_trace, files):
            executions.append((public_trace, dict(files)))
            assert public_trace["public_artifacts_dir"] == host_snapshot
            return program("failed", exception="NameError") if len(executions) == 1 else program()

    def model(payload):
        requests.append(payload)
        return {
            "files": [
                {"path": "tests/test_public.py", "content": "def test_public(): assert True"}
            ],
            "diagnosis": "repair local test helper import",
        }

    journal = Journal(tmp_path / "journal")
    verifier = SurrogateVerifier(model, Runner(), journal=journal)
    initial = verifier.create_suite({"instruction": "public"}, FrozenBase((), {}), trace)
    report = verifier.verify({"instruction": "public"}, FrozenBase((), {}), trace, initial)
    assert report.passed and report.suite.repairs == 1 and report.suite.version == 0
    assert len(executions) == 2
    assert all(captured[0] == trace for captured in executions)
    assert all("public_artifacts_dir" not in request["public_trace"] for request in requests)
    assert host_snapshot not in str(requests)
    records = [json.loads(path.read_text()) for path in journal.root.glob("*/request.json")]
    execute_requests = [
        record for record in records if record["payload"].get("action") == "execute_tests"
    ]
    assert len(execute_requests) == 2
    assert all(
        record["payload"]["public_artifacts_dir"] == host_snapshot for record in execute_requests
    )


def test_diagnosed_extractor_assertion_repaired_once_on_same_trace_and_journal_replay(tmp_path):
    original = suite()
    public_inputs = {"read_only_observations": [{"result": "1. Record ID: example"}]}
    base = FrozenBase((), public_inputs)
    trace = {"events": [{"actor": "assistant", "kind": "message", "payload": {"content": "ok"}}]}
    executions = []
    requests = []

    class Runner:
        def run_verifier(self, inputs, frozen, public_trace, files):
            executions.append((inputs, frozen, public_trace, dict(files)))
            return program("failed") if len(executions) == 1 else program()

    def model(payload):
        requests.append(payload)
        if payload["action"] == "diagnosis":
            return {"test_program_error": True, "diagnosis": "extractor misread a numbered heading"}
        assert payload["action"] == "repair"
        assert payload["test_results"]["program_error"] is True
        return {
            "files": [
                {"path": "tests/test_public.py", "content": "def test_public(trace): assert trace"}
            ],
            "diagnosis": "fixed extraction without removing the public obligation",
        }

    journal = Journal(tmp_path / "journal")
    verifier = SurrogateVerifier(model, Runner(), journal=journal)
    report = verifier.verify(public_inputs, base, trace, original)
    assert report.passed and report.pass_rate == 1
    assert report.suite.version == original.version and report.suite.repairs == 1
    assert report.suite.test_hash != original.test_hash
    assert [r["action"] for r in requests] == ["diagnosis", "repair"]
    assert len(executions) == 2 and executions[0][:3] == executions[1][:3]
    first = journal.response("verification-tests")["output"]["results"]
    repaired = journal.response("verification-repaired-tests")["output"]["results"]
    assert first[0]["outcome"] == "failed" and repaired[0]["outcome"] == "passed"
    restored = SurrogateVerifier(model, Runner(), journal=Journal(tmp_path / "journal"))
    assert restored.verify(public_inputs, base, trace, original).to_dict() == report.to_dict()
    assert len(executions) == 2 and len(requests) == 2


@pytest.mark.parametrize("flag", [False, None, 1, "true", [], {}])
def test_only_explicit_json_true_reclassifies_a_measured_assertion(flag):
    calls = []

    class Runner:
        def run_verifier(self, *args):
            calls.append("execute")
            return program("failed")

    def model(payload):
        calls.append(payload["action"])
        return {"test_program_error": flag, "diagnosis": "ordinary public requirement missing"}

    original = suite()
    report = SurrogateVerifier(model, Runner()).verify({}, FrozenBase((), {}), {}, original)
    assert not report.passed and not report.program_error
    assert report.results[0]["outcome"] == "failed" and report.suite == original
    assert calls == ["execute", "diagnosis"]


def test_optional_diagnosis_error_does_not_erase_measured_failure():
    class Runner:
        def run_verifier(self, *args):
            return program("failed")

    def model(_):
        raise ValueError("unusable diagnosis")

    original = suite()
    report = SurrogateVerifier(model, Runner()).verify({}, FrozenBase((), {}), {}, original)
    assert report.suite == original and not report.program_error
    assert report.results[0]["outcome"] == "failed"


def test_repaired_skill_failure_uses_repair_advice_without_second_diagnosis():
    calls = []

    class Runner:
        def run_verifier(self, *args):
            calls.append("execute")
            return program(
                "failed", exception="NameError" if calls.count("execute") == 1 else "AssertionError"
            )

    def model(payload):
        calls.append(payload["action"])
        return {
            "files": [
                {
                    "path": "tests/test_public.py",
                    "content": "def test_public(trace): assert trace['ok']",
                }
            ],
            "diagnosis": "test now executes; public bank action is missing",
            "recommendations": ["perform the public bank action"],
        }

    report = SurrogateVerifier(model, Runner()).verify({}, FrozenBase((), {}), {}, suite())
    assert not report.passed and not report.program_error and report.suite.repairs == 1
    assert report.recommendations == ("perform the public bank action",)
    assert calls == ["execute", "repair", "execute"]


@pytest.mark.parametrize(
    ("old_source", "new_source"),
    [
        ("def test_public(): pass\ndef test_other(): pass", "def test_public(): pass"),
        ("def test_public(): pass", "def test_renamed(): pass"),
        (
            "class Case:\n    async def test_public(self): pass",
            "class Case:\n    def helper(self): pass",
        ),
        (
            "class Case:\n    def test_public(self): pass",
            "class Other:\n    def test_public(self): pass",
        ),
    ],
)
def test_repair_cannot_delete_or_rename_declared_checks(old_source, new_source):
    original = TestSuite({"tests/test_public.py": old_source})
    executions = []

    class Runner:
        def run_verifier(self, *args):
            executions.append(1)
            return program("failed", exception="NameError")

    verifier = SurrogateVerifier(
        lambda _: {"files": [{"path": "tests/test_public.py", "content": new_source}]}, Runner()
    )
    report = verifier.verify({}, FrozenBase((), {}), {}, original)
    assert report.program_error and report.failure == "test_repair_failed"
    assert "repair_removed_declared_checks" in report.diagnosis
    assert report.suite.files == original.files and report.suite.repairs == 1
    assert len(executions) == 1 and report.results[0]["outcome"] == "failed"


def parametrized_program(ids, *, outcome="passed", stage="call"):
    results = [
        {
            "nodeid": f"tests/test_public.py::test_public[{value}]",
            "stage": stage,
            "outcome": outcome,
            "exception": "NameError" if outcome == "failed" else None,
            "xfail": False,
        }
        for value in ids
    ]
    return ProgramResult(
        0,
        {
            "collected": len(ids),
            "collection_errors": 0,
            "exit_code": 0 if outcome == "passed" else 1,
            "results": results,
        },
    )


def test_repair_cannot_reduce_collected_parametrized_cases():
    original = suite()
    responses = iter(
        [parametrized_program(["a", "b"], outcome="failed"), parametrized_program(["a"])]
    )

    class Runner:
        def run_verifier(self, *args):
            return next(responses)

    repaired_source = "def test_public(trace): assert trace"
    verifier = SurrogateVerifier(
        lambda _: {"files": [{"path": "tests/test_public.py", "content": repaired_source}]},
        Runner(),
    )
    report = verifier.verify({}, FrozenBase((), {}), {}, original)
    assert report.program_error and report.failure == "test_repair_failed"
    assert "repair_removed_collected_checks" in report.diagnosis
    assert report.suite.files == original.files and report.suite.repairs == 1
    assert len(report.results) == 2 and all(r["outcome"] == "failed" for r in report.results)


def test_repair_may_change_parameter_labels_while_preserving_cases():
    responses = iter(
        [
            parametrized_program(["old::a", "old[b]"], outcome="failed"),
            parametrized_program(["new::a", "new[b]"]),
        ]
    )

    class Runner:
        def run_verifier(self, *args):
            return next(responses)

    verifier = SurrogateVerifier(
        lambda _: {
            "files": [{"path": "tests/test_public.py", "content": "def test_public(): assert True"}]
        },
        Runner(),
    )
    report = verifier.verify({}, FrozenBase((), {}), {}, suite())
    assert report.passed and report.suite.repairs == 1


def test_repair_cannot_transfer_parametrized_cases_between_checks():
    original = TestSuite({"tests/test_public.py": "def test_a(): pass\ndef test_b(): pass"})
    first = parametrized_program(["1", "2", "3"], outcome="failed")
    second = parametrized_program(["x", "y", "z"])
    for row, name in zip(
        first.output["results"], ["test_a[1]", "test_a[2]", "test_b[1]"], strict=True
    ):
        row["nodeid"] = "tests/test_public.py::" + name
    for row, name in zip(
        second.output["results"], ["test_a[x]", "test_b[y]", "test_b[z]"], strict=True
    ):
        row["nodeid"] = "tests/test_public.py::" + name
    responses = iter([first, second])

    class Runner:
        def run_verifier(self, *args):
            return next(responses)

    verifier = SurrogateVerifier(
        lambda _: {
            "files": [
                {"path": "tests/test_public.py", "content": original.files["tests/test_public.py"]}
            ]
        },
        Runner(),
    )
    report = verifier.verify({}, FrozenBase((), {}), {}, original)
    assert report.program_error and "repair_removed_collected_checks" in report.diagnosis
    assert report.suite.files == original.files and report.suite.repairs == 1


def test_repair_preserves_check_identities_reported_only_at_setup():
    original = suite()
    first = parametrized_program(["setup-only"], outcome="failed", stage="setup")
    second = program()
    second.output["results"][0]["nodeid"] = "tests/test_public.py::test_other"
    responses = iter([first, second])

    class Runner:
        def run_verifier(self, *args):
            return next(responses)

    verifier = SurrogateVerifier(
        lambda _: {
            "files": [
                {
                    "path": "tests/test_public.py",
                    "content": "def test_public(): pass\ndef test_other(): pass",
                }
            ]
        },
        Runner(),
    )
    report = verifier.verify({}, FrozenBase((), {}), {}, original)
    assert report.program_error and "repair_removed_collected_checks" in report.diagnosis
    assert report.suite.files == original.files and report.suite.repairs == 1


def test_verifier_reported_program_error_cannot_repair_twice():
    calls = []

    class Runner:
        def run_verifier(self, *args):
            calls.append("execute")
            return program("failed")

    verifier = SurrogateVerifier(
        lambda payload: calls.append(payload["action"]) or {"test_program_error": True}, Runner()
    )
    original = TestSuite(suite().files, repairs=1)
    report = verifier.verify({}, FrozenBase((), {}), {}, original)
    assert report.program_error and report.suite == original
    assert calls == ["execute", "diagnosis"]
