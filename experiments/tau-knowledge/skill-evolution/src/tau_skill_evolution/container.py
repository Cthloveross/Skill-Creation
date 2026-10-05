"""Bounded program execution and shared Skill/verifier staging."""

from __future__ import annotations

import hashlib
import json
import os
import re
import selectors
import shutil
import signal
import stat
import subprocess
import tempfile
import threading
import time
import uuid
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

PINNED_DEPENDENCIES = {"numpy": "2.2.6", "pandas": "2.2.3", "pytest": "8.4.2"}
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


class ContainerUnavailable(RuntimeError):
    """A required container boundary is unavailable; host execution is forbidden."""


@dataclass(frozen=True)
class ImageLock:
    image: str
    digest: str | None
    dependency_hash: str | None
    dependency_lock: Path | None = None
    digest_kind: str = "repo_digest"

    @classmethod
    def from_file(cls, path: Path, requirements_lock: Path | None = None) -> ImageLock:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("invalid_image_lock")
        return cls(
            value["image"],
            value.get("digest"),
            value.get("dependency_hash"),
            requirements_lock or path.with_name("requirements.lock"),
            value.get("digest_kind", "repo_digest"),
        )

    @property
    def reference(self) -> str:
        self.validate()
        return (
            self.digest
            if self.digest_kind == "image_id"
            else f"{self.image.split('@', 1)[0]}@{self.digest}"
        )

    def validate(self) -> None:
        if not self.image or not isinstance(self.digest, str) or not _DIGEST.fullmatch(self.digest):
            raise ContainerUnavailable("image_digest_not_prepared")
        if self.digest_kind not in {"repo_digest", "image_id"}:
            raise ContainerUnavailable("unknown_image_digest_kind")
        self.validate_dependencies()

    def validate_dependencies(self) -> None:
        """Validate wheel pins independently of whether an image has been prepared yet."""
        if not isinstance(self.dependency_hash, str) or not re.fullmatch(
            r"[0-9a-f]{64}", self.dependency_hash
        ):
            raise ContainerUnavailable("dependency_lock_not_prepared")
        if self.dependency_lock is None or not self.dependency_lock.is_file():
            raise ContainerUnavailable("dependency_lock_missing")
        content = self.dependency_lock.read_bytes()
        if hashlib.sha256(content).hexdigest() != self.dependency_hash:
            raise ContainerUnavailable("dependency_lock_hash_mismatch")
        text = content.decode("utf-8")
        for name, version in PINNED_DEPENDENCIES.items():
            if not re.search(rf"(?mi)^{name}=={re.escape(version)}(?:\s|$)", text):
                raise ContainerUnavailable(f"dependency_lock_missing_{name}")
        # Every requirement must carry a real pip hash; an un-hashed version list is insufficient.
        requirements = re.split(r"\n(?=[A-Za-z0-9])", text)
        if any(
            "==" in requirement and not re.search(r"--hash=sha256:[0-9a-f]{64}", requirement)
            for requirement in requirements
        ):
            raise ContainerUnavailable("dependency_lock_unhashed_requirement")


@dataclass(frozen=True)
class ProcessResult:
    returncode: int
    stdout: bytes = b""
    stderr: bytes = b""
    failure: str | None = None


class ProcessTransport(Protocol):
    def run(
        self, command: Sequence[str], *, stdin: bytes, timeout: float, output_limit: int
    ) -> ProcessResult: ...


