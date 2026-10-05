import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from tau_skill_evolution.artifacts import SkillBundle
from tau_skill_evolution.constants import EXPERIMENT_ROOT
from tau_skill_evolution.container import ProcessResult
from tau_skill_evolution.skillsbench import (
    SkillsBenchAdapter,
    SkillsBenchSource,
    _environment_inputs,
    _json_hash,
    _public_path,
    validate_pool,
)
from tau_skill_evolution.skillsbench_runtime import SkillsBenchRunner


@pytest.fixture
def prepared_source():
    if os.environ.get("TAU_RUN_SKILLSBENCH_SOURCE_INTEGRATION") != "1":
        pytest.skip("Pinned SkillsBench source and pool checks require prepared data and opt-in.")
    source = SkillsBenchSource(EXPERIMENT_ROOT)
    source.validate()
    return source


@pytest.fixture
def public_source(tmp_path, monkeypatch):
    """Small public task trees for mocked Docker, grading and adapter checks."""
    from tau_skill_evolution import skillsbench, skillsbench_runtime

    source = SkillsBenchSource.__new__(SkillsBenchSource)
    source.root = tmp_path / "public-source"
    source.checkout = source.root / "data/upstream/coevo-skills"
    inputs = {
        "3d-scan-calc": (
            "/root",
            {"scan_data.stl": "input", "material_density_table.md": "density"},
        ),
        "travel-planning": ("/app", {"data.csv": "public data"}),
        "fix-visual-stability": (
            "/app",
            {"src/components/ProductCard.tsx": "component", "src/app/globals.css": "style"},
        ),
        "glm-lake-mendota": ("/root", {"glm": "executable"}),
        "xlsx-recover-data": ("/root", {"nasa_budget_incomplete.xlsx": "public input"}),
        "trend-anomaly-causal-inference": ("/root", {"data.csv": "public data"}),
    }
    files, tree, environments = [], [], {}
    for task_id, (workdir, contents) in inputs.items():
        directory = source.checkout / "tasks" / task_id
        environment = directory / "environment"
        environment.mkdir(parents=True)
        recipe = f"FROM base\nWORKDIR {workdir}\n" + "".join(
            f"COPY {relative} {workdir}/{relative}\n" for relative in contents
        )
        if task_id == "trend-anomaly-causal-inference":
            recipe += "COPY skills /root/skills\n"
            (environment / "skills").mkdir()
            (environment / "skills/SKILL.md").write_text("Excluded author skill")
        if task_id == "xlsx-recover-data":
            (environment / "groundtruth").mkdir()
            (environment / "groundtruth/answers.txt").write_text("Excluded answer")
        for relative, content in {**contents, "Dockerfile": recipe}.items():
            path = environment / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
            original = path.relative_to(source.checkout).as_posix()
            files.append(
                {
                    "task_id": task_id,
                    "relative_path": "environment/" + relative,
                    "path": original,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "bytes": path.stat().st_size,
                }
            )
            tree.append(
                {
                    "type": "blob",
                    "path": original,
                    "mode": "100755" if relative == "glm" else "100644",
                }
            )
        (directory / "instruction.md").write_text("Write `/root/mass_report.json`.")
        (directory / "task.toml").write_text(
            "[environment]\ncpus=1\nmemory_mb=4096\nstorage_mb=10240\n"
            "[agent]\ntimeout_sec=900\n[verifier]\ntimeout_sec=900\n"
        )
        (directory / "tests").mkdir()
        (directory / "tests/test.sh").write_text("exit 0\n")
        environments[task_id] = _environment_inputs(directory)
    source.manifest = {
        "tasks": list(inputs),
        "files": files,
        "environments": environments,
        "manifest_hash": "mock-public-inputs",
    }
    source.validate = lambda: None
    data = source.root / "data/skillsbench"
    data.mkdir()
    (data / "source-tree.json").write_text(json.dumps({"sha": skillsbench.COMMIT, "tree": tree}))
    monkeypatch.setattr(skillsbench, "SkillsBenchSource", lambda _root: source)
    monkeypatch.setattr(skillsbench_runtime, "SkillsBenchSource", lambda _root: source)
    return source


def test_copy_allowlist_excludes_unseen_groundtruth_and_preserves_destinations(tmp_path):
    task = tmp_path / "task"
    environment = task / "environment"
    (environment / "groundtruth").mkdir(parents=True)
    (environment / "groundtruth/answers.txt").write_text("private")
    (environment / "input.xlsx").write_text("input")
    (environment / "reference").mkdir()
    (environment / "reference/data.csv").write_text("public reference")
    (environment / "Dockerfile").write_text(
        "FROM ubuntu\nWORKDIR /app\nCOPY input.xlsx /app/renamed.xlsx\n"
        "COPY reference /data/reference\n"
    )
    (task / "instruction.md").write_text("Write /output/report.json")
    mapping = _environment_inputs(task)
    assert mapping["workdir"] == "/app"
    assert mapping["copies"] == [
        {"source": "input.xlsx", "destination": "/app/renamed.xlsx"},
        {"source": "reference/data.csv", "destination": "/data/reference/data.csv"},
    ]
    assert mapping["workspace_roots"] == ["/app", "/data", "/output", "/root"]
    env = {"task": mapping}
    assert _public_path("tasks/task/environment/groundtruth/answers.txt", env) is None
    assert _public_path("tasks/task/environment/input.xlsx", env) == (
        "task",
        "environment/input.xlsx",
    )
    assert _public_path("tasks/task/tests/test_outputs.py", env) is None
    assert _public_path("tasks/task/solution/solve.sh", env) is None


def test_copy_globs_dockerignore_and_public_project_templates(tmp_path):
    task = tmp_path / "task"
    environment = task / "environment"
    (environment / "workspace/src/test").mkdir(parents=True)
    for relative in [
        "workspace/solution.lean",
        "workspace/baseline_solution.json",
        "workspace/src/test/public.java",
        "workspace/groundtruth/answers.txt",
    ]:
        path = environment / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("public or excluded")
    (environment / "Dockerfile").write_text(
        "FROM base\nENV WORKSPACE=/root\nWORKDIR ${WORKSPACE}\nCOPY workspace/ /workspace/\n"
    )
    (task / "instruction.md").write_text("Complete the public source template.")
    mapping = _environment_inputs(task)
    assert mapping["workdir"] == "/root"
    sources = {e["source"] for e in mapping["copies"]}
    assert "workspace/solution.lean" in sources
    assert "workspace/baseline_solution.json" in sources
    assert "workspace/src/test/public.java" in sources
    assert "workspace/groundtruth/answers.txt" not in sources
    assert mapping["private_copied"] == ["workspace/groundtruth/answers.txt"]
    (environment / ".dockerignore").write_text("workspace/src/test/\n")
    assert "workspace/src/test/public.java" not in {
        e["source"] for e in _environment_inputs(task)["copies"]
    }


def test_pinned_public_population_and_xlsx_answer_regression(prepared_source):
    source = prepared_source
    assert len(source.manifest["tasks"]) == 85
    files = [
        e["relative_path"] for e in source.manifest["files"] if e["task_id"] == "xlsx-recover-data"
    ]
    assert "environment/nasa_budget_incomplete.xlsx" in files
    assert not any("groundtruth" in path for path in files)
    task = source.task("xlsx-recover-data")
    assert task["public_input_manifest"][0]["sandbox_paths"] == [
        "/root/nasa_budget_incomplete.xlsx"
    ]
    assert not any(
        "/tests/" in e["path"] or "/solution/" in e["path"] for e in source.manifest["files"]
    )


def test_pinned_pool_contains_all_backgrounds_and_no_task_files(prepared_source):
    source = prepared_source
    manifest = validate_pool(EXPERIMENT_ROOT, source)
    assert manifest["schema"] == "skillsbench.pool.v2"
    assert manifest["scope"] == "background_docs_only"
    directory = EXPERIMENT_ROOT / "data/skillsbench/corpus"
    indexed = {
        json.loads((directory / record["file"]).read_text())["source_document_id"]
        for record in manifest["pages"]
    }
    backgrounds = {
        e["document_id"]
        for e in source.manifest["files"]
        if e["relative_path"].startswith("background/")
    }
    assert indexed == backgrounds
    assert all("::background/" in document_id for document_id in indexed)


