"""Fresh SkillsBench terminal and grader sandboxes; no host execution fallback."""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import math
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import uuid
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .artifacts import atomic_json
from .container import (
    BoundedProcessTransport,
    ContainerUnavailable,
    ProcessResult,
    ProgramResult,
    SkillEpisode,
    _episode,
    _program_result,
    _public_workspace,
    _run_verifier,
    _safe_path,
    _workspace_writable_roots,
)
from .skillsbench import (
    COMMIT,
    SkillsBenchSource,
    _hash,
    _json_hash,
    _private_path,
    _public_link_target,
    task_config,
)

_GRADER_PREFIX = "/opt/tau-grader"
_VERIFIER_PREFIX = "/.tau-verifier"
# Official graders print verbose pytest output that is never shown to a model; it is
# only scanned by _validate_grader_warmup, so it may be far larger than tool output.
_GRADER_OUTPUT_LIMIT = 16 * 1024 * 1024
_GRADER_DIAGNOSTICS_LIMIT = 1024 * 1024
# The verifier lock is resolved for CPython 3.11; images lacking exactly that (or pip)
# receive a hash-verified python-build-standalone interpreter outside the task PATH.
_UV_IMAGE = "ghcr.io/astral-sh/uv:0.9.26"
_STANDALONE_PYTHON_DIR = "/.tau-python"
_STANDALONE_PYTHON = _STANDALONE_PYTHON_DIR + "/python3"
_NATIVE_PYTHON = "python3"
_EPISODE_SCHEMA = "skillsbench.episode.v2"
_WORKSPACE_SCHEMA = "skillsbench.workspace.v1"
_WORKSPACE_DIRECTORIES = {
    "3d-scan-calc": "/root",
    "enterprise-information-search": "/root",
    "lab-unit-harmonization": "/root",
    "manufacturing-codebook-normalization": "/app",
    "dialogue-parser": "/app",
}
_WORKSPACE_TASKS = set(_WORKSPACE_DIRECTORIES)
_ENTERPRISE_TEST_SCRIPT_SHA256 = "e26daee2de02446ae541140c19d4616cc85818bb3291713657e2bd360db6248a"
_WORKSPACE_TEST_SCRIPT_SHA256 = {
    "enterprise-information-search": _ENTERPRISE_TEST_SCRIPT_SHA256,
    "lab-unit-harmonization": "216867e838a0b5925d8f347803ebbbef253f97bb56ad7aa57a62c10dd12fa70e",
    "manufacturing-codebook-normalization": (
        "8123b529f99e5860d52feb7605dae90aef0409af26af8e34d6021d6d23b45fda"
    ),
    "dialogue-parser": "d422a9278f3ecf4fd3712671ca92e1145dd66ec7920612bbdfb799ed7d5526dc",
}
_VERIFIER_PYTHON_PROBE = 'python3 -c "import sys, pip; assert sys.version_info[:2] == (3, 11)"'
_RESERVED_PROVIDER_CREDENTIALS = {
    "OPENAI_API_KEY",
    "OPENAI_API_KEY_FILE",
    "CODEX_API_KEY",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "AZURE_OPENAI_API_KEY",
    "GEMINI_API_KEY",
    "ELEVENLABS_API_KEY",
    "GOOGLE_API_KEY",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "AWS_BEARER_TOKEN_BEDROCK",
    "AWS_BEARER_TOKEN_BEDROCK_FILE",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "AWS_SECURITY_TOKEN",
    "AWS_SHARED_CREDENTIALS_FILE",
    "AWS_CONFIG_FILE",
}
_TASK_API_KEYS = {"OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "ELEVENLABS_API_KEY"}


def _check_task_environment(settings: Mapping[str, str]) -> None:
    names = set(settings)
    for value in settings.values():
        names.update(re.findall(r"\$(?:\{)?([A-Za-z_]\w*)", str(value)))
    if reserved := sorted(names & _RESERVED_PROVIDER_CREDENTIALS):
        raise ContainerUnavailable(f"skillsbench_reserved_provider_credential:{reserved[0]}")


def _task_environment(settings: Mapping[str, str], task_id: str | None) -> dict[str, str]:
    """Map declared task API keys to separate, task-scoped host credentials."""
    mapped = {}
    for name, value in settings.items():
        if task_id is not None and name in _TASK_API_KEYS:
            if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", task_id) or value not in (
                "${" + name + "}",
                "${" + name + ":-}",
                "$" + name,
            ):
                raise ContainerUnavailable(f"skillsbench_reserved_provider_credential:{name}")
            scoped = "SKILLSBENCH_TASK_" + task_id.upper().replace("-", "_") + "_" + name
            mapped[name] = "${" + scoped + "}"
        else:
            _check_task_environment({name: value})
            mapped[name] = value
    return mapped


def _resolve_environment(
    settings: Mapping[str, str], *, required: bool = True, task_id: str | None = None
) -> dict[str, str]:
    """Resolve only declared task variables; never copy the host's credential environment."""
    settings = _task_environment(settings, task_id)

    def replace(match: re.Match[str]) -> str:
        name, fallback = match.groups()
        value = os.environ.get(name) or fallback
        if not value and required:
            raise ContainerUnavailable(f"skillsbench_required_environment_missing:{name}")
        return value or ""

    return {
        str(name): re.sub(r"\$\{([A-Za-z_]\w*)(?::-([^}]*))?\}", replace, str(value))
        for name, value in settings.items()
    }


def _missing_environment(settings: Mapping[str, str], *, task_id: str | None = None) -> list[str]:
    settings = _task_environment(settings, task_id)
    return sorted(
        {
            name
            for value in settings.values()
            for name, fallback in re.findall(r"\$\{([A-Za-z_]\w*)(?::-([^}]*))?\}", str(value))
            if not (os.environ.get(name) or fallback)
        }
    )


def _host_environment(extra: Mapping[str, str] | None = None) -> dict[str, str]:
    names = ("PATH", "HOME", "DOCKER_HOST", "DOCKER_CONTEXT", "XDG_RUNTIME_DIR")
    return {**{k: os.environ[k] for k in names if k in os.environ}, **(extra or {})}


def _compose_definition(directory: Path) -> dict[str, Any]:
    """Follow pinned Harbor's .yaml-only convention and discard host agent bindings."""
    path = directory / "environment/docker-compose.yaml"
    value = (
        yaml.safe_load(path.read_text())
        if path.exists()
        else {
            "services": {
                "main": {"build": {"context": "."}, "command": ["sh", "-c", "sleep infinity"]}
            }
        }
    )
    if not isinstance(value, dict) or "main" not in value.get("services", {}):
        raise ContainerUnavailable("skillsbench_compose_requires_main")
    ignored = {
        "GOOGLE_APPLICATION_CREDENTIALS",
        "CLAUDE_CODE_USE_VERTEX",
        "CLOUD_ML_REGION",
        "ANTHROPIC_VERTEX_PROJECT_ID",
        "TEST_DIR",
    }
    services = {}
    allowed = {
        "command",
        "entrypoint",
        "depends_on",
        "healthcheck",
        "expose",
        "networks",
        "read_only",
        "tmpfs",
        "cap_drop",
        "security_opt",
        "user",
        "working_dir",
    }
    for name, original in value["services"].items():
        if not re.fullmatch(r"[A-Za-z0-9_-]+", name) or not isinstance(original, dict):
            raise ContainerUnavailable("skillsbench_compose_service_invalid")
        if original.get("ports") or original.get("privileged") or original.get("devices"):
            raise ContainerUnavailable("skillsbench_compose_host_access_unsupported")
        build = original.get("build", {"context": "."})
        if isinstance(build, str):
            build = {"context": build}
        context = build.get("context", ".")
        if context == "${CONTEXT_DIR}":
            context = "."
        if context != ".":
            _safe_path(context.removeprefix("./"))
        recipe = build.get("dockerfile", "Dockerfile")
        _safe_path(recipe)
        environment = original.get("environment", {})
        if isinstance(environment, list):
            environment = dict(
                item.split("=", 1) if "=" in item else (item, "${" + item + "}")
                for item in environment
            )
        services[name] = {
            **{k: v for k, v in original.items() if k in allowed},
            "build": {"context": context, "dockerfile": recipe},
            "environment": {k: str(v) for k, v in environment.items() if k not in ignored},
        }
    return {"services": services, "networks": value.get("networks", {})}


@dataclass(frozen=True)
class SkillsBenchRuntimeLock:
    path: Path
    value: Mapping[str, Any]

    @classmethod
    def from_file(cls, path: Path) -> SkillsBenchRuntimeLock:
        path = Path(path).resolve()
        value = json.loads(path.read_text())
        if value.get("runtime_schema") == _WORKSPACE_SCHEMA:
            base_name = _safe_path(value["base_runtime_lock"]).as_posix()
            if (
                set(value)
                != {
                    "runtime_schema",
                    "base_runtime_lock",
                    "base_runtime_lock_sha256",
                    "task_ids",
                    "public_task_binding",
                    "grader_bootstrap",
                    "author_environment_equivalent",
                    "method_adaptation",
                }
                or base_name != "skillsbench-bubblewrap-lock.json"
                or not isinstance(value.get("task_ids"), list)
                or len(value["task_ids"]) != 1
                or value["task_ids"][0] not in _WORKSPACE_TEST_SCRIPT_SHA256
                or value.get("author_environment_equivalent") is not False
            ):
                raise ContainerUnavailable("skillsbench_workspace_descriptor_invalid")
            base = path.parent / base_name
            if base.is_symlink() or _hash(base) != value["base_runtime_lock_sha256"]:
                raise ContainerUnavailable("skillsbench_workspace_base_lock_mismatch")
            original = json.loads(base.read_text())
            value = {**original, **value}
        return cls(path, value)

    @property
    def rootfs(self) -> Path:
        return (self.path.parent / self.value["rootfs"]).resolve()

    def validate(self, task_id: str) -> None:
        value = self.value
        if (
            value.get("aggregate_limits_enforced") is not False
            or value.get("demo_only") is not True
            or task_id not in value.get("task_ids", [])
            or value.get("python_version") != [3, 11, 14]
        ):
            raise ContainerUnavailable("skillsbench_demo_runtime_invalid")
        if value.get("runtime_schema") == _WORKSPACE_SCHEMA and value.get(
            "public_task_binding"
        ) != _workspace_task_binding(self.path.parent.parent, task_id):
            raise ContainerUnavailable("skillsbench_workspace_task_binding_mismatch")
        if value.get("runtime_schema") == _WORKSPACE_SCHEMA:
            original, adapted = _workspace_grader_script(self.path.parent.parent, task_id)
            if value.get("grader_bootstrap") != {
                "mode": "offline_pinned_pytest",
                "original_script_sha256": hashlib.sha256(original.encode()).hexdigest(),
                "executed_script_sha256": hashlib.sha256(adapted.encode()).hexdigest(),
            }:
                raise ContainerUnavailable("skillsbench_workspace_grader_bootstrap_mismatch")
        dependency = self.path.with_name("skillsbench-requirements.lock")
        if _hash(dependency) != value["dependency_hash"]:
            raise ContainerUnavailable("skillsbench_dependency_hash_mismatch")
        for requirement in re.split(r"\n(?=[A-Za-z0-9])", dependency.read_text()):
            if "==" in requirement and not re.search(r"--hash=sha256:[0-9a-f]{64}", requirement):
                raise ContainerUnavailable("skillsbench_dependency_unhashed")
        root = self.rootfs
        if not root.is_dir() or root.is_symlink():
            raise ContainerUnavailable("skillsbench_rootfs_missing")
        files, links = {}, {}
        for directory, directories, names in os.walk(root, followlinks=False):
            for name in [*directories, *names]:
                path = Path(directory) / name
                relative = path.relative_to(root).as_posix()
                _safe_path(relative)
                mode = path.lstat().st_mode
                if stat.S_ISLNK(mode):
                    target = os.readlink(path)
                    if Path(target).is_absolute() or not path.resolve(strict=True).is_relative_to(
                        root
                    ):
                        raise ContainerUnavailable("skillsbench_rootfs_unsafe_symlink")
                    links[relative] = target
                elif stat.S_ISREG(mode):
                    files[relative] = _hash(path)
                elif not stat.S_ISDIR(mode):
                    raise ContainerUnavailable("skillsbench_rootfs_special_file")
        if files != value["files"] or links != value.get("symlinks", {}):
            raise ContainerUnavailable("skillsbench_rootfs_manifest_mismatch")


def prepare_demo_runtime(root: Path, task_id: str) -> dict[str, Any]:
    """Build a separate Python/bash rootfs with the exact official 3d grader pins."""
    root = Path(root).resolve()
    if task_id != "3d-scan-calc":
        raise ContainerUnavailable("skillsbench_demo_task_not_prepared")
    lock_path = root / "runtime/skillsbench-bubblewrap-lock.json"
    if lock_path.exists():
        SkillsBenchRuntimeLock.from_file(lock_path).validate(task_id)
        return {"ready": True, "reused": True, "lock_hash": _hash(lock_path)}
    source = root / "data/bubblewrap/rootfs"
    destination = root / "data/skillsbench/rootfs"
    staging = destination.with_name(".rootfs-preparing")
    if destination.exists() or staging.exists():
        raise ValueError("unsealed_skillsbench_rootfs_exists")
    shutil.copytree(source, staging, symlinks=True)
    site = staging / "usr/local/lib/python3.11/site-packages"
    shutil.rmtree(site)
    site.mkdir()
    requirements = lock_path.with_name("skillsbench-requirements.lock")
    requirements_input = requirements.with_suffix(".in")
    requirements_input.write_text(
        "numpy==2.2.6\npandas==2.2.3\npytest==8.4.1\npytest-json-ctrf==0.3.5\npip==25.2\n"
    )
    clean_env = {"PATH": os.environ["PATH"], "HOME": str(Path.home())}
    subprocess.run(
        [
            "uv",
            "pip",
            "compile",
            "--python-version",
            "3.11",
            "--generate-hashes",
            "--no-progress",
            str(requirements_input),
            "-o",
            str(requirements),
        ],
        check=True,
        env=clean_env,
    )
    subprocess.run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            str(staging / "usr/local/bin/python"),
            "--target",
            str(site),
            "--require-hashes",
            "--only-binary",
            ":all:",
            "--link-mode",
            "copy",
            "--no-progress",
            "-r",
            str(requirements),
        ],
        check=True,
        env=clean_env,
    )
    for name in ("root", "inputs", "bundle", "work", "tests", "logs/verifier", "bin", "usr/bin"):
        (staging / name).mkdir(parents=True, exist_ok=True)
    for name in (
        "bash",
        "env",
        "mkdir",
        "cat",
        "ls",
        "head",
        "tail",
        "wc",
        "sed",
        "grep",
        "sort",
        "cut",
        "tr",
        "cp",
        "mv",
        "rm",
        "touch",
        "chmod",
        "pwd",
        "date",
        "find",
        "xargs",
        "timeout",
        "true",
        "false",
    ):
        source_binary = shutil.which(name)
        if source_binary:
            shutil.copy2(Path(source_binary).resolve(), staging / "usr/bin" / name)
    for name, target in {"bash": "../usr/bin/bash", "sh": "../usr/bin/bash"}.items():
        (staging / "bin" / name).symlink_to(target)
    for name, module in {"pip": "pip", "pip3": "pip", "pytest": "pytest"}.items():
        script = staging / "usr/local/bin" / name
        script.write_text(f'#!/bin/bash\nexec /usr/local/bin/python -I -m {module} "$@"\n')
        script.chmod(0o755)
    for path in sorted(staging.rglob("__pycache__"), reverse=True):
        shutil.rmtree(path)
    spec = importlib.util.spec_from_file_location(
        "prepare_bwrap", root / "scripts/prepare_bubblewrap.py"
    )
    assert spec and spec.loader
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    helper.copy_libraries(staging)
    files, links = helper.manifest(staging)
    staging.rename(destination)
    dependencies = {
        "numpy": "2.2.6",
        "pandas": "2.2.3",
        "pytest": "8.4.1",
        "pytest-json-ctrf": "0.3.5",
        "pip": "25.2",
    }
    atomic_json(
        lock_path,
        {
            "rootfs": "../data/skillsbench/rootfs",
            "files": files,
            "symlinks": links,
            "python_version": [3, 11, 14],
            "dependency_hash": _hash(requirements),
            "dependencies": dependencies,
            "task_ids": [task_id],
            "demo_only": True,
            "aggregate_limits_enforced": False,
        },
    )
    return {"ready": True, "lock_hash": _hash(lock_path), "dependencies": dependencies}


