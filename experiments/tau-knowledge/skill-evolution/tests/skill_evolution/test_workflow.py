from __future__ import annotations

import copy
import json
import shutil
from contextlib import contextmanager

import pytest
from tau_skill_evolution import cli
from tau_skill_evolution.artifacts import (
    FrozenBase,
    SkillBundle,
    atomic_json,
    load_base,
    load_bundle,
    seal_bundle,
)
from tau_skill_evolution.container import ProgramResult
from tau_skill_evolution.evolution import EvolutionResult
from tau_skill_evolution.generator import SKILL_BUNDLE_RESPONSE_FORMAT
from tau_skill_evolution.journal import Journal
from tau_skill_evolution.model import ModelClientError
from tau_skill_evolution.spec import DEFAULT_CONFIG, ExperimentSpec, load_spec
from tau_skill_evolution.workflow import Workflow

DOCUMENT = {"page_id": "policy", "title": "Public Policy", "content": "Use the current user ID."}


def _gold_upstream(root, tasks):
    directory = root / "data/tau2/domains/banking_knowledge/tasks"
    directory.mkdir(parents=True)
    for task in tasks:
        atomic_json(directory / f"{task}.json", {"required_documents": [DOCUMENT["page_id"]]})
    return root


@pytest.fixture(autouse=True)
def gold_metadata(tmp_path, monkeypatch):
    upstream = _gold_upstream(tmp_path / "upstream", load_spec().tasks)
    original = ExperimentSpec.upstream.fget
    monkeypatch.setattr(
        ExperimentSpec,
        "upstream",
        property(lambda self: upstream if self.experiment == "tau" else original(self)),
    )


class Corpus:
    def __init__(self, log):
        self.log = log

    def search_web(self, query):
        self.log.append(("search", query))
        return {
            "results": [DOCUMENT, {"page_id": "unselected", "title": "Unused", "content": "unused"}]
        }

    def close(self):
        self.log.append(("corpus_closed",))


class Bank:
    tool_schemas = [
        {"type": "function", "function": {"name": "get_current_time"}},
        {"type": "function", "function": {"name": "write_bank_action"}},
    ]

    def __init__(self, log, metrics):
        self.log, self.metrics = log, metrics

    @contextmanager
    def acquisition(self):
        self.log.append(("acquire",))

        class Session:
            public_inputs = {"opening_message": "Help with my account"}
            tool_schemas = Bank.tool_schemas

            def read(self, name, arguments):
                if name == "get_current_time":
                    return {"current_time": "2026-11-14T12:00:00Z"}
                pytest.fail("this task requires no additional bank observations")

            def clarify(self, question):
                pytest.fail("this task requires no clarification")

        yield Session()

    def evaluate(self, bundle):
        self.log.append(("evaluate", bundle.bundle_hash))
        return self.metrics


def _workflow(tmp_path, *, output=None, metrics=None, experiment="tau"):
    spec = load_spec(
        DEFAULT_CONFIG if experiment == "tau" else DEFAULT_CONFIG.parent / "skillsbench.yaml"
    )
    log, requests = [], []

    def model_factory(role):
        def model(payload):
            requests.append((role, copy.deepcopy(payload)))
            if role == "analyzer":
                selected = ["policy"] if payload["returned_documents"] else []
                return {
                    "gaps": [] if selected else ["policy"],
                    "action": {"kind": "freeze"}
                    if selected
                    else {"kind": "search", "query": "account policy"},
                    "evidence": [{"requirement": "bank task", "document_id": "policy"}]
                    if selected
                    else [],
                    "document_scores": [
                        {
                            "document_id": item["document_id"],
                            "confidence": 0.8 if item["document_id"] in selected else 0,
                            "reason": "Relevant policy"
                            if item["document_id"] in selected
                            else "Unrelated document",
                        }
                        for item in payload["returned_documents"]
                    ],
                    "sufficient": bool(selected),
                    "coverage": {
                        name: selected
                        for name in ("policies", "tools", "parameters", "preconditions")
                    },
                    "conflicts": [],
                }
            assert role == "generator"
            if callable(output):
                return output(payload)
            return (
                output
                if output is not None
                else {"files": [{"path": "SKILL.md", "content": "bank instructions"}]}
            )

        return model

    workflow = Workflow(
        spec,
        tmp_path / "run",
        bank_factory=lambda _: Bank(log, metrics or {"utility": 1.0, "asr": 0.0}),
        model_factory=model_factory,
        corpus_factory=lambda task, arm: Corpus(log),
        counter=len,
    )
    return workflow, log, requests


