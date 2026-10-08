"""Opt-in real MAIN + local HTTP model acceptance; no paid provider is used."""

import asyncio
import base64
import io
import json
import os
import shlex
import subprocess
import threading
import time
import urllib.request
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest
from tau_skill_evolution.artifacts import FrozenBase, SkillBundle
from tau_skill_evolution.author_controller import AuthorControllerBridge
from tau_skill_evolution.author_verifier import _RUN, author_module, author_source
from tau_skill_evolution.constants import EXPERIMENT_ROOT
from tau_skill_evolution.container import _public_workspace
from tau_skill_evolution.journal import Journal
from tau_skill_evolution.model import GenerationConfig, OpenAICompatibleClient
from tau_skill_evolution.skillsbench_runtime import SkillsBenchRunner


def _wheel():
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        files = {
            "tau_author_fixture.py": "VALUE = 7\n",
            "tau_author_fixture-0.0.1.dist-info/METADATA": (
                "Metadata-Version: 2.1\nName: tau-author-fixture\nVersion: 0.0.1\n"
            ),
            "tau_author_fixture-0.0.1.dist-info/WHEEL": (
                "Wheel-Version: 1.0\nGenerator: offline-fixture\n"
                "Root-Is-Purelib: true\nTag: py3-none-any\n"
            ),
        }
        files["tau_author_fixture-0.0.1.dist-info/RECORD"] = "".join(
            path + ",,\n" for path in files
        )
        for path, content in files.items():
            archive.writestr(path, content)
    return output.getvalue()


def _write(path, content):
    data = base64.b64encode(content if isinstance(content, bytes) else content.encode()).decode()
    return f"printf %s {shlex.quote(data)} | base64 -d > {shlex.quote(path)}"


