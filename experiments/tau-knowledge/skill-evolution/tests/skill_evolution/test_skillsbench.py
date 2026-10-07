import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
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

_ENTERPRISE_BOOTSTRAP = """#!/bin/bash

# Use this file to install test dependencies and run the tests.
# It will be copied to /tests/test.sh and run from the working directory.

apt-get update
apt-get install -y curl

curl -LsSf https://astral.sh/uv/0.9.7/install.sh | sh

source $HOME/.local/bin/env

# CTRF produces a standard test report in JSON format which is useful for logging.
uvx \\
  --with pytest==8.4.1 \\
  --with pytest-json-ctrf==0.3.5 \\
  pytest --ctrf /logs/verifier/ctrf.json /tests/test_outputs.py -rA

if [ $? -eq 0 ]; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi
"""


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
        "enterprise-information-search": (
            "/root",
            {"DATA/products.json": "public data", "question.txt": "public questions"},
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
        (directory / "tests/test.sh").write_text(
            _ENTERPRISE_BOOTSTRAP if task_id == "enterprise-information-search" else "exit 0\n"
        )
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
    assert result["official_checks"] == {
        "status": "MEASURED",
        "source": "pytest-json-ctrf.summary",
        "unit": "reporter_group",
        "passed": 1,
        "total": 2,
        "rate": 0.5,
    }


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


def test_public_snapshot_preserves_internal_links_and_executable_files(public_source, tmp_path):
    adapter = SkillsBenchAdapter(
        SimpleNamespace(root=EXPERIMENT_ROOT),
        "3d-scan-calc",
        demo=True,
        artifact_root=tmp_path / "artifacts",
    )
    work = tmp_path / "work"
    (work / "node_modules/.bin").mkdir(parents=True)
    executable = work / "node_modules/tool.js"
    executable.write_text("#!/bin/sh\necho task\n")
    executable.chmod(0o755)
    (work / "node_modules/.bin/tool").symlink_to("../tool.js")
    (work / "python").symlink_to("/usr/bin/python3")
    trace = adapter._snapshot(SimpleNamespace(work=work))
    root = adapter.runner._public_artifacts(trace)
    assert (root / "root/node_modules/tool.js").stat().st_mode & 0o777 == 0o555
    assert os.readlink(root / "root/node_modules/.bin/tool") == "../tool.js"
    assert os.readlink(root / "root/python") == "/usr/bin/python3"
    link = root / "root/node_modules/.bin/tool"
    link.unlink()
    link.symlink_to("../changed.js")
    with pytest.raises(ValueError, match="snapshot_corrupt"):
        adapter.runner._public_artifacts(trace)


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


def test_executor_seals_raw_responses_in_private_episode_journal(public_source, tmp_path):
    from tau_skill_evolution.model import GenerationConfig, OpenAICompatibleClient

    sends = []
    body = json.dumps(
        {
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "status": "completed",
                    "content": [{"type": "output_text", "text": "PRIVATE_EXECUTOR_TEXT"}],
                }
            ],
            "usage": {"input_tokens": 3, "output_tokens": 2},
        }
    ).encode()
    client = OpenAICompatibleClient(
        "https://bedrock-mantle.us-east-1.api.aws/openai/v1",
        api_key="offline-only",
        config=GenerationConfig(model="openai.gpt-5.5", transport="bedrock-responses"),
    )
    client._send = lambda prepared: sends.append(prepared) or (200, body)
    spec = SimpleNamespace(
        root=EXPERIMENT_ROOT,
        values={
            "runtime": {
                "max_turns": 2,
                "controls": {
                    "assistant_completion_budget": 30,
                    "agent": {"max_output_tokens": 10},
                },
            }
        },
    )
    adapter = SkillsBenchAdapter(
        spec,
        "3d-scan-calc",
        demo=True,
        model_factory=lambda _: client,
        model_journal_dir=tmp_path / "private/models",
    )
    trace = adapter._execute(SkillBundle({"SKILL.md": "PRIVATE_SKILL"}), SimpleNamespace())
    files = list((tmp_path / "private/models").rglob("raw-response.json"))
    assert len(files) == len(sends) == 1
    assert json.loads(files[0].read_text())["length"] == len(body)
    assert "PRIVATE_EXECUTOR_TEXT" not in json.dumps(trace)
    assert "private/models" not in json.dumps(trace)


def test_unknown_executor_request_cannot_be_resent_in_same_episode(public_source, tmp_path):
    from tau_skill_evolution.journal import UnknownOperation

    calls = []

    def complete(*_args, **_kwargs):
        calls.append(1)
        raise TimeoutError("unknown remote outcome")

    spec = SimpleNamespace(
        root=EXPERIMENT_ROOT,
        values={
            "runtime": {
                "max_turns": 2,
                "controls": {
                    "assistant_completion_budget": 30,
                    "agent": {"max_output_tokens": 10},
                },
            }
        },
    )
    adapter = SkillsBenchAdapter(
        spec,
        "3d-scan-calc",
        demo=True,
        model_factory=lambda _: SimpleNamespace(complete=complete),
        model_journal_dir=tmp_path / "private/models",
    )
    bundle, episode = SkillBundle({"SKILL.md": "current"}), SimpleNamespace()
    for _ in range(2):
        with pytest.raises(UnknownOperation):
            adapter._execute(bundle, episode)
    assert calls == [1]


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
        _validate_grader_warmup(
            1, "0", None, "x" * 5000 + "\n\x1b[31mModuleNotFoundError: No module named 'scipy'\n"
        )
    message = str(failure.value)
    assert message.startswith("skillsbench_warmup_dependency_or_collection_error\n")
    assert "No module named 'scipy'" in message and "\x1b" not in message
    assert len(message) < 1500 and "x" * 1300 not in message


def test_deliverable_modules_require_declared_public_name_and_workspace_import(tmp_path):
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
    declared = ["parallel_solution", "solution"]
    assert _deliverable_modules(diagnostics, tests, declared) == declared
    assert _deliverable_modules(diagnostics, tests) == []
    (tests / "test_outputs.py").write_text("from solution import solve\n")
    assert _deliverable_modules(diagnostics, tests, declared) == []
    (tests / "test_outputs.py").write_text(
        "import sys\nsys.path.append('/x')\nimport os, solution\n"
    )
    assert _deliverable_modules("No module named 'solution'", tests, declared) == ["solution"]
    assert _deliverable_modules("No module named 'solutions'", tests, declared) == []


@pytest.fixture
def docker_runner(public_source, tmp_path, monkeypatch):
    """Emulate the Docker API, never execute task or grader code on the host."""
    import shutil
    import tarfile

    import yaml
    from tau_skill_evolution.skillsbench_runtime import _compose_definition

    runner = SkillsBenchRunner(tmp_path, "travel-planning", demo=False)
    definition = _compose_definition(runner.task_directory)
    identity = {
        "image": "prepared-task",
        "digest": "sha256:" + "a" * 64,
        "environment": ["PATH=/task/bin:/usr/bin:/bin"],
        "user": "original-user",
        "workdir": "/app",
        "entrypoint": ["/task/start.sh"],
    }
    lock = {
        "images": {
            "environment": identity,
            "runtime": {**identity, "digest": "sha256:" + "b" * 64, "verifier_python": "python3"},
        },
        "service_images": {"main": identity},
        "services": definition,
        "layout": public_source.manifest["environments"][runner.task_id],
    }
    monkeypatch.setattr(runner, "_docker_lock", lambda: lock)
    monkeypatch.setattr("tau_skill_evolution.skillsbench_runtime.shutil.which", lambda _: "docker")

    class Docker:
        def __init__(self):
            self.calls = []
            self.logs = None
            self.uploaded = False
            self.reward = "0"
            self.grader_exit = 0
            self.grader_failure = None
            self.diagnostics = b""
            self.grader_stdout = b""
            self.report = None
            self.filesystem = {}
            self.archives = {}
            self.generation = 0
            self.restart_count = 0

        def run(self, command, **kwargs):
            self.calls.append((list(command), kwargs))
            if command[:2] == ["docker", "cp"]:
                if ":" in command[2]:
                    source = command[2].split(":", 1)[1]
                    if source in self.archives:
                        shutil.copyfile(self.archives[source], command[3])
                    else:
                        shutil.copytree(
                            self.filesystem[source.removesuffix("/.")],
                            command[3],
                            dirs_exist_ok=True,
                            symlinks=True,
                        )
                elif runner.container_name and command[3] == runner.container_name + ":/tests":
                    assert not runner.public_open
                    self.uploaded = True
                return ProcessResult(0)
            if command[:2] == ["docker", "compose"] and "up" in command:
                self.uploaded = False
                self.generation += 1
                self.filesystem = {
                    destination: tmp_path
                    / f"mock-container-{self.generation}"
                    / destination.lstrip("/")
                    for destination in public_source.task(runner.task_id)["environment"][
                        "workspace_roots"
                    ]
                }
                for directory in self.filesystem.values():
                    directory.mkdir(parents=True)
                for entry in public_source.task(runner.task_id)["public_input_manifest"]:
                    for destination in entry["sandbox_paths"]:
                        root = "/" + destination.lstrip("/").split("/", 1)[0]
                        output = self.filesystem[root] / destination.removeprefix(root + "/")
                        output.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(runner.task_directory / entry["relative_path"], output)
                value = yaml.safe_load(Path(command[command.index("-f") + 1]).read_text())
                value = yaml.safe_load(Path(command[command.index("-f") + 1]).read_text())
                self.mounts = {
                    v["target"]: Path(v["source"]) for v in value["services"]["main"]["volumes"]
                }
                logs = (
                    next(
                        v["source"]
                        for v in value["services"]["main"]["volumes"]
                        if v["target"] == "/logs/verifier"
                    )
                    if "/logs/verifier" in self.mounts
                    else None
                )
                self.logs = Path(logs) if logs else None
                return ProcessResult(0)
            if command[:2] == ["docker", "compose"] and "ps" in command:
                return ProcessResult(0, stdout=("c" * 64).encode())
            if command[:2] == ["docker", "inspect"] and ".State.StartedAt" in command[-2]:
                return ProcessResult(
                    0,
                    stdout=json.dumps(
                        {
                            "id": command[-1],
                            "name": "/mock-main",
                            "service": "main",
                            "started_at": "2026-10-07T00:00:00Z",
                            "restart_count": self.restart_count,
                            "running": True,
                            "status": "running",
                            "exit_code": 0,
                            "health": None,
                        }
                    ).encode(),
                )
            if command[:2] == ["docker", "exec"]:
                if command[-1] == "find /work/candidate -mindepth 1 -depth -delete":
                    for child in self.mounts["/work/candidate"].iterdir():
                        if child.is_dir() and not child.is_symlink():
                            shutil.rmtree(child)
                        else:
                            child.unlink()
                    return ProcessResult(0)
                if len(command) > 3 and command[-3] == "snapshot":
                    source, archive = command[-2:]
                    if source not in self.filesystem:
                        return ProcessResult(44)
                    saved = tmp_path / Path(archive).name
                    with tarfile.open(saved, "w", dereference=False) as output:
                        output.add(self.filesystem[source], arcname=".")
                    self.archives[archive] = saved
                    return ProcessResult(0)
                if command[-4:-1] == ["/bin/rm", "-f", "--"]:
                    saved = self.archives.pop(command[-1], None)
                    if saved is not None:
                        saved.unlink()
                    return ProcessResult(0)
                if command[-2:] == ["/bin/bash", "/tests/test.sh"]:
                    assert self.uploaded and not runner.public_open
                    if self.reward is not None:
                        (self.logs / "reward.txt").write_text(self.reward)
                    if self.report is not None:
                        (self.logs / "ctrf.json").write_text(json.dumps(self.report))
                    return ProcessResult(
                        self.grader_exit,
                        stdout=self.grader_stdout,
                        stderr=self.diagnostics,
                        failure=self.grader_failure,
                    )
                if "sys.version_info" in command[-1]:
                    return ProcessResult(0, stdout=b"[3,11,14]")
                return ProcessResult(0, stdout=b"{}")
            if command[:2] == ["docker", "run"]:
                if "m.version" in command[-1]:
                    return ProcessResult(0, stdout=b'{"pytest":"8.4.1","pytest-json-ctrf":"0.3.5"}')
                return ProcessResult(0, stdout=b"{}")
            return ProcessResult(0)

    docker = Docker()
    runner.transport = docker
    return runner, docker, lock


@pytest.fixture
def evolution_adapter(docker_runner, tmp_path, monkeypatch):
    from tau_skill_evolution.journal import Journal

    formal, docker, lock = docker_runner
    formal.runtime_lock_path.parent.mkdir(parents=True, exist_ok=True)
    formal.runtime_lock_path.write_text(json.dumps(lock))
    original = SkillsBenchRunner

    def learning_runner(*args, **kwargs):
        result = original(*args, **kwargs)
        result._docker_lock = lambda: lock
        return result

    monkeypatch.setattr(
        "tau_skill_evolution.skillsbench_runtime.SkillsBenchRunner", learning_runner
    )
    adapter = SkillsBenchAdapter(
        SimpleNamespace(root=tmp_path),
        "travel-planning",
        demo=False,
        artifact_root=tmp_path / "artifacts",
    )
    adapter.runner = formal
    journal = Journal(tmp_path / "journal", identity={"trial": "direct-generator"})
    return adapter, docker, journal, tmp_path / "learning"


