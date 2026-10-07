"""Opt-in real Docker boundaries; skipped tests do not attest container isolation."""

import json
import os
import shlex
import subprocess
from pathlib import Path

import pytest
from tau_skill_evolution.artifacts import SkillBundle
from tau_skill_evolution.container import BoundedProcessTransport, DockerRunner, ImageLock
from tau_skill_evolution.verifier import TestSuite, _report

pytestmark = pytest.mark.skipif(
    os.environ.get("TAU_RUN_CONTAINER_INTEGRATION") != "1",
    reason="real Docker integration is opt-in; no container boundary has been measured",
)


@pytest.fixture(scope="module")
def runner():
    path = Path(
        os.environ.get(
            "TAU_IMAGE_LOCK", "experiments/tau-knowledge/skill-evolution/runtime/image-lock.json"
        )
    )
    runner = DockerRunner(ImageLock.from_file(path))
    readiness = runner.preflight()
    _record("preflight", readiness)
    assert readiness["ready"], "explicit integration requires prepared pinned Docker runtime"
    return runner


def _record(name, value):
    """Optionally preserve real results without changing historical run paths."""
    directory = os.environ.get("TAU_CONTAINER_EVIDENCE")
    if directory:
        root = Path(directory)
        root.mkdir(parents=True, exist_ok=True)
        (root / f"{name}.json").write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )


def _python(code):
    return "python -c " + shlex.quote(code)


def test_real_dependencies_helpers_references_and_episode_workspace(runner):
    code = """import importlib.metadata as m,json,pathlib,sys,helper
data=json.load(sys.stdin)
path=pathlib.Path('/work/state')
previous=path.read_text() if path.exists() else None
path.write_text(data['state'])
print(json.dumps({'previous':previous,'helper':helper.VALUE,
 'reference':pathlib.Path('/bundle/references/policy.txt').read_text(),
 'versions':{p:m.version(p) for p in ('numpy','pandas','pytest')}}))
"""
    bundle = SkillBundle(
        {
            "SKILL.md": "s",
            "scripts/main.py": code,
            "scripts/helper.py": "VALUE=7",
            "references/policy.txt": "public policy",
        }
    )
    with runner.episode(bundle) as episode:
        first = episode.run_skill_script("scripts/main.py", {"state": "one"})
        assert first.failure is None and first.output["previous"] is None
        assert first.output["helper"] == 7 and first.output["reference"] == "public policy"
        assert first.output["versions"] == {"numpy": "2.2.6", "pandas": "2.2.3", "pytest": "8.4.2"}
        _record("dependencies-helper-reference", first.to_dict())
        assert (
            episode.run_skill_script("scripts/main.py", {"state": "two"}).output["previous"]
            == "one"
        )
    with runner.episode(bundle) as episode:
        assert (
            episode.run_skill_script("scripts/main.py", {"state": "new"}).output["previous"] is None
        )


def test_real_network_host_files_and_root_are_inaccessible(runner, tmp_path, monkeypatch):
    secret = tmp_path / "host-secret"
    secret.write_text("must never mount this file")
    monkeypatch.setenv("TAU_CONTAINER_HOST_ONLY", "host-fixture-must-not-be-inherited")
    code = f"""import json,os,pathlib,socket
result={{'uid':os.getuid(),'host_visible':pathlib.Path({json.dumps(str(secret))}).exists(),
 'docker_socket_visible':pathlib.Path('/var/run/docker.sock').exists(),
 'host_env_inherited':'TAU_CONTAINER_HOST_ONLY' in os.environ,
 'aws_credentials_present':any(key in os.environ for key in
 ('AWS_BEARER_TOKEN_BEDROCK','AWS_ACCESS_KEY_ID','AWS_SECRET_ACCESS_KEY','AWS_SESSION_TOKEN'))}}
try:
 socket.create_connection(('1.1.1.1',443),timeout=1).close()
 result['network']=True
except OSError: result['network']=False
try:
 pathlib.Path('/root-file').write_text('x')
 result['root_writable']=True
except OSError: result['root_writable']=False
print(json.dumps(result))
"""
    with runner.episode(SkillBundle({"SKILL.md": "s", "scripts/probe.py": code})) as episode:
        result = episode.run_skill_script("scripts/probe.py", {})
        _record("network-host-environment-isolation", result.to_dict())
        assert result.failure is None
        assert result.output == {
            "uid": os.getuid() if os.getuid() else 10001,
            "host_visible": False,
            "docker_socket_visible": False,
            "host_env_inherited": False,
            "aws_credentials_present": False,
            "network": False,
            "root_writable": False,
        }


