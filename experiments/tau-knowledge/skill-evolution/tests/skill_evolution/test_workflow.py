from __future__ import annotations

import copy
import json
import shutil
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
import yaml
from tau_skill_evolution import cli
from tau_skill_evolution.artifacts import (
    EvolutionSubmission,
    FrozenBase,
    SkillBundle,
    atomic_json,
    load_base,
    load_bundle,
    seal_bundle,
)
from tau_skill_evolution.bank import BankWorkerError
from tau_skill_evolution.container import ContainerUnavailable, ProgramResult
from tau_skill_evolution.core._canonical import canonical_json_sha256
from tau_skill_evolution.evaluation import not_measured, report_cases
from tau_skill_evolution.evolution import EvolutionResult
from tau_skill_evolution.generator import SKILL_BUNDLE_RESPONSE_FORMAT
from tau_skill_evolution.journal import Journal, UnknownOperation
from tau_skill_evolution.model import CredentialError, ModelClientError
from tau_skill_evolution.spec import DEFAULT_CONFIG, SKILLSBENCH_CONFIG, ExperimentSpec, load_spec
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

    def __init__(self, log, metrics, *, experiment="tau"):
        self.log, self.metrics, self.experiment = log, metrics, experiment

    @contextmanager
    def acquisition(self, *, checkpoint=None, identity=None):
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

        session = Session()
        if self.experiment == "skillsbench":
            session.public_inputs = {
                "task_id": "3d-scan-calc",
                "opening": "Analyze the supplied scan.",
                "workspace": {"directory": "/root", "input_directories": ["/root"]},
            }
            session.allowed_read_only_tool_names = ("list_input_directory", "read_input_file")
            session.tool_schemas = [
                {"type": "function", "function": {"name": name}}
                for name in session.allowed_read_only_tool_names
            ]
        yield session

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
        bank_factory=lambda _: Bank(
            log, metrics or {"utility": 1.0, "asr": 0.0}, experiment=experiment
        ),
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


def test_codex_plan_models_are_scoped_by_task_role_and_phase_without_api_credentials(
    tmp_path, monkeypatch
):
    from tau_skill_evolution import codex_plan
    from tau_skill_evolution import workflow as workflow_module

    values = yaml.safe_load(SKILLSBENCH_CONFIG.read_text())
    pinned = values["runtime"]["codex"]
    values["provider"] = {
        "model": "gpt-6.1-sol",
        "transport": "codex-plan",
        "binary": "/opt/codex-0.160.1/codex",
        "version": pinned["version"],
        "binary_sha256": pinned["binary_sha256"],
    }
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(values))
    clients = []

    class Client:
        def __init__(self, **options):
            self.options = options
            self.config = options["config"]
            self.closed = False
            clients.append(self)

        def close(self):
            self.closed = True

    def forbidden_credential(_):
        pytest.fail("Codex subscription transport must not read an API credential")

    monkeypatch.setattr(codex_plan, "CodexPlanClient", Client)
    monkeypatch.setattr(workflow_module, "bearer_token_source", forbidden_credential)
    workflow = Workflow(load_spec(path), tmp_path / "run", counter=len)
    for task, role, phase in (
        ("dialogue-parser", "generator", "create"),
        ("dialogue-parser", "generator", "revise"),
        ("dialogue-parser", "verifier", "create"),
        ("3d-scan-calc", "generator", "create"),
    ):
        with workflow._model_context(role, phase=phase, scope=f"{task}/benign") as client:
            assert not client.closed
            assert client.config.model == "gpt-6.1-sol"
            assert client.config.transport == "codex-plan"
            assert client.config.max_output_tokens is None
            assert client.config.response_format == (
                SKILL_BUNDLE_RESPONSE_FORMAT if role == "generator" and phase == "create" else None
            )
    assert all(client.closed for client in clients)
    scopes = [client.options["journal_dir"] for client in clients]
    assert len(set(scopes)) == 4
    assert all("private/codex-plan" in str(scope) for scope in scopes)


@pytest.mark.parametrize("output", [None, "invalid JSON"])
def test_creation_closes_role_clients_after_success_or_invalid_output(tmp_path, output):
    workflow, log, _ = _workflow(tmp_path, output=output)
    original = workflow.model_factory

    def model_factory(role):
        model = original(role)
        model.close = lambda: log.append(("model_closed", role))
        return model

    workflow.model_factory = model_factory
    workflow.create(((workflow.spec.tasks[0], "benign"),))
    assert [event[1] for event in log if event[0] == "model_closed"] == [
        "analyzer",
        "generator",
    ]


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
    assert requests[0][1]["allowed_read_only_tools"] == [
        "list_input_directory",
        "read_input_file",
    ]
    assert requests[0][1]["remaining"]["clarify"] == 0
    assert requests[0][1]["remaining"]["read_only"] == 10
    assert "public_input_manifest" not in json.dumps(requests)
    assert "copies" not in json.dumps(requests)
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


def test_skillsbench_discovery_observations_reach_s0_and_resume_does_not_repeat_reads(tmp_path):
    workflow, log, requests = _workflow(tmp_path, experiment="skillsbench")
    original_factory = workflow.model_factory
    actions = iter(
        [
            {"kind": "read_only", "tool": "list_input_directory", "arguments": {"path": "/root"}},
            {
                "kind": "read_only",
                "tool": "read_input_file",
                "arguments": {"path": "/root/input.txt"},
            },
        ]
    )

    def model_factory(role):
        original = original_factory(role)
        if role != "analyzer":
            return original

        def model(payload):
            result = original(payload)
            if action := next(actions, None):
                result["action"] = action
            return result

        return model

    class FileAdapter(Bank):
        @contextmanager
        def acquisition(self, **options):
            with super().acquisition(**options) as session:

                def read(tool, arguments):
                    log.append(("input_read", tool, dict(arguments)))
                    return (
                        {"entries": [{"name": "input.txt", "path": "/root/input.txt"}]}
                        if tool == "list_input_directory"
                        else {"content": "public supplied content", "encoding": "utf-8"}
                    )

                session.read = read
                yield session
            log.append(("input_view_closed",))

    workflow.model_factory = model_factory
    workflow.bank_factory = lambda _: FileAdapter(log, {}, experiment="skillsbench")
    cell = ("3d-scan-calc", "benign")
    workflow.create((cell,))
    root, journal = workflow._cell(*cell)
    assert journal.response("creation")["status"] == "CREATED"
    base = load_base(root / "base")
    observations = base.public_inputs["read_only_observations"]
    assert [item["tool"] for item in observations] == [
        "list_input_directory",
        "read_input_file",
    ]
    generator_payload = next(payload for role, payload in requests if role == "generator")
    assert (
        generator_payload["frozen_base"]["public_inputs"]["read_only_observations"][1]["result"][
            "content"
        ]
        == "public supplied content"
    )
    assert "public_input_manifest" not in json.dumps(requests)
    assert log.index(("input_view_closed",)) < len(log)
    before = copy.deepcopy((log, requests))
    workflow.create((cell,))
    assert (log, requests) == before
    assert len([role for role, _ in requests if role == "generator"]) == 1
    assert len([event for event in log if event[0] == "input_read"]) == 2


def test_previous_manifest_based_method_is_readable_but_cannot_start_or_resume(tmp_path):
    values = yaml.safe_load(SKILLSBENCH_CONFIG.read_text())
    values["schema_version"] = "skillsbench.skill-evolution.v6"
    values["acquisition"]["max_reads"] = 0
    path = tmp_path / "historical-config.yaml"
    path.write_text(yaml.safe_dump(values))
    old = load_spec(path)
    assert old.namespace == "skillsbench.skill-evolution.v6"
    assert old.values["acquisition"]["max_reads"] == 0
    run = tmp_path / "historical"
    with pytest.raises(ValueError, match="historical methods are read-only"):
        Workflow(
            old,
            run,
            model_factory=lambda _: pytest.fail("historical method cannot make a request"),
            counter=len,
        )
    assert not run.exists()