@pytest.mark.parametrize("experiment", ["tau", "skillsbench"])
@pytest.mark.parametrize("role", ["analyzer", "generator", "verifier", "execution"])
def test_only_generator_client_uses_strict_package_response_format(
    tmp_path, monkeypatch, experiment, role
):
    spec = load_spec(
        DEFAULT_CONFIG if experiment == "tau" else DEFAULT_CONFIG.parent / "skillsbench.yaml"
    )
    monkeypatch.setenv(spec.provider_settings["api_key_env"], "offline-placeholder")
    workflow = Workflow(spec, tmp_path / "run", counter=len)
    client = workflow._model(role)
    assert client.config.response_format == (
        SKILL_BUNDLE_RESPONSE_FORMAT if role == "generator" else None
    )
    assert client.usage_history == ()


def test_complete_bundle_json_with_trailing_garbage_fails_creation_without_retry(tmp_path):
    raw = json.dumps({"files": [{"path": "SKILL.md", "content": "instructions"}]}) + "]}"
    workflow, _, requests = _workflow(tmp_path, output=raw)
    cell = (workflow.spec.tasks[0], "benign")
    workflow.create((cell,))
    workflow.create((cell,))
    root, journal = workflow._cell(*cell)
    assert [role for role, _ in requests].count("generator") == 1
    assert journal.response("generate_initial") == raw
    assert journal.result("generate_initial")["reason"] == "invalid_package"
    assert journal.response("creation")["status"] == "CREATION_FAILED"
    assert not (root / "initial").exists()


def test_skillsbench_uses_shared_creation_and_domain_specific_reports(tmp_path):
    workflow, log, requests = _workflow(
        tmp_path,
        experiment="skillsbench",
        metrics={
            "utility": True,
            "reward": 1.0,
            "asr": None,
            "asr_status": "NOT_APPLICABLE",
            "official_checks": {"status": "MEASURED", "passed": 2, "total": 2, "rate": 1.0},
        },
    )
    cells = (("3d-scan-calc", "benign"),)
    workflow.create(cells)
    assert requests[0][1]["allowed_read_only_tools"] == []
    assert requests[0][1]["remaining"]["clarify"] == 0
    learning_requests = copy.deepcopy(requests)
    workflow.evaluate(cells)
    workflow.evaluate(cells)
    report = workflow.report()
    assert len(report["cases"]) == 85 and len(report["versions"]) == 1
    assert report["arms"][0]["task_denominator"] == 85
    assert report["arms"][0]["measured_asr"] is None
    assert [role for role, _ in requests].count("generator") == 1
    assert requests == learning_requests
    text = (workflow.root / "REPORT.md").read_text()
    assert "Official check rate" in text and "Reference matched" not in text
    assert "ASR mean" not in text and "Reference action checks" not in text
    assert len([event for event in log if event[0] == "evaluate"]) == 1


def test_create_resume_never_repeats_s0_or_reopens_corpus(tmp_path):
    workflow, log, requests = _workflow(tmp_path)
    cell = (workflow.spec.tasks[0], "benign")
    workflow.create((cell,))
    before = copy.deepcopy((log, requests))
    workflow.create((cell,))
    assert (log, requests) == before
    assert [role for role, _ in requests].count("generator") == 1
    generator_payload = requests[-1][1]
    assert [doc["document_id"] for doc in generator_payload["frozen_base"]["documents"]] == [
        "policy"
    ]
    assert "unselected" not in json.dumps(generator_payload)
    assert [tool["function"]["name"] for tool in requests[0][1]["tool_schemas"]] == [
        "get_current_time"
    ]


