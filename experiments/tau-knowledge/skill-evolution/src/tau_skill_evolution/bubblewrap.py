"""Locked local workspaces with Bubblewrap isolation and per-process limits."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import tempfile
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .container import (
    PINNED_DEPENDENCIES,
    BoundedProcessTransport,
    ContainerUnavailable,
    ImageLock,
    ProcessTransport,
    ProgramResult,
    SkillEpisode,
    _episode,
    _program_result,
    _public_workspace,
    _run_verifier,
    _safe_path,
    _workspace_writable_roots,
)


@dataclass(frozen=True)
class RuntimeLock:
    rootfs: Path
    files: Mapping[str, str]
    python_version: tuple[int, ...]
    dependency_hash: str
    dependency_lock: Path
    symlinks: Mapping[str, str] = field(default_factory=dict)
    aggregate_limits_enforced: bool = False

    @classmethod
    def from_file(cls, path: Path) -> RuntimeLock:
        path = Path(path)
        value = json.loads(path.read_text(encoding="utf-8"))
        rootfs = Path(value["rootfs"])
        if not rootfs.is_absolute():
            rootfs = path.parent / rootfs
        return cls(
            rootfs.absolute(),
            value["files"],
            tuple(value["python_version"]),
            value["dependency_hash"],
            path.with_name("requirements.lock"),
            value.get("symlinks", {}),
            value["aggregate_limits_enforced"],
        )

    def validate(self) -> None:
        if self.python_version != (3, 11, 14) or self.aggregate_limits_enforced is not False:
            raise ContainerUnavailable("bubblewrap_demo_lock_invalid")
        ImageLock(
            "bubblewrap-rootfs", None, self.dependency_hash, self.dependency_lock
        ).validate_dependencies()
        if self.rootfs.is_symlink() or not self.rootfs.is_dir():
            raise ContainerUnavailable("bubblewrap_rootfs_missing")
        root = self.rootfs.resolve(strict=True)
        if (
            not self.files
            or not isinstance(self.files, Mapping)
            or not isinstance(self.symlinks, Mapping)
        ):
            raise ContainerUnavailable("bubblewrap_rootfs_manifest_invalid")
        for relative in [*self.files, *self.symlinks]:
            _safe_path(relative)
        if set(self.files) & set(self.symlinks):
            raise ContainerUnavailable("bubblewrap_rootfs_duplicate_path")
        actual_files, actual_links = set(), set()
        for directory, directories, files in os.walk(root, followlinks=False):
            for name in [*directories, *files]:
                path = Path(directory) / name
                relative = path.relative_to(root).as_posix()
                mode = path.lstat().st_mode
                if stat.S_ISLNK(mode):
                    actual_links.add(relative)
                    target = os.readlink(path)
                    if target != self.symlinks.get(relative) or Path(target).is_absolute():
                        raise ContainerUnavailable("bubblewrap_rootfs_unsafe_symlink")
                    try:
                        destination = path.resolve(strict=True)
                    except (OSError, RuntimeError) as exc:
                        raise ContainerUnavailable("bubblewrap_rootfs_unsafe_symlink") from exc
                    if destination != root and root not in destination.parents:
                        raise ContainerUnavailable("bubblewrap_rootfs_unsafe_symlink")
                elif stat.S_ISREG(mode):
                    actual_files.add(relative)
                    expected = self.files.get(relative)
                    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                        raise ContainerUnavailable("bubblewrap_rootfs_hash_mismatch")
                elif not stat.S_ISDIR(mode):
                    raise ContainerUnavailable("bubblewrap_rootfs_special_file")
        if actual_files != set(self.files) or actual_links != set(self.symlinks):
            raise ContainerUnavailable("bubblewrap_rootfs_manifest_mismatch")
        if not (root / "usr/local/bin/python").is_file():
            raise ContainerUnavailable("bubblewrap_python_missing")


class BubblewrapRunner:
    def __init__(
        self,
        runtime_lock: RuntimeLock,
        *,
        transport: ProcessTransport | None = None,
        bwrap: str = "bwrap",
        taskset: str = "taskset",
        prlimit: str = "prlimit",
        timeout: float = 60,
        output_limit: int = 65536,
        runtime: str = "bubblewrap-demo",
    ) -> None:
        if not 0 < timeout <= 60 or not 0 < output_limit <= 65536:
            raise ValueError("sandbox limits cannot exceed protocol limits")
        if runtime not in ("workspace", "bubblewrap-demo"):
            raise ValueError("unknown Bubblewrap runtime")
        self.runtime = runtime
        self.runtime_lock = runtime_lock
        self.transport = transport or BoundedProcessTransport(kill_process_group=True)
        self.bwrap, self.taskset, self.prlimit = bwrap, taskset, prlimit
        self.timeout, self.output_limit = timeout, output_limit
        self.cpu = min(os.sched_getaffinity(0))

    def preflight(self) -> dict[str, Any]:
        checks: dict[str, Any] = {
            "backend": self.runtime,
            "demo_only": self.runtime == "bubblewrap-demo",
            "resources_scope": "local_process",
            "formal_environment_equivalent": False,
            "aggregate_limits_enforced": False,
            "limits": {
                "cpu_affinity": self.cpu,
                "address_space_per_process": 1073741824,
                "nproc_per_uid": 64,
                "timeout_seconds": self.timeout,
                "output_bytes": self.output_limit,
            },
        }
        try:
            self.runtime_lock.validate()
            checks["runtime_lock"] = True
        except (OSError, ValueError, RuntimeError) as exc:
            checks.update(runtime_lock=False, runtime_lock_error=str(exc))
        checks["commands"] = all(
            shutil.which(name) for name in (self.bwrap, self.taskset, self.prlimit)
        )
        checks["dependencies"] = False
        checks["terminal"] = False
        if checks["runtime_lock"] and checks["commands"]:
            code = (
                "import json,sys,importlib.metadata as m; "
                "print(json.dumps({'python':list(sys.version_info[:3]),"
                "'dependencies':{n:m.version(n) for n in ('numpy','pandas','pytest')}}))"
            )
            with tempfile.TemporaryDirectory(prefix="tau-bwrap-preflight-") as temp:
                root = Path(temp)
                (root / "bundle").mkdir()
                (root / "work").mkdir(mode=0o777)
                result = self._run(root / "bundle", root / "work", ["python", "-I", "-c", code])
                checks["dependencies"] = result.failure is None and result.output == {
                    "python": list(self.runtime_lock.python_version),
                    "dependencies": PINNED_DEPENDENCIES,
                }
                if not checks["dependencies"]:
                    checks["dependencies_error"] = result.to_dict()
                else:
                    code = (
                        "import json,pathlib,subprocess,sys; "
                        "subprocess.run(['/bin/sh','-c',"
                        '"mkdir -p /work/scripts /work/references; '
                        "printf 'VALUE = 7\\n' > /work/scripts/helper.py; "
                        "printf public > /work/references/policy.txt; "
                        'cat /work/references/policy.txt > /work/copy"],check=True); '
                        "sys.path.insert(0,'/work/scripts'); import helper; "
                        "print(json.dumps({'terminal':True,'helper':helper.VALUE,"
                        "'reference':pathlib.Path('/work/copy').read_text()}))"
                    )
                    terminal = self._run(
                        root / "bundle", root / "work", ["python", "-I", "-c", code]
                    )
                    checks["terminal"] = terminal.failure is None and terminal.output == {
                        "terminal": True,
                        "helper": 7,
                        "reference": "public",
                    }
                    if not checks["terminal"]:
                        checks["terminal_error"] = terminal.to_dict()
        checks["ready"] = all(
            checks[key] for key in ("runtime_lock", "commands", "dependencies", "terminal")
        )
        return checks

    @contextmanager
    def episode(self, bundle: Any) -> Iterator[SkillEpisode]:
        self.runtime_lock.validate()
        with _episode(self, bundle) as episode:
            yield episode

    def run_verifier(
        self,
        public_inputs: Mapping[str, Any],
        frozen_base: Mapping[str, Any],
        trace: Mapping[str, Any],
        test_files: Mapping[str, str],
    ) -> ProgramResult:
        self.runtime_lock.validate()
        return _run_verifier(self, public_inputs, frozen_base, trace, test_files)

    def authoring_session(
        self,
        previous_bundle: Any,
        public_inputs: Mapping[str, Any],
        frozen_base: Any,
        *,
        workspace: Path | None = None,
    ) -> Any:
        self.runtime_lock.validate()
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
        self.runtime_lock.validate()
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
        self.runtime_lock.validate()
        if not args or (args[0] != "python" and not (raw and args[:2] == ["/bin/sh", "-c"])):
            raise ValueError("bubblewrap supports the locked Python interpreter only")
        writable = _workspace_writable_roots(package)
        command = [
            self.taskset,
            "--cpu-list",
            str(self.cpu),
            self.prlimit,
            "--as=1073741824",
            "--",
            self.bwrap,
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
            "--ro-bind",
            str(self.runtime_lock.rootfs.resolve()),
            "/",
            "--ro-bind",
            str(package.resolve()),
            "/bundle",
            "--ro-bind" if writable else "--bind",
            str(work.resolve()),
            "/work",
        ]
        for relative in writable:
            command.extend(["--bind", str((work / relative).resolve()), f"/work/{relative}"])
        command.extend(
            [
                "--proc",
                "/proc",
                "--dev",
                "/dev",
                "--size",
                "67108864",
                "--tmpfs",
                "/tmp",
                "--chdir",
                "/work",
            ]
        )
        for name, value in {
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "LD_LIBRARY_PATH": "/usr/local/lib",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": "/bundle:/bundle/scripts",
            "TMPDIR": "/work",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "OMP_NUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1",
        }.items():
            command.extend(["--setenv", name, value])
        # Applying NPROC before creating the namespace counts unrelated host-user
        # threads. Set it inside the sandbox, then replace this trusted wrapper.
        wrapper = (
            "import os,resource,sys; "
            "resource.setrlimit(resource.RLIMIT_NPROC,(64,64)); "
            "os.execv(sys.argv[1],sys.argv[1:])"
        )
        executable = "/usr/local/bin/python" if args[0] == "python" else args[0]
        command.extend(["--", "/usr/local/bin/python", "-I", "-c", wrapper, executable, *args[1:]])
        try:
            result = self.transport.run(
                command, stdin=stdin, timeout=self.timeout, output_limit=self.output_limit
            )
        except OSError as exc:
            return ProgramResult(None, stderr=str(exc), failure="container_unavailable")
        return _program_result(result, raw=raw)
