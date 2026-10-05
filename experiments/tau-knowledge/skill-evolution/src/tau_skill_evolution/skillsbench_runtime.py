"""Fresh SkillsBench terminal and grader sandboxes; no host execution fallback."""

from __future__ import annotations

import hashlib
import importlib.util
import inspect
import json
import math
import os
import re
import shutil
import stat
import subprocess
import tempfile
import uuid
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tomllib

from .artifacts import atomic_json
from .container import (
    BoundedProcessTransport,
    ContainerUnavailable,
    ProcessResult,
    ProgramResult,
    SkillEpisode,
    _episode,
    _program_result,
    _run_verifier,
    _safe_path,
)
from .skillsbench import COMMIT, SkillsBenchSource, _hash, _json_hash

_GRADER_PREFIX = "/opt/tau-grader"
_VERIFIER_PREFIX = "/.tau-verifier"
# Official graders print verbose pytest output that is never shown to a model; it is
# only scanned by _validate_grader_warmup, so it may be far larger than tool output.
_GRADER_OUTPUT_LIMIT = 16 * 1024 * 1024
_GRADER_DIAGNOSTICS_LIMIT = 1024 * 1024
# The verifier lock is resolved for CPython 3.11; images lacking exactly that (or pip)
# receive a hash-verified python-build-standalone interpreter outside the task PATH.
_UV_IMAGE = "ghcr.io/astral-sh/uv:0.9.26"
_STANDALONE_PYTHON_DIR = "/opt/tau-python"
_STANDALONE_PYTHON = _STANDALONE_PYTHON_DIR + "/python3"
_NATIVE_PYTHON = "python3"
_VERIFIER_PYTHON_PROBE = 'python3 -c "import sys, pip; assert sys.version_info[:2] == (3, 11)"'
# The astral installer skips writing $HOME/.local/bin/env when the install dir is already
# on PATH (as the grader image arranges), yet official test.sh files `source` it.
_UV_ENV_FILE = (
    '{ [ -e "$HOME/.local/bin/env" ] || printf '
    '\'#!/bin/sh\\ncase ":${PATH}:" in *:"%s":*) ;; *) export PATH="%s:$PATH" ;; esac\\n\' '
    '"$HOME/.local/bin" "$HOME/.local/bin" > "$HOME/.local/bin/env"; } 2>/dev/null || true; '
)


def _grader_bootstrap(*, prepare: bool) -> str:
    """Record successful installer calls, then permit exactly those prepared calls."""
    action = (
        'if [ "$tool" = curl ]; then local installer; '
        f"installer=$(mktemp {_GRADER_PREFIX}/installer.XXXXXX) || return; "
        'if command curl "$@" > "$installer" && command sh "$installer" >&2; then '
        f'rm "$installer"; {_UV_ENV_FILE}printf "#!/bin/sh\\nexit 0\\n"; '
        'else status=$?; rm "$installer"; touch "$failure"; return "$status"; fi; '
        'elif ! command "$tool" "$@"; then touch "$failure"; return 97; fi; '
        'printf "%s\\n" "$key" >> "$log"'
        if prepare
        else 'if ! grep -Fxq -- "$key" "$log"; then touch "$failure"; return 97; fi; '
        'if [ "$tool" = curl ]; then printf "#!/bin/sh\\nexit 0\\n"; fi'
    )
    return (
        f"log={_GRADER_PREFIX}/bootstrap.commands; failure={_GRADER_PREFIX}/bootstrap.failed; "
        'bootstrap() { local tool="$1"; shift; local key; '
        'key=$(printf "%q " "$tool" "$@"); ' + action + "; }; "
        'apt-get() { case "$1" in update|install) bootstrap apt-get "$@";; '
        '*) touch "$failure"; return 97;; esac; }; '
        'curl() { case "$*" in *https://astral.sh/uv/*install.sh*) bootstrap curl "$@";; '
        '*) command curl "$@";; esac; }; source /tests/test.sh'
    )


@dataclass(frozen=True)
class SkillsBenchRuntimeLock:
    path: Path
    value: Mapping[str, Any]

    @classmethod
    def from_file(cls, path: Path) -> SkillsBenchRuntimeLock:
        return cls(Path(path).resolve(), json.loads(Path(path).read_text()))

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