@pytest.fixture
def background_pool(tmp_path, monkeypatch):
    from tau_skill_evolution import skillsbench

    checkout = tmp_path / "upstream"
    files = []
    for task_id in ("alpha", "beta"):
        for relative, original, content in (
            (
                "background/guide.md",
                f"artifacts/background_docs/{task_id}/guide.md",
                f"Public {task_id} prerequisites.\n" * 100,
            ),
            ("instruction.md", f"tasks/{task_id}/instruction.md", "Current task instructions"),
            (
                "environment/data.csv",
                f"tasks/{task_id}/environment/data.csv",
                "label,value\nprovided,42\n",
            ),
            (
                "environment/Dockerfile",
                f"tasks/{task_id}/environment/Dockerfile",
                "FROM base\nCOPY data.csv /app/data.csv\n",
            ),
        ):
            path = checkout / original
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
            files.append(
                {
                    "path": original,
                    "task_id": task_id,
                    "relative_path": relative,
                    "document_id": f"{task_id}::{relative}",
                    "sha256": hashlib.sha256(content.encode()).hexdigest(),
                    "bytes": len(content.encode()),
                    "kind": "text",
                    "summary": None,
                }
            )
        private = checkout / f"tasks/{task_id}/tests/test_outputs.py"
        private.parent.mkdir(parents=True)
        private.write_text("Hidden checks never enter the public manifest.")
    source = SimpleNamespace(
        root=tmp_path,
        checkout=checkout,
        manifest={"manifest_hash": "sealed-public-inputs", "files": files},
        validate=lambda: None,
    )
    monkeypatch.setattr(skillsbench, "SkillsBenchSource", lambda _root: source)

    class Tokenizer:
        def encode(self, text, **_kwargs):
            return list(text.encode())

        def decode(self, tokens, **_kwargs):
            return bytes(tokens).decode()

    skillsbench.prepare_pool(tmp_path, Tokenizer())
    directory = tmp_path / "data/skillsbench/corpus"
    return source, directory, json.loads((directory / "manifest.json").read_text())


def test_prepare_pool_excludes_task_inputs_without_removing_public_inputs(background_pool):
    source, directory, manifest = background_pool
    validate_pool(source.root, source)
    pages = [json.loads((directory / record["file"]).read_text()) for record in manifest["pages"]]
    assert {page["source_document_id"] for page in pages} == {
        "alpha::background/guide.md",
        "beta::background/guide.md",
    }
    assert all("prerequisites" in page["body"] for page in pages)
    assert len(source.manifest["files"]) == 8
    assert (
        (source.checkout / "tasks/alpha/environment/data.csv").read_text().endswith("provided,42\n")
    )


def test_pool_rejects_tampered_body(background_pool):
    source, directory, manifest = background_pool
    record = manifest["pages"][0]
    page = json.loads((directory / record["file"]).read_text())
    page["body"] += "tampered"
    (directory / record["file"]).write_text(json.dumps(page))
    with pytest.raises(ValueError, match="corpus_hash_mismatch"):
        validate_pool(source.root, source)


@pytest.mark.parametrize("field", ["schema", "scope"])
def test_pool_rejects_legacy_scope_even_when_resealed(background_pool, field):
    source, directory, manifest = background_pool
    manifest.pop(field)
    manifest["corpus_hash"] = _json_hash({k: v for k, v in manifest.items() if k != "corpus_hash"})
    (directory / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="pool_manifest_invalid"):
        validate_pool(source.root, source)


@pytest.mark.parametrize(
    "relative",
    ["instruction.md", "environment/data.csv", "environment/Dockerfile", "tests/test_outputs.py"],
)
def test_pool_rejects_task_or_private_pages_even_when_resealed(background_pool, relative):
    source, directory, manifest = background_pool
    record = manifest["pages"][0]
    page = json.loads((directory / record["file"]).read_text())
    document_id = f"alpha::{relative}"
    entry = next((e for e in source.manifest["files"] if e["document_id"] == document_id), None)
    page["source_document_id"] = document_id
    page["source_sha256"] = entry["sha256"] if entry else "0" * 64
    page["page_id"] = f"{document_id}::tokens-{page['token_start']}-{page['token_end']}"
    page["title"] = document_id
    record.update(source_sha256=page["source_sha256"], page_id=page["page_id"])
    (directory / record["file"]).write_text(json.dumps(page))
    manifest["corpus_hash"] = _json_hash({k: v for k, v in manifest.items() if k != "corpus_hash"})
    (directory / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="corpus_hash_mismatch"):
        validate_pool(source.root, source)