def test_new_authenticated_invocation_skips_failed_chain_without_retrying_s0(tmp_path):
    def rejected_s0(payload):
        raise ModelClientError("http_error", "redacted", status=401)

    workflow, _, requests = _workflow(tmp_path, output=rejected_s0)
    cells = tuple((task, "benign") for task in workflow.spec.tasks[:2])
    with pytest.raises(ModelClientError, match="authentication"):
        workflow.run(cells)
    assert [role for role, _ in requests].count("generator") == 1
    assert not (workflow.root / "cells" / cells[1][0]).exists()
    # Reusing this invocation cannot bypass its newly observed failure.
    with pytest.raises(ModelClientError, match="authentication"):
        workflow.run(cells)
    assert [role for role, _ in requests].count("generator") == 1

    resumed, _, new_requests = _workflow(tmp_path)
    evolved = []
    resumed.evolve = lambda selected: evolved.extend(selected)
    report = resumed.run(cells)
    assert evolved == [cells[1]]
    assert [role for role, _ in new_requests].count("generator") == 1
    cases = {case["task_id"]: case for case in report["cases"] if case["condition"] == "benign"}
    assert cases[cells[0][0]]["status"] == "CREATION_FAILED"
    assert cases[cells[0][0]]["authentication_status"] == 401
    assert cases[cells[0][0]]["evaluations"] == {}
    assert cases[cells[1][0]]["status"] == "CREATED"
    assert len(cases[cells[1][0]]["evaluations"]) == 1


def test_restore_after_s0_seal_before_phase_result_never_resends(tmp_path, monkeypatch):
    workflow, log, requests = _workflow(tmp_path)
    cell = (workflow.spec.tasks[0], "benign")
    original_dispatch = Journal.dispatch

    def interrupt(journal, operation, payload, callback):
        if operation == "creation":
            raise KeyboardInterrupt()
        return original_dispatch(journal, operation, payload, callback)

    monkeypatch.setattr(Journal, "dispatch", interrupt)
    with pytest.raises(KeyboardInterrupt):
        workflow.create((cell,))
    root, _ = workflow._cell(*cell)
    assert load_base(root / "base") and load_bundle(root / "initial")
    before = copy.deepcopy((log, requests))
    monkeypatch.setattr(Journal, "dispatch", original_dispatch)
    workflow.create((cell,))
    assert (log, requests) == before
    assert workflow.report()["cases"][0]["status"] == "CREATED"


def test_creation_failure_keeps_full_denominator_and_null_measurements(tmp_path):
    workflow, log, requests = _workflow(tmp_path, output="unparseable")
    cell = (workflow.spec.tasks[0], "benign")
    workflow.create((cell,))
    workflow.create((cell,))
    workflow.evaluate((cell,))
    report = workflow.report()
    case = report["cases"][0]
    assert case["status"] == "CREATION_FAILED" and case["versions"] == []
    assert case["evaluations"] == {}
    assert len(report["cases"]) == 291
    benign = next(arm for arm in report["arms"] if arm["condition"] == "benign")
    assert benign["task_denominator"] == 97
    assert benign["measured_count"] == 0 and benign["not_measured_count"] == 97
    assert benign["measured_utility"] is None and benign["measured_asr"] is None
    assert benign["end_to_end_utility"] == 0
    assert benign["actual_chains"] == 0
    assert [role for role, _ in requests].count("generator") == 1
    assert not any(item[0] == "evaluate" for item in log)


def test_polluted_frozen_control_aliases_exact_s0_independent_evaluation(tmp_path):
    workflow, log, requests = _workflow(tmp_path)
    cell = (workflow.spec.tasks[0], "poison-5")
    workflow.create((cell,))
    learning_requests = copy.deepcopy(requests)
    workflow.evaluate((cell,))
    workflow.evaluate((cell,))
    report = workflow.report()
    case = next(case for case in report["cases"] if (case["task_id"], case["condition"]) == cell)
    assert case["frozen_control_hash"] == case["initial_bundle_hash"] == case["final_bundle_hash"]
    assert len(case["evaluations"]) == 1 and len(case["versions"]) == 1
    assert case["gold_coverage"]["gold_count"] == 1
    assert case["gold_coverage"]["returned_recall"] == case["gold_coverage"]["base_recall"] == 1
    assert len([item for item in log if item[0] == "evaluate"]) == 1
    assert requests == learning_requests
    arms = [arm for arm in report["arms"] if arm["condition"] == "poison-5"]
    assert all(arm["measured_count"] == arm["actual_chains"] == 1 for arm in arms)
    assert all(arm["end_to_end_utility"] == 1 / 97 for arm in arms)


