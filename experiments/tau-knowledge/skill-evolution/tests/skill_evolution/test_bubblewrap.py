import hashlib
import json
import os
import time
import uuid
from pathlib import Path

import pytest
from tau_skill_evolution.artifacts import SkillBundle
from tau_skill_evolution.bubblewrap import BubblewrapRunner, RuntimeLock
from tau_skill_evolution.constants import EXPERIMENT_ROOT
from tau_skill_evolution.container import ContainerUnavailable, ProcessResult


def locked(tmp_path):
    rootfs = tmp_path / "rootfs"
    binary = rootfs / "usr/local/bin/python"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"offline fixture, never executed")
    requirements = tmp_path / "requirements.lock"
    requirements.write_bytes((EXPERIMENT_ROOT / "runtime/requirements.lock").read_bytes())
    value = {
        "rootfs": "rootfs",
        "files": {"usr/local/bin/python": hashlib.sha256(binary.read_bytes()).hexdigest()},
        "python_version": [3, 11, 14],
        "dependency_hash": hashlib.sha256(requirements.read_bytes()).hexdigest(),
        "aggregate_limits_enforced": False,
    }
    path = tmp_path / "bubblewrap-lock.json"
    path.write_text(json.dumps(value))
    return RuntimeLock.from_file(path)


@pytest.mark.parametrize("change", ["tamper", "extra", "symlink", "special"])
def test_rootfs_lock_rejects_mutation_and_unsealed_paths(tmp_path, change):
    lock = locked(tmp_path)
    lock.validate()
    if change == "tamper":
        (lock.rootfs / "usr/local/bin/python").write_bytes(b"changed")
    elif change == "extra":
        (lock.rootfs / "unsealed").write_bytes(b"extra")
    elif change == "symlink":
        (lock.rootfs / "outside").symlink_to(tmp_path)
    else:
        os.mkfifo(lock.rootfs / "pipe")
    with pytest.raises(ContainerUnavailable):
        lock.validate()


def test_runner_uses_only_locked_rootfs_and_episode_mounts(tmp_path):
    calls = []

    class Transport:
        def run(self, command, *, stdin, timeout, output_limit):
            calls.append(command)
            assert stdin == b'{"a": 1}' and timeout == 60 and output_limit == 65536
            return ProcessResult(0, b'{"ok":true}')

    lock = locked(tmp_path)
    runner = BubblewrapRunner(lock, transport=Transport())
    with runner.episode(SkillBundle({"SKILL.md": "s", "scripts/main.py": "bad syntax"})) as episode:
        assert episode.run_skill_script("scripts/main.py", {"a": 1}).output == {"ok": True}
        command = calls[0]
        assert "--unshare-all" in command and "--clearenv" in command
        assert "--disable-userns" in command and "--die-with-parent" in command
        assert command[command.index("--uid") + 1] == "10001"
        assert command[command.index("--gid") + 1] == "10001"
        assert "--as=1073741824" in command
        assert "resource.RLIMIT_NPROC,(64,64)" in command[-3]
        mounts = [
            command[i + 1 : i + 3]
            for i, value in enumerate(command)
            if value in {"--bind", "--ro-bind"}
        ]
        assert mounts == [
            [str(lock.rootfs), "/"],
            [str(episode.package), "/bundle"],
            [str(episode.work), "/work"],
        ]
        assert command[-2:] == ["/usr/local/bin/python", "/bundle/scripts/main.py"]
        staging = episode.package.parent
    assert not staging.exists()


def test_missing_runtime_never_executes_script_on_host(tmp_path):
    class Missing:
        def run(self, *_args, **_kwargs):
            raise FileNotFoundError("no bwrap")

    runner = BubblewrapRunner(locked(tmp_path), transport=Missing())
    with runner.episode(
        SkillBundle({"SKILL.md": "s", "scripts/main.py": "print('host')"})
    ) as episode:
        assert episode.run_skill_script("scripts/main.py", {}).failure == "container_unavailable"


