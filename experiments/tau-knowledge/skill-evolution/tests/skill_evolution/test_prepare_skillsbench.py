import importlib.util
import json
import subprocess
import sys
import threading
from pathlib import Path
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


def test_non_dense_preparation_keeps_current_python(preparation_cli, monkeypatch):
    calls = []
    monkeypatch.setattr(preparation_cli.os, "execve", lambda *args: calls.append(args))
    preparation_cli._ensure_dense_runtime(
        SimpleNamespace(index_settings=None, all_indices=False, freeze_matrix=False),
        SimpleNamespace(error=lambda message: pytest.fail(message)),
    )
    assert calls == []


def test_dense_preparation_reexecs_in_pinned_embedding_python(
    preparation_cli, monkeypatch, tmp_path
):
    target = tmp_path / "embedding/.venv/bin/python"
    target.parent.mkdir(parents=True)
    target.write_text("")
    calls = []
    settings = json.dumps({"vllm": "embedding/.venv/bin/vllm"})
    monkeypatch.setattr(preparation_cli.importlib.util, "find_spec", lambda name: None)
    monkeypatch.setattr(preparation_cli, "ROOT", tmp_path)
    monkeypatch.setattr(preparation_cli.sys, "executable", "/usr/bin/python3")
    monkeypatch.setattr(preparation_cli.sys, "argv", ["prepare", "--index-settings", settings])
    monkeypatch.setattr(
        preparation_cli.os,
        "execve",
        lambda executable, argv, env: calls.append((executable, argv, env)),
    )
    preparation_cli._ensure_dense_runtime(
        SimpleNamespace(
            index_settings=settings,
            all_indices=False,
            freeze_matrix=False,
        ),
        SimpleNamespace(error=lambda message: pytest.fail(message)),
    )
    assert calls == [
        (
            str(target.absolute()),
            [
                str(target.absolute()),
                str(Path(preparation_cli.__file__).resolve()),
                "--index-settings",
                settings,
            ],
            preparation_cli.os.environ,
        )
    ]


def test_parent_dispatches_only_dense_worker_to_embedding_python(
    preparation_cli, monkeypatch, tmp_path
):
    target = tmp_path / "data/embedding/.venv/bin/python"
    target.parent.mkdir(parents=True)
    target.write_text("")
    directory = tmp_path / "pool"
    calls = []

    def run(command, **options):
        calls.append((command, options))
        return SimpleNamespace(stdout='{"ready": true, "corpus_hash": "sealed"}\n')

    monkeypatch.setattr(preparation_cli, "ROOT", tmp_path)
    monkeypatch.setattr(preparation_cli.subprocess, "run", run)
    result = preparation_cli._prepare_dense_in_pinned_runtime(
        {"vllm": "data/embedding/.venv/bin/vllm", "model": "fixture"}, directory
    )
    assert result == {"ready": True, "corpus_hash": "sealed"}
    command, options = calls[0]
    assert command[:3] == [
        str(target.absolute()),
        str(Path(preparation_cli.__file__).resolve()),
        "--index-settings",
    ]
    assert command[-2:] == ["--pool-directory", str(directory)]
    assert options == {
        "check": True,
        "capture_output": True,
        "text": True,
        "timeout": 3600,
    }
