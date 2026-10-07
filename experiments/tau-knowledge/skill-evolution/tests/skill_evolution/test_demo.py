"""The user-authorized Bubblewrap demonstration cannot become a formal matrix run."""

import hashlib
import importlib
import json
import shutil

import pytest
import yaml
from tau_skill_evolution import cli
from tau_skill_evolution import preflight as admission
from tau_skill_evolution.spec import ExperimentSpec, load_spec
from tau_skill_evolution.workflow import Workflow
from test_preflight import infrastructure as _infrastructure
from test_workflow import _gold_upstream, _workflow


@pytest.fixture
def infrastructure(tmp_path, monkeypatch):
    return _infrastructure.__wrapped__(tmp_path, monkeypatch)


def _status(arguments):
    try:
        return cli.main(arguments)
    except SystemExit as exc:
        return exc.code


@pytest.mark.parametrize("command", ["create", "evolve", "evaluate", "run"])
@pytest.mark.parametrize(
    "selection",
    [
        [],
        ["--arm", "benign"],
        ["--task", "{first}"],
        ["--task", "{first}", "--arm", "poison-5"],
        ["--task", "{first}", "--arm", "poison-10"],
        ["--task", "{first}", "--task", "{second}", "--arm", "benign"],
    ],
)
def test_demo_rejects_matrix_and_poison_before_starting_workflow(
    tmp_path,
    monkeypatch,
    command,
    selection,
):
    spec = load_spec()
    selectors = [value.format(first=spec.tasks[0], second=spec.tasks[1]) for value in selection]
    monkeypatch.setattr(cli, "preflight", lambda spec, **kwargs: {"ready": True})

    def forbidden_workflow(*args, **kwargs):
        raise AssertionError("unsafe demo selection must be rejected before workflow construction")

    monkeypatch.setattr(cli, "Workflow", forbidden_workflow)
    destination = tmp_path / "must-not-start"
    status = _status([command, "--demo", "--run-dir", str(destination), *selectors])
    assert status == 2 and not destination.exists()


def test_demo_preflight_is_available_without_task_selection(monkeypatch, capsys):
    calls = []

    def preflight(spec, *, demo=False, **kwargs):
        calls.append(demo)
        return {"ready": True, "formal_matrix_result": False}

    monkeypatch.setattr(cli, "preflight", preflight)
    assert cli.main(["preflight", "--demo"]) == 0
    assert calls == [True]
    assert json.loads(capsys.readouterr().out)["formal_matrix_result"] is False


def test_single_benign_cli_demo_propagates_mode_and_runs_stages_in_order(
    tmp_path,
    monkeypatch,
    capsys,
):
    spec = load_spec()
    calls = []

    def preflight(spec, *, demo=False, **kwargs):
        assert demo is True
        return {"ready": True}

    class FakeWorkflow:
        def __init__(
            self,
            configured,
            directory,
            *,
            demo=False,
            demo_task=None,
            interim_report=True,
            runtime=None,
        ):
            assert demo is True and demo_task == spec.tasks[0]
            assert runtime == "bubblewrap-demo"
            assert interim_report is True
            assert configured.tasks == spec.tasks

        def create(self, cells):
            calls.append(("create", cells))

        def evolve(self, cells):
            calls.append(("evolve", cells))

        def evaluate(self, cells):
            calls.append(("evaluate", cells))

        def report(self):
            calls.append(("report", None))
            return {"formal_matrix_result": False}

        def run(self, cells):
            for cell in cells:
                for stage in (self.create, self.evolve, self.evaluate):
                    stage((cell,))
            return self.report()

    monkeypatch.setattr(cli, "preflight", preflight)
    monkeypatch.setattr(cli, "Workflow", FakeWorkflow)
    assert (
        cli.main(
            [
                "run",
                "--demo",
                "--task",
                spec.tasks[0],
                "--arm",
                "benign",
                "--run-dir",
                str(tmp_path / "demo"),
            ]
        )
        == 0
    )
    assert calls == [
        (name, ((spec.tasks[0], "benign"),)) for name in ("create", "evolve", "evaluate")
    ] + [("report", None)]
    assert json.loads(capsys.readouterr().out)["formal_matrix_result"] is False


@pytest.fixture
def demo_spec(tmp_path, monkeypatch):
    original = load_spec()
    root = tmp_path / "experiment"
    for directory in ("configs", "prompts", "injections", "runtime"):
        shutil.copytree(original.root / directory, root / directory)
    config = root / "configs" / "experiment.yaml"
    values = yaml.safe_load(config.read_text())
    # Formal data checks are exercised by preflight tests; fake bank sessions need no copy.
    config.write_text(yaml.safe_dump(values, sort_keys=False))
    rootfs = root / "runtime" / "fixture-rootfs"
    rootfs.mkdir()
    lock = root / "runtime" / "bubblewrap-lock.json"
    lock.write_text(
        json.dumps(
            {
                "rootfs": rootfs.name,
                "files": {},
                "symlinks": {},
                "python_version": [3, 11, 14],
                "dependency_hash": hashlib.sha256(
                    (root / "runtime" / "requirements.lock").read_bytes()
                ).hexdigest(),
                "aggregate_limits_enforced": False,
            },
            indent=2,
        )
    )
    bubblewrap = importlib.import_module("tau_skill_evolution.bubblewrap")
    # Only filesystem identity behavior is under test; no sandbox process is launched.
    monkeypatch.setattr(bubblewrap.RuntimeLock, "validate", lambda self: None)
    configured = load_spec(config)
    upstream = _gold_upstream(tmp_path / "upstream", original.tasks)
    monkeypatch.setattr(ExperimentSpec, "root", property(lambda self: root))
    monkeypatch.setattr(ExperimentSpec, "upstream", property(lambda self: upstream))
    return configured, lock