def test_direct_generator_submits_actual_same_environment_and_keeps_parent(evolution_adapter):
    import yaml

    adapter, docker, journal, workspace = evolution_adapter
    parent = SkillBundle({"SKILL.md": "sealed S0", "scripts/main.py": "print('public')"})
    with adapter.evolution_session(
        parent, adapter.public_inputs, {}, journal=journal, workspace=workspace
    ) as session:
        assert session.runner is not adapter.runner
        session.begin_attempt(parent, True, operation_id="initial-execution")
        session.terminal("python3 /work/candidate/scripts/main.py")
        initial = session.submit(parent, initial=True, operation_id="initial-submit")
        assert initial.bundle == parent and initial.bundle.parent_hash is None
        container = session.runner.container_name
        session.begin_attempt(parent, False, operation_id="revision-1")
        (session.public.target / "SKILL.md").write_text("edited in actual task environment")
        output = docker.filesystem["/app"] / "answer.json"
        output.write_text('{"actual":"published"}')
        session.terminal("python3 /work/candidate/scripts/main.py")
        revised = session.submit(parent, operation_id="revision-1/submit")
        assert revised.bundle.parent_hash == parent.bundle_hash
        assert dict(parent.files)["SKILL.md"] == "sealed S0"
        assert initial.execution_id == revised.execution_id
        assert revised.operation_cursor == 2
        assert session.runner.container_name == container
        assert (
            Path(revised.public_trace["public_artifacts_dir"])
            .joinpath("app/answer.json")
            .read_text()
            == output.read_text()
        )
        assert "print('public')" not in json.dumps(revised.to_dict()["public_trace"])
        assert session.submit(parent, operation_id="revision-1/submit") == revised
        with pytest.raises(PermissionError, match="attempt_not_open"):
            session.terminal("touch /app/after-submit")
        definition = yaml.safe_load(session.runner.compose_path.read_text())
        mounts = {v["target"]: v for v in definition["services"]["main"]["volumes"]}
        assert mounts["/bundle"]["read_only"] and mounts["/work"]["read_only"]
        assert not mounts["/work/candidate"]["read_only"]
        assert "/run/skill-provider" not in mounts and "/logs/verifier" not in mounts
        assert not any(str(journal.root) in v["source"] for v in mounts.values())
    assert json.loads((workspace / "evolution-runtime.json").read_text())["status"] == "CLOSED"
    assert sum("up" in c for c, _ in docker.calls if c[:2] == ["docker", "compose"]) == 1


def test_direct_generator_raw_results_are_readonly_and_snapshot_ignores_live_outputs(
    evolution_adapter,
):
    adapter, docker, journal, workspace = evolution_adapter
    parent = SkillBundle({"SKILL.md": "parent"})
    with adapter.evolution_session(
        parent, adapter.public_inputs, {}, journal=journal, workspace=workspace
    ) as session:
        session.begin_attempt(parent, True, operation_id="initial")
        before = session.snapshot()
        (docker.filesystem["/app"] / "service-output.json").write_text("background update")
        (session.public.work / "scratch/result").write_text("self-check state")
        value = {"exit_code": 0, "output": "x" * 30000, "stderr": ""}
        path = session.record_tool_result("initial/model-0/tool-0", value)
        assert path.startswith("/work/observations/tools/")
        assert session.record_tool_result("initial/model-0/tool-0", value) == path
        assert session.snapshot() == before
        with pytest.raises(ValueError, match="result_changed"):
            session.record_tool_result("initial/model-0/tool-0", {"output": "changed"})
        raw = session.public.work / path.removeprefix("/work/")
        assert raw.stat().st_mode & 0o777 == 0o444
        assert (workspace / "evolution-runtime.json").stat().st_mode & 0o777 == 0o600
        public = adapter._seal_public_workspace(
            {"/work": session.public.work},
            excluded_roots=("/work/candidate", "/work/observations", "/work/scratch"),
        )
        assert public["public_artifact_count"] == 0


def test_direct_generator_initial_package_cannot_change_and_new_attempt_restores_parent(
    evolution_adapter,
):
    adapter, _docker, journal, workspace = evolution_adapter
    parent = SkillBundle({"SKILL.md": "parent"})
    with adapter.evolution_session(
        parent, adapter.public_inputs, {}, journal=journal, workspace=workspace
    ) as session:
        session.begin_attempt(parent, True, operation_id="initial")
        (session.public.target / "SKILL.md").write_text("illegal free repair")
        with pytest.raises(ValueError, match="initial_execution_changed"):
            session.submit(parent, initial=True, operation_id="initial/submit")
        session.begin_attempt(parent, False, operation_id="revision-1")
        assert session.files() == dict(parent.files)
        (session.public.target / "SKILL.md").write_text("in-flight revision")
        session.begin_attempt(parent, False, operation_id="revision-1")
        assert session.files()["SKILL.md"] == "in-flight revision"
        session.begin_attempt(parent, False, operation_id="revision-2")
        assert session.files() == dict(parent.files)


def test_direct_generator_reconnects_exact_surviving_task_without_replaying_commands(
    evolution_adapter,
):
    adapter, docker, journal, workspace = evolution_adapter
    parent = SkillBundle({"SKILL.md": "parent"})
    with (
        pytest.raises(KeyboardInterrupt),
        adapter.evolution_session(
            parent, adapter.public_inputs, {}, journal=journal, workspace=workspace
        ) as session,
    ):
        session.begin_attempt(parent, False, operation_id="revision-1")
        session.terminal("export ALREADY_EXECUTED=1")
        (session.public.target / "SKILL.md").write_text("pending draft")
        original_id = session.state["execution_id"]
        raise KeyboardInterrupt
    count = len(docker.calls)
    with adapter.evolution_session(
        parent, adapter.public_inputs, {}, journal=journal, workspace=workspace
    ) as session:
        session.begin_attempt(parent, False, operation_id="revision-1")
        assert session.files()["SKILL.md"] == "pending draft"
        assert (
            session.state["execution_id"] == original_id and session.state["operation_cursor"] == 1
        )
        assert not any("up" in c for c, _ in docker.calls[count:] if c[:2] == ["docker", "compose"])
        assert not any(
            k.get("stdin") == b"export ALREADY_EXECUTED=1" for _, k in docker.calls[count:]
        )


def test_direct_generator_missing_original_environment_never_rebuilds(
    evolution_adapter, monkeypatch
):
    from tau_skill_evolution.container import ContainerUnavailable

    adapter, docker, journal, workspace = evolution_adapter
    parent = SkillBundle({"SKILL.md": "parent"})
    with (
        pytest.raises(KeyboardInterrupt),
        adapter.evolution_session(
            parent, adapter.public_inputs, {}, journal=journal, workspace=workspace
        ),
    ):
        raise KeyboardInterrupt
    original = docker.run

    def missing(command, **kwargs):
        if command[:2] == ["docker", "inspect"]:
            return ProcessResult(1)
        return original(command, **kwargs)

    monkeypatch.setattr(docker, "run", missing)
    count = len(docker.calls)
    with (
        pytest.raises(ContainerUnavailable, match="environment_missing"),
        adapter.evolution_session(
            parent, adapter.public_inputs, {}, journal=journal, workspace=workspace
        ),
    ):
        pytest.fail("must not create a replacement task environment")
    assert not any("up" in c for c, _ in docker.calls[count:] if c[:2] == ["docker", "compose"])


def test_direct_generator_rejects_restarted_same_container(evolution_adapter):
    from tau_skill_evolution.container import ContainerUnavailable

    adapter, docker, journal, workspace = evolution_adapter
    parent = SkillBundle({"SKILL.md": "parent"})
    with (
        pytest.raises(KeyboardInterrupt),
        adapter.evolution_session(
            parent, adapter.public_inputs, {}, journal=journal, workspace=workspace
        ),
    ):
        raise KeyboardInterrupt
    docker.restart_count = 1
    count = len(docker.calls)
    with (
        pytest.raises(ContainerUnavailable, match="environment_missing"),
        adapter.evolution_session(
            parent, adapter.public_inputs, {}, journal=journal, workspace=workspace
        ),
    ):
        pytest.fail("same ID after restart has lost the previous process state")
    assert not any("up" in c for c, _ in docker.calls[count:] if c[:2] == ["docker", "compose"])


@pytest.mark.parametrize(
    ("condition", "running", "exit_code", "health", "ready"),
    [
        ("service_completed_successfully", False, 0, None, True),
        ("service_completed_successfully", False, 1, None, False),
        ("service_completed_successfully", True, 0, None, False),
        ("service_healthy", True, 0, "healthy", True),
        ("service_healthy", True, 0, "unhealthy", False),
        ("service_started", False, 0, None, False),
        (None, False, 0, None, True),
    ],
)
def test_learning_container_admission_retains_official_sidecar_conditions(
    docker_runner, condition, running, exit_code, health, ready
):
    from tau_skill_evolution.container import ContainerUnavailable

    runner, docker, lock = docker_runner
    runner.container_name, runner.compose_path = "fixture", Path("fixture-compose.yaml")
    lock["services"]["services"]["initializer"] = {}
    if condition:
        lock["services"]["services"]["main"]["depends_on"] = {
            "initializer": {"condition": condition}
        }
    original = docker.run

    def inspect_services(command, **kwargs):
        if command[:2] == ["docker", "compose"] and "ps" in command:
            return ProcessResult(0, stdout=(("c" * 64) + "\n" + ("d" * 64)).encode())
        if command[:2] == ["docker", "inspect"] and command[-1] == "d" * 64:
            return ProcessResult(
                0,
                stdout=json.dumps(
                    {
                        "id": "d" * 64,
                        "name": "/fixture-initializer",
                        "service": "initializer",
                        "started_at": "2026-10-07T00:00:00Z",
                        "restart_count": 0,
                        "running": running,
                        "status": "running" if running else "exited",
                        "exit_code": exit_code,
                        "health": health,
                    }
                ).encode(),
            )
        return original(command, **kwargs)

    docker.run = inspect_services
    if ready:
        states = runner._learning_containers()
        assert len(states) == 2 and states[1]["service"] == "initializer"
    else:
        with pytest.raises(ContainerUnavailable, match="environment_missing|service_not_ready"):
            runner._learning_containers()


def test_direct_generator_resume_allows_successful_optional_sidecar_completion(
    evolution_adapter,
):
    adapter, docker, journal, workspace = evolution_adapter
    lock = adapter.runner._docker_lock()
    lock["services"]["services"]["initializer"] = {}
    lock["service_images"]["initializer"] = lock["service_images"]["main"]
    original = docker.run
    finished = False

    def inspect_services(command, **kwargs):
        if command[:2] == ["docker", "compose"] and "ps" in command:
            return ProcessResult(0, stdout=(("c" * 64) + "\n" + ("d" * 64)).encode())
        if command[:2] == ["docker", "inspect"] and command[-1] == "d" * 64:
            return ProcessResult(
                0,
                stdout=json.dumps(
                    {
                        "id": "d" * 64,
                        "name": "/fixture-initializer",
                        "service": "initializer",
                        "started_at": "2026-10-07T00:00:00Z",
                        "restart_count": 0,
                        "running": not finished,
                        "status": "exited" if finished else "running",
                        "exit_code": 0,
                        "health": None,
                    }
                ).encode(),
            )
        return original(command, **kwargs)

    docker.run = inspect_services
    parent = SkillBundle({"SKILL.md": "parent"})
    with (
        pytest.raises(KeyboardInterrupt),
        adapter.evolution_session(
            parent, adapter.public_inputs, {}, journal=journal, workspace=workspace
        ),
    ):
        raise KeyboardInterrupt
    finished = True
    count = len(docker.calls)
    with adapter.evolution_session(
        parent, adapter.public_inputs, {}, journal=journal, workspace=workspace
    ):
        assert not any("up" in c for c, _ in docker.calls[count:] if c[:2] == ["docker", "compose"])


@pytest.mark.parametrize("reward", ["0", "0.6", "1"])
def test_official_checks_do_not_fail_on_keywords_in_printed_candidate_source(docker_runner, reward):
    runner, docker, _lock = docker_runner
    docker.reward = reward
    docker.grader_stdout = b"raise ImportError('command not found')\nModuleNotFoundError: example\n"
    docker.report = {"results": {"summary": {"tests": 2, "passed": 1, "errors": 0}, "tests": []}}
    with runner.episode(SkillBundle({"SKILL.md": "Public task"})) as episode:
        runner.close_public(episode)
        grade = runner.grade(episode)
    assert grade["status"] == "MEASURED" and grade["reward"] == float(reward)
    assert grade["official_checks"]["rate"] == 0.5