def test_invalid_evaluation_response_remains_unmeasured_and_reportable(tmp_path):
    workflow, _, _ = _workflow(tmp_path, metrics={"asr": 0.0})
    cell = (workflow.spec.tasks[0], "benign")
    workflow.create((cell,))
    workflow.evaluate((cell,))
    report = workflow.report()
    measurement = next(iter(report["cases"][0]["evaluations"].values()))
    assert measurement["status"] == "NOT_MEASURED"
    assert measurement["utility"] is None and measurement["asr"] is None


@pytest.mark.parametrize("artifact", ["base", "initial"])
def test_completed_creation_binds_artifacts_to_original_journal_hash(tmp_path, artifact):
    workflow, _, _ = _workflow(tmp_path)
    cell = (workflow.spec.tasks[0], "benign")
    workflow.create((cell,))
    root, _ = workflow._cell(*cell)
    if artifact == "base":
        original = load_base(root / "base")
        replacement = FrozenBase(original.documents, {"opening_message": "changed public input"})
        atomic_json(root / "base", replacement.to_dict())
    else:
        shutil.rmtree(root / "initial")
        seal_bundle(root / "initial", SkillBundle({"SKILL.md": "replaced but internally valid"}))
    with pytest.raises(ValueError, match="hash|binding|differ"):
        workflow.create((cell,))


def test_live_cli_cannot_construct_workflow_when_preflight_is_not_ready(
    tmp_path, monkeypatch, capsys
):
    admission = {
        "ready": False,
        "checks": [{"name": "docker_daemon", "ok": False}],
        "namespace": "tau.skill-evolution.v1",
    }
    monkeypatch.setattr(cli, "preflight", lambda _, **kwargs: admission)
    monkeypatch.setattr(
        cli, "Workflow", lambda *args, **kwargs: pytest.fail("live run must be blocked")
    )
    assert cli.main(["run", "--run-dir", str(tmp_path / "run")]) == 2
    assert json.loads(capsys.readouterr().out)["ready"] is False
    assert not (tmp_path / "run").exists()


def test_report_cli_needs_no_docker_upstream_or_model_calls(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "preflight", lambda _: pytest.fail("report is offline"))
    monkeypatch.setattr(Workflow, "_bank", lambda *args: pytest.fail("report cannot execute bank"))
    monkeypatch.setattr(Workflow, "_model", lambda *args: pytest.fail("report cannot call model"))
    assert cli.main(["report", "--run-dir", str(tmp_path / "run")]) == 0
    report = json.loads(capsys.readouterr().out)
    assert len(report["cases"]) == 291
    assert all(case["status"] == "NOT_MEASURED" for case in report["cases"])
    assert report["run_mode"] == "formal"
    assert not report["formal_matrix_result"]
    assert not report["execution"]["formal_matrix_result"]


def test_formal_report_requires_independent_measurement(tmp_path):
    workflow, _, _ = _workflow(tmp_path)
    cells = ((workflow.spec.tasks[0], "benign"),)
    workflow.create(cells)
    assert not workflow.report()["formal_matrix_result"]
    workflow.evaluate(cells)
    report = workflow.report()
    assert report["formal_matrix_result"]
    assert report["execution"]["formal_matrix_result"]


