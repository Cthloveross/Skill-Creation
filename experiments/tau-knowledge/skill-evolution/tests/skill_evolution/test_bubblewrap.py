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


@pytest.mark.parametrize("runtime", ["workspace", "bubblewrap-demo"])
def test_preflight_labels_local_resource_scope_without_claiming_formal_equivalence(
    tmp_path, monkeypatch, runtime
):
    class Transport:
        def run(self, command, **kwargs):
            assert "--unshare-all" in command and "--clearenv" in command
            if "'terminal':True" in command[-1]:
                return ProcessResult(0, b'{"terminal":true,"helper":7,"reference":"public"}')
            return ProcessResult(
                0,
                json.dumps(
                    {
                        "python": [3, 11, 14],
                        "dependencies": {"numpy": "2.2.6", "pandas": "2.2.3", "pytest": "8.4.2"},
                    }
                ).encode(),
            )

    monkeypatch.setattr("tau_skill_evolution.bubblewrap.shutil.which", lambda name: name)
    checks = BubblewrapRunner(locked(tmp_path), runtime=runtime, transport=Transport()).preflight()
    assert checks["ready"]
    assert checks["backend"] == runtime
    assert checks["demo_only"] is (runtime == "bubblewrap-demo")
    assert checks["resources_scope"] == "local_process"
    assert checks["formal_environment_equivalent"] is False
    assert checks["aggregate_limits_enforced"] is False


def test_preflight_requires_actual_terminal_read_write_and_helper_import(tmp_path, monkeypatch):
    class Transport:
        def run(self, command, **kwargs):
            if "'terminal':True" in command[-1]:
                return ProcessResult(1, b"", b"/bin/sh is missing")
            return ProcessResult(
                0,
                b'{"python":[3,11,14],"dependencies":'
                b'{"numpy":"2.2.6","pandas":"2.2.3","pytest":"8.4.2"}}',
            )

    monkeypatch.setattr("tau_skill_evolution.bubblewrap.shutil.which", lambda name: name)
    checks = BubblewrapRunner(
        locked(tmp_path), runtime="workspace", transport=Transport()
    ).preflight()
    assert checks["runtime_lock"] and checks["commands"] and checks["dependencies"]
    assert checks["terminal"] is False and checks["ready"] is False
    assert checks["terminal_error"]["failure"] == "nonzero_exit"


def test_unknown_runtime_is_rejected_before_execution(tmp_path):
    with pytest.raises(ValueError, match="unknown Bubblewrap runtime"):
        BubblewrapRunner(locked(tmp_path), runtime="host")


def test_authoring_terminal_uses_locked_rootfs_and_only_writable_subtrees(tmp_path):
    calls = []

    class Transport:
        def run(self, command, **kwargs):
            calls.append(command)
            return ProcessResult(3, b"ordinary stdout", b"ordinary stderr")

    runner = BubblewrapRunner(locked(tmp_path), transport=Transport())
    with runner.authoring_session(
        SkillBundle({"SKILL.md": "parent"}), {"request": "public"}, {}
    ) as session:
        result = session.terminal("cat /work/candidate/SKILL.md")
        assert result.exit_code == 3 and result.failure is None
        assert result.output == {"stdout": "ordinary stdout", "stderr": "ordinary stderr"}
        command = calls[0]
        mounts = [
            (part, command[i + 1], command[i + 2])
            for i, part in enumerate(command)
            if part in {"--bind", "--ro-bind"}
        ]
        assert mounts == [
            ("--ro-bind", str(runner.runtime_lock.rootfs), "/"),
            ("--ro-bind", str(session.package), "/bundle"),
            ("--ro-bind", str(session.work), "/work"),
            ("--bind", str(session.work / "candidate"), "/work/candidate"),
            ("--bind", str(session.work / "scratch"), "/work/scratch"),
        ]
        assert command[-3:] == ["/bin/sh", "-c", "cat /work/candidate/SKILL.md"]
        assert "--unshare-all" in command and "--clearenv" in command


