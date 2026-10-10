"""Run the pinned author's Codex adapter inside a fresh SkillsBench episode."""

from __future__ import annotations

import asyncio
import hashlib
import json
import shlex
import shutil
import subprocess
import tempfile
import time
from collections.abc import Mapping
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path
from typing import Any

from .container import ContainerUnavailable

AUTHOR_COMMIT = "4380d4bff673dd6e1d58e5babeb2aaa0fe527119"
HARBOR_COMMIT = "3f28e5ce2acbff36d8b5df431e35e050ac13bef6"
_HOME = "/installed-agent/codex-home"
_LOG = "/logs/agent/codex.txt"
_OUTPUT_LIMIT = 32 * 1024 * 1024


@dataclass(frozen=True)
class CodexProvider:
    """The episode gateway handles provider credentials outside the task container."""

    model: str
    base_url: str
    reasoning_effort: str = "high"
    binary: Path | None = None
    code_mode_host: Path | None = None
    relay_command: tuple[str, ...] = ()
    context_window: int = 272_000
    input_token_limit: int = 114_688

    def config(self) -> str:
        # JSON strings are valid TOML basic strings and avoid shell interpolation.
        quote = json.dumps
        return (
            f"model = {quote(self.model)}\n"
            'model_provider = "episode_gateway"\n'
            f"model_reasoning_effort = {quote(self.reasoning_effort)}\n"
            f"model_context_window = {self.context_window}\n"
            f"model_auto_compact_token_limit = {int(self.input_token_limit * 0.85)}\n"
            'web_search = "disabled"\n'
            "[model_providers.episode_gateway]\n"
            'name = "Bedrock episode gateway"\n'
            f"base_url = {quote(self.base_url)}\n"
            'wire_api = "responses"\n'
            "requires_openai_auth = false\n"
            "request_max_retries = 0\n"
            "stream_max_retries = 0\n"
            "[agents]\n"
            "enabled = false\n"
            "[features]\n"
            "multi_agent = false\n"
            "multi_agent_v2 = false\n"
        )


def _author_source() -> dict[str, Any]:
    directory = Path(__file__).with_name("author")
    value = json.loads((directory / "SOURCE.json").read_text())
    digest = hashlib.sha256((directory / "codex_skill_only.py").read_bytes()).hexdigest()
    if (
        value.get("commit") != AUTHOR_COMMIT
        or value.get("harbor_commit") != HARBOR_COMMIT
        or value.get("sha256") != digest
        or value.get("adaptations") != []
    ):
        raise ContainerUnavailable("codex_author_source_hash_mismatch")
    return value


