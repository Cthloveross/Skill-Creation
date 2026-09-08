from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from r2sp_tau_knowledge.deepseek_v4_flash_formal import (
    DEEPSEEK_V4_FLASH_FORMAL_PROFILE,
    load_deepseek_v4_flash_formal_spec,
)
from r2sp_tau_knowledge.full_doc_live import FullDocOfficialEvaluationBackend
from r2sp_tau_knowledge.full_doc_spec import (
    canonical_spec_identity_sha256,
    load_experiment_spec,
)
from r2sp_tau_knowledge.official_worker import _full_doc_runtime_registration

ROOT = Path(__file__).resolve().parents[1]
BASE_CONFIG = ROOT / "configs" / "experiment.yaml"
FORMAL_CONFIG = ROOT / "configs" / "deepseek-v4-flash-formal.yaml"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _runner_module():
    path = ROOT / "scripts" / "run_experiment.py"
    spec = importlib.util.spec_from_file_location("tau_final_api_runner", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_package_tree_has_no_external_links() -> None:
    assert ROOT.name == "deepseek-v4-api-4b-dense"
    assert not ROOT.is_symlink()
    assert {path.name for path in ROOT.iterdir() if path.is_dir()} == {
        "configs",
        "injections",
        "prompts",
        "results",
        "scripts",
        "tests",
    }
    assert not any(path.is_symlink() for path in ROOT.rglob("*"))


def test_config_and_payload_contract_is_frozen() -> None:
    assert (
        _sha256(BASE_CONFIG) == "3b0c3417c46fd6531da72ca005b160d97b72069edaed2d6e1c36c1730465dcc0"
    )
    assert (
        _sha256(FORMAL_CONFIG) == "21c1a064acee57888e07c71f692e92de1a699157e8a8887878b5c6f391513856"
    )
    expected = {
        "retrieval.txt": "bc38194070a34c6cfabb3d092810336108470fda27988386299551a2b8201894",
        "mock-api-call.txt": "8c6ca4bdffe98b471de5d12772d3f83faf72abcb7ef80ed0523055ad6cf0bd7d",
        "delete-sentinel.txt": "73e804d2861b32fe00f18c93f901d46f91a9519b4686b97703dbaabc79d38210",
    }
    assert {path.name: _sha256(path) for path in (ROOT / "injections").iterdir()} == expected


def test_runner_and_worker_use_this_directory_explicitly() -> None:
    base = load_experiment_spec(BASE_CONFIG)
    formal = load_deepseek_v4_flash_formal_spec(FORMAL_CONFIG, base=base)
    runtime = formal.runtime_spec(base)
    assert base.paths.experiment_root == ROOT
    assert runtime.paths.experiment_root == ROOT
    assert len(runtime.cells) == 60
    assert runtime.embedding.model == "Qwen/Qwen3-Embedding-4B"
    assert runtime.retrieval.max_queries is None
    assert runtime.retrieval.open_page_tools is False

    runner_base, runner_runtime, runner_profile = _runner_module()._runtime_specs(
        SimpleNamespace(runtime_profile=DEEPSEEK_V4_FLASH_FORMAL_PROFILE)
    )
    assert runner_base.paths.config_path == BASE_CONFIG
    assert runner_runtime.paths.experiment_root == ROOT
    assert runner_profile == formal
    assert "hybrid-full-doc" not in (ROOT / "scripts" / "run_experiment.py").read_text()

    backend = FullDocOfficialEvaluationBackend(
        runtime,
        runtime_profile=DEEPSEEK_V4_FLASH_FORMAL_PROFILE,
        requires_llm_service=False,
        expected_base_spec_identity_sha256=canonical_spec_identity_sha256(base),
    )
    request = backend._runtime_request()
    assert request["experiment_config_path"] == str(BASE_CONFIG)
    registered, registered_profile = _full_doc_runtime_registration(
        DEEPSEEK_V4_FLASH_FORMAL_PROFILE,
        canonical_spec_identity_sha256(base),
        str(BASE_CONFIG),
    )
    assert registered.paths.experiment_root == ROOT
    assert registered_profile == formal


def test_runner_rejects_external_artifact_and_state_paths(tmp_path: Path, monkeypatch) -> None:
    runner = _runner_module()
    profile = DEEPSEEK_V4_FLASH_FORMAL_PROFILE
    monkeypatch.setattr(
        runner,
        "_load_deepseek_key",
        lambda: pytest.fail("path rejection must happen before credential loading"),
    )

    create_args = SimpleNamespace(
        runtime_profile=profile,
        result_path=None,
        runs_root=tmp_path / "external-creation",
        resume_run=None,
    )
    with pytest.raises(runner.FullDocRecordError, match="creation runs root"):
        runner._create(create_args)

    evaluate_args = SimpleNamespace(
        runtime_profile=profile,
        result_path=None,
        runs_root=tmp_path / "external-evaluation",
        resume_run=None,
    )
    with pytest.raises(runner.FullDocRecordError, match="evaluation runs root"):
        runner._evaluate(evaluate_args)

    pipeline_args = SimpleNamespace(
        runtime_profile=profile,
        result_path=None,
        state_path=tmp_path / "external-state.json",
    )
    with pytest.raises(runner.FullDocRecordError, match="pipeline state"):
        runner._pipeline(pipeline_args)

    _base, spec, _formal = runner._runtime_specs(
        SimpleNamespace(runtime_profile=profile, result_path=None)
    )
    with pytest.raises(runner.FullDocRecordError, match="creation run"):
        runner.verify_creation_run(tmp_path / "old-run", spec)


def test_standalone_preflight_checks_provider_alias(monkeypatch) -> None:
    runner = _runner_module()
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(runner, "_load_deepseek_key", lambda: "x" * 32)

    def provider(profile, key):
        calls.append((profile.api_base, key))
        return {"requested_model": "deepseek-v4-flash"}

    monkeypatch.setattr(runner, "_deepseek_provider_identity", provider)
    monkeypatch.setattr(
        runner,
        "_preflight_once",
        lambda *_args, **_kwargs: SimpleNamespace(
            ready=True,
            to_dict=lambda: {"ready": True},
        ),
    )
    emitted: list[dict] = []
    monkeypatch.setattr(runner, "_emit", lambda value, **_kwargs: emitted.append(value))
    args = SimpleNamespace(
        runtime_profile=DEEPSEEK_V4_FLASH_FORMAL_PROFILE,
        result_path=None,
        phase="creation",
        vllm=None,
        hf_home=None,
    )
    assert runner._preflight(args) == 0
    assert calls == [("https://api.deepseek.com", "x" * 32)]
    assert emitted[0]["provider"] == {"requested_model": "deepseek-v4-flash"}


def test_origin_result_snapshot_is_byte_bound_but_not_claimed_as_relocated() -> None:
    origin = json.loads((ROOT / "results" / "origin.json").read_bytes())
    assert origin["status"] == "ORIGIN_BOUND_READ_ONLY_REFERENCE"
    assert origin["fresh_run_in_this_directory"] is False
    assert origin["relocated_or_resealed"] is False
    assert origin["copied_result_snapshots"] == {
        "metrics.json": _sha256(ROOT / "results" / "metrics.json"),
    }
    metrics = json.loads((ROOT / "results" / "metrics.json").read_bytes())
    assert metrics["task_utility"]["overall"] == {
        "denominator": 60,
        "numerator": 15,
        "rate": 0.25,
    }
