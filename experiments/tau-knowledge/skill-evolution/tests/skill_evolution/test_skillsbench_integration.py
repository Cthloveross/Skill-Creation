"""Opt-in checks of prepared SkillsBench Docker and workspace runtimes.

Enable TAU_RUN_SKILLSBENCH_DOCKER_INTEGRATION=1 only after preparing the current
3d-scan-calc episode lock. An enabled check fails if source, lock, image or daemon
is unavailable; it never substitutes mocks, prepares a new image, or calls a model.
TAU_RUN_SKILLSBENCH_WORKSPACE_INTEGRATION=1 runs the independent folder/venv
environment with a handcrafted public-input solution and the real official grader.
"""

import json
import os
import re
import shlex
from pathlib import Path
from types import SimpleNamespace

import pytest
from tau_skill_evolution.artifacts import SkillBundle
from tau_skill_evolution.constants import EXPERIMENT_ROOT
from tau_skill_evolution.container import BoundedProcessTransport, _program_result
from tau_skill_evolution.skillsbench import SkillsBenchAdapter
from tau_skill_evolution.skillsbench_runtime import SkillsBenchRunner
from tau_skill_evolution.verifier import TestSuite, _report

TASK = "3d-scan-calc"
PUBLIC_ROOT = "/root/.tau-docker-integration"
HOST_ENV_SENTINEL = "TAU_INTEGRATION_UNDECLARED_HOST_VALUE"
PARENT_MARKER = "PARENT_SKILL_ONLY_72d9a9"

_SCAN_FIXTURE = r"""import collections,json,re,struct
from pathlib import Path
import numpy as np
data=Path('/root/scan_data.stl').read_bytes()
count=struct.unpack_from('<I',data,80)[0]
records=[struct.unpack_from('<12fH',data,84+i*50) for i in range(count)]
triangles=np.array([record[3:12] for record in records],dtype=float).reshape(-1,3,3)
parent=list(range(count))
def find(i):
    while parent[i]!=i:
        parent[i]=parent[parent[i]]
        i=parent[i]
    return i
vertices={}
for i,triangle in enumerate(triangles):
    for vertex in triangle:
        key=tuple(vertex)
        if key in vertices: parent[find(i)]=find(vertices[key])
        else: vertices[key]=i
groups=collections.defaultdict(list)
for i in range(count): groups[find(i)].append(i)
def volume(indices):
    t=triangles[indices]
    return abs(float(np.einsum('ij,ij->i',t[:,0],np.cross(t[:,1],t[:,2])).sum()/6))
main=max(groups.values(),key=volume)
material=collections.Counter(records[i][-1] for i in main).most_common(1)[0][0]
table=Path('/root/material_density_table.md').read_text()
density=float(re.search(r'\|\s*\*\*'+str(material)+r'\*\*\s*\|[^|]*\|\s*([\d.]+)',table)[1])
report={'main_part_mass':volume(main)/1000*density,'material_id':material}
Path('/root/mass_report.json').write_text(json.dumps(report))
print(json.dumps({'status':'written','numpy':np.__version__}))
"""


class RecordedTransport:
    """Real subprocess transport; retain argv and variable names, never secret values."""

    def __init__(self):
        self.delegate = BoundedProcessTransport(kill_process_group=True)
        self.calls = []

    def run(self, command, *, stdin, timeout, output_limit, env=None):
        self.calls.append((list(command), frozenset(env or {})))
        return self.delegate.run(
            command, stdin=stdin, timeout=timeout, output_limit=output_limit, env=env
        )


@pytest.fixture(scope="module")
def prepared(tmp_path_factory):
    if os.environ.get("TAU_RUN_SKILLSBENCH_DOCKER_INTEGRATION") != "1":
        pytest.skip("prepared persistent SkillsBench Docker integration requires explicit opt-in")
    root = Path(os.environ.get("TAU_SKILLSBENCH_ROOT", str(EXPERIMENT_ROOT))).resolve()
    transport = RecordedTransport()
    selected_lock = os.environ.get("TAU_SKILLSBENCH_DOCKER_LOCK")
    runner = SkillsBenchRunner(
        root,
        TASK,
        demo=False,
        transport=transport,
        runtime_lock_path=Path(selected_lock) if selected_lock else None,
    )
    checks = runner.preflight()
    assert checks["ready"], (
        "explicit Docker integration requires the current prepared episode runtime"
    )
    assert not checks["demo_only"]
    assert checks["main_cpu_memory_limits_configured"]
    assert checks["resources_scope"] == "main_container"
    assert not checks["aggregate_limits_enforced"]
    adapter = SkillsBenchAdapter(
        SimpleNamespace(root=root),
        TASK,
        demo=False,
        artifact_root=tmp_path_factory.mktemp("skillsbench-real-public-snapshots"),
    )
    adapter.runner = runner
    assert adapter.public_inputs["environment"]["workdir"] == "/root"
    return runner, adapter, transport


def python_command(source):
    return "python3 -c " + shlex.quote(source)


def terminal_json(session, command):
    result = session.terminal(command)
    assert result.failure is None and result.exit_code == 0, result.to_dict()
    return json.loads(result.output if isinstance(result.output, str) else result.output["stdout"])


def episode_json(runner, episode, command):
    result = runner.terminal(episode, command)
    assert result.failure is None and result.exit_code == 0, result.to_dict()
    return json.loads(result.output if isinstance(result.output, str) else result.output["stdout"])