def test_no_ctrf_partial_reward_does_not_invent_checks_or_scan_stdout_keywords(docker_runner):
    runner, docker, _lock = docker_runner
    docker.reward = "0.6"
    docker.grader_stdout = b"ImportError is a candidate example; command not found is a string.\n"
    with runner.episode(SkillBundle({"SKILL.md": "Public task"})) as episode:
        runner.close_public(episode)
        grade = runner.grade(episode)
    assert grade["status"] == "MEASURED" and grade["reward"] == 0.6
    assert grade["official_checks"]["status"] == "NOT_MEASURED"
    assert grade["official_checks"]["rate"] is None


def test_official_grader_evidence_survives_cleanup_and_remains_private(docker_runner, tmp_path):
    runner, docker, _lock = docker_runner
    docker.reward = "0.5\n"
    docker.grader_stdout = b"private expected value\x00\xff\n"
    docker.diagnostics = b"private assertion detail\n"
    docker.report = {
        "results": {
            "summary": {"tests": 2, "passed": 1, "failed": 1},
            "tests": [
                {"name": "private_check_pass", "status": "passed"},
                {"name": "private_check_fail", "status": "failed"},
            ],
        }
    }
    evidence = tmp_path / "private/episode-id/official-grader"
    with runner.episode(SkillBundle({"SKILL.md": "public skill"})) as episode:
        staging = episode.work.parent
        episode.grader_evidence_dir = evidence
        episode.grader_identity = {"episode_id": "episode-id", "bundle_hash": "bound-hash"}
        runner.close_public(episode)
        result = runner.grade(episode)
        assert not any(str(evidence) in str(command) for command, _ in docker.calls)
    assert not staging.exists()
    record = json.loads((evidence / "evidence.json").read_text())
    assert record["verdict"] == result
    assert record["identity"] == episode.grader_identity
    assert record["official_items"] == docker.report["results"]["tests"]
    assert (evidence / "stdout.bin").read_bytes() == docker.grader_stdout
    assert (evidence / "stderr.bin").read_bytes() == docker.diagnostics
    assert (evidence / "reward.txt").read_text() == docker.reward
    assert json.loads((evidence / "ctrf.json").read_text()) == docker.report
    assert evidence.stat().st_mode & 0o777 == 0o700
    for path in evidence.iterdir():
        assert path.stat().st_mode & 0o777 == 0o600
        if path.name in record["files"]:
            assert record["files"][path.name] == {
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "bytes": path.stat().st_size,
            }
    assert "private_check" not in json.dumps(result)
    assert "official-grader" not in json.dumps(result)


@pytest.mark.parametrize(
    "reward,report,failure,expected",
    [
        ("invalid", None, None, "official_reward_invalid"),
        ("0", {"results": []}, None, "official_grader_program_error"),
        (None, None, None, "official_reward_missing"),
        ("0", None, "timeout", "timeout"),
        ("0", None, "output_limit", "output_limit"),
    ],
)
def test_official_grader_failure_keeps_raw_private_evidence(
    docker_runner, tmp_path, reward, report, failure, expected
):
    runner, docker, _lock = docker_runner
    docker.reward, docker.report, docker.grader_failure = reward, report, failure
    docker.diagnostics = b"captured diagnostics"
    evidence = tmp_path / "private/official-grader"
    with runner.episode(SkillBundle({"SKILL.md": "public skill"})) as episode:
        episode.grader_evidence_dir = evidence
        runner.close_public(episode)
        result = runner.grade(episode)
    assert result["status"] == "NOT_MEASURED" and result["failure"] == expected
    record = json.loads((evidence / "evidence.json").read_text())
    assert record["verdict"] == result and record["official_items"] == []
    assert record["process_failure"] == failure
    assert record["output_capture"]["limit_exceeded"] is (failure == "output_limit")
    assert (evidence / "stderr.bin").read_bytes() == docker.diagnostics
    assert (evidence / "reward.txt").exists() is (reward is not None)
    assert (evidence / "ctrf.json").exists() is (report is not None)


def test_unparseable_official_report_is_sealed_before_validation(public_source, tmp_path):
    runner = SkillsBenchRunner(public_source.root, "3d-scan-calc", demo=True)
    work = tmp_path / "work"
    work.mkdir()
    evidence = tmp_path / "private/official-grader"
    raw_report = b'{"results": invalid\xff\n'

    def grade(*_args, **_kwargs):
        logs = tmp_path / "grader-logs"
        (logs / "reward.txt").write_text("0")
        (logs / "ctrf.json").write_bytes(raw_report)
        return ProcessResult(0)

    runner._raw = grade
    result = runner.grade(SimpleNamespace(work=work, grader_evidence_dir=evidence))
    assert result["status"] == "NOT_MEASURED"
    assert result["failure"] == "official_grader_program_error"
    assert (evidence / "ctrf.json").read_bytes() == raw_report
    assert json.loads((evidence / "evidence.json").read_text())["verdict"] == result


@pytest.mark.parametrize("write_declared", [False, True])
def test_official_grader_binds_the_declared_alternate_report_filename(
    docker_runner, tmp_path, write_declared
):
    runner, docker, _lock = docker_runner
    script = runner.task_directory / "tests/test.sh"
    script.write_text("pytest --ctrf=/logs/verifier/ctrf-report.json /tests/test_outputs.py\n")
    docker.report = {
        "results": {
            "summary": {"tests": 2, "passed": 0, "failed": 2},
            "tests": [{"name": "missing_deliverable", "status": "failed"}],
        }
    }
    original = docker.run

    def run(command, **kwargs):
        result = original(command, **kwargs)
        if write_declared and command[-2:] == ["/bin/bash", "/tests/test.sh"]:
            (docker.logs / "ctrf.json").rename(docker.logs / "ctrf-report.json")
        return result

    docker.run = run
    evidence = tmp_path / "private/official-grader"
    with runner.episode(SkillBundle({"SKILL.md": "No deliverable"})) as episode:
        episode.grader_evidence_dir = evidence
        runner.close_public(episode)
        result = runner.grade(episode)
    assert result["status"] == "MEASURED" and result["reward"] == 0
    record = json.loads((evidence / "evidence.json").read_text())
    assert record["official_report"] == {
        "file": "ctrf-report.json",
        "sandbox_path": "/logs/verifier/ctrf-report.json",
        "script_sha256": hashlib.sha256(script.read_bytes()).hexdigest(),
    }
    if write_declared:
        assert result["official_checks"]["rate"] == 0
        assert record["official_items"] == docker.report["results"]["tests"]
        assert json.loads((evidence / "ctrf-report.json").read_text()) == docker.report
    else:
        # A canonical file cannot silently replace the declared official report.
        assert result["official_checks"]["status"] == "NOT_MEASURED"
        assert record["official_items"] == []
        assert (evidence / "ctrf.json").is_file()


@pytest.mark.parametrize(
    "arguments,error",
    [
        ("--ctrf /logs/verifier/../ctrf.json", "path_invalid"),
        ("--ctrf /tmp/ctrf.json", "path_invalid"),
        (
            "--ctrf /logs/verifier/ctrf.json --ctrf /logs/verifier/ctrf-report.json",
            "declarations_ambiguous",
        ),
    ],
)
def test_official_grader_refuses_unsafe_or_ambiguous_report_declarations(
    docker_runner, tmp_path, arguments, error
):
    runner, docker, _lock = docker_runner
    (runner.task_directory / "tests/test.sh").write_text("pytest " + arguments + "\n")
    docker.report = {"results": {"summary": {"tests": 1, "passed": 1}, "tests": []}}
    evidence = tmp_path / "private/official-grader"
    with runner.episode(SkillBundle({"SKILL.md": "candidate"})) as episode:
        episode.grader_evidence_dir = evidence
        runner.close_public(episode)
        result = runner.grade(episode)
    assert result["status"] == "NOT_MEASURED"
    assert result["grader_failure"] == "skillsbench_official_report_" + error
    assert json.loads((evidence / "ctrf.json").read_text()) == docker.report


def test_official_grader_preserves_and_rejects_multiple_report_files(docker_runner, tmp_path):
    runner, docker, _lock = docker_runner
    docker.report = {"results": {"summary": {"tests": 1, "passed": 1}, "tests": []}}
    original = docker.run

    def run(command, **kwargs):
        result = original(command, **kwargs)
        if command[-2:] == ["/bin/bash", "/tests/test.sh"]:
            (docker.logs / "ctrf-report.json").write_bytes((docker.logs / "ctrf.json").read_bytes())
        return result

    docker.run = run
    evidence = tmp_path / "private/official-grader"
    with runner.episode(SkillBundle({"SKILL.md": "candidate"})) as episode:
        episode.grader_evidence_dir = evidence
        runner.close_public(episode)
        result = runner.grade(episode)
    assert result["status"] == "NOT_MEASURED"
    assert result["grader_failure"] == "skillsbench_official_report_files_ambiguous"
    record = json.loads((evidence / "evidence.json").read_text())
    assert {"ctrf.json", "ctrf-report.json"} <= record["files"].keys()
    assert (evidence / "ctrf.json").read_bytes() == (evidence / "ctrf-report.json").read_bytes()


@pytest.mark.parametrize("phase", ["oracle", "evaluate"])
def test_adapter_binds_grade_evidence_to_private_execution_episode(docker_runner, tmp_path, phase):
    runner, docker, _lock = docker_runner
    docker.report = {
        "results": {
            "summary": {"tests": 1, "passed": 0, "failed": 1},
            "tests": [{"name": "hidden_official_check", "status": "failed"}],
        }
    }
    adapter = SkillsBenchAdapter(
        SimpleNamespace(root=tmp_path),
        "travel-planning",
        demo=False,
        artifact_root=tmp_path / "artifacts",
        model_journal_dir=tmp_path / "private-models",
    )
    adapter.runner = runner
    adapter._execute = lambda *_: {}
    bundle = SkillBundle({"SKILL.md": "current skill"})
    result = getattr(adapter, phase)(bundle)
    evidence = list((tmp_path / "private-models/travel-planning").glob("*/official-grader"))
    assert len(evidence) == 1
    record = json.loads((evidence[0] / "evidence.json").read_text())
    assert record["identity"] == {
        "episode_id": evidence[0].parent.name,
        "bundle_hash": bundle.bundle_hash,
        "evaluation": phase == "evaluate",
    }
    assert record["official_items"] == docker.report["results"]["tests"]
    assert "hidden_official_check" not in json.dumps(result)
    assert all(
        "hidden_official_check" not in path.read_text()
        for path in (tmp_path / "artifacts").rglob("*.json")
    )


@pytest.mark.parametrize(
    "diagnostic",
    [
        "ERROR: Could not find a version that satisfies the requirement pytest==8.3.4",
        "ERROR: No matching distribution found for pytest-json-ctrf==0.3.6",
        "ERROR: Could not install packages due to an OSError: No space left on device",
        "error: Failed to download scipy",
        "  × No solution found when resolving dependencies:",
        "error: externally-managed-environment",
        "pytest: error: unrecognized arguments: --ctrf /logs/verifier/ctrf.json",
        "ERROR: file or directory not found: /tests/test_outputs.py",
    ],
)
def test_no_ctrf_fallback_reward_does_not_score_failed_official_grader_setup(
    docker_runner, diagnostic
):
    runner, docker, _lock = docker_runner
    docker.reward = "0"
    docker.diagnostics = diagnostic.encode()
    with runner.episode(SkillBundle({"SKILL.md": "Public task"})) as episode:
        runner.close_public(episode)
        grade = runner.grade(episode)
    assert grade["status"] == "NOT_MEASURED" and grade["reward"] is None
    assert grade["grader_failure"] == "skillsbench_warmup_dependency_or_collection_error"


@pytest.mark.parametrize(
    "frame,dependency,measured",
    [
        ("/app/solution.py", "candidate_typo", True),
        ("/tests/test_outputs.py", "official_dependency", False),
        ("/root/.venv/lib/site-packages/solution.py", "official_dependency", False),
        (None, "unattributed_dependency", False),
    ],
)
def test_grader_import_failures_require_actual_candidate_origin(
    docker_runner, frame, dependency, measured
):
    runner, docker, _lock = docker_runner
    original = runner.source.task

    def public(task_id):
        value = original(task_id)
        return {**value, "opening": value["opening"] + " Write solution.py."}

    runner.source.task = public
    docker.grader_exit, docker.reward = 1, "0"
    docker.report = {"results": {"summary": {"tests": 1, "passed": 0, "errors": 1}, "tests": []}}
    docker.diagnostics = (
        "Traceback (most recent call last):\n"
        + (f'  File "{frame}", line 1, in <module>\n' if frame else "")
        + f"ModuleNotFoundError: No module named '{dependency}'\n"
    ).encode()
    with runner.episode(SkillBundle({"SKILL.md": "Public task"})) as episode:
        runner.close_public(episode)
        grade = runner.grade(episode)
    assert grade["status"] == ("MEASURED" if measured else "NOT_MEASURED")
    if not measured:
        assert grade["reward"] is None
        assert grade["grader_failure"] == "skillsbench_warmup_dependency_or_collection_error"