def test_no_skill_workflow_skips_learning_and_keeps_fixed_population(tmp_path):
    spec = load_spec(DEFAULT_CONFIG.parent / "skillsbench.yaml")
    values = copy.deepcopy(spec.values)
    values["runtime"]["executor"] = "author-codex"
    spec = ExperimentSpec(spec.path, values)
    calls = []

    class NoSkillAdapter:
        def evaluate_no_skill(self):
            calls.append("fresh_no_skill")
            return {
                "utility": True,
                "reward": 1.0,
                "asr": None,
                "asr_status": "NOT_APPLICABLE",
                "executor": {"name": "author-codex", "model": "offline"},
                "official_checks": {"status": "MEASURED", "passed": 2, "total": 2, "rate": 1.0},
            }

    workflow = Workflow(
        spec,
        tmp_path / "run",
        runtime="docker",
        counter=len,
        bank_factory=lambda _: NoSkillAdapter(),
        model_factory=lambda _: pytest.fail("baseline cannot invoke learning roles"),
        corpus_factory=lambda *args: pytest.fail("baseline cannot retrieve"),
    )
    cell = (spec.tasks[0], "benign")
    workflow.evaluate_no_skill((cell,))
    workflow.evaluate_no_skill((cell,))
    report = workflow.report()
    assert calls == ["fresh_no_skill"]
    assert len(report["cases"]) == 85
    case = next(case for case in report["cases"] if case["task_id"] == cell[0])
    assert case["versions"] == [] and case["evaluations"] == {}
    assert case["no_skill_evaluation"]["utility"] is True
    assert report["versions"] == [] and report["rounds"] == []
    baseline = next(arm for arm in report["arms"] if arm["arm"] == "no_skill")
    assert baseline["task_denominator"] == 85 and baseline["measured_count"] == 1
    assert baseline["not_measured_count"] == 84 and baseline["actual_chains"] == 0
    assert report["formal_matrix_result"]
    assert "No-Skill independent measurements" in (workflow.root / "REPORT.md").read_text()
    root, journal = workflow._cell(*cell)
    assert not journal.dispatched("creation") and not journal.dispatched("generate_initial")
    assert not (root / "base").exists() and not (root / "initial").exists()


@pytest.mark.parametrize("runtime, executor", [("docker", "local"), ("workspace", "author-codex")])
def test_no_skill_workflow_requires_same_author_executor(tmp_path, runtime, executor):
    spec = load_spec(DEFAULT_CONFIG.parent / "skillsbench.yaml")
    values = copy.deepcopy(spec.values)
    values["runtime"]["executor"] = executor
    values["source"]["runtime_lock"] = "runtime/skillsbench-bubblewrap-lock.json"
    workflow = Workflow(
        ExperimentSpec(spec.path, values),
        tmp_path / "run",
        runtime=runtime,
        counter=len,
        bank_factory=lambda _: pytest.fail("unsupported baseline must not execute"),
    )
    with pytest.raises(ValueError, match="author Codex Docker"):
        workflow.evaluate_no_skill(((spec.tasks[0], "benign"),))


def test_no_skill_new_authenticated_invocation_preserves_unknown_and_continues(tmp_path):
    calls = []

    def rejected():
        calls.append("rejected")
        raise ModelClientError("http_error", "redacted", status=401)

    workflow = _codex_control_workflow(tmp_path, SimpleNamespace(evaluate_no_skill=rejected))
    cells = tuple((task, "benign") for task in workflow.spec.tasks[:2])
    with pytest.raises(ModelClientError, match="authentication"):
        workflow.evaluate_no_skill(cells)
    assert calls == ["rejected"]

    def accepted():
        calls.append("accepted")
        return {"utility": True, "asr": None, "asr_status": "NOT_APPLICABLE"}

    resumed = _codex_control_workflow(tmp_path, SimpleNamespace(evaluate_no_skill=accepted))
    resumed.evaluate_no_skill(cells)
    assert calls == ["rejected", "accepted"]
    report = resumed.report()
    assert report["cases"][0]["no_skill_evaluation"]["status"] == "NOT_MEASURED"
    assert report["cases"][1]["no_skill_evaluation"]["status"] == "MEASURED"


def test_no_skill_cli_routes_evaluation_without_creation(tmp_path, monkeypatch, capsys):
    spec = load_spec(DEFAULT_CONFIG.parent / "skillsbench.yaml")
    values = copy.deepcopy(spec.values)
    values["runtime"]["executor"] = "author-codex"
    spec = ExperimentSpec(spec.path, values)
    monkeypatch.setattr(cli, "load_spec", lambda _: spec)
    monkeypatch.setattr(cli, "preflight", lambda *args, **kwargs: {"ready": True})
    calls = []

    class BaselineWorkflow:
        def __init__(self, *args, **kwargs):
            assert kwargs["runtime"] == "docker"

        def evaluate_no_skill(self, cells):
            calls.append(cells)

        def report(self):
            return {"baseline": "no_skill"}

    monkeypatch.setattr(cli, "Workflow", BaselineWorkflow)
    assert (
        cli.main(
            [
                "evaluate",
                "--experiment",
                "skillsbench",
                "--no-skill",
                "--runtime",
                "docker",
                "--task",
                spec.tasks[0],
                "--arm",
                "benign",
                "--run-dir",
                str(tmp_path / "run"),
            ]
        )
        == 0
    )
    assert calls == [((spec.tasks[0], "benign"),)]
    assert json.loads(capsys.readouterr().out) == {"baseline": "no_skill"}


@pytest.mark.parametrize(
    "arguments",
    [
        ["run", "--no-skill"],
        ["evaluate", "--no-skill"],
        ["run", "--bundles-from", "source"],
        ["evaluate", "--no-skill", "--bundles-from", "source"],
        ["evaluate", "--bundles-from", "source", "--runtime", "docker"],
        ["evaluate", "--experiment", "skillsbench", "--no-skill", "--runtime", "workspace"],
    ],
)
def test_no_skill_cli_invalid_modes_fail_before_preflight(arguments, monkeypatch):
    monkeypatch.setattr(cli, "preflight", lambda *args, **kwargs: pytest.fail("must fail locally"))
    with pytest.raises(SystemExit) as exc:
        cli.main(arguments)
    assert exc.value.code == 2


def _import_source(tmp_path, task, *, after_revisit=False):
    source = tmp_path / "source"
    identity = {"experiment": "skillsbench", "namespace": "skillsbench.skill-evolution.v2"}
    Journal(source / "journal", identity=identity)
    trial = "0" * 32
    atomic_json(source / "journal" / "trial.json", {"trial_id": trial})
    cell = source / "cells" / task / "benign"
    journal = Journal(
        cell / "journal",
        identity={
            **identity,
            "trial_id": trial,
            "task": task,
            "arm": "benign",
        },
    )
    initial = SkillBundle({"SKILL.md": "initial"})
    final = SkillBundle({"SKILL.md": "improved"}, parent_hash=initial.bundle_hash)
    versions = (initial, final)
    seal_bundle(cell / "initial", initial)
    seal_bundle(cell / "versions" / final.bundle_hash, final)
    if after_revisit:
        final = SkillBundle({"SKILL.md": "new after reverting"}, parent_hash=initial.bundle_hash)
        versions = (*versions, final)
        seal_bundle(cell / "versions" / final.bundle_hash, final)
    journal.dispatch(
        "creation",
        {},
        lambda: {
            "status": "CREATED",
            "initial_bundle_hash": initial.bundle_hash,
        },
        external=False,
    )
    result = EvolutionResult(
        versions,
        tuple(
            {
                "attempt": index,
                "status": "changed",
                "parent_hash": parent.bundle_hash,
                "bundle_hash": child.bundle_hash,
            }
            for index, (parent, child) in enumerate(
                ((initial, versions[1]), (versions[1], initial), (initial, final)), start=1
            )
        )
        if after_revisit
        else (),
        (),
        (True,),
        3 if after_revisit else 1,
        "oracle_success",
        final.bundle_hash,
        final_bundle_ref={"bundle_hash": final.bundle_hash, "parent_hash": final.parent_hash}
        if after_revisit
        else None,
    )
    journal.dispatch("evolution-result", {}, result.to_dict, external=False)
    journal.dispatch(
        f"evaluation-{initial.bundle_hash}",
        {},
        lambda: {
            "utility": 1,
            "old_private_score": "must not be imported",
        },
        external=False,
    )
    return source, initial, final


