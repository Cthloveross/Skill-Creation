"""Admission is checked against independent infrastructure failure scenarios."""

import hashlib
import io
import json
import shutil
import subprocess
from copy import deepcopy
from dataclasses import replace

import pytest
from tau_skill_evolution import cli
from tau_skill_evolution import preflight as admission
from tau_skill_evolution.container import DockerRunner
from tau_skill_evolution.spec import ExperimentSpec, load_spec


@pytest.fixture
def infrastructure(tmp_path, monkeypatch):
    original = load_spec()
    config_path = tmp_path / "configs" / "experiment.yaml"
    config_path.parent.mkdir()
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    shutil.copyfile(original.root / "runtime" / "requirements.lock", runtime / "requirements.lock")
    values = deepcopy(original.values)
    values["source"]["upstream_checkout"] = str(original.upstream)
    values["provider"]["region"] = None
    spec = replace(original, path=config_path, values=values)
    monkeypatch.setattr(ExperimentSpec, "root", property(lambda self: tmp_path))
    monkeypatch.setattr(
        admission,
        "bedrock_authentication",
        lambda _: {"status": 200, "generation_requested": False},
    )
    image_id = "sha256:" + "b" * 64
    lock = {
        "image": "tau-skill-python:3.11",
        "digest": image_id,
        "digest_kind": "image_id",
        "dependency_hash": hashlib.sha256((runtime / "requirements.lock").read_bytes()).hexdigest(),
    }
    (runtime / "image-lock.json").write_text(json.dumps(lock))
    monkeypatch.setenv(spec.values["provider"]["api_key_env"], "offline-test-credential")
    monkeypatch.setenv(spec.values["provider"]["region_env"], "us-east-1")
    monkeypatch.setattr(admission, "UPSTREAM_ROOT", spec.upstream)
    state = {"fault": None, "requests": []}

    def pinned_snapshot(*, config_root):
        assert config_root == spec.root / "configs"
        if state["fault"] == "upstream":
            raise ValueError("upstream commit/tree differs from the pinned snapshot")
        return {"commit": spec.values["source"]["commit"]}

    def command_available(name):
        return None if state["fault"] == "cli_missing" else "/usr/bin/docker"

    def official_python(command, **kwargs):
        return json.dumps([[3, 12, 14], str(spec.upstream / ".venv")])

    def process(command, **kwargs):
        state["requests"].append(command)
        if "info" in command:
            denied = state["fault"] == "socket_permission"
            return subprocess.CompletedProcess(
                command,
                1 if denied else 0,
                "" if denied else "28.0.0",
                "permission denied while connecting to /var/run/docker.sock" if denied else "",
            )
        if "inspect" in command:
            if state["fault"] == "image_missing":
                return subprocess.CompletedProcess(command, 1, "", "No such image")
            actual = (
                "sha256:" + "c" * 64
                if state["fault"] == "digest_mismatch"
                else state.get("image_id", image_id)
            )
            metadata = state.get(
                "image_metadata", [{"Id": actual, "RepoDigests": state.get("repo_digests", [])}]
            )
            return subprocess.CompletedProcess(command, 0, json.dumps(metadata), "")
        raise AssertionError(f"unexpected infrastructure call: {command}")

    def container_admission(self):
        good = state["fault"] != "installed_dependencies"
        return {"ready": good and state["fault"] != "secondary_not_ready", "dependencies": good}

    monkeypatch.setattr(admission, "verify_tracked_snapshot", pinned_snapshot)
    monkeypatch.setattr(admission.shutil, "which", command_available)
    monkeypatch.setattr(admission.subprocess, "check_output", official_python)
    monkeypatch.setattr(admission.subprocess, "run", process)
    monkeypatch.setattr(DockerRunner, "preflight", container_admission)
    monkeypatch.setattr(
        admission.urllib.request,
        "urlopen",
        lambda *args, **kwargs: io.BytesIO(
            json.dumps({"data": [{"id": spec.values["embedding"]["model"]}]}).encode()
        ),
    )
    return spec, state, lock