def test_real_task_credentials_use_scoped_values_and_do_not_inherit_provider_key(
    prepared, monkeypatch, tmp_path
):
    import copy

    runner, _adapter, transport = prepared
    lock = runner._docker_lock()
    config = copy.deepcopy(runner.config)
    config["environment"]["env"] = {"ANTHROPIC_API_KEY": "${ANTHROPIC_API_KEY}"}
    config["verifier"]["env"] = {"OPENAI_API_KEY": "${OPENAI_API_KEY}"}
    # Bind this synthetic environment declaration in a separate test lock; the
    # original pinned task and its prepared lock remain byte-for-byte unchanged.
    from tau_skill_evolution.skillsbench import _json_hash

    lock["task_config_hash"] = _json_hash(config)
    lock["resources"] = config["environment"]
    probe_lock = tmp_path / "skillsbench-docker-3d-scan-calc-credential-probe-lock.json"
    probe_lock.write_text(json.dumps(lock))
    monkeypatch.setattr(runner, "runtime_lock_path", probe_lock)
    monkeypatch.setattr(runner, "config", config)
    monkeypatch.setenv("OPENAI_API_KEY", "dummy-model-provider-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy-model-anthropic-key")
    monkeypatch.setenv("SKILLSBENCH_TASK_3D_SCAN_CALC_ANTHROPIC_API_KEY", "dummy-public-task-key")
    monkeypatch.setenv("SKILLSBENCH_TASK_3D_SCAN_CALC_OPENAI_API_KEY", "dummy-private-task-key")
    with runner.episode(SkillBundle({"SKILL.md": "No external model calls"})) as episode:
        observed = episode_json(
            runner,
            episode,
            python_command(
                "import os,json;print(json.dumps({'task':os.environ.get('ANTHROPIC_API_KEY'),"
                "'provider':os.environ.get('OPENAI_API_KEY'),"
                "'source':os.environ.get('SKILLSBENCH_TASK_3D_SCAN_CALC_ANTHROPIC_API_KEY')}))"
            ),
        )
        assert observed == {"task": "dummy-public-task-key", "provider": None, "source": None}
        composed = runner.compose_path.read_text()
        assert "dummy-" not in composed
        runner.close_public(episode)
        grade = runner.grade(episode)
        assert grade["status"] == "MEASURED" and grade["reward"] == 0
        grade_env = next(
            names
            for command, names in reversed(transport.calls)
            if command[-2:] == ["/bin/bash", "/tests/test.sh"]
        )
        assert "OPENAI_API_KEY" in grade_env


def test_real_direct_generator_persists_task_state_and_fresh_execution_is_clean(prepared, tmp_path):
    from tau_skill_evolution.journal import Journal

    formal, adapter, transport = prepared
    script = (
        "import json;from pathlib import Path\n"
        "Path('/root/direct-evolution-output.json').write_text(json.dumps({'version':0}))\n"
        "print(json.dumps({'written':True}))\n"
    )
    parent = SkillBundle(
        {"SKILL.md": "initial Skill; no creation execution", "scripts/main.py": script}
    )
    journal = Journal(tmp_path / "journal", identity={"test": "direct-generator-docker"})
    workspace = tmp_path / "learning"
    with adapter.evolution_session(
        parent, adapter.public_inputs, {}, journal=journal, workspace=workspace
    ) as session:
        session.begin_attempt(parent, True, operation_id="initial")
        written = terminal_json(session, "python3 /work/candidate/scripts/main.py")
        assert written == {"written": True}
        initial = session.submit(parent, initial=True, operation_id="initial/submit")
        assert initial.bundle.bundle_hash == parent.bundle_hash
        original_container = session.runner.container_name
        session.begin_attempt(parent, False, operation_id="revision-1")
        setup = (
            "import json,sysconfig;from pathlib import Path\n"
            "Path(sysconfig.get_path('purelib')).joinpath('tau_evolution_fixture.py').write_text('VALUE=73\\n')\n"
            "Path('/work/candidate/SKILL.md').write_text('revised Skill')\n"
            "p=Path('/work/candidate/scripts/main.py');p.write_text(p.read_text().replace(\"'version':0\",\"'version':1\"))\n"
            "print(json.dumps({'dependency_installed':True}))\n"
        )
        assert terminal_json(session, python_command(setup))["dependency_installed"]
        result = session.terminal(
            "cd /root; export TAU_EVOLUTION_STATE=retained; "
            "python3 -m http.server 8765 --bind 127.0.0.1 >/tmp/tau-evolution-service.log 2>&1 &"
        )
        assert not result.failure and result.exit_code == 0
        probe = (
            "import json,os,time,urllib.request,tau_evolution_fixture\n"
            "for _ in range(30):\n"
            " try: urllib.request.urlopen('http://127.0.0.1:8765',timeout=1); break\n"
            " except OSError: time.sleep(.1)\n"
            "else: raise AssertionError('background service unavailable')\n"
            "print(json.dumps({'state':os.environ['TAU_EVOLUTION_STATE'],'dependency':tau_evolution_fixture.VALUE,'cwd':os.getcwd()}))\n"
        )
        assert terminal_json(session, python_command(probe)) == {
            "state": "retained",
            "dependency": 73,
            "cwd": "/root",
        }
        assert not session.terminal("python3 /work/candidate/scripts/main.py").failure
        revised = session.submit(parent, operation_id="revision-1/submit")
        assert revised.bundle.bundle_hash != parent.bundle_hash
        assert revised.bundle.parent_hash == parent.bundle_hash
        assert revised.execution_id == initial.execution_id
        assert json.loads(
            Path(revised.public_trace["public_artifacts_dir"])
            .joinpath("root/direct-evolution-output.json")
            .read_text()
        ) == {"version": 1}
        assert not any(
            "candidate" in p["path"] or "skills/" in p["path"]
            for p in revised.public_trace["public_artifacts"]
        )
        with formal.episode(revised.bundle) as episode:
            clean = (
                "import importlib.util,json,os;from pathlib import Path\n"
                "print(json.dumps({'output':Path('/root/direct-evolution-output.json').exists(),"
                "'dependency':importlib.util.find_spec('tau_evolution_fixture') is not None,"
                "'state':os.environ.get('TAU_EVOLUTION_STATE')}))\n"
            )
            assert episode_json(formal, episode, python_command(clean)) == {
                "output": False,
                "dependency": False,
                "state": None,
            }
        assert session.runner.container_name == original_container
        session.begin_attempt(revised.bundle, False, operation_id="revision-2")
        session.runner.timeout = 0.2
        timeout = session.terminal("sleep 5")
        assert timeout.failure == "timeout"
        session.runner.timeout = 60
        assert terminal_json(session, python_command(probe))["dependency"] == 73
        evidence = {
            "model_calls": 0,
            "official_grader_calls": 0,
            "execution_id": revised.execution_id,
            "initial_hash": parent.bundle_hash,
            "revised_hash": revised.bundle.bundle_hash,
            "same_container": True,
            "dependency_state": True,
            "background_service": True,
            "shell_state": True,
            "fresh_execution_clean": True,
            "remote_timeout": timeout.failure,
            "submission_hash": revised.submission_hash,
        }
    assert session.runner.container_name is None
    assert any("down" in c for c, _ in transport.calls if c[:2] == ["docker", "compose"])
    if directory := os.environ.get("TAU_CONTAINER_EVIDENCE"):
        destination = Path(directory)
        destination.mkdir(parents=True, exist_ok=True)
        (destination / "skillsbench-direct-generator-docker.json").write_text(
            json.dumps(evidence, indent=2)
        )