@pytest.fixture(params=["bubblewrap-demo", "workspace"])
def real_runner(request):
    if os.environ.get("TAU_RUN_BUBBLEWRAP_INTEGRATION") != "1":
        pytest.skip("real Bubblewrap boundaries are opt-in and not attested by mocks")
    lock = RuntimeLock.from_file(EXPERIMENT_ROOT / "runtime/bubblewrap-lock.json")
    runner = BubblewrapRunner(lock, runtime=request.param)
    checks = runner.preflight()
    assert checks["ready"] and not checks["aggregate_limits_enforced"], checks
    assert checks["backend"] == request.param
    assert checks["demo_only"] is (request.param == "bubblewrap-demo")
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


def test_real_public_workspaces_copy_parent_and_keep_diagnosis_tests_readonly(real_runner):
    parent = SkillBundle({"SKILL.md": "parent", "references/policy.txt": "public policy"})
    with real_runner.authoring_session(
        parent, {"request": "public"}, {"policy": "fixed"}
    ) as session:
        result = session.terminal(
            "cat /work/candidate/references/policy.txt; "
            "printf revised > /work/candidate/SKILL.md; "
            "printf saved > /work/scratch/marker"
        )
        assert result.failure is None and result.exit_code == 0, result.to_dict()
        assert result.output["stdout"] == "public policy"
        assert session.files()["SKILL.md"] == "revised"
        assert session.snapshot()["manifest"]["work"]["scratch/marker"]
        assert parent.files["SKILL.md"] == "parent"
        assert session.terminal("printf changed > /bundle/base.json").exit_code != 0
    tests = {
        "tests/test_public.py": (
            "from pathlib import Path\n"
            "def test_public(public_inputs, frozen_base, trace):\n"
            "    assert public_inputs['request'] == 'public'\n"
            "    assert frozen_base['policy'] == 'fixed' and trace['ok']\n"
            "    assert not Path('/work/candidate').exists()\n"
            "    assert not Path('/bundle/SKILL.md').exists()\n"
            "    assert not Path('/work/scratch/marker').exists()\n"
        )
    }
    for readonly in (False, True):
        with real_runner.public_verifier_session(
            {"request": "public"}, {"policy": "fixed"}, {"ok": True}, tests, readonly_tests=readonly
        ) as session:
            result = session.run_tests()
            assert result.failure is None, result.to_dict()
            assert result.output["collected"] == 1
            assert result.output["results"][0]["outcome"] == "passed"
            if readonly:
                assert (
                    session.terminal("printf changed > /bundle/tests/test_public.py").exit_code != 0
                )
                assert session.files() == tests


def test_real_timeout_kills_forked_descendants(real_runner):
    marker = "tau-bwrap-timeout-" + uuid.uuid4().hex
    code = f"""import subprocess,sys,time
subprocess.Popen([sys.executable,'-c','import time;time.sleep(10)',{marker!r}],
                 start_new_session=True)
time.sleep(10)
"""
    runner = BubblewrapRunner(real_runner.runtime_lock, runtime=real_runner.runtime, timeout=0.5)
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


def test_real_py_compile_caches_survive_snapshot_and_trusted_test_execution(real_runner):
    parent = SkillBundle({"SKILL.md": "parent", "scripts/helper.py": "VALUE = 7\n"})
    with real_runner.authoring_session(parent, {}, {}) as session:
        result = session.terminal("python -m py_compile /work/candidate/scripts/helper.py")
        assert result.failure is None and result.exit_code == 0, result.to_dict()
        snapshot = session.snapshot()
        assert snapshot["files"] == dict(parent.files)
        assert any(path.endswith(".pyc") for path in snapshot["manifest"]["work"])
    tests = {"tests/test_public.py": "def test_trace(trace): assert trace['ok']\n"}
    with real_runner.public_verifier_session({}, {}, {"ok": True}, tests) as session:
        result = session.terminal("python -m py_compile /work/tests/test_public.py")
        assert result.failure is None and result.exit_code == 0, result.to_dict()
        snapshot = session.snapshot()
        assert snapshot["files"] == tests
        assert any(path.endswith(".pyc") for path in snapshot["manifest"]["work"])
        result = session.run_tests()
        assert result.failure is None, result.to_dict()
        assert result.output["collected"] == 1
        assert result.output["results"][0]["outcome"] == "passed"