def test_real_cgroup_resource_limits_and_bundle_readonly(runner):
    code = """import json,pathlib
root=pathlib.Path('/sys/fs/cgroup')
result={name:(root/name).read_text().strip()
 for name in ('cpu.max','memory.max','memory.swap.max','pids.max')}
try:
 pathlib.Path('/bundle/SKILL.md').write_text('tampered')
 result['bundle_writable']=True
except OSError: result['bundle_writable']=False
print(json.dumps(result))
"""
    with runner.episode(SkillBundle({"SKILL.md": "parent", "scripts/probe.py": code})) as episode:
        result = episode.run_skill_script("scripts/probe.py", {})
        _record("resource-limits-readonly-bundle", result.to_dict())
        assert result.failure is None
        quota, period = map(int, result.output["cpu.max"].split())
        assert quota / period == 1
        assert result.output["memory.max"] == "1073741824"
        assert result.output["memory.swap.max"] == "0"
        assert result.output["pids.max"] == "64"
        assert result.output["bundle_writable"] is False
        assert episode.read_skill_file("SKILL.md") == "parent"


def test_real_verifier_reports_assertions(runner):
    result = runner.run_verifier(
        {}, {}, {"ok": True}, {"tests/test_trace.py": "def test_trace(trace): assert trace['ok']\n"}
    )
    assert result.failure is None and result.output["collected"] == 1
    assert result.output["results"][0]["outcome"] == "passed"
    _record("verifier-pass", result.to_dict())
    result = runner.run_verifier(
        {},
        {},
        {"ok": False},
        {"tests/test_trace.py": "def test_trace(trace): assert trace['ok']\n"},
    )
    assert result.exit_code == 1 and result.failure == "nonzero_exit"
    assert result.output["exit_code"] == result.exit_code
    assert result.output["results"][0]["exception"] == "AssertionError"
    report = _report(
        TestSuite({"tests/test_trace.py": "def test_trace(trace): assert trace['ok']\n"}), result
    )
    assert not report.passed and not report.program_error
    _record("verifier-assertion-failure", {"program": result.to_dict(), "report": report.to_dict()})


def test_real_verifier_report_survives_known_serializer_monkeypatch(runner):
    spoof = json.dumps(
        {
            "exit_code": 0,
            "collected": 1,
            "collected_nodeids": ["tests/test_trace.py::test_trace"],
            "collection_errors": 0,
            "results": [
                {
                    "nodeid": "tests/test_trace.py::test_trace",
                    "stage": "call",
                    "outcome": "passed",
                    "exception": None,
                    "requirement_failure": False,
                    "xfail": False,
                }
            ],
        }
    )
    source = (
        "import json\ndef test_trace(trace):\n"
        f" json.dumps = lambda *args, **kwargs: {spoof!r}\n"
        f" json.JSONEncoder.encode = lambda *args, **kwargs: {spoof!r}\n"
        " assert trace['ok']\n"
    )
    suite = TestSuite({"tests/test_trace.py": source})
    result = runner.run_verifier({}, {}, {"ok": False}, suite.files)
    report = _report(suite, result)
    _record(
        "verifier-serializer-contamination",
        {"program": result.to_dict(), "report": report.to_dict()},
    )
    assert result.exit_code == result.output["exit_code"] == 1
    assert result.failure == "nonzero_exit" and "AssertionError" in result.stderr
    assert result.output["results"][0]["outcome"] == "failed"
    assert not report.passed and not report.program_error


@pytest.mark.parametrize("outcome", ["skip", "xfail"])
def test_real_verifier_rejects_runtime_skips_and_xfails(runner, outcome):
    source = (
        "import pytest\ndef test_trace(trace):\n"
        f" getattr(pytest, {outcome!r})('runtime fixture')\n assert trace['ok']\n"
    )
    suite = TestSuite({"tests/test_trace.py": source})
    program = runner.run_verifier({}, {}, {"ok": True}, suite.files)
    report = _report(suite, program)
    _record(f"verifier-{outcome}", {"program": program.to_dict(), "report": report.to_dict()})
    assert program.failure is None
    assert not report.passed and report.program_error and report.failure == "skip_or_xfail"


def test_real_revision_edits_parent_without_public_or_private_access(runner, tmp_path):
    private = tmp_path / "official-grader.py"
    private.write_text("host-only-private-fixture")
    parent = SkillBundle(
        {"SKILL.md": "parent", "scripts/helper.py": "VALUE=7", "references/policy.txt": "policy"}
    )
    public_inputs, base = {"request": "public"}, {"documents": ["policy"]}
    self_check = (
        "import helper,json,pathlib\n"
        "print(json.dumps({'value':helper.VALUE,"
        "'policy':pathlib.Path('references/policy.txt').read_text()}))\n"
    )
    with runner.authoring_session(parent, public_inputs, base) as session:
        code = f"""import json,pathlib
root=pathlib.Path('/work/candidate')
assert (root/'SKILL.md').read_text()=='parent'
assert json.loads(pathlib.Path('/bundle/public_inputs.json').read_text())=={{'request':'public'}}
assert not pathlib.Path({json.dumps(str(private))}).exists()
assert not pathlib.Path('/work/tests').exists()
assert not pathlib.Path('/bundle/SKILL.md').exists()
assert json.loads(pathlib.Path('/bundle/trace.json').read_text())=={{}}
for path in ('/bundle/base.json','/work/unauthorized'):
 try: pathlib.Path(path).write_text('tampered')
 except OSError: pass
 else: raise AssertionError('public boundary writable: '+path)
(root/'SKILL.md').write_text('revised')
(root/'scripts/main.py').write_text({self_check!r})
pathlib.Path('/work/scratch/state').write_text('same authoring session')
print(json.dumps({{'revised':True}}))
"""
        edit = session.terminal(_python(code))
        assert edit.failure is None and edit.exit_code == 0, edit.to_dict()
        check = session.terminal("cd /work/candidate && python scripts/main.py")
        _record(
            "revision-parent-public-isolation",
            {"edit": edit.to_dict(), "self_check": check.to_dict()},
        )
        assert check.failure is None and check.exit_code == 0, check.to_dict()
        assert json.loads(check.output["stdout"]) == {"value": 7, "policy": "policy"}
        assert session.files()["SKILL.md"] == "revised"
        assert (session.work / "scratch/state").read_text() == "same authoring session"
        staging = session.package.parent
    assert not staging.exists() and parent.files["SKILL.md"] == "parent"


