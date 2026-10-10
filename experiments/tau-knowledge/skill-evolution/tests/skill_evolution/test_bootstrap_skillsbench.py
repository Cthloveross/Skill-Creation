import importlib.util
import json
import subprocess
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from tau_skill_evolution.constants import EXPERIMENT_ROOT


@pytest.fixture
def bootstrap_cli(monkeypatch, tmp_path):
    module_spec = importlib.util.spec_from_file_location(
        "bootstrap_skillsbench", EXPERIMENT_ROOT / "scripts/bootstrap_skillsbench.py"
    )
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    root = tmp_path / "project/experiments/tau-knowledge/skill-evolution"
    canonical = root / "configs/skillsbench.yaml"
    canonical.parent.mkdir(parents=True)
    values = {
        "embedding": {
            "gpu_uuid": "GPU-original",
            "model": "Qwen/Qwen3-Embedding-4B",
            "revision": "pinned-revision",
            "endpoint": "http://127.0.0.1:18140/v1",
        },
        "source": {"runtime_lock": "runtime/skillsbench-docker-{task_id}-v4-lock.json"},
        "tasks": {"selected": [f"task-{index:03d}" for index in range(85)]},
    }
    canonical.write_text(yaml.safe_dump(values))
    (root / module.MATRIX_MANIFEST).write_text('{"matrix":"frozen"}')

    class Spec:
        def __init__(self, path):
            self.path = path
            self.values = yaml.safe_load(path.read_text())
            self.root = root
            self.tasks = tuple(self.values["tasks"]["selected"])

        @property
        def identity(self):
            locks = [
                root / self.values["source"]["runtime_lock"].replace("{task_id}", task)
                for task in self.tasks
            ]
            identity = module._hash(self.path) + "".join(
                module._hash(path) if path.exists() else "missing" for path in locks
            )
            return {"identity_hash": module.hashlib.sha256(identity.encode()).hexdigest()}

    calls = []

    def run(command, path):
        calls.append(command)
        path.write_text("completed\n")
        if "--docker" in command:
            template = command[command.index("--runtime-lock") + 1]
            for task in values["tasks"]["selected"]:
                lock = Path(template.replace("{task_id}", task))
                lock.parent.mkdir(parents=True, exist_ok=True)
                lock.write_text(f'{{"task_id":"{task}"}}')

    @contextmanager
    def embedding(spec, log):
        calls.append(["service-start", spec.values["embedding"]["gpu_uuid"]])
        try:
            yield "owned_temporary_service"
        finally:
            calls.append(["service-stop"])

    monkeypatch.setattr(module, "load_spec", Spec)
    monkeypatch.setattr(module, "_run", run)
    monkeypatch.setattr(module, "_resolve_gpu", lambda gpu: "GPU-chosen")
    monkeypatch.setattr(module.shutil, "which", lambda command: f"/usr/bin/{command}")
    monkeypatch.setattr(module, "_embedding_service", embedding)
    monkeypatch.setattr(module, "validate_matrix_manifest", lambda spec: {})
    return module, root, calls


def test_clone_preparation_uses_local_locks_and_preserves_frozen_inputs(bootstrap_cli):
    module, root, calls = bootstrap_cli
    canonical = root / "configs/skillsbench.yaml"
    original = canonical.read_bytes()
    matrix = (root / module.MATRIX_MANIFEST).read_bytes()
    binding = module.bootstrap("0", 8, root)
    assert binding["status"] == "PREPARED" and binding["ready"] is False
    assert len(binding["runtime_locks"]) == 85
    assert canonical.read_bytes() == original
    assert (root / module.MATRIX_MANIFEST).read_bytes() == matrix
    local = yaml.safe_load((root / binding["config_path"]).read_text())
    assert local == module._local_values(
        yaml.safe_load(original), "GPU-chosen", binding["canonical_identity_hash"]
    )
    assert not any("--freeze-matrix" in call for call in calls)
    task_build = next(call for call in calls if "--docker" in call)
    assert task_build[-1] == str(root / module._lock_template(binding["canonical_identity_hash"]))
    assert task_build[task_build.index("--jobs") + 1] == "8"
    assert calls.index(["service-stop"]) < calls.index(task_build)
    assert module.check_binding(root) == binding
    completed = list(calls)
    assert module.bootstrap("0", 8, root)["reused"] is True
    assert calls == completed


