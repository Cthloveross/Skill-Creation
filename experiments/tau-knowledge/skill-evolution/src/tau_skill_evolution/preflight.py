"""Admission probes; unavailable isolation never permits host execution."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlsplit

from .constants import SUPPORTED_MODELS, UPSTREAM_ROOT, WORKER_PYTHON_VERSION
from .credentials import bearer_token_source, describe_credential
from .data import verify_tracked_snapshot
from .model import GenerationConfig, bedrock_messages_endpoint, bedrock_responses_endpoint
from .spec import ExperimentSpec


def bedrock_authentication(spec: ExperimentSpec) -> dict[str, Any]:
    provider = spec.provider_settings
    model = spec.values["provider"]["model"]
    token = bearer_token_source(provider["api_key_env"])()
    if not token:
        raise ValueError("Bedrock credential is missing")
    # Both inference transports use the same catalog, outside their API prefix.
    route = (
        bedrock_messages_endpoint
        if provider["transport"] == "bedrock-messages"
        else bedrock_responses_endpoint
    )
    endpoint = urlsplit(route(provider["api_base"]))
    host = f"https://{endpoint.netloc}"
    request = urllib.request.Request(
        host + "/v1/models", headers={"Authorization": "Bearer " + token}
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            value = json.load(response)
            status = response.status
    except urllib.error.HTTPError as exc:
        raise ValueError(f"Bedrock catalog returned HTTP {exc.code}") from None
    if not any(item.get("id") == model for item in value.get("data", [])):
        raise ValueError(f"Bedrock catalog does not expose the configured model {model}")
    return {"status": status, "model": model, "generation_requested": False}


def codex_plan_authentication(spec: ExperimentSpec) -> dict[str, Any]:
    """Read public app-server metadata without inference or exporting account identity."""
    from .codex_plan import CodexPlanClient

    provider = spec.provider_settings
    with tempfile.TemporaryDirectory(prefix="skillsbench-codex-admission-") as directory:
        client = CodexPlanClient(
            model=provider["model"],
            role="preflight",
            journal_dir=directory,
            binary=provider["binary"],
            timeout_seconds=30,
        )
        try:
            metadata = client.metadata()
        finally:
            client.close()
    if metadata.get("authentication") != "chatgpt":
        raise ValueError("Codex must be logged in using ChatGPT for subscription inference")
    if provider["model"] not in metadata.get("models", []):
        raise ValueError(f"Codex catalog does not expose the configured model {provider['model']}")
    return {
        "model": provider["model"],
        "authentication": "chatgpt",
        "used_percent": metadata.get("used_percent"),
        "generation_requested": False,
        "s0_http_post_count": "NOT_OBSERVABLE",
    }


def preflight(
    spec: ExperimentSpec,
    *,
    demo: bool = False,
    authenticate: bool = False,
    task_ids: tuple[str, ...] | None = None,
    runtime: str | None = None,
) -> dict[str, Any]:
    runtime = runtime or ("bubblewrap-demo" if demo else "docker")
    if runtime not in {"docker", "workspace", "bubblewrap-demo"}:
        raise ValueError("unsupported runtime")
    if demo != (runtime == "bubblewrap-demo"):
        raise ValueError("demo and runtime differ")
    checks: list[dict[str, Any]] = []

    def check(name: str, callback: Any) -> None:
        try:
            detail = callback()
            checks.append({"name": name, "ok": True, "detail": detail})
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
            checks.append({"name": name, "ok": False, "detail": str(exc)})

    def interpreter() -> str:
        python = spec.upstream / ".venv" / "bin" / "python"
        output = subprocess.check_output(
            [
                str(python),
                "-c",
                "import sys,json;print(json.dumps([list(sys.version_info[:3]),sys.prefix]))",
            ],
            text=True,
            timeout=20,
        )
        version, prefix = json.loads(output)
        pinned = ".".join(str(part) for part in WORKER_PYTHON_VERSION)
        if tuple(version) != WORKER_PYTHON_VERSION or str(spec.upstream / ".venv") != prefix:
            raise ValueError(f"official worker interpreter is not the pinned Python {pinned}")
        return str(python)

    def upstream() -> dict[str, Any]:
        if spec.upstream != UPSTREAM_ROOT.resolve():
            raise ValueError("configured upstream is outside the preserved pinned checkout")
        return verify_tracked_snapshot(config_root=spec.root / "configs")

    def bedrock_model() -> str:
        provider = spec.values["provider"]
        try:
            GenerationConfig(model=provider["model"], transport=provider["transport"])
        except ValueError as exc:
            raise ValueError(
                "unsupported_model: this experiment uses supported Bedrock Mantle models "
                + " / ".join(SUPPORTED_MODELS)
            ) from exc
        return provider["model"]

    def bedrock_region() -> str:
        return spec.provider_settings["api_base"]

    def credential() -> str:
        return describe_credential(spec.values["provider"]["api_key_env"])

    def codex_installation() -> dict[str, Any]:
        from .codex_runtime import codex_identity

        if spec.experiment != "skillsbench":
            raise ValueError("Codex subscription transport is only supported by SkillsBench")
        provider = spec.provider_settings
        identity = codex_identity(provider)
        return {key: identity[key] for key in ("binary", "codex_version", "binary_sha256")}

    def codex_login() -> str:
        result = subprocess.run(
            [spec.provider_settings["binary"], "login", "status"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode or "Logged in using ChatGPT" not in result.stdout + result.stderr:
            raise ValueError("Codex is not logged in using ChatGPT")
        return "Logged in using ChatGPT"

    def docker_cli() -> str:
        command = shutil.which("docker")
        if command is None:
            raise ValueError("Docker CLI is missing")
        return command

    def docker_info() -> str:
        result = subprocess.run(
            ["docker", "info", "--format", "{{.ServerVersion}}"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if result.returncode:
            raise ValueError(f"Docker daemon/socket inaccessible: {result.stderr.strip()}")
        return result.stdout.strip()

    def dependency_lock() -> str:
        from .container import ImageLock

        lock = ImageLock.from_file(spec.root / "runtime" / "image-lock.json")
        lock.validate_dependencies()
        return lock.dependency_hash

    def image() -> str:
        from .container import ContainerUnavailable, ImageLock

        lock = ImageLock.from_file(spec.root / "runtime" / "image-lock.json")
        try:
            reference = lock.reference
        except ContainerUnavailable as exc:
            if str(exc) == "image_digest_not_prepared":
                raise ValueError(
                    "runtime_unprepared: no real image digest has been recorded"
                ) from exc
            raise
        result = subprocess.run(
            ["docker", "image", "inspect", reference],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if result.returncode:
            raise ValueError(f"locked Docker image missing: {result.stderr.strip()}")
        metadata = json.loads(result.stdout)
        if (
            not isinstance(metadata, list)
            or len(metadata) != 1
            or not isinstance(metadata[0], dict)
        ):
            raise ValueError("locked Docker image inspection is malformed")
        observed = metadata[0]
        matches = (
            observed.get("Id") == lock.digest
            if lock.digest_kind == "image_id"
            else isinstance(observed.get("RepoDigests"), list)
            and reference in observed["RepoDigests"]
        )
        if not matches:
            raise ValueError("Docker image digest mismatch")
        return reference

    def embedding() -> str:
        settings = spec.values["embedding"]
        url = settings["endpoint"].rstrip("/") + "/models"
        with urllib.request.urlopen(url, timeout=10) as response:
            models = json.load(response)
        if settings["model"] not in [model["id"] for model in models["data"]]:
            raise ValueError("embedding service exposes the wrong model")
        return settings["endpoint"]

    def container_dependencies() -> str:
        from .container import DockerRunner, ImageLock

        needed = {"docker_cli", "docker_daemon", "dependency_lock", "docker_image"}
        if any(not item["ok"] for item in checks if item["name"] in needed):
            raise ValueError(
                "container dependencies not checked: runtime prerequisites unavailable"
            )
        result = DockerRunner(
            ImageLock.from_file(spec.root / "runtime" / "image-lock.json")
        ).preflight()
        if not result.get("ready") or not result.get("dependencies"):
            raise ValueError(
                "container readiness/Python/dependencies do not match the runtime lock"
            )
        return "Python 3.11 and fixed dependencies verified in the locked container"

    def local_runtime() -> dict[str, Any]:
        from .bubblewrap import BubblewrapRunner, RuntimeLock

        result = BubblewrapRunner(
            RuntimeLock.from_file(spec.root / "runtime" / "bubblewrap-lock.json"),
            runtime=runtime,
        ).preflight()
        if not result.get("ready"):
            raise ValueError(f"Local workspace runtime is unavailable: {result}")
        return result

    if spec.experiment == "tau":
        check("pinned_upstream", upstream)
        check("official_python", interpreter)
    codex_plan = spec.values["provider"]["transport"] == "codex-plan"
    if codex_plan:
        check("codex_cli", codex_installation)
        check("codex_login", codex_login)
        if authenticate:
            check("codex_catalog", lambda: codex_plan_authentication(spec))
    else:
        check("bedrock_model", bedrock_model)
        check("bedrock_region", bedrock_region)
        check("credential", credential)
        if authenticate:
            check("bedrock_authentication", lambda: bedrock_authentication(spec))
    if spec.experiment == "skillsbench":
        from .skillsbench import skillsbench_preflight

        if runtime == "docker":
            check("docker_cli", docker_cli)
            check("docker_daemon", docker_info)
        result = skillsbench_preflight(spec, demo=demo, task_ids=task_ids, runtime=runtime)
        checks.extend(result["checks"])
    else:
        if runtime != "docker":
            check("bubblewrap_demo" if demo else "workspace_runtime", local_runtime)
        else:
            check("dependency_lock", dependency_lock)
            check("docker_cli", docker_cli)
            check("docker_daemon", docker_info)
            check("docker_image", image)
            check("container_dependencies", container_dependencies)
    check("embedding_service", embedding)
    ready = all(item["ok"] for item in checks)
    result = {
        "namespace": spec.namespace,
        "experiment": spec.experiment,
        "ready": ready,
        "requested_runtime": "bubblewrap_demo" if demo else runtime,
        "formal_matrix_result": ready and runtime == "docker",
        "aggregate_limits_enforced": ready and runtime == "docker" and spec.experiment == "tau",
        "resources_scope": (
            "local_process"
            if runtime != "docker"
            else "bank_script_process_tree"
            if spec.experiment == "tau"
            else "main_container"
        ),
        "checks": checks,
    }
    if codex_plan:
        model_checks = {"codex_cli", "codex_login", "codex_catalog"}
        result.update(
            environment_ready=all(
                item["ok"] for item in checks if item["name"] not in model_checks
            ),
            model_access_ready=(
                all(item["ok"] for item in checks if item["name"] in model_checks)
                if authenticate
                else None
            ),
            s0_http_post_count="NOT_OBSERVABLE",
        )
    return result