def codex_identity(binary: Path | Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Check local installation without contacting a provider."""
    source = _author_source()
    settings = binary if isinstance(binary, Mapping) else {}
    configured = settings.get("binary", "codex") if settings else binary
    if isinstance(configured, str):
        configured = Path(shutil.which(configured) or configured)
    candidate = configured or Path(shutil.which("codex") or "")
    if not candidate.is_file():
        raise ContainerUnavailable("codex_cli_not_installed")
    candidate = candidate.resolve()
    # A copied npm launcher is insufficient: use the native executable it launches.
    with candidate.open("rb") as stream:
        if stream.read(4) != b"\x7fELF":
            raise ContainerUnavailable("codex_cli_native_binary_required")
    version = subprocess.run(
        [str(candidate), "--version"], capture_output=True, text=True, timeout=15, check=True
    ).stdout.strip()
    cli_sha256 = hashlib.sha256(candidate.read_bytes()).hexdigest()
    if settings.get("version") and version != "codex-cli " + str(settings["version"]):
        raise ContainerUnavailable("codex_cli_version_mismatch")
    if settings.get("binary_sha256") and cli_sha256 != settings["binary_sha256"]:
        raise ContainerUnavailable("codex_cli_hash_mismatch")
    companion_path = settings.get("code_mode_host_binary") or candidate.with_name(
        "codex-code-mode-host"
    )
    if isinstance(companion_path, str):
        companion_path = shutil.which(companion_path) or companion_path
    companion = Path(companion_path).expanduser().resolve()
    companion_identity: dict[str, Any] = {}
    if companion.is_file():
        with companion.open("rb") as stream:
            if stream.read(4) != b"\x7fELF":
                raise ContainerUnavailable("codex_code_mode_host_native_binary_required")
        companion_hash = hashlib.sha256(companion.read_bytes()).hexdigest()
        if (
            settings.get("code_mode_host_sha256")
            and companion_hash != settings["code_mode_host_sha256"]
        ):
            raise ContainerUnavailable("codex_code_mode_host_hash_mismatch")
        companion_identity = {
            "code_mode_host_binary": str(companion),
            "code_mode_host_sha256": companion_hash,
        }
    elif settings.get("code_mode_host_binary"):
        raise ContainerUnavailable("codex_code_mode_host_not_installed")
    try:
        installed = distribution("harbor")
    except PackageNotFoundError as exc:
        raise ContainerUnavailable("codex_pinned_harbor_not_installed") from exc
    direct_url = json.loads(installed.read_text("direct_url.json") or "{}")
    if direct_url.get("vcs_info", {}).get("commit_id") != HARBOR_COMMIT:
        raise ContainerUnavailable("codex_harbor_commit_mismatch")
    for relative, expected in source["harbor_source_hashes"].items():
        path = Path(installed.locate_file("harbor/" + relative))
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ContainerUnavailable("codex_harbor_source_hash_mismatch")
    return {
        "framework": "author-codex",
        "author_commit": AUTHOR_COMMIT,
        "author_source_sha256": source["sha256"],
        "harbor_commit": HARBOR_COMMIT,
        "cli_version": version,
        "codex_version": version.removeprefix("codex-cli "),
        "cli_sha256": cli_sha256,
        "binary_sha256": cli_sha256,
        "harbor_source_hashes": source["harbor_source_hashes"],
        "binary": str(candidate),
        **companion_identity,
    }


class _EpisodeEnvironment:
    """Map the actual Harbor agent's environment interface to our live container."""

    def __init__(self, runner: Any, logs_dir: Path):
        self.runner, self.logs_dir = runner, logs_dir
        self.executions: list[dict[str, Any]] = []
        self.last_agent_result: Any = None
        self.relay_identity: tuple[int, int] | None = None

    def _run(
        self, command: list[str], *, timeout: float, stdin: bytes = b"", output_limit: int = 65536
    ) -> Any:
        from .skillsbench_runtime import _host_environment

        return self.runner.transport.run(
            command,
            stdin=stdin,
            timeout=timeout,
            output_limit=output_limit,
            env=_host_environment(),
        )

    def shell(self, command: str, *, timeout: float = 30, root: bool = False) -> Any:
        arguments = ["docker", "exec", "--interactive"]
        if root:
            arguments += ["--user", "root"]
        arguments += [self.runner.container_name, "/bin/bash", "-c", command]
        return self._run(arguments, timeout=timeout)

    async def exec(
        self,
        command: str,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout_sec: int | None = None,
    ) -> Any:
        from harbor.environments.base import ExecResult

        if not self.runner.public_open:
            raise PermissionError("skillsbench_public_episode_closed")
        if env:
            # The local proxy is unauthenticated; never inject a provider key here.
            raise ValueError("codex_task_environment_credentials_forbidden")
        arguments = ["docker", "exec", "--interactive", "--workdir"]
        arguments += [cwd or self.runner.source.task(self.runner.task_id)["environment"]["workdir"]]
        is_agent = "codex exec " in command
        if is_agent and hasattr(self.runner, "attack_shell_command"):
            command = self.runner.attack_shell_command(command)
        arguments += [self.runner.container_name, "/bin/bash", "-c", command]
        budget = self.runner.agent_timeout_seconds or self.runner.config["agent"]["timeout_sec"]
        remaining = budget - (time.monotonic() - self.runner.episode_started)
        timeout = max(0.1, remaining) if is_agent else float(timeout_sec or 30)
        phase_remaining = self.runner.phase_remaining()
        if phase_remaining <= 0:
            raise TimeoutError("skillsbench_execution_deadline_exhausted")
        timeout = min(timeout, phase_remaining)
        result = self._run(arguments, timeout=timeout, output_limit=_OUTPUT_LIMIT)
        if is_agent and hasattr(self.runner, "record_attack_output"):
            self.runner.record_attack_output(result.stdout, result.stderr)
            if hasattr(self.runner, "redact_attack_output"):
                result = type(result)(
                    result.returncode,
                    self.runner.redact_attack_output(result.stdout),
                    self.runner.redact_attack_output(result.stderr),
                    result.failure,
                )
        self.executions.append(
            {
                "phase": "agent" if is_agent else "setup_or_attestation",
                "return_code": result.returncode,
                "failure": result.failure,
            }
        )
        if is_agent:
            self.last_agent_result = result
            if result.failure:
                self.stop_agent()
        return ExecResult(
            return_code=result.returncode,
            stdout=result.stdout.decode("utf-8", "replace"),
            stderr=result.stderr.decode("utf-8", "replace"),
        )

    async def upload_file(self, source_path: Path | str, target_path: str) -> None:
        result = self._run(
            ["docker", "cp", str(source_path), self.runner.container_name + ":" + target_path],
            timeout=60,
        )
        if result.returncode or result.failure:
            raise ContainerUnavailable("codex_file_staging_failed")

    def download_log(self) -> None:
        destination = self.logs_dir / "codex.txt"
        with tempfile.TemporaryDirectory(prefix="codex-log-private-") as temporary:
            raw_path = Path(temporary) / "codex.txt"
            result = self._run(
                [
                    "docker",
                    "cp",
                    self.runner.container_name + ":" + _LOG,
                    str(raw_path),
                ],
                timeout=60,
            )
            if result.returncode or result.failure:
                raise ContainerUnavailable("codex_log_capture_failed")
            raw = raw_path.read_bytes()
            if hasattr(self.runner, "record_attack_output"):
                self.runner.record_attack_output(raw)
            if hasattr(self.runner, "redact_attack_output"):
                raw = self.runner.redact_attack_output(raw)
            rewrite = self._run(
                [
                    "docker",
                    "exec",
                    "--interactive",
                    "--user",
                    "root",
                    self.runner.container_name,
                    "/bin/sh",
                    "-c",
                    "cat > " + shlex.quote(_LOG) + " && chmod 0600 " + shlex.quote(_LOG),
                ],
                stdin=raw,
                timeout=30,
            )
            if rewrite.returncode or rewrite.failure:
                raise ContainerUnavailable("codex_log_sanitize_failed")
            destination.write_bytes(raw)
        destination.chmod(0o600)

    def stop_agent(self) -> None:
        # Never trust a PID file in the candidate-writable Codex home.  Discover
        # only the pinned executable, then kill and attest its process groups.
        script = r"""import os,signal,time
groups=set()
for name in os.listdir('/proc'):
    if not name.isdecimal(): continue
    try:
        if os.readlink('/proc/'+name+'/exe') == '/installed-agent/codex':
            pid=int(name); group=os.getpgid(pid)
            if pid > 1 and group > 1: groups.add(group)
    except (FileNotFoundError,PermissionError,ProcessLookupError): pass
for group in groups:
    try: os.killpg(group,signal.SIGTERM)
    except ProcessLookupError: pass
time.sleep(.2)
for group in groups:
    try: os.killpg(group,signal.SIGKILL)
    except ProcessLookupError: pass
time.sleep(.05)
for name in os.listdir('/proc'):
    if not name.isdecimal(): continue
    try:
        if os.readlink('/proc/'+name+'/exe') == '/installed-agent/codex': raise SystemExit(45)
    except (FileNotFoundError,PermissionError): pass
"""
        python = getattr(self.runner, "public_python", "python3")
        result = self.shell(
            "# identity-checked kill -TERM and kill -KILL\n"
            + python
            + " -I -c "
            + shlex.quote(script),
            root=True,
        )
        if result.returncode or result.failure:
            raise ContainerUnavailable("codex_agent_process_cleanup_failed")

    def capture_relay_identity(self) -> None:
        script = (
            r"""import json,os,pathlib
raw=pathlib.Path('"""
            + _HOME
            + r"""/relay.pid').read_text()
if not raw.isdecimal() or int(raw) <= 1: raise SystemExit(45)
pid=int(raw); fields=pathlib.Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()
print(json.dumps({'pid':pid,'starttime':int(fields[19])}))
"""
        )
        python = getattr(self.runner, "public_python", "python3")
        result = self.shell(python + " -I -c " + shlex.quote(script), root=True)
        if result.returncode or result.failure:
            raise ContainerUnavailable("codex_relay_process_identity_invalid")
        try:
            value = json.loads(result.stdout)
            self.relay_identity = (int(value["pid"]), int(value["starttime"]))
        except (UnicodeError, ValueError, KeyError, TypeError) as exc:
            raise ContainerUnavailable("codex_relay_process_identity_invalid") from exc

    def stop_relay(self) -> None:
        if self.relay_identity is None:
            return
        pid, starttime = self.relay_identity
        script = r"""import os,pathlib,signal,sys,time
pid=int(sys.argv[1]); expected=int(sys.argv[2]); path=pathlib.Path(f'/proc/{pid}/stat')
if path.exists():
    fields=path.read_text().rsplit(')',1)[1].split()
    if int(fields[19]) != expected: raise SystemExit(45)
    os.kill(pid,signal.SIGTERM); time.sleep(.2)
    try: os.kill(pid,signal.SIGKILL)
    except ProcessLookupError: pass
"""
        python = getattr(self.runner, "public_python", "python3")
        result = self.shell(
            python + " -I -c " + shlex.quote(script) + " " + str(pid) + " " + str(starttime),
            root=True,
        )
        if result.returncode or result.failure:
            raise ContainerUnavailable("codex_relay_process_cleanup_failed")
        self.relay_identity = None

    def cleanup(self) -> None:
        if self.last_agent_result is not None and self.last_agent_result.failure:
            self.stop_agent()
        self.stop_relay()
        result = self.shell(f"rm -rf -- {_HOME}", root=True)
        if result.returncode or result.failure:
            raise ContainerUnavailable("codex_ephemeral_home_cleanup_failed")


def _agent_classes() -> tuple[type, type]:
    try:
        from harbor.agents.installed.base import ExecInput
        from harbor.agents.installed.codex import Codex

        from .author.codex_skill_only import CodexSkillOnly
    except ImportError as exc:
        raise ContainerUnavailable("codex_pinned_harbor_not_installed") from exc

    class ProviderTransport:
        """Only installation and provider configuration differ from upstream."""

        async def setup(self, environment: _EpisodeEnvironment) -> None:
            self.environment = environment
            python = shlex.quote(
                self.provider.relay_command[0]
                if self.provider.relay_command
                else getattr(getattr(environment, "runner", None), "public_python", "python3")
            )
            owner = environment.shell("id -u; id -g")
            values = owner.stdout.decode().split()
            if (
                owner.returncode
                or owner.failure
                or len(values) != 2
                or not all(value.isdecimal() for value in values)
            ):
                raise ContainerUnavailable("codex_task_user_not_resolved")
            ownership = ":".join(values)
            result = environment.shell(
                f"mkdir -p /installed-agent /logs/agent {_HOME}; "
                f"chown {ownership} /logs/agent {_HOME}; chmod 0700 {_HOME}",
                root=True,
            )
            if result.returncode or result.failure:
                raise ContainerUnavailable("codex_installation_directory_failed")
            await environment.upload_file(self.provider.binary, "/installed-agent/codex")
            if self.provider.code_mode_host is not None:
                await environment.upload_file(
                    self.provider.code_mode_host, "/installed-agent/codex-code-mode-host"
                )
                result = environment.shell(
                    "chmod 0755 /installed-agent/codex-code-mode-host; "
                    "/installed-agent/codex-code-mode-host --help >/dev/null",
                    root=True,
                )
                if result.returncode or result.failure:
                    raise ContainerUnavailable("codex_task_code_mode_host_not_usable")
            result = environment.shell(
                "chmod 0755 /installed-agent/codex; "
                "ln -sf /installed-agent/codex /usr/local/bin/codex; "
                "codex --version; command -v setsid",
                root=True,
            )
            if result.returncode or result.failure:
                raise ContainerUnavailable("codex_task_binary_not_usable")
            config = self.logs_dir / "provider-config.toml"
            config.write_text(self.provider.config())
            config.chmod(0o600)
            await environment.upload_file(config, _HOME + "/config.toml")
            result = environment.shell(
                f"chown {ownership} {_HOME}/config.toml; chmod 0600 {_HOME}/config.toml",
                root=True,
            )
            if result.returncode or result.failure:
                raise ContainerUnavailable("codex_provider_config_protection_failed")
            if self.provider.relay_command:
                launch = shlex.join(self.provider.relay_command)
                result = environment.shell(
                    f'{launch} >/tmp/tau-codex-relay.log 2>&1 & printf "%s" "$!" >{_HOME}/relay.pid'
                )
                if result.returncode or result.failure:
                    raise ContainerUnavailable("codex_episode_relay_not_started")
                if hasattr(environment, "capture_relay_identity"):
                    environment.capture_relay_identity()
                probe = (
                    "import socket,time; "
                    "\nfor attempt in range(50):"
                    "\n try: socket.create_connection(('127.0.0.1',18765),.1).close(); break"
                    "\n except OSError: time.sleep(.1)"
                    "\nelse: raise RuntimeError('episode relay unavailable')"
                )
                result = environment.shell(python + " -c " + shlex.quote(probe))
                if result.returncode or result.failure:
                    raise ContainerUnavailable("codex_episode_relay_not_ready")
            if isinstance(self, CodexSkillOnly):
                # The author's chmod cannot change modes on a read-only bind mount.
                # Retain its barrier/staging, and require the stronger kernel boundary
                # if that single installation operation fails.
                try:
                    await self._setup_skill_only(environment)
                except RuntimeError as exc:
                    if str(exc) != "Failed to make evolved Skill sources read-only":
                        raise
                    mount_check = (
                        "from pathlib import Path;import hashlib;"
                        "roots=['/bundle','/app/environment/skills/evo-current'];"
                        "mounts=[line.split() for line in Path('/proc/self/mountinfo').read_text()"
                        ".splitlines()];"
                        "assert all(any(row[4]==root and 'ro' in row[5].split(',') "
                        "for row in mounts) for root in roots), 'read-only bind mount required';"
                        "assert not any(p.is_symlink() for root in roots "
                        "for p in Path(root).rglob('*')), 'Skill symlinks forbidden';"
                        "manifest=lambda root:{str(p.relative_to(root)):"
                        "hashlib.sha256(p.read_bytes())"
                        ".hexdigest() for p in Path(root).rglob('*') if p.is_file()};"
                        "assert manifest(roots[0]) and 'SKILL.md' in manifest(roots[0]);"
                        "assert manifest(roots[0])==manifest(roots[1])"
                    )
                    protected = await environment.exec(
                        command=python + " -c " + shlex.quote(mount_check),
                        timeout_sec=15,
                    )
                    if protected.return_code:
                        raise RuntimeError(
                            "Codex Skill read-only mount attestation failed"
                        ) from exc
                    self.skill_protection = "read_only_bind_mount"
                result = environment.shell(f"ln -sfn /logs/agent/skills {_HOME}/skills")
            else:
                result = environment.shell(
                    "test ! -e /app/environment/doc && test ! -e /app/environment/skills "
                    "&& test ! -e /logs/agent/skills && test ! -e /bundle/SKILL.md"
                )
            if result.returncode or result.failure:
                raise ContainerUnavailable("codex_no_skill_or_skill_barrier_failed")

        def create_run_agent_commands(self, instruction: str) -> list[Any]:
            if isinstance(self, CodexSkillOnly):
                instruction = self._skill_transfer_instruction(instruction)
            # Pin the same Codex execution flags as the author's Harbor adapter.
            command = (
                f"export CODEX_HOME={_HOME}; "
                "setsid codex exec --dangerously-bypass-approvals-and-sandbox "
                "--skip-git-repo-check "
                f"--model {shlex.quote(self.model_name)} --json --enable unified_exec "
                "--strict-config "
                f"-c model_reasoning_effort={shlex.quote(self._reasoning_effort)} "
                f"-- {shlex.quote(instruction)} >{_LOG} 2>&1 </dev/null & "
                f'pid=$!; wait "$pid"; status=$?; cat {_LOG}; exit "$status"'
            )
            return [ExecInput(command=command)]

        def populate_context_post_run(self, context: Any) -> None:
            self.environment.download_log()
            super().populate_context_post_run(context)

    class BedrockSkillOnly(ProviderTransport, CodexSkillOnly):
        pass

    class BedrockNoSkill(ProviderTransport, Codex):
        pass

    return BedrockSkillOnly, BedrockNoSkill


def execute_codex(
    runner: Any,
    episode: Any,
    *,
    instruction: str,
    logs_dir: Path,
    provider: CodexProvider,
    bundle: Any = None,
) -> dict[str, Any]:
    """Execute real Codex, returning public status while keeping raw JSON private."""
    from dataclasses import replace

    if runner.runtime != "docker" or not runner.public_open or not runner.container_name:
        raise ContainerUnavailable("codex_requires_live_docker_episode")
    settings: Any = provider.binary
    if provider.code_mode_host is not None:
        settings = {
            "binary": provider.binary,
            "code_mode_host_binary": str(provider.code_mode_host),
        }
    identity = codex_identity(settings)
    companion_path = identity.pop("code_mode_host_binary", None)
    if provider.model == "gpt-5.6-terra" and companion_path is None:
        raise ContainerUnavailable("codex_code_mode_host_not_installed")
    provider = replace(
        provider,
        binary=Path(identity.pop("binary")),
        code_mode_host=Path(companion_path) if companion_path else None,
    )
    skill_class, no_skill_class = _agent_classes()
    from harbor.models.agent.context import AgentContext

    logs_dir = Path(logs_dir)
    logs_dir.mkdir(parents=True, exist_ok=False, mode=0o700)
    environment = _EpisodeEnvironment(runner, logs_dir)
    agent_class = skill_class if bundle is not None else no_skill_class
    agent = agent_class(
        logs_dir=logs_dir,
        model_name=provider.model,
        reasoning_effort=provider.reasoning_effort,
        version=identity["cli_version"],
    )
    agent.provider = provider
    context = AgentContext()
    error: str | None = None

    async def run() -> None:
        await agent.setup(environment)
        await agent.run(instruction, environment, context)

    try:
        asyncio.run(run())
    except Exception as exc:
        error = type(exc).__name__
        (logs_dir / "error.txt").write_text(str(exc))
        (logs_dir / "error.txt").chmod(0o600)
    finally:
        environment.cleanup()
    result = environment.last_agent_result
    reason = (
        "codex_runtime_error"
        if error
        else "episode_timeout"
        if result and result.failure == "timeout"
        else "codex_output_limit"
        if result and result.failure == "output_limit"
        else "codex_error"
        if not result or result.returncode != 0
        else "agent_finished"
    )
    usage = {
        "input_tokens": context.n_input_tokens,
        "cached_input_tokens": context.n_cache_tokens,
        "output_tokens": context.n_output_tokens,
    }
    metadata = {
        **identity,
        "model": provider.model,
        "condition": "skill_only" if bundle is not None else "no_skill",
        "bundle_hash": bundle.bundle_hash if bundle is not None else None,
        "skill_protection": getattr(agent, "skill_protection", None),
        "termination_reason": reason,
        "error_type": error,
        "usage": usage,
        "execution_statuses": environment.executions,
    }
    (logs_dir / "execution.json").write_text(json.dumps(metadata, indent=2) + "\n")
    for path in logs_dir.rglob("*"):
        if path.is_file():
            path.chmod(0o600)
    # No command text, Skill source, raw stdout/stderr or model messages leave this layer.
    return metadata