def test_matrix_mismatch_stops_before_images_and_never_publishes_binding(
    bootstrap_cli, monkeypatch
):
    module, root, calls = bootstrap_cli

    def mismatch(spec):
        raise ValueError("skillsbench_injection_matrix_manifest_changed")

    monkeypatch.setattr(module, "validate_matrix_manifest", mismatch)
    with pytest.raises(ValueError, match="matrix_manifest_changed"):
        module.bootstrap("0", 8, root)
    assert ["service-stop"] in calls
    assert not any("--docker" in call for call in calls)
    assert not list((root / module.SETUP / "builds").glob("*/skillsbench.yaml"))
    assert not (root / module.SETUP / "binding.json").exists()
    assert (root / module.MATRIX_MANIFEST).read_text() == '{"matrix":"frozen"}'


def test_source_drift_during_preparation_is_rejected(bootstrap_cli, monkeypatch):
    module, root, _calls = bootstrap_cli
    run = module._run

    def mutate(command, path):
        run(command, path)
        if "--docker" in command:
            config = root / "configs/skillsbench.yaml"
            config.write_text(config.read_text() + "changed: true\n")

    monkeypatch.setattr(module, "_run", mutate)
    with pytest.raises(ValueError, match="identity changed"):
        module.bootstrap("0", 8, root)
    assert not list((root / module.SETUP / "builds").glob("*/skillsbench.yaml"))
    assert not (root / module.SETUP / "binding.json").exists()


@pytest.mark.parametrize("part", ["source", "config", "lock", "matrix"])
def test_check_rejects_binding_drift_without_dispatch(bootstrap_cli, part):
    module, root, calls = bootstrap_cli
    binding = module.bootstrap("0", 8, root)
    if part == "source":
        target = root / "configs/skillsbench.yaml"
    elif part == "config":
        target = root / binding["config_path"]
    elif part == "lock":
        target = root / binding["runtime_locks"][0]["path"]
    else:
        target = root / module.MATRIX_MANIFEST
    target.write_text(target.read_text() + "\n")
    previous = list(calls)
    with pytest.raises(ValueError):
        module.check_binding(root)
    assert calls == previous


def test_even_rehashed_local_config_cannot_change_experiment_parameters(bootstrap_cli):
    module, root, _calls = bootstrap_cli
    sealed = module.bootstrap("0", 8, root)
    config = root / sealed["config_path"]
    values = yaml.safe_load(config.read_text())
    values["embedding"]["revision"] = "different-revision"
    config.write_text(yaml.safe_dump(values))
    path = root / module.SETUP / "binding.json"
    binding = json.loads(path.read_text())
    binding["config_sha256"] = module._hash(config)
    binding["identity_hash"] = module.load_spec(config).identity["identity_hash"]
    path.write_text(json.dumps(binding))
    with pytest.raises(ValueError, match="unapproved_changes"):
        module.check_binding(root)


def test_preparation_binding_cannot_claim_task_readiness(bootstrap_cli):
    module, root, _calls = bootstrap_cli
    module.bootstrap("0", 8, root)
    path = root / module.SETUP / "binding.json"
    binding = json.loads(path.read_text())
    binding["ready"] = True
    path.write_text(json.dumps(binding))
    with pytest.raises(ValueError, match="binding_invalid"):
        module.check_binding(root)