def test_pool_rejects_missing_background_source_even_when_resealed(background_pool):
    source, directory, manifest = background_pool
    manifest["pages"] = [
        record for record in manifest["pages"] if record["page_id"].startswith("alpha::")
    ]
    manifest["corpus_hash"] = _json_hash({k: v for k, v in manifest.items() if k != "corpus_hash"})
    (directory / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        validate_pool(source.root, source)


@pytest.mark.parametrize("reward,utility", [("0", False), ("0.5", False), ("1", True)])
def test_reward_file_is_authoritative_not_zero_exit_code(public_source, tmp_path, reward, utility):
    runner = SkillsBenchRunner(EXPERIMENT_ROOT, "3d-scan-calc", demo=True)
    work = tmp_path / "work"
    work.mkdir()
    episode = SimpleNamespace(work=work)

    def grade(_package, _work, _args, **_kwargs):
        logs = tmp_path / "grader-logs"
        (logs / "reward.txt").write_text(reward)
        (logs / "ctrf.json").write_text(
            json.dumps({"results": {"summary": {"tests": 2, "passed": 1}}})
        )
        return ProcessResult(0)

    runner._raw = grade
    result = runner.grade(episode)
    assert result["status"] == "MEASURED"
    assert result["utility"] is utility
    assert result["reward"] == float(reward)
    assert result["official_checks"]["rate"] == 0.5


@pytest.mark.parametrize("reward", ["NaN", "-1", "2", "not-json"])
def test_invalid_canonical_reward_is_not_measured(public_source, tmp_path, reward):
    runner = SkillsBenchRunner(EXPERIMENT_ROOT, "3d-scan-calc", demo=True)
    work = tmp_path / "work"
    work.mkdir()

    def grade(*_args, **_kwargs):
        (tmp_path / "grader-logs/reward.txt").write_text(reward)
        return ProcessResult(0)

    runner._raw = grade
    assert runner.grade(SimpleNamespace(work=work))["status"] == "NOT_MEASURED"


@pytest.mark.parametrize(
    "exit_code,diagnostics,report,measured",
    [
        (0, b"ModuleNotFoundError: required grader dependency", None, False),
        (0, b"ERROR collecting /tests/test_outputs.py", None, False),
        (2, b"", None, False),
        (0, b"", {"results": {"summary": {"tests": 0, "passed": 0}}}, False),
        (0, b"", {"results": {"summary": {"tests": 2, "errors": 1}}}, False),
        (
            0,
            b"",
            {"results": {"summary": {"tests": 2}, "tests": [{"status": "broken"}]}},
            False,
        ),
        (0, b"", "invalid-json", False),
        (1, b"AssertionError: candidate output is wrong", None, True),
        (0, b"", None, True),
    ],
)
def test_grader_program_errors_are_unmeasured_even_when_reward_file_exists(
    public_source, tmp_path, exit_code, diagnostics, report, measured
):
    runner = SkillsBenchRunner(EXPERIMENT_ROOT, "3d-scan-calc", demo=True)
    work = tmp_path / "work"
    work.mkdir()

    def grade(*_args, **_kwargs):
        logs = tmp_path / "grader-logs"
        (logs / "reward.txt").write_text("0")
        if report is not None:
            (logs / "ctrf.json").write_text(
                report if isinstance(report, str) else json.dumps(report)
            )
        return ProcessResult(exit_code, stderr=diagnostics)

    runner._raw = grade
    result = runner.grade(SimpleNamespace(work=work))
    if measured:
        assert result["status"] == "MEASURED" and result["reward"] == 0
        assert result["utility"] is False
    else:
        assert result["status"] == "NOT_MEASURED"
        assert result["failure"] == "official_grader_program_error"
        assert result["reward"] is result["utility"] is None


@pytest.mark.parametrize("allow_internet", [True, False, None])
def test_docker_restores_declared_layout_and_cleans_named_container(
    public_source, tmp_path, monkeypatch, allow_internet
):
    runner = SkillsBenchRunner(EXPERIMENT_ROOT, "travel-planning", demo=False)
    runner.config["environment"]["allow_internet"] = allow_internet
    images = {
        name: {"digest": "sha256:" + "a" * 64, "environment": ["PATH=/usr/bin:/bin"]}
        for name in ("environment", "runtime", "grader")
    }
    value = {
        "images": images,
        "layout": {
            "workdir": "/app",
            "copies": [
                {"source": "helper", "destination": "/usr/local/bin/helper"},
                {"source": "data.csv", "destination": "/app/data.csv"},
            ],
        },
    }
    monkeypatch.setattr(Path, "read_text", lambda *args, **kwargs: json.dumps(value))
    runner.workspace_mounts = {"/app": tmp_path / "app", "/output": tmp_path / "output"}
    calls = []

    class Transport:
        def run(self, command, **_kwargs):
            calls.append(command)
            if command[:3] == ["docker", "rm", "--force"]:
                return ProcessResult(0)
            return ProcessResult(-9, failure="timeout")

    runner.transport = Transport()
    result = runner._raw(tmp_path, tmp_path, ["python", "-c", "pass"])
    command = calls[0]
    assert command[command.index("--workdir") + 1] == "/app"
    assert "--network" in command and "--read-only" in command and "--memory-swap" in command
    assert command[command.index("--network") + 1] == (
        "bridge" if allow_internet is True else "none"
    )
    assert f"type=bind,src={tmp_path / 'app'},dst=/app" in command
    assert f"type=bind,src={tmp_path / 'output'},dst=/output" in command
    assert "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1" in command
    assert not any("dst=/usr/local/bin/helper" in word for word in command)
    assert not any("dst=/app/data.csv" in word for word in command)
    assert "-i" in command and "--entrypoint" in command
    name = command[command.index("--name") + 1]
    assert calls[-1] == ["docker", "rm", "--force", "--volumes", name]
    assert result.failure == "timeout"


def test_task_workspace_edits_are_not_restricted_by_file_extension(
    public_source, tmp_path, monkeypatch
):
    runner = SkillsBenchRunner(EXPERIMENT_ROOT, "fix-visual-stability", demo=False)
    sources = {
        entry["source"]: entry["destination"]
        for entry in runner.source.manifest["environments"][runner.task_id]["copies"]
    }
    assert "/app/src/components/ProductCard.tsx" in sources.values()
    assert "/app/src/app/globals.css" in sources.values()
    lock = {
        "images": {
            "environment": {"digest": "sha256:" + "a" * 64, "environment": []},
        },
        "layout": {
            "workdir": "/app",
            "copies": [
                {"source": source, "destination": target} for source, target in sources.items()
            ],
        },
    }
    monkeypatch.setattr(Path, "read_text", lambda *args, **kwargs: json.dumps(lock))
    runner.workspace_mounts = {"/app": tmp_path / "app", "/api": tmp_path / "api"}
    command = runner._docker_command(
        tmp_path / "bundle", tmp_path / "episode", ["/bin/bash"], grader=False
    )
    mounts = [value for value in command if value.startswith("type=bind,")]
    assert mounts == [
        f"type=bind,src={tmp_path / 'bundle'},dst=/bundle,readonly",
        f"type=bind,src={tmp_path / 'app'},dst=/app",
        f"type=bind,src={tmp_path / 'api'},dst=/api",
    ]
    assert "--read-only" in command
    assert not any(str(runner.task_directory) in argument for argument in command)


@pytest.mark.parametrize(
    "reward,exit_code,failure,report,ready",
    [
        ("0", 0, None, None, True),
        ("0", 1, None, None, True),
        (None, 0, None, None, False),
        ("NaN", 0, None, None, False),
        ("1", -9, "timeout", None, False),
        ("0", 127, None, None, False),
        ("0", 0, None, {"results": {"summary": {"tests": 0, "passed": 0}}}, False),
        ("0", 1, None, {"results": {"summary": {"tests": 1, "errors": 1}}}, False),
        (
            "0",
            0,
            None,
            {"results": {"summary": {"tests": 1}, "tests": [{"status": "broken"}]}},
            False,
        ),
    ],
)
def test_docker_preflight_executes_private_grader_and_requires_a_valid_result(
    public_source, tmp_path, monkeypatch, reward, exit_code, failure, report, ready
):
    runner = SkillsBenchRunner(EXPERIMENT_ROOT, "3d-scan-calc", demo=False)
    runner.root = tmp_path
    images = {
        role: {
            "digest": "sha256:" + str(index) * 64,
            "environment": [
                "PATH=/usr/bin:/bin",
                "HOME=/opt/tau-grader/home" if role == "grader" else "HOME=/root",
                "UV_CACHE_DIR=/opt/tau-grader/cache",
            ],
        }
        for index, role in enumerate(("environment", "runtime", "grader"), 1)
    }
    lock = {
        "images": images,
        "layout": runner.source.manifest["environments"][runner.task_id],
    }
    lock_path = tmp_path / f"runtime/skillsbench-docker-{runner.task_id}-lock.json"
    lock_path.parent.mkdir()
    lock_path.write_text(json.dumps(lock))
    monkeypatch.setattr(runner, "_docker_lock", lambda: lock)
    monkeypatch.setattr("tau_skill_evolution.skillsbench_runtime.shutil.which", lambda _: "docker")
    calls = []

    class Transport:
        def run(self, command, **_kwargs):
            calls.append(command)
            if command[:2] == ["docker", "cp"]:
                if command[2].endswith(":/opt/tau-grader/."):
                    (Path(command[3]) / "bootstrap.commands").touch()
                return ProcessResult(0)
            if command[:2] != ["docker", "run"]:
                return ProcessResult(0)
            if images["environment"]["digest"] in command:
                return ProcessResult(0, stdout=b"[3,11,14]")
            if images["runtime"]["digest"] in command:
                return ProcessResult(0, stdout=b'{"pytest":"8.4.1","pytest-json-ctrf":"0.3.5"}')
            assert images["grader"]["digest"] in command
            assert command[command.index("--network") + 1] == "none"
            assert command[command.index("--user") + 1] == "10001:10001"
            assert "--read-only" in command and "no-new-privileges" in command
            mounts = {}
            for argument in command:
                if argument.startswith("type=bind,"):
                    value = dict(part.split("=", 1) for part in argument.split(",") if "=" in part)
                    mounts[value["dst"]] = Path(value["src"])
            assert not list(mounts["/bundle"].iterdir())
            assert not list(mounts["/logs/verifier"].iterdir())
            assert mounts["/opt/tau-grader"].joinpath("bootstrap.commands").is_file()
            assert not any(str(runner.source.checkout) in argument for argument in command)
            assert "source /tests/test.sh" in command[-1]
            if reward is not None:
                mounts["/logs/verifier"].joinpath("reward.txt").write_text(reward)
            if report is not None:
                mounts["/logs/verifier"].joinpath("ctrf.json").write_text(json.dumps(report))
            return ProcessResult(exit_code, failure=failure)

    runner.transport = Transport()
    result = runner.preflight(validate_source=False)
    runs = [command for command in calls if command[:2] == ["docker", "run"]]
    assert len(runs) == 3
    assert result["ready"] is ready and result["official_grader"] is ready
    assert result["official_grader_probe"] == {
        "purpose": "runtime_admission",
        "experiment_measurement": False,
        "status": "PASSED" if ready else "FAILED",
    }
    assert not {"utility", "reward", "official_checks"} & result.keys()
    assert runner.grader_cache is None and runner.verifier_artifacts is None


def test_artifact_snapshot_rejects_host_escape_symlink(public_source, tmp_path):
    adapter = SkillsBenchAdapter(
        SimpleNamespace(root=EXPERIMENT_ROOT),
        "3d-scan-calc",
        demo=True,
        artifact_root=tmp_path / "artifacts",
    )
    work = tmp_path / "work"
    work.mkdir()
    (work / "mass_report.json").symlink_to(tmp_path / "host-data")
    (tmp_path / "host-data").write_text("host private")
    with pytest.raises(ValueError, match="not_regular"):
        adapter._snapshot(SimpleNamespace(work=work))


@pytest.fixture
def real_runner():
    if os.environ.get("TAU_RUN_SKILLSBENCH_INTEGRATION") != "1":
        pytest.skip("Real SkillsBench Bubblewrap boundaries require explicit opt-in.")
    runner = SkillsBenchRunner(EXPERIMENT_ROOT, "3d-scan-calc", demo=True)
    assert runner.preflight()["ready"]
    return runner


def test_real_isolation_lifetime_and_verifier_source_blindness(real_runner, tmp_path):
    code = """import json,os,pathlib,socket,resource
state=pathlib.Path('/root/state.json'); old=state.exists(); state.write_text('{}')
try: socket.create_connection(('1.1.1.1',443),timeout=.5); network=True
except OSError: network=False
try: pathlib.Path('/root/material_density_table.md').write_text('changed'); inputs_ro=False
except OSError: inputs_ro=True
print(json.dumps({'uid':os.getuid(),'network':network,'inputs_ro':inputs_ro,'old':old,
'host':pathlib.Path('/home/tc442/projects/Skill-Creation').exists(),
'key':bool(os.environ.get('AWS_BEARER_TOKEN_BEDROCK')),
'as':resource.getrlimit(resource.RLIMIT_AS)[0],'pids':resource.getrlimit(resource.RLIMIT_NPROC)[0]}))
"""
    bundle = SkillBundle({"SKILL.md": "No API test.", "scripts/main.py": code})
    adapter = SkillsBenchAdapter(
        SimpleNamespace(root=EXPERIMENT_ROOT),
        "3d-scan-calc",
        demo=True,
        artifact_root=tmp_path / "artifacts",
    )
    with real_runner.episode(bundle) as episode:
        result = episode.run_skill_script("scripts/main.py", {})
        assert result.output == {
            "uid": 10001,
            "network": False,
            "inputs_ro": True,
            "old": False,
            "host": False,
            "key": False,
            "as": 4096 * 1024 * 1024,
            "pids": 64,
        }
        assert episode.run_skill_script("scripts/main.py", {}).output["old"]
        (episode.work / "mass_report.json").write_text("{}")
        snapshot = adapter._snapshot(episode)
    with real_runner.episode(bundle) as episode:
        assert not episode.run_skill_script("scripts/main.py", {}).output["old"]
    tests = {
        "tests/test_public.py": """from pathlib import Path
def test_boundaries():
 assert Path('/root/mass_report.json').is_file()
 assert not Path('/bundle/SKILL.md').exists()
 assert not Path('/tests/test_outputs.py').exists()
"""
    }
    result = real_runner.run_verifier(adapter.public_inputs, {}, snapshot, tests)
    assert result.failure is None and result.output["collected"] == 1
    assert result.output["exit_code"] == 0


def test_real_invalid_json_output_cap_and_timeout_cleanup(real_runner):
    real_runner.timeout = 0.6
    for code, failure in [
        ('print("invalid")', "invalid_json"),
        ('print("x"*70000)', "output_limit"),
        (
            'import subprocess,time; subprocess.Popen(["python","-c",'
            '"import time; time.sleep(10)"]); time.sleep(10)',
            "timeout",
        ),
    ]:
        with real_runner.episode(
            SkillBundle({"SKILL.md": "probe", "scripts/main.py": code})
        ) as episode:
            staging = episode.package.parent
            result = episode.run_skill_script("scripts/main.py", {})
            assert result.failure == failure
        assert not staging.exists()


def test_dense_build_checkpoints_resume_and_matches_shared_cache(tmp_path, monkeypatch):
    from tau_skill_evolution import dense, skillsbench
    from tau_skill_evolution.core import Page
    from tests.test_tau_dense import _Client, _Tokenizer

    directory = tmp_path / "data/skillsbench/corpus"
    directory.mkdir(parents=True)
    pages, records = [], []
    for index in range(259):
        page = Page(f"doc-{index:04d}", "Title", "Public content")
        pages.append(page)
        filename = f"{index}.json"
        (directory / filename).write_text(
            json.dumps(
                {
                    "page_id": page.page_id,
                    "title": page.title,
                    "body": page.body,
                    "content_sha256": page.content_sha256,
                }
            )
        )
        records.append({"file": filename})
    manifest = {"pages": records, "corpus_hash": hashlib.sha256(b"fixture").hexdigest()}
    monkeypatch.setattr(skillsbench, "validate_pool", lambda _root: manifest)
    monkeypatch.setattr(
        dense.HuggingFaceQwenTokenizer, "from_pretrained", lambda **_kw: _Tokenizer()
    )
    client = _Client()
    monkeypatch.setattr(dense, "OpenAICompatibleEmbeddingClient", lambda *a, **kw: client)
    result = skillsbench.prepare_dense(
        tmp_path,
        {
            "model": client.model_id,
            "revision": client.revision,
            "dimension": client.dimensions,
            "endpoint": "offline",
        },
    )
    assert result["ready"] and result["pages"] == 259
    assert len(client.document_calls) == 2
    output = tmp_path / "data/skillsbench/dense" / manifest["corpus_hash"]
    loaded = dense.DenseIndex.load_cache(output, pages, client=client, tokenizer=_Tokenizer())
    assert loaded.page_count == 259
    (output / "manifest.json").unlink()
    skillsbench.prepare_dense(
        tmp_path,
        {
            "model": client.model_id,
            "revision": client.revision,
            "dimension": client.dimensions,
            "endpoint": "offline",
        },
    )
    assert len(client.document_calls) == 2  # Both completed part caches reused.


def test_acquisition_has_no_simulator_or_bank_tools(public_source):
    adapter = SkillsBenchAdapter(SimpleNamespace(root=EXPERIMENT_ROOT), "3d-scan-calc", demo=True)
    assert adapter.allowed_read_only_tool_names == ()
    with adapter.acquisition() as context:
        assert context.tool_schemas == []
        with pytest.raises(PermissionError):
            context.read("get_current_time", {})
        with pytest.raises(PermissionError):
            context.clarify("Question")
    assert "private" not in adapter.public_inputs


def test_execution_receives_package_but_public_trace_excludes_tool_io(public_source, tmp_path):
    from tau_skill_evolution.container import ProgramResult
    from tau_skill_evolution.skillsbench import SkillsBenchAdapter

    roles, histories = [], []
    responses = [
        {
            "role": "assistant",
            "content": "",
            "usage": {"completion_tokens": 1},
            "finish_reason": "tool_calls",
            "tool_calls": [
                {
                    "id": "c1",
                    "type": "function",
                    "function": {
                        "name": "read_skill_file",
                        "arguments": '{"relative_path":"references/policy.md"}',
                    },
                }
            ],
        },
        {
            "role": "assistant",
            "content": "",
            "usage": {"completion_tokens": 1},
            "finish_reason": "tool_calls",
            "tool_calls": [
                {
                    "id": "c2",
                    "type": "function",
                    "function": {
                        "name": "run_terminal_command",
                        "arguments": '{"command":"private command"}',
                    },
                }
            ],
        },
        {"role": "assistant", "content": "Finished.", "usage": {"completion_tokens": 1}},
    ]

    class Model:
        def complete(self, messages, **_kwargs):
            from tau_skill_evolution.model import _assistant_response

            histories.append(json.loads(json.dumps(messages)))
            response = responses.pop(0)
            output = [
                {
                    "type": "function_call",
                    "status": "completed",
                    "call_id": c["id"],
                    "id": "fc_" + c["id"],
                    **c["function"],
                }
                for c in response.get("tool_calls", [])
            ]
            if response.get("content"):
                output.append(
                    {
                        "type": "message",
                        "role": "assistant",
                        "status": "completed",
                        "content": [{"type": "output_text", "text": response["content"]}],
                    }
                )
            return _assistant_response(
                {
                    "status": "completed",
                    "output": output,
                    "usage": {"input_tokens": 1, "output_tokens": 1},
                }
            )

    def factory(role):
        roles.append(role)
        return Model()

    spec = SimpleNamespace(
        root=EXPERIMENT_ROOT,
        values={
            "runtime": {
                "max_turns": 5,
                "controls": {"assistant_completion_budget": 30, "agent": {"max_output_tokens": 10}},
            }
        },
    )
    adapter = SkillsBenchAdapter(spec, "3d-scan-calc", demo=True, model_factory=factory)
    adapter.runner.terminal = lambda *args, **kwargs: ProgramResult(0, "RAW_TERMINAL")
    episode = SimpleNamespace(read_skill_file=lambda **kwargs: "RAW_REFERENCE")
    result = adapter._execute(SkillBundle({"SKILL.md": "CURRENT_SKILL_ONLY"}), episode)
    assert roles == ["execution"]
    assert "RAW_REFERENCE" in json.dumps(histories[-1])
    assert "RAW_TERMINAL" in json.dumps(histories[-1])
    public = json.dumps(result)
    assert "RAW_REFERENCE" not in public and "RAW_TERMINAL" not in public
    assert "CURRENT_SKILL_ONLY" not in public and "private command" not in public
    assert "Finished." not in public
    assert result["events"][-1] == {
        "type": "message_status",
        "role": "assistant",
        "status": "returned",
    }


def test_executor_source_quotes_stay_private_to_its_session(public_source):
    from tau_skill_evolution.verifier import SurrogateVerifier

    skill_source = "PRIVATE_SKILL_SOURCE: execute scripts/main.py with the task inputs."
    script_source = "def private_skill_helper():\n    return 'PRIVATE_SCRIPT_SOURCE'\n"
    quoted = f"Loaded SKILL.md:\n{skill_source}\nLoaded script:\n{script_source}"
    responses = [
        {
            "role": "assistant",
            "content": quoted,
            "reasoning": "PRIVATE_EXECUTOR_REASONING",
            "finish_reason": "tool_calls",
            "usage": {"completion_tokens": 1},
            "tool_calls": [
                {
                    "id": "read-source",
                    "function": {
                        "name": "read_skill_file",
                        "arguments": '{"relative_path":"scripts/main.py"}',
                    },
                }
            ],
        },
        {
            "role": "assistant",
            "content": quoted,
            "finish_reason": "stop",
            "usage": {"completion_tokens": 1},
        },
    ]
    histories = []

    def complete(messages, **_kwargs):
        histories.append(json.loads(json.dumps(messages)))
        return responses.pop(0)

    spec = SimpleNamespace(
        root=EXPERIMENT_ROOT,
        values={
            "runtime": {
                "max_turns": 5,
                "controls": {"assistant_completion_budget": 30, "agent": {"max_output_tokens": 10}},
            }
        },
    )
    adapter = SkillsBenchAdapter(
        spec,
        "3d-scan-calc",
        demo=True,
        model_factory=lambda _role: SimpleNamespace(complete=complete),
    )
    bundle = SkillBundle({"SKILL.md": skill_source, "scripts/main.py": script_source})
    episode = SimpleNamespace(read_skill_file=lambda relative_path: bundle.files[relative_path])
    trace = adapter._execute(bundle, episode)
    payload = SurrogateVerifier._payload(adapter.public_inputs, {}, trace, None, "initial")
    executor_history = json.dumps(histories[-1])
    verifier_input = json.dumps(payload)
    for private in ("PRIVATE_SKILL_SOURCE", "PRIVATE_SCRIPT_SOURCE", "PRIVATE_EXECUTOR_REASONING"):
        assert private in executor_history
        assert private not in verifier_input
    assert trace["termination_reason"] == "agent_finished" and trace["tool_calls"] == 1
    assert trace["events"] == [
        {"type": "message_status", "role": "assistant", "status": "returned"},
        {
            "type": "tool_status",
            "name": "read_skill_file",
            "exit_code": None,
            "failure": None,
            "status": "returned",
        },
        {"type": "message_status", "role": "assistant", "status": "returned"},
    ]


def test_relative_declared_output_is_snapshotted(public_source, tmp_path):
    adapter = SkillsBenchAdapter(
        SimpleNamespace(root=EXPERIMENT_ROOT),
        "3d-scan-calc",
        demo=True,
        artifact_root=tmp_path / "artifacts",
    )
    adapter.public_inputs["opening"] = "Write `report.csv` in the working directory."
    work = tmp_path / "work"
    work.mkdir()
    (work / "report.csv").write_text("public output")
    snapshot = adapter._snapshot(SimpleNamespace(work=work))
    assert snapshot["public_artifacts"][0]["path"] == "root/report.csv"
    files = Path(snapshot["public_artifacts_dir"])
    assert (files / "root/report.csv").read_text() == "public output"


def test_real_official_reward_catches_failure_despite_test_script_exit_zero(real_runner):
    with real_runner.episode(SkillBundle({"SKILL.md": "Offline boundary probe."})) as episode:
        (episode.work / "mass_report.json").write_text('{"main_part_mass":-1,"material_id":-1}')
        result = real_runner.grade(episode)
    assert result["status"] == "MEASURED"
    assert result["utility"] is False and result["reward"] == 0
    assert result["grader_exit_code"] == 0


@pytest.mark.parametrize(
    "task", ["glm-lake-mendota", "xlsx-recover-data", "trend-anomaly-causal-inference"]
)
def test_public_build_context_restores_git_mode_and_excludes_answers_author_skills(
    public_source, tmp_path, task
):
    from tau_skill_evolution.skillsbench_runtime import _prepare_build_context

    source = public_source
    recipe = _prepare_build_context(source, task, tmp_path)
    if task == "glm-lake-mendota":
        assert (tmp_path / "glm").stat().st_mode & 0o777 == 0o755
    if task == "xlsx-recover-data":
        assert not (tmp_path / "groundtruth").exists()
        assert (tmp_path / "nasa_budget_incomplete.xlsx").is_file()
    if task == "trend-anomaly-causal-inference":
        assert not any(
            line.strip().lower().startswith("copy skills") for line in recipe.splitlines()
        )
        assert not (tmp_path / "skills").exists()


def test_incomplete_native_response_never_dispatches_partial_tool(public_source):
    from tau_skill_evolution.model import _assistant_response

    response = _assistant_response(
        {
            "status": "incomplete",
            "incomplete_details": {"reason": "max_output_tokens"},
            "output": [
                {
                    "type": "function_call",
                    "call_id": "partial",
                    "name": "run_terminal_command",
                    "arguments": '{"command":"never dispatch"}',
                }
            ],
            "usage": {"input_tokens": 1, "output_tokens": 1},
        }
    )
    assert response["finish_reason"] == "length"
    model = SimpleNamespace(complete=lambda *args, **kwargs: response)
    spec = SimpleNamespace(
        root=EXPERIMENT_ROOT,
        values={
            "runtime": {
                "max_turns": 5,
                "controls": {"assistant_completion_budget": 30, "agent": {"max_output_tokens": 10}},
            }
        },
    )
    adapter = SkillsBenchAdapter(spec, "3d-scan-calc", demo=True, model_factory=lambda role: model)
    result = adapter._execute(SkillBundle({"SKILL.md": "current"}), SimpleNamespace())
    assert result["termination_reason"] == "model_output_incomplete"
    assert result["tool_calls"] == 0 and result["events"] == []


@pytest.mark.parametrize("exit_code,reward", [(0, "0"), (1, "0"), (0, "0.5"), (1, "0.5"), (0, "1")])
def test_grader_prepare_accepts_real_reward_even_when_assertions_exit_one(exit_code, reward):
    from tau_skill_evolution.skillsbench_runtime import _validate_grader_warmup

    report = {
        "results": {
            "summary": {"tests": 2, "passed": 0, "failed": 2},
            "tests": [{"status": "failed"}, {"status": "failed"}],
        }
    }
    _validate_grader_warmup(exit_code, reward, report, "assertion failed: candidate output missing")


@pytest.mark.parametrize(
    "exit_code,reward,report,diagnostics",
    [
        (0, None, None, ""),
        (1, None, None, ""),
        (0, "NaN", None, ""),
        (0, "2", None, ""),
        (127, "0", None, "command not found"),
        (2, "0", None, "pytest collection failed"),
        (0, "0", None, "ModuleNotFoundError: dependency unavailable"),
        (0, "0", None, "ERROR collecting /tests/test_outputs.py"),
        (0, "0", None, "uvx: command not found"),
        (0, "0", {"results": {"summary": {"tests": 0}}}, ""),
        (0, "0", {"results": {"summary": {"tests": 1, "errors": 1}}}, ""),
        (0, "0", {"results": {"summary": {"tests": 1}, "tests": [{"status": "broken"}]}}, ""),
    ],
)
def test_grader_prepare_rejects_missing_invalid_reward_and_infrastructure(
    exit_code, reward, report, diagnostics
):
    from tau_skill_evolution.skillsbench_runtime import _validate_grader_warmup

    with pytest.raises(RuntimeError, match="skillsbench_warmup"):
        _validate_grader_warmup(exit_code, reward, report, diagnostics)


@pytest.mark.parametrize("mode", ["native", "standalone"])
def test_docker_grader_preparation_uses_private_guard_and_discards_warmup_scores(
    public_source, tmp_path, monkeypatch, mode
):
    from tau_skill_evolution import skillsbench_runtime as runtime

    source = public_source
    monkeypatch.setattr(runtime, "SkillsBenchSource", lambda root: source)
    monkeypatch.setattr(runtime.shutil, "which", lambda name: "docker")
    (tmp_path / "runtime").mkdir()
    (tmp_path / "runtime/skillsbench-verifier-requirements.lock").write_bytes(
        (EXPERIMENT_ROOT / "runtime/skillsbench-verifier-requirements.lock").read_bytes()
    )
    builds, probes, readbacks = [], [], []
    interpreter = "python3" if mode == "native" else "/opt/tau-python/python3"

    def run(command, **kwargs):
        if command[1] == "build":
            stage = Path(command[-1])
            recipe = (stage / "Dockerfile").read_text()
            guard = (stage / "warmup.py").read_text() if (stage / "warmup.py").exists() else None
            builds.append((recipe, guard, (stage / "tests").exists()))
        if command[1] == "run":
            probes.append(command)
            assert "import sys, pip" in command[-1] and "--network" in command
            return SimpleNamespace(returncode=0 if mode == "native" else 1)
        return SimpleNamespace(returncode=0)

    def check_output(command):
        readbacks.append(command)
        if command[1] == "image":
            return json.dumps(
                [{"Id": "sha256:" + "a" * 64, "Config": {"Env": ["PATH=/usr/bin:/bin"]}}]
            ).encode()
        assert command[1] == "run" and "--network" in command
        if "cat" in command:
            assert command[-1] == "/opt/tau-grader/warmup.json"
            return b'{"exit_code": 1, "missing_deliverable_modules": [], "reward": 0.0}'
        assert command[command.index("--entrypoint") + 1] == interpreter
        return b"[3, 11, 14]"

    monkeypatch.setattr(runtime.subprocess, "run", run)
    monkeypatch.setattr(runtime.subprocess, "check_output", check_output)
    result = runtime.prepare_docker(tmp_path, "3d-scan-calc")
    assert result["ready"]
    assert len(probes) == 1 and probes[0][-3] == "tau-skillsbench-3d-scan-calc:4380d4bff673"
    assert len(builds) == 3 and not builds[0][2] and not builds[1][2]
    assert "--target /.tau-verifier" in builds[1][0] and "--require-hashes" in builds[1][0]
    assert "numpy" not in (tmp_path / "runtime/skillsbench-verifier-requirements.lock").read_text()
    recipe, guard, hidden_tests_present = builds[2]
    assert recipe.startswith("FROM tau-skillsbench-3d-scan-calc:")
    assert "-runtime\n" not in recipe
    assert "HOME=/opt/tau-grader/home" in recipe
    assert "UV_CACHE_DIR=/opt/tau-grader/cache" in recipe
    assert hidden_tests_present and f"RUN {interpreter} -I /tmp/grader-warmup.py" in recipe
    assert "RUN /bin/bash /tests/test.sh" not in recipe
    compile(guard, "private grader warmup", "exec")
    assert "capture_output=True" in guard and "math.isfinite" in guard
    assert "bootstrap.commands').touch()" in guard
    assert "bootstrap.failed" in guard
    assert "shutil.rmtree('/logs/verifier', ignore_errors=True)" in guard
    assert "def _deliverable_modules" in guard and "/opt/tau-grader/warmup.json" in guard
    assert "rm -rf /logs" in recipe
    assert "reward" not in result and "utility" not in result
    assert result["verifier_python_mode"] == mode
    assert result["images"]["runtime"]["verifier_python"] == interpreter
    assert result["images"]["runtime"]["verifier_python_version"] == [3, 11, 14]
    assert result["grader_warmup"] == {
        "reward": 0.0,
        "exit_code": 1,
        "missing_deliverable_modules": [],
    }
    standalone = "COPY --from=ghcr.io/astral-sh/uv:0.9.26 /uv /usr/local/bin/tau-uv"
    for stage_recipe in (builds[1][0], recipe):
        assert (standalone in stage_recipe) is (mode == "standalone")
        assert ("tau-uv python install 3.11" in stage_recipe) is (mode == "standalone")
    assert ("python3 -m pip install" in builds[1][0]) is (mode == "native")
    assert ("tau-uv pip install --no-cache --python /opt/tau-python/python3" in builds[1][0]) is (
        mode == "standalone"
    )
    assert standalone not in builds[0][0]


@pytest.mark.parametrize("role", ["execution", "verifier", "grader"])
def test_docker_keeps_task_python_and_isolates_verifier_and_grader(
    public_source, tmp_path, monkeypatch, role
):
    runner = SkillsBenchRunner(EXPERIMENT_ROOT, "travel-planning", demo=False)
    runner.config["environment"]["allow_internet"] = True
    images = {
        name: {
            "digest": "sha256:" + str(index) * 64,
            "environment": [
                "PATH=/original/python/bin:/usr/bin:/bin",
                "HOME=/opt/tau-grader/home" if name == "grader" else "HOME=/root",
                "UV_CACHE_DIR=/opt/tau-grader/cache",
            ],
        }
        for index, name in enumerate(("environment", "runtime", "grader"), 1)
    }
    images["runtime"]["verifier_python"] = "/opt/tau-python/python3"
    lock = {"images": images, "layout": {"workdir": "/app", "copies": []}}
    monkeypatch.setattr(Path, "read_text", lambda *args, **kwargs: json.dumps(lock))
    runner.workspace_mounts = {"/app": tmp_path / "app", "/opt": tmp_path / "opt"}
    if role == "verifier":
        runner.verifier_artifacts = tmp_path / "public"
        runner.verifier_artifacts.mkdir()
        (runner.verifier_artifacts / "opt").mkdir()
        (runner.verifier_artifacts / "paper.pdf").write_bytes(b"public artifact")
    if role == "grader":
        runner.grader_cache = tmp_path / "private-runtime"
    args = (
        ["python", "-I", "/bundle/_harness.py"] if role == "verifier" else ["python", "-c", "pass"]
    )
    command = runner._docker_command(tmp_path, tmp_path, args, grader=role == "grader")
    identity = images[{"execution": "environment", "verifier": "runtime", "grader": "grader"}[role]]
    assert identity["digest"] in command
    assert command[command.index("--network") + 1] == ("bridge" if role == "execution" else "none")
    assert "PATH=/original/python/bin:/usr/bin:/bin" in command
    if role == "verifier":
        # The verifier runs on the locked interpreter, never on the task's python.
        assert "/opt/tau-python/python3" in command and "python3" not in command
        assert command[-1] == "/bundle/_harness.py"
        assert "sys.path.insert(0, '/.tau-verifier')" in command[-2]
        assert f"type=bind,src={runner.verifier_artifacts / 'opt'},dst=/opt,readonly" in command
        assert (
            f"type=bind,src={runner.verifier_artifacts / 'paper.pdf'},dst=/paper.pdf,readonly"
            in command
        )
    elif role == "grader":
        assert "python3" in command and "/opt/tau-python/python3" not in command
        assert "HOME=/opt/tau-grader/home" in command and "UV_OFFLINE=1" in command
        assert f"type=bind,src={runner.grader_cache},dst=/opt/tau-grader" in command
    else:
        assert "python3" in command and "/opt/tau-python/python3" not in command
        assert "UV_OFFLINE=1" not in command
        assert not any("private-runtime" in arg for arg in command)
        assert "sys.path.insert" not in command[-1]


def test_grader_bootstrap_replays_only_successfully_prepared_exact_commands(tmp_path):
    import subprocess

    from tau_skill_evolution.skillsbench_runtime import _grader_bootstrap

    private = tmp_path / "private"
    private.mkdir()
    (private / "bootstrap.commands").touch()
    binaries = tmp_path / "bin"
    binaries.mkdir()
    called = tmp_path / "called"
    for name in ("apt-get", "curl"):
        executable = binaries / name
        executable.write_text(f'#!/bin/bash\necho {name} >> "{called}"\n')
        executable.chmod(0o755)
    script = tmp_path / "test.sh"
    script.write_text(
        "set -e\napt-get update\napt-get install -y curl\n"
        "curl -LsSf https://astral.sh/uv/0.9.7/install.sh | sh\n"
    )
    env = {"PATH": f"{binaries}:/usr/bin:/bin"}

    def run(prepare):
        code = _grader_bootstrap(prepare=prepare).replace("/opt/tau-grader", str(private))
        code = code.replace("/tests/test.sh", str(script))
        return subprocess.run(["/bin/bash", "-c", code], env=env, capture_output=True)

    assert run(True).returncode == 0
    original = called.read_text()
    assert len((private / "bootstrap.commands").read_text().splitlines()) == 3
    assert run(False).returncode == 0 and called.read_text() == original
    script.write_text("apt-get install -y unprepared-package\n")
    assert run(False).returncode == 97
    assert (private / "bootstrap.failed").exists() and called.read_text() == original


def test_grader_prepare_does_not_record_failed_astral_installer(tmp_path):
    import subprocess

    from tau_skill_evolution.skillsbench_runtime import _grader_bootstrap

    private, binaries = tmp_path / "private", tmp_path / "bin"
    private.mkdir()
    binaries.mkdir()
    (private / "bootstrap.commands").touch()
    curl = binaries / "curl"
    curl.write_text("#!/bin/bash\nprintf '#!/bin/sh\\nexit 23\\n'\n")
    curl.chmod(0o755)
    script = tmp_path / "test.sh"
    script.write_text("curl -LsSf https://astral.sh/uv/0.9.7/install.sh | sh\n")
    code = _grader_bootstrap(prepare=True).replace("/opt/tau-grader", str(private))
    code = code.replace("/tests/test.sh", str(script))
    subprocess.run(
        ["/bin/bash", "-c", code], env={"PATH": f"{binaries}:/usr/bin:/bin"}, check=False
    )
    assert (private / "bootstrap.failed").is_file()
    assert (private / "bootstrap.commands").read_text() == ""


def test_docker_private_cache_copy_is_required_and_always_cleaned(public_source, tmp_path):
    runner = SkillsBenchRunner(EXPERIMENT_ROOT, "travel-planning", demo=False)
    calls = []

    class Transport:
        def run(self, command, **kwargs):
            calls.append(command)
            return (
                ProcessResult(1, stderr=b"Could not find")
                if command[1] == "cp"
                else ProcessResult(0)
            )

    runner.transport = Transport()
    with pytest.raises(RuntimeError, match="workspace_copy_failed"):
        runner._copy_image_directories(
            "locked-private-image", {"/opt/tau-grader": tmp_path}, allow_missing=False
        )
    assert calls[0][-1] == "locked-private-image"
    assert calls[-1][:4] == ["docker", "rm", "--force", "--volumes"]


@pytest.mark.parametrize("bootstrap_failed", [True, False])
def test_private_grader_failure_marker_cannot_become_a_measured_zero(
    public_source, tmp_path, bootstrap_failed
):
    runner = SkillsBenchRunner(EXPERIMENT_ROOT, "travel-planning", demo=False)
    work = tmp_path / "work"
    work.mkdir()
    runner._docker_lock = lambda: {"images": {"grader": {"digest": "locked-private-image"}}}
    observed = []

    def copy(image, directories, **kwargs):
        observed.append((image, directories, kwargs))
        (runner.grader_cache / "bootstrap.commands").touch()

    def grade(package, work, args, **kwargs):
        assert runner.grader_cache is not None and package.name == "grader-package"
        assert args[:2] == ["/bin/bash", "-c"] and "source /tests/test.sh" in args[2]
        (tmp_path / "grader-logs/reward.txt").write_text("0")
        if bootstrap_failed:
            (runner.grader_cache / "bootstrap.failed").touch()
        return ProcessResult(0)

    runner._copy_image_directories, runner._raw = copy, grade
    result = runner.grade(SimpleNamespace(work=work))
    assert runner.grader_cache is None
    assert observed[0][0] == "locked-private-image"
    assert observed[0][2] == {"allow_missing": False}
    assert result["status"] == ("NOT_MEASURED" if bootstrap_failed else "MEASURED")
    assert result.get("failure") == ("grader_bootstrap_failed" if bootstrap_failed else None)
    assert result["utility"] is (None if bootstrap_failed else False)


def test_grader_prepare_creates_the_uv_env_file_the_installer_skips(tmp_path):
    import subprocess

    from tau_skill_evolution.skillsbench_runtime import _grader_bootstrap

    private, binaries, home = tmp_path / "private", tmp_path / "bin", tmp_path / "home"
    private.mkdir()
    binaries.mkdir()
    (home / ".local/bin").mkdir(parents=True)
    (private / "bootstrap.commands").touch()
    curl = binaries / "curl"
    # Like the real installer when $HOME/.local/bin is already on PATH: install, no env file.
    curl.write_text("#!/bin/bash\nprintf '#!/bin/sh\\ntouch \"$HOME/.local/bin/uv\"\\n'\n")
    curl.chmod(0o755)
    script = tmp_path / "test.sh"
    script.write_text(
        "set -euo pipefail\ncurl -LsSf https://astral.sh/uv/0.9.7/install.sh | sh\n"
        'source "$HOME/.local/bin/env"\necho "$PATH" > "$HOME/path.txt"\n'
    )
    env = {"PATH": f"{home / '.local/bin'}:{binaries}:/usr/bin:/bin", "HOME": str(home)}

    def run(prepare):
        code = _grader_bootstrap(prepare=prepare).replace("/opt/tau-grader", str(private))
        return subprocess.run(
            ["/bin/bash", "-c", code.replace("/tests/test.sh", str(script))],
            env=env,
            capture_output=True,
        )

    assert run(True).returncode == 0
    assert (home / ".local/bin/uv").exists()
    env_file = (home / ".local/bin/env").read_text()
    assert env_file.startswith("#!/bin/sh\n") and 'export PATH="' in env_file
    assert (home / "path.txt").read_text().startswith(str(home / ".local/bin"))
    assert not (private / "bootstrap.failed").exists()
    (home / ".local/bin/env").write_text("# kept\n")
    assert run(False).returncode == 0
    assert (home / ".local/bin/env").read_text() == "# kept\n"
    assert not (private / "bootstrap.failed").exists()


def test_warmup_accepts_missing_agent_deliverables_but_not_missing_dependencies():
    from tau_skill_evolution.skillsbench_runtime import _missing_modules, _validate_grader_warmup

    collection = (
        "ERROR collecting /tests/test_outputs.py\n"
        "ModuleNotFoundError: No module named 'solution'\n"
        "!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!\n"
    )
    empty = {"results": {"summary": {"tests": 0, "passed": 0}, "tests": []}}
    assert _missing_modules(collection) == ["solution"]
    assert _missing_modules(
        "ImportError: cannot import name 'solve' from 'solution' (/root/workspace/solution.py)"
    ) == ["solution"]
    assert _missing_modules("No module named 'package.sub'; 'package' is not a package") == [
        "package"
    ]
    _validate_grader_warmup(1, "0", empty, collection, ["solution"])
    _validate_grader_warmup(1, "0", None, collection, ["solution", "helpers"])
    with pytest.raises(RuntimeError, match="dependency_or_collection_error"):
        _validate_grader_warmup(1, "0", empty, collection)
    with pytest.raises(RuntimeError, match="dependency_or_collection_error"):
        _validate_grader_warmup(
            1, "0", empty, collection + "No module named 'numpy'\n", ["solution"]
        )
    with pytest.raises(RuntimeError, match="dependency_or_collection_error"):
        _validate_grader_warmup(1, "0", None, collection + "uvx: command not found\n", ["solution"])
    with pytest.raises(RuntimeError, match="dependency_or_collection_error"):
        _validate_grader_warmup(1, "0", None, "ImportError: libGL.so.1 missing", ["solution"])
    with pytest.raises(RuntimeError, match="no_collected_checks"):
        _validate_grader_warmup(1, "0", empty, "4 failed", ["solution"])
    with pytest.raises(RuntimeError) as failure:
        _validate_grader_warmup(1, "0", None, "x" * 5000 + "\x1b[31mNo module named 'scipy'\n")
    message = str(failure.value)
    assert message.startswith("skillsbench_warmup_dependency_or_collection_error\n")
    assert "No module named 'scipy'" in message and "\x1b" not in message
    assert len(message) < 1500 and "x" * 1300 not in message


def test_deliverable_modules_require_workspace_import_and_absence_from_image(tmp_path):
    from tau_skill_evolution.skillsbench_runtime import _deliverable_modules

    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_outputs.py").write_text(
        "import sys, json\nsys.path.insert(0, '/root/workspace')\n"
        "from solution import solve\n\ndef test_x():\n    from parallel_solution import run\n"
    )
    diagnostics = (
        "No module named 'solution'\nNo module named 'json'\nNo module named 'numpy'\n"
        "No module named 'parallel_solution'\n"
    )
    assert _deliverable_modules(diagnostics, tests) == ["parallel_solution", "solution"]
    (tests / "test_outputs.py").write_text("from solution import solve\n")
    assert _deliverable_modules(diagnostics, tests) == []
    (tests / "test_outputs.py").write_text(
        "import sys\nsys.path.append('/x')\nimport os, solution\n"
    )
    assert _deliverable_modules("No module named 'solution'", tests) == ["solution"]
    assert _deliverable_modules("No module named 'solutions'", tests) == []