def test_real_direct_generator_reconnects_surviving_container(prepared, tmp_path):
    from tau_skill_evolution.journal import Journal

    _formal, adapter, _transport = prepared
    parent = SkillBundle({"SKILL.md": "recoverable parent"})
    journal = Journal(tmp_path / "journal", identity={"test": "direct-generator-recovery"})
    workspace = tmp_path / "learning"
    with (
        pytest.raises(KeyboardInterrupt),
        adapter.evolution_session(
            parent, adapter.public_inputs, {}, journal=journal, workspace=workspace
        ) as session,
    ):
        session.begin_attempt(parent, False, operation_id="revision-1")
        assert not session.terminal(
            "printf 'pending draft' >/work/candidate/SKILL.md; "
            "echo executed >/root/direct-recovery-marker"
        ).failure
        container = session.runner.container_name
        execution_id = session.state["execution_id"]
        raise KeyboardInterrupt
    with adapter.evolution_session(
        parent, adapter.public_inputs, {}, journal=journal, workspace=workspace
    ) as restored:
        restored.begin_attempt(parent, False, operation_id="revision-1")
        assert restored.runner.container_name == container
        assert restored.state["execution_id"] == execution_id
        assert restored.files()["SKILL.md"] == "pending draft"
        assert restored.state["operation_cursor"] == 1
        probe = (
            "import json;from pathlib import Path;"
            "print(json.dumps({'marker':Path('/root/direct-recovery-marker').read_text().strip()}))"
        )
        assert terminal_json(restored, python_command(probe)) == {"marker": "executed"}
    assert restored.runner.container_name is None


