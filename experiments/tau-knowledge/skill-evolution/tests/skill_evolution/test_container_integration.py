"""Opt-in real Docker boundaries; skipped tests do not attest container isolation."""

import json
import os
from pathlib import Path

import pytest
from tau_skill_evolution.artifacts import SkillBundle
from tau_skill_evolution.container import DockerRunner, ImageLock

pytestmark = pytest.mark.skipif(
    os.environ.get("TAU_RUN_CONTAINER_INTEGRATION") != "1",
    reason="real Docker integration is opt-in; no container boundary has been measured",
)


@pytest.fixture
def runner():
    path = Path(
        os.environ.get(
            "TAU_IMAGE_LOCK", "experiments/tau-knowledge/skill-evolution/runtime/image-lock.json"
        )
    )
    runner = DockerRunner(ImageLock.from_file(path))
    assert runner.preflight()["ready"], (
        "explicit integration requires prepared pinned Docker runtime"
    )
    return runner


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
        assert (
            episode.run_skill_script("scripts/main.py", {"state": "two"}).output["previous"]
            == "one"
        )
    with runner.episode(bundle) as episode:
        assert (
            episode.run_skill_script("scripts/main.py", {"state": "new"}).output["previous"] is None
        )


def test_real_network_host_files_and_root_are_inaccessible(runner, tmp_path):
    secret = tmp_path / "host-secret"
    secret.write_text("must never mount this file")
    code = f"""import json,os,pathlib,socket
result={{'uid':os.getuid(),'host_visible':pathlib.Path({json.dumps(str(secret))}).exists()}}
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
        assert result.failure is None
        assert result.output == {
            "uid": os.getuid() if os.getuid() else 10001,
            "host_visible": False,
            "network": False,
            "root_writable": False,
        }


def test_real_verifier_reports_assertions_and_rejects_skips(runner):
    result = runner.run_verifier(
        {}, {}, {"ok": True}, {"tests/test_trace.py": "def test_trace(trace): assert trace['ok']\n"}
    )
    assert result.failure is None and result.output["collected"] == 1
    assert result.output["results"][0]["outcome"] == "passed"
    result = runner.run_verifier(
        {},
        {},
        {"ok": False},
        {"tests/test_trace.py": "def test_trace(trace): assert trace['ok']\n"},
    )
    assert result.failure is None and result.output["exit_code"] == 1
    assert result.output["results"][0]["exception"] == "AssertionError"