def test_docker_lock_accepts_legacy_and_standalone_locks_and_rejects_inconsistent_ones(
    public_source, tmp_path, monkeypatch
):
    import hashlib

    from tau_skill_evolution.skillsbench_runtime import _grader_bootstrap

    runner = SkillsBenchRunner(EXPERIMENT_ROOT, "3d-scan-calc", demo=False)
    runner.root = tmp_path
    (tmp_path / "runtime").mkdir()
    (tmp_path / "runtime/skillsbench-verifier-requirements.lock").write_bytes(
        (EXPERIMENT_ROOT / "runtime/skillsbench-verifier-requirements.lock").read_bytes()
    )
    (runner.task_directory / "environment").mkdir(parents=True, exist_ok=True)
    (runner.task_directory / "environment/Dockerfile").write_text("FROM base\n")
    (runner.task_directory / "task.toml").write_text("[environment]\ncpus = 1\n[verifier]\n")
    runner.config = {"environment": {"cpus": 1}, "verifier": {}}
    runner.transport = SimpleNamespace(run=lambda *args, **kwargs: ProcessResult(0))
    images = {
        role: {
            "digest": "sha256:" + str(index) * 64,
            "environment": [
                "HOME=/opt/tau-grader/home" if role == "grader" else "HOME=/root",
                "UV_CACHE_DIR=/opt/tau-grader/cache",
            ],
        }
        for index, role in enumerate(("environment", "runtime", "grader"), 1)
    }
    base = {
        "commit": runner.source.manifest.get("commit", "4380d4bff673dd6e1d58e5babeb2aaa0fe527119"),
        "task_id": "3d-scan-calc",
        "dockerfile_sha256": hashlib.sha256(b"FROM base\n").hexdigest(),
        "public_manifest_hash": runner.source.manifest["manifest_hash"],
        "dependency_hash": hashlib.sha256(
            (EXPERIMENT_ROOT / "runtime/skillsbench-verifier-requirements.lock").read_bytes()
        ).hexdigest(),
        "grader_bootstrap_sha256": hashlib.sha256(
            _grader_bootstrap(prepare=False).encode()
        ).hexdigest(),
        "resources": {"cpus": 1},
        "layout": runner.source.manifest["environments"]["3d-scan-calc"],
        "images": images,
    }
    path = tmp_path / "runtime/skillsbench-docker-3d-scan-calc-lock.json"

    def validate(**changes):
        value = json.loads(json.dumps(base))
        for key, replacement in changes.items():
            target = value
            parts = key.split(".")
            for part in parts[:-1]:
                target = target[part]
            if replacement is None:
                target.pop(parts[-1], None)
            else:
                target[parts[-1]] = replacement
        path.write_text(json.dumps(value))
        return runner._docker_lock()

    assert validate()["images"]["runtime"].get("verifier_python") is None
    standalone = validate(
        verifier_python_mode="standalone",
        **{"images.runtime.verifier_python": "/opt/tau-python/python3"},
        grader_warmup={"reward": 0.0, "exit_code": 1, "missing_deliverable_modules": ["solution"]},
    )
    assert standalone["grader_warmup"]["missing_deliverable_modules"] == ["solution"]
    validate(verifier_python_mode="native", **{"images.runtime.verifier_python": "python3"})
    for changes in (
        {"verifier_python_mode": "standalone"},
        {"images.runtime.verifier_python": "/opt/tau-python/python3"},
        {"verifier_python_mode": "system"},
        {"grader_warmup": {"missing_deliverable_modules": "solution"}},
        {"grader_warmup": {"missing_deliverable_modules": ["../solution"]}},
        {"grader_warmup": []},
        {"images.runtime.digest": None},
    ):
        with pytest.raises(RuntimeError, match="skillsbench_"):
            validate(**changes)