def test_positive_reward_with_candidate_collection_error_is_contradictory():
    from tau_skill_evolution.skillsbench_runtime import _validate_grader_warmup

    with pytest.raises(RuntimeError, match="reward_contradicts_grader_error"):
        _validate_grader_warmup(
            1,
            "1",
            {"results": {"summary": {"tests": 0}}},
            "ERROR collecting /tests/test_outputs.py\n"
            "ModuleNotFoundError: No module named 'solution'\n",
            ["solution"],
        )


def test_task_defaults_and_legacy_units_match_pinned_harbor(tmp_path):
    from tau_skill_evolution.skillsbench import task_config

    config = tmp_path / "task.toml"
    config.write_text("[environment]\n")
    defaults = task_config(tmp_path)
    assert defaults["environment"] == {
        "build_timeout_sec": 600.0,
        "cpus": 1,
        "memory_mb": 2048,
        "storage_mb": 10240,
        "gpus": 0,
        "allow_internet": True,
    }
    config.write_text('[environment]\nmemory="4G"\nstorage="512M"\nallow_internet=false\n')
    parsed = task_config(tmp_path)["environment"]
    assert parsed["memory_mb"] == 4096 and parsed["storage_mb"] == 512
    assert "memory" not in parsed and "storage" not in parsed and not parsed["allow_internet"]
    config.write_text('[environment]\nmemory="unbounded"\n')
    with pytest.raises(ValueError, match="resource_size"):
        task_config(tmp_path)


def test_compose_uses_only_author_yaml_and_removes_host_credential_bindings(tmp_path):
    import yaml
    from tau_skill_evolution.skillsbench_runtime import _compose_definition

    environment = tmp_path / "environment"
    environment.mkdir()
    (environment / "docker-compose.yml").write_text("services: {website: {image: forbidden}}")
    assert list(_compose_definition(tmp_path)["services"]) == ["main"]
    value = {
        "services": {
            "main": {
                "build": {"context": "${CONTEXT_DIR}"},
                "environment": [
                    "HVAC_SIMULATOR_URL=http://simulator:8080",
                    "GOOGLE_APPLICATION_CREDENTIALS=/root/cloud-key",
                    "CLAUDE_CODE_USE_VERTEX=${CLAUDE_CODE_USE_VERTEX}",
                ],
                "volumes": [
                    "${HOME}/.config/gcloud:/root/key:ro",
                    "/var/run/docker.sock:/docker.sock",
                ],
                "depends_on": {"simulator": {"condition": "service_healthy"}},
                "networks": ["task-net"],
            },
            "simulator": {
                "build": {"context": ".", "dockerfile": "Dockerfile.simulator"},
                "healthcheck": {"test": ["CMD", "true"]},
                "networks": ["task-net"],
            },
        },
        "networks": {"task-net": {"driver": "bridge"}},
    }
    (environment / "docker-compose.yaml").write_text(yaml.safe_dump(value))
    parsed = _compose_definition(tmp_path)
    main = parsed["services"]["main"]
    assert main["environment"] == {"HVAC_SIMULATOR_URL": "http://simulator:8080"}
    assert "volumes" not in main and main["build"]["context"] == "."
    assert parsed["services"]["simulator"]["healthcheck"] == {"test": ["CMD", "true"]}
    value["services"]["main"]["privileged"] = True
    (environment / "docker-compose.yaml").write_text(yaml.safe_dump(value))
    with pytest.raises(RuntimeError, match="host_access"):
        _compose_definition(tmp_path)


def test_docker_episode_reuses_container_and_closes_all_public_tools_before_grade(docker_runner):
    import yaml

    runner, docker, _lock = docker_runner
    bundle = SkillBundle({"SKILL.md": "Current skill", "scripts/main.py": "print('{}')"})
    with runner.episode(bundle) as episode:
        original = runner.container_name
        definition = yaml.safe_load(runner.compose_path.read_text())
        main = definition["services"]["main"]
        assert main["network_mode"] == "bridge"
        assert main["deploy"]["resources"]["limits"]["memory"] == "4096M"
        assert "user" not in main and "entrypoint" not in main and "read_only" not in main
        assert "cap_drop" not in main  # Original root tasks may install dependencies.
        assert {v["target"] for v in main["volumes"]} == {"/bundle", "/logs/verifier"}
        assert main["image"] == _lock["images"]["environment"]["digest"]
        assert not any(str(runner.source.checkout) in v["source"] for v in main["volumes"])
        assert next(v for v in main["volumes"] if v["target"] == "/bundle")["read_only"]
        runner.terminal(episode, "export CUSTOM=1; cd /app; echo state")
        episode.run_skill_script("scripts/main.py", {})
        assert not docker.uploaded
        with pytest.raises(PermissionError, match="before_public_close"):
            runner.grade(episode)
        runner.close_public(episode)
        for invoke in (
            lambda: runner.terminal(episode, "cat /tests/test.sh"),
            lambda: episode.read_skill_file("SKILL.md"),
            lambda: episode.run_skill_script("scripts/main.py", {}),
        ):
            with pytest.raises(PermissionError, match="closed"):
                invoke()
        assert runner.grade(episode)["status"] == "MEASURED"
        grade_command = next(
            c for c, _ in docker.calls if c[-2:] == ["/bin/bash", "/tests/test.sh"]
        )
        assert original in grade_command
        assert not any(c[:2] == ["docker", "run"] for c, _ in docker.calls)
    assert runner.container_name is None and not runner.public_open
    assert "down" in docker.calls[-1][0]


def test_terminal_retains_cwd_exports_with_no_host_environment(docker_runner, tmp_path):
    import subprocess

    runner, docker, _lock = docker_runner
    with runner.episode(SkillBundle({"SKILL.md": "Shell-state probe"})) as episode:
        runner.terminal(episode, "echo probe")
        command, _kwargs = docker.calls[-1]
        wrapper = command[-1].replace("/tmp/tau-public-shell", str(tmp_path / "shell-state"))
        child = tmp_path / "subdir"
        child.mkdir()
        for script in (
            f"cd {child}; export PROBE_VARIABLE=42",
            'printf "%s:%s" "$PWD" "$PROBE_VARIABLE"',
        ):
            result = subprocess.run(
                ["/bin/bash", "-c", wrapper],
                input=script.encode(),
                capture_output=True,
                env={"PATH": "/usr/bin:/bin"},
            )
        assert result.returncode == 0
        assert result.stdout.decode() == f"{child}:42"


def test_live_snapshot_copy_does_not_change_candidate_permissions(docker_runner, tmp_path):
    runner, docker, _lock = docker_runner
    adapter = SkillsBenchAdapter(
        SimpleNamespace(root=EXPERIMENT_ROOT),
        "travel-planning",
        demo=False,
        artifact_root=tmp_path / "artifacts",
    )
    adapter.runner = runner
    with runner.episode(SkillBundle({"SKILL.md": "Snapshot probe"})) as episode:
        output = docker.filesystem["/app"] / "outputs/plan.bin"
        output.parent.mkdir()
        output.write_bytes(b"candidate plan")
        output.chmod(0o400)
        trace = adapter._snapshot(episode)
        assert output.stat().st_mode & 0o777 == 0o400
        assert (
            adapter.runner._public_artifacts(trace).joinpath("app/outputs/plan.bin").read_bytes()
            == b"candidate plan"
        )
        assert not any("chmod -R" in str(c) for c, _ in docker.calls)


def test_original_image_permissions_and_fresh_layer_are_not_rewritten(docker_runner):
    runner, docker, _lock = docker_runner
    entry = runner.source.task(runner.task_id)["public_input_manifest"][0]
    original = runner.task_directory / entry["relative_path"]
    original.chmod(0o440)
    destination = entry["sandbox_paths"][0]
    root = "/" + destination.lstrip("/").split("/", 1)[0]
    relative = destination.removeprefix(root + "/")
    with runner.episode(SkillBundle({"SKILL.md": "Original image layer"})):
        assert (docker.filesystem[root] / relative).stat().st_mode & 0o777 == 0o440
        (docker.filesystem[root] / "episode-only.txt").write_text("candidate output")
    with runner.episode(SkillBundle({"SKILL.md": "Fresh image layer"})):
        assert not (docker.filesystem[root] / "episode-only.txt").exists()
        assert (docker.filesystem[root] / relative).stat().st_mode & 0o777 == 0o440
    assert not any(c[:2] == ["docker", "create"] for c, _ in docker.calls)
    chmod = [c[-1] for c, _ in docker.calls if "chmod -R" in c[-1]]
    assert chmod == ["chmod -R a+rwX -- /logs/verifier"] * 2
    assert original.stat().st_mode & 0o777 == 0o440


def test_snapshot_preserves_missing_output_roots_but_rejects_copy_errors(docker_runner):
    runner, docker, _lock = docker_runner
    original = docker.run

    def missing(command, **kwargs):
        if command[:2] == ["docker", "exec"] and command[-3:-1] == ["snapshot", "/outputs"]:
            return ProcessResult(44)
        return original(command, **kwargs)

    docker.run = missing
    with runner.episode(SkillBundle({"SKILL.md": "Unsolved output"})):
        runner.workspace_roots += ("/outputs",)
        with runner.snapshot_workspace() as roots:
            assert "/outputs" not in roots and "/app" in roots

        def broken(command, **kwargs):
            if command[:2] == ["docker", "cp"]:
                return ProcessResult(1, stderr=b"daemon connection failed")
            return original(command, **kwargs)

        docker.run = broken
        with (
            pytest.raises(RuntimeError, match="snapshot_copy_failed"),
            runner.snapshot_workspace(),
        ):
            pytest.fail("unknown copy error cannot become an empty snapshot")
        assert not docker.archives


def test_snapshot_copies_readonly_directories_and_excludes_nested_private_files(
    docker_runner, tmp_path
):
    runner, docker, _lock = docker_runner
    adapter = SkillsBenchAdapter(
        SimpleNamespace(root=EXPERIMENT_ROOT),
        "travel-planning",
        demo=False,
        artifact_root=tmp_path / "artifacts",
    )
    adapter.runner = runner
    with runner.episode(SkillBundle({"SKILL.md": "Snapshot probe"})) as episode:
        root = docker.filesystem["/app"]
        output = root / "readonly/nested/output.bin"
        output.parent.mkdir(parents=True)
        output.write_bytes(bytes(range(256)) * 1024)
        output.chmod(0o500)
        private = [
            root / "environment/skills/current/SKILL.md",
            root / ".skills/current/SKILL.md",
            root / ".codex/private-response.json",
            root / "nested/grader/test_outputs.py",
        ]
        for file in private:
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text("Private fixture")
        locked = [output.parent, output.parent.parent, private[0].parent.parent]
        for directory in locked:
            directory.chmod(0o555)
        trace = adapter._snapshot(episode)
        public = adapter.runner._public_artifacts(trace)
        assert (public / "app/readonly/nested/output.bin").read_bytes() == output.read_bytes()
        assert (public / "app/readonly/nested/output.bin").stat().st_mode & 0o111
        assert all(directory.stat().st_mode & 0o777 == 0o555 for directory in locked)
        assert output.stat().st_mode & 0o777 == 0o500
        assert not any((public / "app" / file.relative_to(root)).exists() for file in private)
        assert not docker.archives
        assert all(
            not command[2].endswith("/.")
            for command, _ in docker.calls
            if command[:2] == ["docker", "cp"]
        )


@pytest.mark.parametrize("unsafe", ["traversal", "symlink_parent", "special_file", "truncated"])
def test_snapshot_rejects_unsafe_or_invalid_archives_and_cleans_up(docker_runner, unsafe):
    import io
    import tarfile

    runner, docker, _lock = docker_runner
    original = docker.run

    def corrupt(command, **kwargs):
        result = original(command, **kwargs)
        if command[:2] == ["docker", "exec"] and command[-3] == "snapshot":
            archive = docker.archives[command[-1]]
            if unsafe == "truncated":
                archive.write_bytes(b"invalid tar")
            else:
                with tarfile.open(archive, "w") as stream:
                    if unsafe == "symlink_parent":
                        link = tarfile.TarInfo("./parent")
                        link.type, link.linkname = tarfile.SYMTYPE, "safe"
                        stream.addfile(link)
                    member = tarfile.TarInfo(
                        "../escape" if unsafe == "traversal" else "parent/child"
                    )
                    member.type = tarfile.FIFOTYPE if unsafe == "special_file" else tarfile.REGTYPE
                    member.size = 0 if unsafe == "special_file" else 1
                    stream.addfile(member, io.BytesIO(b"x"))
        return result

    docker.run = corrupt
    with runner.episode(SkillBundle({"SKILL.md": "Unsafe snapshot fixture"})):
        with pytest.raises(RuntimeError, match="snapshot_copy_failed"), runner.snapshot_workspace():
            pytest.fail("unsafe archive was admitted")
        assert not docker.archives