@pytest.fixture
def real_runner():
    if os.environ.get("TAU_RUN_BUBBLEWRAP_INTEGRATION") != "1":
        pytest.skip("real Bubblewrap boundaries are opt-in and not attested by mocks")
    lock = RuntimeLock.from_file(EXPERIMENT_ROOT / "runtime/bubblewrap-lock.json")
    runner = BubblewrapRunner(lock)
    checks = runner.preflight()
    assert checks["ready"] and checks["demo_only"] and not checks["aggregate_limits_enforced"]
    return runner


def test_real_helpers_dependencies_reference_and_episode_lifetime(real_runner):
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
            "scripts/resource.py": "raise RuntimeError('untrusted resource shadow')",
            "references/policy.txt": "policy",
        }
    )
    with real_runner.episode(bundle) as episode:
        first = episode.run_skill_script("scripts/main.py", {"state": "one"})
        assert first.failure is None, first.to_dict()
        assert first.output == {
            "previous": None,
            "helper": 7,
            "reference": "policy",
            "versions": {"numpy": "2.2.6", "pandas": "2.2.3", "pytest": "8.4.2"},
        }
        assert (
            episode.run_skill_script("scripts/main.py", {"state": "two"}).output["previous"]
            == "one"
        )
    with real_runner.episode(bundle) as episode:
        assert (
            episode.run_skill_script("scripts/main.py", {"state": "new"}).output["previous"] is None
        )


def test_real_network_root_host_files_and_env_isolation(real_runner, tmp_path, monkeypatch):
    secret = tmp_path / "host-secret"
    secret.write_text("private fixture")
    monkeypatch.setenv("TAU_ISOLATION_SECRET", "private-environment-fixture")
    code = f"""import json,os,pathlib,socket
result={{'uid':os.getuid(),'host_visible':pathlib.Path({json.dumps(str(secret))}).exists(),
        'environment_visible':'TAU_ISOLATION_SECRET' in os.environ}}
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
    with real_runner.episode(SkillBundle({"SKILL.md": "s", "scripts/probe.py": code})) as episode:
        result = episode.run_skill_script("scripts/probe.py", {})
        assert result.failure is None, result.to_dict()
        assert result.output == {
            "uid": 10001,
            "host_visible": False,
            "environment_visible": False,
            "network": False,
            "root_writable": False,
        }


def test_real_verifier_and_explicit_program_failures(real_runner):
    result = real_runner.run_verifier(
        {},
        {},
        {"ok": True},
        {
            "tests/test_trace.py": "def test_trace(trace): assert trace['ok']\n",
        },
    )
    assert result.failure is None, result.to_dict()
    assert result.output["collected"] == 1 and result.output["results"][0]["outcome"] == "passed"
    programs = {
        "invalid": ("print('not JSON')", "invalid_json"),
        "output": ("print('x'*70000)", "output_limit"),
        "dependency": ("import missing_tau_dependency", "nonzero_exit"),
    }
    for name, (code, failure) in programs.items():
        with real_runner.episode(
            SkillBundle({"SKILL.md": "s", f"scripts/{name}.py": code})
        ) as episode:
            assert episode.run_skill_script(f"scripts/{name}.py", {}).failure == failure


def test_real_timeout_kills_forked_descendants(real_runner):
    marker = "tau-bwrap-timeout-" + uuid.uuid4().hex
    code = f"""import subprocess,sys,time
subprocess.Popen([sys.executable,'-c','import time;time.sleep(10)',{marker!r}],
                 start_new_session=True)
time.sleep(10)
"""
    runner = BubblewrapRunner(real_runner.runtime_lock, timeout=0.5)
    with runner.episode(SkillBundle({"SKILL.md": "s", "scripts/timeout.py": code})) as episode:
        result = episode.run_skill_script("scripts/timeout.py", {})
        assert result.failure == "timeout", result.to_dict()
    time.sleep(0.2)
    for process in Path("/proc").glob("[0-9]*"):
        try:
            if process.stat().st_uid == os.getuid():
                assert marker.encode() not in (process / "cmdline").read_bytes()
        except (OSError, ProcessLookupError):
            continue