def _workspace_lock_path(root: Path, task_id: str, selected: Path | None = None) -> Path:
    if selected is not None:
        return Path(selected) if Path(selected).is_absolute() else Path(root) / selected
    name = (
        f"skillsbench-workspace-{task_id}-lock.json"
        if task_id in _WORKSPACE_TEST_SCRIPT_SHA256
        else "skillsbench-bubblewrap-lock.json"
    )
    return Path(root) / "runtime" / name


def _docker_lock_path(root: Path, task_id: str, selected: Path | None = None) -> Path:
    # Existing shared configurations select a workspace lock. Keep that default
    # compatible while allowing a Docker configuration to bind a separate lock.
    if (
        selected is None
        or Path(selected).name == "skillsbench-bubblewrap-lock.json"
        or (Path(selected).name.startswith("skillsbench-workspace-"))
    ):
        return Path(root) / f"runtime/skillsbench-docker-{task_id}-lock.json"
    path = Path(selected)
    if "{" in str(path) or "}" in str(path):
        if (
            str(path).count("{task_id}") != 1
            or "{" in str(path).replace("{task_id}", "")
            or "}" in str(path).replace("{task_id}", "")
            or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", task_id)
        ):
            raise ValueError("skillsbench_docker_lock_path_invalid")
        path = Path(str(path).replace("{task_id}", task_id))
    if not path.name.startswith("skillsbench-docker-"):
        raise ValueError("skillsbench_docker_lock_path_invalid")
    return path if path.is_absolute() else Path(root) / path


def _workspace_task_binding(root: Path, task_id: str) -> dict[str, Any]:
    source = SkillsBenchSource(root)
    task = source.task(task_id)
    directory = source.checkout / "tasks" / task_id
    if (
        task["environment"]["workdir"] != _WORKSPACE_DIRECTORIES.get(task_id)
        or len(_compose_definition(directory)["services"]) != 1
        or not task["public_input_manifest"]
        or any(
            not destination.startswith(_WORKSPACE_DIRECTORIES[task_id] + "/")
            for entry in task["public_input_manifest"]
            for destination in entry["sandbox_paths"]
        )
    ):
        raise ContainerUnavailable("skillsbench_workspace_layout_not_prepared")
    for entry in task["public_input_manifest"]:
        path = directory / _safe_path(entry["relative_path"])
        if path.is_symlink() or _hash(path) != entry["sha256"]:
            raise ContainerUnavailable("skillsbench_workspace_public_input_hash_mismatch")
    return {
        "commit": COMMIT,
        "public_manifest_hash": source.manifest["manifest_hash"],
        "public_task_sha256": _json_hash(task),
        "dockerfile_sha256": _hash(directory / "environment/Dockerfile"),
        "task_config_sha256": _hash(directory / "task.toml"),
    }


def _enterprise_grader_script(root: Path) -> tuple[str, str]:
    """Replace this pinned grader's network bootstrap, retaining its scoring commands."""
    source = SkillsBenchSource(root)
    path = source.checkout / "tasks/enterprise-information-search/tests/test.sh"
    if path.is_symlink() or _hash(path) != _ENTERPRISE_TEST_SCRIPT_SHA256:
        raise ContainerUnavailable("skillsbench_enterprise_grader_recipe_mismatch")
    original = path.read_text()
    setup = (
        "apt-get update\napt-get install -y curl\n\n"
        "curl -LsSf https://astral.sh/uv/0.9.7/install.sh | sh\n\n"
        "source $HOME/.local/bin/env\n"
    )
    launcher = "uvx \\\n  --with pytest==8.4.1 \\\n  --with pytest-json-ctrf==0.3.5 \\\n  pytest "
    if original.count(setup) != 1 or original.count(launcher) != 1:
        raise ContainerUnavailable("skillsbench_enterprise_grader_recipe_mismatch")
    adapted = original.replace(
        setup, "# Dependency installation supplied by the hash-locked offline workspace.\n", 1
    ).replace(launcher, "/usr/local/bin/python -I -m pytest ", 1)
    return original, adapted


def _workspace_grader_script(root: Path, task_id: str) -> tuple[str, str]:
    """Adapt only known installation/launch commands, preserving official scoring."""
    if task_id == "enterprise-information-search":
        return _enterprise_grader_script(root)
    source = SkillsBenchSource(root)
    path = source.checkout / "tasks" / task_id / "tests/test.sh"
    if path.is_symlink() or _hash(path) != _WORKSPACE_TEST_SCRIPT_SHA256.get(task_id):
        raise ContainerUnavailable("skillsbench_workspace_grader_recipe_mismatch")
    original = path.read_text()
    if task_id == "lab-unit-harmonization":
        setup = (
            "pip3 install --break-system-packages pytest pytest-json-ctrf || "
            "pip install pytest pytest-json-ctrf\n"
        )
        launcher = "python3 -m pytest "
    elif task_id == "manufacturing-codebook-normalization":
        setup = (
            "apt-get update\n"
            "apt-get install -y --no-install-recommends curl ca-certificates\n"
            "rm -rf /var/lib/apt/lists/*\n\n"
            "curl -LsSf https://astral.sh/uv/0.9.7/install.sh | sh\n"
            'source "$HOME/.local/bin/env"\n'
        )
        launcher = (
            "uvx \\\n  --with pytest==8.4.1 \\\n  --with pytest-json-ctrf==0.3.5 \\\n  pytest "
        )
    elif task_id == "dialogue-parser":
        setup = "pip3 install --break-system-packages pytest==8.3.4 pytest-json-ctrf==0.3.6\n"
        launcher = "pytest --ctrf "
    else:
        raise ContainerUnavailable("skillsbench_workspace_task_environment_not_prepared")
    if original.count(setup) != 1 or original.count(launcher) != 1:
        raise ContainerUnavailable("skillsbench_workspace_grader_recipe_mismatch")
    replacement = "/usr/local/bin/python -I -m pytest "
    if task_id == "dialogue-parser":
        replacement += "--ctrf "
    adapted = original.replace(
        setup, "# Dependencies supplied by the hash-locked offline workspace.\n", 1
    ).replace(launcher, replacement, 1)
    if task_id == "dialogue-parser":
        capture = (
            "import sys;from pathlib import Path;"
            "data=sys.stdin.buffer.read();Path(sys.argv[1]).write_bytes(data);"
            "sys.stdout.buffer.write(data)"
        )
        adapted = adapted.replace(
            "| tee /logs/verifier/pytest_output.txt",
            "| /usr/local/bin/python -I -c "
            + shlex.quote(capture)
            + " /logs/verifier/pytest_output.txt",
            1,
        )
    # Reward extraction also runs after candidate files exist. Keep imports and
    # startup hooks independent of the task cwd and its writable virtualenv.
    adapted = adapted.replace("python3 -c ", "/usr/local/bin/python -I -c ")
    return original, adapted


def workspace_preparation(
    root: Path, task_id: str, *, runtime_lock_path: Path | None = None
) -> dict[str, Any]:
    """Only declare task environments actually migrated into the isolated workspace."""
    source = SkillsBenchSource(root)
    if task_id not in source.manifest["tasks"]:
        raise ValueError("unknown_skillsbench_task")
    directory = source.checkout / "tasks" / task_id
    reason = None
    if task_id not in _WORKSPACE_TASKS:
        definition = _compose_definition(directory)
        reason = (
            "skillsbench_workspace_sidecars_not_prepared"
            if len(definition["services"]) > 1
            else "skillsbench_workspace_task_environment_not_prepared"
        )
    prepared = False
    lock_path = _workspace_lock_path(root, task_id, runtime_lock_path)
    if reason is None:
        try:
            SkillsBenchRuntimeLock.from_file(lock_path).validate(task_id)
            prepared = True
        except (OSError, ValueError, ContainerUnavailable):
            pass
    return {
        "task_id": task_id,
        "runtime": "workspace",
        "supported": reason is None,
        "prepared": prepared,
        "ready": False,
        "reason": reason,
        "runtime_lock": str(lock_path),
        "requires_fresh_preflight": True,
    }


def prepare_workspace_runtime(root: Path, task_id: str) -> dict[str, Any]:
    status = workspace_preparation(root, task_id)
    if not status["supported"]:
        return status
    if task_id == "3d-scan-calc":
        prepared = prepare_demo_runtime(root, task_id)
    else:
        base = Path(root) / "runtime/skillsbench-bubblewrap-lock.json"
        SkillsBenchRuntimeLock.from_file(base).validate("3d-scan-calc")
        source = SkillsBenchSource(root)
        source.validate()
        original_script, executed_script = _workspace_grader_script(root, task_id)
        descriptor = {
            "runtime_schema": _WORKSPACE_SCHEMA,
            "base_runtime_lock": base.name,
            "base_runtime_lock_sha256": _hash(base),
            "task_ids": [task_id],
            "public_task_binding": _workspace_task_binding(root, task_id),
            "grader_bootstrap": {
                "mode": "offline_pinned_pytest",
                "original_script_sha256": hashlib.sha256(original_script.encode()).hexdigest(),
                "executed_script_sha256": hashlib.sha256(executed_script.encode()).hexdigest(),
            },
            "author_environment_equivalent": False,
            "method_adaptation": (
                "official_ubuntu24_python_replaced_by_pinned_workspace_python311"
                if task_id == "enterprise-information-search"
                else "official_task_environment_replaced_by_pinned_workspace_python311"
            ),
        }
        path = _workspace_lock_path(root, task_id)
        if path.exists():
            if json.loads(path.read_text()) != descriptor:
                raise ContainerUnavailable("skillsbench_workspace_descriptor_mismatch")
        else:
            atomic_json(path, descriptor)
        SkillsBenchRuntimeLock.from_file(path).validate(task_id)
        prepared = {"lock_hash": _hash(path), "runtime_lock": str(path)}
    return {**status, **{k: v for k, v in prepared.items() if k != "ready"}, "prepared": True}


def _prepare_build_context(
    source: SkillsBenchSource,
    task_id: str,
    stage: Path,
    *,
    context: str = ".",
    dockerfile: str = "Dockerfile",
) -> str:
    tree = json.loads((source.root / "data/skillsbench/source-tree.json").read_text())
    if tree.get("sha") != COMMIT:
        raise ContainerUnavailable("skillsbench_source_tree_invalid")
    modes = {e["path"]: e.get("mode") for e in tree["tree"] if e["type"] == "blob"}
    environment = source.checkout / "tasks" / task_id / "environment"
    origin = environment if context == "." else environment / _safe_path(context.removeprefix("./"))
    recipe_path = origin / _safe_path(dockerfile)
    recipe = recipe_path.read_text()
    selected = {recipe_path}
    for raw in re.sub(r"\\\n[ \t]*", " ", recipe).splitlines():
        operation, _, arguments = raw.strip().partition(" ")
        if operation.upper() not in {"COPY", "ADD"}:
            continue
        words = json.loads(arguments) if arguments.startswith("[") else shlex.split(arguments)
        if any(word.startswith("--from=") for word in words):
            continue
        words = [word for word in words if not word.startswith("--")]
        for name in words[:-1]:
            if name.startswith(("http://", "https://")):
                continue
            if "$" in name or ".." in Path(name).parts or Path(name).is_absolute():
                raise ContainerUnavailable("skillsbench_build_source_unresolved")
            for entry in origin.glob(name.rstrip("/")):
                selected.update(entry.rglob("*") if entry.is_dir() else [entry])
    ignored = origin / ".dockerignore"
    if ignored.is_file():
        selected.add(ignored)
    for original in sorted(selected):
        if (
            not original.is_file()
            or original.is_symlink()
            or _private_path(original.relative_to(origin).as_posix())
        ):
            continue
        target = stage / original.relative_to(origin)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, target)
        mode = modes.get(original.relative_to(source.checkout).as_posix())
        if mode not in {"100644", "100755"}:
            raise ContainerUnavailable("skillsbench_source_mode_unsupported")
        target.chmod(0o755 if mode == "100755" else 0o644)
    # Released author Skills stay outside this experiment, including missing COPY skills.
    recipe = (
        "\n".join(
            line for line in recipe.splitlines() if not re.match(r"(?i)^\s*COPY\s+skills/?\s", line)
        )
        + "\n"
    )
    (stage / dockerfile).write_text(recipe)
    return recipe


def _missing_modules(diagnostics: str) -> list[str]:
    """Top-level names whose import failed because the module (or a name in it) is absent."""
    names = re.findall(r"No module named '([A-Za-z_]\w*)", diagnostics)
    names += re.findall(r"cannot import name '\w+' from '([A-Za-z_]\w*)'", diagnostics)
    return sorted(set(names))


