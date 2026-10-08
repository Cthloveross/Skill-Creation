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
from tau_skill_evolution.constants import WORKER_PYTHON_VERSION
from tau_skill_evolution.container import DockerRunner
from tau_skill_evolution.spec import ExperimentSpec, load_spec


@pytest.mark.parametrize(
    "model,transport,prefix",
    [
        ("openai.gpt-5.6-terra", "bedrock-responses", "openai"),
        ("anthropic.claude-opus-4-8", "bedrock-messages", "anthropic"),
    ],
)
def test_authentication_uses_shared_catalog_without_requesting_generation(
    monkeypatch, model, transport, prefix
):
    original = load_spec()
    values = deepcopy(original.values)
    values["provider"].update(model=model, transport=transport, region="us-east-1")
    spec = replace(original, values=values)
    monkeypatch.setattr(admission, "bearer_token_source", lambda _: lambda: "offline-fixture")
    requests = []

    class Response(io.BytesIO):
        status = 200

    def opener(request, *, timeout):
        requests.append(request)
        assert request.full_url == "https://bedrock-mantle.us-east-1.api.aws/v1/models"
        assert request.get_method() == "GET" and request.data is None
        return Response(json.dumps({"data": [{"id": model}]}).encode())

    monkeypatch.setattr(admission.urllib.request, "urlopen", opener)
    assert spec.provider_settings["api_base"].endswith(f"/{prefix}/v1")
    assert admission.bedrock_authentication(spec) == {
        "status": 200,
        "model": model,
        "generation_requested": False,
    }
    assert len(requests) == 1


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
        return json.dumps([list(WORKER_PYTHON_VERSION), str(spec.upstream / ".venv")])

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