def test_full_workflow_alternates_tests_and_skills_then_resumes_without_side_effects(tmp_path):
    generated = []

    def package(payload):
        generated.append(payload)
        return {"files": [{"path": "SKILL.md", "content": f"instructions v{len(generated)}"}]}

    workflow, log, requests = _workflow(tmp_path, output=package)
    original_factory = workflow.model_factory

    def models(role):
        if role != "verifier":
            return original_factory(role)

        def verifier(payload):
            requests.append((role, copy.deepcopy(payload)))
            if payload["action"] == "diagnosis":
                return {"diagnosis": "Required public bank action missing"}
            name = payload["action"]
            return {
                "files": [
                    {
                        "path": f"tests/test_{name}.py",
                        "content": "def test_bank(trace): assert trace['events']",
                    }
                ]
            }

        return verifier

    class FreshBank(Bank):
        oracle_results = iter([False, True])

        def rollout(self, bundle):
            log.append(("rollout", bundle.bundle_hash))
            return {"events": [], "status": "completed"}

        def oracle(self, bundle):
            log.append(("oracle", bundle.bundle_hash))
            return next(self.oracle_results)

    class TestRunner:
        outcomes = iter([False, True, False, True])

        def run_verifier(self, inputs, base, trace, files):
            passed = next(self.outcomes)
            return ProgramResult(
                0,
                {
                    "collected": 1,
                    "collection_errors": 0,
                    "exit_code": 0 if passed else 1,
                    "results": [
                        {
                            "stage": "call",
                            "outcome": "passed" if passed else "failed",
                            "exception": None if passed else "AssertionError",
                        }
                    ],
                },
            )

    bank = FreshBank(log, {"utility": 1.0, "asr": 0.0})
    workflow.bank_factory = lambda _: bank
    workflow.model_factory = models
    workflow.runner = TestRunner()
    cells = ((workflow.spec.tasks[0], "poison-5"),)
    workflow.create(cells)
    workflow.evolve(cells)
    learning = copy.deepcopy(requests)
    workflow.evaluate(cells)
    report = workflow.report()
    case = next(case for case in report["cases"] if case["condition"] == "poison-5")
    assert case["stop_reason"] == "oracle_success"
    assert case["revision_attempts"] == case["oracle_calls"] == 2
    assert len(case["versions"]) == len(case["evaluations"]) == 3
    assert [check["test_version"] for check in case["verifications"]] == [0, 0, 1, 1]
    assert len({check["test_hash"] for check in case["verifications"]}) == 2
    assert [payload["phase"] for payload in generated] == ["create", "revise", "revise"]
    assert len({payload["frozen_base"]["base_hash"] for payload in generated}) == 1
    assert requests == learning
    hashes = [item[1] for item in log if item[0] == "rollout"]
    assert hashes[0] != hashes[1] == hashes[2] != hashes[3]
    markdown = (workflow.root / "REPORT.md").read_text()
    assert "NOT_MEASURED" in markdown and "Independent measurements" in markdown
    assert all(check["test_hash"] in markdown for check in case["verifications"])
    before = copy.deepcopy((log, requests))
    workflow.create(cells)
    workflow.evolve(cells)
    workflow.evaluate(cells)
    assert (log, requests) == before


def test_report_shows_independent_reference_actions_and_components_for_s0_and_final(tmp_path):
    workflow, log, requests = _workflow(tmp_path)
    cell = (workflow.spec.tasks[0], "benign")
    workflow.create((cell,))
    root, journal = workflow._cell(*cell)
    initial = load_bundle(root / "initial")
    final = SkillBundle({"SKILL.md": "revised instructions"}, parent_hash=initial.bundle_hash)
    seal_bundle(root / "versions" / final.bundle_hash, final)
    evolution = EvolutionResult(
        (initial, final), (), (), (True,), 1, "oracle_success", final.bundle_hash
    )
    journal.dispatch("evolution-result", {}, evolution.to_dict)

    def metrics(all_matched):
        return {
            # A DB-only alternative workflow may succeed despite unmatched reference calls.
            "utility": True,
            "asr": False,
            "reward_info": {
                "reward_basis": ["DB"],
                "db_check": {"db_match": True, "db_reward": 1.0},
                "action_checks": [
                    {
                        "action": {
                            "name": "get_user_information_by_id",
                            "requestor": "assistant",
                            "arguments": {"user_id": "demo-user"},
                        },
                        "action_match": True,
                    },
                    {
                        "action": {
                            "name": "update_transaction",
                            "requestor": "assistant",
                            "arguments": {"note": "Update | review\ncomplete"},
                        },
                        "action_match": all_matched,
                    },
                ],
                "communicate_checks": [
                    {
                        "info": "Explain the | adjustment",
                        "met": all_matched,
                        "justification": "Specific amount\nwas explained"
                        if all_matched
                        else "Missing",
                    }
                ],
                "env_assertions": [],
                "nl_assertions": None,
            },
        }

    class EvaluationBank(Bank):
        def evaluate(self, bundle):
            self.log.append(("evaluate", bundle.bundle_hash))
            return metrics(bundle.bundle_hash == final.bundle_hash)

    workflow.bank_factory = lambda _: EvaluationBank(log, {})
    learning = copy.deepcopy(requests)
    workflow.evaluate((cell,))
    report = workflow.report()
    assert requests == learning
    assert len([event for event in log if event[0] == "evaluate"]) == 2
    assert [row["completion_steps"]["rate"] for row in report["versions"]] == [0.5, 1.0]
    assert all(row["utility"] for row in report["versions"])
    markdown = (workflow.root / "REPORT.md").read_text()
    assert "S0" in markdown and "S1 / final" in markdown and "S2" not in markdown
    assert "Reference-action matching is separate from official utility" in markdown
    assert "valid alternative workflow" in markdown
    assert "Reference action checks" in markdown and "Official evaluation components" in markdown
    assert "Official communication checks" in markdown
    assert '"user_id": "demo-user"' in markdown
    assert '"note": "Update \\| review\\ncomplete"' in markdown
    assert "Explain the \\| adjustment" in markdown
    assert "Specific amount was explained" in markdown
    assert '["DB"] | True | 1 | NO_CHECKS | 0/1 | NOT_MEASURED' in markdown
    assert '["DB"] | True | 1 | NO_CHECKS | 1/1 | NOT_MEASURED' in markdown
    assert markdown.count("| update_transaction | assistant |") == 2
    assert "| update_transaction | assistant |" in markdown
    assert "| True |" in markdown and "| False |" in markdown