def _demo(spec, destination, *, bank=None, models=None, corpus=None):
    return Workflow(
        spec,
        destination,
        demo=True,
        demo_task=spec.tasks[0],
        counter=len,
        bank_factory=bank,
        model_factory=models,
        corpus_factory=corpus,
    )


def test_unprepared_demo_runtime_blocks_before_creating_a_journal(demo_spec, tmp_path):
    spec, lock = demo_spec
    lock.unlink()
    destination = tmp_path / "unprepared"
    with pytest.raises((OSError, ValueError, RuntimeError)):
        _demo(spec, destination)
    assert not (destination / "journal").exists()


def test_demo_preflight_fails_closed_for_missing_runtime(infrastructure):
    spec, _, _ = infrastructure
    result = admission.preflight(spec, demo=True)
    assert result["ready"] is False
    failed = [check for check in result["checks"] if not check["ok"]]
    assert any("bubblewrap" in str(check["detail"]).lower() for check in failed)


@pytest.mark.parametrize("first_demo", [False, True])
def test_formal_and_demo_journals_cannot_be_interchanged(demo_spec, tmp_path, first_demo):
    spec, _ = demo_spec
    destination = tmp_path / "shared-run"
    first = _demo(spec, destination) if first_demo else Workflow(spec, destination, counter=len)
    assert first.journal.root.exists()
    with pytest.raises(ValueError, match="identity|configuration|checkpoint"):
        if first_demo:
            Workflow(spec, destination, counter=len)
        else:
            _demo(spec, destination)


def test_demo_identity_binds_actual_runtime_lock_bytes(demo_spec, tmp_path):
    spec, lock = demo_spec
    destination = tmp_path / "bound-runtime"
    workflow = _demo(spec, destination)
    execution = workflow.identity["execution"]
    assert execution["runtime_lock_hash"] == hashlib.sha256(lock.read_bytes()).hexdigest()
    assert execution["backend"] == "bubblewrap-demo"
    assert execution["formal_matrix_result"] is False
    assert execution["aggregate_limits_enforced"] is False
    # Even semantically identical but differently serialized lock bytes require a new run.
    lock.write_text(json.dumps(json.loads(lock.read_text()), indent=4))
    with pytest.raises(ValueError, match="identity|configuration|checkpoint"):
        _demo(spec, destination)


def test_demo_cannot_access_other_tasks_or_poison_cells(demo_spec, tmp_path):
    spec, _ = demo_spec
    workflow = _demo(spec, tmp_path / "restricted")
    for cell in (
        (spec.tasks[1], "benign"),
        (spec.tasks[0], "poison-5"),
        (spec.tasks[0], "poison-10"),
    ):
        with pytest.raises(ValueError):
            workflow._cell(*cell)


@pytest.mark.parametrize("stage", ["create", "evolve", "evaluate"])
def test_demo_public_stages_reject_matrix_before_bank_or_model_access(demo_spec, tmp_path, stage):
    spec, _ = demo_spec

    def forbidden(*args, **kwargs):
        raise AssertionError("invalid demo cells must be rejected before bank or model access")

    workflow = _demo(spec, tmp_path / stage, bank=forbidden, models=forbidden, corpus=forbidden)
    with pytest.raises(ValueError):
        getattr(workflow, stage)(spec.cells)


def test_demo_report_is_explicitly_not_a_formal_matrix_result(demo_spec, tmp_path):
    spec, _ = demo_spec
    template, _, requests = _workflow(tmp_path / "fake-factories")
    workflow = _demo(
        spec,
        tmp_path / "demo-report",
        bank=template.bank_factory,
        models=template.model_factory,
        corpus=template.corpus_factory,
    )
    cell = (spec.tasks[0], "benign")
    workflow.create((cell,))
    workflow.evaluate((cell,))
    report = workflow.report()
    assert report["formal_matrix_result"] is False
    assert report["run_mode"] == "single-task-demo"
    assert report["execution"]["backend"] == "bubblewrap-demo"
    assert report["execution"]["aggregate_limits_enforced"] is False
    assert [role for role, _ in requests].count("generator") == 1
    executed = [case for case in report["cases"] if case["status"] != "NOT_MEASURED"]
    assert {case["condition"] for case in executed} == {"benign"}
    assert {case["task_id"] for case in executed} == {spec.tasks[0]}
    markdown = (workflow.root / "REPORT.md").read_text()
    assert "formal_matrix_result=false" in markdown
    assert "Aggregate cgroup CPU/memory/PID limits are not enforced" in markdown
