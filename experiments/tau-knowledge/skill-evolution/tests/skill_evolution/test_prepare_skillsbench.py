import importlib.util
import json
import subprocess
import sys
import threading
from types import SimpleNamespace

import pytest
from tau_skill_evolution.constants import EXPERIMENT_ROOT


@pytest.fixture
def preparation_cli(monkeypatch):
    from tau_skill_evolution import skillsbench

    spec = importlib.util.spec_from_file_location(
        "prepare_skillsbench", EXPERIMENT_ROOT / "scripts/prepare_skillsbench.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(
        skillsbench,
        "SkillsBenchSource",
        lambda root: SimpleNamespace(manifest={"tasks": ["one", "two", "three", "four"]}),
    )
    return module


def test_parallel_preparation_is_bounded_and_reports_every_task(
    preparation_cli, monkeypatch, capsys
):
    from tau_skill_evolution import skillsbench_runtime

    barrier = threading.Barrier(2, timeout=5)
    lock = threading.Lock()
    active = peak = 0

    def prepare(root, task, **settings):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        barrier.wait()
        with lock:
            active -= 1
        return {"prepared": True, "ready": False, "requires_fresh_preflight": True}

    monkeypatch.setattr(skillsbench_runtime, "prepare_docker", prepare)
    monkeypatch.setattr(sys, "argv", ["prepare", "--docker", "--all-tasks", "--jobs", "2"])
    preparation_cli.main()
    rows = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert peak == 2
    assert {row["task_id"] for row in rows} == {"one", "two", "three", "four"}
    assert all(row["prepared"] and not row["ready"] for row in rows)


def test_build_error_does_not_discard_other_task_results(preparation_cli, monkeypatch, capsys):
    from tau_skill_evolution import skillsbench_runtime

    def prepare(root, task, **settings):
        if task == "one":
            raise subprocess.CalledProcessError(1, ["docker", "build"])
        return {"prepared": True, "ready": False}

    monkeypatch.setattr(skillsbench_runtime, "prepare_docker", prepare)
    monkeypatch.setattr(sys, "argv", ["prepare", "--docker", "--all-tasks", "--jobs", "2"])
    with pytest.raises(SystemExit) as stopped:
        preparation_cli.main()
    assert stopped.value.code == 1
    rows = {row["task_id"]: row for row in map(json.loads, capsys.readouterr().out.splitlines())}
    assert len(rows) == 4
    assert not rows["one"]["prepared"] and rows["one"]["error"]
    assert all(rows[task]["prepared"] for task in ("two", "three", "four"))


@pytest.mark.parametrize(
    "arguments",
    [
        ["--docker", "--all-tasks", "--jobs", "0"],
        ["--docker", "--all-tasks", "--jobs", "-1"],
        ["--docker", "--jobs", "2"],
        ["--workspace", "--all-tasks", "--jobs", "2"],
    ],
)
def test_invalid_parallelism_is_rejected_before_dispatch(preparation_cli, monkeypatch, arguments):
    from tau_skill_evolution import skillsbench_runtime

    calls = []
    monkeypatch.setattr(
        skillsbench_runtime, "prepare_docker", lambda *args, **kw: calls.append(args)
    )
    monkeypatch.setattr(sys, "argv", ["prepare", *arguments])
    with pytest.raises(SystemExit) as stopped:
        preparation_cli.main()
    assert stopped.value.code == 2
    assert calls == []