@pytest.mark.parametrize("reward_info", [None, {"action_checks": []}])
def test_report_keeps_unavailable_reference_checks_null_and_labels_s0_final_once(
    tmp_path, reward_info
):
    metrics = {"utility": False, "asr": False}
    if reward_info is not None:
        metrics["reward_info"] = reward_info
    workflow, _, requests = _workflow(tmp_path, metrics=metrics)
    cell = (workflow.spec.tasks[0], "poison-5")
    workflow.create((cell,))
    learning = copy.deepcopy(requests)
    workflow.evaluate((cell,))
    report = workflow.report()
    assert requests == learning
    assert len(report["versions"]) == 1
    match = report["versions"][0]["completion_steps"]
    assert match["status"] == "NOT_MEASURED"
    assert match["matched"] is match["expected"] is match["rate"] is None
    assert not match["steps"]
    markdown = (workflow.root / "REPORT.md").read_text()
    measurements = markdown.split("## Independent measurements", 1)[1].split(
        "## Reference action checks", 1
    )[0]
    assert measurements.count("S0 / final") == 1
    assert "| NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED |" in measurements
    assert "| 0 | 0 |" not in measurements and "| 1 | 1 |" not in measurements


@pytest.mark.parametrize("authentication", [True, False])
def test_report_preserves_attempted_unknown_evaluation_without_resending(tmp_path, authentication):
    workflow, log, _ = _workflow(tmp_path)
    cell = (workflow.spec.tasks[0], "benign")
    workflow.create((cell,))

    class FailedBank(Bank):
        def evaluate(self, bundle):
            self.log.append(("evaluate", bundle.bundle_hash))
            if authentication:
                raise ModelClientError("http_error", "redacted", status=401)
            raise RuntimeError("transport interrupted")

    workflow.bank_factory = lambda _: FailedBank(log, {})
    if authentication:
        with pytest.raises(ModelClientError):
            workflow.evaluate((cell,))
    else:
        workflow.evaluate((cell,))
    report = workflow.report()
    case = report["cases"][0]
    measurement = next(iter(case["evaluations"].values()))
    assert measurement["status"] == "NOT_MEASURED" and measurement["utility"] is None
    assert measurement["reason"] == (
        "authentication_failed" if authentication else "result_unknown"
    )
    if authentication:
        assert case["authentication_status"] == 401
        assert case["stop_reason"] == "authentication_failed"
    assert len([item for item in log if item[0] == "evaluate"]) == 1
    _, journal = workflow._cell(*cell)
    operation = f"evaluation-{case['initial_bundle_hash']}"
    assert journal.dispatched(operation) and not journal.completed(operation)
    workflow.report()
    assert len([item for item in log if item[0] == "evaluate"]) == 1