def _prepare_build_context(source: SkillsBenchSource, task_id: str, stage: Path) -> str:
    tree = json.loads((source.root / "data/skillsbench/source-tree.json").read_text())
    if tree.get("sha") != COMMIT:
        raise ContainerUnavailable("skillsbench_source_tree_invalid")
    modes = {e["path"]: e.get("mode") for e in tree["tree"] if e["type"] == "blob"}
    for entry in source.manifest["files"]:
        if entry["task_id"] != task_id or not entry["relative_path"].startswith("environment/"):
            continue
        target = stage / entry["relative_path"].removeprefix("environment/")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source.checkout / entry["path"], target)
        mode = modes[entry["path"]]
        if mode not in {"100644", "100755"}:
            raise ContainerUnavailable("skillsbench_source_mode_unsupported")
        target.chmod(0o755 if mode == "100755" else 0o644)
    recipe = (stage / "Dockerfile").read_text()
    # Released author Skills stay outside this experiment, including missing COPY skills.
    recipe = (
        "\n".join(
            line for line in recipe.splitlines() if not re.match(r"(?i)^\s*COPY\s+skills/?\s", line)
        )
        + "\n"
    )
    (stage / "Dockerfile").write_text(recipe)
    return recipe


def _missing_modules(diagnostics: str) -> list[str]:
    """Top-level names whose import failed because the module (or a name in it) is absent."""
    names = re.findall(r"No module named '([A-Za-z_]\w*)", diagnostics)
    names += re.findall(r"cannot import name '\w+' from '([A-Za-z_]\w*)'", diagnostics)
    return sorted(set(names))


def _deliverable_modules(diagnostics: str, tests: Path) -> list[str]:
    """Missing modules that the official tests import from the agent workspace.

    A module counts as an agent deliverable only when the grader image cannot import
    it, the tests' own source imports it, and that source extends sys.path (i.e. it
    reaches into the workspace); missing third-party dependencies never qualify.
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
        try:
            installed = importlib.util.find_spec(name) is not None
        except (ImportError, ValueError):
            installed = False
        if imported and not installed:
            names.append(name)
    return names


def _validate_grader_warmup(
    exit_code: int,
    reward: str | None,
    report: Any,
    diagnostics: str,
    deliverables: Sequence[str] = (),
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
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise fail("skillsbench_warmup_reward_invalid")
    if exit_code not in {0, 1}:
        raise fail("skillsbench_warmup_execution_failed")
    missing = _missing_modules(diagnostics)
    only_deliverables = bool(missing) and all(name in deliverables for name in missing)
    if re.search(r"command not found", diagnostics) or (missing and not only_deliverables):
        raise fail("skillsbench_warmup_dependency_or_collection_error")
    if not only_deliverables and re.search(
        r"ModuleNotFoundError|ImportError|ERROR collecting|errors? during collection",
        diagnostics,
    ):
        raise fail("skillsbench_warmup_dependency_or_collection_error")
    if report is not None and not only_deliverables:
        summary = report.get("results", {}).get("summary", {})
        if not isinstance(summary.get("tests"), int) or summary["tests"] <= 0:
            raise fail("skillsbench_warmup_no_collected_checks")
        if summary.get("errors", 0) or any(
            t.get("status") in {"broken", "error"}
            for t in report.get("results", {}).get("tests", [])
        ):
            raise fail("skillsbench_warmup_dependency_or_collection_error")


def _verifier_python_mode(docker: str, image: str) -> str:
    """Use the image's own interpreter only when it matches the verifier lock resolution."""
    probe = subprocess.run(
        [docker, "run", "--rm", "--network", "none", "--entrypoint", "/bin/sh", image, "-c"]
        + [_VERIFIER_PYTHON_PROBE],
        capture_output=True,
    )
    return "native" if probe.returncode == 0 else "standalone"


def _standalone_python_layer() -> str:
    """Dockerfile lines adding a hash-verified CPython 3.11 outside the task's PATH."""
    return (
        f"COPY --from={_UV_IMAGE} /uv /usr/local/bin/tau-uv\n"
        "RUN /usr/local/bin/tau-uv python install 3.11 --no-cache --no-bin --no-registry "
        f"--install-dir {_STANDALONE_PYTHON_DIR} && ln -s "
        f'"$(ls -d {_STANDALONE_PYTHON_DIR}/cpython-3.11*/bin/python3.11 | head -n1)" '
        f"{_STANDALONE_PYTHON}\n"
    )


