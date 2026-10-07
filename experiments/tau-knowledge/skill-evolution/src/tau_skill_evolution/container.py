"""Bounded program execution and shared Skill/verifier staging."""

from __future__ import annotations

import hashlib
import json
import os
import posixpath
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
from collections.abc import Callable, Iterator, Mapping, Sequence
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
        self,
        command: Sequence[str],
        *,
        stdin: bytes,
        timeout: float,
        output_limit: int,
        env: Mapping[str, str] | None = None,
    ) -> ProcessResult: ...


class BoundedProcessTransport:
    """Drain both pipes incrementally and kill before output can grow without bound."""

    def __init__(self, *, kill_process_group: bool = False) -> None:
        self.kill_process_group = kill_process_group

    def run(
        self,
        command: Sequence[str],
        *,
        stdin: bytes,
        timeout: float,
        output_limit: int,
        env: Mapping[str, str] | None = None,
    ) -> ProcessResult:
        process = subprocess.Popen(
            list(command),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=self.kill_process_group,
            env=None if env is None else dict(env),
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


def _remove_staging(path: str, *, allow_privileged_cleanup: bool = True) -> None:
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
            if not allow_privileged_cleanup:
                raise ContainerUnavailable(
                    f"staging_cleanup_failed:{root}:host_permission_denied"
                ) from exc
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


def _remove_runtime_staging(runner: Any, path: str) -> None:
    local = getattr(runner, "runtime", None) in {
        "workspace",
        "bubblewrap",
        "bubblewrap-demo",
    } or bool(getattr(runner, "demo", None))
    _remove_staging(path, allow_privileged_cleanup=not local)


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

    def authoring_session(
        self,
        previous_bundle: Any,
        public_inputs: Mapping[str, Any],
        frozen_base: Any,
        *,
        workspace: Path | None = None,
    ) -> Any:
        self.image_lock.validate()
        return _public_workspace(
            self,
            public_inputs,
            frozen_base,
            previous_bundle=previous_bundle,
            workspace=workspace,
        )

    def public_verifier_session(
        self,
        public_inputs: Mapping[str, Any],
        base: Any,
        trace: Mapping[str, Any],
        files: Mapping[str, str] | None = None,
        readonly_tests: bool = False,
        *,
        workspace: Path | None = None,
    ) -> Any:
        self.image_lock.validate()
        return _public_workspace(
            self,
            public_inputs,
            base,
            trace=trace,
            test_files=files,
            readonly_tests=readonly_tests,
            workspace=workspace,
        )

    def _terminal(self, package: Path, work: Path, command: str) -> ProgramResult:
        return self._run(package, work, ["/bin/sh", "-c", command], raw=True)

    def _run(
        self,
        package: Path,
        work: Path,
        args: Sequence[str],
        stdin: bytes = b"",
        *,
        raw: bool = False,
    ) -> ProgramResult:
        name = f"tau-skill-{uuid.uuid4().hex}"
        writable = _workspace_writable_roots(package)
        command = [
            self.docker,
            "run",
            "--name",
            name,
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
            "/work/scratch" if "scratch" in writable and "candidate" not in writable else "/work",
            "--env",
            "PYTHONDONTWRITEBYTECODE=1",
            "--env",
            "PYTHONPATH=/bundle:/bundle/scripts",
            "--env",
            "TMPDIR=/work/scratch" if "scratch" in writable else "TMPDIR=/work",
            "--env",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1",
            "--tmpfs",
            "/tmp:rw,nosuid,nodev,noexec,size=64m,mode=1777",
            "--mount",
            f"type=bind,src={package.resolve()},dst=/bundle,readonly",
            "--mount",
            f"type=bind,src={work.resolve()},dst=/work" + (",readonly" if writable else ""),
        ]
        for relative in writable:
            command.extend(
                ["--mount", f"type=bind,src={(work / relative).resolve()},dst=/work/{relative}"]
            )
        command.extend([self.image_lock.reference, *args])
        cleanup: ProcessResult | None = None
        launch_failed = False
        try:
            result = self.transport.run(
                command, stdin=stdin, timeout=self.timeout, output_limit=self.output_limit
            )
            outcome = _program_result(result, raw=raw)
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


def _program_result(result: ProcessResult, *, raw: bool = False) -> ProgramResult:
    stderr = result.stderr.decode("utf-8", "replace")
    if raw:
        return ProgramResult(
            result.returncode,
            {"stdout": result.stdout.decode("utf-8", "replace"), "stderr": stderr},
            stderr,
            result.failure,
        )
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


def _workspace_writable_roots(package: Path) -> tuple[str, ...]:
    policy = package / "_workspace_policy.json"
    if not policy.exists():
        return ()
    values = json.loads(policy.read_text(encoding="utf-8"))
    if not isinstance(values, list) or any(
        value not in {"candidate", "tests", "scratch"} for value in values
    ):
        raise ValueError("invalid_workspace_policy")
    return tuple(values)


def _tree_manifest(root: Path, *, scratch_links: bool = False) -> dict[str, str]:
    """Hash regular bytes and record safe scratch links without following them."""
    if root.is_symlink() or not root.is_dir():
        raise ValueError("unsafe_workspace_root")
    manifest = {}

    def unreadable(error: OSError) -> None:
        raise error

    for directory, directories, files in os.walk(root, followlinks=False, onerror=unreadable):
        for name in sorted([*directories, *files]):
            path = Path(directory) / name
            relative = path.relative_to(root).as_posix()
            _safe_path(relative)
            mode = path.lstat().st_mode
            if stat.S_ISDIR(mode):
                manifest[relative + "/"] = "directory"
            elif stat.S_ISREG(mode):
                # O_NOFOLLOW also rejects a link replacing a file after lstat.
                descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                with os.fdopen(descriptor, "rb") as source:
                    if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
                        raise ValueError("unsafe_workspace_file")
                    manifest[relative] = hashlib.sha256(source.read()).hexdigest()
            elif stat.S_ISLNK(mode) and scratch_links and relative.startswith("scratch/"):
                target = os.readlink(path)
                if "\\" in target or "\x00" in target:
                    raise ValueError("unsafe_workspace_symlink")
                destination = posixpath.normpath(
                    posixpath.join("/work", posixpath.dirname(relative), target)
                )
                if destination != "/work/scratch" and not destination.startswith("/work/scratch/"):
                    raise ValueError("unsafe_workspace_symlink")
                # Preserve the link itself, never traverse its target on the host.
                manifest[relative] = "symlink:" + target
            else:
                raise ValueError("unsafe_workspace_file")
    return manifest


@dataclass
class PublicWorkspaceSession:
    """One isolated authoring/checking workspace; public mounts are immutable."""

    package: Path
    work: Path
    target: Path
    terminal_callback: Callable[[Path, Path, str], ProgramResult]
    tests_callback: Callable[[Path, Path, Sequence[str]], ProgramResult]
    readonly_tests: bool = False
    tests: bool = False
    cleanup_failed: bool = False

    def terminal(self, command: str) -> ProgramResult:
        if not isinstance(command, str) or not command or "\x00" in command:
            raise ValueError("invalid_terminal_command")
        result = self.terminal_callback(self.package, self.work, command)
        self.cleanup_failed |= result.failure == "cleanup_failed"
        return result

    def files(self) -> dict[str, str]:
        from .artifacts import decode_package_text

        manifest = _tree_manifest(self.target)
        files = {}
        for relative in manifest:
            if relative.endswith("/"):
                continue
            parts = Path(relative).parts
            if ".pytest_cache" in parts[:-1] or (
                "__pycache__" in parts[:-1] and Path(relative).suffix in {".pyc", ".pyo"}
            ):
                continue
            path = self.target / relative
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(descriptor, "rb") as source:
                if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
                    raise ValueError("unsafe_workspace_file")
                key = "tests/" + relative if self.tests else relative
                files[key] = decode_package_text(source.read(), key)
        return files

    def snapshot(self) -> dict[str, Any]:
        manifest = {
            "public": _tree_manifest(self.package),
            "work": _tree_manifest(self.work, scratch_links=True),
        }
        encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
        result = {
            "workspace_hash": hashlib.sha256(encoded).hexdigest(),
            "manifest": manifest,
        }
        try:
            result["files"] = self.files()
        except ValueError as exc:
            if not str(exc).startswith("non_utf8_package_file: "):
                raise
            result.update(files=None, invalid_package=str(exc))
        return result

    def run_tests(self) -> ProgramResult:
        if not self.tests:
            raise ValueError("tests_not_available_in_authoring")
        from .verifier import _validate_test_source

        _validate_test_source(self.files())
        testroot = "/bundle/tests" if self.readonly_tests else "/work/tests"
        result = self.tests_callback(
            self.package, self.work, ["python", "-I", "/bundle/_harness.py", testroot]
        )
        self.cleanup_failed |= result.failure == "cleanup_failed"
        return result


@contextmanager
def _public_workspace(
    runner: Any,
    public_inputs: Mapping[str, Any],
    frozen_base: Any,
    *,
    previous_bundle: Any = None,
    trace: Mapping[str, Any] | None = None,
    test_files: Mapping[str, str] | None = None,
    readonly_tests: bool = False,
    workspace: Path | None = None,
    terminal_callback: Callable[[Path, Path, str], ProgramResult] | None = None,
    tests_callback: Callable[[Path, Path, Sequence[str]], ProgramResult] | None = None,
) -> Iterator[PublicWorkspaceSession]:
    from .core._canonical import thaw_json

    base = frozen_base.to_dict() if hasattr(frozen_base, "to_dict") else thaw_json(frozen_base)
    authoring = previous_bundle is not None
    trace_value = thaw_json(trace or {})
    trace_value.pop("public_artifacts_dir", None)
    public = {
        "public_inputs.json": json.dumps(
            thaw_json(public_inputs), ensure_ascii=False, allow_nan=False
        ),
        "base.json": json.dumps(base, ensure_ascii=False, allow_nan=False),
        "trace.json": json.dumps(trace_value, ensure_ascii=False, allow_nan=False),
        "_harness.py": _PYTEST_HARNESS,
        "_workspace_policy.json": json.dumps(
            ["candidate", "scratch"]
            if authoring
            else ["scratch"]
            if readonly_tests
            else ["tests", "scratch"]
        ),
    }
    if readonly_tests:
        public.update(test_files or {})
    staging = str(workspace) if workspace is not None else tempfile.mkdtemp(prefix="tau-public-")
    root = Path(staging)
    session = None
    try:
        if root.is_symlink():
            raise ValueError("unsafe_workspace_root")
        root.mkdir(parents=True, exist_ok=True)
        package, work = root / "bundle", root / "work"
        resumed = package.exists() or work.exists()
        if resumed:
            expected = {
                relative: hashlib.sha256(content.encode()).hexdigest()
                for relative, content in public.items()
            }
            observed = {
                path: digest
                for path, digest in _tree_manifest(package).items()
                if not path.endswith("/")
            }
            if expected != observed:
                raise ValueError("public_workspace_input_mismatch")
            _tree_manifest(work, scratch_links=True)
        else:
            package.mkdir()
            work.mkdir(mode=0o777)
            work.chmod(0o777)
            _stage_files(package, public)
            for relative in _workspace_writable_roots(package):
                (work / relative).mkdir(mode=0o777)
                (work / relative).chmod(0o777)
            initial = dict(previous_bundle.files) if authoring else dict(test_files or {})
            for relative, content in initial.items():
                path = (
                    work / "candidate" / _safe_path(relative)
                    if authoring
                    else work / _safe_path(relative)
                )
                if readonly_tests:
                    continue
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
                path.chmod(0o666)
                for parent in path.parents:
                    if parent == work:
                        break
                    parent.chmod(0o777)
        target = (
            work / "candidate"
            if authoring
            else package / "tests"
            if readonly_tests
            else work / "tests"
        )
        if readonly_tests and not target.exists():
            raise ValueError("empty_test_suite")
        session = PublicWorkspaceSession(
            package,
            work,
            target,
            terminal_callback or runner._terminal,
            tests_callback or runner._run,
            readonly_tests,
            not authoring,
        )
        yield session
    finally:
        if workspace is None and (session is None or not session.cleanup_failed):
            _remove_runtime_staging(runner, staging)


@contextmanager
def _episode(runner: Any, bundle: Any) -> Iterator[SkillEpisode]:
    from .artifacts import SkillBundle

    files = {} if bundle is None else SkillBundle.from_dict(bundle.to_dict()).files
    staging = tempfile.mkdtemp(prefix="tau-skill-")
    episode: SkillEpisode | None = None
    try:
        root = Path(staging)
        package, work = root / "bundle", root / "work"
        package.mkdir()
        work.mkdir(mode=0o777)
        work.chmod(0o777)
        _stage_files(package, files)
        episode = SkillEpisode(runner, package, work, files)
        yield episode
    finally:
        if episode is None or not episode.cleanup_failed:
            _remove_runtime_staging(runner, staging)


def _run_verifier(
    runner: Any,
    public_inputs: Mapping[str, Any],
    frozen_base: Mapping[str, Any],
    trace: Mapping[str, Any],
    test_files: Mapping[str, str],
) -> ProgramResult:
    from .verifier import _validate_test_source

    _validate_test_source(test_files)
    with _public_workspace(
        runner,
        public_inputs,
        frozen_base,
        trace=trace,
        test_files=test_files,
        readonly_tests=True,
        terminal_callback=lambda package, work, command: runner._run(
            package, work, ["/bin/sh", "-c", command]
        ),
    ) as session:
        return session.run_tests()


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
sys.dont_write_bytecode = True
import pytest

ROOT = pathlib.Path('/bundle')
TESTROOT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'tests'
# Keep final report formatting independent of ordinary module monkeypatches in tests.
# Arbitrary Python in this process is still not a security boundary.
_encode_report = json.JSONEncoder(ensure_ascii=False, allow_nan=False).encode
_write_report = sys.stdout.write
_exit = SystemExit
_integer = int

class Report:
    def __init__(self):
        self.items = []
        self.nodeids = []
        self.collection_errors = 0
    @pytest.fixture
    def public_inputs(self):
        return json.loads((ROOT/'public_inputs.json').read_text())
    @pytest.fixture
    def frozen_base(self):
        return json.loads((ROOT/'base.json').read_text())
    @pytest.fixture
    def trace(self):
        return json.loads((ROOT/'trace.json').read_text())
    def pytest_collection_finish(self, session):
        self.nodeids = [item.nodeid for item in session.items]
    def pytest_collectreport(self, report):
        if report.failed:
            self.collection_errors += 1
    def pytest_runtest_logreport(self, report):
        if report.when == 'call' or report.failed or report.skipped:
            self.items.append({'nodeid':report.nodeid,'stage':report.when,
                               'outcome':report.outcome,
                               'exception':getattr(report, 'tau_exception', None),
                               'requirement_failure':getattr(report,
                                                            'tau_requirement_failure', False),
                               'xfail':hasattr(report, 'wasxfail'),
                               'detail':str(report.longrepr)[:4000] if report.longrepr else ''})
    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_makereport(self, item, call):
        outcome = yield
        report = outcome.get_result()
        report.tau_exception = call.excinfo.type.__name__ if call.excinfo else None
        report.tau_requirement_failure = bool(call.excinfo and isinstance(
            call.excinfo.value, (AssertionError, pytest.fail.Exception)))

report = Report()
# No generated conftest/plugin is loaded; this host-owned plugin supplies fixtures.
with contextlib.redirect_stdout(sys.stderr):
    code = pytest.main([str(TESTROOT), '--rootdir=' + str(TESTROOT.parent), '-q',
                       '--noconftest', '-p', 'no:cacheprovider', '--disable-warnings'],
                       plugins=[report])
result = {'exit_code':_integer(code),'collected':len(report.nodeids),
          'collected_nodeids':report.nodeids,
          'collection_errors':report.collection_errors,'results':report.items}
_write_report(_encode_report(result) + '\n')
raise _exit(_integer(code))
"""
