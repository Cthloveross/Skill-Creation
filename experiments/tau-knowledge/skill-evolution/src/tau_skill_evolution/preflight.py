"""Read-only admission checks; unavailable isolation never permits host execution."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from typing import Any

from .constants import UPSTREAM_ROOT
from .data import verify_tracked_snapshot
from .spec import BEDROCK_MODEL, ExperimentSpec


def bedrock_authentication(spec: ExperimentSpec) -> dict[str, Any]:
    provider = spec.provider_settings
    token = os.environ.get(provider["api_key_env"])
    if not token:
        raise ValueError("Bedrock credential is missing")
    # The model catalog uses /v1; GPT inference separately uses /openai/v1/responses.
    host = provider["api_base"].removesuffix("/openai/v1")
    request = urllib.request.Request(
        host + "/v1/models", headers={"Authorization": "Bearer " + token}
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            value = json.load(response)
            status = response.status
    except urllib.error.HTTPError as exc:
        raise ValueError(f"Bedrock catalog returned HTTP {exc.code}") from None
    if not any(item.get("id") == BEDROCK_MODEL for item in value.get("data", [])):
        raise ValueError("Bedrock catalog does not expose the configured GPT-5.5 model")
    return {"status": status, "model": BEDROCK_MODEL, "generation_requested": False}


def preflight(
    spec: ExperimentSpec,
    *,
    demo: bool = False,
    authenticate: bool = False,
    task_ids: tuple[str, ...] | None = None,
) -> dict[str, Any]:
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
        if version != [3, 12, 14] or str(spec.upstream / ".venv") != prefix:
            raise ValueError("official worker interpreter is not the pinned Python 3.12.14")
        return str(python)

    def upstream() -> dict[str, Any]:
        if spec.upstream != UPSTREAM_ROOT.resolve():
            raise ValueError("configured upstream is outside the preserved pinned checkout")
        return verify_tracked_snapshot(config_root=spec.root / "configs")

    def bedrock_model() -> str:
        provider = spec.values["provider"]
        if provider["model"] != BEDROCK_MODEL or provider["transport"] != "bedrock-responses":
            raise ValueError(
                "unsupported_model: this experiment uses GPT-5.5 Bedrock Mantle Responses"
            )
        return BEDROCK_MODEL

    def bedrock_region() -> str:
        return spec.provider_settings["api_base"]

    def credential() -> str:
        variable = spec.values["provider"]["api_key_env"]
        if not os.environ.get(variable):
            raise ValueError(f"required environment variable is missing: {variable}")
        return f"{variable} is present (value not recorded)"

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

    def bubblewrap_demo() -> dict[str, Any]:
        from .bubblewrap import BubblewrapRunner, RuntimeLock

        result = BubblewrapRunner(
            RuntimeLock.from_file(spec.root / "runtime" / "bubblewrap-lock.json")
        ).preflight()
        if not result.get("ready"):
            raise ValueError(f"Bubblewrap demo runtime is unavailable: {result}")
        return result

    if spec.experiment == "tau":
        check("pinned_upstream", upstream)
        check("official_python", interpreter)
    check("bedrock_model", bedrock_model)
    check("bedrock_region", bedrock_region)
    check("credential", credential)
    if authenticate:
        check("bedrock_authentication", lambda: bedrock_authentication(spec))
    if spec.experiment == "skillsbench":
        from .skillsbench import skillsbench_preflight

        if not demo:
            check("docker_cli", docker_cli)
            check("docker_daemon", docker_info)
        result = skillsbench_preflight(spec, demo=demo, task_ids=task_ids)
        checks.extend(result["checks"])
    else:
        check("dependency_lock", dependency_lock)
        if demo:
            check("bubblewrap_demo", bubblewrap_demo)
        else:
            check("docker_cli", docker_cli)
            check("docker_daemon", docker_info)
            check("docker_image", image)
            check("container_dependencies", container_dependencies)
    check("embedding_service", embedding)
    ready = all(item["ok"] for item in checks)
    return {
        "namespace": spec.namespace,
        "experiment": spec.experiment,
        "ready": ready,
        "requested_runtime": "bubblewrap_demo" if demo else "docker",
        "formal_matrix_result": ready and not demo,
        "aggregate_limits_enforced": ready and not demo,
        "checks": checks,
    }