def test_failed_build_keeps_reusable_locks_but_no_published_configuration(
    bootstrap_cli, monkeypatch
):
    module, root, _calls = bootstrap_cli
    run = module._run

    def fail(command, path):
        run(command, path)
        if "--docker" in command:
            raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(module, "_run", fail)
    with pytest.raises(subprocess.CalledProcessError):
        module.bootstrap("0", 8, root)
    assert len(list((root / module.SETUP / "builds").glob("*/runtime/*.json"))) == 85
    assert not list((root / module.SETUP / "builds").glob("*/skillsbench.yaml"))
    assert not (root / module.SETUP / "binding.json").exists()
    monkeypatch.setattr(module, "_run", run)
    assert module.bootstrap("0", 8, root)["prepared"] is True


def test_source_update_builds_new_identity_and_preserves_previous_environment(bootstrap_cli):
    module, root, _calls = bootstrap_cli
    previous = module.bootstrap("0", 8, root)
    originals = {
        path: (root / path).read_bytes()
        for path in [previous["config_path"], *(r["path"] for r in previous["runtime_locks"])]
    }
    canonical = root / "configs/skillsbench.yaml"
    canonical.write_text(canonical.read_text() + "source_update: true\n")
    current = module.bootstrap("0", 8, root)
    assert current["canonical_identity_hash"] != previous["canonical_identity_hash"]
    assert current["config_path"] != previous["config_path"]
    assert not set(r["path"] for r in previous["runtime_locks"]) & set(
        r["path"] for r in current["runtime_locks"]
    )
    assert all((root / path).read_bytes() == raw for path, raw in originals.items())
    assert module.check_binding(root) == current


def test_failed_source_update_keeps_original_active_binding(bootstrap_cli, monkeypatch):
    module, root, _calls = bootstrap_cli
    previous = module.bootstrap("0", 8, root)
    active = root / module.SETUP / "binding.json"
    binding_bytes = active.read_bytes()
    previous_config = (root / previous["config_path"]).read_bytes()
    original_lock = (root / previous["runtime_locks"][0]["path"]).read_bytes()
    canonical = root / "configs/skillsbench.yaml"
    canonical.write_text(canonical.read_text() + "source_update: true\n")
    run = module._run

    def fail(command, path):
        run(command, path)
        if "--docker" in command:
            raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(module, "_run", fail)
    with pytest.raises(subprocess.CalledProcessError):
        module.bootstrap("0", 8, root)
    assert active.read_bytes() == binding_bytes
    assert (root / previous["config_path"]).read_bytes() == previous_config
    assert (root / previous["runtime_locks"][0]["path"]).read_bytes() == original_lock
    with pytest.raises(ValueError, match="source_changed"):
        module.check_binding(root)
    monkeypatch.setattr(module, "_run", run)
    assert (
        module.bootstrap("0", 8, root)["canonical_identity_hash"]
        != previous["canonical_identity_hash"]
    )


def test_same_source_corrupted_binding_cannot_trigger_automatic_rebuild(bootstrap_cli):
    module, root, calls = bootstrap_cli
    binding = module.bootstrap("0", 8, root)
    config = root / binding["config_path"]
    config.write_text(config.read_text() + "modified: true\n")
    previous = list(calls)
    with pytest.raises(ValueError, match="config_changed"):
        module.bootstrap("0", 8, root)
    assert calls == previous


def test_late_source_drift_does_not_replace_original_active_binding(bootstrap_cli, monkeypatch):
    module, root, _calls = bootstrap_cli
    previous = module.bootstrap("0", 8, root)
    active = root / module.SETUP / "binding.json"
    original_binding = active.read_bytes()
    canonical = root / "configs/skillsbench.yaml"
    canonical.write_text(canonical.read_text() + "source_update: true\n")
    identity = module.load_spec(canonical).identity["identity_hash"]
    candidate = root / module._build_directory(identity) / "skillsbench.yaml"
    hash_file = module._hash
    injected = False

    def late_drift(path):
        nonlocal injected
        if path == candidate and not injected:
            injected = True
            canonical.write_text(canonical.read_text() + "late_source_update: true\n")
        return hash_file(path)

    monkeypatch.setattr(module, "_hash", late_drift)
    with pytest.raises(ValueError, match="source_changed"):
        module.bootstrap("0", 8, root)
    assert injected
    assert active.read_bytes() == original_binding
    assert (root / previous["config_path"]).is_file()