def _codex_control_workflow(tmp_path, adapter):
    spec = load_spec(DEFAULT_CONFIG.parent / "skillsbench.yaml")
    values = copy.deepcopy(spec.values)
    values["runtime"]["executor"] = "author-codex"
    return Workflow(
        ExperimentSpec(spec.path, values),
        tmp_path / "run",
        runtime="docker",
        counter=len,
        bank_factory=lambda _: adapter,
        model_factory=lambda _: pytest.fail("control cannot invoke learning models"),
        corpus_factory=lambda *args: pytest.fail("control cannot retrieve"),
    )


def test_imported_versions_regraded_and_paired_with_baseline_without_creation(
    tmp_path, monkeypatch
):
    calls = []
    executor = {"name": "author-codex", "model": "offline"}

    class Adapter:
        def evaluate_no_skill(self):
            calls.append("no_skill")
            return {
                "utility": False,
                "reward": 0.5,
                "asr": None,
                "asr_status": "NOT_APPLICABLE",
                "executor": executor,
            }

        def evaluate(self, bundle):
            calls.append(bundle.bundle_hash)
            return {
                "utility": bundle.parent_hash is not None,
                "reward": 1.0 if bundle.parent_hash is not None else 0.5,
                "asr": None,
                "asr_status": "NOT_APPLICABLE",
                "executor": executor,
            }

    workflow = _codex_control_workflow(tmp_path, Adapter())
    task = workflow.spec.tasks[0]
    source, initial, final = _import_source(tmp_path, task)
    original_response = Journal.response

    def response(journal, operation):
        if journal.root.is_relative_to(source) and operation.startswith("evaluation-"):
            pytest.fail("source scores must not be read")
        return original_response(journal, operation)

    monkeypatch.setattr(Journal, "response", response)
    cells = ((task, "benign"),)
    workflow.evaluate_no_skill(cells)
    workflow.evaluate_imported(cells, source)
    report = workflow.report()
    assert calls == ["no_skill", initial.bundle_hash, final.bundle_hash]
    case = report["cases"][0]
    assert case["status"] == "IMPORTED_EVALUATION"
    assert "creation" not in case and "evolution" not in case
    assert case["evaluation_source"] == "imported_frozen_packages"
    assert case["initial_bundle_hash"] == initial.bundle_hash
    assert case["final_bundle_hash"] == final.bundle_hash
    assert case["evaluation_import"]["source_revision_attempts"] == 1
    assert case["evaluation_import"]["source_stop_reason"] == "oracle_success"
    assert case["evaluations"][initial.bundle_hash]["utility"] is False
    assert report["baseline_paired_progress"][1]["rescued_count"] == 1
    assert "old_private_score" not in json.dumps(report)
    root, journal = workflow._cell(task, "benign")
    assert not journal.dispatched("creation") and not journal.dispatched("evolution-result")
    assert load_bundle(root / "imported" / final.bundle_hash).bundle_hash == final.bundle_hash
    # Recovery needs only this run's sealed copies and results, not the source run.
    shutil.rmtree(source)
    workflow.evaluate_imported(cells, source)
    assert calls == ["no_skill", initial.bundle_hash, final.bundle_hash]
    with pytest.raises(ValueError, match="cannot create or evolve"):
        workflow.create(cells)


def test_imported_content_versions_allow_parent_revisited_before_new_content(tmp_path):
    calls = []

    class Adapter:
        def evaluate(self, bundle):
            calls.append(bundle.bundle_hash)
            return {"utility": True, "asr": None, "asr_status": "NOT_APPLICABLE"}

    workflow = _codex_control_workflow(tmp_path, Adapter())
    task = workflow.spec.tasks[0]
    source, initial, final = _import_source(tmp_path, task, after_revisit=True)
    cells = ((task, "benign"),)
    workflow.evaluate_imported(cells, source)
    case = workflow.report()["cases"][0]
    assert len(calls) == len(set(calls)) == 3
    assert final.parent_hash == initial.bundle_hash
    assert case["final_bundle_ref"] == {
        "bundle_hash": final.bundle_hash,
        "parent_hash": initial.bundle_hash,
    }
    workflow.evaluate_imported(cells, source)
    assert len(calls) == 3


def test_new_trial_imported_evaluation_preserves_source_close_failure(tmp_path):
    calls = []
    workflow = _codex_control_workflow(
        tmp_path,
        SimpleNamespace(
            evaluate=lambda bundle: (
                calls.append(bundle.bundle_hash)
                or {"utility": True, "asr": None, "asr_status": "NOT_APPLICABLE"}
            )
        ),
    )
    task = workflow.spec.tasks[0]
    source, initial, final = _import_source(tmp_path, task)
    source_root = source / "cells" / task / "benign" / "journal"
    source_journal = Journal(
        source_root, identity=json.loads((source_root / "identity.json").read_text())["identity"]
    )
    failure = {
        "status": "NOT_MEASURED",
        "index": 0,
        "stage": "close",
        "error_type": "ContainerUnavailable",
        "reason": "skillsbench_episode_cleanup_failed",
    }
    source_journal.dispatch("learning-environment-failure-0", {}, lambda: failure, external=False)
    before = source_journal.response("evolution-result")
    cells = ((task, "benign"),)
    workflow.evaluate_imported(cells, source)
    case = workflow.report()["cases"][0]
    imported = case["evaluation_import"]
    assert imported["source_stop_reason"] == "learning_environment_close_failed"
    assert imported["source_evolution_stop_reason"] == "oracle_success"
    assert imported["source_learning_environment_failure"] == failure
    assert imported["source_trial_id"] != workflow.trial_id
    assert source_journal.response("evolution-result") == before
    assert source_journal.response("learning-environment-failure-0") == failure
    assert calls == [initial.bundle_hash, final.bundle_hash]
    shutil.rmtree(source)
    workflow.evaluate_imported(cells, source)
    assert calls == [initial.bundle_hash, final.bundle_hash]
    assert workflow.report()["cases"][0]["evaluation_import"] == imported


@pytest.mark.parametrize("tamper", ["initial", "parent", "task"])
def test_import_rejects_tampered_source_before_evaluation(tmp_path, tamper):
    workflow = _codex_control_workflow(
        tmp_path,
        SimpleNamespace(evaluate=lambda _: pytest.fail("tampered source cannot run")),
    )
    task = workflow.spec.tasks[0]
    source, initial, final = _import_source(tmp_path, task)
    cell = source / "cells" / task / "benign"
    if tamper == "initial":
        (cell / "initial" / "SKILL.md").write_text("tampered")
    elif tamper == "parent":
        wrong_parent = SkillBundle({"SKILL.md": "improved"}, parent_hash="f" * 64)
        shutil.rmtree(cell / "versions" / final.bundle_hash)
        seal_bundle(cell / "versions" / final.bundle_hash, wrong_parent)
    else:
        identity_path = cell / "journal" / "identity.json"
        identity = json.loads(identity_path.read_text())
        identity["identity"]["task"] = "other-task"
        atomic_json(identity_path, identity)
    with pytest.raises(ValueError):
        workflow.evaluate_imported(((task, "benign"),), source)


def test_import_unknown_evaluation_never_resamples(tmp_path):
    calls = []

    def evaluate(bundle):
        calls.append(bundle.bundle_hash)
        raise RuntimeError("response lost")

    workflow = _codex_control_workflow(tmp_path, SimpleNamespace(evaluate=evaluate))
    task = workflow.spec.tasks[0]
    source, initial, final = _import_source(tmp_path, task)
    workflow.evaluate_imported(((task, "benign"),), source)
    workflow.evaluate_imported(((task, "benign"),), source)
    assert calls == [initial.bundle_hash, final.bundle_hash]
    report = workflow.report()
    assert all(
        row["status"] == "NOT_MEASURED" and row["utility"] is None for row in report["versions"]
    )