def test_skillsbench_admission_does_not_claim_project_resource_limits(infrastructure, monkeypatch):
    from tau_skill_evolution import skillsbench

    spec, _, _ = infrastructure
    monkeypatch.setattr(ExperimentSpec, "experiment", property(lambda self: "skillsbench"))
    monkeypatch.setattr(
        skillsbench,
        "skillsbench_preflight",
        lambda *args, **kwargs: {
            "ready": True,
            "checks": [{"name": "task", "ok": True, "detail": "mock"}],
        },
    )
    result = admission.preflight(spec)
    assert result["ready"]
    assert result["resources_scope"] == "main_container"
    assert not result["aggregate_limits_enforced"]


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
    assert cli.main([command, "--run-dir", str(destination), "--runtime", "docker"]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["ready"] is False
    assert not destination.exists()


def test_workspace_admission_does_not_probe_docker(infrastructure, monkeypatch):
    from tau_skill_evolution.bubblewrap import BubblewrapRunner, RuntimeLock

    spec, state, _ = infrastructure
    state["fault"] = "socket_permission"
    monkeypatch.setattr(RuntimeLock, "from_file", lambda _: object())

    def local_admission(self):
        assert self.runtime == "workspace"
        return {"ready": True, "aggregate_limits_enforced": False}

    monkeypatch.setattr(BubblewrapRunner, "preflight", local_admission)
    result = admission.preflight(spec, runtime="workspace")
    assert result["ready"]
    assert state["requests"] == []
    assert result["requested_runtime"] == "workspace"
    assert result["resources_scope"] == "local_process"
    assert not result["aggregate_limits_enforced"]
    assert not result["formal_matrix_result"]


def test_workspace_failure_has_no_docker_fallback(infrastructure, monkeypatch):
    from tau_skill_evolution.bubblewrap import BubblewrapRunner, RuntimeLock

    spec, state, _ = infrastructure
    monkeypatch.setattr(RuntimeLock, "from_file", lambda _: object())
    monkeypatch.setattr(BubblewrapRunner, "preflight", lambda _: {"ready": False})
    result = admission.preflight(spec, runtime="workspace")
    assert not result["ready"]
    assert state["requests"] == []
    assert any(item["name"] == "workspace_runtime" and not item["ok"] for item in result["checks"])


@pytest.fixture
def codex_plan_infrastructure(infrastructure, monkeypatch):
    from tau_skill_evolution import codex_runtime, skillsbench

    spec, state, _ = infrastructure
    provider = {
        "transport": "codex-plan",
        "model": "gpt-6.1-sol",
        "binary": "/pinned/codex",
        "version": "0.160.1",
        "binary_sha256": "a" * 64,
    }
    spec.values["provider"] = provider
    monkeypatch.setattr(ExperimentSpec, "experiment", property(lambda self: "skillsbench"))
    monkeypatch.setattr(ExperimentSpec, "provider_settings", property(lambda self: provider))

    def identity(settings):
        assert settings == provider
        return {
            "binary": provider["binary"],
            "codex_version": provider["version"],
            "binary_sha256": provider["binary_sha256"],
        }

    original_run = admission.subprocess.run

    def process(command, **kwargs):
        if command == [provider["binary"], "login", "status"]:
            state["login_checked"] = True
            logged_in = state["fault"] != "codex_login"
            return subprocess.CompletedProcess(
                command,
                0 if logged_in else 1,
                "",
                "Logged in using ChatGPT" if logged_in else "private login error",
            )
        return original_run(command, **kwargs)

    monkeypatch.setattr(codex_runtime, "codex_identity", identity)
    monkeypatch.setattr(admission.subprocess, "run", process)
    monkeypatch.setattr(
        skillsbench,
        "skillsbench_preflight",
        lambda *args, **kwargs: {
            "checks": [{"name": "task_environment", "ok": True, "detail": "offline fixture"}]
        },
    )

    def unexpected_credentials(*args):
        raise AssertionError("Codex subscription admission must not inspect Bedrock credentials")

    monkeypatch.setattr(admission, "describe_credential", unexpected_credentials)
    monkeypatch.setattr(admission, "bearer_token_source", unexpected_credentials)
    return spec, state, provider


def test_codex_plan_admission_uses_pinned_binary_and_local_login(codex_plan_infrastructure):
    spec, state, provider = codex_plan_infrastructure
    result = admission.preflight(spec)
    checks = {item["name"]: item for item in result["checks"]}
    assert result["ready"] and result["environment_ready"]
    assert result["model_access_ready"] is None
    assert result["s0_http_post_count"] == "NOT_OBSERVABLE"
    assert state["login_checked"]
    assert checks["codex_cli"]["detail"]["binary"] == provider["binary"]
    assert "codex_catalog" not in checks and "bedrock_model" not in checks


def test_codex_plan_login_failure_does_not_mislabel_task_environment(codex_plan_infrastructure):
    spec, state, _ = codex_plan_infrastructure
    state["fault"] = "codex_login"
    result = admission.preflight(spec)
    assert not result["ready"] and result["environment_ready"]
    check = next(item for item in result["checks"] if item["name"] == "codex_login")
    assert not check["ok"] and "private login error" not in check["detail"]


@pytest.mark.parametrize("failure", [None, "model", "authentication", "rpc"])
def test_codex_plan_metadata_is_no_inference_sanitized_and_closed(
    codex_plan_infrastructure, monkeypatch, failure
):
    from tau_skill_evolution import codex_plan

    spec, _, provider = codex_plan_infrastructure
    calls = []

    class Client:
        def __init__(self, **kwargs):
            calls.append(("init", kwargs))
            assert kwargs["model"] == provider["model"]
            assert kwargs["binary"] == provider["binary"]
            assert kwargs["role"] == "preflight" and kwargs["timeout_seconds"] == 30

        def metadata(self):
            calls.append(("metadata", None))
            if failure == "rpc":
                raise RuntimeError("codex_plan_rpc_error")
            return {
                "models": ["another-model"] if failure == "model" else [provider["model"]],
                "authentication": "apiKey" if failure == "authentication" else "chatgpt",
                "used_percent": 37,
                "email": "never-export@example.invalid",
                "credential": "never-export",
            }

        def close(self):
            calls.append(("close", None))

    monkeypatch.setattr(codex_plan, "CodexPlanClient", Client)
    result = admission.preflight(spec, authenticate=True)
    assert [name for name, _ in calls] == ["init", "metadata", "close"]
    assert result["model_access_ready"] == (failure is None)
    assert result["environment_ready"]
    assert "never-export" not in json.dumps(result)
    if failure is None:
        check = next(item for item in result["checks"] if item["name"] == "codex_catalog")
        assert check["detail"] == {
            "model": provider["model"],
            "authentication": "chatgpt",
            "used_percent": 37,
            "generation_requested": False,
            "s0_http_post_count": "NOT_OBSERVABLE",
        }
    elif failure == "model":
        assert "does not expose the configured model gpt-6.1-sol" in json.dumps(result)