def test_snapshot_filters_private_or_external_links_and_keeps_normal_output(docker_runner):
    runner, docker, _lock = docker_runner
    with runner.episode(SkillBundle({"SKILL.md": "Private link fixture"})):
        root = docker.filesystem["/app"]
        (root / "output.txt").write_text("public output")
        for index, target in enumerate(
            ["/private/grader.py", "/bundle/SKILL.md", "/app/environment/skills/current/SKILL.md"]
        ):
            (root / f"private-link-{index}").symlink_to(target)
        with runner.snapshot_workspace() as roots:
            assert (roots["/app"] / "output.txt").read_text() == "public output"
            assert not list(roots["/app"].glob("private-link-*"))
        assert not docker.archives


def test_snapshot_archive_cleanup_failure_is_not_swallowed(docker_runner):
    runner, docker, _lock = docker_runner
    original = docker.run

    def failed_cleanup(command, **kwargs):
        if command[-4:-1] == ["/bin/rm", "-f", "--"]:
            return ProcessResult(1, stderr=b"cannot remove snapshot archive")
        return original(command, **kwargs)

    docker.run = failed_cleanup
    with runner.episode(SkillBundle({"SKILL.md": "Cleanup failure fixture"})):
        with (
            pytest.raises(RuntimeError, match="snapshot_copy_failed:archive_cleanup_failed"),
            runner.snapshot_workspace(),
        ):
            pytest.fail("snapshot archive cleanup failure was swallowed")
        assert len(docker.archives) == 1


def test_preflight_reports_only_missing_declared_environment_names(docker_runner, monkeypatch):
    runner, docker, lock = docker_runner
    monkeypatch.delenv("TAU_REQUIRED_TEST_KEY", raising=False)
    monkeypatch.delenv("TAU_OPTIONAL_PROVIDER", raising=False)
    runner.config["verifier"]["env"] = {"PRIVATE_KEY": "${TAU_REQUIRED_TEST_KEY}"}
    lock["services"]["services"]["main"]["environment"] = {
        "OPTIONAL_PROVIDER": "${TAU_OPTIONAL_PROVIDER}",
        "FALLBACK": "${TAU_UNUSED:-public}",
    }
    report = runner.preflight(validate_source=False)
    assert report["ready"] is False
    assert report["required_environment_missing"] == ["TAU_REQUIRED_TEST_KEY"]
    assert report["compose_optional_environment_missing"] == {"main": ["TAU_OPTIONAL_PROVIDER"]}
    assert not any("up" in c for c, _ in docker.calls)
    monkeypatch.setenv("TAU_REQUIRED_TEST_KEY", "private-declared-value")
    report = runner.preflight(validate_source=False)
    assert report["ready"] is True and report["required_environment_missing"] == []
    assert "private-declared-value" not in json.dumps(report)


@pytest.mark.parametrize(
    "credential",
    [
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "AWS_BEARER_TOKEN_BEDROCK",
        "AWS_BEARER_TOKEN_BEDROCK_FILE",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "AWS_SHARED_CREDENTIALS_FILE",
    ],
)
def test_task_environment_never_resolves_host_provider_credentials(monkeypatch, credential):
    from tau_skill_evolution.container import ContainerUnavailable
    from tau_skill_evolution.skillsbench_runtime import _missing_environment, _resolve_environment

    monkeypatch.setenv(credential, "dummy-provider-secret-not-a-real-key")
    for value in ("${" + credential + "}", "$" + credential, "${" + credential + ":-fallback}"):
        settings = {"RENAMED_TASK_TOKEN": value}
        with pytest.raises(
            ContainerUnavailable, match="reserved_provider_credential:" + credential
        ):
            _resolve_environment(settings, required=False)
        with pytest.raises(
            ContainerUnavailable, match="reserved_provider_credential:" + credential
        ):
            _missing_environment(settings)


@pytest.mark.parametrize("private_grader", [False, True])
def test_preflight_refuses_reserved_credential_targets_without_starting_containers(
    docker_runner, private_grader
):
    runner, docker, lock = docker_runner
    settings = {"OPENAI_API_KEY": "literal-task-provider-secret"}
    if private_grader:
        runner.config["verifier"]["env"] = settings
    else:
        lock["services"]["services"]["main"]["environment"] = settings
    report = runner.preflight(validate_source=False)
    assert not report["ready"]
    assert report["error"] == "skillsbench_reserved_provider_credential:OPENAI_API_KEY"
    assert "literal-task-provider-secret" not in json.dumps(report)
    assert not any("up" in command for command, _ in docker.calls)


def test_codex_main_incompatibility_prevents_ready_without_changing_legacy_admission(
    docker_runner, monkeypatch
):
    runner, _docker, _lock = docker_runner
    monkeypatch.setattr(
        runner,
        "_codex_admission",
        lambda *_args: {
            "ready": False,
            "python3": False,
            "error": "codex_main_runtime_dependency_missing",
        },
    )
    legacy = runner.preflight(validate_source=False)
    assert legacy["ready"] and "author_codex_runtime" not in legacy
    native = runner.preflight(validate_source=False, author_codex={"binary": "codex"})
    assert native["official_grader"] and not native["ready"]
    assert not native["author_codex_runtime"]["ready"]


def test_episode_start_error_still_removes_partial_services(docker_runner):
    runner, docker, _lock = docker_runner
    original = docker.run

    def fail_up(command, **kwargs):
        if command[:2] == ["docker", "compose"] and "up" in command:
            docker.calls.append((command, kwargs))
            return ProcessResult(1)
        return original(command, **kwargs)

    docker.run = fail_up
    with (
        pytest.raises(RuntimeError, match="services_not_ready"),
        runner.episode(SkillBundle({"SKILL.md": "Probe"})),
    ):
        pytest.fail("failed episode cannot be exposed")
    assert runner.container_name is None and not runner.public_open
    assert any("down" in c for c, _ in docker.calls)


@pytest.mark.parametrize(
    "reward,exit_code,failure,diagnostics,ready",
    [
        ("0", 0, None, b"", True),
        ("0", 1, None, b"AssertionError", True),
        (None, 0, None, b"", False),
        ("NaN", 0, None, b"", False),
        ("0", 127, None, b"", False),
        ("1", -9, "timeout", b"", False),
        ("0", 0, None, b"ModuleNotFoundError: No module named 'required_dependency'", False),
    ],
)
def test_fresh_official_admission_runs_grade_in_executed_episode(
    docker_runner, reward, exit_code, failure, diagnostics, ready
):
    runner, docker, _lock = docker_runner
    docker.reward, docker.grader_exit = reward, exit_code
    docker.grader_failure, docker.diagnostics = failure, diagnostics
    result = runner.preflight(validate_source=False)
    assert result["public_snapshot"] is True and result["storage_limit_enforced"] is False
    assert result["main_cpu_memory_limits_configured"] is True
    assert result["resources_scope"] == "main_container"
    assert result["aggregate_limits_enforced"] is result["sidecar_limits_enforced"] is False
    assert result["ready"] is ready and result["official_grader"] is ready
    assert result["official_grader_probe"]["experiment_measurement"] is False
    assert not {"reward", "utility", "official_checks"} & result.keys()
    assert docker.uploaded
    commands = [c for c, _ in docker.calls]
    assert sum(c[:2] == ["docker", "run"] for c in commands) == 1  # independent verifier probe
    assert commands[-1][-3:] == ["down", "--volumes", "--remove-orphans"]


@pytest.fixture
def task_setup_probe(docker_runner):
    runner, docker, _lock = docker_runner
    source = runner.source
    path = runner.task_directory / "environment/project.py"
    path.write_text("import project_dependency\n")
    source.manifest["files"].append(
        {
            "task_id": runner.task_id,
            "relative_path": "environment/project.py",
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "bytes": path.stat().st_size,
        }
    )
    source.manifest["environments"][runner.task_id]["copies"].append(
        {"source": "project.py", "destination": "/app/project.py"}
    )
    (runner.task_directory / "instruction.md").write_text(
        "Please setup the environment for this project. Produce result.json."
    )
    docker.report = {"results": {"summary": {"tests": 0, "passed": 0}, "tests": []}}
    docker.diagnostics = (
        b"________________ ERROR collecting /tests/test_outputs.py ________________\n"
        b"/tests/test_outputs.py:12: in <module>\n"
        b"E   ModuleNotFoundError: No module named 'project_dependency'\n"
    )
    return runner, docker


def test_preflight_defers_public_task_setup_without_weakening_official_grade(task_setup_probe):
    runner, docker = task_setup_probe
    admission = runner.preflight(validate_source=False)
    assert admission["ready"] and admission["official_grader_admission"]
    assert not admission["official_grader"]
    probe = admission["official_grader_probe"]
    assert probe["status"] == "DEFERRED_TASK_SETUP"
    assert not probe["experiment_measurement"]
    assert probe["public_import_evidence"] == {
        "project_dependency": [
            {
                "path": "environment/project.py",
                "sha256": hashlib.sha256(b"import project_dependency\n").hexdigest(),
            }
        ]
    }
    assert "test_outputs" not in json.dumps(admission)
    with runner.episode(SkillBundle({"SKILL.md": "Unfixed public task"})) as episode:
        runner.close_public(episode)
        grade = runner.grade(episode)
    assert grade["status"] == "NOT_MEASURED"
    assert grade["reward"] is grade["utility"] is None
    # Only an actual, fresh successful official execution can produce success.
    docker.diagnostics, docker.reward = b"", "1"
    docker.report = {"results": {"summary": {"tests": 1, "passed": 1}}}
    with runner.episode(SkillBundle({"SKILL.md": "Install public project"})) as episode:
        runner.close_public(episode)
        grade = runner.grade(episode)
    assert grade["status"] == "MEASURED" and grade["utility"] is True


@pytest.mark.parametrize(
    "failure",
    [
        "no_public_setup",
        "unknown_dependency",
        "no_collection_phase",
        "grader_plugin_frame",
        "no_report",
        "invalid_report",
        "missing_report_items",
        "contradictory_reward",
        "contradictory_summary",
        "install_failure",
        "runtime_failure",
        "timeout",
        "tampered_public_input",
        "missing_pytest_driver",
        "missing_ctrf_driver",
        "missing_uv_driver",
    ],
)
def test_task_setup_deferral_does_not_admit_broken_grader_or_unproven_dependency(
    task_setup_probe, failure
):
    runner, docker = task_setup_probe
    if failure == "no_public_setup":
        (runner.task_directory / "instruction.md").write_text("Produce result.json.")
    elif failure == "unknown_dependency":
        docker.diagnostics = docker.diagnostics.replace(b"project_dependency", b"grader_driver")
    elif failure == "no_collection_phase":
        docker.diagnostics = docker.diagnostics.split(b"\n", 1)[1]
    elif failure == "grader_plugin_frame":
        docker.diagnostics = docker.diagnostics.replace(
            b"/tests/test_outputs.py:12", b"/usr/lib/site-packages/pytest/plugin.py:12"
        )
    elif failure == "no_report":
        docker.report = None
    elif failure == "invalid_report":
        docker.report = "malformed reporter data"
    elif failure == "missing_report_items":
        del docker.report["results"]["tests"]
    elif failure == "contradictory_reward":
        docker.reward = "1"
    elif failure == "contradictory_summary":
        docker.report["results"]["summary"]["passed"] = 1
    elif failure == "install_failure":
        docker.diagnostics += b"error: Failed to install pytest\n"
    elif failure == "runtime_failure":
        docker.diagnostics = docker.diagnostics.replace(b"ModuleNotFoundError", b"RuntimeError")
    elif failure == "timeout":
        docker.grader_failure = "timeout"
    elif failure == "tampered_public_input":
        (runner.task_directory / "environment/project.py").write_text("import unrelated\n")
    elif failure == "missing_pytest_driver":
        docker.report = None
        docker.diagnostics = b"python3: No module named pytest\n"
    elif failure == "missing_ctrf_driver":
        docker.report = None
        docker.diagnostics = b"pytest: error: unrecognized arguments: --ctrf\n"
    elif failure == "missing_uv_driver":
        docker.report = None
        docker.diagnostics = b"/tests/test.sh: line 5: uvx: command not found\n"
    report = runner.preflight(validate_source=False)
    assert not report["ready"] and not report["official_grader_admission"]
    assert report["official_grader_probe"]["status"] == "FAILED"


