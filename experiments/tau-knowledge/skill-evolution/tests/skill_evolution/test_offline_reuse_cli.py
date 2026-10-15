"""The real consumer CLI replays catalogs without any retrieval service or index."""

from __future__ import annotations

import copy
import json
import shutil
import subprocess
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from tau_skill_evolution import (
    cli,
    codex_runtime,
    dense,
    retrieval,
    skillsbench,
    skillsbench_evolution,
    skillsbench_runtime,
)
from tau_skill_evolution import preflight as admission
from tau_skill_evolution import skillsbench_attack as attack
from tau_skill_evolution import workflow as workflow_module
from tau_skill_evolution.artifacts import atomic_json, load_base
from tau_skill_evolution.core._canonical import canonical_json_sha256 as digest
from tau_skill_evolution.evolution import EvolutionResult
from test_parallel_terra import _load_script
from test_retrieval_dataset import dataset as dataset


@pytest.fixture
def offline_cli(dataset, monkeypatch):
    """Replace external boundaries while retaining both production preflight layers."""
    state = SimpleNamespace(calls=[], tokens=[], tokenizer_loads=[], fault=None)
    spec = dataset.spec("consumer-gpt")
    spec.provider_settings = {**spec.values["provider"], "api_base": "https://offline.invalid"}
    spec.values["source"]["runtime_lock"] = "runtime/fake-task-lock.json"
    (spec.root / "prompts/skillsbench-verifier-adapter.txt").write_text("Use public-inputs")
    monkeypatch.setattr(cli, "load_spec", lambda _: spec)

    original_source = skillsbench.SkillsBenchSource

    class Source(original_source):
        def __init__(self, root):
            super().__init__(root)
            self.manifest["tasks"] = list(spec.tasks)

        def validate(self):
            state.calls.append("source")
            if state.fault == "source":
                raise ValueError("prepared source is unavailable")

    monkeypatch.setattr(skillsbench, "SkillsBenchSource", Source)
    monkeypatch.setattr(
        attack, "validate_condition_design", lambda _: {"status": "fake pinned source design"}
    )
    monkeypatch.setattr(
        codex_runtime, "codex_identity", lambda _: {"binary": "fake", "codex_version": "fake"}
    )
    monkeypatch.setattr(admission, "describe_credential", lambda _: "fake credential metadata")
    monkeypatch.setattr(admission.shutil, "which", lambda _: "/fake/docker")

    def infrastructure(command, **kwargs):
        assert command == ["docker", "info", "--format", "{{.ServerVersion}}"]
        state.calls.append("docker")
        return subprocess.CompletedProcess(command, 0, "fake server", "")

    monkeypatch.setattr(admission.subprocess, "run", infrastructure)

    def authentication(_):
        state.calls.append("authentication")
        if state.fault == "authentication":
            raise ValueError("fake model authentication failed")
        return {"status": 200, "generation_requested": False}

    monkeypatch.setattr(admission, "bedrock_authentication", authentication)

    class Runner:
        def __init__(self, root, task, **kwargs):
            assert root == spec.root and kwargs["runtime"] == "docker"
            self.task = task

        def preflight(self, **kwargs):
            assert kwargs["validate_source"] is False
            state.calls.append(f"runtime:{self.task}")
            return {"ready": state.fault != "runtime"}

    monkeypatch.setattr(skillsbench_runtime, "SkillsBenchRunner", Runner)

    class Tokenizer:
        def no_truncation(self):
            pass

        def no_padding(self):
            pass

        def encode(self, text, *, add_special_tokens=False):
            assert add_special_tokens is False
            state.tokens.append(text)
            return SimpleNamespace(ids=list(range(len(text.split()))))

    def tokenizer(identity):
        assert identity == {
            "tokenizer": spec.values["embedding"]["model"],
            "revision": spec.values["embedding"]["revision"],
        }
        state.tokenizer_loads.append(identity)
        return Tokenizer()

    monkeypatch.setattr(attack, "_load_tokenizer", tokenizer)

    class Client:
        def __init__(self, endpoint, **kwargs):
            assert endpoint == spec.provider_settings["api_base"]
            self.config, self.token_counter = kwargs["config"], kwargs["token_counter"]
            self.role = kwargs["usage_role"]

        def complete(self, messages, **kwargs):
            assert self.role == "generator", "catalog reuse must never dispatch Analyzer"
            state.calls.append("generate")
            assert self.token_counter.count(messages) > 0
            return {"files": [{"path": "SKILL.md", "content": "Use public facts"}]}

        def close(self):
            pass

    monkeypatch.setattr(workflow_module, "OpenAICompatibleClient", Client)
    monkeypatch.setattr(workflow_module, "bearer_token_source", lambda _: lambda: "fake")

    class Adapter:
        tool_schemas = ()

        def __init__(self, _spec, task, **kwargs):
            assert _spec is spec and task == "task-a"
            self.counter = kwargs["counter"]

        def acquisition(self, **kwargs):
            pytest.fail("catalog reuse must never reopen acquisition")

        @contextmanager
        def evolution_session(self, initial, public, base, **kwargs):
            state.calls.append("learning")
            assert base.base_hash == dataset.base.base_hash
            yield SimpleNamespace(counter=self.counter)

        def evaluate(self, bundle):
            state.calls.append("evaluate")
            assert self.counter("independent executor context") > 0
            return {"utility": 1.0, "asr": 0.0}

    monkeypatch.setattr(skillsbench, "SkillsBenchAdapter", Adapter)

    def evolve(session, initial, base, generator, verifier, **kwargs):
        state.calls.append("evolve")
        counter = kwargs["token_counter"]
        assert counter is session.counter
        assert counter is generator.token_counter.text_counter
        assert counter is verifier.token_counter.text_counter
        assert generator.token_counter.count([{"role": "user", "content": "revision gate"}]) > 0
        assert verifier.token_counter.count([{"role": "user", "content": "verifier gate"}]) > 0
        return EvolutionResult(
            (initial,), (), (), (True,), 0, "gt_oracle_pass", initial.bundle_hash
        )

    monkeypatch.setattr(skillsbench_evolution, "run_author_evolution", evolve)

    def forbidden(*args, **kwargs):
        pytest.fail("consumer CLI attempted network, retrieval, corpus, or Dense construction")

    monkeypatch.setattr(admission.urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(skillsbench, "validate_pool", forbidden)
    monkeypatch.setattr(attack, "validate_matrix_manifest", forbidden)
    monkeypatch.setattr(workflow_module, "prepare_corpus", forbidden)
    monkeypatch.setattr(retrieval, "ensure_cache", forbidden)
    monkeypatch.setattr(dense.DenseIndex, "build", forbidden)
    monkeypatch.setattr(dense.DenseIndex, "load_cache", forbidden)
    monkeypatch.setattr(dense.OpenAICompatibleEmbeddingClient, "embed_documents", forbidden)
    monkeypatch.setattr(dense.OpenAICompatibleEmbeddingClient, "embed_query", forbidden)

    # Only the portable public recipe and pinned source remain available.
    (dataset.directory / "base").unlink()
    shutil.rmtree(dataset.directory / "journal")
    (dataset.directory / "probe-result.json").unlink()
    shutil.rmtree(dataset.dense_dir)

    run_dir = dataset.tmp / "consumer-cli"

    def invoke(command, *, explicit=True, tasks=("task-a",)):
        args = [
            command,
            "--experiment",
            "skillsbench",
            "--run-dir",
            str(run_dir),
            "--arm",
            "benign",
            "--no-interim-report",
        ]
        for task in tasks:
            args.extend(("--task", task))
        if explicit:
            args.extend(("--bases-from", str(dataset.producer.root / "catalog.json")))
        return cli.main(args)

    return SimpleNamespace(invoke=invoke, state=state, run_dir=run_dir, spec=spec, dataset=dataset)


@pytest.mark.parametrize("command", ["create", "run"])
def test_actual_cli_replays_portable_catalog_with_real_preflight(offline_cli, capsys, command):
    fixture = offline_cli
    assert fixture.invoke(command) == 0
    assert json.loads(capsys.readouterr().out)["stage"] == command
    cell = fixture.run_dir / "cells/task-a/benign"
    assert load_base(cell / "base").to_dict() == fixture.dataset.base.to_dict()
    identity = json.loads((fixture.run_dir / "journal/identity.json").read_text())["identity"]
    assert identity["frozen_bases"]["catalog_hash"] == fixture.dataset.catalog["catalog_hash"]
    requests = [json.loads(path.read_text()) for path in (cell / "journal").glob("*/request.json")]
    assert not any(request["operation_id"].startswith("acquisition/") for request in requests)
    imported = next(
        request for request in requests if request["operation_id"] == "import-acquisition"
    )
    assert imported["payload"]["calls_performed_here"] == {
        "analyzer": 0,
        "search": 0,
        "read_only": 0,
        "clarify": 0,
    }
    assert {"authentication", "source", "runtime:task-a", "generate"} <= set(fixture.state.calls)
    assert fixture.state.tokenizer_loads and fixture.state.tokens
    if command == "run":
        assert {"learning", "evolve", "evaluate"} <= set(fixture.state.calls)


def test_cli_evolve_and_evaluate_resume_catalog_binding_offline(offline_cli, capsys):
    fixture = offline_cli
    assert fixture.invoke("create") == 0
    capsys.readouterr()
    assert fixture.invoke("evolve", explicit=False) == 0
    assert json.loads(capsys.readouterr().out)["stage"] == "evolve"
    assert fixture.invoke("evaluate", explicit=False) == 0
    assert json.loads(capsys.readouterr().out)["stage"] == "evaluate"
    assert fixture.state.calls.count("generate") == 1
    assert fixture.state.calls.count("evolve") == 1
    assert fixture.state.calls.count("authentication") == 3
    assert fixture.state.calls.count("source") == 3
    assert fixture.state.calls.count("runtime:task-a") == 3
    assert fixture.state.calls.count("evaluate") == 1


def test_launcher_generated_report_and_child_commands_reuse_offline(offline_cli, capsys):
    fixture = offline_cli
    launcher = _load_script("launch_matrix")
    arguments = ("r2sp", "skillsbench", fixture.dataset.root / "consumer.yaml", fixture.run_dir)
    catalog = fixture.dataset.producer.root / "catalog.json"
    report = launcher.report_command(*arguments, bases_from=catalog)
    assert cli.main(report[1:]) == 0
    capsys.readouterr()
    child = launcher.build_command(*arguments, "task-a", "benign", bases_from=catalog)
    assert cli.main(child[1:]) == 0
    assert {"generate", "evolve", "evaluate"} <= set(fixture.state.calls)
    assert fixture.state.calls.count("authentication") == 1
    assert fixture.state.tokenizer_loads and fixture.state.tokens


@pytest.mark.parametrize("error", [OSError("missing cache"), Exception("invalid tokenizer JSON")])
def test_reuse_requires_a_readable_pinned_local_tokenizer(offline_cli, monkeypatch, capsys, error):
    def unavailable(_identity):
        raise error

    monkeypatch.setattr(attack, "_load_tokenizer", unavailable)
    assert offline_cli.invoke("create") == 2
    checks = json.loads(capsys.readouterr().out)["checks"]
    tokenizer = next(check for check in checks if check["name"] == "local_context_tokenizer")
    assert tokenizer["ok"] is False
    assert "offline_context_tokenizer_unavailable" in tokenizer["detail"]
    assert "generate" not in offline_cli.state.calls


@pytest.mark.parametrize("fault", ["source", "runtime", "authentication"])
def test_catalog_reuse_retains_source_runtime_and_model_admission(offline_cli, capsys, fault):
    fixture = offline_cli
    fixture.state.fault = fault
    assert fixture.invoke("create") == 2
    result = json.loads(capsys.readouterr().out)
    assert result["ready"] is False
    assert not fixture.run_dir.exists()
    assert "generate" not in fixture.state.calls


def test_cli_missing_catalog_cell_fails_before_authentication_or_generation(offline_cli, capsys):
    fixture = offline_cli
    assert fixture.invoke("create", tasks=("task-a", "task-b")) == 2
    assert (
        "retrieval_dataset_cell_missing:task-b/benign"
        in json.loads(capsys.readouterr().out)["error"]
    )
    assert not fixture.run_dir.exists()
    assert fixture.state.calls == []


def test_cli_resume_rejects_replaced_catalog_before_authentication(offline_cli, capsys):
    fixture = offline_cli
    assert fixture.invoke("create") == 0
    capsys.readouterr()
    value = copy.deepcopy(fixture.dataset.catalog)
    value["status"] = "COMPLETE"
    value["catalog_hash"] = digest({k: v for k, v in value.items() if k != "catalog_hash"})
    atomic_json(fixture.dataset.producer.root / "catalog.json", value)
    fixture.state.calls.clear()
    assert fixture.invoke("evolve", explicit=False) == 2
    assert "retrieval_dataset_catalog_changed" in json.loads(capsys.readouterr().out)["error"]
    assert fixture.state.calls == []


def test_cli_without_catalog_still_requires_retrieval_preflight(offline_cli, monkeypatch, capsys):
    fixture = offline_cli

    def missing_pool(*args, **kwargs):
        fixture.state.calls.append("chunk-pool")
        raise ValueError("chunk Dense pool is absent")

    def missing_matrix(*args, **kwargs):
        fixture.state.calls.append("matrix-indexes")
        raise ValueError("condition Dense indexes are absent")

    def missing_embedding(*args, **kwargs):
        fixture.state.calls.append("embedding-service")
        raise OSError("embedding service is offline")

    monkeypatch.setattr(skillsbench, "validate_pool", missing_pool)
    monkeypatch.setattr(attack, "validate_matrix_manifest", missing_matrix)
    monkeypatch.setattr(admission.urllib.request, "urlopen", missing_embedding)
    assert fixture.invoke("create", explicit=False) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["ready"] is False
    assert {"chunk-pool", "matrix-indexes", "embedding-service"} <= set(fixture.state.calls)
    assert "generate" not in fixture.state.calls
    assert not fixture.run_dir.exists()