def test_real_direct_generator_loop_with_local_responses_provider(prepared, tmp_path):
    import threading
    import urllib.request
    from http.server import BaseHTTPRequestHandler, HTTPServer

    from tau_skill_evolution.artifacts import FrozenBase
    from tau_skill_evolution.generator import RevisionConversation, execute_initial, revise
    from tau_skill_evolution.journal import Journal
    from tau_skill_evolution.model import GenerationConfig, OpenAICompatibleClient

    _formal, adapter, _transport = prepared
    script = (
        "import json;from pathlib import Path\n"
        "Path('/root/provider-loop-output.json').write_text(json.dumps({'version':0}))\n"
        "print(json.dumps({'version':0}))\n"
    )
    parent = SkillBundle({"SKILL.md": "single sealed S0", "scripts/main.py": script})
    edit = (
        "from pathlib import Path;import subprocess\n"
        "Path('/work/candidate/SKILL.md').write_text('inherited S1')\n"
        "p=Path('/work/candidate/scripts/main.py');p.write_text(p.read_text().replace(\"'version':0\",\"'version':1\"))\n"
        "subprocess.run(['python3',str(p)],check=True)\n"
    )
    actions = [
        ("terminal", {"command": "python3 /work/candidate/scripts/main.py"}),
        ("submit_revision", {}),
        ("terminal", {"command": python_command(edit)}),
        ("submit_revision", {}),
    ]
    requests = []

    class Provider(BaseHTTPRequestHandler):
        def do_POST(self):
            requests.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            name, arguments = actions[len(requests) - 1]
            body = json.dumps(
                {
                    "id": f"local-fixture-{len(requests)}",
                    "status": "completed",
                    "output": [
                        {
                            "type": "function_call",
                            "call_id": f"local-{len(requests)}",
                            "name": name,
                            "arguments": json.dumps(arguments),
                        }
                    ],
                    "usage": {"input_tokens": 100, "output_tokens": 30, "total_tokens": 130},
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Provider)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    local_url = f"http://127.0.0.1:{server.server_port}/responses"

    def local_opener(request, *, timeout):
        # Exercise the production client wire contract without contacting its AWS URL.
        redirected = urllib.request.Request(
            local_url,
            data=request.data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        return urllib.request.urlopen(redirected, timeout=timeout)

    counter = SimpleNamespace(
        count=lambda messages, **kwargs: len(json.dumps([messages, kwargs])) // 4 + 1
    )
    model = OpenAICompatibleClient(
        "https://bedrock-mantle.us-east-1.api.aws/openai/v1",
        config=GenerationConfig(
            model="openai.gpt-5.4", reasoning_effort="high", max_output_tokens=None
        ),
        api_key="offline-fixture",
        opener=local_opener,
        token_counter=counter,
    )
    base = FrozenBase((), adapter.public_inputs)
    journal = Journal(tmp_path / "journal", identity={"test": "docker-local-provider"})
    conversation = RevisionConversation()
    try:
        with adapter.evolution_session(
            parent, adapter.public_inputs, base, journal=journal, workspace=tmp_path / "learning"
        ) as session:
            options = {"journal": journal, "session": session, "conversation": conversation}
            initial = execute_initial(model, parent, base.public_inputs, base, **options)
            assert initial.initial and initial.bundle == parent
            revised = revise(model, parent, base.public_inputs, base, {}, **options)
            assert (
                revised.bundle.parent_hash == parent.bundle_hash
                and revised.bundle.bundle_hash != parent.bundle_hash
            )
            assert revised.execution_id == initial.execution_id and revised.operation_cursor == 2
            assert conversation.turns == 4 and len(requests) == 4
            assert json.loads(
                Path(revised.public_trace["public_artifacts_dir"])
                .joinpath("root/provider-loop-output.json")
                .read_text()
            ) == {"version": 1}
            # Completed phase replay parses sealed responses and submits nothing again.
            assert execute_initial(model, parent, base.public_inputs, base, **options) == initial
            assert revise(model, parent, base.public_inputs, base, {}, **options) == revised
            assert len(requests) == 4
            assert all("max_output_tokens" not in request for request in requests)
            assert all(request["reasoning"]["effort"] == "high" for request in requests)
            evidence = {
                "provider": "local HTTP fixture through explicit opener redirect",
                "external_model_calls": 0,
                "local_http_posts": 4,
                "synthetic_usage": True,
                "official_grader_calls_in_test": 0,
                "initial_hash": parent.bundle_hash,
                "revised_hash": revised.bundle.bundle_hash,
                "execution_id": revised.execution_id,
                "operation_cursor": revised.operation_cursor,
                "initial_submission": initial.submission_hash,
                "revision_submission": revised.submission_hash,
                "completed_replay_posts": 0,
            }
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    if directory := os.environ.get("TAU_CONTAINER_EVIDENCE"):
        destination = Path(directory)
        destination.mkdir(parents=True, exist_ok=True)
        (destination / "skillsbench-generator-local-provider-docker.json").write_text(
            json.dumps(evidence, indent=2)
        )


@pytest.mark.skipif(
    os.environ.get("TAU_RUN_SKILLSBENCH_WORKSPACE_INTEGRATION") != "1",
    reason="prepared SkillsBench workspace integration requires explicit opt-in",
)
def test_real_enterprise_workspace_public_inputs_private_grade_and_fresh_environment(tmp_path):
    """Exercise isolation and an unsolved official grade, without a model or answer fixture."""
    root = Path(os.environ.get("TAU_SKILLSBENCH_ROOT", str(EXPERIMENT_ROOT))).resolve()
    original = root / "runtime/skillsbench-bubblewrap-lock.json"
    original_bytes = original.read_bytes()
    selected = root / "runtime/skillsbench-workspace-enterprise-information-search-lock.json"
    runner = SkillsBenchRunner(
        root,
        "enterprise-information-search",
        demo=False,
        runtime="workspace",
        runtime_lock_path=selected,
    )
    preflight = runner.preflight()
    assert preflight["ready"] and preflight["official_grader"], preflight
    assert not preflight["author_environment_equivalent"]
    adapter = SkillsBenchAdapter(
        SimpleNamespace(root=root, values={"source": {"runtime_lock": str(selected)}}),
        "enterprise-information-search",
        demo=False,
        runtime="workspace",
        artifact_root=tmp_path / "public-snapshots",
    )
    adapter.runner = runner
    bundle = SkillBundle({"SKILL.md": "Environment admission only; deliberately unsolved."})
    with runner.episode(bundle) as episode:
        inspection = episode_json(
            runner,
            episode,
            python_command(
                "import json;from pathlib import Path;"
                "Path('/root/episode-marker').write_text('current episode');"
                "print(json.dumps({'input':Path('/root/question.txt').is_file(),"
                "'data':len(list(Path('/root/DATA').rglob('*.json'))),"
                "'private_tests':Path('/tests/test.sh').exists(),"
                "'key':Path('/key.env').exists(),'venv':Path('/root/.venv/bin/python').exists()}))"
            ),
        )
        assert inspection == {
            "input": True,
            "data": 33,
            "private_tests": False,
            "key": False,
            "venv": True,
        }
        # The candidate can write modules in its task directory. The private grader
        # must import the locked pytest, rather than this forged replacement.
        shadow = (
            "from pathlib import Path\n"
            "Path('/root/shadow-was-imported').write_text('unsafe import')\n"
        )
        planted = runner.terminal(
            episode,
            python_command(
                "from pathlib import Path;Path('/root/pytest.py').write_text(" + repr(shadow) + ")"
            ),
        )
        assert planted.exit_code == 0 and planted.failure is None
        trace = adapter._snapshot(episode)
        with runner.public_verifier_session(adapter.public_inputs, {}, trace) as verifier:
            public = terminal_json(
                verifier,
                python_command(
                    "import json;from pathlib import Path;print(json.dumps({"
                    "'input':Path('/root/question.txt').is_file(),"
                    "'skill':Path('/bundle/SKILL.md').exists(),"
                    "'grader':Path('/tests/test.sh').exists()}))"
                ),
            )
            assert public == {"input": True, "skill": False, "grader": False}
        runner.close_public(episode)
        with pytest.raises(PermissionError, match="closed"):
            runner.terminal(episode, "true")
        grade = runner.grade(episode)
        assert grade["status"] == "MEASURED" and grade["reward"] == 0, grade
        (tmp_path / "negative-grade.json").write_text(
            json.dumps(
                {
                    "kind": "offline_module_name_conflict",
                    "experiment_measurement": False,
                    "grade": grade,
                    "shadow_imported": (episode.work / "shadow-was-imported").exists(),
                    "pytest_collected_items": [
                        int(count)
                        for count in re.findall(
                            r"collected\s+(\d+)\s+items?", runner.grader_diagnostics or ""
                        )
                    ],
                    "pytest_terminal_summary": re.findall(
                        r"^=+\s+\d+ (?:passed|failed)[^\n]+?=+$",
                        runner.grader_diagnostics or "",
                        re.MULTILINE,
                    ),
                }
            )
        )
        assert grade["official_checks"] == {
            "status": "MEASURED",
            "source": "pytest-json-ctrf.summary",
            "unit": "reporter_group",
            "passed": 1,
            "total": 3,
            "rate": 1 / 3,
        }
        assert not (episode.work / "shadow-was-imported").exists()
    with runner.episode(bundle) as fresh:
        state = episode_json(
            runner,
            fresh,
            python_command(
                "import json;from pathlib import Path;print(json.dumps({"
                "'marker':Path('/root/episode-marker').exists(),"
                "'input':Path('/root/question.txt').is_file()}))"
            ),
        )
        assert state == {"marker": False, "input": True}
    assert original.read_bytes() == original_bytes


@pytest.mark.skipif(
    os.environ.get("TAU_RUN_SKILLSBENCH_WORKSPACE_INTEGRATION") != "1",
    reason="prepared SkillsBench workspace integration requires explicit opt-in",
)
@pytest.mark.parametrize(
    "task_id,workdir,public_input",
    [
        ("lab-unit-harmonization", "/root", "/root/environment/data/ckd_lab_data.csv"),
        ("manufacturing-codebook-normalization", "/app", "/app/data/test_center_logs.csv"),
        ("dialogue-parser", "/app", "/app/script.txt"),
    ],
)
def test_real_added_workspaces_public_paths_private_grade_and_fresh_episode(
    tmp_path, task_id, workdir, public_input
):
    """Admission only: original public inputs and an unsolved official grade; no answers."""
    root = Path(os.environ.get("TAU_SKILLSBENCH_ROOT", str(EXPERIMENT_ROOT))).resolve()
    original = root / "runtime/skillsbench-bubblewrap-lock.json"
    original_bytes = original.read_bytes()
    runner = SkillsBenchRunner(root, task_id, demo=False, runtime="workspace")
    preflight = runner.preflight()
    assert preflight["ready"] and preflight["official_grader"], preflight
    assert not preflight["author_environment_equivalent"]
    adapter = SkillsBenchAdapter(
        SimpleNamespace(root=root),
        task_id,
        demo=False,
        runtime="workspace",
        artifact_root=tmp_path / "public-snapshots",
    )
    adapter.runner = runner
    bundle = SkillBundle({"SKILL.md": "Environment admission only; deliberately unsolved."})
    marker = workdir + "/episode-marker"
    with runner.episode(bundle) as episode:
        inspection = episode_json(
            runner,
            episode,
            python_command(
                "import json,os;from pathlib import Path;"
                f"Path({marker!r}).write_text('current episode');"
                "print(json.dumps({'cwd':os.getcwd(),"
                f"'input':Path({public_input!r}).is_file(),"
                "'private':Path('/tests/test.sh').exists(),"
                "'key':Path('/key.env').exists(),'venv':Path('/root/.venv/bin/python').exists()}))"
            ),
        )
        assert inspection == {
            "cwd": workdir,
            "input": True,
            "private": False,
            "key": False,
            "venv": True,
        }
        trace = adapter._snapshot(episode)
        with runner.public_verifier_session(adapter.public_inputs, {}, trace) as verifier:
            visibility = terminal_json(
                verifier,
                python_command(
                    "import json;from pathlib import Path;print(json.dumps({"
                    f"'input':Path({public_input!r}).is_file(),"
                    f"'marker':Path({marker!r}).is_file(),"
                    "'skill':Path('/bundle/SKILL.md').exists(),"
                    "'grader':Path('/tests/test.sh').exists()}))"
                ),
            )
            assert visibility == {"input": True, "marker": True, "skill": False, "grader": False}
        runner.close_public(episode)
        with pytest.raises(PermissionError, match="closed"):
            runner.terminal(episode, "true")
        grade = runner.grade(episode)
        assert grade["status"] == "MEASURED" and 0 <= grade["reward"] < 1, grade
        assert grade["official_checks"]["status"] == "MEASURED", grade
        (tmp_path / "negative-grade.json").write_text(
            json.dumps(
                {
                    "experiment_measurement": False,
                    "preflight": preflight,
                    "grade": grade,
                    "pytest_collected_items": [
                        int(n)
                        for n in re.findall(
                            r"collected\s+(\d+)\s+items?", runner.grader_diagnostics or ""
                        )
                    ],
                }
            )
        )
    with runner.episode(bundle) as fresh:
        state = episode_json(
            runner,
            fresh,
            python_command(
                "import json;from pathlib import Path;print(json.dumps({"
                f"'marker':Path({marker!r}).exists(),'input':Path({public_input!r}).is_file()"
                + "}))"
            ),
        )
        assert state == {"marker": False, "input": True}
    assert original.read_bytes() == original_bytes


@pytest.mark.skipif(
    os.environ.get("TAU_RUN_SKILLSBENCH_WORKSPACE_INTEGRATION") != "1",
    reason="prepared SkillsBench workspace integration requires explicit opt-in",
)
def test_real_workspace_public_solution_private_grade_and_fresh_environment(tmp_path, monkeypatch):
    from tau_skill_evolution.artifacts import atomic_json
    from tau_skill_evolution.skillsbench import _hash

    root = Path(os.environ.get("TAU_SKILLSBENCH_ROOT", str(EXPERIMENT_ROOT))).resolve()
    runner = SkillsBenchRunner(root, TASK, demo=False, runtime="workspace")
    preflight = runner.preflight()
    assert preflight["ready"] and not preflight["demo_only"]
    assert preflight["official_grader"] and not preflight["author_environment_equivalent"]
    adapter = SkillsBenchAdapter(
        SimpleNamespace(root=root),
        TASK,
        demo=False,
        runtime="workspace",
        artifact_root=tmp_path / "public-snapshots",
    )
    adapter.runner = runner
    monkeypatch.setenv(HOST_ENV_SENTINEL, "host-only-public-test-sentinel")
    host_file = tmp_path / "host-only.txt"
    host_file.write_text("host-only-public-test-sentinel")
    host_key = Path(__file__).resolve().parents[5] / "key.env"
    bundle = SkillBundle(
        {
            "SKILL.md": "Handcrafted public-input environment fixture; no model execution.",
            "scripts/fixture.py": _SCAN_FIXTURE,
        }
    )
    with runner.episode(bundle) as episode:
        boundary = episode_json(
            runner,
            episode,
            python_command(
                f"import json,os;from pathlib import Path;print(json.dumps({{"
                f"'host_file_visible':Path({str(host_file)!r}).exists(),"
                f"'host_key_visible':Path({str(host_key)!r}).exists(),"
                f"'host_env_visible':os.environ.get({HOST_ENV_SENTINEL!r}) is not None,"
                "'official_tests_visible':Path('/tests/test.sh').exists(),"
                "'venv':os.environ.get('VIRTUAL_ENV')}))"
            ),
        )
        assert boundary == {
            "host_file_visible": False,
            "host_key_visible": False,
            "host_env_visible": False,
            "official_tests_visible": False,
            "venv": "/root/.venv",
        }
        state = runner.terminal(
            episode,
            "mkdir -p /root/state; cd /root/state; export WORKSPACE_TEST_STATE=public; "
            "echo kept >marker.txt",
        )
        assert state.exit_code == 0 and state.failure is None
        persisted = episode_json(
            runner,
            episode,
            python_command(
                "import json,os;from pathlib import Path;print(json.dumps({'cwd':os.getcwd(),"
                "'export':os.environ.get('WORKSPACE_TEST_STATE'),"
                "'file':Path('marker.txt').read_text().strip()}))"
            ),
        )
        assert persisted == {"cwd": "/root/state", "export": "public", "file": "kept"}
        execution = episode.run_skill_script("scripts/fixture.py", {})
        assert execution.exit_code == 0 and execution.failure is None, execution.to_dict()
        trace = adapter._snapshot(episode)
        assert not any(
            "/.venv/" in p["path"] or "/.evolution/" in p["path"] for p in trace["public_artifacts"]
        )
        with runner.public_verifier_session(adapter.public_inputs, {}, trace) as verifier:
            inspection = terminal_json(
                verifier,
                python_command(
                    "import json;from pathlib import Path;print(json.dumps({"
                    "'report':Path('/root/mass_report.json').exists(),"
                    "'skill':Path('/bundle/SKILL.md').exists(),'grader':Path('/tests/test.sh').exists()}))"
                ),
            )
            assert inspection == {"report": True, "skill": False, "grader": False}
            readonly = verifier.terminal("echo tampered >>/root/mass_report.json")
            assert readonly.exit_code != 0
        runner.close_public(episode)
        for invoke in (
            lambda: runner.terminal(episode, "cat /tests/test.sh"),
            lambda: episode.read_skill_file("SKILL.md"),
            lambda: episode.run_skill_script("scripts/fixture.py", {}),
        ):
            with pytest.raises(PermissionError, match="closed"):
                invoke()
        grade = runner.grade(episode)
        assert grade["status"] == "MEASURED" and grade["reward"] == 1, grade
        assert grade["official_checks"] == {
            "status": "MEASURED",
            "source": "pytest-json-ctrf.summary",
            "unit": "reporter_group",
            "passed": 2,
            "total": 2,
            "rate": 1.0,
        }
    with runner.episode(bundle) as fresh_episode:
        fresh = episode_json(
            runner,
            fresh_episode,
            python_command(
                "import json,os;from pathlib import Path;print(json.dumps({"
                "'old_report':Path('/root/mass_report.json').exists(),"
                "'old_marker':Path('/root/state/marker.txt').exists(),"
                "'export':os.environ.get('WORKSPACE_TEST_STATE'),"
                "'fresh_venv':Path('/root/.venv/bin/python').exists()}))"
            ),
        )
        assert fresh == {
            "old_report": False,
            "old_marker": False,
            "export": None,
            "fresh_venv": True,
        }
    atomic_json(
        root / "data/skillsbench/workspace-checks.json",
        {
            "kind": "offline-handcrafted",
            "experiment_measurement": False,
            "model_requests": 0,
            "api_requests": 0,
            "task_id": TASK,
            "runtime": "workspace",
            "lock_hash": _hash(root / "runtime/skillsbench-bubblewrap-lock.json"),
            "preflight": preflight,
            "boundary": boundary,
            "persisted": persisted,
            "fresh": fresh,
            "public_tools_closed": 3,
            "official_grade": grade,
        },
    )


def test_real_persistent_shell_background_service_and_fresh_episode(prepared):
    runner, _adapter, _transport = prepared
    server = """from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from functools import partial
from pathlib import Path
root = Path(__file__).parent
server = ThreadingHTTPServer(
    ('127.0.0.1', 0), partial(SimpleHTTPRequestHandler, directory=str(root)))
(root/'port').write_text(str(server.server_address[1]))
server.serve_forever()
"""
    prepare = f"""from pathlib import Path
root = Path({PUBLIC_ROOT!r}); root.mkdir()
(root/'server.py').write_text({server!r})
(root/'index.html').write_text('live integration fixture')
"""
    bundle = SkillBundle({"SKILL.md": "No model or external service is used by this check."})
    with runner.episode(bundle) as episode:
        container = runner.container_name
        setup = (
            python_command(prepare)
            + "; cd "
            + shlex.quote(PUBLIC_ROOT)
            + "; export TAU_INTEGRATION_PERSISTED=public-fixture; "
            "nohup python3 server.py >server.log 2>&1 </dev/null & "
            "printf '%s\n' '{\"started\":true}'"
        )
        assert episode_json(runner, episode, setup) == {"started": True}
        inspect = f"""import json, os, time, urllib.request
from pathlib import Path
root = Path({PUBLIC_ROOT!r})
for _ in range(100):
    if (root/'port').exists(): break
    time.sleep(.05)
port = int((root/'port').read_text())
body = urllib.request.urlopen(f'http://127.0.0.1:{{port}}/', timeout=5).read().decode()
print(json.dumps({{'cwd':os.getcwd(),'export':os.environ.get('TAU_INTEGRATION_PERSISTED'),
                  'body':body,'private_tests':Path('/tests/test.sh').exists()}}))
"""
        assert episode_json(runner, episode, python_command(inspect)) == {
            "cwd": PUBLIC_ROOT,
            "export": "public-fixture",
            "body": "live integration fixture",
            "private_tests": False,
        }
        assert runner.container_name == container
    assert runner.container_name is None and not runner.public_open
    with runner.episode(bundle) as fresh:
        result = episode_json(
            runner,
            fresh,
            python_command(
                f"import json, os; from pathlib import Path; "
                f"print(json.dumps({{'old':Path({PUBLIC_ROOT!r}).exists(),"
                "'export':os.environ.get('TAU_INTEGRATION_PERSISTED')}))"
            ),
        )
        assert result == {"old": False, "export": None}
        assert runner.container_name != container


def test_real_public_verifier_reads_complete_artifacts_and_locks_diagnosis_tests(
    prepared, monkeypatch
):
    runner, adapter, _transport = prepared
    monkeypatch.setenv(HOST_ENV_SENTINEL, "undeclared-host-fixture")
    live = SkillBundle({"SKILL.md": PARENT_MARKER})
    with runner.episode(live) as episode:
        episode_json(
            runner,
            episode,
            python_command(
                f"import json; from pathlib import Path; root=Path({PUBLIC_ROOT!r}); root.mkdir(); "
                "(root/'artifact.bin').write_bytes(b'actual public bytes'); "
                "(root/'empty').mkdir(); print(json.dumps({'created':True}))"
            ),
        )
        trace = adapter._snapshot(episode)
    public_file = PUBLIC_ROOT + "/artifact.bin"
    source = f"""import os
from pathlib import Path

def test_public_artifacts_and_source_blindness():
    assert Path({public_file!r}).read_bytes() == b'actual public bytes'
    assert Path({(PUBLIC_ROOT + "/empty")!r}).is_dir()
    assert not Path('/bundle/SKILL.md').exists()
    assert not Path('/work/candidate').exists()
    assert not Path('/tests/test.sh').exists()
    assert not Path('/app/environment/skills').exists()
    assert {HOST_ENV_SENTINEL!r} not in os.environ
    try:
        Path({public_file!r}).write_bytes(b'tamper')
    except OSError:
        pass
    else:
        assert False, 'public artifact mount is writable'
"""
    files = {"tests/test_public.py": source}
    with runner.public_verifier_session(adapter.public_inputs, {}, trace) as verifier:
        terminal_json(
            verifier,
            python_command(
                f"import json; from pathlib import Path; "
                f"Path('/work/tests/test_public.py').write_text({source!r}); "
                "print(json.dumps({'written':True}))"
            ),
        )
        report = _report(TestSuite(verifier.files()), verifier.run_tests())
        assert report.passed, report.to_dict()
        assert verifier.files() == files
    with runner.public_verifier_session(
        adapter.public_inputs, {}, trace, files, readonly_tests=True
    ) as diagnosis:
        probe = """import json
from pathlib import Path
try:
    Path('/bundle/tests/test_public.py').write_text('tamper')
    readonly = False
except OSError:
    readonly = True
Path('/work/scratch/diagnosis').write_text('public-only note')
print(json.dumps({'tests_readonly':readonly,'candidate_visible':Path('/work/candidate').exists()}))
"""
        assert terminal_json(diagnosis, python_command(probe)) == {
            "tests_readonly": True,
            "candidate_visible": False,
        }
        assert diagnosis.files() == files
        assert _report(TestSuite(files), diagnosis.run_tests()).passed
    assert (
        runner._public_artifacts(trace) / public_file.lstrip("/")
    ).read_bytes() == b"actual public bytes"


def test_real_public_verifier_rejects_existing_outputs_with_broken_export_entry(prepared):
    """A synthetic public rebuild obligation, never an ACC answer or official grade."""
    runner, adapter, _transport = prepared
    fixture_root = "/root/.tau-public-export-fixture"
    public_inputs = {
        "task": "synthetic public export requirement",
        "request": "Generate JSON and CSV reports containing value 12; "
        "export.py must rebuild them.",
        "export_entry": fixture_root + "/export.py",
    }
    package = SkillBundle({"SKILL.md": PARENT_MARKER})
    code = f"""import json
from pathlib import Path
root = Path({fixture_root!r})
root.mkdir()
(root/'report.json').write_text(json.dumps({{'value':12}}))
(root/'report.csv').write_text('value\\n12\\n')
(root/'export.py').write_text("raise RuntimeError('synthetic public entry cannot rebuild')\\n")
print(json.dumps({{'created':True}}))
"""
    with runner.episode(package) as episode:
        assert episode_json(runner, episode, python_command(code)) == {"created": True}
        trace = adapter._snapshot(episode)
    simple = f"""import csv,json,subprocess,sys
from pathlib import Path
ROOT = Path({fixture_root!r})

def test_existing_json_report():
    assert json.loads((ROOT/'report.json').read_text()) == {{'value':12}}

def test_existing_csv_report():
    with (ROOT/'report.csv').open() as stream:
        assert list(csv.DictReader(stream)) == [{{'value':'12'}}]
"""
    rebuild = """
def test_public_export_rebuilds_in_scratch():
    destination = Path('/work/scratch/rebuilt')
    destination.mkdir()
    result = subprocess.run(
        [sys.executable,str(ROOT/'export.py'),'--output',str(destination)],
        capture_output=True,text=True,check=False,
    )
    assert result.returncode == 0, 'public export entry must rebuild reports'
    assert json.loads((destination/'report.json').read_text()) == {'value':12}
    assert (destination/'report.csv').read_text() == 'value\\n12\\n'
"""
    with runner.public_verifier_session(public_inputs, {}, trace) as verifier:
        visibility = terminal_json(
            verifier,
            python_command(
                "import json;from pathlib import Path;print(json.dumps({"
                "'skill':Path('/bundle/SKILL.md').exists(),"
                "'candidate':Path('/work/candidate').exists(),"
                "'official_grader':Path('/tests/test.sh').exists()}))"
            ),
        )
        assert visibility == {"skill": False, "candidate": False, "official_grader": False}
        terminal_json(
            verifier,
            python_command(
                "import json;from pathlib import Path;"
                f"Path('/work/tests/test_public.py').write_text({simple!r});"
                "print(json.dumps({'written':True}))"
            ),
        )
        existing = _report(TestSuite(verifier.files()), verifier.run_tests())
        assert existing.passed and existing.pass_rate == 1
        terminal_json(
            verifier,
            python_command(
                "import json;from pathlib import Path;"
                f"Path('/work/tests/test_public.py').write_text({(simple + rebuild)!r});"
                "print(json.dumps({'written':True}))"
            ),
        )
        program = verifier.run_tests()
        checked = _report(TestSuite(verifier.files()), program)
        assert program.exit_code == 1 and program.failure == "nonzero_exit"
        assert not checked.passed and not checked.program_error and checked.failure is None
        assert checked.pass_rate == 2 / 3
        failed = [
            item
            for item in checked.results
            if item["stage"] == "call" and item["outcome"] == "failed"
        ]
        assert len(failed) == 1 and failed[0]["exception"] == "AssertionError"
    if directory := os.environ.get("TAU_CONTAINER_EVIDENCE"):
        destination = Path(directory)
        destination.mkdir(parents=True, exist_ok=True)
        (destination / "skillsbench-public-export-rebuild-counterexample.json").write_text(
            json.dumps(
                {
                    "fixture": "synthetic public rebuild obligation in prepared 3d-scan-calc image",
                    "experiment_measurement": False,
                    "external_model_calls": 0,
                    "official_grader_calls_in_test": 0,
                    "public_inputs": public_inputs,
                    "visibility": visibility,
                    "existing_outputs": existing.to_dict(),
                    "with_rebuild_obligation": checked.to_dict(),
                    "actual_pytest_exit_code": program.exit_code,
                },
                indent=2,
            )
        )


def test_real_official_grade_uses_closed_same_episode_and_process_environment(prepared, tmp_path):
    runner, adapter, transport = prepared
    marker_name, marker_value = "TAU_INTEGRATION_PRIVATE_FIXTURE", "public-integration-fixture"
    bundle = SkillBundle({"SKILL.md": "No deliverable: official checks should measure failure."})
    evidence = tmp_path / "private/official-grader"
    start = len(transport.calls)
    with runner.episode(bundle) as episode:
        staging = episode.work.parent
        episode.grader_evidence_dir = evidence
        episode.grader_identity = {"bundle_hash": bundle.bundle_hash}
        container = runner.container_name
        episode_json(
            runner,
            episode,
            python_command(
                f"import json; from pathlib import Path; root=Path({PUBLIC_ROOT!r}); root.mkdir(); "
                "(root/'episode.marker').write_text('same episode'); "
                "print(json.dumps({'created':True}))"
            ),
        )
        with pytest.raises(PermissionError, match="before_public_close"):
            runner.grade(episode)
        trace = adapter._snapshot(episode)
        runner.close_public(episode)
        for operation in (
            lambda: runner.terminal(episode, "true"),
            lambda: episode.read_skill_file("SKILL.md"),
            lambda: episode.run_skill_script("scripts/missing.py", {}),
        ):
            with pytest.raises(PermissionError, match="public_episode_closed"):
                operation()
        # A harmless declared fixture proves Docker exec uses process env, while
        # official task variables remain untouched and their values are never logged.
        private = runner._exec(
            [
                "python",
                "-c",
                "import os,json; print(json.dumps({'marker':os.environ.get("
                + repr(marker_name)
                + ")}))",
            ],
            public=False,
            environment={marker_name: marker_value},
        )
        assert _program_result(private).output == {"marker": marker_value}
        measured = runner.grade(episode)
        assert measured["status"] == "MEASURED", measured
        assert measured["utility"] is False and measured["reward"] == 0, measured
        assert runner.container_name == container and not runner.public_open
        private = runner._exec(
            [
                "python",
                "-c",
                f"import json; from pathlib import Path; print(json.dumps("
                f"{{'state':Path({(PUBLIC_ROOT + '/episode.marker')!r}).read_text()}}))",
            ],
            public=False,
        )
        assert _program_result(private).output == {"state": "same episode"}
        with pytest.raises(PermissionError, match="already_started"):
            runner.grade(episode)
        assert runner._public_artifacts(trace).is_dir()
    assert not staging.exists()
    record = json.loads((evidence / "evidence.json").read_text())
    assert record["verdict"] == measured
    assert record["identity"]["bundle_hash"] == bundle.bundle_hash
    assert record["official_items"] == [
        {"name": item.get("name"), "status": item.get("status")}
        for item in json.loads((evidence / "ctrf.json").read_text())["results"]["tests"]
    ]
    assert record["official_items"] and record["files"]["stdout.bin"]["bytes"] > 0
    assert evidence.stat().st_mode & 0o777 == 0o700
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in evidence.iterdir())
    calls = transport.calls[start:]
    graders = [
        (command, variables)
        for command, variables in calls
        if command[:2] == ["docker", "exec"] and command[-2:] == ["/bin/bash", "/tests/test.sh"]
    ]
    assert len(graders) == 1 and container in graders[0][0]
    expected_variables = set(runner.config["verifier"].get("env", {}))
    assert expected_variables <= graders[0][1]
    for name in expected_variables:
        assert any(
            graders[0][0][index : index + 2] == ["--env", name]
            for index in range(len(graders[0][0]) - 1)
        )
    private_probes = [command for command, _variables in calls if marker_name in command]
    assert len(private_probes) == 1
    assert marker_value not in private_probes[0]
    assert runner.container_name is None and not runner.public_open