def test_real_verifier_inspects_public_files_and_locks_diagnosis_suite(runner):
    tests = {
        "tests/test_trace.py": (
            "def test_trace(public_inputs, frozen_base, trace):\n"
            " assert public_inputs['request']=='public'\n"
            " assert frozen_base['documents']==['policy']\n"
            " assert trace['ok']\n"
        )
    }
    public_inputs, base, trace = {"request": "public"}, {"documents": ["policy"]}, {"ok": True}
    with runner.public_verifier_session(public_inputs, base, trace) as session:
        code = (
            """import json,pathlib
root=pathlib.Path('/bundle')
assert not (root/'SKILL.md').exists()
assert not pathlib.Path('/work/candidate').exists()
assert json.loads((root/'trace.json').read_text())['ok']
"""
            + "pathlib.Path('/work/tests/test_trace.py').write_text("
            + repr(tests["tests/test_trace.py"])
            + ")\n"
        )
        inspect = session.terminal(_python(code))
        assert inspect.failure is None and inspect.exit_code == 0, inspect.to_dict()
        result = session.run_tests()
        _record("verifier-public-file-authoring", result.to_dict())
        assert _report(TestSuite(session.files()), result).passed
        assert session.files() == tests
        staging = session.package.parent
    assert not staging.exists()
    with runner.public_verifier_session(
        public_inputs, base, trace, tests, readonly_tests=True
    ) as session:
        code = """import pathlib
for path in ('/bundle/tests/test_trace.py','/bundle/base.json','/work/tests/test_trace.py'):
 try: pathlib.Path(path).write_text('tampered')
 except OSError: pass
 else: raise AssertionError('diagnostic boundary writable: '+path)
pathlib.Path('/work/scratch/diagnosis').write_text('public inspection')
"""
        diagnosis = session.terminal(_python(code))
        assert diagnosis.failure is None and diagnosis.exit_code == 0, diagnosis.to_dict()
        result = session.run_tests()
        _record(
            "verifier-readonly-diagnosis",
            {"diagnosis": diagnosis.to_dict(), "program": result.to_dict()},
        )
        assert _report(TestSuite(session.files()), result).passed and session.files() == tests


@pytest.mark.parametrize(
    ("source", "failure"),
    [
        ("print('not JSON')", "invalid_json"),
        ("import unavailable_tau_fixture_dependency", "nonzero_exit"),
        ("import time; time.sleep(30)", "timeout"),
        ("import sys; sys.stderr.write('x'*8192)", "output_limit"),
    ],
)
def test_real_script_failures_are_bounded_and_containers_cleaned(runner, source, failure):
    class ObservedTransport(BoundedProcessTransport):
        def __init__(self):
            super().__init__()
            self.names = []

        def run(self, command, **kwargs):
            if "run" in command and "--name" in command:
                self.names.append(command[command.index("--name") + 1])
            return super().run(command, **kwargs)

    transport = ObservedTransport()
    bounded = DockerRunner(runner.image_lock, transport=transport, timeout=3, output_limit=1024)
    with bounded.episode(SkillBundle({"SKILL.md": "s", "scripts/main.py": source})) as episode:
        result = episode.run_skill_script("scripts/main.py", {})
        _record(f"script-failure-{failure}", result.to_dict())
        assert result.failure == failure, result.to_dict()
        assert len(result.stderr.encode()) <= 1024
        staging = episode.package.parent
    assert not staging.exists() and len(transport.names) == 1
    inspection = subprocess.run(
        [runner.docker, "container", "inspect", transport.names[0]],
        capture_output=True,
        text=True,
        timeout=10,
    )
    _record(f"cleanup-{failure}", {"exit_code": inspection.returncode, "stderr": inspection.stderr})
    assert inspection.returncode != 0 and "no such" in inspection.stderr.lower()