def test_preflight_ready_only_when_all_infrastructure_ready(infrastructure):
    spec, _, _ = infrastructure
    result = admission.preflight(spec)
    assert result["ready"]
    assert all(check["ok"] for check in result["checks"])


@pytest.mark.parametrize(
    "fault,check_name", [("cli_missing", "docker_cli"), ("socket_permission", "docker_daemon")]
)
def test_skillsbench_reports_docker_access_even_before_task_images_exist(
    infrastructure, monkeypatch, fault, check_name
):
    from tau_skill_evolution import skillsbench

    spec, state, _ = infrastructure
    monkeypatch.setattr(ExperimentSpec, "experiment", property(lambda self: "skillsbench"))
    monkeypatch.setattr(
        skillsbench,
        "skillsbench_preflight",
        lambda *args, **kwargs: {
            "ready": False,
            "checks": [
                {"name": "skillsbench_environment:task", "ok": False, "detail": "unprepared"}
            ],
        },
    )
    state["fault"] = fault
    result = admission.preflight(spec)
    checks = {check["name"]: check for check in result["checks"]}
    assert not result["ready"] and not result["formal_matrix_result"]
    assert not checks[check_name]["ok"]
    assert not checks["skillsbench_environment:task"]["ok"]


def test_missing_region_blocks_live_without_inventing_an_endpoint(infrastructure, monkeypatch):
    spec, _, _ = infrastructure
    monkeypatch.delenv(spec.values["provider"]["region_env"], raising=False)
    result = admission.preflight(spec)
    check = next(check for check in result["checks"] if check["name"] == "bedrock_region")
    assert not check["ok"] and not result["ready"]
    assert "missing_region" in check["detail"]


def test_wrong_model_is_explicitly_unsupported_without_fallback(infrastructure):
    spec, _, _ = infrastructure
    spec.values["provider"]["model"] = "openai.gpt-oss-120b"
    result = admission.preflight(spec)
    check = next(check for check in result["checks"] if check["name"] == "bedrock_model")
    assert not check["ok"] and not result["ready"]
    assert "unsupported_model" in check["detail"]


@pytest.mark.parametrize(
    "fault,check_name,detail",
    [
        ("cli_missing", "docker_cli", "CLI"),
        ("socket_permission", "docker_daemon", "permission denied"),
        ("image_missing", "docker_image", "missing"),
        ("digest_mismatch", "docker_image", "digest mismatch"),
        ("upstream", "pinned_upstream", "commit/tree"),
        ("installed_dependencies", "container_dependencies", "dependencies"),
        ("secondary_not_ready", "container_dependencies", "readiness"),
    ],
)
def test_preflight_distinguishes_infrastructure_failures(infrastructure, fault, check_name, detail):
    spec, state, _ = infrastructure
    state["fault"] = fault
    result = admission.preflight(spec)
    check = next(check for check in result["checks"] if check["name"] == check_name)
    assert not result["ready"] and not check["ok"]
    assert not result["formal_matrix_result"]
    assert not result["aggregate_limits_enforced"]
    assert detail.lower() in str(check["detail"]).lower()


def test_dependency_file_tampering_blocks_admission(infrastructure):
    spec, _, _ = infrastructure
    (spec.root / "runtime" / "requirements.lock").write_text("numpy==2.2.6\n")
    result = admission.preflight(spec)
    check = next(check for check in result["checks"] if check["name"] == "dependency_lock")
    assert not check["ok"] and not result["ready"]


def test_repository_digest_admission_uses_repo_identity_not_image_id(infrastructure):
    spec, state, lock = infrastructure
    lock.update(image="registry.invalid/tau-skill:3.11", digest_kind="repo_digest")
    reference = f"{lock['image']}@{lock['digest']}"
    state["image_id"] = "sha256:" + "c" * 64
    state["repo_digests"] = [reference]
    (spec.root / "runtime" / "image-lock.json").write_text(json.dumps(lock))
    result = admission.preflight(spec)
    assert result["ready"]
    assert any(command[-1] == reference for command in state["requests"] if "inspect" in command)