def _deliverable_modules(
    diagnostics: str, tests: Path, candidate_modules: Sequence[str] = ()
) -> list[str]:
    """Missing modules that the official tests import from the agent workspace.

    Require a declared public module and an official workspace import. The host's
    Python installation cannot establish what the grader's interpreter provides.
    """
    source = "\n".join(
        path.read_text(encoding="utf-8", errors="replace") for path in sorted(tests.rglob("*.py"))
    )
    if not re.search(r"sys\.path\.(insert|append)\(", source):
        return []
    names = []
    for name in _missing_modules(diagnostics):
        imported = re.search(
            rf"^\s*(?:from\s+{name}(?:\.\w+)*\s+import|import\s+(?:[\w.]+\s*,\s*)*{name}\b)",
            source,
            re.MULTILINE,
        )
        if imported and name in candidate_modules:
            names.append(name)
    return names


def _grader_errors(diagnostics: str) -> list[tuple[str, str | None, str]]:
    """Read exception lines and their last frame, not keywords in printed source."""
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", diagnostics)
    errors, frame, collecting = [], None, False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("Traceback (most recent call last):") or re.match(
            r"(?:_+\s*)?ERROR collecting\b", line
        ):
            frame, collecting = None, True
        location = re.match(r'File "([^"\n]+)", line \d+', line) or re.match(
            r"(/[^\n:]+):\d+:\s*(?:in\b|$)", line
        )
        if location:
            frame = location.group(1)
        exception = re.match(r"(?:E\s+)?([A-Za-z_]\w*(?:Error|Exception)):\s*(.*)", line)
        if exception and exception.group(1) != "AssertionError":
            errors.append((exception.group(1), frame, exception.group(2)))
            frame = None
        elif collecting and line.startswith("No module named '"):
            errors.append(("ModuleNotFoundError", frame, line))
            frame = None
        elif re.fullmatch(r"\S+:(?: line \d+:)?(?: \S+:)? command not found", line):
            errors.append(("CommandNotFound", None, line))
        elif (
            re.match(
                r"(?:ERROR:|error:) (?:Could not find a version that satisfies the requirement|"
                r"No matching distribution found for|Could not install packages|"
                r"Failed building wheel for|Could not build wheels for|"
                r"[Ff]ailed to (?:download|build|fetch|install)|"
                r"No solution found when resolving dependencies)\b",
                line,
            )
            or re.match(
                r"× (?:No solution found when resolving dependencies|"
                r"Failed to (?:download|build|fetch|install))\b",
                line,
            )
            or line == "error: externally-managed-environment"
        ):
            errors.append(("DependencyInstallError", None, line))
        elif (
            re.match(r"(?:\S*/)?(?:pytest|uvx|python[\d.]*): error:", line)
            or re.match(r"(?:\S*/)?python[\d.]*: No module named\b", line)
            or line.startswith("ERROR: file or directory not found:")
        ):
            errors.append(("GraderInvocationError", None, line))
    if collecting and not errors:
        errors.append(("CollectionError", None, "unattributed collection failure"))
    return errors


def _validate_grader_warmup(
    exit_code: int,
    reward: str | None,
    report: Any,
    diagnostics: str,
    deliverables: Sequence[str] = (),
    *,
    error_output: str | None = None,
    candidate_modules: Sequence[str] = (),
    candidate_roots: Sequence[str] = (),
    allow_finite_reward: bool = False,
) -> None:
    """Accept an actual negative grade, never missing dependencies or a missing result.

    Missing *deliverables* (agent modules the tests import from the workspace, see
    _deliverable_modules) are the expected negative outcome without a solution, so
    their import and collection errors are accepted; anything else stays fatal.
    """
    excerpt = re.sub(r"[^\x20-\x7e\n\t]", "?", diagnostics[-1200:])

    def fail(reason: str) -> RuntimeError:
        return RuntimeError(f"{reason}\n--- official grader output (tail) ---\n{excerpt}")

    if reward is None:
        raise fail("skillsbench_warmup_reward_missing")
    try:
        value = float(reward.strip())
    except ValueError as exc:
        raise fail("skillsbench_warmup_reward_invalid") from exc
    if not math.isfinite(value) or (not allow_finite_reward and not 0 <= value <= 1):
        raise fail("skillsbench_warmup_reward_invalid")
    if exit_code not in {0, 1}:
        raise fail("skillsbench_warmup_execution_failed")
    broken = False
    total = None
    if report is not None:
        summary = report.get("results", {}).get("summary", {})
        total = summary.get("tests")
        if isinstance(total, bool) or not isinstance(total, int) or total < 0:
            raise fail("skillsbench_warmup_invalid_check_report")
        broken = bool(summary.get("errors", 0)) or any(
            t.get("status") in {"broken", "error"}
            for t in report.get("results", {}).get("tests", [])
        )
        if total > 0 and not broken:
            return  # Fresh official checks ran: printed source is not failure evidence.

    if broken or total == 0 or error_output is None:
        errors = _grader_errors(diagnostics)
    else:
        errors = _grader_errors(error_output)
        errors.extend(error for error in _grader_errors(diagnostics) if error[1] is not None)
        errors = list(dict.fromkeys(errors))

    def task_error(error: tuple[str, str | None, str]) -> bool:
        _kind, frame, detail = error
        missing = _missing_modules(detail)
        if missing and all(name in deliverables for name in missing):
            return True
        return bool(
            frame
            and Path(frame).stem in candidate_modules
            and any(frame.startswith(root.rstrip("/") + "/") for root in candidate_roots)
            and not any(part in {"site-packages", ".venv"} for part in Path(frame).parts)
        )

    if errors and not all(task_error(error) for error in errors):
        raise fail("skillsbench_warmup_dependency_or_collection_error")
    if errors and value == 1:
        raise fail("skillsbench_warmup_reward_contradicts_grader_error")
    if (broken or total == 0) and not errors:
        raise fail(
            "skillsbench_warmup_unattributed_grader_error"
            if broken
            else "skillsbench_warmup_no_collected_checks"
        )


def _verifier_python_mode(docker: str, image: str) -> str:
    """Use the image's own interpreter only when it matches the verifier lock resolution."""
    probe = subprocess.run(
        [docker, "run", "--rm", "--network", "none", "--entrypoint", "/bin/sh", image, "-c"]
        + [_VERIFIER_PYTHON_PROBE],
        capture_output=True,
    )
    return "native" if probe.returncode == 0 else "standalone"


def _public_python_path(docker: str, image: str) -> str | None:
    """Find MAIN's usable stdlib interpreter without requiring verifier dependencies."""
    probe = subprocess.run(
        [
            docker,
            "run",
            "--rm",
            "--network",
            "none",
            "--entrypoint",
            "/bin/sh",
            image,
            "-c",
            "python3 -I -c 'import json, subprocess, sys; "
            "assert sys.version_info.major == 3; print(json.dumps(sys.executable))'",
        ],
        capture_output=True,
        timeout=30,
    )
    if probe.returncode:
        return None
    path = json.loads(probe.stdout)
    if not isinstance(path, str) or not path.startswith("/") or "\x00" in path:
        raise ContainerUnavailable("skillsbench_public_python_probe_invalid")
    return path


def _standalone_python_layer() -> str:
    """Dockerfile lines adding a hash-verified CPython 3.11 outside the task's PATH."""
    return (
        f"COPY --from={_UV_IMAGE} /uv /usr/local/bin/tau-uv\n"
        "RUN /usr/local/bin/tau-uv python install 3.11 --no-cache --no-bin --no-registry "
        f"--install-dir {_STANDALONE_PYTHON_DIR} && ln -s "
        f'"$(ls -d {_STANDALONE_PYTHON_DIR}/cpython-3.11*/bin/python3.11 | head -n1)" '
        f"{_STANDALONE_PYTHON}\n"
    )


def prepare_docker(
    root: Path, task_id: str, *, runtime_lock_path: Path | None = None
) -> dict[str, Any]:
    """Prepare public task images without replacing a valid existing lock."""
    root = Path(root).resolve()
    if runtime_lock_path is not None and not Path(runtime_lock_path).name.startswith(
        "skillsbench-docker-"
    ):
        raise ValueError("skillsbench_docker_lock_path_invalid")
    lock_path = _docker_lock_path(root, task_id, runtime_lock_path)
    source = SkillsBenchSource(root)
    source.validate()
    if task_id not in source.manifest["tasks"]:
        raise ValueError("unknown_skillsbench_task")
    directory = source.checkout / "tasks" / task_id
    docker = shutil.which("docker")
    if not docker or subprocess.run([docker, "info"], capture_output=True, timeout=10).returncode:
        raise ContainerUnavailable("skillsbench_docker_daemon_unavailable")
    config = task_config(directory)
    if config["environment"].get("gpus", 0):
        raise ContainerUnavailable("skillsbench_gpu_runtime_not_prepared")
    if lock_path.exists() or lock_path.is_symlink():
        if lock_path.is_symlink() or not lock_path.is_file():
            raise ContainerUnavailable("skillsbench_docker_lock_not_regular")
        runner = SkillsBenchRunner(root, task_id, demo=False, runtime_lock_path=lock_path)
        locked = runner._docker_lock()
        return {
            **locked,
            "prepared": True,
            "ready": False,
            "requires_fresh_preflight": True,
            "reused": True,
            "runtime_lock": str(lock_path),
        }
    definition = _compose_definition(directory)
    images, recipes = {}, {}
    for service, settings in definition["services"].items():
        image = f"tau-skillsbench-{task_id}-{service}:{COMMIT[:12]}"
        with tempfile.TemporaryDirectory(prefix="sb-environment-build-") as temp:
            stage = Path(temp)
            build = settings["build"]
            recipe = _prepare_build_context(source, task_id, stage, **build)
            subprocess.run(
                [docker, "build", "-t", image, "-f", str(stage / build["dockerfile"]), str(stage)],
                check=True,
                stdout=sys.stderr,
            )
        metadata = json.loads(subprocess.check_output([docker, "image", "inspect", image]))[0]
        images[service] = {
            "image": image,
            "digest": metadata["Id"],
            "digest_kind": "image_id",
            "environment": metadata["Config"].get("Env") or [],
            "user": metadata["Config"].get("User") or "root",
            "workdir": metadata["Config"].get("WorkingDir") or "/",
            "entrypoint": metadata["Config"].get("Entrypoint"),
        }
        recipes[service] = hashlib.sha256(recipe.encode()).hexdigest()
    image = images["main"]["digest"]
    base_tag = images["main"]["image"]

    def verify_base_tag() -> None:
        metadata = json.loads(subprocess.check_output([docker, "image", "inspect", base_tag]))[0]
        if metadata["Id"] != image:
            raise ContainerUnavailable("skillsbench_build_base_image_changed")

    runtime_image = f"tau-skillsbench-{task_id}-runtime:{COMMIT[:12]}"
    environment = source.manifest["environments"][task_id]
    public_python = _public_python_path(docker, image)
    mode = _verifier_python_mode(docker, image)
    verifier_python = _NATIVE_PYTHON if mode == "native" else _STANDALONE_PYTHON
    python_layer = "" if mode == "native" else _standalone_python_layer()
    installer = (
        f"python3 -m pip install --require-hashes --target {_VERIFIER_PREFIX}"
        if mode == "native"
        else f"/usr/local/bin/tau-uv pip install --no-cache --python {_STANDALONE_PYTHON} "
        f"--require-hashes --target {_VERIFIER_PREFIX}"
    )
    requirements = root / "runtime/skillsbench-verifier-requirements.lock"
    with tempfile.TemporaryDirectory(prefix="sb-runtime-build-") as temp:
        stage = Path(temp)
        shutil.copy2(requirements, stage / "requirements.lock")
        (stage / "Dockerfile").write_text(
            # BuildKit resolves FROM as an image reference, not a bare local image ID.
            f"FROM {base_tag}\nUSER root\n{python_layer}"
            "COPY requirements.lock /tmp/runtime-requirements.lock\n"
            f"RUN {installer} -r /tmp/runtime-requirements.lock "
            "&& rm /tmp/runtime-requirements.lock\n"
            "RUN mkdir -p /bundle /work\n"
            f"USER {images['main']['user']}\n"
        )
        verify_base_tag()
        subprocess.run(
            [docker, "build", "-t", runtime_image, str(stage)], check=True, stdout=sys.stderr
        )
        verify_base_tag()
    metadata = json.loads(subprocess.check_output([docker, "image", "inspect", runtime_image]))[0]
    runtime = {
        **images["main"],
        "image": runtime_image,
        "digest": metadata["Id"],
        "environment": metadata["Config"].get("Env") or [],
    }
    identities = {"environment": images["main"], "runtime": runtime}
    run = [docker, "run", "--rm", "--network", "none", "--entrypoint"]
    identities["runtime"]["verifier_python"] = verifier_python
    identities["runtime"]["verifier_python_version"] = json.loads(
        subprocess.check_output(
            run
            + [verifier_python, runtime_image, "-I", "-c"]
            + ["import json, sys; print(json.dumps(list(sys.version_info[:3])))"]
        )
    )
    if public_python is None:
        if mode != "standalone":
            raise ContainerUnavailable("skillsbench_public_python_not_prepared")
        public_image = f"tau-skillsbench-{task_id}-public-main:{COMMIT[:12]}"
        runtime_digest = runtime["digest"]

        def verify_runtime_tag() -> None:
            current = json.loads(
                subprocess.check_output([docker, "image", "inspect", runtime_image])
            )[0]
            if current["Id"] != runtime_digest:
                raise ContainerUnavailable("skillsbench_build_runtime_image_changed")

        with tempfile.TemporaryDirectory(prefix="sb-public-main-build-") as temp:
            stage = Path(temp)
            # Inherit the official image configuration unchanged. Only the separate
            # interpreter is copied; verifier packages and private tests stay out.
            (stage / "Dockerfile").write_text(
                f"FROM {base_tag}\n"
                f"COPY --from={runtime_image} {_STANDALONE_PYTHON_DIR} {_STANDALONE_PYTHON_DIR}\n"
            )
            verify_base_tag()
            verify_runtime_tag()
            subprocess.run(
                [docker, "build", "-t", public_image, str(stage)], check=True, stdout=sys.stderr
            )
            verify_base_tag()
            verify_runtime_tag()
        public_metadata = json.loads(
            subprocess.check_output([docker, "image", "inspect", public_image])
        )[0]
        original = images["main"]
        inherited = public_metadata["Config"]
        if (
            (inherited.get("Env") or []) != original["environment"]
            or (inherited.get("User") or "root") != original["user"]
            or (inherited.get("WorkingDir") or "/") != original["workdir"]
            or inherited.get("Entrypoint") != original["entrypoint"]
        ):
            raise ContainerUnavailable("skillsbench_public_image_configuration_changed")
        images["main"] = {
            **original,
            "image": public_image,
            "digest": public_metadata["Id"],
            "source_digest": original["digest"],
        }
        public_python = _STANDALONE_PYTHON
    public_version = json.loads(
        subprocess.check_output(
            run
            + [public_python, images["main"]["image"], "-I", "-c"]
            + ["import json,sys; print(json.dumps(list(sys.version_info[:3])))"]
        )
    )
    if (
        not isinstance(public_version, list)
        or len(public_version) != 3
        or any(type(part) is not int for part in public_version)
        or public_version[0] != 3
    ):
        raise ContainerUnavailable("skillsbench_public_python_version_invalid")
    images["main"]["public_python"] = public_python
    images["main"]["public_python_version"] = public_version
    lock = {
        "runtime_schema": _EPISODE_SCHEMA,
        "task_id": task_id,
        "commit": COMMIT,
        "images": identities,
        "verifier_python_mode": mode,
        "services": definition,
        "service_images": images,
        "adapted_recipe_hashes": recipes,
        "compose_sha256": _hash(directory / "environment/docker-compose.yaml")
        if (directory / "environment/docker-compose.yaml").exists()
        else None,
        "task_config_hash": _json_hash(config),
        "dockerfile_sha256": _hash(directory / "environment/Dockerfile"),
        "public_manifest_hash": source.manifest["manifest_hash"],
        "dependency_hash": _hash(requirements),
        "resources": config["environment"],
        "layout": environment,
        "grader_tests_hash": _json_hash(
            {
                p.relative_to(directory / "tests").as_posix(): _hash(p)
                for p in sorted((directory / "tests").rglob("*"))
                if p.is_file()
            }
        ),
    }
    atomic_json(lock_path, lock)
    return {
        "prepared": True,
        "ready": False,
        "requires_fresh_preflight": True,
        "runtime_lock": str(lock_path),
        **lock,
    }


