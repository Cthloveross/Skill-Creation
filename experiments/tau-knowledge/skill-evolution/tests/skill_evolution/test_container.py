import hashlib
import json
import os
import sys
from pathlib import Path

import pytest
from tau_skill_evolution.artifacts import SkillBundle
from tau_skill_evolution.container import (
    BoundedProcessTransport,
    ContainerUnavailable,
    DockerRunner,
    ImageLock,
    ProcessResult,
    _remove_staging,
)


def locked(tmp_path):
    path = tmp_path / "requirements.lock"
    path.write_text(
        "\n".join(
            f"{name}=={version} --hash=sha256:{'a' * 64}"
            for name, version in (("numpy", "2.2.6"), ("pandas", "2.2.3"), ("pytest", "8.4.2"))
        )
    )
    return ImageLock(
        "tau-skill-python:3.11",
        "sha256:" + "b" * 64,
        hashlib.sha256(path.read_bytes()).hexdigest(),
        path,
    )


class Transport:
    def __init__(self, response=None):
        self.commands = []
        self.inputs = []
        self.response = response or ProcessResult(0, b'{"ok":true}')
        self.workspace = None

    def run(self, command, *, stdin, timeout, output_limit):
        self.commands.append(command)
        self.inputs.append(stdin)
        if "run" in command:
            mounts = [
                command[index + 1] for index, value in enumerate(command) if value == "--mount"
            ]
            assert len(mounts) == 2
            self.workspace = Path(mounts[1].split("src=", 1)[1].split(",", 1)[0])
            assert timeout <= 60 and output_limit <= 65536
            return self.response
        return ProcessResult(0, b"[]")


def test_script_container_limits_and_episode_state(tmp_path):
    transport = Transport()
    runner = DockerRunner(locked(tmp_path), transport=transport)
    bundle = SkillBundle(
        {
            "SKILL.md": "skill",
            "scripts/helper.py": "VALUE=1",
            "scripts/main.py": "import helper",
            "references/policy.txt": "policy",
        }
    )
    with runner.episode(bundle) as episode:
        assert episode.read_skill_file("references/policy.txt") == "policy"
        assert episode.run_skill_script("scripts/main.py", {"a": 1}).output == {"ok": True}
        workspace = transport.workspace
        (workspace / "persisted").write_text("same episode")
        episode.run_skill_script("scripts/main.py", {})
        assert (transport.workspace / "persisted").exists()
        command = transport.commands[0]
        for option, value in (
            ("--network", "none"),
            ("--user", f"{os.getuid()}:{os.getgid()}" if os.getuid() else "10001:10001"),
            ("--cpus", "1"),
            ("--memory", "1g"),
            ("--memory-swap", "1g"),
            ("--pids-limit", "64"),
            ("--cap-drop", "ALL"),
            ("--security-opt", "no-new-privileges"),
            ("--pull", "never"),
        ):
            assert command[command.index(option) + 1] == value
        assert "--read-only" in command
        assert command[-2:] == ["python", "/bundle/scripts/main.py"]
        assert transport.inputs[0] == b'{"a": 1}'
        assert transport.commands[1][:3] == ["docker", "rm", "--force"]
    assert not workspace.exists()
    with runner.episode(bundle) as episode:
        assert not (episode.work / "persisted").exists()


@pytest.mark.parametrize(
    "response,failure",
    [
        (ProcessResult(0, b"oops"), "invalid_json"),
        (ProcessResult(0, b'{"a":NaN}'), "invalid_json"),
        (ProcessResult(1, b"", b"missing numpy"), "nonzero_exit"),
        (ProcessResult(-9, b"", b"", "timeout"), "timeout"),
        (ProcessResult(-9, b"", b"", "output_limit"), "output_limit"),
    ],
)
def test_script_explicit_failure_and_cleanup(tmp_path, response, failure):
    transport = Transport(response)
    with DockerRunner(locked(tmp_path), transport=transport).episode(
        SkillBundle({"SKILL.md": "s", "scripts/main.py": "invalid syntax!"})
    ) as episode:
        assert episode.run_skill_script("scripts/main.py", None).failure == failure
        assert transport.commands[-1][:3] == ["docker", "rm", "--force"]


def test_no_host_fallback_when_docker_missing(tmp_path):
    class Missing:
        def run(self, *args, **kwargs):
            raise FileNotFoundError("docker unavailable")

    runner = DockerRunner(locked(tmp_path), transport=Missing())
    with runner.episode(SkillBundle({"SKILL.md": "s", "scripts/main.py": "pass"})) as episode:
        assert episode.run_skill_script("scripts/main.py", {}).failure == "container_unavailable"
    checks = runner.preflight()
    assert not checks["ready"] and not checks["docker_cli"] and not checks["docker_daemon"]


def test_missing_or_tampered_lock_blocks_runner(tmp_path):
    lock = locked(tmp_path)
    ImageLock(lock.image, None, lock.dependency_hash, lock.dependency_lock)
    with pytest.raises(ContainerUnavailable, match="image_digest_not_prepared"):
        ImageLock(lock.image, None, lock.dependency_hash, lock.dependency_lock).validate()
    lock.dependency_lock.write_text("tampered")
    with pytest.raises(ContainerUnavailable, match="dependency_lock_hash_mismatch"):
        lock.validate()