def test_official_grader_output_limit_exceeds_tool_output_limit(
    public_source, tmp_path, monkeypatch
):
    from tau_skill_evolution.skillsbench_runtime import _GRADER_OUTPUT_LIMIT

    runner = SkillsBenchRunner(EXPERIMENT_ROOT, "travel-planning", demo=False)
    runner.config["verifier"] = {"timeout_sec": 30}
    images = {
        role: {"digest": "sha256:" + str(index) * 64, "environment": []}
        for index, role in enumerate(("environment", "runtime", "grader"), 1)
    }
    lock = {"images": images, "layout": {"workdir": "/app", "copies": []}}
    monkeypatch.setattr(Path, "read_text", lambda *args, **kwargs: json.dumps(lock))
    runner.grader_cache = tmp_path
    limits = []

    class Transport:
        def run(self, command, **kwargs):
            if command[:2] == ["docker", "run"]:
                limits.append((kwargs["output_limit"], kwargs["timeout"]))
            return ProcessResult(0)

    runner.transport = Transport()
    runner._raw(tmp_path, tmp_path, ["/bin/bash", "-c", "true"], grader=True)
    runner._raw(tmp_path, tmp_path, ["/bin/bash", "-c", "true"])
    assert _GRADER_OUTPUT_LIMIT == 16 * 1024 * 1024
    assert limits == [(_GRADER_OUTPUT_LIMIT, 30.0), (65536, 60.0)]