def test_bundles_from_cli_uses_import_path(tmp_path, monkeypatch, capsys):
    spec = load_spec(DEFAULT_CONFIG.parent / "skillsbench.yaml")
    values = copy.deepcopy(spec.values)
    values["runtime"]["executor"] = "author-codex"
    spec = ExperimentSpec(spec.path, values)
    monkeypatch.setattr(cli, "load_spec", lambda _: spec)
    monkeypatch.setattr(cli, "preflight", lambda *args, **kwargs: {"ready": True})
    source = tmp_path / "source"
    calls = []

    class ImportedWorkflow:
        def __init__(self, *args, **kwargs):
            pass

        def evaluate_imported(self, cells, source_run):
            calls.append((cells, source_run))

        def report(self):
            return {"source": "imported_frozen_packages"}

    monkeypatch.setattr(cli, "Workflow", ImportedWorkflow)
    assert (
        cli.main(
            [
                "evaluate",
                "--experiment",
                "skillsbench",
                "--runtime",
                "docker",
                "--bundles-from",
                str(source),
                "--task",
                spec.tasks[0],
                "--arm",
                "benign",
                "--run-dir",
                str(tmp_path / "run"),
            ]
        )
        == 0
    )
    assert calls == [(((spec.tasks[0], "benign"),), source)]
    assert json.loads(capsys.readouterr().out)["source"] == "imported_frozen_packages"


@pytest.mark.parametrize("output_limit", [32768, None])
def test_create_resume_never_repeats_s0_or_reopens_corpus(tmp_path, output_limit):
    workflow, log, requests = _workflow(tmp_path)
    workflow.spec.values["roles"]["generator"]["max_output_tokens"] = output_limit
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
    journal = workflow._cell(*cell)[1]
    creation = next(
        request
        for path in journal.root.glob("*/request.json")
        if (request := json.loads(path.read_text()))["operation_id"] == "generate_initial"
    )
    admission = creation["payload"]["context_admission"]
    assert admission["reserved_output_tokens"] == 32768
    assert admission["max_input_tokens"] == 157632


def test_tau_acquisition_checkpoint_is_private_and_bound_to_cell(tmp_path):
    workflow, log, requests = _workflow(tmp_path)
    cell = (workflow.spec.tasks[0], "benign")
    bank = Bank(log, {"utility": 1, "asr": 0})
    acquisition = bank.acquisition
    bindings = []

    @contextmanager
    def recording_acquisition(**options):
        bindings.append(options)
        with acquisition(**options) as session:
            yield session

    bank.acquisition = recording_acquisition
    workflow.bank_factory = lambda _: bank
    workflow.create((cell,))
    assert bindings == [
        {
            "checkpoint": (
                workflow.root / "private" / "acquisition" / cell[0] / cell[1] / "session.json"
            ).resolve(),
            "identity": {**workflow.identity, "task": cell[0], "arm": cell[1]},
        }
    ]
    assert str(bindings[0]["checkpoint"]) not in json.dumps(requests)


def test_unfinished_acquisition_without_private_snapshot_never_rerolls(tmp_path):
    workflow, log, requests = _workflow(tmp_path)
    cell = (workflow.spec.tasks[0], "benign")
    _, journal = workflow._cell(*cell)
    journal.dispatch("acquisition/analyzer/0", {}, lambda: {}, external=False)
    workflow.create((cell,))
    creation = journal.response("creation")
    assert creation["status"] == "CREATION_FAILED"
    assert creation["reason"] == "acquisition_snapshot_missing_requires_new_trial"
    assert not requests and not log


def test_acquisition_resume_preserves_opening_after_unsent_key_expiration(tmp_path):
    workflow, log, requests = _workflow(tmp_path)
    cell = (workflow.spec.tasks[0], "benign")
    bank = Bank(log, {"utility": 1, "asr": 0})
    acquisition = bank.acquisition
    fresh_openings = []

    @contextmanager
    def persistent_acquisition(*, checkpoint, identity):
        if not checkpoint.exists():
            fresh_openings.append("Help with my account")
            atomic_json(checkpoint, {"opening": fresh_openings[-1], "identity": identity})
        saved = json.loads(checkpoint.read_text())
        assert saved["identity"] == identity
        with acquisition(checkpoint=checkpoint, identity=identity) as session:
            session.public_inputs = {"opening_message": saved["opening"]}
            yield session

    bank.acquisition = persistent_acquisition
    workflow.bank_factory = lambda _: bank
    original_model = workflow.model_factory
    expired = False

    def model_factory(role):
        model = original_model(role)

        def complete(payload):
            nonlocal expired
            if role == "analyzer" and payload["returned_documents"] and not expired:
                expired = True
                raise CredentialError("credential_expired", "fixture credential expired")
            return model(payload)

        return complete

    workflow.model_factory = model_factory
    with pytest.raises(CredentialError):
        workflow.create((cell,))
    _, journal = workflow._cell(*cell)
    assert journal.completed("acquisition/analyzer/0")
    assert journal.status("acquisition/analyzer/1") == "NOT_SENT"
    assert not journal.completed("creation")
    workflow.create((cell,))
    assert fresh_openings == ["Help with my account"]
    assert len([entry for entry in log if entry[0] == "search"]) == 1
    assert [role for role, _ in requests].count("generator") == 1
    assert journal.response("creation")["status"] == "CREATED"


@pytest.mark.parametrize("lost_reply", ["opening", "read", "local_recovery"])
def test_acquisition_lost_worker_reply_resumes_private_result(tmp_path, lost_reply):
    workflow, log, requests = _workflow(tmp_path)
    cell = (workflow.spec.tasks[0], "benign")
    bank = Bank(log, {"utility": 1, "asr": 0})
    acquisition = bank.acquisition
    openings, reads = [], []
    interrupted = False

    @contextmanager
    def persistent_acquisition(*, checkpoint, identity):
        nonlocal interrupted
        if not checkpoint.exists():
            openings.append("Help with my account")
            atomic_json(checkpoint, {"opening": openings[-1], "identity": identity})
        if lost_reply == "opening" and not interrupted:
            interrupted = True
            raise BankWorkerError("bank_worker_exited")
        with acquisition(checkpoint=checkpoint, identity=identity) as session:

            def perform(operation_id, action):
                nonlocal interrupted
                saved = json.loads(checkpoint.read_text())
                if "read_result" not in saved:
                    reads.append(operation_id)
                    saved["read_result"] = session.read(action["tool"], action["arguments"])
                    atomic_json(checkpoint, saved)
                if lost_reply in {"read", "local_recovery"} and not interrupted:
                    interrupted = True
                    if lost_reply == "local_recovery":
                        raise ModelClientError("acquisition_recovery_failed", "local replay failed")
                    raise BankWorkerError("bank_worker_exited")
                return saved["read_result"]

            session.perform = perform
            yield session

    bank.acquisition = persistent_acquisition
    workflow.bank_factory = lambda _: bank
    with pytest.raises((BankWorkerError, ModelClientError)):
        workflow.create((cell,))
    _, journal = workflow._cell(*cell)
    assert not journal.dispatched("creation")
    assert not requests
    workflow.create((cell,))
    assert journal.response("creation")["status"] == "CREATED"
    assert openings == ["Help with my account"]
    assert reads == ["acquisition/read_only/0"]
    assert [role for role, _ in requests].count("generator") == 1


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

    def interrupt(journal, operation, payload, callback, **kwargs):
        if operation == "creation":
            raise KeyboardInterrupt()
        return original_dispatch(journal, operation, payload, callback, **kwargs)

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


def test_usage_reparse_is_not_double_counted_and_unknown_billing_is_explicit(tmp_path):
    workflow, _, _ = _workflow(tmp_path)
    item = {
        "role": "generator",
        "operation_key": "same-request",
        "usage": {"input_tokens": 12, "output_tokens": 3},
    }
    (workflow.root / "usage.jsonl").write_text(json.dumps(item) + "\n" + json.dumps(item) + "\n")
    cell = (workflow.spec.tasks[0], "benign")
    _, journal = workflow._cell(*cell)
    with pytest.raises(UnknownOperation):
        journal.dispatch(
            "unknown-provider-call",
            {"delivery_policy": "single_post"},
            lambda: (_ for _ in ()).throw(TimeoutError()),
        )
    summary = workflow._usage_summary()
    assert summary["total"]["requests"] == 1
    assert summary["total"]["input_tokens"] == 12
    assert summary["model_request_states"]["UNKNOWN"] == 1
    assert summary["unknown_requests_may_be_billed"] == 1
    assert summary["cost_usd"] is None