def test_declared_grader_credentials_use_process_environment_not_arguments_or_disk(
    docker_runner, monkeypatch
):
    runner, docker, _lock = docker_runner
    monkeypatch.setenv("TASK_SECRET", "private-grader-secret")
    runner.config["verifier"]["env"] = {
        "TASK_GRADER_TOKEN": "${TASK_SECRET}",
        "REPO_ID": "example/repo",
    }
    with runner.episode(SkillBundle({"SKILL.md": "No grader credentials"})) as episode:
        text = runner.compose_path.read_text()
        runner.close_public(episode)
        runner.grade(episode)
        command, kwargs = next(
            (c, k) for c, k in docker.calls if c[-2:] == ["/bin/bash", "/tests/test.sh"]
        )
        assert kwargs["env"]["TASK_GRADER_TOKEN"] == "private-grader-secret"
        assert kwargs["env"]["REPO_ID"] == "example/repo"
        assert "--env" in command and "TASK_GRADER_TOKEN" in command
        assert "private-grader-secret" not in json.dumps(command) + text
        for c, k in docker.calls:
            if c != command:
                assert "TASK_GRADER_TOKEN" not in k.get("env", {})
    monkeypatch.delenv("TASK_SECRET")
    assert not runner.preflight(validate_source=False)["ready"]


def test_snapshot_covers_nested_manifest_outputs_extensions_and_empty_directories(
    public_source, tmp_path
):
    adapter = SkillsBenchAdapter(
        SimpleNamespace(root=EXPERIMENT_ROOT),
        "3d-scan-calc",
        demo=True,
        artifact_root=tmp_path / "artifacts",
    )
    work = tmp_path / "candidate"
    (work / "outputs/empty").mkdir(parents=True)
    (work / "problem.json").write_text('{"tasks":[{"plan_output":"outputs/task01/plan.bin"}]}')
    (work / "outputs/task01").mkdir()
    (work / "outputs/task01/plan.bin").write_bytes(b"plan")
    (work / "results.npy").write_bytes(b"array")
    (work / "deck.pptx").write_bytes(b"slides")
    (work / "skills").mkdir()
    (work / "skills/SKILL.md").write_text("Private candidate skill copy")
    trace = adapter._snapshot(SimpleNamespace(work=work))
    manifest = json.loads(
        (Path(trace["public_artifacts_dir"]).parent / "snapshot.json").read_text()
    )
    paths = {f["path"] for f in manifest["files"]}
    assert {
        "root/problem.json",
        "root/outputs/task01/plan.bin",
        "root/results.npy",
        "root/deck.pptx",
    } <= paths
    assert "root/outputs/empty" in manifest["directories"]
    assert not any("skills/" in name for name in paths)
    assert adapter.runner._public_artifacts(trace).joinpath("root/outputs/empty").is_dir()
    output = Path(trace["public_artifacts_dir"]) / "root/outputs/task01/plan.bin"
    with pytest.raises(PermissionError):
        output.write_bytes(b"changed")
    output.chmod(0o644)  # Simulate host-side tampering outside the readonly container boundary.
    output.write_bytes(b"changed")
    with pytest.raises(ValueError, match="snapshot_corrupt"):
        adapter.runner._public_artifacts(trace)


def test_public_sessions_use_task_image_and_only_public_readonly_artifacts(docker_runner, tmp_path):
    from tau_skill_evolution.skillsbench import SkillsBenchAdapter

    runner, docker, lock = docker_runner
    adapter = SkillsBenchAdapter(
        SimpleNamespace(root=EXPERIMENT_ROOT),
        "travel-planning",
        demo=False,
        artifact_root=tmp_path / "artifacts",
    )
    adapter.runner = runner
    source = tmp_path / "public-output"
    source.mkdir()
    (source / "result.bin").write_bytes(b"actual public candidate output")
    trace = adapter._seal_public_workspace({"/app": source})
    tests = {"tests/test_public.py": "def test_public():\n    assert True\n"}
    with runner.public_verifier_session({}, {}, trace, files=tests, readonly_tests=True) as session:
        assert session.files() == tests
        session.terminal("ls /app; test ! -e /bundle/SKILL.md; test ! -e /tests/test.sh")
    command = next(c for c, _ in docker.calls if c[:2] == ["docker", "run"])
    assert lock["images"]["runtime"]["digest"] in command
    assert "--read-only" in command and command[command.index("--network") + 1] == "none"
    assert any("dst=/app,readonly" in arg for arg in command)
    assert any("dst=/work,readonly" in arg for arg in command)
    assert any("dst=/work/scratch" in arg and "readonly" not in arg for arg in command)
    assert not any("dst=/work/tests" in arg for arg in command)
    assert not any(str(runner.task_directory / "tests") in arg for arg in command)


