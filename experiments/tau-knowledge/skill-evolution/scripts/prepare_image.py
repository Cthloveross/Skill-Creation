#!/usr/bin/env python3
"""Build and verify the bank sandbox using a real, immutable Python base."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

from tau_skill_evolution.artifacts import atomic_json
from tau_skill_evolution.container import PINNED_DEPENDENCIES, ImageLock


def prepare_image(runtime: Path) -> dict:
    path = runtime / "image-lock.json"
    lock = json.loads(path.read_text())
    requirements = runtime / "requirements.lock"
    dependency_hash = hashlib.sha256(requirements.read_bytes()).hexdigest()
    dockerfile_hash = hashlib.sha256((runtime / "Dockerfile").read_bytes()).hexdigest()
    ImageLock(lock["image"], None, dependency_hash, requirements).validate_dependencies()
    env = {
        name: os.environ[name]
        for name in ("PATH", "HOME", "DOCKER_HOST", "DOCKER_CONTEXT", "XDG_RUNTIME_DIR")
        if name in os.environ
    }
    base_image = lock.get("base_image", "python:3.11-slim")
    source = lock.get("base_digest") or base_image
    subprocess.run(["docker", "pull", "--platform", "linux/amd64", source], check=True, env=env)
    inspected = json.loads(
        subprocess.check_output(
            ["docker", "image", "inspect", source],
            text=True,
            env=env,
        )
    )[0]
    digests = inspected.get("RepoDigests") or []
    base_digest = source if source in digests else next(iter(digests), None)
    if not isinstance(base_digest, str) or not re.fullmatch(
        r"[A-Za-z0-9/_.:\-]+@sha256:[0-9a-f]{64}", base_digest
    ):
        raise RuntimeError("python_base_repository_digest_missing")
    subprocess.run(
        [
            "docker",
            "buildx",
            "build",
            "--load",
            "--platform",
            "linux/amd64",
            "--tag",
            lock["image"],
            "--build-arg",
            "PYTHON_BASE=" + base_digest,
            str(runtime),
        ],
        check=True,
        env=env,
    )
    image = json.loads(
        subprocess.check_output(
            ["docker", "image", "inspect", lock["image"]],
            text=True,
            env=env,
        )
    )[0]
    digest = image.get("Id")
    if not isinstance(digest, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise RuntimeError("built_image_id_missing")
    verification = json.loads(
        subprocess.check_output(
            [
                "docker",
                "run",
                "--rm",
                "--pull",
                "never",
                "--network",
                "none",
                "--read-only",
                "--cpus",
                "1",
                "--memory",
                "1g",
                "--memory-swap",
                "1g",
                "--pids-limit",
                "64",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                digest,
                "python",
                "-c",
                "import json,platform,numpy,pandas,pytest;"
                "print(json.dumps({'python':platform.python_version(),'dependencies':"
                "{'numpy':numpy.__version__,'pandas':pandas.__version__,'pytest':pytest.__version__}}))",
            ],
            text=True,
            env=env,
        )
    )
    if not verification["python"].startswith("3.11.") or (
        verification["dependencies"] != PINNED_DEPENDENCIES
    ):
        raise RuntimeError("built_image_runtime_versions_differ")
    if dependency_hash != hashlib.sha256(requirements.read_bytes()).hexdigest() or (
        dockerfile_hash != hashlib.sha256((runtime / "Dockerfile").read_bytes()).hexdigest()
    ):
        raise RuntimeError("image_build_inputs_changed")
    lock.update(
        digest=digest,
        digest_kind="image_id",
        dependency_hash=dependency_hash,
        base_image=base_image,
        base_digest=base_digest,
        dockerfile_hash=dockerfile_hash,
        platform="linux/amd64",
        python_version=verification["python"],
        dependencies=verification["dependencies"],
    )
    atomic_json(path, lock)
    return lock


if __name__ == "__main__":
    runtime = Path(__file__).resolve().parent.parent / "runtime"
    print(json.dumps(prepare_image(runtime), indent=2))