class SkillsBenchRunner:
    def __init__(
        self,
        root: Path,
        task_id: str,
        *,
        demo: bool,
        transport: Any = None,
        runtime: str | None = None,
        runtime_lock_path: Path | None = None,
    ):
        self.root, self.task_id, self.demo = Path(root).resolve(), task_id, demo
        self.runtime = runtime or ("bubblewrap-demo" if demo else "docker")
        if self.runtime not in {"workspace", "bubblewrap-demo", "docker"}:
            raise ValueError("unsupported_skillsbench_runtime")
        self.use_bwrap = self.runtime != "docker"
        lock_path = _workspace_lock_path if self.use_bwrap else _docker_lock_path
        self.runtime_lock_path = lock_path(self.root, task_id, runtime_lock_path)
        self.source = SkillsBenchSource(root)
        self.task_directory = self.source.checkout / "tasks" / task_id
        self.config = task_config(self.task_directory)
        self.transport = transport or BoundedProcessTransport(kill_process_group=True)
        self.timeout, self.output_limit = 60.0, 65536
        self.cpu = min(os.sched_getaffinity(0))
        self.verifier_artifacts: Path | None = None
        self.workspace_roots: tuple[str, ...] = ()
        self.container_name: str | None = None
        self.compose_path: Path | None = None
        self.public_open = False
        self.episode_started = 0.0
        self.public_workspace_mode = False
        self.private_grade_started = False
        self.grader_diagnostics: str | None = None
        self.execution_framework = "local-tools"
        self.codex_skill_mode = True
        self.provider_directory: Path | None = None
        self.agent_timeout_seconds: float | None = None
        self.learning_workspace: Any | None = None
        self.learning_checkpoint: Path | None = None
        self.learning_state: dict[str, Any] | None = None
        self.learning_scratch: Path | None = None
        self.learning_deadline: float | None = None
        self.execution_deadline: float | None = None
        self.timeout_multiplier: float = 5

    def _lock(self) -> SkillsBenchRuntimeLock:
        return SkillsBenchRuntimeLock.from_file(self.runtime_lock_path)

    @property
    def workspace_directory(self) -> str:
        return _WORKSPACE_DIRECTORIES[self.task_id] if self.runtime == "workspace" else "/root"

    @property
    def public_python(self) -> str:
        """The locked MAIN interpreter for relay/harness use, outside the task PATH."""
        if self.use_bwrap:
            return "/usr/local/bin/python"
        return self._docker_lock()["service_images"]["main"].get("public_python", _NATIVE_PYTHON)

    def _validate_workspace(self) -> None:
        if self.runtime == "workspace":
            status = workspace_preparation(
                self.root, self.task_id, runtime_lock_path=self.runtime_lock_path
            )
            if not status["supported"]:
                raise ContainerUnavailable(status["reason"])
        self._lock().validate(self.task_id)

    def _command(
        self, package: Path, work: Path, args: Sequence[str], *, grader: bool = False
    ) -> list[str]:
        if not self.use_bwrap:
            return self._docker_command(package, work, args, grader=grader)
        memory = int(self.config["environment"].get("memory_mb", 1024)) * 1024 * 1024
        command = [
            "taskset",
            "--cpu-list",
            str(self.cpu),
            "prlimit",
            f"--as={memory}",
            "--",
            "bwrap",
            "--unshare-all",
            "--unshare-user",
            "--uid",
            "10001",
            "--gid",
            "10001",
            "--cap-drop",
            "ALL",
            "--clearenv",
            "--new-session",
            "--die-with-parent",
            "--disable-userns",
        ]
        rootfs = self._lock().rootfs
        if self.workspace_directory == "/app":
            # The immutable original rootfs has no /app mount point. Assemble its
            # existing roots unchanged, then protect the new namespace root below.
            command += ["--tmpfs", "/", "--dir", "/app"]
            for child in sorted(rootfs.iterdir()):
                command += ["--ro-bind", str(child), "/" + child.name]
        else:
            command += ["--ro-bind", str(rootfs), "/"]
        command += [
            "--ro-bind",
            str(package),
            "/bundle",
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--size",
            "67108864",
            "--tmpfs",
            "/tmp",
        ]
        if self.public_workspace_mode:
            writable = _workspace_writable_roots(package)
            command += [
                "--ro-bind",
                str(work),
                "/work",
                "--chdir",
                "/work/scratch"
                if "scratch" in writable and "candidate" not in writable
                else "/work",
            ]
            for relative in _workspace_writable_roots(package):
                command += ["--bind", str(work / relative), "/work/" + relative]
            if self.verifier_artifacts is None:
                # Original public inputs may have parents absent from the sealed
                # rootfs. Create mount points here, then protect this root below.
                command += ["--size", "67108864", "--tmpfs", self.workspace_directory]
        if self.verifier_artifacts is not None:
            for entry in sorted(self.verifier_artifacts.iterdir()):
                if entry.is_symlink() or not (entry.is_dir() or entry.is_file()):
                    raise ValueError("skillsbench_artifact_mount_not_regular")
                command += ["--ro-bind", str(entry), "/" + entry.name]
            if not self.public_workspace_mode:
                command += ["--bind", str(work), "/work", "--chdir", "/work"]
        else:
            if not self.public_workspace_mode:
                command += ["--bind", str(work), "/root"]
                if self.workspace_directory != "/root":
                    command += ["--bind", str(work), self.workspace_directory]
                command += ["--chdir", self.workspace_directory]
            for entry in (
                self.source.task(self.task_id)["public_input_manifest"]
                if self.demo or self.public_workspace_mode
                else ()
            ):
                relative = entry["relative_path"].removeprefix("environment/")
                original = self.task_directory / "environment" / _safe_path(relative)
                for destination in entry["sandbox_paths"]:
                    prefix = self.workspace_directory + "/"
                    if not destination.startswith(prefix):
                        raise ContainerUnavailable("skillsbench_demo_layout_not_prepared")
                    _safe_path(destination.removeprefix(prefix))
                    command += ["--ro-bind", str(original), destination]
        if grader:
            command += [
                "--ro-bind",
                str(self.task_directory / "tests"),
                "/tests",
                "--bind",
                str(work.parent / "grader-logs"),
                "/logs/verifier",
            ]
            if self.runtime == "workspace" and self.task_id in _WORKSPACE_TEST_SCRIPT_SHA256:
                command += [
                    "--ro-bind",
                    str(work.parent / "grader-bootstrap.sh"),
                    "/tests/test.sh",
                ]
        environment = {
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "HOME": "/root",
            "LD_LIBRARY_PATH": "/usr/local/lib",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": "/bundle:/bundle/scripts",
            "PIP_NO_INDEX": "1",
            "PIP_DISABLE_PIP_VERSION_CHECK": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "OMP_NUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1",
        }
        if self.public_workspace_mode:
            environment.update(HOME="/work/scratch", TMPDIR="/work/scratch")
        if (
            self.runtime == "workspace"
            and not self.public_workspace_mode
            and self.verifier_artifacts is None
        ):
            environment["PATH"] = "/root/.venv/bin:" + environment["PATH"]
            environment["VIRTUAL_ENV"] = "/root/.venv"
        if not grader:
            environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
        for name, value in environment.items():
            command += ["--setenv", name, value]
        if self.public_workspace_mode and self.verifier_artifacts is None:
            command += ["--remount-ro", self.workspace_directory]
        if self.workspace_directory == "/app":
            command += ["--remount-ro", "/"]
        wrapper = (
            "import os,resource,sys; resource.setrlimit(resource.RLIMIT_NPROC,(64,64)); "
            "os.execv(sys.argv[1],sys.argv[1:])"
        )
        command += [
            "--",
            "/usr/local/bin/python",
            "-I",
            "-c",
            wrapper,
            *(
                (
                    "/root/.venv/bin/python"
                    if self.runtime == "workspace"
                    and not self.public_workspace_mode
                    and self.verifier_artifacts is None
                    else "/usr/local/bin/python"
                )
                if args[0] == "python"
                else args[0],
                *args[1:],
            ),
        ]
        return command

    def _docker_command(
        self, package: Path, work: Path, args: Sequence[str], *, grader: bool
    ) -> list[str]:
        """Independent public inspection, never a second baseline-image official grade."""
        if grader:
            raise PermissionError("official_grader_requires_closed_episode")
        lock = self._docker_lock()
        identity = lock["images"]["runtime"]
        resources = self.config["environment"]
        command = [
            "docker",
            "run",
            "--interactive",
            "--user",
            f"{os.getuid()}:{os.getgid()}" if os.getuid() else "10001:10001",
            "--name",
            "tau-sb-public-" + uuid.uuid4().hex,
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--cpus",
            str(resources["cpus"]),
            "--memory",
            f"{resources['memory_mb']}m",
            "--memory-swap",
            f"{resources['memory_mb']}m",
            "--workdir",
            "/work",
            "--mount",
            f"type=bind,src={package},dst=/bundle,readonly",
        ]
        writable = _workspace_writable_roots(package)
        if "scratch" in writable and "candidate" not in writable:
            command[command.index("--workdir") + 1] = "/work/scratch"
        if not writable:
            command += ["--mount", f"type=bind,src={work},dst=/work"]
        else:
            command += ["--mount", f"type=bind,src={work},dst=/work,readonly"]
            for relative in writable:
                path = work / _safe_path(relative)
                command += ["--mount", f"type=bind,src={path},dst=/work/{relative}"]
        if self.verifier_artifacts is not None:
            for entry in sorted(self.verifier_artifacts.iterdir()):
                if entry.is_symlink() or not entry.is_dir():
                    raise ValueError("skillsbench_artifact_mount_not_regular")
                command += ["--mount", f"type=bind,src={entry},dst=/{entry.name},readonly"]
        interpreter = identity["verifier_python"]
        if args[0] == "python":
            args = [interpreter, *args[1:]]
            if args[1:3] == ["-I", "-c"]:
                args[3] = f"import sys; sys.path.insert(0, {_VERIFIER_PREFIX!r}); " + args[3]
            else:
                script = args[2:] if len(args) > 1 and args[1] == "-I" else args[1:]
                args = [
                    interpreter,
                    "-I",
                    "-c",
                    f"import sys,runpy; sys.path.insert(0, {_VERIFIER_PREFIX!r}); "
                    "sys.argv = sys.argv[1:]; "
                    "runpy.run_path(sys.argv[0],run_name='__main__')",
                    *script,
                ]
        command += [
            "--tmpfs",
            "/tmp:rw,nosuid,nodev,size=64m",
            "--entrypoint",
            "/usr/bin/env",
            identity["digest"],
            "-i",
            "PATH=/usr/local/bin:/usr/bin:/bin",
            "HOME=/work/scratch",
            "TMPDIR=/work/scratch" if "scratch" in writable else "TMPDIR=/tmp",
            f"PYTHONPATH={_VERIFIER_PREFIX}",
            "PYTHONDONTWRITEBYTECODE=1",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1",
            *args,
        ]
        return command

    def _compose_command(self, *args: str) -> list[str]:
        if self.compose_path is None or self.container_name is None:
            raise ContainerUnavailable("skillsbench_episode_not_started")
        return ["docker", "compose", "-p", self.container_name, "-f", str(self.compose_path), *args]

    def _start_episode(self, episode: SkillEpisode) -> None:
        lock = self._docker_lock()
        self.container_name = "tau-sb-" + uuid.uuid4().hex
        self.compose_path = episode.work.parent / "docker-compose.yaml"
        logs = episode.work.parent / "grader-logs"
        logs.mkdir(mode=0o777)
        logs.chmod(0o777)
        definition = json.loads(json.dumps(lock["services"]))
        resolved = {}
        for name, service in definition["services"].items():
            service.pop("build", None)
            service["image"] = lock["service_images"][name]["digest"]
            declared = service.pop("environment", {})
            if name == "main":
                declared = {**self.config["environment"].get("env", {}), **declared}
            env = _resolve_environment(declared, required=False, task_id=self.task_id)
            service["environment"] = {}
            for key, value in env.items():
                variable = "TAU_SB_ENV_" + name.replace("-", "_") + "_" + key
                resolved[variable] = value
                service["environment"][key] = "${" + variable + "}"
        main = definition["services"]["main"]
        main["container_name"] = self.container_name
        main["volumes"] = [
            {
                "type": "bind",
                "source": str(episode.package),
                "target": "/bundle",
                "read_only": True,
            },
            {"type": "bind", "source": str(logs), "target": "/logs/verifier"},
        ]
        if self.learning_workspace is not None:
            session = self.learning_workspace
            self._prepare_frozen_documents(json.loads((session.package / "base.json").read_text()))
            main["volumes"] = [
                {
                    "type": "bind",
                    "source": str(session.package),
                    "target": "/bundle",
                    "read_only": True,
                },
                {"type": "bind", "source": str(session.work), "target": "/work", "read_only": True},
                *[
                    {
                        "type": "bind",
                        "source": str(session.target),
                        "target": target,
                        "read_only": False,
                    }
                    for target in ("/work/candidate", "/app/environment/skills/current")
                ],
                {
                    "type": "bind",
                    "source": str(self.learning_scratch),
                    "target": "/work/scratch",
                    "read_only": False,
                },
                {
                    "type": "bind",
                    "source": str(session.work.parent / "frozen-documents"),
                    "target": "/app/environment/doc",
                    "read_only": True,
                },
            ]
        elif self.execution_framework == "author-codex":
            # The no-Skill control exposes no package, including an empty dummy package.
            main["volumes"] = [main["volumes"][-1]]
            if self.codex_skill_mode:
                main["volumes"] += [
                    {
                        "type": "bind",
                        "source": str(episode.package),
                        "target": target,
                        "read_only": True,
                    }
                    for target in ("/bundle", "/app/environment/skills/current")
                ]
            if self.provider_directory is None:
                raise ContainerUnavailable("codex_provider_not_started")
            main["volumes"].append(
                {
                    "type": "bind",
                    "source": str(self.provider_directory),
                    "target": "/run/skill-provider",
                    "read_only": True,
                }
            )
        # Retain ordinary task-image privileges so root tasks can install their
        # declared dependencies. Public inspection containers remain cap-drop ALL.
        main.setdefault("security_opt", ["no-new-privileges:true"])
        resources = self.config["environment"]
        main["deploy"] = {
            "resources": {
                "limits": {"cpus": str(resources["cpus"]), "memory": f"{resources['memory_mb']}M"}
            }
        }
        if len(definition["services"]) == 1 and not main.get("networks"):
            main["network_mode"] = "bridge" if resources["allow_internet"] else "none"
        elif not resources["allow_internet"]:
            networks = definition.setdefault("networks", {})
            if any(not service.get("networks") for service in definition["services"].values()):
                networks.setdefault("default", {})
            for name, network in networks.items():
                networks[name] = {**(network or {}), "internal": True}
        self.compose_path.write_text(yaml.safe_dump(definition, sort_keys=True))
        self.compose_path.chmod(0o600)
        if self.learning_checkpoint is not None:
            self.learning_state.update(
                container_name=self.container_name,
                compose_path=str(self.compose_path),
                compose_hash=_hash(self.compose_path),
            )
            atomic_json(self.learning_checkpoint, self.learning_state)
        result = self.transport.run(
            self._compose_command("up", "--detach", "--wait", "--no-build"),
            stdin=b"",
            timeout=(
                min(resources["build_timeout_sec"], self.phase_remaining())
                if self.learning_deadline is not None or self.execution_deadline is not None
                else resources["build_timeout_sec"]
            ),
            output_limit=self.output_limit,
            env=_host_environment(resolved),
        )
        if result.returncode or result.failure:
            raise ContainerUnavailable("skillsbench_task_services_not_ready")
        self.public_open = True
        self.private_grade_started = False
        self.episode_started = time.monotonic()
        self._guard_public_episode(episode)
        skill_boundary = (
            "test -f /app/environment/skills/current/SKILL.md"
            if self.learning_workspace is not None
            or (self.execution_framework == "author-codex" and self.codex_skill_mode)
            else "test ! -e /app/environment/skills"
        )
        boundary = self._exec(
            [
                "/bin/bash",
                "-c",
                "test ! -e /tests/test.sh && "
                + (
                    "test -d /app/environment/doc"
                    if self.learning_workspace is not None
                    else "test ! -e /app/environment/doc"
                )
                + " && "
                + skill_boundary,
            ],
            public=True,
        )
        if boundary.returncode or boundary.failure:
            raise ContainerUnavailable("skillsbench_public_environment_contains_private_files")
        if self.learning_workspace is not None:
            self.stage_frozen_documents(
                json.loads((self.learning_workspace.package / "base.json").read_text())
            )

    def _prepare_frozen_documents(self, base: Mapping[str, Any]) -> None:
        directory = self.learning_workspace.work.parent / "frozen-documents"
        if directory.exists():
            self.stage_frozen_documents(base)
            return
        directory.mkdir(mode=0o755)
        for document in base.get("documents", ()):
            name = hashlib.sha256(document["document_id"].encode()).hexdigest() + ".md"
            path = directory / name
            path.write_text(document["content"], encoding="utf-8")
            path.chmod(0o444)

    def stage_frozen_documents(self, base: Mapping[str, Any]) -> None:
        """Check the frozen host bytes mounted at the author's public doc path."""
        from .container import _tree_manifest

        directory = self.learning_workspace.work.parent / "frozen-documents"
        expected = {
            hashlib.sha256(document["document_id"].encode()).hexdigest() + ".md": hashlib.sha256(
                document["content"].encode()
            ).hexdigest()
            for document in base.get("documents", ())
        }
        if directory.is_symlink() or _tree_manifest(directory) != expected:
            raise ContainerUnavailable("skillsbench_frozen_documents_changed")

    def _guard_public_episode(self, episode: SkillEpisode) -> None:
        # Both SkillEpisode helpers and terminal capability close before private grading.
        for name in ("read_skill_file", "run_skill_script"):
            original = getattr(episode, name)

            def guarded(*args: Any, _original: Any = original, **kwargs: Any) -> Any:
                if not self.public_open:
                    raise PermissionError("skillsbench_public_episode_closed")
                return _original(*args, **kwargs)

            setattr(episode, name, guarded)

    def _stop_episode(self) -> None:
        try:
            if self.compose_path is not None and self.container_name is not None:
                # Only grader logs are writable host mounts. Task files stay in the
                # fresh image layer with their original ownership and permissions.
                self.transport.run(
                    [
                        "docker",
                        "exec",
                        "--user",
                        "root",
                        self.container_name,
                        "/bin/bash",
                        "-c",
                        "chmod -R a+rwX -- /logs/verifier",
                    ],
                    stdin=b"",
                    timeout=30,
                    output_limit=self.output_limit,
                    env=_host_environment(),
                )
                result = self.transport.run(
                    self._compose_command("down", "--volumes", "--remove-orphans"),
                    stdin=b"",
                    timeout=30,
                    output_limit=self.output_limit,
                    env=_host_environment(),
                )
                if result.returncode or result.failure:
                    raise ContainerUnavailable("skillsbench_episode_cleanup_failed")
        finally:
            self.public_open = False
            self.container_name = None
            self.compose_path = None

    def close_public(self, _episode: SkillEpisode) -> None:
        self.public_open = False

    @contextmanager
    def snapshot_workspace(self) -> Iterator[dict[str, Path]]:
        """Copy the live public filesystem without changing the candidate's permissions."""
        if not self.public_open or self.container_name is None:
            raise PermissionError("skillsbench_public_episode_closed")
        with tempfile.TemporaryDirectory(prefix="sb-public-copy-") as staging:
            roots = {}
            for destination in self.workspace_roots:
                target = Path(staging) / destination.lstrip("/")
                target.mkdir(parents=True)
                archive = "/.tau-public-copy-" + uuid.uuid4().hex + ".tar"
                prefix = ["docker", "exec", "--user", "root", self.container_name]

                def run(command: Sequence[str]) -> ProcessResult:
                    remaining = self.phase_remaining()
                    bound = (
                        self.learning_deadline is not None or self.execution_deadline is not None
                    )
                    if bound and remaining <= 0:
                        raise TimeoutError("learning_timeout")
                    return self.transport.run(
                        command,
                        stdin=b"",
                        timeout=min(60, remaining) if bound else 60,
                        output_limit=self.output_limit,
                        env=_host_environment(),
                    )

                try:
                    result = run(
                        [
                            *prefix,
                            "/bin/bash",
                            "-c",
                            'test -e "$1" || exit 44; tar --hard-dereference -cf "$2" -C "$1" .',
                            "snapshot",
                            destination,
                            archive,
                        ]
                    )
                    if result.returncode == 44 and not result.failure:
                        # Preserve an output root the task never created as absent.
                        continue
                    if result.returncode or result.failure:
                        raise ContainerUnavailable("skillsbench_public_snapshot_copy_failed")
                    copied = Path(staging) / Path(archive).name
                    result = run(["docker", "cp", self.container_name + ":" + archive, str(copied)])
                    if result.returncode or result.failure:
                        raise ContainerUnavailable("skillsbench_public_snapshot_copy_failed")
                    # A flat archive bypasses docker cp's eager chmod of directories;
                    # its binary contents never pass through the bounded stdout pipe.
                    with tarfile.open(copied, "r|") as content:
                        for member in content:
                            if member.name in {".", "./"}:
                                continue
                            relative = member.name.removeprefix("./").rstrip("/")
                            path = _safe_path(relative)
                            if (
                                _private_path(relative)
                                or any(p in {".skills", ".evolution", ".venv"} for p in path.parts)
                                or (destination.lstrip("/") + "/" + relative).startswith(
                                    ("root/verifier/", "logs/verifier/")
                                )
                            ):
                                continue
                            output = target / path
                            if (
                                output.exists()
                                or output.is_symlink()
                                or any(p.is_symlink() for p in output.parents if p != target)
                            ):
                                raise ValueError("skillsbench_public_snapshot_archive_path")
                            output.parent.mkdir(parents=True, exist_ok=True)
                            if member.isdir():
                                output.mkdir(exist_ok=True)
                            elif member.issym():
                                if not _public_link_target(
                                    destination.lstrip("/") + "/" + relative,
                                    member.linkname,
                                    self.workspace_roots,
                                ):
                                    continue
                                output.symlink_to(member.linkname)
                            elif member.isfile():
                                with (
                                    content.extractfile(member) as source,
                                    output.open("wb") as sink,
                                ):
                                    shutil.copyfileobj(source, sink)
                                output.chmod((member.mode & 0o777) | 0o400)
                            else:
                                raise ValueError("skillsbench_public_snapshot_archive_member")
                except (OSError, ValueError, tarfile.TarError) as exc:
                    raise ContainerUnavailable("skillsbench_public_snapshot_copy_failed") from exc
                finally:
                    result = run([*prefix, "/bin/rm", "-f", "--", archive])
                    if result.returncode or result.failure:
                        raise ContainerUnavailable(
                            "skillsbench_public_snapshot_copy_failed:archive_cleanup_failed"
                        )
                roots[destination] = target
            yield roots

    def public_environment_manifest(self) -> dict[str, str]:
        """Host audit of public bytes, excluding author tests and private role files."""
        manifest = {}
        with self.snapshot_workspace() as roots:
            for mount, directory in roots.items():
                for path in sorted(directory.rglob("*")):
                    relative = path.relative_to(directory)
                    public_path = mount.rstrip("/") + "/" + relative.as_posix()
                    if any(
                        part
                        in {
                            "skills",
                            "candidate",
                            ".skills",
                            ".claude",
                            ".codex",
                            ".evolution",
                            ".venv",
                        }
                        for part in relative.parts
                    ) or public_path.startswith(("/root/verifier", "/logs/verifier")):
                        continue
                    if path.is_symlink():
                        manifest[public_path] = "symlink:" + os.readlink(path)
                    elif path.is_file():
                        manifest[public_path] = _hash(path)
        return manifest

    def _exec(
        self,
        args: Sequence[str],
        stdin: bytes = b"",
        *,
        public: bool,
        environment: Mapping[str, str] | None = None,
    ) -> ProcessResult:
        if self.container_name is None:
            raise ContainerUnavailable("skillsbench_episode_not_started")
        if public != self.public_open:
            raise PermissionError(
                "skillsbench_public_episode_closed"
                if public
                else "skillsbench_private_grade_before_public_close"
            )
        command = [
            "docker",
            "exec",
            "--interactive",
            "--workdir",
            self.source.task(self.task_id)["environment"]["workdir"],
        ]
        for name in environment or {}:
            command += ["--env", name]
        command += [
            self.container_name,
            *(self.public_python if args[0] == "python" else args[0], *args[1:]),
        ]
        remaining = self.phase_remaining()
        deadline_bound = self.learning_deadline is not None or self.execution_deadline is not None
        if deadline_bound and remaining <= 0:
            raise TimeoutError("learning_timeout")
        timeout = (
            min(
                900.0,
                self.config["agent"]["timeout_sec"] * self.timeout_multiplier,
                self.phase_remaining(),
            )
            if self.learning_workspace is not None
            else (
                max(
                    0.1,
                    (self.agent_timeout_seconds or self.config["agent"]["timeout_sec"])
                    - (time.monotonic() - self.episode_started),
                )
                if public
                else self.config["verifier"]["timeout_sec"]
            )
        )
        if deadline_bound:
            timeout = min(timeout, remaining)
        if self.learning_workspace is not None:
            # Bound the process inside the persistent container, not just docker exec.
            command = command[: -len(args)] + [
                "timeout",
                "--signal=TERM",
                "--kill-after=5",
                str(timeout),
                *command[-len(args) :],
            ]
        result = self.transport.run(
            command,
            stdin=stdin,
            timeout=(
                min(timeout + 10, remaining)
                if self.learning_workspace is not None and deadline_bound
                else timeout + 10
                if self.learning_workspace is not None
                else timeout
            ),
            output_limit=self.output_limit if public else _GRADER_OUTPUT_LIMIT,
            env=_host_environment(environment),
        )
        if self.learning_workspace is not None and result.returncode in (124, 137):
            return ProcessResult(result.returncode, result.stdout, result.stderr, "timeout")
        return result

    def _raw(
        self,
        package: Path,
        work: Path,
        args: Sequence[str],
        stdin: bytes = b"",
        *,
        grader: bool = False,
    ) -> Any:
        if (
            not self.use_bwrap
            and self.container_name is not None
            and self.verifier_artifacts is None
            and not self.public_workspace_mode
        ):
            return self._exec(args, stdin, public=not grader)
        command = self._command(package.resolve(), work.resolve(), args, grader=grader)
        timeout = self.config["verifier"]["timeout_sec"] if grader else self.timeout
        result = None
        launch_failed = False
        try:
            result = self.transport.run(
                command,
                stdin=stdin,
                timeout=timeout,
                output_limit=_GRADER_OUTPUT_LIMIT if grader else self.output_limit,
                env=_host_environment(),
            )
        except OSError as exc:
            launch_failed = isinstance(exc, FileNotFoundError)
            result = ProcessResult(-1, stderr=str(exc).encode(), failure="container_unavailable")
        finally:
            if not self.use_bwrap and not launch_failed:
                name = command[command.index("--name") + 1]
                try:
                    cleanup = self.transport.run(
                        ["docker", "rm", "--force", "--volumes", name],
                        stdin=b"",
                        timeout=10,
                        output_limit=self.output_limit,
                        env=_host_environment(),
                    )
                except OSError as exc:
                    cleanup = ProcessResult(
                        -1, stderr=str(exc).encode(), failure="container_unavailable"
                    )
                detail = (cleanup.stdout + cleanup.stderr).decode("utf-8", "replace")
                if cleanup.failure or (
                    cleanup.returncode and "no such container" not in detail.lower()
                ):
                    original = result.failure if result else "interrupted"
                    trusted = (
                        f"[trusted cleanup] container={name}; staging={package.parent}; "
                        f"original_failure={original}; "
                        f"cleanup_failure={cleanup.failure or cleanup.returncode}; {detail[:512]}\n"
                    )
                    diagnostic = (trusted.encode() + (result.stderr if result else b""))[
                        : self.output_limit
                    ]
                    result = ProcessResult(
                        result.returncode if result else -1,
                        result.stdout[: self.output_limit - len(diagnostic)] if result else b"",
                        diagnostic,
                        "cleanup_failed",
                    )
        return result

    def _run(
        self, package: Path, work: Path, args: Sequence[str], stdin: bytes = b""
    ) -> ProgramResult:
        return _program_result(self._raw(package, work, args, stdin))

    def terminal(self, episode: SkillEpisode, command: str) -> ProgramResult:
        if not isinstance(command, str) or not command.strip():
            raise ValueError("terminal_command_must_be_nonempty")
        if not self.public_open:
            raise PermissionError("skillsbench_public_episode_closed")
        # The pinned author's environment.exec creates a fresh interactive shell
        # for each command. Container files, installs and services still persist.
        result = self._raw(episode.package, episode.work, ["/bin/bash", "-ic", command])
        return ProgramResult(
            result.returncode,
            result.stdout.decode("utf-8", "replace"),
            result.stderr.decode("utf-8", "replace"),
            result.failure,
        )

    def phase_remaining(self) -> float:
        deadline = (
            self.learning_deadline
            if self.learning_deadline is not None
            else self.execution_deadline
        )
        return (
            max(0.0, deadline - time.time())
            if deadline is not None
            else float(self.config["agent"]["timeout_sec"] * self.timeout_multiplier)
        )

    def author_exec(
        self,
        command: str,
        *,
        cwd: str | None = None,
        env: Mapping[str, str] | None = None,
        timeout_sec: float | None = None,
    ) -> ProcessResult:
        """Author BaseEnvironment.exec semantics in the active learning MAIN."""
        if self.learning_workspace is None or not self.public_open or self.container_name is None:
            raise ContainerUnavailable("author_verifier_requires_live_learning_main")
        remaining = self.phase_remaining()
        if remaining <= 0:
            raise TimeoutError("learning_timeout")
        timeout = min(float(timeout_sec or 900), 900.0, remaining)
        arguments = ["docker", "exec", "--interactive"]
        if cwd is not None:
            arguments += ["--workdir", cwd]
        for name, value in (env or {}).items():
            arguments += ["--env", f"{name}={value}"]
        arguments += [
            self.container_name,
            "timeout",
            "--signal=TERM",
            "--kill-after=5",
            str(timeout),
            "/bin/bash",
            "-ic",
            command,
        ]
        result = self.transport.run(
            arguments,
            stdin=b"",
            timeout=min(timeout + 10, remaining),
            output_limit=self.output_limit,
            env=_host_environment(),
        )
        if result.returncode in (124, 137):
            return ProcessResult(result.returncode, result.stdout, result.stderr, "timeout")
        return result

    @contextmanager
    def learning_episode(
        self,
        session: Any,
        *,
        checkpoint: Path,
        identity: Mapping[str, Any],
        deadline: float | None = None,
    ) -> Iterator[tuple[SkillEpisode, dict[str, Any]]]:
        """Own one task environment; reconnect only to the exact surviving containers."""
        if self.use_bwrap:
            raise ContainerUnavailable("skillsbench_direct_evolution_requires_docker")
        self._docker_lock()
        identity_hash = _json_hash(identity)
        if checkpoint.exists():
            state = json.loads(checkpoint.read_text())
            if state.get("identity_hash") != identity_hash:
                raise ValueError("skillsbench_evolution_runtime_identity_differs")
            if state.get("status") != "ACTIVE":
                raise ContainerUnavailable("skillsbench_evolution_environment_not_active")
            self.container_name = state["container_name"]
            self.compose_path = Path(state["compose_path"])
            if self.compose_path != session.work.parent / "docker-compose.yaml" or (
                not self.compose_path.is_file() or _hash(self.compose_path) != state["compose_hash"]
            ):
                raise ContainerUnavailable("skillsbench_evolution_compose_changed")
            fields = ("id", "name", "service", "started_at", "restart_count")
            current = [
                tuple(item[field] for field in fields) for item in self._learning_containers()
            ]
            saved = [tuple(item[field] for field in fields) for item in state["containers"]]
            if current != saved:
                raise ContainerUnavailable("skillsbench_evolution_environment_missing")
        else:
            state = {
                "schema": "skillsbench.evolution-runtime.v1",
                "identity_hash": identity_hash,
                "execution_id": uuid.uuid4().hex,
                "status": "STARTING",
                "operation_cursor": 0,
                "events": [],
                "learning_deadline": deadline if deadline is not None else time.time() + 7200,
            }
            atomic_json(checkpoint, state)
        self.learning_workspace = session
        self.learning_deadline = state.get("learning_deadline")
        if not isinstance(self.learning_deadline, (int, float)):
            raise ContainerUnavailable("skillsbench_learning_deadline_missing")
        if deadline is not None and deadline != self.learning_deadline:
            raise ContainerUnavailable("skillsbench_learning_deadline_changed")
        self.learning_checkpoint, self.learning_state = checkpoint, state
        self.learning_scratch = session.work.parent / "task-scratch"
        if self.learning_scratch.is_symlink():
            raise ValueError("unsafe_learning_scratch_root")
        self.learning_scratch.mkdir(mode=0o777, exist_ok=True)
        self.learning_scratch.chmod(0o777)
        self.workspace_roots = tuple(
            self.source.task(self.task_id)["environment"]["workspace_roots"]
        )
        episode = SkillEpisode(self, session.target, session.work, session.files())
        interrupted = False
        try:
            if state["status"] == "STARTING":
                self._start_episode(episode)
                state["containers"] = self._learning_containers()
                state["status"] = "ACTIVE"
                atomic_json(checkpoint, state)
            else:
                self.public_open, self.private_grade_started = True, False
                self.episode_started = time.monotonic()
            probe = self._exec(["/bin/sh", "-c", "command -v timeout >/dev/null"], public=True)
            if probe.returncode or probe.failure:
                raise ContainerUnavailable("skillsbench_learning_terminal_timeout_unavailable")
            yield episode, state
        except (KeyboardInterrupt, SystemExit):
            # A later process may reconnect; no terminal/model UNKNOWN is replayed.
            interrupted = True
            raise
        finally:
            try:
                if not interrupted:
                    self._stop_episode()
                    state["status"] = "CLOSED"
                    atomic_json(checkpoint, state)
            finally:
                self.learning_workspace = None
                self.learning_checkpoint = self.learning_state = None
                self.learning_scratch = None
                self.learning_deadline = None
                self.workspace_roots = ()

    def _learning_containers(self) -> list[dict[str, Any]]:
        services = self._docker_lock()["services"]["services"]
        requirements: dict[str, set[str]] = {"main": {"service_started"}}
        for service in services.values():
            dependencies = service.get("depends_on", {})
            if isinstance(dependencies, list):
                dependencies = {name: {} for name in dependencies}
            for name, dependency in dependencies.items():
                if dependency.get("required", True):
                    requirements.setdefault(name, set()).add(
                        dependency.get("condition", "service_started")
                    )
        result = self.transport.run(
            self._compose_command("ps", "--all", "--quiet"),
            stdin=b"",
            timeout=10,
            output_limit=65536,
            env=_host_environment(),
        )
        containers = sorted(result.stdout.decode().split())
        if result.returncode or result.failure or not containers:
            raise ContainerUnavailable("skillsbench_evolution_environment_missing")
        states = []
        for identifier in containers:
            if not re.fullmatch(r"[0-9a-f]{64}", identifier):
                raise ContainerUnavailable("skillsbench_evolution_container_identity_invalid")
            probe = self.transport.run(
                [
                    "docker",
                    "inspect",
                    "--format",
                    '{"id":{{json .Id}},"name":{{json .Name}},'
                    '"service":{{json (index .Config.Labels "com.docker.compose.service")}},'
                    '"started_at":{{json .State.StartedAt}},'
                    '"restart_count":{{json .RestartCount}},"running":{{json .State.Running}},'
                    '"status":{{json .State.Status}},"exit_code":{{json .State.ExitCode}},'
                    '"health":{{with (index .State "Health")}}{{json .Status}}'
                    "{{else}}null{{end}}}",
                    identifier,
                ],
                stdin=b"",
                timeout=10,
                output_limit=65536,
                env=_host_environment(),
            )
            try:
                state = json.loads(probe.stdout)
            except (ValueError, UnicodeError):
                state = {}
            if (
                probe.returncode
                or probe.failure
                or state.get("id") != identifier
                or not isinstance(state.get("started_at"), str)
                or not state["started_at"]
                or isinstance(state.get("restart_count"), bool)
                or not isinstance(state.get("restart_count"), int)
                or state["restart_count"] < 0
                or state.get("service") not in services
                or not isinstance(state.get("name"), str)
                or not state["name"]
                or not (
                    state.get("running") is True
                    or (state.get("status") == "exited" and state.get("exit_code") == 0)
                )
            ):
                raise ContainerUnavailable("skillsbench_evolution_environment_missing")
            for condition in requirements.get(state["service"], ()):
                valid = {
                    "service_started": state.get("running") is True,
                    "service_healthy": state.get("running") is True
                    and state.get("health") == "healthy",
                    "service_completed_successfully": state.get("running") is False
                    and state.get("status") == "exited"
                    and state.get("exit_code") == 0,
                }
                if not valid.get(condition, False):
                    raise ContainerUnavailable("skillsbench_evolution_service_not_ready")
            if (
                state["service"] == "main"
                and (service_health := services["main"].get("healthcheck"))
                and not service_health.get("disable", False)
                and state.get("health") != "healthy"
            ):
                raise ContainerUnavailable("skillsbench_evolution_service_not_ready")
            states.append(state)
        if {state["service"] for state in states} != set(services) or len(states) != len(services):
            raise ContainerUnavailable("skillsbench_evolution_environment_missing")
        return states

    @contextmanager
    def episode(self, bundle: Any) -> Iterator[SkillEpisode]:
        if self.use_bwrap:
            self._validate_workspace()
        else:
            self._docker_lock()
        with _episode(self, bundle) as episode:
            layout = self.source.task(self.task_id)["environment"]
            if self.use_bwrap:
                if layout["workdir"] != self.workspace_directory:
                    raise ContainerUnavailable("skillsbench_demo_layout_not_prepared")
                for entry in self.source.task(self.task_id)["public_input_manifest"]:
                    for destination in entry["sandbox_paths"]:
                        prefix = self.workspace_directory + "/"
                        if not destination.startswith(prefix):
                            raise ContainerUnavailable("skillsbench_demo_layout_not_prepared")
                        target = episode.work / _safe_path(destination.removeprefix(prefix))
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(self.task_directory / entry["relative_path"], target)
                        if self.demo:
                            target.chmod(0o444)
            try:
                if not self.use_bwrap:
                    self.workspace_roots = tuple(layout["workspace_roots"])
                    self._start_episode(episode)
                else:
                    self.public_open = True
                    self.private_grade_started = False
                    if self.runtime == "workspace":
                        self._guard_public_episode(episode)
                        result = self._raw(
                            episode.package,
                            episode.work,
                            [
                                "/usr/local/bin/python",
                                "-m",
                                "venv",
                                "--without-pip",
                                "--system-site-packages",
                                "/root/.venv",
                            ],
                        )
                        if result.returncode or result.failure:
                            raise ContainerUnavailable("skillsbench_workspace_venv_creation_failed")
                        for name in ("pip", "pip3"):
                            script = episode.work / ".venv/bin" / name
                            script.write_text(
                                '#!/bin/bash\nexec /root/.venv/bin/python -m pip "$@"\n'
                            )
                            script.chmod(0o755)
                yield episode
            finally:
                try:
                    if not self.use_bwrap:
                        self._stop_episode()
                except Exception:
                    episode.cleanup_failed = True
                    raise
                finally:
                    self.public_open = False
                    self.workspace_roots = ()

    def _docker_lock(self) -> dict[str, Any]:
        value = json.loads(self.runtime_lock_path.read_text())
        compose = self.task_directory / "environment/docker-compose.yaml"
        tests = self.task_directory / "tests"
        expected = {
            "runtime_schema": _EPISODE_SCHEMA,
            "commit": COMMIT,
            "task_id": self.task_id,
            "dockerfile_sha256": _hash(self.task_directory / "environment/Dockerfile"),
            "compose_sha256": _hash(compose) if compose.exists() else None,
            "task_config_hash": _json_hash(self.config),
            "public_manifest_hash": self.source.manifest["manifest_hash"],
            "dependency_hash": _hash(self.root / "runtime/skillsbench-verifier-requirements.lock"),
            "resources": self.config["environment"],
            "layout": self.source.manifest["environments"][self.task_id],
            "services": _compose_definition(self.task_directory),
            "grader_tests_hash": _json_hash(
                {
                    p.relative_to(tests).as_posix(): _hash(p)
                    for p in sorted(tests.rglob("*"))
                    if p.is_file()
                }
            ),
        }
        if any(value.get(k) != v for k, v in expected.items()) or set(value.get("images", {})) != {
            "environment",
            "runtime",
        }:
            raise ContainerUnavailable("skillsbench_episode_runtime_not_prepared")
        mode = value.get("verifier_python_mode")
        if mode not in {"native", "standalone"} or value["images"]["runtime"].get(
            "verifier_python"
        ) != (_NATIVE_PYTHON if mode == "native" else _STANDALONE_PYTHON):
            raise ContainerUnavailable("skillsbench_verifier_runtime_not_prepared")
        if set(value.get("service_images", {})) != set(value["services"]["services"]):
            raise ContainerUnavailable("skillsbench_service_images_not_prepared")
        main = value["service_images"]["main"]
        if "public_python" in main:
            interpreter, version = main["public_python"], main.get("public_python_version")
            if (
                not isinstance(interpreter, str)
                or not interpreter.startswith("/")
                or "\x00" in interpreter
                or ".." in Path(interpreter).parts
                or not isinstance(version, list)
                or len(version) != 3
                or any(type(part) is not int for part in version)
                or version[0] != 3
            ):
                raise ContainerUnavailable("skillsbench_public_python_not_prepared")
            if main.get("source_digest") is not None and (
                main["source_digest"] != value["images"]["environment"]["digest"]
                or mode != "standalone"
                or interpreter != _STANDALONE_PYTHON
                or version != value["images"]["runtime"].get("verifier_python_version")
                or any(
                    main.get(field) != value["images"]["environment"].get(field)
                    for field in ("environment", "user", "workdir", "entrypoint")
                )
            ):
                raise ContainerUnavailable("skillsbench_public_python_source_changed")
        for image in [*value["images"].values(), *value["service_images"].values()]:
            if not re.fullmatch(r"sha256:[0-9a-f]{64}", image.get("digest", "")):
                raise ContainerUnavailable("skillsbench_image_digest_not_prepared")
            result = self.transport.run(
                ["docker", "image", "inspect", image["digest"]],
                stdin=b"",
                timeout=10,
                output_limit=65536,
                env=_host_environment(),
            )
            if result.returncode or result.failure:
                raise ContainerUnavailable("skillsbench_locked_image_missing")
            try:
                inspected = json.loads(result.stdout)
            except (ValueError, UnicodeError) as exc:
                raise ContainerUnavailable("skillsbench_locked_image_identity_invalid") from exc
            if (
                not isinstance(inspected, list)
                or len(inspected) != 1
                or not isinstance(inspected[0], dict)
                or inspected[0].get("Id") != image["digest"]
            ):
                raise ContainerUnavailable("skillsbench_locked_image_identity_invalid")
        return value

    def _official_report_name(self) -> str:
        """Bind the released grader's two report contracts without interpreting shell."""
        script = (self.task_directory / "tests/test.sh").read_text()
        names = set()
        for argument in re.findall(r"--ctrf(?:=|\s+)([^\s]+)", script):
            argument = argument.strip("\"'")
            if ".." in Path(argument).parts:
                raise ValueError("skillsbench_official_report_path_invalid")
            if argument.startswith("/logs/verifier/"):
                name = argument.removeprefix("/logs/verifier/")
                if name not in {"ctrf.json", "ctrf-report.json"}:
                    raise ValueError("skillsbench_official_report_path_invalid")
                names.add(name)
            elif argument == "ctrf.json" or argument.startswith("$"):
                # Released variable and relative forms write the original ctrf.json.
                names.add("ctrf.json")
            else:
                raise ValueError("skillsbench_official_report_path_invalid")
        if len(names) > 1:
            raise ValueError("skillsbench_official_report_declarations_ambiguous")
        return next(iter(names), "ctrf.json")

    def _seal_grader_output(
        self, episode: SkillEpisode, logs: Path, result: ProcessResult
    ) -> tuple[Path, dict[str, Any]]:
        """Preserve private scoring evidence before the temporary episode is removed."""
        directory = Path(
            getattr(
                episode,
                "grader_evidence_dir",
                self.source.root
                / "data/skillsbench/private-grades"
                / self.task_id
                / uuid.uuid4().hex,
            )
        )
        directory.mkdir(mode=0o700, parents=True, exist_ok=False)
        directory.chmod(0o700)
        files = {}
        contents = {"stdout.bin": result.stdout, "stderr.bin": result.stderr}
        for name in ("reward.txt", "ctrf.json", "ctrf-report.json"):
            path = logs / name
            if path.is_file() and not path.is_symlink():
                contents[name] = path.read_bytes()
        for name, content in contents.items():
            descriptor, temporary = tempfile.mkstemp(prefix=f".{name}.", dir=directory)
            try:
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, directory / name)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            files[name] = {"sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content)}
        evidence = {
            "schema": "skillsbench.official-grader-evidence.v1",
            "task_id": self.task_id,
            "identity": getattr(episode, "grader_identity", {}),
            "grader_exit_code": result.returncode,
            "process_failure": result.failure,
            "output_capture": {
                "scope": "captured_process_output",
                "combined_limit_bytes": _GRADER_OUTPUT_LIMIT,
                "limit_exceeded": result.failure == "output_limit",
            },
            "files": files,
        }
        atomic_json(directory / "capture.json", evidence)
        return directory, evidence

    def grade(self, episode: SkillEpisode) -> dict[str, Any]:
        if not self.use_bwrap or self.runtime == "workspace":
            if self.public_open:
                raise PermissionError("skillsbench_private_grade_before_public_close")
            if not self.use_bwrap and self.container_name is None:
                raise ContainerUnavailable("skillsbench_episode_not_started")
            if self.private_grade_started:
                raise PermissionError("skillsbench_private_grade_already_started")
            self.private_grade_started = True
        logs = episode.work.parent / "grader-logs"
        logs.mkdir(mode=0o777, exist_ok=True)
        logs.chmod(0o777)
        for old in logs.iterdir():
            if old.is_dir() and not old.is_symlink():
                shutil.rmtree(old)
            else:
                old.unlink()
        empty = episode.work.parent / "grader-package"
        empty.mkdir(exist_ok=True)
        deliverables: list[str] = []
        self.grader_diagnostics = None
        self.grader_probe_context = None
        if self.use_bwrap:
            if self.runtime == "workspace" and self.task_id in _WORKSPACE_TEST_SCRIPT_SHA256:
                self._lock().validate(self.task_id)
                _, bootstrap = _workspace_grader_script(self.root, self.task_id)
                path = episode.work.parent / "grader-bootstrap.sh"
                path.write_text(bootstrap)
                path.chmod(0o444)
            result = self._raw(empty, episode.work, ["/bin/bash", "/tests/test.sh"], grader=True)
        else:
            if self.public_open:
                raise PermissionError("skillsbench_private_grade_before_public_close")
            if self.container_name is None:
                raise ContainerUnavailable("skillsbench_episode_not_started")
            settings = _resolve_environment(
                self.config["verifier"].get("env", {}), task_id=self.task_id
            )
            copied = self.transport.run(
                [
                    "docker",
                    "cp",
                    str(self.task_directory / "tests") + "/.",
                    self.container_name + ":/tests",
                ],
                stdin=b"",
                timeout=60,
                output_limit=self.output_limit,
                env=_host_environment(),
            )
            if copied.returncode or copied.failure:
                result = ProcessResult(
                    copied.returncode, copied.stdout, copied.stderr, "official_tests_upload_failed"
                )
            else:
                result = self._exec(
                    ["/bin/bash", "/tests/test.sh"], public=False, environment=settings
                )
        evidence_directory, evidence = self._seal_grader_output(episode, logs, result)
        data = None

        def finish(verdict: dict[str, Any]) -> dict[str, Any]:
            results = data.get("results", {}) if isinstance(data, dict) else {}
            checks = results.get("tests", []) if isinstance(results, dict) else []
            items = (
                [{"name": item.get("name"), "status": item.get("status")} for item in checks]
                if isinstance(checks, list) and all(isinstance(item, dict) for item in checks)
                else []
            )
            atomic_json(
                evidence_directory / "evidence.json",
                {**evidence, "verdict": verdict, "official_items": items},
            )
            return verdict

        reward = evidence_directory / "reward.txt"
        if result.failure or not reward.is_file() or reward.is_symlink():
            return finish(
                {
                    "utility": None,
                    "reward": None,
                    "status": "NOT_MEASURED",
                    "failure": result.failure or "official_reward_missing",
                    "official_checks": None,
                }
            )
        try:
            measured = float(reward.read_text().strip())
        except ValueError:
            return finish(
                {
                    "utility": None,
                    "reward": None,
                    "status": "NOT_MEASURED",
                    "failure": "official_reward_invalid",
                    "official_checks": None,
                }
            )
        if not math.isfinite(measured) or not 0 <= measured <= 1:
            return finish(
                {
                    "utility": None,
                    "reward": None,
                    "status": "NOT_MEASURED",
                    "failure": "official_reward_invalid",
                    "official_checks": None,
                }
            )
        checks = None
        # Grader output never reaches a model; a bounded tail is kept only for preflight's
        # re-validation and for the classification of missing agent deliverables.
        self.grader_diagnostics = (
            (result.stdout + result.stderr)[-_GRADER_DIAGNOSTICS_LIMIT:]
        ).decode("utf-8", "replace")
        try:
            name = self._official_report_name()
            if all(
                (evidence_directory / file).is_file() for file in ("ctrf.json", "ctrf-report.json")
            ):
                raise ValueError("skillsbench_official_report_files_ambiguous")
            report = evidence_directory / name
            evidence["official_report"] = {
                "file": name,
                "sandbox_path": "/logs/verifier/" + name,
                "script_sha256": _hash(self.task_directory / "tests/test.sh"),
            }
            data = (
                json.loads(report.read_text())
                if report.is_file() and not report.is_symlink()
                else None
            )
            self.grader_probe_context = {
                "exit_code": result.returncode,
                "reward": measured,
                "report": data,
            }
            public = self.source.task(self.task_id)
            candidate_modules = sorted(
                set(
                    re.findall(r"\b([A-Za-z_]\w*)\.py\b", public["opening"])
                    + [
                        Path(entry["relative_path"]).stem
                        for entry in public["public_input_manifest"]
                        if entry["relative_path"].endswith(".py")
                    ]
                )
            )
            deliverables = _deliverable_modules(
                self.grader_diagnostics, self.task_directory / "tests", candidate_modules
            )
            _validate_grader_warmup(
                result.returncode,
                str(measured),
                data,
                self.grader_diagnostics,
                deliverables,
                error_output=result.stderr.decode("utf-8", "replace"),
                candidate_modules=candidate_modules,
                candidate_roots=public["environment"]["workspace_roots"],
            )
        except (RuntimeError, ValueError, TypeError, AttributeError) as exc:
            return finish(
                {
                    "utility": None,
                    "reward": None,
                    "status": "NOT_MEASURED",
                    "failure": "official_grader_program_error",
                    "grader_failure": str(exc).splitlines()[0],
                    "official_checks": None,
                }
            )
        if data is not None:
            summary = data.get("results", {}).get("summary", {})
            total = summary.get("tests")
            if isinstance(total, int) and total > 0:
                checks = {
                    "status": "MEASURED",
                    "source": "pytest-json-ctrf.summary",
                    "unit": "reporter_group",
                    "passed": summary.get("passed"),
                    "total": total,
                    "rate": summary.get("passed", 0) / total,
                }
        if checks is None:
            checks = {
                "status": "NOT_MEASURED",
                "source": None,
                "unit": None,
                "passed": None,
                "total": None,
                "rate": None,
            }
        return finish(
            {
                "status": "MEASURED",
                "utility": measured == 1,
                "reward": measured,
                "official_checks": checks,
                "grader_exit_code": result.returncode,
            }
        )

    def _deferred_task_setup(self, grade: Mapping[str, Any]) -> dict[str, Any] | None:
        """An empty probe cannot require dependencies the public task asks an agent to install.

        This is admission evidence, never a replacement for a measured official grade.
        Require an actual collection failure and public source imports, rather than
        accepting arbitrary missing grader dependencies or guessing from task names.
        """
        context = getattr(self, "grader_probe_context", None)
        if (
            grade.get("failure") != "official_grader_program_error"
            or grade.get("grader_failure") != "skillsbench_warmup_dependency_or_collection_error"
            or not isinstance(context, dict)
            or context["exit_code"] not in {0, 1}
            or context["reward"] != 0
        ):
            return None
        report = context["report"]
        if not isinstance(report, dict) or not isinstance(report.get("results"), dict):
            return None
        results = report["results"]
        summary = results.get("summary")
        if (
            not isinstance(summary, dict)
            or type(summary.get("tests")) is not int
            or summary["tests"] != 0
            or type(summary.get("passed")) is not int
            or summary["passed"] != 0
            or results.get("tests") != []
            or any(
                type(summary.get(name, 0)) is not int or summary.get(name, 0) < 0
                for name in ("failed", "skipped", "pending", "other", "errors")
            )
            or any(summary.get(name, 0) != 0 for name in ("failed", "skipped", "pending", "other"))
        ):
            return None
        diagnostics = self.grader_diagnostics or ""
        if not re.search(r"(?:^|\n)\s*(?:_+\s*)?ERROR collecting\b", diagnostics):
            return None
        errors = _grader_errors(diagnostics)
        public = self.source.task(self.task_id)
        requirement = re.search(
            r"\b(?:set\s*up|setup|install|configure|prepare|create)\b[^\n.!?]{0,180}"
            r"\b(?:environment|dependencies|packages|requirements|virtualenv|venv)\b",
            public["opening"],
            re.IGNORECASE,
        )
        if not requirement or not errors:
            return None
        modules = set()
        roots = ["/tests", *public["environment"]["workspace_roots"]]
        for kind, frame, detail in errors:
            missing = _missing_modules(detail)
            if (
                kind != "ModuleNotFoundError"
                or not missing
                or not frame
                or not any(frame.startswith(root.rstrip("/") + "/") for root in roots)
                or any(part in {"site-packages", ".venv"} for part in Path(frame).parts)
            ):
                return None
            modules.update(missing)
        evidence = {}
        for entry in public["public_input_manifest"]:
            if not entry["relative_path"].endswith(".py") or not entry["sandbox_paths"]:
                continue
            path = self.task_directory / _safe_path(entry["relative_path"])
            if path.is_symlink() or _hash(path) != entry["sha256"]:
                return None
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeError):
                continue
            imported = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    imported.add(node.module.split(".")[0])
            for module in modules & imported:
                evidence.setdefault(module, []).append(
                    {"path": entry["relative_path"], "sha256": entry["sha256"]}
                )
        if set(evidence) != modules:
            return None
        return {"public_requirement": requirement.group(), "public_import_evidence": evidence}

    def _record_grader_probe(self, checks: dict[str, Any], grade: Mapping[str, Any]) -> None:
        measured = grade.get("status") == "MEASURED"
        deferred = None if measured else self._deferred_task_setup(grade)
        checks["official_grader"] = measured
        checks["official_grader_admission"] = measured or deferred is not None
        checks["official_grader_probe"] = {
            "purpose": "runtime_admission",
            "experiment_measurement": False,
            "status": "PASSED" if measured else "DEFERRED_TASK_SETUP" if deferred else "FAILED",
        }
        if not measured:
            checks["official_grader_error"] = grade.get("failure", "official_grader_not_measured")
        if deferred:
            checks["official_grader_probe"].update(deferred)

    def _public_artifacts(self, trace: Mapping[str, Any]) -> Path:
        path = Path(trace["public_artifacts_dir"]).resolve(strict=True)
        manifest = json.loads((path.parent / "snapshot.json").read_text())
        expected = {x["path"]: x["sha256"] for x in manifest["files"]}
        actual, directories, links = {}, [], []
        roots = tuple("/" + p.name for p in path.iterdir() if not p.is_symlink())
        for file in path.rglob("*"):
            relative = file.relative_to(path).as_posix()
            if file.is_symlink():
                target = os.readlink(file)
                if not _public_link_target(relative, target, roots):
                    raise ValueError("skillsbench_public_snapshot_symlink")
                links.append({"path": relative, "target": target})
            elif file.is_file():
                actual[relative] = _hash(file)
            elif file.is_dir():
                directories.append(relative)
            else:
                raise ValueError("skillsbench_public_snapshot_special_file")
        content = (
            {"files": manifest["files"], "directories": sorted(directories)}
            if "directories" in manifest
            else manifest["files"]
        )
        if "symlinks" in manifest:
            content["symlinks"] = sorted(links, key=lambda entry: entry["path"])
        elif links:
            raise ValueError("skillsbench_public_snapshot_symlink")
        if (
            actual != expected
            or any(
                entry.get("mode", (path / entry["path"]).stat().st_mode & 0o777)
                != (path / entry["path"]).stat().st_mode & 0o777
                for entry in manifest["files"]
                if entry["path"] in actual
            )
            or _json_hash(content) != manifest["snapshot_hash"]
            or manifest["snapshot_hash"] != trace["public_artifacts_hash"]
        ):
            raise ValueError("skillsbench_public_snapshot_corrupt")
        return path

    def _public_terminal(self, package: Path, work: Path, command: str) -> ProgramResult:
        return _program_result(self._raw(package, work, ["/bin/bash", "-c", command]), raw=True)

    @contextmanager
    def public_verifier_session(
        self,
        public_inputs: Mapping[str, Any],
        base: Any,
        trace: Mapping[str, Any],
        files: Mapping[str, str] | None = None,
        readonly_tests: bool = False,
        *,
        workspace: Path | None = None,
    ) -> Iterator[Any]:
        path = self._public_artifacts(trace)
        before = trace["public_artifacts_hash"]
        self.verifier_artifacts = path
        self.public_workspace_mode = True
        try:
            with _public_workspace(
                self,
                public_inputs,
                base,
                trace=trace,
                test_files=files,
                readonly_tests=readonly_tests,
                workspace=workspace,
                terminal_callback=self._public_terminal,
            ) as session:
                yield session
            if self._public_artifacts(trace) != path or before != trace["public_artifacts_hash"]:
                raise ValueError("skillsbench_public_snapshot_changed")
        finally:
            self.verifier_artifacts = None
            self.public_workspace_mode = False

    def run_verifier(
        self,
        public_inputs: Mapping[str, Any],
        frozen_base: Mapping[str, Any],
        trace: Mapping[str, Any],
        test_files: Mapping[str, str],
    ) -> ProgramResult:
        self.verifier_artifacts = self._public_artifacts(trace)
        previous_mode = self.public_workspace_mode
        self.public_workspace_mode = True
        try:
            return _run_verifier(
                self,
                public_inputs,
                frozen_base,
                {k: v for k, v in trace.items() if k != "public_artifacts_dir"},
                test_files,
            )
        finally:
            self.verifier_artifacts = None
            self.public_workspace_mode = previous_mode

    def _codex_admission(
        self, episode: SkillEpisode, settings: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Check native agent dependencies in MAIN, without a provider or model call."""
        from .codex_runtime import codex_identity

        identity = codex_identity(settings)
        interpreter = self.public_python
        probe = self._run(
            episode.package,
            episode.work,
            [
                "/bin/bash",
                "-c",
                "python=false; session=false; command -v "
                + shlex.quote(interpreter)
                + " >/dev/null && python=true; "
                "command -v setsid >/dev/null && session=true; "
                'printf \'{"python3":%s,"setsid":%s}\\n\' "$python" "$session"',
            ],
        )
        result = {
            "python3": False,
            "setsid": False,
            "native_cli_abi": False,
            "cli_version": None,
            "expected_cli_version": identity["cli_version"],
            "cli_sha256": identity["cli_sha256"],
            "public_python": interpreter,
            "code_mode_host_abi": None,
            "official_task_user": True,
            "model_calls": 0,
            "ready": False,
        }
        if probe.failure or probe.exit_code or not isinstance(probe.output, dict):
            result["error"] = "codex_main_dependency_probe_failed"
            return result
        result.update(
            python3=probe.output.get("python3") is True, setsid=probe.output.get("setsid") is True
        )
        if not result["python3"] or not result["setsid"]:
            result["error"] = "codex_main_runtime_dependency_missing"
            return result
        destination = "/tmp/tau-codex-admission"
        commands = [
            ["docker", "cp", identity["binary"], self.container_name + ":" + destination],
            ["docker", "exec", "--user", "root", self.container_name, "chmod", "0755", destination],
        ]
        companion = identity.get("code_mode_host_binary")
        companion_destination = "/tmp/codex-code-mode-host"
        if companion is not None:
            result["code_mode_host_sha256"] = identity["code_mode_host_sha256"]
            commands += [
                ["docker", "cp", companion, self.container_name + ":" + companion_destination],
                [
                    "docker",
                    "exec",
                    "--user",
                    "root",
                    self.container_name,
                    "chmod",
                    "0755",
                    companion_destination,
                ],
            ]
        for command in commands:
            staged = self.transport.run(
                command, stdin=b"", timeout=60, output_limit=65536, env=_host_environment()
            )
            if staged.returncode or staged.failure:
                result["error"] = "codex_main_binary_staging_failed"
                return result
        code = (
            "import json,subprocess; "
            "\ntry:"
            f"\n p=subprocess.run([{destination!r},'--version'],capture_output=True,text=True);"
            "\n print(json.dumps({'return_code':p.returncode,'version':p.stdout.strip()}))"
            "\nexcept OSError: print(json.dumps({'return_code':-1,'version':None}))"
        )
        version = self._run(episode.package, episode.work, [interpreter, "-I", "-c", code])
        observed = version.output if isinstance(version.output, dict) else {}
        result["cli_version"] = observed.get("version")
        result["native_cli_abi"] = (
            version.failure is None
            and version.exit_code == 0
            and observed.get("return_code") == 0
            and observed.get("version") == identity["cli_version"]
        )
        if companion is not None:
            code = (
                "import json,subprocess; "
                "\ntry:"
                f"\n p=subprocess.run([{companion_destination!r},'--help'],capture_output=True);"
                "\n print(json.dumps({'return_code':p.returncode}))"
                "\nexcept OSError: print(json.dumps({'return_code':-1}))"
            )
            companion_probe = self._run(
                episode.package, episode.work, [interpreter, "-I", "-c", code]
            )
            observed_companion = (
                companion_probe.output if isinstance(companion_probe.output, dict) else {}
            )
            result["code_mode_host_abi"] = (
                companion_probe.failure is None
                and companion_probe.exit_code == 0
                and observed_companion.get("return_code") == 0
            )
        result["ready"] = result["native_cli_abi"] and result["code_mode_host_abi"] is not False
        if not result["ready"]:
            result["error"] = "codex_main_binary_not_compatible"
        return result

    def preflight(
        self, *, validate_source: bool = True, author_codex: Mapping[str, Any] | None = None
    ) -> dict[str, Any]:
        checks: dict[str, Any] = {
            "demo_only": self.demo,
            "runtime": self.runtime,
            "aggregate_limits_enforced": False,
            "main_cpu_memory_limits_configured": False,
            "resources_scope": "workspace_process" if self.use_bwrap else "main_container",
            "storage_limit_enforced": False,
            "sidecar_limits_enforced": False,
            "ready": False,
            "runtime_lock_path": str(self.runtime_lock_path),
        }
        try:
            if author_codex is not None and self.use_bwrap:
                raise ContainerUnavailable("author_codex_requires_docker")
            if validate_source:
                self.source.validate()
            checks["source"] = True
            if self.use_bwrap:
                if self.runtime == "workspace":
                    checks["preparation"] = workspace_preparation(
                        self.root, self.task_id, runtime_lock_path=self.runtime_lock_path
                    )
                    checks["isolation"] = "bubblewrap"
                    checks["network"] = "none"
                    checks["per_episode_venv"] = True
                    checks["persistent_background_services"] = False
                    checks["author_environment_equivalent"] = False
                    checks["method_adaptation"] = (
                        "task_public_inputs_and_pinned_python_dependencies_in_fresh_workspace"
                    )
                    if self.task_id in _WORKSPACE_TEST_SCRIPT_SHA256:
                        checks["grader_bootstrap"] = self._lock().value.get("grader_bootstrap")
                    if not checks["preparation"]["supported"]:
                        checks["error"] = checks["preparation"]["reason"]
                        return checks
                self._validate_workspace()
                checks["commands"] = all(shutil.which(x) for x in ("bwrap", "prlimit", "taskset"))
            else:
                checks["commands"] = shutil.which("docker") is not None
                if not checks["commands"]:
                    return checks
                for name, command in (
                    ("docker_daemon", ["docker", "info"]),
                    ("docker_compose", ["docker", "compose", "version"]),
                ):
                    probe = self.transport.run(
                        command, stdin=b"", timeout=10, output_limit=65536, env=_host_environment()
                    )
                    checks[name] = probe.returncode == 0 and probe.failure is None
                    if not checks[name]:
                        return checks
                lock = self._docker_lock()
                required = self.config["verifier"].get("env", {})
                checks["required_environment_missing"] = _missing_environment(
                    required, task_id=self.task_id
                )
                declared_main = self.config["environment"].get("env", {})
                checks["compose_optional_environment_missing"] = {
                    name: missing
                    for name, settings in lock["services"]["services"].items()
                    if (
                        missing := _missing_environment(
                            {
                                **(declared_main if name == "main" else {}),
                                **settings.get("environment", {}),
                            },
                            task_id=self.task_id,
                        )
                    )
                }
                if checks["required_environment_missing"]:
                    checks["error"] = "skillsbench_required_environment_missing"
                    return checks
                _resolve_environment(required, task_id=self.task_id)
                checks["effective_resources"] = self.config["environment"]
            checks["runtime_lock"] = True
            if not checks["commands"]:
                return checks
            from .artifacts import SkillBundle

            with self.episode(
                SkillBundle({"SKILL.md": "Runtime admission probe; no model execution."})
            ) as episode:
                if author_codex is not None:
                    checks["author_codex_runtime"] = self._codex_admission(episode, author_codex)
                code = "import json,sys; print(json.dumps(list(sys.version_info[:3])))"
                if self.use_bwrap:
                    code = (
                        "import json,sys,importlib.metadata as m; "
                        "print(json.dumps({'python':list(sys.version_info[:3]),"
                        "'dependencies':{n:m.version(n) for n in "
                        "('numpy','pandas','pytest','pytest-json-ctrf','pip')}}))"
                    )
                    result = self._run(episode.package, episode.work, ["python", "-I", "-c", code])
                    checks["dependencies"] = result.failure is None and result.output == {
                        "python": [3, 11, 14],
                        "dependencies": self._lock().value["dependencies"],
                    }
                    if self.runtime == "workspace":
                        from .skillsbench import SkillsBenchAdapter

                        admission = SkillsBenchAdapter.__new__(SkillsBenchAdapter)
                        admission.runner = self
                        admission.artifact_root = episode.work.parent / "preflight-public"
                        public = admission._snapshot(episode)
                        self.verifier_artifacts = self._public_artifacts(public)
                        checks["public_snapshot"] = True
                        try:
                            verifier = self._run(
                                episode.package,
                                episode.work,
                                [
                                    "python",
                                    "-I",
                                    "-c",
                                    "import json,pytest; "
                                    "print(json.dumps({'pytest':pytest.__version__}))",
                                ],
                            )
                        finally:
                            self.verifier_artifacts = None
                        checks["verifier_dependencies"] = (
                            verifier.output == {"pytest": "8.4.1"} and verifier.failure is None
                        )
                        self.close_public(episode)
                        grade = self.grade(episode)
                        self._record_grader_probe(checks, grade)
                else:
                    checks["main_cpu_memory_limits_configured"] = True
                    result = self._run(
                        episode.package,
                        episode.work,
                        [
                            "/bin/bash",
                            "-c",
                            "if command -v python3 >/dev/null 2>&1; "
                            f"then exec python3 -I -c '{code}'; fi; echo null",
                        ],
                    )
                    checks["task_python"] = result.output
                    checks["dependencies"] = result.failure is None and result.exit_code == 0
                    from .skillsbench import SkillsBenchAdapter

                    admission = SkillsBenchAdapter.__new__(SkillsBenchAdapter)
                    admission.demo, admission.runner = False, self
                    admission.artifact_root = episode.work.parent / "preflight-public"
                    public = admission._snapshot(episode)
                    self.verifier_artifacts = self._public_artifacts(public)
                    checks["public_snapshot"] = True
                    try:
                        verifier = self._run(
                            episode.package,
                            episode.work,
                            [
                                "python",
                                "-I",
                                "-c",
                                "import json,pytest,importlib.metadata as m; "
                                "print(json.dumps({'pytest':m.version('pytest'),"
                                "'pytest-json-ctrf':m.version('pytest-json-ctrf')}))",
                            ],
                        )
                    finally:
                        self.verifier_artifacts = None
                    checks["verifier_dependencies"] = (
                        verifier.failure is None
                        and verifier.output == {"pytest": "8.4.1", "pytest-json-ctrf": "0.3.5"}
                    )
                    self.close_public(episode)
                    grade = self.grade(episode)
                    self._record_grader_probe(checks, grade)
            checks["ready"] = (
                checks["dependencies"]
                and checks.get("verifier_dependencies", True)
                and checks.get("official_grader_admission", True)
                and checks.get("author_codex_runtime", {}).get("ready", author_codex is None)
            )
        except (OSError, ValueError, RuntimeError) as exc:
            checks["error"] = str(exc)
        return checks