def test_usage_includes_unknown_requests_with_historical_delivery_policy(tmp_path):
    workflow, _, _ = _workflow(tmp_path, experiment="skillsbench")
    _, journal = workflow._cell(workflow.spec.tasks[0], "benign")
    policy = "bounded_resend_of_unobserved_transport_failures_v1"
    with pytest.raises(UnknownOperation):
        journal.dispatch(
            "historical-provider-call",
            {"delivery_policy": policy},
            lambda: (_ for _ in ()).throw(TimeoutError()),
        )
    # Task tools must not become model requests merely because they share a journal.
    journal.dispatch("terminal", {"name": "terminal"}, lambda: {"exit_code": 0})
    summary = workflow._usage_summary()
    assert summary["model_request_states"]["UNKNOWN"] == 1
    assert summary["dispatched_model_requests"] == 1
    assert summary["unknown_requests_may_be_billed"] == 1
    assert summary["delivery_policies"] == {policy: 1}
    assert summary["http_posts"]["status"] == "NOT_MEASURED"
    assert summary["http_posts"]["count"] is None


def test_skillsbench_stage_failure_and_verifier_tools_survive_report_export(tmp_path):
    workflow, _, requests = _workflow(tmp_path, experiment="skillsbench")
    task = workflow.spec.tasks[0]
    workflow.create(((task, "benign"),))
    directory, journal = workflow._cell(task, "benign")
    _, initial = workflow._created(directory, journal)
    operation = "evolution-turn-0-suite-turn-0-tool-0"
    program = ProgramResult(1, stderr="collection failed", failure="nonzero_exit").to_dict()
    journal.dispatch(
        operation,
        {"name": "run_tests", "arguments": {}},
        lambda: {
            "program": program,
            "snapshot": {
                "workspace_hash": "a" * 64,
                "files": {"test_public.py": "def test_output(): assert False\n"},
                "manifest": {"work": {"tests/test_public.py": "b" * 64}},
            },
        },
    )
    rejection = {
        "stage": "test_submission",
        "operation_id": operation,
        "exception_type": "ValueError",
        "reason": "missing_test_obligations",
        "detail": "missing_test_obligations",
    }
    failure = {
        "stage": "verifier_initialization",
        "operation_id": "evolution-turn-0-suite",
        "exception_type": "ValueError",
        "reason": "ungrounded_test_evidence",
        "detail": "ungrounded_test_evidence",
        "rejections": [rejection],
    }
    result = EvolutionResult(
        (initial,),
        (),
        (),
        (),
        0,
        "verifier_initialization_failed",
        initial.bundle_hash,
        stage_failures=(failure,),
    )
    journal.dispatch("evolution-result", {}, result.to_dict, external=False)
    before = copy.deepcopy(requests)
    report = workflow.report()
    case = next(item for item in report["cases"] if item["task_id"] == task)
    assert case["stage_failures"] == [failure]
    assert case["verifications"] == []
    audit = json.loads((workflow.root / case["public_audit"]).read_text())
    assert audit["stage_failures"] == [failure]
    assert audit["verifier_operations"] == [
        {
            "operation_id": operation,
            "status": "COMPLETED",
            "tool": "run_tests",
            "program": program,
            "workspace_hash": "a" * 64,
            "test_files": {"test_public.py": "def test_output(): assert False\n"},
            "manifest": {"work": {"tests/test_public.py": "b" * 64}},
        }
    ]
    assert audit["terminal_operations"] == []
    assert audit["bank_actions"] == []
    markdown = (workflow.root / "REPORT.md").read_text()
    assert "ungrounded_test_evidence" in markdown
    assert "missing_test_obligations" in markdown
    assert requests == before  # Audit data never makes another learning-model request.


def _native_journal(workflow, episode):
    return Journal(
        workflow.root / "private" / "skillsbench-models" / "task" / episode / "provider",
        identity={"executor": {"framework": "author-codex"}, "episode_id": episode},
    )


def test_native_usage_counts_all_episode_requests_once_and_preserves_failure_states(tmp_path):
    workflow, _, _ = _workflow(tmp_path)
    usage = {"input_tokens": 20, "output_tokens": 3, "input_tokens_details": {"cached_tokens": 12}}
    native = _native_journal(workflow, "first")
    same_payload_id = "same-native-payload"
    native.dispatch(
        same_payload_id, {"input": "public task"}, lambda: {"response": {"usage": usage}}
    )
    native.dispatch(
        same_payload_id,
        {"input": "public task"},
        lambda: pytest.fail("a completed native request must not resample"),
    )
    # Native statistics mirror the journal and must not become additional charged calls.
    atomic_json(
        native.root.parent / "provider-statistics.json",
        {
            "requests": 1,
            "usage": [{"operation_key": same_payload_id, **usage}],
        },
    )
    second = _native_journal(workflow, "second")
    second.dispatch(
        same_payload_id, {"input": "public task"}, lambda: {"response": {"usage": usage}}
    )
    # Identical model inputs in independent episodes are two distinct paid calls.
    key = canonical_json_sha256(
        {"journal": str(native.root.resolve()), "operation_id": same_payload_id}
    )
    logged = {"role": "execution", "model": "offline", "operation_key": key, "usage": usage}
    generator = {
        "role": "generator",
        "operation_key": "generator-usage",
        "usage": {
            "input_tokens": 5,
            "output_tokens": 1,
            "input_tokens_details": {"cached_tokens": 1},
        },
    }
    (workflow.root / "usage.jsonl").write_text(
        json.dumps(logged) + "\n" + json.dumps(logged) + "\n" + json.dumps(generator) + "\n"
    )
    workflow.journal.dispatch("normal-generator", {"delivery_policy": "single_post"}, lambda: {})

    def raise_timeout(_):
        raise TimeoutError("unknown native response")

    with pytest.raises(UnknownOperation):
        native.dispatch_raw(
            "unknown", {"input": "next"}, lambda: None, raise_timeout, lambda *_: {}
        )

    def reject_response(*_):
        raise ModelClientError("provider_http_error", "received", status=401)

    with pytest.raises(ModelClientError):
        native.dispatch_raw(
            "rejected", {"input": "rejected"}, lambda: None, lambda _: (401, b"{}"), reject_response
        )

    def unavailable_credential():
        raise CredentialError("credential_unavailable", "no request sent")

    with pytest.raises(CredentialError):
        native.dispatch_raw(
            "not-sent",
            {"input": "not sent"},
            unavailable_credential,
            lambda _: pytest.fail("no POST allowed"),
            lambda *_: {},
        )
    first = workflow._usage_summary()
    assert first == workflow._usage_summary()
    assert first["status"] == "MEASURED"
    assert first["roles"]["execution"] == {
        "requests": 2,
        "input_tokens": 40,
        "output_tokens": 6,
        "cached_input_tokens": 24,
    }
    assert first["total"] == {
        "requests": 3,
        "input_tokens": 45,
        "output_tokens": 7,
        "cached_input_tokens": 25,
    }
    assert first["model_request_states"] == {
        "NOT_SENT": 1,
        "RECEIVED_INVALID": 1,
        "COMPLETED": 3,
        "UNKNOWN": 1,
    }
    assert first["dispatched_model_requests"] == 5
    assert first["unknown_requests_may_be_billed"] == 1 and first["cost_usd"] is None


def test_native_no_usage_distinguishes_absent_calls_from_unresolved_requests(tmp_path):
    workflow, _, _ = _workflow(tmp_path)
    empty = workflow._usage_summary()
    assert empty["status"] == "NOT_MEASURED" and empty["dispatched_model_requests"] == 0
    journal = _native_journal(workflow, "unknown")
    with pytest.raises(UnknownOperation):
        journal.dispatch(
            "native-request", {"input": "public"}, lambda: (_ for _ in ()).throw(TimeoutError())
        )
    unresolved = workflow._usage_summary()
    assert unresolved["status"] == "NOT_MEASURED" and unresolved["roles"] == {}
    assert unresolved["dispatched_model_requests"] == 1
    assert unresolved["unknown_requests_may_be_billed"] == 1
    assert unresolved["total"]["requests"] == 0  # No valid response usage is available.


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