def _grader_warmup_driver() -> str:
    """Self-contained build-time driver: run the official grader once without a solution."""
    return (
        "from __future__ import annotations\n"
        "import importlib.util, json, math, re, shutil, subprocess\nfrom pathlib import Path\n"
        + inspect.getsource(_missing_modules)
        + "\n"
        + inspect.getsource(_deliverable_modules)
        + "\n"
        + inspect.getsource(_validate_grader_warmup)
        + "\nshutil.rmtree('/logs/verifier', ignore_errors=True)\n"
        "Path('/logs/verifier').mkdir(parents=True)\n"
        f"Path('{_GRADER_PREFIX}/bootstrap.commands').touch()\n"
        f"result = subprocess.run(['/bin/bash', '-c', {_grader_bootstrap(prepare=True)!r}], "
        "capture_output=True)\n"
        f"if Path('{_GRADER_PREFIX}/bootstrap.failed').exists(): "
        "raise RuntimeError('skillsbench_warmup_bootstrap_failed')\n"
        "reward = Path('/logs/verifier/reward.txt')\n"
        "report = Path('/logs/verifier/ctrf.json')\n"
        "diagnostics = (result.stdout + result.stderr)"
        f"[-{_GRADER_DIAGNOSTICS_LIMIT}:].decode('utf-8', 'replace')\n"
        "deliverables = _deliverable_modules(diagnostics, Path('/tests'))\n"
        "_validate_grader_warmup(result.returncode, "
        "reward.read_text() if reward.is_file() else None, "
        "json.loads(report.read_text()) if report.is_file() else None, "
        "diagnostics, deliverables)\n"
        f"Path('{_GRADER_PREFIX}/warmup.json').write_text(json.dumps({{"
        "'reward': float(reward.read_text().strip()), 'exit_code': result.returncode, "
        "'missing_deliverable_modules': deliverables}, sort_keys=True))\n"
    )


def prepare_docker(root: Path, task_id: str) -> dict[str, Any]:
    """Build task and separate private grader images only when the daemon is accessible."""
    root = Path(root).resolve()
    source = SkillsBenchSource(root)
    source.validate()
    if task_id not in source.manifest["tasks"]:
        raise ValueError("unknown_skillsbench_task")
    directory = source.checkout / "tasks" / task_id
    docker = shutil.which("docker")
    if not docker or subprocess.run([docker, "info"], capture_output=True, timeout=10).returncode:
        raise ContainerUnavailable("skillsbench_docker_daemon_unavailable")
    image = f"tau-skillsbench-{task_id}:{COMMIT[:12]}"
    runtime_image, grader = image + "-runtime", image + "-grader"
    environment = source.manifest["environments"][task_id]
    # The author checkout stays untouched; only explicitly public build context is copied.
    with tempfile.TemporaryDirectory(prefix="sb-environment-build-") as temp:
        stage = Path(temp)
        recipe = _prepare_build_context(source, task_id, stage)
        subprocess.run([docker, "build", "-t", image, str(stage)], check=True)
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
            f"FROM {image}\nUSER root\n{python_layer}"
            "COPY requirements.lock /tmp/runtime-requirements.lock\n"
            f"RUN {installer} -r /tmp/runtime-requirements.lock "
            "&& rm /tmp/runtime-requirements.lock\n"
            "RUN mkdir -p /bundle /work\n"
        )
        subprocess.run([docker, "build", "-t", runtime_image, str(stage)], check=True)
    with tempfile.TemporaryDirectory(prefix="sb-grader-build-") as temp:
        stage = Path(temp)
        shutil.copytree(directory / "tests", stage / "tests")
        warmup = _grader_warmup_driver()
        (stage / "warmup.py").write_text(warmup)
        (stage / "Dockerfile").write_text(
            f"FROM {image}\nUSER root\n{python_layer}"
            f"ENV HOME={_GRADER_PREFIX}/home UV_CACHE_DIR={_GRADER_PREFIX}/cache "
            f"XDG_CACHE_HOME={_GRADER_PREFIX}/cache\n"
            f"ENV PATH={_GRADER_PREFIX}/home/.local/bin:${{PATH}}\n"
            f"RUN mkdir -p {_GRADER_PREFIX}/home {_GRADER_PREFIX}/cache /logs/verifier\n"
            "COPY tests /tests\n"
            "COPY warmup.py /tmp/grader-warmup.py\n"
            f"RUN {verifier_python} -I /tmp/grader-warmup.py && rm /tmp/grader-warmup.py "
            "&& rm -rf /logs\n"
        )
        subprocess.run([docker, "build", "-t", grader, str(stage)], check=True)
    identities = {}
    for name, reference in (("environment", image), ("runtime", runtime_image), ("grader", grader)):
        metadata = json.loads(subprocess.check_output([docker, "image", "inspect", reference]))[0]
        identities[name] = {
            "image": reference,
            "digest": metadata["Id"],
            "digest_kind": "image_id",
            "environment": metadata["Config"].get("Env") or [],
        }
    run = [docker, "run", "--rm", "--network", "none", "--entrypoint"]
    identities["runtime"]["verifier_python"] = verifier_python
    identities["runtime"]["verifier_python_version"] = json.loads(
        subprocess.check_output(
            run
            + [verifier_python, runtime_image, "-I", "-c"]
            + ["import json, sys; print(json.dumps(list(sys.version_info[:3])))"]
        )
    )
    warmup_result = json.loads(
        subprocess.check_output(run + ["cat", grader, f"{_GRADER_PREFIX}/warmup.json"])
    )
    lock = {
        "task_id": task_id,
        "commit": COMMIT,
        "images": identities,
        "verifier_python_mode": mode,
        "grader_warmup": {
            key: warmup_result[key]
            for key in ("reward", "exit_code", "missing_deliverable_modules")
        },
        "dockerfile_sha256": _hash(directory / "environment/Dockerfile"),
        "public_manifest_hash": source.manifest["manifest_hash"],
        "dependency_hash": _hash(requirements),
        "resources": tomllib.loads((directory / "task.toml").read_text())["environment"],
        "layout": environment,
        "author_skill_copy_removed": recipe != (directory / "environment/Dockerfile").read_text(),
        "adapted_dockerfile_sha256": hashlib.sha256(recipe.encode()).hexdigest(),
        "grader_warmup_sha256": hashlib.sha256(warmup.encode()).hexdigest(),
        "grader_bootstrap_sha256": hashlib.sha256(
            _grader_bootstrap(prepare=False).encode()
        ).hexdigest(),
    }
    atomic_json(root / f"runtime/skillsbench-docker-{task_id}-lock.json", lock)
    return {"ready": True, **lock}