@pytest.mark.parametrize("isolated", [False, True])
def test_docker_python_script_wrapper_preserves_harness_arguments(
    docker_runner, tmp_path, isolated
):
    """Execute only the generated Python driver, not task code or a host fallback."""
    import subprocess
    import sys

    runner, _docker, _lock = docker_runner
    script = tmp_path / "argv_probe.py"
    script.write_text("import json,sys; print(json.dumps(sys.argv))")
    testroot = "/work/tests"
    arguments = ["python", *(["-I"] if isolated else []), str(script), testroot]
    command = runner._docker_command(tmp_path, tmp_path, arguments, grader=False)
    driver = command[command.index("-c") + 1 :]
    result = subprocess.run(
        [sys.executable, "-I", "-c", *driver],
        capture_output=True,
        check=True,
        env={"PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert json.loads(result.stdout) == [str(script), testroot]


@pytest.mark.parametrize("separate_lock", [False, True])
@pytest.mark.parametrize("missing_python", [False, True])
def test_docker_preparation_restores_task_user_and_never_embeds_official_tests(
    public_source, monkeypatch, separate_lock, missing_python
):
    from tau_skill_evolution import skillsbench_runtime as runtime

    builds = []
    monkeypatch.setattr(runtime.shutil, "which", lambda _: "docker")
    monkeypatch.setattr(
        runtime, "_verifier_python_mode", lambda *_: "standalone" if missing_python else "native"
    )
    monkeypatch.setattr(
        runtime, "_public_python_path", lambda *_: None if missing_python else "/usr/bin/python3"
    )

    def run(command, **_kwargs):
        if "build" in command:
            assert _kwargs["stdout"] is runtime.sys.stderr
            recipe = (
                Path(command[command.index("-f") + 1])
                if "-f" in command
                else Path(command[-1]) / "Dockerfile"
            )
            stage = Path(command[-1])
            builds.append(
                (
                    recipe.read_text(),
                    [p.relative_to(stage).as_posix() for p in stage.rglob("*") if p.is_file()],
                )
            )
        return SimpleNamespace(returncode=0)

    def output(command, **_kwargs):
        if "inspect" in command:
            return json.dumps(
                [
                    {
                        "Id": "sha256:"
                        + (
                            "c"
                            if "public-main" in command[-1]
                            else "b"
                            if "runtime" in command[-1]
                            else "a"
                        )
                        * 64,
                        "Config": {
                            "Env": ["PATH=/task/bin:/usr/bin:/bin"],
                            "User": "node",
                            "WorkingDir": "/app",
                            "Entrypoint": ["/task/start.sh"],
                        },
                    }
                ]
            ).encode()
        return b"[3,11,14]"

    monkeypatch.setattr(runtime.subprocess, "run", run)
    monkeypatch.setattr(runtime.subprocess, "check_output", output)
    (public_source.root / "runtime").mkdir()
    (public_source.root / "runtime/skillsbench-verifier-requirements.lock").write_text(
        "pytest==8.4.1 --hash=sha256:" + "c" * 64
    )
    old_lock = public_source.root / "runtime/skillsbench-docker-travel-planning-lock.json"
    selected = Path("runtime/skillsbench-docker-travel-planning-v2-test-lock.json")
    if separate_lock:
        old_lock.write_bytes(b"historical runtime lock")
    result = runtime.prepare_docker(
        public_source.root,
        "travel-planning",
        runtime_lock_path=selected if separate_lock else None,
    )
    written = public_source.root / selected if separate_lock else old_lock
    assert Path(result["runtime_lock"]) == written
    assert json.loads(written.read_text())["runtime_schema"] == "skillsbench.episode.v2"
    if separate_lock:
        assert old_lock.read_bytes() == b"historical runtime lock"
    assert result["prepared"] and not result["ready"] and result["requires_fresh_preflight"]
    assert result["runtime_schema"] == "skillsbench.episode.v2"
    assert set(result["images"]) == {"environment", "runtime"}
    assert result["images"]["environment"]["user"] == "node"
    assert result["images"]["environment"]["entrypoint"] == ["/task/start.sh"]
    assert builds[1][0].startswith("FROM tau-skillsbench-travel-planning-main:4380d4bff673\n")
    assert builds[1][0].endswith("USER node\n")
    assert result["service_images"]["main"]["public_python_version"] == [3, 11, 14]
    if missing_python:
        assert result["service_images"]["main"]["public_python"] == "/.tau-python/python3"
        assert result["service_images"]["main"]["source_digest"] == "sha256:" + "a" * 64
        assert result["images"]["environment"]["digest"] == "sha256:" + "a" * 64
        assert builds[2] == (
            "FROM tau-skillsbench-travel-planning-main:4380d4bff673\n"
            "COPY --from=tau-skillsbench-travel-planning-runtime:4380d4bff673 "
            "/.tau-python /.tau-python\n",
            ["Dockerfile"],
        )
        assert "/.tau-verifier" not in builds[2][0]
    else:
        assert result["service_images"]["main"]["public_python"] == "/usr/bin/python3"
        assert len(builds) == 2
    assert not any("tests/" in file or "warmup" in file for _, files in builds for file in files)
    assert "reward" not in result and "utility" not in result
    original_bytes, build_count = written.read_bytes(), len(builds)
    monkeypatch.setattr(
        runtime.BoundedProcessTransport,
        "run",
        lambda _self, command, **_kwargs: ProcessResult(
            0, stdout=json.dumps([{"Id": command[-1]}]).encode()
        ),
    )
    reused = runtime.prepare_docker(
        public_source.root,
        "travel-planning",
        runtime_lock_path=selected if separate_lock else None,
    )
    assert reused["prepared"] and reused["reused"] and not reused["ready"]
    assert reused["requires_fresh_preflight"]
    assert written.read_bytes() == original_bytes and len(builds) == build_count


@pytest.mark.parametrize("drift_stage", ["before", "after"])
def test_docker_preparation_rejects_base_tag_drift_without_sealing_lock(
    public_source, monkeypatch, drift_stage
):
    from tau_skill_evolution import skillsbench_runtime as runtime

    monkeypatch.setattr(runtime.shutil, "which", lambda _: "docker")
    monkeypatch.setattr(runtime, "_verifier_python_mode", lambda *_: "native")
    monkeypatch.setattr(runtime, "_public_python_path", lambda *_: "/usr/bin/python3")
    builds, inspections = [], []

    def run(command, **_kwargs):
        if "build" in command:
            builds.append(list(command))
        return SimpleNamespace(returncode=0)

    def output(command, **_kwargs):
        assert command[1:3] == ["image", "inspect"]
        inspections.append(list(command))
        drifting = len(inspections) >= (2 if drift_stage == "before" else 3)
        return json.dumps(
            [{"Id": "sha256:" + ("b" if drifting else "a") * 64, "Config": {}}]
        ).encode()

    monkeypatch.setattr(runtime.subprocess, "run", run)
    monkeypatch.setattr(runtime.subprocess, "check_output", output)
    directory = public_source.root / "runtime"
    directory.mkdir()
    (directory / "skillsbench-verifier-requirements.lock").write_text("locked dependencies")
    historical = directory / "skillsbench-docker-travel-planning-lock.json"
    historical.write_bytes(b"historical locked image")
    selected = directory / "skillsbench-docker-travel-planning-v2-test-lock.json"
    with pytest.raises(RuntimeError, match="skillsbench_build_base_image_changed"):
        runtime.prepare_docker(public_source.root, "travel-planning", runtime_lock_path=selected)
    assert len(builds) == (1 if drift_stage == "before" else 2)
    assert all(
        command[-1] == "tau-skillsbench-travel-planning-main:4380d4bff673"
        for command in inspections
    )
    assert not selected.exists()
    assert historical.read_bytes() == b"historical locked image"


@pytest.mark.parametrize("companion_exit", [0, 127])
def test_codex_admission_uses_public_interpreter_and_checks_companion(
    docker_runner, monkeypatch, companion_exit
):
    from tau_skill_evolution import codex_runtime
    from tau_skill_evolution.container import ProgramResult

    runner, docker, _lock = docker_runner
    runner._docker_lock()["service_images"]["main"]["public_python"] = "/.tau-python/python3"
    monkeypatch.setattr(
        codex_runtime,
        "codex_identity",
        lambda _settings: {
            "binary": "/host/codex",
            "cli_version": "codex-cli 0.120.0",
            "cli_sha256": "a" * 64,
            "code_mode_host_binary": "/host/codex-code-mode-host",
            "code_mode_host_sha256": "b" * 64,
        },
    )
    probes = []

    def probe(_package, _work, command):
        probes.append(command)
        if "python=false" in command[-1]:
            return ProgramResult(0, {"python3": True, "setsid": True}, "", None)
        assert command[:3] == ["/.tau-python/python3", "-I", "-c"]
        compile(command[-1], "probe", "exec")
        if "--version" in command[-1]:
            return ProgramResult(0, {"return_code": 0, "version": "codex-cli 0.120.0"}, "", None)
        assert "--help" in command[-1]
        return ProgramResult(0, {"return_code": companion_exit}, "", None)

    monkeypatch.setattr(runner, "_run", probe)
    with runner.episode(None) as episode:
        result = runner._codex_admission(episode, {})
    assert result["public_python"] == "/.tau-python/python3"
    assert result["native_cli_abi"]
    assert result["code_mode_host_abi"] is (companion_exit == 0)
    assert result["ready"] is (companion_exit == 0)
    assert any(
        command[:3] == ["docker", "cp", "/host/codex-code-mode-host"]
        and command[-1].endswith(":/tmp/codex-code-mode-host")
        for command, _kwargs in docker.calls
    )
    assert len(probes) == 3


@pytest.mark.parametrize(
    "mismatch,error",
    [
        ("runtime_tag", "skillsbench_build_runtime_image_changed"),
        ("configuration", "skillsbench_public_image_configuration_changed"),
        ("version", "skillsbench_public_python_version_invalid"),
    ],
)
def test_public_main_derivative_rejects_drift_without_sealing_lock(
    public_source, monkeypatch, mismatch, error
):
    from tau_skill_evolution import skillsbench_runtime as runtime

    monkeypatch.setattr(runtime.shutil, "which", lambda _: "docker")
    monkeypatch.setattr(runtime, "_public_python_path", lambda *_: None)
    monkeypatch.setattr(runtime, "_verifier_python_mode", lambda *_: "standalone")
    monkeypatch.setattr(
        runtime.subprocess, "run", lambda *_args, **_kwargs: SimpleNamespace(returncode=0)
    )
    runtime_inspections = 0

    def output(command, **_kwargs):
        nonlocal runtime_inspections
        if "inspect" not in command:
            return (
                b"[2,7,18]"
                if mismatch == "version" and any("public-main" in argument for argument in command)
                else b"[3,11,14]"
            )
        target = command[-1]
        config = {
            "Env": ["PATH=/task/bin"],
            "User": "node",
            "WorkingDir": "/app",
            "Entrypoint": ["/task/start"],
        }
        digest = "a"
        if "runtime" in target:
            runtime_inspections += 1
            digest = "d" if mismatch == "runtime_tag" and runtime_inspections > 1 else "b"
        if "public-main" in target:
            digest = "c"
            if mismatch == "configuration":
                config["Env"] = ["PATH=/changed"]
        return json.dumps([{"Id": "sha256:" + digest * 64, "Config": config}]).encode()

    monkeypatch.setattr(runtime.subprocess, "check_output", output)
    directory = public_source.root / "runtime"
    directory.mkdir()
    (directory / "skillsbench-verifier-requirements.lock").write_text("locked dependencies")
    selected = directory / "skillsbench-docker-travel-planning-v4-test-lock.json"
    with pytest.raises(RuntimeError, match=error):
        runtime.prepare_docker(public_source.root, "travel-planning", runtime_lock_path=selected)
    assert not selected.exists()


@pytest.mark.parametrize("separate_lock", [False, True])
def test_old_baseline_grader_lock_cannot_admit_new_episode_runtime(
    public_source, tmp_path, separate_lock
):
    from tau_skill_evolution.skillsbench_runtime import _compose_definition

    selected = Path("runtime/skillsbench-docker-travel-planning-v2-test-lock.json")
    runner = SkillsBenchRunner(
        tmp_path,
        "travel-planning",
        demo=False,
        runtime_lock_path=selected if separate_lock else None,
    )
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    dependency = runtime / "skillsbench-verifier-requirements.lock"
    dependency.write_text("dependency lock")
    tests = runner.task_directory / "tests"
    value = {
        "runtime_schema": "skillsbench.episode.v2",
        "commit": "4380d4bff673dd6e1d58e5babeb2aaa0fe527119",
        "task_id": runner.task_id,
        "dockerfile_sha256": hashlib.sha256(
            (runner.task_directory / "environment/Dockerfile").read_bytes()
        ).hexdigest(),
        "compose_sha256": None,
        "task_config_hash": _json_hash(runner.config),
        "public_manifest_hash": public_source.manifest["manifest_hash"],
        "dependency_hash": hashlib.sha256(dependency.read_bytes()).hexdigest(),
        "resources": runner.config["environment"],
        "layout": public_source.manifest["environments"][runner.task_id],
        "services": _compose_definition(runner.task_directory),
        "grader_tests_hash": _json_hash(
            {
                p.relative_to(tests).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in tests.rglob("*")
                if p.is_file()
            }
        ),
        "images": {
            "environment": {"digest": "sha256:" + "a" * 64},
            "runtime": {"digest": "sha256:" + "b" * 64, "verifier_python": "python3"},
        },
        "service_images": {"main": {"digest": "sha256:" + "a" * 64}},
        "verifier_python_mode": "native",
    }
    path = runner.runtime_lock_path
    runner.transport = SimpleNamespace(
        run=lambda command, **_kwargs: ProcessResult(
            0, stdout=json.dumps([{"Id": command[-1]}]).encode()
        )
    )
    path.write_text(json.dumps(value))
    assert runner._docker_lock()["runtime_schema"] == "skillsbench.episode.v2"
    runner.transport = SimpleNamespace(
        run=lambda *_args, **_kwargs: ProcessResult(
            0, stdout=json.dumps([{"Id": "sha256:" + "f" * 64}]).encode()
        )
    )
    with pytest.raises(RuntimeError, match="locked_image_identity_invalid"):
        runner._docker_lock()
    value["task_id"] = "3d-scan-calc"
    path.write_text(json.dumps(value))
    with pytest.raises(RuntimeError, match="runtime_not_prepared"):
        runner._docker_lock()
    value["task_id"] = runner.task_id
    value.pop("runtime_schema")
    value["images"]["grader"] = {"digest": "sha256:" + "c" * 64}
    path.write_text(json.dumps(value))
    with pytest.raises(RuntimeError, match="runtime_not_prepared"):
        runner._docker_lock()


@pytest.mark.parametrize(
    "reason", ["skillsbench_episode_runtime_not_prepared", "skillsbench_locked_image_missing"]
)
def test_existing_invalid_runtime_lock_is_preserved_without_automatic_rebuild(
    public_source, monkeypatch, reason
):
    from tau_skill_evolution import skillsbench_runtime as runtime
    from tau_skill_evolution.container import ContainerUnavailable

    directory = public_source.root / "runtime"
    directory.mkdir()
    lock = directory / "skillsbench-docker-travel-planning-v4-lock.json"
    original = b'{"sealed": "original invalid or missing-image runtime"}\n'
    lock.write_bytes(original)
    monkeypatch.setattr(runtime.shutil, "which", lambda _: "docker")

    def command(command, **_kwargs):
        assert command == ["docker", "info"]
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(runtime.subprocess, "run", command)

    def unavailable(_self):
        raise ContainerUnavailable(reason)

    monkeypatch.setattr(runtime.SkillsBenchRunner, "_docker_lock", unavailable)
    with pytest.raises(ContainerUnavailable, match=reason):
        runtime.prepare_docker(public_source.root, "travel-planning", runtime_lock_path=lock)
    assert lock.read_bytes() == original


@pytest.mark.parametrize(
    "selected",
    [
        None,
        Path("runtime/skillsbench-bubblewrap-lock.json"),
        Path("runtime/skillsbench-workspace-lab-unit-harmonization-lock.json"),
    ],
)
def test_workspace_configuration_keeps_default_docker_lock(public_source, selected):
    runner = SkillsBenchRunner(
        public_source.root, "3d-scan-calc", demo=False, runtime_lock_path=selected
    )
    assert runner.runtime_lock_path == (
        public_source.root / "runtime/skillsbench-docker-3d-scan-calc-lock.json"
    )


@pytest.mark.parametrize("name", ["skillsbench-bubblewrap-lock.json", "unbound-lock.json"])
def test_explicit_docker_preparation_never_falls_back_to_a_historical_lock(
    public_source, monkeypatch, name
):
    from tau_skill_evolution import skillsbench_runtime as runtime

    def unexpected(*_args, **_kwargs):
        pytest.fail("An invalid explicit output must fail before inspecting or building images.")

    monkeypatch.setattr(runtime.subprocess, "run", unexpected)
    with pytest.raises(ValueError, match="skillsbench_docker_lock_path_invalid"):
        runtime.prepare_docker(
            public_source.root, "3d-scan-calc", runtime_lock_path=Path("runtime") / name
        )


def test_separate_docker_lock_is_bound_into_run_identity(public_source, monkeypatch, tmp_path):
    from tau_skill_evolution.spec import ExperimentSpec

    monkeypatch.setattr(ExperimentSpec, "root", property(lambda _: public_source.root))
    lock = public_source.root / "runtime/skillsbench-docker-3d-scan-calc-v2-test-lock.json"
    lock.parent.mkdir()
    lock.write_text("first locked environment")
    config = tmp_path / "config.yaml"
    config.write_text("test identity fixture")
    spec = ExperimentSpec(
        config,
        {
            "experiment": "skillsbench",
            "schema_version": "skillsbench.skill-evolution.v2",
            "source": {
                "upstream_checkout": "data/upstream/coevo-skills",
                "corpus_manifest": "data/skillsbench/public-manifest.json",
                "runtime_lock": lock.relative_to(public_source.root).as_posix(),
            },
            "provider": {
                "model": "openai.gpt-5.5",
                "transport": "bedrock-responses",
                "region": "us-east-1",
            },
        },
    )
    initial = spec.identity
    key = lock.relative_to(public_source.root).as_posix()
    assert initial["files"][key] == hashlib.sha256(lock.read_bytes()).hexdigest()
    lock.write_text("changed locked environment")
    assert initial["identity_hash"] != spec.identity["identity_hash"]


@pytest.mark.parametrize("phase", ["oracle", "evaluate"])
def test_adapter_seals_public_state_then_permanently_closes_tools_before_grade(
    docker_runner, tmp_path, phase
):
    runner, _docker, _lock = docker_runner
    events = []
    adapter = SkillsBenchAdapter(
        SimpleNamespace(root=EXPERIMENT_ROOT),
        "travel-planning",
        demo=False,
        artifact_root=tmp_path / "artifacts",
    )
    adapter.runner = runner
    adapter._execute = lambda *_: events.append("execute") or {}
    original_snapshot, original_close, original_grade = (
        adapter._snapshot,
        runner.close_public,
        runner.grade,
    )

    def snapshot(episode):
        events.append("snapshot")
        assert runner.public_open
        return original_snapshot(episode)

    def close(episode):
        assert events[-1] == "snapshot"
        events.append("close")
        original_close(episode)

    def grade(episode):
        assert events[-1] == "close" and not runner.public_open
        events.append("grade")
        return original_grade(episode)

    adapter._snapshot, runner.close_public, runner.grade = snapshot, close, grade
    result = getattr(adapter, phase)(SkillBundle({"SKILL.md": "Only current candidate"}))
    assert events == ["execute", "snapshot", "close", "grade"]
    assert result is False if phase == "oracle" else result["status"] == "MEASURED"


def test_workspace_preparation_does_not_relabel_unmigrated_tasks(public_source):
    from tau_skill_evolution.skillsbench_runtime import workspace_preparation

    supported = workspace_preparation(public_source.root, "3d-scan-calc")
    assert supported["supported"] and not supported["prepared"] and not supported["ready"]
    unsupported = workspace_preparation(public_source.root, "travel-planning")
    assert not unsupported["supported"] and not unsupported["ready"]
    assert unsupported["reason"] == "skillsbench_workspace_task_environment_not_prepared"
    environment = public_source.checkout / "tasks/travel-planning/environment"
    (environment / "docker-compose.yaml").write_text("services: {main: {}, simulator: {}}")
    assert (
        workspace_preparation(public_source.root, "travel-planning")["reason"]
        == "skillsbench_workspace_sidecars_not_prepared"
    )


def test_workspace_command_keeps_host_keys_and_grader_outside_public_mounts(
    public_source, tmp_path
):
    runner = SkillsBenchRunner(public_source.root, "3d-scan-calc", demo=False, runtime="workspace")
    lock = SimpleNamespace(rootfs=tmp_path / "sealed-rootfs")
    runner._lock = lambda: lock
    command = runner._command(tmp_path / "bundle", tmp_path / "episode", ["python", "script.py"])
    assert "docker" not in command and "--unshare-all" in command and "--clearenv" in command
    assert str(runner.task_directory / "tests") not in command
    assert str(runner.task_directory / "environment/scan_data.stl") not in command
    assert "/root/.venv/bin/python" in command
    assert command[command.index("--bind") + 1 : command.index("--bind") + 3] == [
        str(tmp_path / "episode"),
        "/root",
    ]
    private = runner._command(
        tmp_path / "empty", tmp_path / "episode", ["/bin/bash", "/tests/test.sh"], grader=True
    )
    assert str(runner.task_directory / "tests") in private


def test_workspace_unsupported_task_fails_before_dispatching_any_runtime(public_source):
    calls = []
    runner = SkillsBenchRunner(
        public_source.root,
        "travel-planning",
        demo=False,
        runtime="workspace",
        transport=SimpleNamespace(run=lambda *args, **kwargs: calls.append(args)),
    )
    result = runner.preflight(validate_source=False)
    assert not result["ready"] and not result["demo_only"]
    assert result["error"] == "skillsbench_workspace_task_environment_not_prepared"
    assert not calls


@pytest.mark.parametrize(
    "destination",
    [
        "/root/../tests/test.sh",
        "/root/data/../../key.env",
        "/root/./scan_data.stl",
        "/root//scan_data.stl",
        "/root/",
        "/root/\\scan_data.stl",
        "/root/\x00scan_data.stl",
        "/root-other/scan_data.stl",
        "/app/scan_data.stl",
    ],
)
def test_authoring_public_input_mount_rejects_noncanonical_destinations(
    public_source, tmp_path, monkeypatch, destination
):
    runner = SkillsBenchRunner(public_source.root, "3d-scan-calc", demo=False, runtime="workspace")
    runner._lock = lambda: SimpleNamespace(rootfs=tmp_path / "sealed-rootfs")
    runner.public_workspace_mode = True
    monkeypatch.setattr(
        runner.source,
        "task",
        lambda _: {
            "public_input_manifest": [
                {"relative_path": "environment/scan_data.stl", "sandbox_paths": [destination]}
            ]
        },
    )
    with pytest.raises(
        (ValueError, RuntimeError), match="unsafe_relative_path|layout_not_prepared"
    ):
        runner._command(tmp_path / "bundle", tmp_path / "work", ["python", "-c", "pass"])


def test_enterprise_workspace_descriptor_reuses_historical_runtime_without_mutating_it(
    public_source,
):
    from tau_skill_evolution.skillsbench_runtime import (
        SkillsBenchRuntimeLock,
        prepare_workspace_runtime,
        workspace_preparation,
    )

    root = public_source.root
    runtime = root / "runtime"
    runtime.mkdir()
    rootfs = root / "data/skillsbench/rootfs"
    rootfs.mkdir()
    requirements = runtime / "skillsbench-requirements.lock"
    requirements.write_text("# Empty fixture; real integration validates installed dependencies.\n")
    original = runtime / "skillsbench-bubblewrap-lock.json"
    original.write_text(
        json.dumps(
            {
                "rootfs": "../data/skillsbench/rootfs",
                "files": {},
                "symlinks": {},
                "python_version": [3, 11, 14],
                "dependency_hash": hashlib.sha256(requirements.read_bytes()).hexdigest(),
                "dependencies": {},
                "task_ids": ["3d-scan-calc"],
                "demo_only": True,
                "aggregate_limits_enforced": False,
            }
        )
    )
    original_bytes = original.read_bytes()
    assert not workspace_preparation(root, "enterprise-information-search")["prepared"]
    prepared = prepare_workspace_runtime(root, "enterprise-information-search")
    selected = Path(prepared["runtime_lock"])
    descriptor_bytes = selected.read_bytes()
    assert prepared["prepared"] and not prepared["ready"]
    assert original.read_bytes() == original_bytes
    descriptor = json.loads(descriptor_bytes)
    assert "files" not in descriptor and "rootfs" not in descriptor
    assert descriptor["base_runtime_lock_sha256"] == hashlib.sha256(original_bytes).hexdigest()
    assert not descriptor["author_environment_equivalent"]
    assert SkillsBenchRuntimeLock.from_file(selected).rootfs == rootfs
    assert prepare_workspace_runtime(root, "enterprise-information-search")["prepared"]
    assert selected.read_bytes() == descriptor_bytes and original.read_bytes() == original_bytes
    assert not workspace_preparation(
        root, "enterprise-information-search", runtime_lock_path=original
    )["prepared"]

    spec = SimpleNamespace(root=root, values={"source": {"runtime_lock": str(selected)}})
    adapter = SkillsBenchAdapter(
        spec, "enterprise-information-search", demo=False, runtime="workspace"
    )
    assert adapter.runner.runtime_lock_path == selected
    assert adapter.runner._lock().rootfs == rootfs
    public_input = (
        public_source.checkout / "tasks/enterprise-information-search/environment/question.txt"
    )
    public_bytes = public_input.read_bytes()
    public_input.write_bytes(public_bytes + b"tampered")
    with pytest.raises(RuntimeError, match="public_input_hash_mismatch"):
        adapter.runner._lock().validate("enterprise-information-search")
    public_input.write_bytes(public_bytes)
    selected.write_text(json.dumps({**descriptor, "files": {}}))
    with pytest.raises(RuntimeError, match="descriptor_invalid"):
        SkillsBenchRuntimeLock.from_file(selected)
    selected.write_bytes(descriptor_bytes)
    original.write_bytes(original_bytes + b"\n")
    with pytest.raises(RuntimeError, match="base_lock_mismatch"):
        SkillsBenchRuntimeLock.from_file(selected)


def test_enterprise_workspace_preparation_rejects_unmigrated_layout(public_source):
    from tau_skill_evolution.skillsbench_runtime import _workspace_task_binding

    public_source.manifest["environments"]["enterprise-information-search"]["workdir"] = "/app"
    with pytest.raises(RuntimeError, match="layout_not_prepared"):
        _workspace_task_binding(public_source.root, "enterprise-information-search")


def test_enterprise_bootstrap_changes_only_pinned_installation_and_launcher(public_source):
    from tau_skill_evolution.skillsbench_runtime import _enterprise_grader_script

    original, adapted = _enterprise_grader_script(public_source.root)
    scoring = "--ctrf /logs/verifier/ctrf.json /tests/test_outputs.py -rA\n"
    assert original.split(scoring, 1)[1] == adapted.split(scoring, 1)[1]
    assert "/usr/local/bin/python -I -m pytest " + scoring in adapted
    assert "apt-get update" not in adapted and "uvx" not in adapted
    bootstrap = public_source.checkout / "tasks/enterprise-information-search/tests/test.sh"
    bootstrap.write_text(original.replace("test_outputs.py", "different_tests.py"))
    with pytest.raises(RuntimeError, match="grader_recipe_mismatch"):
        _enterprise_grader_script(public_source.root)


@pytest.mark.parametrize(
    "name", ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "ELEVENLABS_API_KEY"]
)
@pytest.mark.parametrize("placeholder", ["${%s}", "$%s", "${%s:-}"])
def test_task_api_credentials_require_a_separate_per_task_host_value(
    monkeypatch, name, placeholder
):
    from tau_skill_evolution.container import ContainerUnavailable
    from tau_skill_evolution.skillsbench_runtime import _missing_environment, _resolve_environment

    scoped = "SKILLSBENCH_TASK_PG_ESSAY_TO_AUDIOBOOK_" + name
    monkeypatch.setenv(name, "dummy-model-provider-credential")
    monkeypatch.delenv(scoped, raising=False)
    declared = {name: placeholder % name}
    assert _missing_environment(declared, task_id="pg-essay-to-audiobook") == [scoped]
    assert _resolve_environment(declared, required=False, task_id="pg-essay-to-audiobook") == {
        name: ""
    }
    with pytest.raises(ContainerUnavailable, match="required_environment_missing:" + scoped):
        _resolve_environment(declared, task_id="pg-essay-to-audiobook")
    monkeypatch.setenv(scoped, "dummy-task-specific-credential")
    assert _resolve_environment(declared, task_id="pg-essay-to-audiobook") == {
        name: "dummy-task-specific-credential"
    }
    assert _resolve_environment(declared, required=False, task_id="another-task") == {name: ""}
    for forbidden in (
        {name: "dummy-literal-credential"},
        {name: "${AWS_BEARER_TOKEN_BEDROCK}"},
        {"RENAMED_TASK_TOKEN": "${" + name + "}"},
    ):
        with pytest.raises(ContainerUnavailable, match="reserved_provider_credential"):
            _resolve_environment(forbidden, task_id="pg-essay-to-audiobook")


def test_task_credentials_and_toml_environment_keep_phase_and_disk_boundaries(
    docker_runner, monkeypatch
):
    runner, docker, _lock = docker_runner
    scoped = "SKILLSBENCH_TASK_TRAVEL_PLANNING_OPENAI_API_KEY"
    secret = "dummy-task-specific-openai-value"
    monkeypatch.setenv("OPENAI_API_KEY", "dummy-model-secret")
    monkeypatch.setenv(scoped, secret)
    runner.config["environment"]["env"] = {"PUBLIC_SETTING": "from-task-toml"}
    runner.config["verifier"]["env"] = {"OPENAI_API_KEY": "${OPENAI_API_KEY}"}
    with runner.episode(SkillBundle({"SKILL.md": "Task environment boundary fixture"})) as episode:
        compose = yaml.safe_load(runner.compose_path.read_text())
        public_env = compose["services"]["main"]["environment"]
        assert public_env["PUBLIC_SETTING"] == "${TAU_SB_ENV_main_PUBLIC_SETTING}"
        assert "OPENAI_API_KEY" not in public_env
        assert not any(secret in json.dumps(c) for c, _ in docker.calls)
        assert all(secret not in k.get("env", {}).values() for _, k in docker.calls)
        runner.close_public(episode)
        runner.grade(episode)
        grade_command, settings = next(
            (c, k) for c, k in docker.calls if c[-2:] == ["/bin/bash", "/tests/test.sh"]
        )
        assert settings["env"]["OPENAI_API_KEY"] == secret
        assert "dummy-model-secret" not in settings["env"].values()
        assert secret not in json.dumps(grade_command) + runner.compose_path.read_text()


def test_optional_task_api_keys_are_task_scoped_and_reported_without_values(
    docker_runner, monkeypatch
):
    runner, docker, _lock = docker_runner
    scoped = "SKILLSBENCH_TASK_TRAVEL_PLANNING_ANTHROPIC_API_KEY"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy-host-model-credential")
    monkeypatch.delenv(scoped, raising=False)
    runner.config["environment"]["env"] = {"ANTHROPIC_API_KEY": "${ANTHROPIC_API_KEY}"}
    report = runner.preflight(validate_source=False)
    assert report["ready"]
    assert report["compose_optional_environment_missing"] == {"main": [scoped]}
    assert "dummy-host-model-credential" not in json.dumps(report)
    startup = next(k for c, k in docker.calls if "up" in c)
    assert startup["env"]["TAU_SB_ENV_main_ANTHROPIC_API_KEY"] == ""


def test_per_task_docker_lock_template_expands_and_binds_missing_and_present_locks(
    public_source, monkeypatch, tmp_path
):
    from tau_skill_evolution.spec import ExperimentSpec

    template = "runtime/skillsbench-docker-{task_id}-v4-lock.json"
    runner = SkillsBenchRunner(
        public_source.root, "3d-scan-calc", demo=False, runtime_lock_path=Path(template)
    )
    assert runner.runtime_lock_path == (
        public_source.root / "runtime/skillsbench-docker-3d-scan-calc-v4-lock.json"
    )
    monkeypatch.setattr(ExperimentSpec, "root", property(lambda _: public_source.root))
    config = tmp_path / "config.yaml"
    config.write_text("per-task environment fixture")
    spec = ExperimentSpec(
        config,
        {
            "experiment": "skillsbench",
            "schema_version": "skillsbench.skill-evolution.v4",
            "tasks": {"selected": ["3d-scan-calc", "travel-planning"]},
            "source": {
                "upstream_checkout": "data/upstream/coevo-skills",
                "corpus_manifest": "data/skillsbench/public-manifest.json",
                "runtime_lock": template,
            },
            "provider": {
                "model": "openai.gpt-5.4",
                "transport": "bedrock-responses",
                "region": "us-east-1",
            },
        },
    )
    original = spec.identity
    assert template not in original["files"]
    path = runner.runtime_lock_path
    key = path.relative_to(public_source.root).as_posix()
    assert original["files"][key] is None
    path.parent.mkdir(exist_ok=True)
    path.write_text("new environment")
    assert spec.identity["files"][key] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert spec.identity["identity_hash"] != original["identity_hash"]


@pytest.mark.parametrize(
    "template",
    ["skillsbench-docker-{unknown}-lock.json", "skillsbench-docker-{task_id}-{task_id}.json"],
)
def test_runtime_rejects_unsupported_docker_lock_templates(public_source, template):
    with pytest.raises(ValueError, match="docker_lock_path_invalid"):
        SkillsBenchRunner(
            public_source.root,
            "3d-scan-calc",
            demo=False,
            runtime_lock_path=Path("runtime") / template,
        )