def test_existing_embedding_service_is_never_owned_or_stopped(bootstrap_cli, monkeypatch):
    module, root, _calls = bootstrap_cli
    monkeypatch.setattr(module, "_embedding_available", lambda *args: True)
    monkeypatch.setattr(
        module.subprocess, "Popen", lambda *args, **kw: pytest.fail("must not start a service")
    )
    # Use the original context manager rather than the preparation fixture's fake.
    original = importlib.util.spec_from_file_location(
        "original_bootstrap", EXPERIMENT_ROOT / "scripts/bootstrap_skillsbench.py"
    )
    actual = importlib.util.module_from_spec(original)
    original.loader.exec_module(actual)
    monkeypatch.setattr(actual, "_embedding_available", lambda *args: True)
    spec = SimpleNamespace(values={"embedding": {"endpoint": "local", "model": "model"}})
    with actual._embedding_service(spec, root / "service.log") as result:
        assert result == "existing_service"
    assert not (root / "service.log").exists()


@pytest.mark.parametrize("failed", [False, True])
@pytest.mark.parametrize("leader_exited", [False, True])
def test_owned_embedding_service_cleanup_on_success_and_exception(
    bootstrap_cli, monkeypatch, failed, leader_exited
):
    module, root, _calls = bootstrap_cli
    original = importlib.util.spec_from_file_location(
        "original_bootstrap", EXPERIMENT_ROOT / "scripts/bootstrap_skillsbench.py"
    )
    actual = importlib.util.module_from_spec(original)
    original.loader.exec_module(actual)
    statuses = iter([False, True])
    monkeypatch.setattr(actual, "_embedding_available", lambda *args: next(statuses))
    signals = []
    process = SimpleNamespace(
        pid=4321, poll=lambda: 0 if leader_exited else None, wait=lambda **kw: None
    )
    monkeypatch.setattr(actual.subprocess, "Popen", lambda *args, **kw: process)
    monkeypatch.setattr(actual, "embedding_argv", lambda spec: ["vllm", "serve"])
    monkeypatch.setattr(actual.os, "killpg", lambda pid, sig: signals.append((pid, sig)))
    spec = SimpleNamespace(
        values={"embedding": {"endpoint": "local", "model": "model", "gpu_uuid": "GPU-test"}}
    )
    if failed:
        with (
            pytest.raises(ValueError, match="body failed"),
            actual._embedding_service(spec, root / "service.log"),
        ):
            raise ValueError("body failed")
    else:
        with actual._embedding_service(spec, root / "service.log"):
            pass
    assert signals == [(4321, actual.signal.SIGTERM), (4321, actual.signal.SIGKILL)]


def test_real_spec_accepts_local_gpu_and_locks_without_changing_frozen_matrix(tmp_path):
    from tau_skill_evolution.spec import load_spec

    original = importlib.util.spec_from_file_location(
        "original_bootstrap", EXPERIMENT_ROOT / "scripts/bootstrap_skillsbench.py"
    )
    module = importlib.util.module_from_spec(original)
    original.loader.exec_module(module)
    canonical = load_spec(EXPERIMENT_ROOT / "configs/skillsbench.yaml")
    frozen_matrix = (EXPERIMENT_ROOT / module.MATRIX_MANIFEST).read_bytes()
    config = tmp_path / "skillsbench.yaml"
    config.write_text(
        yaml.safe_dump(
            module._local_values(canonical.values, "0", canonical.identity["identity_hash"])
        )
    )
    local = load_spec(config)
    assert local.tasks == canonical.tasks
    assert local.values["provider"] == canonical.values["provider"]
    assert local.identity["identity_hash"] != canonical.identity["identity_hash"]
    assert (EXPERIMENT_ROOT / module.MATRIX_MANIFEST).read_bytes() == frozen_matrix