def test_tau_cli_defaults_to_docker_and_allows_explicit_workspace(tmp_path, monkeypatch, capsys):
    selected = []

    class OfflineWorkflow:
        def __init__(self, *args, **kwargs):
            selected.append(kwargs["runtime"])

        def report(self):
            return {"runtime": selected[-1]}

    monkeypatch.setattr(cli, "Workflow", OfflineWorkflow)
    for name, extra in (("docker", []), ("workspace", ["--runtime", "workspace"])):
        assert cli.main(["report", "--run-dir", str(tmp_path / name), *extra]) == 0
        assert json.loads(capsys.readouterr().out)["runtime"] == name
    assert selected == ["docker", "workspace"]


def test_author_codex_cli_defaults_to_docker(tmp_path, monkeypatch, capsys):
    spec = load_spec(DEFAULT_CONFIG.parent / "skillsbench.yaml")
    values = copy.deepcopy(spec.values)
    values["runtime"]["executor"] = "author-codex"
    monkeypatch.setattr(cli, "load_spec", lambda _: ExperimentSpec(spec.path, values))

    class OfflineWorkflow:
        def __init__(self, *args, **kwargs):
            assert kwargs["runtime"] == "docker"

        def report(self):
            return {"runtime": "docker"}

    monkeypatch.setattr(cli, "Workflow", OfflineWorkflow)
    assert (
        cli.main(
            [
                "report",
                "--experiment",
                "skillsbench",
                "--run-dir",
                str(tmp_path / "run"),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["runtime"] == "docker"


def test_workspace_checkpoint_cannot_resume_as_docker(tmp_path, monkeypatch):
    from tau_skill_evolution.bubblewrap import RuntimeLock

    monkeypatch.setattr(RuntimeLock, "validate", lambda _: None)
    spec = load_spec()
    directory = tmp_path / "workspace-run"
    workflow = Workflow(spec, directory, counter=len, runtime="workspace")
    report = workflow.report()
    assert report["run_mode"] == "workspace"
    assert report["execution"]["backend"] == "workspace"
    assert not report["formal_matrix_result"]
    assert not report["execution"]["aggregate_limits_enforced"]
    with pytest.raises(ValueError, match="identity"):
        Workflow(spec, directory, counter=len, runtime="docker")


def test_formal_report_requires_independent_measurement(tmp_path):
    workflow, _, _ = _workflow(tmp_path)
    cells = ((workflow.spec.tasks[0], "benign"),)
    workflow.create(cells)
    assert not workflow.report()["formal_matrix_result"]
    workflow.evaluate(cells)
    report = workflow.report()
    assert report["formal_matrix_result"]
    assert report["execution"]["formal_matrix_result"]


def test_skillsbench_workflow_calls_published_controller_and_reuses_completed_result(
    tmp_path, monkeypatch
):
    workflow, _, _ = _workflow(tmp_path, experiment="skillsbench")
    cells = ((workflow.spec.tasks[0], "benign"),)
    workflow.create(cells)
    captures = {}
    session = SimpleNamespace(runner=object())

    class Adapter:
        tool_schemas = ()

        @contextmanager
        def evolution_session(self, initial, inputs, base, **kwargs):
            captures["deadline"] = kwargs["deadline"]
            yield session

    def execute(session_arg, initial, base, generator, verifier, **kwargs):
        assert session_arg is session and generator is not verifier
        assert kwargs["deadline"] == captures["deadline"]
        assert kwargs["settings"]["max_episodes"] == 120
        assert "public-inputs" in kwargs["adapter_prompt"]
        captures["calls"] = captures.get("calls", 0) + 1
        return EvolutionResult(
            (initial,),
            (),
            (),
            (True,),
            0,
            "gt_oracle_pass",
            initial.bundle_hash,
            author_counters={
                "generator_episodes": 1,
                "normal_oracle_interventions": 1,
                "surrogate_retries": 0,
            },
            oracle_history=({"phase": "normal", "resolved_reward": 1.0},),
        )

    workflow.bank_factory = lambda _: Adapter()
    monkeypatch.setattr("tau_skill_evolution.skillsbench_evolution.run_author_evolution", execute)
    # No locally copied state machine or fresh Generator execution is invoked.
    monkeypatch.setattr(
        "tau_skill_evolution.workflow.execute_initial",
        lambda *a, **k: pytest.fail("local loop called"),
    )
    workflow.evolve(cells)
    case = workflow.report()["cases"][0]
    assert case["author_counters"]["generator_episodes"] == 1
    assert case["oracle_history"][0]["resolved_reward"] == 1.0
    assert case["evaluations"][case["final_bundle_hash"]]["status"] == "NOT_MEASURED"
    workflow.evolve(cells)
    assert captures["calls"] == 1
    assert workflow.report()["cases"][0] == case
    workflow = Workflow(
        workflow.spec,
        workflow.root,
        bank_factory=lambda _: pytest.fail("completed evolution must not reopen an adapter"),
        model_factory=lambda _: pytest.fail("completed evolution must not reopen a model"),
        counter=len,
    )
    workflow.evolve(cells)
    assert captures["calls"] == 1
    assert workflow.report()["cases"][0] == case


@pytest.mark.parametrize("restart", [False, True])
def test_skillsbench_learning_close_failure_blocks_completed_chain(tmp_path, monkeypatch, restart):
    workflow, log, requests = _workflow(tmp_path, experiment="skillsbench")
    cells = ((workflow.spec.tasks[0], "benign"),)
    workflow.create(cells)
    calls = []

    class Adapter:
        @contextmanager
        def evolution_session(self, *args, **kwargs):
            calls.append("open")
            yield SimpleNamespace()
            calls.append("close")
            raise ContainerUnavailable("skillsbench_episode_cleanup_failed")

        def evaluate(self, bundle):
            pytest.fail("failed cleanup must block fresh evaluation")

        def evaluate_no_skill(self):
            pytest.fail("failed cleanup must block fresh control evaluation")

    def execute(session, initial, base, generator, verifier, **kwargs):
        calls.append("author")
        result = EvolutionResult(
            (initial,), (), (), (True,), 0, "gt_oracle_pass", initial.bundle_hash
        )
        return EvolutionResult.from_dict(
            kwargs["journal"].dispatch("published-author-controller", {}, result.to_dict)
        )

    workflow.bank_factory = lambda _: Adapter()
    monkeypatch.setattr("tau_skill_evolution.skillsbench_evolution.run_author_evolution", execute)
    with pytest.raises(ContainerUnavailable, match="skillsbench_episode_cleanup_failed"):
        workflow.evolve(cells)
    _, journal = workflow._cell(*cells[0])
    operations = (
        "published-author-controller",
        "evolution-result",
        "learning-environment-failure-0",
    )
    completed = {operation: journal.response(operation) for operation in operations}
    assert completed["learning-environment-failure-0"]["stage"] == "close"
    before = copy.deepcopy((calls, log, requests))
    if restart:
        workflow = Workflow(
            workflow.spec,
            workflow.root,
            bank_factory=lambda _: pytest.fail("failed cleanup must block opening an adapter"),
            model_factory=lambda _: pytest.fail("failed cleanup must block opening a model"),
            counter=len,
        )
    for stage in (
        lambda: workflow.create(cells),
        lambda: workflow.evolve(cells),
        lambda: workflow.evaluate(cells),
        lambda: workflow.evaluate_no_skill(cells),
        lambda: workflow.evaluate_imported(cells, tmp_path / "unused-source"),
    ):
        with pytest.raises(
            ContainerUnavailable, match="skillsbench_learning_environment_close_failed"
        ):
            stage()
    assert (calls, log, requests) == before
    assert {operation: journal.response(operation) for operation in operations} == completed
    initial_hash = completed["evolution-result"]["final_bundle_hash"]
    assert not journal.dispatched(f"evaluation-{initial_hash}")
    assert not journal.dispatched("evaluation-no-skill")
    assert not journal.dispatched("imported-versions")
    case = workflow.report()["cases"][0]
    assert case["stop_reason"] == "learning_environment_close_failed"
    assert case["evolution_stop_reason"] == "gt_oracle_pass"
    assert case["evaluations"][initial_hash]["status"] == "NOT_MEASURED"


def test_skillsbench_unknown_learning_result_blocks_later_evaluation_posts(tmp_path):
    workflow, log, requests = _workflow(tmp_path, experiment="skillsbench")
    cells = ((workflow.spec.tasks[0], "benign"),)
    workflow.create(cells)
    root, journal = workflow._cell(*cells[0])
    initial = load_bundle(root / "initial")
    stopped = EvolutionResult(
        (initial,), (), (), (), 0, "oracle_result_unknown", initial.bundle_hash
    )
    journal.dispatch("evolution-result", {}, stopped.to_dict, external=False)
    before = copy.deepcopy((log, requests))
    workflow.evaluate(cells)
    case = workflow.report()["cases"][0]
    assert case["evaluations"][initial.bundle_hash]["status"] == "NOT_MEASURED"
    assert case["evaluations"][initial.bundle_hash]["reason"] == "oracle_result_unknown"
    assert (log, requests) == before


def test_skillsbench_learning_open_failure_still_allows_sealed_s0_evaluation(tmp_path):
    workflow, log, requests = _workflow(tmp_path, experiment="skillsbench")
    cells = ((workflow.spec.tasks[0], "benign"),)
    workflow.create(cells)
    root, journal = workflow._cell(*cells[0])
    initial = load_bundle(root / "initial")
    journal.dispatch(
        "learning-environment-failure-0",
        {},
        lambda: {"index": 0, "stage": "open", "status": "NOT_MEASURED"},
        external=False,
    )
    before = copy.deepcopy(requests)
    workflow.evaluate(cells)
    assert ("evaluate", initial.bundle_hash) in log
    assert requests == before
    assert journal.completed(f"evaluation-{initial.bundle_hash}")


def test_full_workflow_alternates_tests_and_skills_then_resumes_without_side_effects(tmp_path):
    generated = []

    def package(payload):
        generated.append(payload)
        return {"files": [{"path": "SKILL.md", "content": "instructions v0"}]}

    workflow, log, requests = _workflow(tmp_path, output=package)
    original_factory = workflow.model_factory

    class Generator:
        def complete(self, messages, **kwargs):
            payload = json.loads(messages[-1]["content"])
            if payload["phase"] == "create":
                return package(payload)
            generated.append(payload)
            calls = []
            if payload["phase"] == "revise":
                calls.append(
                    {
                        "id": "edit",
                        "function": {
                            "name": "terminal",
                            "arguments": json.dumps(
                                {
                                    "command": json.dumps(
                                        ["write", "SKILL.md", f"instructions v{len(generated)}"]
                                    )
                                }
                            ),
                        },
                    }
                )
            calls.extend(
                [
                    {"id": "perform", "function": {"name": "write_bank_action", "arguments": "{}"}},
                    {"id": "submit", "function": {"name": "submit_revision", "arguments": "{}"}},
                ]
            )
            return {"role": "assistant", "content": None, "tool_calls": calls}

    def models(role):
        if role == "generator":
            return Generator()
        if role != "verifier":
            return original_factory(role)

        def verifier(payload):
            requests.append((role, copy.deepcopy(payload)))
            if payload["action"] == "diagnosis":
                return {"diagnosis": "Required public bank action missing"}
            if payload["action"] == "initial":
                content = "def test_bank(trace): assert trace['events']"
            else:
                content = (
                    "def test_bank_upgrade(trace): "
                    "assert trace['events'][-1]['name'] == 'write_bank_action'"
                )
            return {"files": [{"path": f"tests/test_{payload['action']}.py", "content": content}]}

        return verifier

    class LearningSession:
        tool_schemas = Bank.tool_schemas

        def __init__(self):
            self.files, self.events, self.raw_results = {}, [], {}
            self.cursor = 0

        def begin_attempt(self, parent, *, initial, operation_id):
            self.files = dict(parent.files)

        def terminal(self, command):
            _, path, content = json.loads(command)
            self.files[path] = content
            self.cursor += 1
            log.append(("terminal", path))
            return ProgramResult(0, {"stdout": "", "stderr": ""})

        def execute_tool(self, name, arguments, *, operation_id):
            self.events.append({"type": "tool", "name": name})
            self.cursor += 1
            log.append(("learning_action", name))
            return {"status": "completed"}

        def snapshot(self):
            return {"workspace_hash": canonical_json_sha256(self.files), "files": dict(self.files)}

        def record_tool_result(self, operation_id, raw):
            self.raw_results[operation_id] = raw
            return "/work/tool-results/" + canonical_json_sha256(operation_id) + ".json"

        def submit(self, parent, *, initial, operation_id):
            bundle = SkillBundle(
                self.files, parent_hash=parent.parent_hash if initial else parent.bundle_hash
            )
            return EvolutionSubmission(
                bundle,
                {"events": list(self.events)},
                "shared-learning-episode",
                self.cursor,
                initial,
            )

    class FreshBank(Bank):
        oracle_results = iter([False, True])

        @contextmanager
        def evolution_session(self, initial, inputs, base, *, journal, workspace):
            log.append(("learning_environment_open",))
            yield LearningSession()
            log.append(("learning_environment_closed",))

        def rollout(self, bundle):
            pytest.fail(
                "learning submissions cannot be replaced with a fresh execution-agent rollout"
            )

        def oracle(self, bundle):
            log.append(("oracle", bundle.bundle_hash))
            return next(self.oracle_results)

    class TestRunner:
        outcomes = iter([False, True, False, True])

        def run_verifier(self, inputs, base, trace, files):
            passed = next(self.outcomes)
            nodeids = [
                f"{path}::test_bank{'_upgrade' if 'escalation' in path else ''}" for path in files
            ]
            return ProgramResult(
                0 if passed else 1,
                {
                    "collected": len(nodeids),
                    "collected_nodeids": nodeids,
                    "collection_errors": 0,
                    "exit_code": 0 if passed else 1,
                    "results": [
                        {
                            "nodeid": nodeid,
                            "stage": "call",
                            "outcome": "passed" if passed else "failed",
                            "exception": None if passed else "AssertionError",
                            "xfail": False,
                        }
                        for nodeid in nodeids
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
    assert case["learning_execution_count"] == 1
    assert case["terminal_calls"] == 2 and case["submission_count"] == 3
    assert case["learning_operations_unknown"] == 0
    public_audit = json.loads((workflow.root / case["public_audit"]).read_text())
    assert len(public_audit["submissions"]) == 3
    assert len(public_audit["terminal_operations"]) == 2
    assert len(public_audit["bank_actions"]) == 3
    ordered_submissions = sorted(
        public_audit["submissions"], key=lambda item: item["operation_cursor"]
    )
    assert [item["initial"] for item in ordered_submissions] == [True, False, False]
    assert len({item["execution_id"] for item in public_audit["submissions"]}) == 1
    assert len(case["versions"]) == len(case["evaluations"]) == 3
    assert [check["test_version"] for check in case["verifications"]] == [0, 0, 1, 1]
    assert len({check["test_hash"] for check in case["verifications"]}) == 2
    assert [payload["phase"] for payload in generated] == [
        "create",
        "execute_initial",
        "revise",
        "revise",
    ]
    assert (
        len(
            {
                payload.get("base_hash") or payload["frozen_base"]["base_hash"]
                for payload in generated
            }
        )
        == 1
    )
    assert ["frozen_base" in payload for payload in generated] == [True, True, False, False]
    assert requests == learning
    assert len([item for item in log if item[0] == "learning_environment_open"]) == 1
    assert len([item for item in log if item[0] == "learning_environment_closed"]) == 1
    assert len([item for item in log if item[0] == "evaluate"]) == 3
    markdown = (workflow.root / "REPORT.md").read_text()
    assert "NOT_MEASURED" in markdown and "Independent measurements" in markdown
    assert all(check["test_hash"] in markdown for check in case["verifications"])
    before = copy.deepcopy((log, requests))
    workflow.create(cells)
    workflow.evolve(cells)
    workflow.evaluate(cells)
    assert (log, requests) == before


def test_public_audit_counts_unknown_bank_action_without_resampling_s0(tmp_path):
    workflow, _, requests = _workflow(tmp_path)
    cell = (workflow.spec.tasks[0], "benign")
    workflow.create((cell,))
    _, journal = workflow._cell(*cell)
    operation = "evolution-initial-execution/model-0/tool-0"

    def unknown():
        raise TimeoutError("task action response was not received")

    with pytest.raises(UnknownOperation):
        journal.dispatch(operation, {"name": "write_bank_action", "arguments": {}}, unknown)
    report = workflow.report()
    case = next(item for item in report["cases"] if (item["task_id"], item["condition"]) == cell)
    assert case["terminal_calls"] == 0 and case["submission_count"] == 0
    assert case["learning_operations_unknown"] == 1
    audit = json.loads((workflow.root / case["public_audit"]).read_text())
    assert audit["bank_actions"] == [
        {"operation_id": operation, "status": "UNKNOWN", "tool": "write_bank_action"}
    ]
    assert audit["submissions"] == audit["terminal_operations"] == []
    assert [role for role, _ in requests].count("generator") == 1
    assert case["evaluations"][case["versions"][0]["bundle_hash"]]["status"] == "NOT_MEASURED"


def test_public_audit_counts_started_learning_execution_before_any_submission(tmp_path):
    workflow, _, requests = _workflow(tmp_path)
    cell = (workflow.spec.tasks[0], "benign")
    workflow.create((cell,))
    _, journal = workflow._cell(*cell)
    journal.dispatch(
        "evolution-initial-execution/start",
        {},
        lambda: {
            "learning_execution_state": {
                "execution_id": "started-unsubmitted",
                "execution_count": 1,
                "operation_cursor": 0,
            }
        },
        external=False,
    )
    report = workflow.report()
    case = next(item for item in report["cases"] if (item["task_id"], item["condition"]) == cell)
    assert case["learning_execution_count"] == 1 and case["submission_count"] == 0
    audit = json.loads((workflow.root / case["public_audit"]).read_text())
    assert audit["learning_execution_count"] == 1 and audit["submissions"] == []
    assert [role for role, _ in requests].count("generator") == 1
    assert case["evaluations"][case["versions"][0]["bundle_hash"]]["status"] == "NOT_MEASURED"


@pytest.mark.parametrize("stage", ["open", "close"])
def test_learning_environment_failure_is_reported_without_inventing_task_score(
    tmp_path, monkeypatch, stage
):
    workflow, log, requests = _workflow(tmp_path)
    cell = (workflow.spec.tasks[0], "benign")
    workflow.create((cell,))

    class BrokenBank(Bank):
        @contextmanager
        def evolution_session(self, *args, **kwargs):
            if stage == "open":
                raise RuntimeError("SENSITIVE_RUNTIME_DIAGNOSTIC")
            yield SimpleNamespace()
            raise RuntimeError("SENSITIVE_RUNTIME_DIAGNOSTIC")

        def oracle(self, bundle):
            pytest.fail("lifecycle fixture must not execute an oracle")

    def completed_engine(engine, inputs, base, initial):
        result = EvolutionResult(
            (initial,), (), (), (True,), 0, "oracle_success", initial.bundle_hash
        )
        engine.journal.dispatch("evolution-result", {}, result.to_dict, external=False)
        return result

    monkeypatch.setattr("tau_skill_evolution.evolution.EvolutionEngine.run", completed_engine)
    workflow.bank_factory = lambda _: BrokenBank(log, {})
    workflow.runner = SimpleNamespace()
    with pytest.raises(RuntimeError, match="SENSITIVE_RUNTIME_DIAGNOSTIC"):
        workflow.evolve((cell,))
    report = workflow.report()
    case = next(item for item in report["cases"] if (item["task_id"], item["condition"]) == cell)
    assert case["stop_reason"] == f"learning_environment_{stage}_failed"
    assert case["learning_environment_failure"] == {
        "status": "NOT_MEASURED",
        "index": 0,
        "stage": stage,
        "error_type": "RuntimeError",
        "reason": "RuntimeError",
    }
    assert case["evolution_stop_reason"] == (
        "oracle_success" if stage == "close" else "evolution_not_started"
    )
    assert "SENSITIVE_RUNTIME_DIAGNOSTIC" not in json.dumps(report)
    assert case["evaluations"][case["initial_bundle_hash"]]["status"] == "NOT_MEASURED"
    assert case["evaluations"][case["initial_bundle_hash"]]["utility"] is None
    assert [role for role, _ in requests].count("generator") == 1


@pytest.mark.parametrize("experiment", ["tau", "skillsbench"])
def test_historical_workflow_namespace_cannot_start_a_live_session(tmp_path, experiment):
    config = DEFAULT_CONFIG if experiment == "tau" else DEFAULT_CONFIG.parent / "skillsbench.yaml"
    spec = load_spec(config)
    values = copy.deepcopy(spec.values)
    values["schema_version"] = f"{experiment}.skill-evolution.v3"
    with pytest.raises(ValueError, match="historical methods are read-only"):
        Workflow(
            ExperimentSpec(spec.path, values),
            tmp_path / "forbidden-live",
            bank_factory=lambda _: pytest.fail("historical namespace cannot open an environment"),
            model_factory=lambda _: pytest.fail("historical namespace cannot dispatch a model"),
            counter=len,
        )
    assert not (tmp_path / "forbidden-live").exists()


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


def test_skillsbench_report_renders_native_deltas_without_imputed_versions(tmp_path):
    initial = SkillBundle({"SKILL.md": "original"})
    revised = SkillBundle({"SKILL.md": "revision"}, parent_hash=initial.bundle_hash)

    def measurement(passed, bundle_hash=None):
        return {
            "status": "MEASURED",
            "bundle_hash": bundle_hash,
            "utility": passed == 2,
            "asr": None,
            "metrics": {
                "reward": passed / 2,
                "executor": "author-codex",
                "official_checks": {
                    "status": "MEASURED",
                    "passed": passed,
                    "total": 2,
                    "rate": passed / 2,
                    "unit": "reporter_group",
                    "source": "pytest-json-ctrf.summary",
                },
            },
        }

    case = {
        "task_id": "one",
        "condition": "benign",
        "versions": [initial.to_dict(), revised.to_dict()],
        "final_bundle_hash": initial.bundle_hash,
        "stop_reason": "revision_budget_exhausted",
        "no_skill_evaluation": measurement(1),
        "evaluations": {
            initial.bundle_hash: measurement(2, initial.bundle_hash),
            revised.bundle_hash: not_measured(revised.bundle_hash),
        },
    }
    report = {
        **report_cases([case], task_denominator=85, conditions=("benign",)),
        "namespace": "skillsbench.skill-evolution.v4",
        "cases": [case],
        "usage": {"roles": {}},
    }
    workflow = object.__new__(Workflow)
    workflow.spec = SimpleNamespace(experiment="skillsbench", tasks=tuple(range(85)))
    workflow.root, workflow.execution, workflow.demo = tmp_path, {}, False
    workflow._write_report_md(report)
    markdown = (tmp_path / "REPORT.md").read_text()
    measurements = markdown.split("## Independent measurements", 1)[1].split(
        "## Surrogate checks", 1
    )[0]
    assert measurements.count("S0 / final") == 1
    assert "S2" not in measurements
    assert "| NoSkill | 1 | 0.5 | 50 | MEASURED |" in measurements
    assert "| S0 | NOT_MEASURED | NOT_MEASURED | NOT_MEASURED | not_measured |" in measurements
    assert "GT delta (pp)" in markdown and "Official check unit" in markdown
    assert "Final aliases the selected content's existing evaluation" in markdown
    assert report["version_paired_progress"][-1]["paired_count"] == 0
    assert report["version_paired_progress"][-1]["task_denominator"] == 85
    assert report["version_paired_progress"][-1]["mean_utility_delta"] is None
    assert report["progress"][0]["same_content"] is True
    assert report["progress"][0]["utility_delta"] == 0


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
