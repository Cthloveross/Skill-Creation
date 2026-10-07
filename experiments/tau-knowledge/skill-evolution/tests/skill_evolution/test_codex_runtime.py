"""Author-adapter contract checks; mocks do not assert real container isolation."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import json
import os
import re
import shlex
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
import tomllib
from tau_skill_evolution import codex_runtime as module
from tau_skill_evolution.codex_runtime import CodexProvider, _agent_classes
from tau_skill_evolution.container import ContainerUnavailable, ProcessResult, ProgramResult


def test_vendored_author_class_is_unmodified() -> None:
    source = module._author_source()
    path = Path(module.__file__).with_name("author") / "codex_skill_only.py"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == (
        "ec8652a2671059f1ebd1fd331e3dbae95d62fa6e0487ec2b3bccb04cb525c98e"
    )
    assert source["adaptations"] == []


def test_provider_is_responses_only_and_has_no_credentials_or_auto_retry() -> None:
    provider = CodexProvider("openai.gpt-5.5", "http://127.0.0.1:18765/v1")
    parsed = tomllib.loads(provider.config())
    selected = parsed["model_providers"][parsed["model_provider"]]
    assert selected["wire_api"] == "responses"
    assert selected["requires_openai_auth"] is False
    assert selected["request_max_retries"] == selected["stream_max_retries"] == 0
    assert "env_key" not in selected
    assert parsed["agents"]["enabled"] is False
    assert parsed["features"]["multi_agent_v2"] is False


@pytest.mark.parametrize("problem", [None, "missing", "not-elf", "hash"])
def test_code_mode_companion_is_hash_bound(tmp_path: Path, monkeypatch, problem):
    cli, companion = tmp_path / "codex", tmp_path / "codex-code-mode-host"
    cli.write_bytes(b"\x7fELFfixture-cli")
    companion.write_bytes(b"\x7fELFfixture-companion")
    settings = {
        "binary": str(cli),
        "version": "0.160.1",
        "binary_sha256": hashlib.sha256(cli.read_bytes()).hexdigest(),
        "code_mode_host_binary": str(companion),
        "code_mode_host_sha256": hashlib.sha256(companion.read_bytes()).hexdigest(),
    }
    monkeypatch.setattr(
        module,
        "_author_source",
        lambda: {"sha256": "a" * 64, "harbor_source_hashes": {}},
    )
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(stdout="codex-cli 0.160.1"),
    )
    monkeypatch.setattr(
        module,
        "distribution",
        lambda _name: SimpleNamespace(
            read_text=lambda _: json.dumps({"vcs_info": {"commit_id": module.HARBOR_COMMIT}})
        ),
    )
    if problem == "missing":
        companion.unlink()
    elif problem == "not-elf":
        companion.write_bytes(b"script")
    elif problem == "hash":
        companion.write_bytes(b"\x7fELFchanged")
    if problem:
        with pytest.raises(ContainerUnavailable, match="codex_code_mode_host"):
            module.codex_identity(settings)
    else:
        identity = module.codex_identity(settings)
        assert identity["code_mode_host_binary"] == str(companion)
        assert identity["code_mode_host_sha256"] == settings["code_mode_host_sha256"]


def test_actual_harbor_base_and_author_skill_adapter_are_used(tmp_path: Path) -> None:
    pytest.importorskip("harbor")
    from harbor.agents.installed.codex import Codex
    from tau_skill_evolution.author.codex_skill_only import CodexSkillOnly

    skill_class, no_skill_class = _agent_classes()
    skill = skill_class(logs_dir=tmp_path, model_name="openai.gpt-5.5")
    plain = no_skill_class(logs_dir=tmp_path, model_name="openai.gpt-5.5")
    assert isinstance(skill, CodexSkillOnly)
    assert isinstance(plain, Codex)
    assert not isinstance(plain, CodexSkillOnly)
    skill_command = skill.create_run_agent_commands("Solve the public task.")[0].command
    plain_command = plain.create_run_agent_commands("Solve the public task.")[0].command
    assert "/logs/agent/skills" in skill_command
    assert "read-only" in skill_command
    assert "/logs/agent/skills" not in plain_command
    for command in (plain_command, skill_command):
        assert "codex exec --dangerously-bypass-approvals-and-sandbox" in command
        assert "--json --enable unified_exec" in command
        assert "--skip-git-repo-check" in command
        assert "OPENAI_API_KEY" not in command


def test_authors_actual_post_run_attestation_rejects_changed_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("harbor")
    from harbor.agents.installed.codex import Codex
    from harbor.environments.base import ExecResult
    from tau_skill_evolution.author.codex_skill_only import CodexSkillOnly

    async def no_agent(*_args, **_kwargs):
        return None

    monkeypatch.setattr(Codex, "run", no_agent)
    digests = iter(("a" * 64, "b" * 64))
    commands = []

    class Environment:
        async def exec(self, *, command, **_kwargs):
            commands.append(command)
            return ExecResult(return_code=0, stdout=next(digests))

    agent = CodexSkillOnly(logs_dir=tmp_path, model_name="openai.gpt-5.5")
    with pytest.raises(RuntimeError, match="Frozen evolved Skill changed"):
        asyncio.run(agent.run("public task", Environment(), object()))
    assert len(commands) == 2
    assert all("/app/environment/skills" in command for command in commands)


def test_timeout_stops_real_cli_process_group_and_keeps_raw_output_private(tmp_path: Path) -> None:
    pytest.importorskip("harbor")
    calls = []

    class Transport:
        def run(self, command, **kwargs):
            calls.append((command, kwargs))
            if "codex exec " in command[-1]:
                return ProcessResult(-9, b"private model JSON", b"private stderr", "timeout")
            return ProcessResult(0)

    runner = SimpleNamespace(
        transport=Transport(),
        public_open=True,
        container_name="episode-only",
        task_id="example",
        source=SimpleNamespace(task=lambda _task_id: {"environment": {"workdir": "/app"}}),
        agent_timeout_seconds=3000,
        config={"agent": {"timeout_sec": 7200}},
        episode_started=time.monotonic() - 10,
    )
    environment = module._EpisodeEnvironment(runner, tmp_path)
    result = asyncio.run(environment.exec("codex exec --json"))
    assert result.return_code == -9
    assert 2980 < calls[0][1]["timeout"] <= 2990
    assert "--workdir" in calls[0][0] and "/app" in calls[0][0]
    assert "kill -TERM" in calls[1][0][-1] and "kill -KILL" in calls[1][0][-1]
    public_status = json.dumps(environment.executions)
    assert "private model JSON" not in public_status and "private stderr" not in public_status
    assert environment.executions == [{"phase": "agent", "return_code": -9, "failure": "timeout"}]


def test_environment_rejects_provider_keys_in_task_env(tmp_path: Path) -> None:
    pytest.importorskip("harbor")
    runner = SimpleNamespace(public_open=True)
    environment = module._EpisodeEnvironment(runner, tmp_path)
    with pytest.raises(ValueError, match="credentials_forbidden"):
        asyncio.run(environment.exec("true", env={"OPENAI_API_KEY": "secret"}))


@pytest.mark.parametrize("mount_mode", ["rw", "ro"])
@pytest.mark.parametrize("python", ["python3", "/.tau-python/python3"])
def test_author_readonly_installation_adaptation_rejects_writable_mount(
    tmp_path: Path, mount_mode: str, python: str
) -> None:
    pytest.importorskip("harbor")
    from harbor.environments.base import ExecResult

    skill_class, _ = _agent_classes()
    agent = skill_class(logs_dir=tmp_path, model_name="gpt-5.5")
    companion = tmp_path / "codex-code-mode-host"
    agent.provider = CodexProvider(
        "gpt-5.5",
        "http://127.0.0.1:18765/v1",
        binary=tmp_path,
        code_mode_host=companion,
        relay_command=(python, "/run/skill-provider/relay.py"),
    )
    uploads, python_calls = [], []

    class Environment:
        def shell(self, command, **_kwargs):
            if "import socket,time" in command:
                python_calls.append(shlex.split(command)[0])
            return ProcessResult(0, b"1000\n1000\n" if command == "id -u; id -g" else b"")

        async def upload_file(self, source, target):
            uploads.append((source, target))

        async def exec(self, *, command, **_kwargs):
            if "chmod a-w" in command:
                return ExecResult(return_code=1, stderr="Read-only file system")
            if "/proc/self/mountinfo" not in command:
                return ExecResult(return_code=0)
            # Execute the exact attestation program against a fixture mount table.
            python_calls.append(shlex.split(command)[0])
            program = shlex.split(command)[2]

            class PublicPath:
                def __init__(self, name):
                    self.name = str(name)

                def read_text(self):
                    return "\n".join(
                        f"1 0 0:0 /fixture {target} {mount_mode},relatime - ext4 fixture rw"
                        for target in ("/bundle", "/app/environment/skills/current")
                    )

                def rglob(self, _pattern):
                    return [PublicFile()]

            class PublicFile:
                def is_symlink(self):
                    return False

                def is_file(self):
                    return True

                def relative_to(self, _root):
                    return "SKILL.md"

                def read_bytes(self):
                    return b"unchanged package"

            program = program.replace("from pathlib import Path;", "")
            try:
                exec(program, {"Path": PublicPath})
            except AssertionError:
                return ExecResult(return_code=1)
            return ExecResult(return_code=0)

    if mount_mode == "rw":
        with pytest.raises(RuntimeError, match="read-only mount attestation failed"):
            asyncio.run(agent.setup(Environment()))
    else:
        asyncio.run(agent.setup(Environment()))
        assert agent.skill_protection == "read_only_bind_mount"
    assert (companion, "/installed-agent/codex-code-mode-host") in uploads
    assert python_calls == [python, python]


def test_live_codex_requires_docker_before_inspecting_credentials(tmp_path: Path) -> None:
    runner = SimpleNamespace(runtime="workspace")
    with pytest.raises(ContainerUnavailable, match="live_docker_episode"):
        module.execute_codex(
            runner,
            object(),
            instruction="public task",
            logs_dir=tmp_path,
            provider=CodexProvider("openai.gpt-5.5", "http://127.0.0.1:18765/v1"),
        )


@pytest.mark.parametrize(
    ("python3", "setsid", "cli_code", "host_code", "expected"),
    [
        (False, True, 0, 0, False),
        (True, False, 0, 0, False),
        (True, True, -1, 0, False),
        (True, True, 0, -1, False),
        (True, True, 0, 0, True),
    ],
    ids=[
        "missing-python",
        "missing-setsid",
        "bad-native-abi",
        "bad-code-mode-abi",
        "native-compatible",
    ],
)
def test_main_native_admission_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    python3: bool,
    setsid: bool,
    cli_code: int,
    host_code: int,
    expected: bool,
) -> None:
    from tau_skill_evolution.skillsbench_runtime import SkillsBenchRunner

    monkeypatch.setattr(
        module,
        "codex_identity",
        lambda _settings: {
            "binary": "/host/codex",
            "cli_version": "codex-cli 0.160.1",
            "cli_sha256": "a" * 64,
            "code_mode_host_binary": "/host/codex-code-mode-host",
            "code_mode_host_sha256": "b" * 64,
        },
    )
    probes = iter(
        [
            ProgramResult(0, {"python3": python3, "setsid": setsid}),
            ProgramResult(0, {"return_code": cli_code, "version": "codex-cli 0.160.1"}),
            ProgramResult(0, {"return_code": host_code}),
        ]
    )
    calls = []
    runner = SkillsBenchRunner.__new__(SkillsBenchRunner)
    runner.container_name = "fresh-main"
    runner.use_bwrap = False
    runner._docker_lock = lambda: {"service_images": {"main": {"public_python": "python3"}}}
    runner._run = lambda *_args: next(probes)
    runner.transport = SimpleNamespace(
        run=lambda command, **_kwargs: calls.append(command) or ProcessResult(0)
    )
    result = runner._codex_admission(SimpleNamespace(package=None, work=None), {})
    assert result["ready"] is expected and result["model_calls"] == 0
    assert result["python3"] is python3 and result["setsid"] is setsid
    assert result["native_cli_abi"] is (python3 and setsid and cli_code == 0)
    if not python3 or not setsid:
        assert not calls
    else:
        assert calls[0] == ["docker", "cp", "/host/codex", "fresh-main:/tmp/tau-codex-admission"]
        assert "--user" in calls[1] and "root" in calls[1]  # only install permissions
        assert result["code_mode_host_abi"] is (host_code == 0)


@pytest.mark.skipif(
    os.environ.get("TAU_RUN_CODEX_DOCKER_INTEGRATION") != "1",
    reason="real MAIN image native Codex admission requires explicit opt-in",
)
def test_real_main_native_admission_needs_no_gateway_or_api_key(tmp_path: Path) -> None:
    from tau_skill_evolution.constants import EXPERIMENT_ROOT
    from tau_skill_evolution.skillsbench_runtime import SkillsBenchRunner

    runner = SkillsBenchRunner(
        EXPERIMENT_ROOT,
        "dialogue-parser",
        demo=False,
        runtime_lock_path=EXPERIMENT_ROOT
        / ("runtime/skillsbench-docker-dialogue-parser-v2-20261006-lock.json"),
    )
    result = runner.preflight(author_codex={"binary": "codex", "version": "0.160.1"})
    assert result["ready"], result
    native = result["author_codex_runtime"]
    assert native["ready"] and native["python3"] and native["setsid"]
    assert native["native_cli_abi"] and native["official_task_user"]
    assert native["cli_version"] == "codex-cli 0.160.1" and native["model_calls"] == 0
    assert runner.execution_framework == "local-tools" and runner.provider_directory is None
    assert runner.container_name is None
    (tmp_path / "native-main-admission.json").write_text(json.dumps(result, indent=2) + "\n")


@pytest.mark.skipif(
    os.environ.get("TAU_RUN_CODEX_DOCKER_INTEGRATION") != "1",
    reason="real prepared Docker and native Codex integration requires explicit opt-in",
)
@pytest.mark.parametrize(
    ("with_skill", "force_compaction", "force_incomplete", "messages_transport", "gpt56_profile"),
    [
        (False, False, False, False, False),
        (True, False, False, False, False),
        (False, True, False, False, False),
        (False, False, True, False, False),
        (True, False, False, True, False),
        (True, False, False, False, True),
    ],
    ids=[
        "no-skill",
        "author-skill-only",
        "no-skill-compaction",
        "native-output-budget",
        "messages-bridge",
        "gpt56-profile",
    ],
)
def test_real_native_codex_and_unix_relay_with_fake_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    with_skill: bool,
    force_compaction: bool,
    force_incomplete: bool,
    messages_transport: bool,
    gpt56_profile: bool,
) -> None:
    """Real Docker/CLI/tools, fake model responses; this measures no task utility."""
    from tau_skill_evolution.artifacts import SkillBundle
    from tau_skill_evolution.codex_provider import OUTPUT_TOKEN_BUDGET_STOP, open_provider
    from tau_skill_evolution.constants import EXPERIMENT_ROOT
    from tau_skill_evolution.skillsbench_runtime import SkillsBenchRunner

    root = Path(os.environ.get("TAU_SKILLSBENCH_ROOT", str(EXPERIMENT_ROOT))).resolve()
    new_profile = messages_transport or gpt56_profile
    task_id = "3d-scan-calc" if new_profile else "dialogue-parser"
    model_id = (
        "anthropic.claude-opus-4-8"
        if messages_transport
        else "openai.gpt-5.6-terra"
        if gpt56_profile
        else "openai.gpt-5.5"
    )
    selected = os.environ.get("TAU_CODEX_DOCKER_LOCK")
    lock = (
        Path(selected)
        if selected
        else (
            root
            / "runtime"
            / (
                "skillsbench-docker-3d-scan-calc-v4-lock.json"
                if new_profile
                else "skillsbench-docker-dialogue-parser-v2-20261006-lock.json"
            )
        )
    )
    runner = SkillsBenchRunner(root, task_id, demo=False, runtime_lock_path=lock)
    assert runner.preflight()["ready"], "prepared pinned episode image and daemon required"
    cli_identity = module.codex_identity({"binary": "codex", "version": "0.160.1"})
    runner.execution_framework = "author-codex"
    runner.codex_skill_mode = with_skill
    runner.agent_timeout_seconds = 60
    fixture_key = "TAU_CODEX_INTEGRATION_PROVIDER_KEY"
    monkeypatch.delenv("AWS_BEARER_TOKEN_BEDROCK_FILE", raising=False)
    monkeypatch.setenv(fixture_key, "FAKE_PROVIDER_KEY_NOT_AN_AWS_CREDENTIAL")
    calls = []
    phases = []
    proof_path = (
        "/root/codex-integration-proof.json" if new_profile else "/app/codex-integration-proof.json"
    )
    input_path = "/root/scan_data.stl" if new_profile else "/app/script.txt"
    script_path = "/root/codex-messages-fixture.py"
    image_path = "/root/codex-vision-fixture.png"
    task_command = (
        "import json,os;from pathlib import Path;"
        "p=Path('/app/environment/skills/current/SKILL.md');"
        "proof={'skill_available':p.is_file(),"
        f"'task_input':Path({input_path!r}).is_file(),"
        "'private_tests':Path('/tests/test.sh').exists(),"
        "'host_key_file':Path('/key.env').exists(),"
        f"'provider_key_in_environment':{fixture_key!r} in os.environ}};"
        "\nif p.is_file():"
        "\n proof['skill_read']=bool(p.read_text())"
        "\n try: p.write_text('tampered'); proof['skill_write_rejected']=False"
        "\n except OSError: proof['skill_write_rejected']=True"
        f"\nPath({proof_path!r}).write_text(json.dumps(proof))"
        "\nprint(json.dumps(proof))"
    )
    if new_profile:
        image_size = 512 if gpt56_profile else 8
        task_command += (
            "\nimport random,struct,zlib"
            "\ndef chunk(kind,data):"
            "\n return struct.pack('>I',len(data))+kind+data"
            "+struct.pack('>I',zlib.crc32(kind+data))"
            f"\nsize={image_size}; pixels=random.Random(0).randbytes(size*size*3)"
            "\npng=b'\\x89PNG\\r\\n\\x1a\\n'"
            "+chunk(b'IHDR',struct.pack('>IIBBBBB',size,size,8,2,0,0,0))"
            "\nrows=b''.join(b'\\0'+pixels[y*size*3:(y+1)*size*3] for y in range(size))"
            "\npng+=chunk(b'IDAT',zlib.compress(rows))+chunk(b'IEND',b'')"
            f"\nPath({image_path!r}).write_bytes(png)"
        )
    shell_command = "python3 -c " + shlex.quote(task_command)

    def native_catalog(payload):
        return payload.get("tools") or [
            tool
            for item in payload.get("input", [])
            if isinstance(item, dict) and item.get("type") == "additional_tools"
            for tool in item["tools"]
        ]

    def opener(request, *, timeout):
        assert timeout > 0
        payload = json.loads(request.data)
        calls.append(payload)
        assert request.full_url == "https://fake-provider.invalid/v1/" + (
            "messages" if messages_transport else "responses"
        )
        assert len(calls) <= 5, "fake provider must not hide an unexpected native CLI loop"
        if messages_transport:
            assert payload["model"] == "anthropic.claude-opus-4-8"
            assert payload["max_tokens"] == 128000 and payload["stream"] is False
            if len(calls) <= 3:
                name = "view_image" if len(calls) == 3 else "exec_command"
                tool = next(
                    tool
                    for tool in payload["tools"]
                    if tool["description"].split(". ", 1)[0].rsplit(".", 1)[-1].endswith(name)
                )
                if len(calls) == 1:
                    command = "python3 -c " + shlex.quote(
                        "from pathlib import Path;"
                        + f"Path({script_path!r}).write_text({task_command!r})"
                    )
                    arguments = {"cmd": command, "yield_time_ms": 1000, "max_output_tokens": 2000}
                elif len(calls) == 2:
                    blocks = [
                        block for message in payload["messages"] for block in message["content"]
                    ]
                    assert any(
                        block["type"] == "thinking"
                        and block["signature"] == "fixture-signed-thinking"
                        for block in blocks
                    )
                    assert any(
                        block["type"] == "tool_result"
                        and block["tool_use_id"] == "native_fixture_1"
                        for block in blocks
                    )
                    arguments = {
                        "cmd": "python3 " + script_path,
                        "yield_time_ms": 1000,
                        "max_output_tokens": 2000,
                    }
                else:
                    arguments = {"path": image_path}
                content = [
                    {
                        "type": "thinking",
                        "thinking": "Private simulated thought",
                        "signature": "fixture-signed-thinking",
                    },
                    {
                        "type": "tool_use",
                        "id": f"native_fixture_{len(calls)}",
                        "name": tool["name"],
                        "input": arguments,
                    },
                ]
                stop = "tool_use"
            else:
                blocks = [block for message in payload["messages"] for block in message["content"]]
                blocks += [
                    content
                    for block in blocks
                    if block["type"] == "tool_result" and isinstance(block["content"], list)
                    for content in block["content"]
                ]
                images = [block for block in blocks if block["type"] == "image"]
                assert images and images[-1]["source"]["type"] == "base64"
                assert images[-1]["source"]["media_type"] == "image/png"
                content, stop = (
                    [{"type": "text", "text": "Integration fixture finished."}],
                    "end_turn",
                )
            response = {
                "id": f"msg_fixture_{len(calls)}",
                "type": "message",
                "role": "assistant",
                "model": "anthropic.claude-opus-4-8",
                "content": content,
                "stop_reason": stop,
                "usage": {"input_tokens": 10, "output_tokens": 10},
            }
            stream = io.BytesIO(json.dumps(response).encode())
            stream.status = 200
            return stream
        compacting = not native_catalog(payload) or "CONTEXT CHECKPOINT COMPACTION" in json.dumps(
            payload.get("input", [])
        )
        first_normal = "task_tool" not in phases
        if not compacting and first_normal:
            phases.append("task_tool")
            item = {
                "type": "function_call",
                "id": "fc_native_fixture",
                "call_id": "native_fixture",
                "name": "exec_command",
                "arguments": json.dumps(
                    {"cmd": shell_command, "yield_time_ms": 1000, "max_output_tokens": 2000}
                ),
                "status": "completed",
            }
            if gpt56_profile:
                assert native_catalog(payload)[0]["name"] == "functions"
                item = {
                    "type": "custom_tool_call",
                    "id": "custom_native_fixture",
                    "call_id": "native_fixture",
                    "namespace": "functions",
                    "name": "exec",
                    "input": (
                        '// @exec: {"yield_time_ms": 1}\n'
                        "await new Promise(resolve => setTimeout(resolve, 250));"
                        "text(await tools.exec_command(" + item["arguments"] + "));"
                    ),
                    "status": "completed",
                }
        elif gpt56_profile and len(calls) == 2:
            phases.append("task_wait")
            previous = next(
                item["output"]
                for item in reversed(payload["input"])
                if item.get("type") == "custom_tool_call_output"
            )
            cell = re.search(r"cell ID ([^\s]+)", previous)
            assert cell is not None, previous
            item = {
                "type": "function_call",
                "id": "fc_native_fixture_wait",
                "call_id": "native_fixture_wait",
                "namespace": "functions",
                "name": "wait",
                "arguments": json.dumps({"cell_id": cell[1], "yield_time_ms": 1000}),
                "status": "completed",
            }
        elif gpt56_profile and len(calls) == 3:
            phases.append("disabled_spawn_probe")
            item = {
                "type": "function_call",
                "id": "fc_native_fixture_collaboration",
                "call_id": "native_fixture_collaboration",
                "namespace": "collaboration",
                "name": "spawn_agent",
                "arguments": json.dumps(
                    {"task_name": "must-not-spawn", "message": "No child inference permitted."}
                ),
                "status": "completed",
            }
        elif gpt56_profile and len(calls) == 4:
            phases.append("original_image")
            item = {
                "type": "custom_tool_call",
                "id": "custom_native_fixture_image",
                "call_id": "native_fixture_image",
                "namespace": "functions",
                "name": "exec",
                "input": "image((await tools.view_image("
                + json.dumps({"path": image_path, "detail": "original"})
                + ")).image_url);",
                "status": "completed",
            }
        else:
            phases.append("compaction" if compacting else "task_final")
            item = {
                "type": "message",
                "id": "msg_native_fixture",
                "role": "assistant",
                "status": "completed",
                "content": [
                    {
                        "type": "output_text",
                        "text": (
                            "Context summary: The integration proof file was written successfully. "
                            "Reply that the integration fixture finished."
                            if compacting
                            else "Integration fixture finished."
                        ),
                        "annotations": [],
                    }
                ],
            }
        input_tokens = 1000 if force_compaction and not compacting and first_normal else 10
        incomplete = force_incomplete and not first_normal
        output_tokens = 4096 if incomplete else 10
        response = {
            "id": "resp_native_fixture_" + str(len(calls)),
            "object": "response",
            "status": "incomplete" if incomplete else "completed",
            "model": model_id,
            "output": [item],
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
                "input_tokens_details": {"cached_tokens": 0},
            },
        }
        if incomplete:
            response["incomplete_details"] = {"reason": "max_output_tokens"}
        stream = io.BytesIO(json.dumps(response).encode())
        stream.status = 200
        return stream

    controls = {
        "agent": {"reasoning_effort": "high", "max_output_tokens": 4096},
        "user": {"reasoning_effort": "low", "max_output_tokens": 2048},
        "max_input_tokens": 272000,
        "assistant_completion_budget": 32768,
    }
    provider_settings = {
        "model": model_id,
        "api_base": "https://fake-provider.invalid/v1",
        "api_key_env": fixture_key,
    }
    if messages_transport:
        provider_settings["transport"] = "bedrock-messages"
    if new_profile:
        controls["agent"]["max_output_tokens"] = None
        controls["assistant_completion_budget"] = None
        controls["max_input_tokens"] = 114688
    bundle = (
        SkillBundle(
            {
                "SKILL.md": (
                    "---\nname: codex-integration-fixture\n"
                    "description: A deterministic native execution fixture, "
                    "not a task solution.\n---\n"
                    "Read the public input and write the requested integration proof.\n"
                )
            }
        )
        if with_skill
        else None
    )
    # AF_UNIX has a short path limit; journal/evidence remain in tmp_path.
    with (
        tempfile.TemporaryDirectory(prefix="tau-native-provider-") as provider_staging,
        open_provider(
            Path(provider_staging),
            provider_settings,
            controls,
            tmp_path / "provider-journal",
            {"experiment": "native-codex-integration", "condition": str(with_skill)},
            token_counter=lambda text: max(1, len(text) // 4),
            timeout_seconds=10,
            max_requests=5,
            opener=opener,
        ) as gateway,
    ):
        runner.provider_directory = Path(provider_staging)
        with runner.episode(bundle) as episode:
            # Detach the task's ordinary bridge without changing pinned task files.
            # All model traffic must consequently pass the mounted Unix socket.
            disconnected = runner.transport.run(
                ["docker", "network", "disconnect", "bridge", runner.container_name],
                stdin=b"",
                timeout=30,
                output_limit=65536,
            )
            assert disconnected.returncode == 0 and disconnected.failure is None
            provider = CodexProvider(
                model_id.removeprefix("openai."),
                gateway.base_url,
                relay_command=(
                    "python3",
                    "/run/skill-provider/relay.py",
                    "/run/skill-provider/provider.sock",
                    "18765",
                ),
                input_token_limit=1000 if force_compaction else 114688,
            )
            if force_incomplete:
                from tau_skill_evolution.skillsbench import SkillsBenchAdapter

                adapter = SkillsBenchAdapter.__new__(SkillsBenchAdapter)
                adapter.runner, adapter.task_id = runner, "dialogue-parser"
                adapter.public_inputs = {"opening": "Write the public integration proof file."}
                adapter.spec = SimpleNamespace(
                    provider_settings=provider_settings, values={"runtime": {"controls": controls}}
                )
                adapter._codex_gateway = gateway
                adapter._codex_logs = tmp_path / "private-codex"
                adapter._codex_binary = Path(cli_identity["binary"])
                adapter._executor_identity = {"framework": "author-codex"}
                result = adapter._execute_codex(None, episode)
                native = json.loads((adapter._codex_logs / "execution.json").read_text())
                assert native["termination_reason"] == "codex_error"
                assert native["error_type"] is None
                assert result["termination_reason"] == OUTPUT_TOKEN_BUDGET_STOP
                assert result["assistant_completion_tokens"] == 4106
                assert gateway.statistics["terminal_stop"]["reason"] == "max_output_tokens"
            else:
                result = module.execute_codex(
                    runner,
                    episode,
                    instruction="Write the public integration proof file.",
                    logs_dir=tmp_path / "private-codex",
                    provider=provider,
                    bundle=bundle,
                )
                assert result["termination_reason"] == "agent_finished", result
                assert result["condition"] == ("skill_only" if with_skill else "no_skill")
            proof = runner.terminal(episode, "cat " + shlex.quote(proof_path))
            assert proof.exit_code == 0 and proof.failure is None
            proof_data = json.loads(proof.output)
            assert proof_data == {
                "skill_available": with_skill,
                "task_input": True,
                "private_tests": False,
                "host_key_file": False,
                "provider_key_in_environment": False,
                **({"skill_read": True, "skill_write_rejected": True} if with_skill else {}),
            }
            if force_compaction:
                assert "compaction" in phases, phases
                assert len(calls) >= 3
                assert result["usage"]["input_tokens"] >= 1000
            else:
                assert len(calls) == (5 if gpt56_profile else 4 if messages_transport else 2)
                if not force_incomplete:
                    assert result["usage"]["input_tokens"] == (
                        50 if gpt56_profile else 40 if messages_transport else 20
                    )
            assert gateway.statistics["requests"] == len(calls)
            gateway.close_public()
            runner.close_public(episode)
            if force_incomplete or new_profile:
                # Inference was network-detached. Restore only the original task network
                # after both public/model interfaces close, for its official pip grader.
                assert runner.config["environment"]["allow_internet"] is True
                connected = runner.transport.run(
                    ["docker", "network", "connect", "bridge", runner.container_name],
                    stdin=b"",
                    timeout=30,
                    output_limit=65536,
                )
                assert connected.returncode == 0 and connected.failure is None
                grade = runner.grade(episode)
                (tmp_path / "official-grader-diagnostics.txt").write_text(
                    runner.grader_diagnostics or ""
                )
                assert grade["status"] == "MEASURED" and grade["reward"] == 0
                assert grade["official_checks"]["status"] == "MEASURED"
                assert grade["official_checks"]["total"] > 0
                evidence_name = (
                    "messages-bridge-evidence.json"
                    if messages_transport
                    else "gpt56-profile-evidence.json"
                    if gpt56_profile
                    else "incomplete-budget-evidence.json"
                )
                native_tools = next(
                    native_catalog(json.loads(path.read_text())["payload"])
                    for path in gateway.journal.root.glob("*/request.json")
                    if native_catalog(json.loads(path.read_text())["payload"])
                )
                collaboration_result = (
                    next(
                        item["output"]
                        for item in calls[-1]["input"]
                        if item.get("type") == "function_call_output"
                        and item.get("call_id") == "native_fixture_collaboration"
                    )
                    if gpt56_profile
                    else None
                )
                if gpt56_profile:
                    assert collaboration_result == "unsupported call: collaborationspawn_agent"
                image_evidence = None
                if gpt56_profile:
                    from PIL import Image

                    def images(value):
                        if isinstance(value, dict):
                            if value.get("type") == "input_image":
                                yield value["image_url"]
                            for child in value.values():
                                yield from images(child)
                        elif isinstance(value, list):
                            for child in value:
                                yield from images(child)

                    encoded_image = next(images(calls[-1]))
                    image_bytes = base64.b64decode(encoded_image.split(",", 1)[1], validate=True)
                    with Image.open(io.BytesIO(image_bytes)) as observed:
                        assert observed.size == (512, 512)
                    original = runner.transport.run(
                        ["docker", "exec", runner.container_name, "sha256sum", image_path],
                        stdin=b"",
                        timeout=15,
                        output_limit=1024,
                    )
                    assert original.returncode == 0 and original.failure is None
                    image_hash = hashlib.sha256(image_bytes).hexdigest()
                    assert original.stdout.decode().split()[0] == image_hash
                    estimate = gateway.statistics["input_token_estimates"][-1]
                    assert estimate["total_tokens"] < 114688
                    assert len(json.dumps(calls[-1])) > 1_000_000
                    image_evidence = {
                        "dimensions": [512, 512],
                        "bytes": len(image_bytes),
                        "original_sha256": image_hash,
                        "provider_image_sha256": image_hash,
                        "provider_request_bytes": len(json.dumps(calls[-1]).encode()),
                        "input_limit": 114688,
                        "estimate": estimate,
                    }
                (tmp_path / evidence_name).write_text(
                    json.dumps(
                        {
                            "native": native if force_incomplete else result,
                            "public_trace": result,
                            "grade": grade,
                            "provider": gateway.statistics,
                            "provider_simulated": True,
                            "text_counter_basis": "canonical_json_characters_div_4_mock_only",
                            "native_cli_model": provider.model,
                            "provider_model": model_id,
                            "native_tool_catalog": [
                                {"type": tool["type"], "name": tool.get("name")}
                                for tool in native_tools
                            ],
                            "native_tool_catalog_sha256": hashlib.sha256(
                                json.dumps(native_tools, sort_keys=True).encode()
                            ).hexdigest(),
                            "disabled_spawn_probe": collaboration_result,
                            "original_image_probe": image_evidence,
                        },
                        indent=2,
                    )
                    + "\n"
                )
    assert not gateway.socket_path.exists()
    assert runner.container_name is None
    assert "FAKE_PROVIDER_KEY_NOT_AN_AWS_CREDENTIAL" not in json.dumps(result)
