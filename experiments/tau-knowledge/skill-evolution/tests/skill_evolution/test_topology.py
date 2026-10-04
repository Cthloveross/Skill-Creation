from pathlib import Path

import pytest
from tau_skill_evolution import cli, model, workflow
from tau_skill_evolution.runtime_controls import RuntimeGenerationSettings
from tau_skill_evolution.spec import load_spec


def test_current_experiment_owns_all_runtime_source_and_dependencies():
    spec = load_spec()
    source = spec.root / "src" / "tau_skill_evolution"
    assert all(Path(module.__file__).is_relative_to(source) for module in (cli, model, workflow))
    assert spec.upstream.is_relative_to(spec.root / "data")
    embedding = (spec.root / spec.values["embedding"]["vllm"]).resolve()
    assert embedding.is_relative_to(spec.root / "data" / "embedding")
    assert (spec.root / "configs" / "upstream-manifest.json").is_file()
    assert (spec.root / "configs" / "upstream-checkout-manifest.json").is_file()


def test_repository_has_no_other_experiment_or_duplicate_source_tree():
    root = load_spec().root
    repository = root.parents[2]
    assert tuple(path.name for path in root.parent.iterdir() if path.is_dir()) == (
        "skill-evolution",
    )
    assert tuple(path.name for path in (repository / "experiments").iterdir() if path.is_dir()) == (
        "tau-knowledge",
    )
    assert not (repository / "src").exists()
    assert not (repository / "tests").exists()


def test_runtime_controls_reject_unsupported_gpt_reasoning_effort():
    with pytest.raises(ValueError):
        RuntimeGenerationSettings("minimal", 1024)