def test_matching_image_id_cannot_mask_wrong_repository_digest(infrastructure):
    spec, state, lock = infrastructure
    lock.update(image="registry.invalid/tau-skill:3.11", digest_kind="repo_digest")
    state["repo_digests"] = [f"{lock['image']}@sha256:" + "c" * 64]
    (spec.root / "runtime" / "image-lock.json").write_text(json.dumps(lock))
    result = admission.preflight(spec)
    check = next(check for check in result["checks"] if check["name"] == "docker_image")
    assert not check["ok"] and not result["ready"]
    assert "digest mismatch" in check["detail"]


@pytest.mark.parametrize("metadata", [{}, [], ["malformed"]])
def test_malformed_image_inspection_blocks_admission(infrastructure, metadata):
    spec, state, _ = infrastructure
    state["image_metadata"] = metadata
    result = admission.preflight(spec)
    check = next(check for check in result["checks"] if check["name"] == "docker_image")
    assert not check["ok"] and not result["ready"]
    assert "malformed" in check["detail"]


def test_one_hashed_requirement_cannot_mask_unhashed_dependency(infrastructure):
    spec, _, lock = infrastructure
    dependency_lock = spec.root / "runtime" / "requirements.lock"
    dependency_lock.write_text(
        "numpy==2.2.6 --hash=sha256:" + "a" * 64 + "\npandas==2.2.3\npytest==8.4.2\n"
    )
    lock["dependency_hash"] = hashlib.sha256(dependency_lock.read_bytes()).hexdigest()
    (spec.root / "runtime" / "image-lock.json").write_text(json.dumps(lock))
    result = admission.preflight(spec)
    check = next(check for check in result["checks"] if check["name"] == "dependency_lock")
    assert not check["ok"] and not result["ready"]


@pytest.mark.parametrize("wrong_dependency", ["numpy==2.2.5", "pandas==2.2.2", "pytest==8.4.1"])
def test_hashed_wrong_dependency_version_blocks_admission(infrastructure, wrong_dependency):
    spec, _, lock = infrastructure
    dependency_lock = spec.root / "runtime" / "requirements.lock"
    original = dependency_lock.read_text()
    name = wrong_dependency.split("==", 1)[0]
    expected = {"numpy": "2.2.6", "pandas": "2.2.3", "pytest": "8.4.2"}[name]
    dependency_lock.write_text(original.replace(f"{name}=={expected}", wrong_dependency))
    lock["dependency_hash"] = hashlib.sha256(dependency_lock.read_bytes()).hexdigest()
    (spec.root / "runtime" / "image-lock.json").write_text(json.dumps(lock))
    result = admission.preflight(spec)
    check = next(check for check in result["checks"] if check["name"] == "dependency_lock")
    assert not check["ok"] and not result["ready"]


@pytest.mark.parametrize("command", ["create", "evolve", "evaluate", "run"])
@pytest.mark.parametrize(
    "fault",
    [
        "cli_missing",
        "socket_permission",
        "image_missing",
        "digest_mismatch",
        "upstream",
        "installed_dependencies",
        "secondary_not_ready",
        "lock_hash",
        "digest_unprepared",
    ],
)
def test_every_live_entrypoint_blocks_before_workflow(
    infrastructure,
    monkeypatch,
    tmp_path,
    capsys,
    command,
    fault,
):
    spec, state, image_lock = infrastructure
    state["fault"] = fault
    if fault == "lock_hash":
        (spec.root / "runtime" / "requirements.lock").write_text("tampered lock")
    if fault == "digest_unprepared":
        image_lock["digest"] = None
        (spec.root / "runtime" / "image-lock.json").write_text(json.dumps(image_lock))
    monkeypatch.setattr(cli, "load_spec", lambda _: spec)

    def unauthorized_workflow(*args, **kwargs):
        raise AssertionError("an unavailable boundary must block before starting any workflow")

    monkeypatch.setattr(cli, "Workflow", unauthorized_workflow)
    destination = tmp_path / "never-started"
    assert cli.main([command, "--run-dir", str(destination)]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["ready"] is False
    assert not destination.exists()