class SkillsBenchRunner:
    def __init__(self, root: Path, task_id: str, *, demo: bool, transport: Any = None):
        self.root, self.task_id, self.demo = Path(root).resolve(), task_id, demo
        self.source = SkillsBenchSource(root)
        self.task_directory = self.source.checkout / "tasks" / task_id
        self.config = tomllib.loads((self.task_directory / "task.toml").read_text())
        self.transport = transport or BoundedProcessTransport(kill_process_group=True)
        self.timeout, self.output_limit = 60.0, 65536
        self.cpu = min(os.sched_getaffinity(0))
        self.verifier_artifacts: Path | None = None
        self.workspace_mounts: dict[str, Path] = {}
        self.grader_cache: Path | None = None
        self.grader_diagnostics: str | None = None

    def _lock(self) -> SkillsBenchRuntimeLock:
        return SkillsBenchRuntimeLock.from_file(
            self.root / "runtime/skillsbench-bubblewrap-lock.json"
        )

    def _command(
        self, package: Path, work: Path, args: Sequence[str], *, grader: bool = False
    ) -> list[str]:
        if not self.demo:
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
            "--ro-bind",
            str(self._lock().rootfs),
            "/",
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
        if self.verifier_artifacts is not None:
            for entry in sorted(self.verifier_artifacts.iterdir()):
                if entry.is_symlink() or not (entry.is_dir() or entry.is_file()):
                    raise ValueError("skillsbench_artifact_mount_not_regular")
                command += ["--ro-bind", str(entry), "/" + entry.name]
            command += ["--bind", str(work), "/work", "--chdir", "/work"]
        else:
            command += ["--bind", str(work), "/root", "--chdir", "/root"]
            for entry in self.source.task(self.task_id)["public_input_manifest"]:
                relative = entry["relative_path"].removeprefix("environment/")
                original = self.task_directory / "environment" / _safe_path(relative)
                for destination in entry["sandbox_paths"]:
                    if not destination.startswith("/root/"):
                        raise ContainerUnavailable("skillsbench_demo_layout_not_prepared")
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
        if not grader:
            environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
        for name, value in environment.items():
            command += ["--setenv", name, value]
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
            *("/usr/local/bin/python" if args[0] == "python" else args[0], *args[1:]),
        ]
        return command

    def _docker_command(
        self, package: Path, work: Path, args: Sequence[str], *, grader: bool
    ) -> list[str]:
        path = self.root / f"runtime/skillsbench-docker-{self.task_id}-lock.json"
        value = json.loads(path.read_text())
        role = "grader" if grader else "runtime" if self.verifier_artifacts else "environment"
        identity = value["images"][role]
        image = identity["digest"]
        resources = self.config["environment"]
        command = [
            "docker",
            "run",
            "--rm",
            "--interactive",
            "--name",
            "tau-sb-" + uuid.uuid4().hex,
            "--network",
            "bridge"
            if not grader
            and self.verifier_artifacts is None
            and resources.get("allow_internet") is True
            else "none",
            "--read-only",
            "--user",
            "10001:10001",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--cpus",
            str(resources.get("cpus", 1)),
            "--memory",
            f"{resources.get('memory_mb', 1024)}m",
            "--memory-swap",
            f"{resources.get('memory_mb', 1024)}m",
            "--pids-limit",
            "64",
            "--workdir",
            "/work" if self.verifier_artifacts else value["layout"]["workdir"],
            "--mount",
            f"type=bind,src={package},dst=/bundle,readonly",
        ]
        if self.verifier_artifacts is not None:
            for entry in sorted(self.verifier_artifacts.iterdir()):
                if entry.is_symlink() or not (entry.is_dir() or entry.is_file()):
                    raise ValueError("skillsbench_artifact_mount_not_regular")
                command += ["--mount", f"type=bind,src={entry},dst=/{entry.name},readonly"]
            command += ["--mount", f"type=bind,src={work},dst=/work"]
        else:
            for destination, directory in self.workspace_mounts.items():
                command += ["--mount", f"type=bind,src={directory},dst={destination}"]
        if grader:
            if self.grader_cache is None:
                raise ContainerUnavailable("skillsbench_grader_cache_not_initialized")
            command += [
                "--mount",
                f"type=bind,src={work.parent / 'grader-logs'},dst=/logs/verifier",
                "--mount",
                f"type=bind,src={self.grader_cache},dst={_GRADER_PREFIX}",
            ]
        environment = dict(x.split("=", 1) for x in identity["environment"] if "=" in x)
        environment.update(
            {
                "PYTHONPATH": "/bundle:/bundle/scripts",
                "PYTHONDONTWRITEBYTECODE": "1",
                "PIP_NO_INDEX": "1",
                "PIP_DISABLE_PIP_VERSION_CHECK": "1",
                "OPENBLAS_NUM_THREADS": "1",
                "OMP_NUM_THREADS": "1",
                "NUMEXPR_NUM_THREADS": "1",
            }
        )
        environment.setdefault("HOME", "/root")
        environment.setdefault("PATH", "/usr/local/bin:/usr/bin:/bin")
        if grader:
            environment["UV_OFFLINE"] = "1"
        if not grader:
            environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
        args = [_NATIVE_PYTHON if args[0] == "python" else args[0], *args[1:]]
        if self.verifier_artifacts is not None:
            if args[0] != _NATIVE_PYTHON:
                raise ValueError("skillsbench_verifier_requires_python")
            # Locks built before the standalone fallback existed always used the task python.
            interpreter = identity.get("verifier_python", _NATIVE_PYTHON)
            if args[1:3] == ["-I", "-c"]:
                args[0] = interpreter
                args[3] = f"import sys; sys.path.insert(0, {_VERIFIER_PREFIX!r}); " + args[3]
            else:
                code = (
                    f"import sys,runpy; sys.path.insert(0, {_VERIFIER_PREFIX!r}); "
                    "runpy.run_path(sys.argv[1],run_name='__main__')"
                )
                script = args[2:] if len(args) > 1 and args[1] == "-I" else args[1:]
                args = [interpreter, "-I", "-c", code, *script]
        command += [
            "--tmpfs",
            "/tmp:rw,nosuid,nodev,size=64m",
            "--entrypoint",
            "/usr/bin/env",
            image,
            "-i",
            *[f"{k}={v}" for k, v in environment.items()],
            *args,
        ]
        return command

    def _raw(
        self,
        package: Path,
        work: Path,
        args: Sequence[str],
        stdin: bytes = b"",
        *,
        grader: bool = False,
    ) -> Any:
        timeout = float(self.config["verifier"]["timeout_sec"]) if grader else self.timeout
        output_limit = _GRADER_OUTPUT_LIMIT if grader else self.output_limit
        command = self._command(package.resolve(), work.resolve(), args, grader=grader)
        if self.demo:
            return self.transport.run(
                command, stdin=stdin, timeout=timeout, output_limit=output_limit
            )
        name = command[command.index("--name") + 1]
        try:
            result = self.transport.run(
                command, stdin=stdin, timeout=timeout, output_limit=output_limit
            )
        finally:
            cleanup = self.transport.run(
                ["docker", "rm", "--force", "--volumes", name],
                stdin=b"",
                timeout=10,
                output_limit=65536,
            )
        if cleanup.failure or (cleanup.returncode and b"No such container" not in cleanup.stderr):
            return ProcessResult(result.returncode, result.stdout, result.stderr, "cleanup_failed")
        return result

    def _run(
        self, package: Path, work: Path, args: Sequence[str], stdin: bytes = b""
    ) -> ProgramResult:
        try:
            return _program_result(self._raw(package, work, args, stdin))
        except OSError:
            return ProgramResult(None, failure="container_unavailable")

    def terminal(self, episode: SkillEpisode, command: str) -> ProgramResult:
        if not isinstance(command, str) or not command.strip():
            raise ValueError("terminal_command_must_be_nonempty")
        result = self._raw(episode.package, episode.work, ["/bin/bash", "-c", command])
        return ProgramResult(
            result.returncode,
            result.stdout.decode("utf-8", "replace"),
            result.stderr.decode("utf-8", "replace"),
            result.failure,
        )

    @contextmanager
    def episode(self, bundle: Any) -> Iterator[SkillEpisode]:
        if self.demo:
            self._lock().validate(self.task_id)
        else:
            self._docker_lock()
        with _episode(self, bundle) as episode:
            layout = self.source.task(self.task_id)["environment"]
            if self.demo:
                if layout["workdir"] != "/root":
                    raise ContainerUnavailable("skillsbench_demo_layout_not_prepared")
                for entry in self.source.task(self.task_id)["public_input_manifest"]:
                    for destination in entry["sandbox_paths"]:
                        if not destination.startswith("/root/"):
                            raise ContainerUnavailable("skillsbench_demo_layout_not_prepared")
                        target = episode.work / _safe_path(destination.removeprefix("/root/"))
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(self.task_directory / entry["relative_path"], target)
                        target.chmod(0o444)
            else:
                self._initialize_docker_workspace(episode, layout)
            try:
                yield episode
            finally:
                self.workspace_mounts = {}

    def _initialize_docker_workspace(
        self, episode: SkillEpisode, layout: Mapping[str, Any]
    ) -> None:
        """Copy fresh writable task paths from the locked public image, preserving its layout."""
        lock = self._docker_lock()
        directories = {}
        for destination in layout["workspace_roots"]:
            target = episode.work / destination.lstrip("/")
            target.mkdir()
            directories[destination] = target
        self._copy_image_directories(lock["images"]["environment"]["digest"], directories)
        self.workspace_mounts = directories

    def _copy_image_directories(
        self, image: str, directories: Mapping[str, Path], *, allow_missing: bool = True
    ) -> None:
        name = "tau-sb-init-" + uuid.uuid4().hex
        created = self.transport.run(
            ["docker", "create", "--name", name, image],
            stdin=b"",
            timeout=10,
            output_limit=65536,
        )
        try:
            if created.returncode or created.failure:
                raise ContainerUnavailable("skillsbench_workspace_initialization_failed")
            for destination, target in directories.items():
                copied = self.transport.run(
                    ["docker", "cp", name + ":" + destination + "/.", str(target)],
                    stdin=b"",
                    timeout=60,
                    output_limit=65536,
                )
                if copied.failure or (
                    copied.returncode
                    and (not allow_missing or b"Could not find" not in copied.stderr)
                ):
                    raise ContainerUnavailable("skillsbench_workspace_copy_failed")
                for file in target.rglob("*"):
                    if not file.is_symlink():
                        file.chmod(
                            0o777 if file.is_dir() else stat.S_IMODE(file.stat().st_mode) | 0o666
                        )
                target.chmod(0o777)
        finally:
            cleanup = self.transport.run(
                ["docker", "rm", "--force", "--volumes", name],
                stdin=b"",
                timeout=10,
                output_limit=65536,
            )
            if cleanup.failure or cleanup.returncode:
                raise ContainerUnavailable("skillsbench_workspace_cleanup_failed")

    def _docker_lock(self) -> dict[str, Any]:
        value = json.loads(
            (self.root / f"runtime/skillsbench-docker-{self.task_id}-lock.json").read_text()
        )
        if (
            value.get("commit") != COMMIT
            or value.get("task_id") != self.task_id
            or value.get("dockerfile_sha256")
            != _hash(self.task_directory / "environment/Dockerfile")
            or value.get("public_manifest_hash") != self.source.manifest["manifest_hash"]
            or value.get("dependency_hash")
            != _hash(self.root / "runtime/skillsbench-verifier-requirements.lock")
            or value.get("grader_bootstrap_sha256")
            != hashlib.sha256(_grader_bootstrap(prepare=False).encode()).hexdigest()
            or value.get("resources") != self.config["environment"]
            or value.get("layout") != self.source.manifest["environments"][self.task_id]
            or set(value.get("images", {})) != {"environment", "runtime", "grader"}
        ):
            raise ContainerUnavailable("skillsbench_docker_lock_invalid")
        # Locks predating the standalone fallback carry neither key and used the task python.
        mode = value.get("verifier_python_mode", "native")
        interpreter = value["images"]["runtime"].get("verifier_python", _NATIVE_PYTHON)
        warmup = value.get("grader_warmup", {"missing_deliverable_modules": []})
        if (
            mode not in {"native", "standalone"}
            or interpreter != (_NATIVE_PYTHON if mode == "native" else _STANDALONE_PYTHON)
            or not isinstance(warmup, Mapping)
            or not isinstance(warmup.get("missing_deliverable_modules"), list)
            or not all(
                isinstance(name, str) and re.fullmatch(r"[A-Za-z_]\w*", name)
                for name in warmup["missing_deliverable_modules"]
            )
        ):
            raise ContainerUnavailable("skillsbench_docker_lock_invalid")
        for image in value["images"].values():
            if not re.fullmatch(r"sha256:[0-9a-f]{64}", image.get("digest", "")):
                raise ContainerUnavailable("skillsbench_image_digest_not_prepared")
            result = self.transport.run(
                ["docker", "image", "inspect", image["digest"]],
                stdin=b"",
                timeout=10,
                output_limit=65536,
            )
            if result.returncode or result.failure:
                raise ContainerUnavailable("skillsbench_locked_image_missing")
        grader_env = dict(
            x.split("=", 1) for x in value["images"]["grader"]["environment"] if "=" in x
        )
        if (
            grader_env.get("HOME") != _GRADER_PREFIX + "/home"
            or grader_env.get("UV_CACHE_DIR") != _GRADER_PREFIX + "/cache"
        ):
            raise ContainerUnavailable("skillsbench_grader_cache_lock_invalid")
        return value

    def grade(self, episode: SkillEpisode) -> dict[str, Any]:
        logs = episode.work.parent / "grader-logs"
        logs.mkdir(mode=0o777)
        logs.chmod(0o777)
        empty = episode.work.parent / "grader-package"
        empty.mkdir()
        deliverables: list[str] = []
        self.grader_diagnostics = None
        if self.demo:
            result = self._raw(empty, episode.work, ["/bin/bash", "/tests/test.sh"], grader=True)
        else:
            self.grader_cache = episode.work.parent / "grader-runtime"
            self.grader_cache.mkdir()
            try:
                lock = self._docker_lock()
                deliverables = list(
                    lock.get("grader_warmup", {}).get("missing_deliverable_modules", [])
                )
                self._copy_image_directories(
                    lock["images"]["grader"]["digest"],
                    {_GRADER_PREFIX: self.grader_cache},
                    allow_missing=False,
                )
                if not (self.grader_cache / "bootstrap.commands").is_file():
                    raise ContainerUnavailable("skillsbench_grader_bootstrap_not_prepared")
                result = self._raw(
                    empty,
                    episode.work,
                    ["/bin/bash", "-c", _grader_bootstrap(prepare=False)],
                    grader=True,
                )
                if (self.grader_cache / "bootstrap.failed").exists():
                    result = ProcessResult(
                        result.returncode, result.stdout, result.stderr, "grader_bootstrap_failed"
                    )
            finally:
                self.grader_cache = None
        reward = logs / "reward.txt"
        if result.failure or not reward.is_file():
            return {
                "utility": None,
                "reward": None,
                "status": "NOT_MEASURED",
                "failure": result.failure or "official_reward_missing",
                "official_checks": None,
            }
        try:
            measured = float(reward.read_text().strip())
        except ValueError:
            return {
                "utility": None,
                "reward": None,
                "status": "NOT_MEASURED",
                "failure": "official_reward_invalid",
                "official_checks": None,
            }
        if not math.isfinite(measured) or not 0 <= measured <= 1:
            return {
                "utility": None,
                "reward": None,
                "status": "NOT_MEASURED",
                "failure": "official_reward_invalid",
                "official_checks": None,
            }
        checks = None
        report = logs / "ctrf.json"
        # Grader output never reaches a model; a bounded tail is kept only for preflight's
        # re-validation and for the classification of missing agent deliverables.
        self.grader_diagnostics = (
            (result.stdout + result.stderr)[-_GRADER_DIAGNOSTICS_LIMIT:]
        ).decode("utf-8", "replace")
        try:
            data = json.loads(report.read_text()) if report.is_file() else None
            _validate_grader_warmup(
                result.returncode, str(measured), data, self.grader_diagnostics, deliverables
            )
        except (RuntimeError, ValueError, TypeError, AttributeError):
            return {
                "utility": None,
                "reward": None,
                "status": "NOT_MEASURED",
                "failure": "official_grader_program_error",
                "official_checks": None,
            }
        if data is not None:
            summary = data.get("results", {}).get("summary", {})
            total = summary.get("tests")
            if isinstance(total, int) and total > 0:
                checks = {
                    "status": "MEASURED",
                    "passed": summary.get("passed"),
                    "total": total,
                    "rate": summary.get("passed", 0) / total,
                }
        if checks is None:
            checks = {"status": "NOT_MEASURED", "passed": None, "total": None, "rate": None}
        return {
            "status": "MEASURED",
            "utility": measured == 1,
            "reward": measured,
            "official_checks": checks,
            "grader_exit_code": result.returncode,
        }

    def run_verifier(
        self,
        public_inputs: Mapping[str, Any],
        frozen_base: Mapping[str, Any],
        trace: Mapping[str, Any],
        test_files: Mapping[str, str],
    ) -> ProgramResult:
        path = Path(trace["public_artifacts_dir"]).resolve(strict=True)
        manifest = json.loads((path.parent / "snapshot.json").read_text())
        if manifest["snapshot_hash"] != trace["public_artifacts_hash"]:
            raise ValueError("skillsbench_public_snapshot_hash_mismatch")
        expected = {x["path"]: x["sha256"] for x in manifest["files"]}
        actual = {}
        for file in path.rglob("*"):
            if file.is_symlink():
                raise ValueError("skillsbench_public_snapshot_symlink")
            if file.is_file():
                actual[file.relative_to(path).as_posix()] = _hash(file)
        if actual != expected or _json_hash(manifest["files"]) != manifest["snapshot_hash"]:
            raise ValueError("skillsbench_public_snapshot_corrupt")
        public_trace = {k: v for k, v in trace.items() if k != "public_artifacts_dir"}
        self.verifier_artifacts = path
        try:
            return _run_verifier(self, public_inputs, frozen_base, public_trace, test_files)
        finally:
            self.verifier_artifacts = None

    def preflight(self, *, validate_source: bool = True) -> dict[str, Any]:
        checks: dict[str, Any] = {
            "demo_only": self.demo,
            "aggregate_limits_enforced": not self.demo,
        }
        try:
            if validate_source:
                self.source.validate()
            checks["source"] = True
            if self.demo:
                self._lock().validate(self.task_id)
                checks["runtime_lock"] = True
                checks["commands"] = all(shutil.which(x) for x in ("bwrap", "prlimit", "taskset"))
            else:
                self._docker_lock()
                checks["runtime_lock"] = True
                checks["commands"] = shutil.which("docker") is not None
            checks["dependencies"] = False
            if not self.demo:
                checks["official_grader"] = False
            if checks["commands"]:
                from .artifacts import SkillBundle

                code = "import json,sys; print(json.dumps(list(sys.version_info[:3])))"
                if self.demo:
                    code = (
                        "import json,sys,importlib.metadata as m; "
                        "print(json.dumps({'python':list(sys.version_info[:3]),"
                        "'dependencies':{n:m.version(n) for n in "
                        "('numpy','pandas','pytest','pytest-json-ctrf','pip')}}))"
                    )
                    probe = ["python", "-I", "-c", code]
                else:
                    # Task images need not ship Python (Java, Erlang, Lean, ...): the agent
                    # only gets bash there and the verifier runs in the runtime image.
                    probe = [
                        "/bin/bash",
                        "-c",
                        f"if command -v python3 >/dev/null 2>&1; then exec python3 -I -c '{code}'; "
                        "fi; echo null",
                    ]
                with self.episode(SkillBundle(files={"SKILL.md": "Runtime preflight"})) as episode:
                    result = self._run(episode.package, episode.work, probe)
                    if not self.demo:
                        checks["task_python"] = result.output
                        self.verifier_artifacts = episode.work.parent / "verifier-public"
                        self.verifier_artifacts.mkdir()
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
                            and verifier.exit_code == 0
                            and verifier.output == {"pytest": "8.4.1", "pytest-json-ctrf": "0.3.5"}
                        )
                        if not checks["verifier_dependencies"]:
                            checks["verifier_dependencies_error"] = verifier.to_dict()
                        # This fresh, unsolved episode tests admission under the
                        # actual private grader mounts and runtime restrictions.
                        # A legitimate zero reward is sufficient; it is not an
                        # experiment measurement and never reaches a model.
                        grade = self.grade(episode)
                        reward = grade.get("reward")
                        checks["official_grader"] = (
                            grade.get("status") == "MEASURED"
                            and isinstance(reward, (int, float))
                            and not isinstance(reward, bool)
                            and math.isfinite(reward)
                            and 0 <= reward <= 1
                            and grade.get("grader_exit_code") in {0, 1}
                        )
                        if checks["official_grader"]:
                            report = episode.work.parent / "grader-logs/ctrf.json"
                            deliverables = (
                                self._docker_lock()
                                .get("grader_warmup", {})
                                .get("missing_deliverable_modules", [])
                            )
                            try:
                                _validate_grader_warmup(
                                    grade["grader_exit_code"],
                                    str(reward),
                                    json.loads(report.read_text()) if report.is_file() else None,
                                    self.grader_diagnostics or "",
                                    deliverables,
                                )
                            except RuntimeError:
                                checks["official_grader"] = False
                                checks["official_grader_error"] = "official_grader_program_error"
                        checks["official_grader_probe"] = {
                            "purpose": "runtime_admission",
                            "experiment_measurement": False,
                            "status": "PASSED" if checks["official_grader"] else "FAILED",
                        }
                        if not checks["official_grader"]:
                            checks.setdefault(
                                "official_grader_error",
                                grade.get("failure", "official_grader_not_measured"),
                            )
                checks["dependencies"] = (
                    result.failure is None
                    and result.exit_code == 0
                    and (
                        not self.demo
                        or result.output
                        == {
                            "python": [3, 11, 14],
                            "dependencies": self._lock().value["dependencies"],
                        }
                    )
                )
                if not checks["dependencies"]:
                    checks["dependencies_error"] = result.to_dict()
            checks["ready"] = (
                checks["commands"]
                and checks["dependencies"]
                and checks.get("verifier_dependencies", True)
                and checks.get("official_grader", True)
            )
        except (OSError, ValueError, RuntimeError) as exc:
            checks.update(ready=False, error=str(exc))
        return checks