def test_docker_preflight_admits_task_images_without_python_and_missing_deliverables(
    public_source, tmp_path, monkeypatch
):
    runner = SkillsBenchRunner(EXPERIMENT_ROOT, "3d-scan-calc", demo=False)
    runner.root = tmp_path
    images = {
        role: {
            "digest": "sha256:" + str(index) * 64,
            "environment": [
                "PATH=/usr/bin:/bin",
                "HOME=/opt/tau-grader/home" if role == "grader" else "HOME=/root",
                "UV_CACHE_DIR=/opt/tau-grader/cache",
            ],
        }
        for index, role in enumerate(("environment", "runtime", "grader"), 1)
    }
    images["runtime"]["verifier_python"] = "/opt/tau-python/python3"
    lock = {
        "images": images,
        "layout": runner.source.manifest["environments"][runner.task_id],
        "verifier_python_mode": "standalone",
        "grader_warmup": {
            "reward": 0.0,
            "exit_code": 0,
            "missing_deliverable_modules": ["solution"],
        },
    }
    lock_path = tmp_path / f"runtime/skillsbench-docker-{runner.task_id}-lock.json"
    lock_path.parent.mkdir()
    lock_path.write_text(json.dumps(lock))
    monkeypatch.setattr(runner, "_docker_lock", lambda: lock)
    monkeypatch.setattr("tau_skill_evolution.skillsbench_runtime.shutil.which", lambda _: "docker")
    runs = []

    class Transport:
        def run(self, command, **_kwargs):
            if command[:2] == ["docker", "cp"]:
                if command[2].endswith(":/opt/tau-grader/."):
                    (Path(command[3]) / "bootstrap.commands").touch()
                return ProcessResult(0)
            if command[:2] != ["docker", "run"]:
                return ProcessResult(0)
            runs.append(command)
            if images["environment"]["digest"] in command:
                # A Java/Erlang/Lean task image: bash exists, python3 does not.
                assert command[-3] == "/bin/bash" and "command -v python3" in command[-1]
                return ProcessResult(0, stdout=b"null")
            if images["runtime"]["digest"] in command:
                assert "/opt/tau-python/python3" in command and "python3" not in command
                return ProcessResult(0, stdout=b'{"pytest":"8.4.1","pytest-json-ctrf":"0.3.5"}')
            for argument in command:
                if argument.startswith("type=bind,") and "dst=/logs/verifier" in argument:
                    logs = Path(argument.split("src=")[1].split(",")[0])
            logs.joinpath("reward.txt").write_text("0")
            logs.joinpath("ctrf.json").write_text(
                json.dumps({"results": {"summary": {"tests": 0}, "tests": []}})
            )
            return ProcessResult(
                0, stdout=b"ERROR collecting /tests/test_outputs.py\nNo module named 'solution'\n"
            )

    runner.transport = Transport()
    result = runner.preflight(validate_source=False)
    assert len(runs) == 3
    assert result["task_python"] is None and result["dependencies"] is True
    assert result["verifier_dependencies"] is True
    assert result["official_grader"] is True and result["ready"] is True
    lock["grader_warmup"]["missing_deliverable_modules"] = []
    result = runner.preflight(validate_source=False)
    assert result["official_grader"] is False and result["ready"] is False
    assert result["official_grader_error"] == "official_grader_program_error"
