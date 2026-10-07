"""Preparation failures never publish an unverified bank image lock."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess

import pytest
from tau_skill_evolution.constants import EXPERIMENT_ROOT
from tau_skill_evolution.container import PINNED_DEPENDENCIES

BASE = "python@sha256:" + "a" * 64
IMAGE = "sha256:" + "b" * 64


@pytest.fixture
def builder(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "tau_prepare_image", EXPERIMENT_ROOT / "scripts/prepare_image.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    (tmp_path / "Dockerfile").write_text("ARG PYTHON_BASE\nFROM ${PYTHON_BASE}\n")
    (tmp_path / "requirements.lock").write_text(
        "\n".join(
            f"{name}=={version} --hash=sha256:{'c' * 64}"
            for name, version in PINNED_DEPENDENCIES.items()
        )
    )
    lock = tmp_path / "image-lock.json"
    lock.write_text(json.dumps({"image": "fixture:python311", "digest": "old-image"}))
    original = lock.read_bytes()
    calls = []
    behavior = {
        "build_failure": False,
        "digests": [BASE],
        "change_sources": False,
        "dependencies": dict(PINNED_DEPENDENCIES),
    }

    def run(command, **kwargs):
        calls.append((command, kwargs))
        if "buildx" in command:
            if behavior["build_failure"]:
                raise subprocess.CalledProcessError(1, command)
            if behavior["change_sources"]:
                (tmp_path / "Dockerfile").write_text("changed during build")

    def output(command, **kwargs):
        calls.append((command, kwargs))
        if command[:3] == ["docker", "image", "inspect"]:
            return json.dumps([{"Id": IMAGE, "RepoDigests": behavior["digests"]}])
        assert command[:2] == ["docker", "run"]
        return json.dumps({"python": "3.11.17", "dependencies": behavior["dependencies"]})

    monkeypatch.setattr(module.subprocess, "run", run)
    monkeypatch.setattr(module.subprocess, "check_output", output)
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "DO_NOT_PROPAGATE")
    return module, tmp_path, lock, original, calls, behavior


def test_build_pins_actual_base_and_publishes_verified_provenance(builder):
    module, runtime, path, _, calls, _ = builder
    lock = module.prepare_image(runtime)
    assert lock == json.loads(path.read_text())
    assert lock["digest"] == IMAGE and lock["digest_kind"] == "image_id"
    assert lock["base_digest"] == BASE and lock["python_version"] == "3.11.17"
    assert (
        lock["dependency_hash"]
        == hashlib.sha256((runtime / "requirements.lock").read_bytes()).hexdigest()
    )
    assert (
        lock["dockerfile_hash"] == hashlib.sha256((runtime / "Dockerfile").read_bytes()).hexdigest()
    )
    build = next(command for command, _ in calls if "buildx" in command)
    assert build[:3] == ["docker", "buildx", "build"] and "--load" in build
    assert build[build.index("--build-arg") + 1] == "PYTHON_BASE=" + BASE
    probe = next(command for command, _ in calls if command[:2] == ["docker", "run"])
    assert probe[probe.index("--network") + 1] == "none" and "--read-only" in probe
    assert all("AWS_BEARER_TOKEN_BEDROCK" not in kwargs["env"] for _, kwargs in calls)
    calls.clear()
    assert module.prepare_image(runtime) == lock
    assert calls[0][0][-1] == BASE, "subsequent preparation must reuse the sealed base"


@pytest.mark.parametrize("failure", ["build", "base_digest", "versions", "inputs"])
def test_failed_preparation_preserves_previous_lock(builder, failure):
    module, runtime, path, original, calls, behavior = builder
    if failure == "build":
        behavior["build_failure"] = True
    elif failure == "base_digest":
        behavior["digests"] = []
    elif failure == "versions":
        behavior["dependencies"]["pytest"] = "wrong"
    else:
        behavior["change_sources"] = True
    with pytest.raises((RuntimeError, subprocess.CalledProcessError)):
        module.prepare_image(runtime)
    assert path.read_bytes() == original
    if failure == "base_digest":
        assert all("buildx" not in command for command, _ in calls)