@pytest.mark.parametrize("original_failure", [None, "timeout", "output_limit"])
def test_failed_cleanup_is_explicit_and_records_container(tmp_path, original_failure):
    class FailedCleanup(Transport):
        def run(self, command, **kwargs):
            if "rm" in command:
                return ProcessResult(1, stderr=b"daemon unavailable")
            return super().run(command, **kwargs)

    transport = FailedCleanup(ProcessResult(0, b'{"ok":true}', failure=original_failure))
    with DockerRunner(locked(tmp_path), transport=transport).episode(
        SkillBundle({"SKILL.md": "s", "scripts/main.py": "pass"})
    ) as episode:
        result = episode.run_skill_script("scripts/main.py", {})
        assert result.failure == "cleanup_failed" and result.output is None
        name = transport.commands[0][transport.commands[0].index("--name") + 1]
        assert f"container={name}" in result.stderr
        assert f"original_failure={original_failure}" in result.stderr
        assert f"staging={episode.package.parent}" in result.stderr
        staging = episode.package.parent
    assert staging.exists()
    # Test infrastructure confirms no container was created before deleting the preserved fixture.
    _remove_staging(str(staging))


def test_auto_removed_container_is_successful_cleanup(tmp_path):
    class AlreadyRemoved(Transport):
        def run(self, command, **kwargs):
            if "rm" in command:
                return ProcessResult(1, stderr=b"Error response from daemon: No such container")
            return super().run(command, **kwargs)

    with DockerRunner(locked(tmp_path), transport=AlreadyRemoved()).episode(
        SkillBundle({"SKILL.md": "s", "scripts/main.py": "pass"})
    ) as episode:
        result = episode.run_skill_script("scripts/main.py", {})
        assert result.failure is None and result.output == {"ok": True}


def test_read_and_run_reject_invalid_paths(tmp_path):
    runner = DockerRunner(locked(tmp_path), transport=Transport())
    with runner.episode(SkillBundle({"SKILL.md": "s", "scripts/main.py": "pass"})) as episode:
        for path in ("../secret", "/etc/passwd", "scripts/../../secret", "scripts/main.py/."):
            with pytest.raises(ValueError):
                episode.read_skill_file(path)
        with pytest.raises(ValueError):
            episode.run_skill_script("SKILL.md", {})


def test_cleanup_does_not_follow_untrusted_symlink(tmp_path):
    target = tmp_path / "unmounted"
    target.mkdir(mode=0o700)
    before = target.stat().st_mode
    runner = DockerRunner(locked(tmp_path), transport=Transport())
    with runner.episode(SkillBundle({"SKILL.md": "s"})) as episode:
        (episode.work / "host-directory").symlink_to(target, target_is_directory=True)
    assert target.stat().st_mode == before


def test_permission_tampered_private_directories_are_cleaned(tmp_path):
    runner = DockerRunner(locked(tmp_path), transport=Transport())
    with runner.episode(SkillBundle({"SKILL.md": "s"})) as episode:
        nested = episode.work / "permission-tampered"
        nested.mkdir()
        (nested / "file").write_text("temporary")
        nested.chmod(0)
        staging = episode.package.parent
    assert not staging.exists()


def test_streaming_transport_enforces_combined_output():
    result = BoundedProcessTransport().run(
        [
            sys.executable,
            "-c",
            "import sys;sys.stderr.write('x'*200000);sys.stdout.write('y'*200000)",
        ],
        stdin=b"",
        timeout=2,
        output_limit=4096,
    )
    assert result.failure == "output_limit"
    assert len(result.stdout) + len(result.stderr) == 4096


def test_streaming_transport_timeout():
    result = BoundedProcessTransport().run(
        [sys.executable, "-c", "import time;time.sleep(5)"],
        stdin=b"",
        timeout=0.05,
        output_limit=4096,
    )
    assert result.failure == "timeout"


def test_preflight_accepts_actual_image_id(tmp_path):
    lock = locked(tmp_path)
    lock = ImageLock(
        lock.image, lock.digest, lock.dependency_hash, lock.dependency_lock, "image_id"
    )

    class Preflight(Transport):
        def run(self, command, **kwargs):
            self.commands.append(command)
            if "inspect" in command:
                return ProcessResult(0, json.dumps({"Id": lock.digest, "RepoDigests": []}).encode())
            if "run" in command:
                return ProcessResult(
                    0,
                    b'{"python":[3,11],"dependencies":{"numpy":"2.2.6",'
                    b'"pandas":"2.2.3","pytest":"8.4.2"}}',
                )
            return ProcessResult(0, b'"version"')

    runner = DockerRunner(lock, transport=Preflight())
    assert runner.preflight()["ready"]
    assert lock.reference == lock.digest


def test_verifier_mount_contains_no_skill_source(tmp_path):
    class VerifierTransport(Transport):
        def run(self, command, **kwargs):
            if "run" in command:
                mounts = [
                    command[index + 1] for index, value in enumerate(command) if value == "--mount"
                ]
                package = Path(mounts[0].split("src=", 1)[1].split(",", 1)[0])
                assert sorted(path.name for path in package.iterdir()) == [
                    "_harness.py",
                    "base.json",
                    "public_inputs.json",
                    "tests",
                    "trace.json",
                ]
                assert not (package / "SKILL.md").exists()
                assert "private" not in (package / "trace.json").read_text()
            return super().run(command, **kwargs)

    runner = DockerRunner(locked(tmp_path), transport=VerifierTransport())
    runner.run_verifier(
        {"task": "public"},
        {"documents": []},
        {"events": []},
        {"tests/test_public.py": "def test_public(): assert True"},
    )