class BoundedProcessTransport:
    """Drain both pipes incrementally and kill before output can grow without bound."""

    def __init__(self, *, kill_process_group: bool = False) -> None:
        self.kill_process_group = kill_process_group

    def run(
        self, command: Sequence[str], *, stdin: bytes, timeout: float, output_limit: int
    ) -> ProcessResult:
        process = subprocess.Popen(
            list(command),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=self.kill_process_group,
        )
        assert process.stdin is not None and process.stdout is not None
        assert process.stderr is not None
        stdout, stderr = bytearray(), bytearray()
        failure = None

        def kill() -> None:
            if self.kill_process_group:
                with suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGKILL)
            elif process.poll() is None:
                process.kill()

        def write_input() -> None:
            try:
                process.stdin.write(stdin)
                process.stdin.close()
            except (BrokenPipeError, OSError, ValueError):
                pass

        writer = threading.Thread(target=write_input, daemon=True)
        writer.start()
        deadline = time.monotonic() + timeout
        with selectors.DefaultSelector() as selector:
            for pipe, buffer in ((process.stdout, stdout), (process.stderr, stderr)):
                os.set_blocking(pipe.fileno(), False)
                selector.register(pipe, selectors.EVENT_READ, buffer)
            try:
                while selector.get_map():
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        failure = "timeout"
                        break
                    for key, _ in selector.select(min(remaining, 0.1)):
                        chunk = os.read(key.fileobj.fileno(), 8192)
                        if not chunk:
                            selector.unregister(key.fileobj)
                            continue
                        available = output_limit - len(stdout) - len(stderr)
                        key.data.extend(chunk[: max(0, available)])
                        if len(chunk) > available:
                            failure = "output_limit"
                            break
                    if failure:
                        break
                if failure:
                    kill()
                try:
                    code = process.wait(timeout=max(0.01, deadline - time.monotonic()))
                except subprocess.TimeoutExpired:
                    failure = "timeout"
                    kill()
                    code = process.wait()
            finally:
                if process.poll() is None:
                    kill()
                    process.wait()
                for pipe in (process.stdin, process.stdout, process.stderr):
                    pipe.close()
                writer.join(timeout=0.1)
        return ProcessResult(code, bytes(stdout), bytes(stderr), failure)


@dataclass(frozen=True)
class ProgramResult:
    exit_code: int | None
    output: Any = None
    stderr: str = ""
    failure: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "exit_code": self.exit_code,
            "output": self.output,
            "stderr": self.stderr,
            "failure": self.failure,
        }


def _safe_path(path: str) -> PurePosixPath:
    if not isinstance(path, str) or not path or "\\" in path or "\x00" in path:
        raise ValueError("unsafe_relative_path")
    value = PurePosixPath(path)
    if value.is_absolute() or any(part in {"", ".", ".."} for part in path.split("/")):
        raise ValueError("unsafe_relative_path")
    return value