@pytest.mark.skipif(
    os.environ.get("TAU_RUN_SKILLSBENCH_AUTHOR_INTEGRATION") != "1",
    reason="Real pinned Docker and localhost model fixture require explicit opt-in.",
)
def test_real_author_main_dependency_service_restore_and_role_isolation(tmp_path):
    runner = SkillsBenchRunner(
        EXPERIMENT_ROOT,
        "3d-scan-calc",
        demo=False,
        runtime_lock_path=EXPERIMENT_ROOT / "runtime/skillsbench-docker-3d-scan-calc-v4-lock.json",
    )
    test_script = """from pathlib import Path
import urllib.request
import tau_author_fixture

def test_inherited_dependency_and_service():
    assert tau_author_fixture.VALUE == 7
    response = urllib.request.urlopen('http://127.0.0.1:19761/', timeout=5)
    assert response.read() == b'inherited-service'

def test_public_output():
    assert Path('/root/author-fixture-output.txt').read_text() == 'initial'
"""
    model_commands = [
        "ls /root; cat /app/environment/doc/*.md; mkdir -p /root/verifier; "
        + _write("/root/verifier/test_outputs.py", test_script),
        _write("/root/verifier/test_outputs.py", "def test_tampered(): assert True\n")
        + "; "
        + _write(
            "/root/verifier/diagnosis.md", "Current public output differs from the initial value."
        ),
    ]
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            requests.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            index = len(requests) - 1
            if index >= len(model_commands):
                self.send_error(500, "Unexpected additional model request")
                return
            text = json.dumps(
                {
                    "analysis": "Use the public state in this container.",
                    "plan": "Inspect and verify public outputs.",
                    "commands": [{"keystrokes": model_commands[index], "duration": 0.1}],
                    "task_complete": True,
                }
            )
            response = json.dumps(
                {
                    "id": f"local-author-{index}",
                    "status": "completed",
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": text}],
                        }
                    ],
                    "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def local_open(request, *, timeout):
        redirected = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/responses",
            data=request.data,
            headers={"Content-Type": "application/json"},
        )
        return urllib.request.urlopen(redirected, timeout=timeout)

    model = OpenAICompatibleClient(
        "https://bedrock-mantle.us-east-1.api.aws",
        config=GenerationConfig(max_output_tokens=None),
        timeout_seconds=900,
        opener=local_open,
    )
    base = FrozenBase(
        (
            {
                "document_id": "fixture-public",
                "title": "Public fixture",
                "content": "Public fixture evidence.",
            },
        ),
        {"opening": "Verify the public fixture output and inherited service."},
    )
    skill_marker = "PRIVATE_GENERATOR_SKILL_SOURCE_MARKER"
    journal = Journal(tmp_path / "journal", identity={"task": "author-real-main"})
    evidence = {"scope": "native_author_component_real_MAIN_local_HTTP", "paid_model_calls": 0}
    container_name = None
    try:
        with _public_workspace(  # noqa: SIM117
            runner,
            base.public_inputs,
            base,
            previous_bundle=SkillBundle({"SKILL.md": skill_marker}),
            workspace=tmp_path / "workspace",
            terminal_callback=lambda _package, _work, command: runner.author_exec(command),
        ) as public:
            with runner.learning_episode(
                public,
                checkpoint=tmp_path / "learning.json",
                identity={"task": "author-real-main"},
                deadline=time.time() + 300,
            ):
                container_name = runner.container_name
                wheel_path = "/tmp/tau_author_fixture-0.0.1-py3-none-any.whl"
                server_script = """from http.server import BaseHTTPRequestHandler, HTTPServer
class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  self.send_response(200); self.end_headers(); self.wfile.write(b'inherited-service')
HTTPServer(('127.0.0.1', 19761), Handler).serve_forever()
"""
                setup = runner.author_exec(
                    _write(wheel_path, _wheel())
                    + "; python3 -m pip install --break-system-packages --no-index --no-deps "
                    + wheel_path
                    + "; "
                    + _write("/root/service_fixture.py", server_script)
                    + "; nohup python3 /root/service_fixture.py </dev/null "
                    + ">/root/service_fixture.log 2>&1 & "
                    + "printf initial > /root/author-fixture-output.txt; "
                    + 'python3 -c \'import time,urllib.request; time.sleep(0.3); assert urllib.request.urlopen("http://127.0.0.1:19761/").read()==b"inherited-service"\'',
                    timeout_sec=30,
                )
                assert setup.returncode == 0, setup.stderr.decode()
                binding = AuthorControllerBridge(
                    SimpleNamespace(),
                    model,
                    runner,
                    journal,
                    operation_id="native-verifier",
                    environment_dir=tmp_path / "private-task/environment",
                    token_counter=lambda text: len(text) // 4,
                    max_input_tokens=200000,
                )
                verifier = author_module("evolution.independent_verifier").IndependentVerifier(
                    model_name="fixture"
                )

                async def generate():
                    token = _RUN.set(binding.runs["verifier"])
                    try:
                        value = await verifier.generate_and_run(
                            binding.environment,
                            base.public_inputs["opening"],
                            tmp_path / "author-logs",
                        )
                        binding.check()
                        return value
                    finally:
                        _RUN.reset(token)

                initial = asyncio.run(generate())
                assert initial.source == "script" and initial.tests_passed == 2
                assert initial.tests_failed == 0 and len(requests) == 1
                assert (
                    runner.author_exec(
                        "printf changed > /root/author-fixture-output.txt"
                    ).returncode
                    == 0
                )
                failed = asyncio.run(
                    author_module("evolution.self_verifier")
                    .SelfVerifier()
                    .verify(binding.environment)
                )
                assert failed.source == "script" and failed.tests_failed == 1
                assert failed.tests_passed == 1

                async def diagnose():
                    token = _RUN.set(binding.runs["verifier"])
                    try:
                        value = await verifier.diagnose_failures(
                            binding.environment,
                            base.public_inputs["opening"],
                            tmp_path / "diagnosis-logs",
                            failed,
                        )
                        binding.check()
                        return value
                    finally:
                        _RUN.reset(token)

                failed.diagnosis = asyncio.run(diagnose())
                assert failed.diagnosis == "Current public output differs from the initial value."
                restored = runner.author_exec("cat /root/verifier/test_outputs.py")
                assert restored.stdout.decode() == test_script
                frozen = runner.author_exec("printf changed > /app/environment/doc/*.md")
                assert frozen.returncode != 0
                assert runner.container_name == container_name and runner.public_open
                assert (
                    subprocess.run(
                        ["docker", "inspect", container_name], capture_output=True
                    ).returncode
                    == 0
                )
                assert len(requests) == 2
                assert skill_marker not in json.dumps(requests)
                assert all("max_output_tokens" not in request for request in requests)
                evidence.update(
                    source_commit=author_source()["commit"],
                    container_name=container_name,
                    initial=initial.to_dict(),
                    changed=failed.to_dict(),
                    inherited_dependency=True,
                    inherited_background_service=True,
                    sealed_script_restored=True,
                    frozen_documents_read_only=True,
                    role_source_not_in_model_requests=True,
                    local_http_requests=len(requests),
                    learning_survived_author=True,
                )
        assert (
            subprocess.run(["docker", "inspect", container_name], capture_output=True).returncode
            != 0
        )
        evidence["learning_cleaned_at_owner_exit"] = True
        output = (
            Path(os.environ.get("TAU_READINESS_DIR", tmp_path)) / "author-component-docker.json"
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