def _stage_files(root: Path, files: Mapping[str, str]) -> None:
    for relative, content in files.items():
        destination = root / _safe_path(relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
        destination.chmod(0o444)
    for directory in sorted(root.rglob("*"), reverse=True):
        if directory.is_dir():
            directory.chmod(0o555)
    root.chmod(0o555)


def _remove_staging(path: str) -> None:
    root = Path(path)
    if not shutil.rmtree.avoids_symlink_attacks:
        raise ContainerUnavailable(f"staging_cleanup_failed:{root}:unsafe_rmtree_platform")

    class RetryCleanup(Exception):
        pass

    def repair_permission(function: Any, failed_path: str, error: Any) -> None:
        if not isinstance(error[1], PermissionError):
            raise error[1]
        target = Path(failed_path)
        if function in (os.unlink, os.rmdir):
            target = target.parent
        if target != root and root not in target.parents:
            raise ContainerUnavailable(f"staging_cleanup_failed:{root}:outside_staging")
        # O_PATH requires no directory permissions; O_NOFOLLOW keeps a replaced symlink
        # from redirecting chmod. /proc/self/fd resolves the held inode, not a mutable path.
        descriptor = os.open(target, os.O_PATH | os.O_NOFOLLOW)
        try:
            if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
                raise error[1]
            os.chmod(f"/proc/self/fd/{descriptor}", 0o700)
        finally:
            os.close(descriptor)
        raise RetryCleanup

    for _ in range(128):
        try:
            shutil.rmtree(root, onerror=repair_permission)
            return
        except RetryCleanup:
            continue
        except PermissionError as exc:
            # Official graders run as root and may leave root-owned subdirectories in
            # the bind-mounted staging area; the host user can neither chmod nor unlink
            # those, so delete them from inside a throwaway container instead.
            _privileged_cleanup(root, exc)
            try:
                shutil.rmtree(root)
                return
            except OSError as retry_exc:
                raise ContainerUnavailable(
                    f"staging_cleanup_failed:{root}:{retry_exc}"
                ) from retry_exc
        except OSError as exc:
            raise ContainerUnavailable(f"staging_cleanup_failed:{root}:{exc}") from exc
    raise ContainerUnavailable(f"staging_cleanup_failed:{root}:permission_repair_limit")


CLEANUP_IMAGE = "busybox:stable"


def _privileged_cleanup(root: Path, cause: BaseException) -> None:
    """Remove root-owned staging contents via a container; fail closed otherwise."""
    if (
        not root.is_absolute()
        or not root.is_dir()
        or root.is_symlink()
        or root == Path(root.anchor)
    ):
        raise ContainerUnavailable(f"staging_cleanup_failed:{root}:{cause}") from cause
    command = [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "--mount",
        f"type=bind,src={root},dst=/tau-cleanup",
        CLEANUP_IMAGE,
        "sh",
        "-c",
        "rm -rf /tau-cleanup/* /tau-cleanup/.[!.]* /tau-cleanup/..?* 2>/dev/null; true",
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ContainerUnavailable(f"staging_cleanup_failed:{root}:{cause}") from exc


class DockerRunner:
    def __init__(
        self,
        image_lock: ImageLock,
        *,
        transport: ProcessTransport | None = None,
        docker: str = "docker",
        timeout: float = 60,
        output_limit: int = 64 * 1024,
    ) -> None:
        if not 0 < timeout <= 60 or not 0 < output_limit <= 64 * 1024:
            raise ValueError("container limits cannot exceed protocol limits")
        self.image_lock = image_lock
        self.transport = transport or BoundedProcessTransport()
        self.docker = docker
        self.timeout = timeout
        self.output_limit = output_limit
        self.user = f"{os.getuid()}:{os.getgid()}" if os.getuid() != 0 else "10001:10001"

    def preflight(self) -> dict[str, Any]:
        checks: dict[str, Any] = {}
        try:
            self.image_lock.validate()
            checks["image_lock"] = True
        except (ContainerUnavailable, OSError, UnicodeError) as exc:
            checks.update(image_lock=False, image_lock_error=str(exc))
        for key, args in (
            ("docker_cli", ["version", "--format", "{{json .Client.Version}}"]),
            ("docker_daemon", ["info", "--format", "{{json .ServerVersion}}"]),
        ):
            try:
                result = self.transport.run(
                    [self.docker, *args], stdin=b"", timeout=10, output_limit=65536
                )
                checks[key] = result.returncode == 0 and result.failure is None
                if not checks[key]:
                    checks[f"{key}_error"] = result.stderr.decode("utf-8", "replace")
            except OSError as exc:
                checks[key] = False
                checks[f"{key}_error"] = str(exc)
        checks["image_present"] = False
        checks["dependencies"] = False
        if checks["image_lock"] and checks["docker_daemon"]:
            result = self.transport.run(
                [
                    self.docker,
                    "image",
                    "inspect",
                    self.image_lock.reference,
                    "--format",
                    "{{json .}}",
                ],
                stdin=b"",
                timeout=10,
                output_limit=65536,
            )
            try:
                metadata = json.loads(result.stdout)
                checks["image_present"] = (
                    result.returncode == 0
                    and result.failure is None
                    and isinstance(metadata, dict)
                    and (
                        metadata.get("Id") == self.image_lock.digest
                        if self.image_lock.digest_kind == "image_id"
                        else self.image_lock.reference in (metadata.get("RepoDigests") or [])
                    )
                )
            except (ValueError, TypeError):
                pass
            if checks["image_present"]:
                code = (
                    "import json,sys,importlib.metadata as m; "
                    "print(json.dumps({'python':list(sys.version_info[:2]),"
                    "'dependencies':{n:m.version(n) for n in ('numpy','pandas','pytest')}}))"
                )
                with tempfile.TemporaryDirectory(prefix="tau-preflight-") as temp:
                    root = Path(temp)
                    (root / "bundle").mkdir()
                    (root / "work").mkdir(mode=0o777)
                    result2 = self._run(root / "bundle", root / "work", ["python", "-c", code])
                    checks["dependencies"] = (
                        result2.failure is None
                        and result2.exit_code == 0
                        and result2.output
                        == {"python": [3, 11], "dependencies": PINNED_DEPENDENCIES}
                    )
        checks["ready"] = all(
            checks[key]
            for key in (
                "image_lock",
                "docker_cli",
                "docker_daemon",
                "image_present",
                "dependencies",
            )
        )
        return checks

    @contextmanager
    def episode(self, bundle: Any) -> Iterator[SkillEpisode]:
        self.image_lock.validate()
        with _episode(self, bundle) as episode:
            yield episode

    def run_verifier(
        self,
        public_inputs: Mapping[str, Any],
        frozen_base: Mapping[str, Any],
        trace: Mapping[str, Any],
        test_files: Mapping[str, str],
    ) -> ProgramResult:
        return _run_verifier(self, public_inputs, frozen_base, trace, test_files)

    def _run(
        self, package: Path, work: Path, args: Sequence[str], stdin: bytes = b""
    ) -> ProgramResult:
        name = f"tau-skill-{uuid.uuid4().hex}"
        command = [
            self.docker,
            "run",
            "--name",
            name,
            "--rm",
            "--pull",
            "never",
            "--interactive",
            "--network",
            "none",
            "--user",
            self.user,
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
            "--workdir",
            "/work",
            "--env",
            "PYTHONDONTWRITEBYTECODE=1",
            "--env",
            "PYTHONPATH=/bundle:/bundle/scripts",
            "--env",
            "TMPDIR=/work",
            "--env",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1",
            "--tmpfs",
            "/tmp:rw,nosuid,nodev,noexec,size=64m,mode=1777",
            "--mount",
            f"type=bind,src={package.resolve()},dst=/bundle,readonly",
            "--mount",
            f"type=bind,src={work.resolve()},dst=/work",
            self.image_lock.reference,
            *args,
        ]
        cleanup: ProcessResult | None = None
        launch_failed = False
        try:
            result = self.transport.run(
                command, stdin=stdin, timeout=self.timeout, output_limit=self.output_limit
            )
            outcome = _program_result(result)
        except FileNotFoundError as exc:
            launch_failed = True
            outcome = ProgramResult(None, stderr=str(exc), failure="container_unavailable")
        except OSError as exc:
            outcome = ProgramResult(None, stderr=str(exc), failure="container_unavailable")
        finally:
            # Killing a Docker client alone does not reliably kill its container.
            if not launch_failed:
                try:
                    cleanup = self.transport.run(
                        [self.docker, "rm", "--force", name],
                        stdin=b"",
                        timeout=10,
                        output_limit=65536,
                    )
                except OSError as exc:
                    cleanup = ProcessResult(
                        -1, stderr=str(exc).encode("utf-8"), failure="container_unavailable"
                    )
        if cleanup is not None:
            detail = (cleanup.stdout + cleanup.stderr).decode("utf-8", "replace")
            if cleanup.failure or (
                cleanup.returncode and "no such container" not in detail.lower()
            ):
                trusted = (
                    f"[trusted cleanup] container={name}; staging={package.parent}; "
                    f"original_failure={outcome.failure}; "
                    f"cleanup_failure={cleanup.failure or cleanup.returncode}; {detail[:512]}\n"
                )
                stderr = (trusted + outcome.stderr).encode("utf-8")[: self.output_limit]
                return ProgramResult(
                    outcome.exit_code,
                    stderr=stderr.decode("utf-8", "ignore"),
                    failure="cleanup_failed",
                )
        return outcome


def _reject_constant(value: str) -> None:
    raise ValueError(f"invalid JSON constant: {value}")


def _program_result(result: ProcessResult) -> ProgramResult:
    stderr = result.stderr.decode("utf-8", "replace")
    if result.failure:
        return ProgramResult(result.returncode, stderr=stderr, failure=result.failure)
    try:
        output = json.loads(result.stdout.decode("utf-8"), parse_constant=_reject_constant)
        return ProgramResult(
            result.returncode, output, stderr, "nonzero_exit" if result.returncode else None
        )
    except (UnicodeDecodeError, ValueError):
        return ProgramResult(
            result.returncode,
            stderr=stderr,
            failure="nonzero_exit" if result.returncode else "invalid_json",
        )


@contextmanager
def _episode(runner: Any, bundle: Any) -> Iterator[SkillEpisode]:
    from .artifacts import SkillBundle

    bundle = SkillBundle.from_dict(bundle.to_dict())
    staging = tempfile.mkdtemp(prefix="tau-skill-")
    episode: SkillEpisode | None = None
    try:
        root = Path(staging)
        package, work = root / "bundle", root / "work"
        package.mkdir()
        work.mkdir(mode=0o777)
        work.chmod(0o777)
        _stage_files(package, bundle.files)
        episode = SkillEpisode(runner, package, work, bundle.files)
        yield episode
    finally:
        if episode is None or not episode.cleanup_failed:
            _remove_staging(staging)


def _run_verifier(
    runner: Any,
    public_inputs: Mapping[str, Any],
    frozen_base: Mapping[str, Any],
    trace: Mapping[str, Any],
    test_files: Mapping[str, str],
) -> ProgramResult:
    files = dict(test_files)
    files["public_inputs.json"] = json.dumps(public_inputs, ensure_ascii=False, allow_nan=False)
    files["base.json"] = json.dumps(frozen_base, ensure_ascii=False, allow_nan=False)
    files["trace.json"] = json.dumps(trace, ensure_ascii=False, allow_nan=False)
    files["_harness.py"] = _PYTEST_HARNESS
    staging = tempfile.mkdtemp(prefix="tau-verifier-")
    result: ProgramResult | None = None
    try:
        root = Path(staging)
        package, work = root / "bundle", root / "work"
        package.mkdir()
        work.mkdir(mode=0o777)
        work.chmod(0o777)
        _stage_files(package, files)
        result = runner._run(package, work, ["python", "-I", "/bundle/_harness.py"])
        return result
    finally:
        if result is None or result.failure != "cleanup_failed":
            _remove_staging(staging)


@dataclass
class SkillEpisode:
    runner: Any
    package: Path
    work: Path
    files: Mapping[str, str]
    cleanup_failed: bool = False

    def read_skill_file(self, relative_path: str) -> str:
        _safe_path(relative_path)
        if relative_path not in self.files:
            raise ValueError("skill_file_not_found")
        return self.files[relative_path]

    def run_skill_script(self, relative_path: str, input_json: Any) -> ProgramResult:
        _safe_path(relative_path)
        if (
            relative_path not in self.files
            or not relative_path.startswith("scripts/")
            or not relative_path.endswith(".py")
        ):
            raise ValueError("skill_script_not_found")
        encoded = json.dumps(input_json, ensure_ascii=False, allow_nan=False).encode("utf-8")
        result = self.runner._run(
            self.package, self.work, ["python", f"/bundle/{relative_path}"], encoded
        )
        if result.failure == "cleanup_failed":
            self.cleanup_failed = True
        return result


_PYTEST_HARNESS = r"""
import contextlib
import json
import pathlib
import sys
import pytest

class Report:
    def __init__(self):
        self.items = []
        self.collected = 0
        self.collection_errors = 0
    def pytest_collection_finish(self, session):
        self.collected = len(session.items)
    def pytest_collectreport(self, report):
        if report.failed:
            self.collection_errors += 1
    def pytest_runtest_logreport(self, report):
        if report.when == 'call' or report.failed or report.skipped:
            self.items.append({'nodeid':report.nodeid,'stage':report.when,
                               'outcome':report.outcome,
                               'exception':getattr(report, 'tau_exception', None),
                               'xfail':hasattr(report, 'wasxfail'),
                               'detail':str(report.longrepr)[:4000] if report.longrepr else ''})
    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_makereport(self, item, call):
        outcome = yield
        report = outcome.get_result()
        report.tau_exception = call.excinfo.type.__name__ if call.excinfo else None

report = Report()
# Fixtures contain public data only; no Skill or evaluator mount exists.
fixture_source = '''import json, pathlib, pytest
ROOT = pathlib.Path('/bundle')
@pytest.fixture
def public_inputs(): return json.loads((ROOT/'public_inputs.json').read_text())
@pytest.fixture
def frozen_base(): return json.loads((ROOT/'base.json').read_text())
@pytest.fixture
def trace(): return json.loads((ROOT/'trace.json').read_text())
'''
pathlib.Path('/work/conftest.py').write_text(fixture_source)
# Put conftest and tests in one private writable tree; source remains readonly in /bundle.
import shutil
shutil.copytree('/bundle/tests', '/work/tests')
with contextlib.redirect_stdout(sys.stderr):
    code = pytest.main(['/work', '-q', '-p', 'no:cacheprovider', '--disable-warnings'],
                       plugins=[report])
result = {'exit_code':int(code),'collected':report.collected,
          'collection_errors':report.collection_errors,'results':report.items}
print(json.dumps(result, ensure_ascii=False, allow_nan=False))
"""
