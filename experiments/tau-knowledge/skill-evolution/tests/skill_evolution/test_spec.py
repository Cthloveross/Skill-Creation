from __future__ import annotations

import hashlib
import json
import shutil

import pytest
import yaml
from tau_skill_evolution import spec as spec_module
from tau_skill_evolution.constants import (
    BANKING_TREE,
    EXPERIMENT_ROOT,
    UPSTREAM_COMMIT,
    UPSTREAM_ROOT_TREE,
)
from tau_skill_evolution.journal import Journal
from tau_skill_evolution.spec import (
    ARMS,
    DEFAULT_CONFIG,
    LEGACY_ATTACK_PROFILES,
    NAMESPACE,
    POISON_SAMPLE_SHA256,
    SKILLSBENCH_COMMIT,
    SKILLSBENCH_CONFIG,
    digest,
    load_spec,
)


def _copy_config(tmp_path, mutate=None, source=DEFAULT_CONFIG):
    values = yaml.safe_load(source.read_text())
    if mutate:
        mutate(values)
    path = tmp_path / "snapshot.yaml"
    path.write_text(yaml.safe_dump(values, sort_keys=False))
    return path


def test_full_tau_matrix_preserves_legacy_profiles_poison_sample_and_source():
    spec = load_spec()
    assert spec.experiment == "tau" and spec.namespace == "tau.skill-evolution.v2"
    assert len(spec.tasks) == 97 and len(spec.cells) == 291 and spec.arms == ARMS
    assert list(spec.tasks) == sorted(spec.tasks)
    assert all(spec.profile(task) == profile for task, profile in LEGACY_ATTACK_PROFILES.items())
    remaining = [task for task in spec.tasks if task not in LEGACY_ATTACK_PROFILES]
    assert [spec.profile(task) for task in remaining] == [
        ("mock-api-call", "delete-sentinel")[index % 2] for index in range(77)
    ]
    assert spec.targets("benign") == ()
    assert len(spec.targets("poison-5")) == 35 and len(spec.targets("poison-10")) == 70
    assert spec.targets("poison-5") == spec.targets("poison-10")[:35]
    assert digest(list(spec.targets("poison-10"))) == POISON_SAMPLE_SHA256
    assert (
        spec.values["source"]["commit"],
        spec.values["source"]["root_tree"],
        spec.values["source"]["banking_tree"],
    ) == (UPSTREAM_COMMIT, UPSTREAM_ROOT_TREE, BANKING_TREE)
    assert spec.values["evolution"] == {"max_revisions": 15, "max_oracles": 5}
    assert spec.values["acquisition"] == {
        "min_document_confidence": 0.1,
        "max_searches": 30,
        "max_clarifications": 4,
        "max_reads": 10,
        "base_token_limit": 32768,
        "max_steps": 50,
    }


def test_skillsbench_configuration_has_the_fixed_matrix_and_only_benign_arm():
    spec = load_spec(SKILLSBENCH_CONFIG)
    assert spec.values["source"]["commit"] == SKILLSBENCH_COMMIT
    assert len(spec.tasks) == len(set(spec.tasks)) == len(spec.cells) == 85
    assert list(spec.tasks) == sorted(spec.tasks)
    assert spec.experiment == "skillsbench" and spec.namespace == "skillsbench.skill-evolution.v1"
    assert spec.arms == ("benign",) and spec.targets("benign") == ()
    assert spec.profile(spec.tasks[0]) == "benign"
    assert spec.values["acquisition"]["max_reads"] == 0
    assert spec.values["acquisition"]["max_clarifications"] == 0
    assert spec.values["roles"]["analyzer"]["prompt"] == "analyzer-skillsbench.md"
    assert spec.values["embedding"]["chunk_tokens"] == 2048
    assert spec.values["embedding"]["chunk_overlap_tokens"] == 128
    with pytest.raises(ValueError, match="arm"):
        spec.targets("poison-5")


@pytest.mark.skipif(
    not (EXPERIMENT_ROOT / "data/skillsbench/source-tree.json").is_file(),
    reason="requires prepared SkillsBench upstream tree metadata",
)
def test_prepared_skillsbench_matches_the_official_pinned_github_tree():
    spec = load_spec(SKILLSBENCH_CONFIG)
    tree = json.loads((EXPERIMENT_ROOT / "data/skillsbench/source-tree.json").read_text())
    names = sorted(
        item["path"].split("/")[1]
        for item in tree["tree"]
        if item["type"] == "tree"
        and item["path"].startswith("tasks/")
        and item["path"].count("/") == 1
    )
    assert tree["sha"] == SKILLSBENCH_COMMIT and not tree["truncated"]
    assert list(spec.tasks) == names


def test_generator_context_budget_is_explicit_and_separate_from_bank_admission():
    for path in (DEFAULT_CONFIG, SKILLSBENCH_CONFIG):
        spec = load_spec(path)
        generator = spec.values["roles"]["generator"]
        assert generator["reasoning_effort"] == "high" and generator["max_output_tokens"] == 32768
        assert generator["max_input_tokens"] == int(272000 * 0.7) - 32768 == 157632
        assert spec.values["runtime"]["controls"]["max_input_tokens"] == 114688
        assert spec.values["roles"]["analyzer"]["max_input_tokens"] == 114688


@pytest.mark.parametrize(
    "mutate",
    [
        lambda v: v.update(schema_version=NAMESPACE),
        lambda v: v["source"].update(commit="0" * 40),
        lambda v: v["tasks"]["selected"].__setitem__(0, "changed-task"),
        lambda v: v["tasks"]["attack_profiles"].__setitem__(0, "changed-profile"),
        lambda v: v["poison_sampling"]["target_document_ids"].__setitem__(0, "changed-doc"),
        lambda v: v["matrix"].update(retries=1),
        lambda v: v["retrieval"].update(rrf_k=61),
        lambda v: v["provider"].update(model="openai.gpt-oss-120b"),
        lambda v: v["provider"].update(transport="bedrock-converse"),
        lambda v: v["source"].update(upstream_checkout="../other-experiment/upstream"),
        lambda v: v["embedding"].update(vllm="../other-experiment/vllm"),
        lambda v: v["acquisition"].update(max_searches=True),
        lambda v: v["acquisition"].update(max_searches=31),
        lambda v: v["acquisition"].update(max_steps=51),
        lambda v: v["acquisition"].update(base_token_limit=0),
        lambda v: v["acquisition"].update(min_document_confidence=True),
        lambda v: v["acquisition"].update(min_document_confidence=float("nan")),
        lambda v: v["acquisition"].update(min_document_confidence=-0.1),
        lambda v: v["acquisition"].update(min_document_confidence=1.1),
        lambda v: v["evolution"].update(max_revisions=16),
        lambda v: v["roles"]["generator"].update(max_input_tokens=157633),
    ],
)
def test_spec_rejects_changed_commitments_or_invalid_controls(tmp_path, mutate):
    with pytest.raises(ValueError):
        load_spec(_copy_config(tmp_path, mutate))


@pytest.mark.parametrize("name", ["max_reads", "max_clarifications"])
def test_skillsbench_rejects_enabling_bank_acquisition_actions(tmp_path, name):
    with pytest.raises(ValueError, match="cannot clarify"):
        load_spec(
            _copy_config(tmp_path, lambda v: v["acquisition"].update({name: 1}), SKILLSBENCH_CONFIG)
        )


def test_snapshot_configuration_uses_current_experiment_root(tmp_path):
    spec = load_spec(
        _copy_config(
            tmp_path, lambda v: v["acquisition"].update(max_searches=20, min_document_confidence=0)
        )
    )
    assert spec.root == EXPERIMENT_ROOT and spec.path.parent == tmp_path
    assert spec.upstream == (EXPERIMENT_ROOT / "data/upstream/tau2-bench").resolve()
    assert spec.values["acquisition"]["min_document_confidence"] == 0
    assert spec.identity["files"]["config"] == hashlib.sha256(spec.path.read_bytes()).hexdigest()


def test_identity_binds_source_prompt_meta_manifest_lock_but_excludes_keys_and_runs(
    tmp_path, monkeypatch
):
    root = tmp_path / "resources"
    for directory in ("prompts", "injections", "runtime", "configs"):
        shutil.copytree(EXPERIMENT_ROOT / directory, root / directory)
    source = root / "src/tau_skill_evolution/acquisition.py"
    source.parent.mkdir(parents=True)
    source.write_text("# source v1\n")
    meta = root / "data/upstream/coevo-skills/meta_skills/skill-creator/SKILL.md"
    meta.parent.mkdir(parents=True)
    meta.write_text("Authoring rules\n")
    public = root / "data/skillsbench/public-manifest.json"
    public.parent.mkdir(parents=True)
    public.write_text('{"documents":[]}\n')
    (public.parent / "source-tree.json").write_text("{}\n")
    monkeypatch.setattr(spec_module, "EXPERIMENT_ROOT", root)
    spec = load_spec(_copy_config(tmp_path, source=SKILLSBENCH_CONFIG))
    initial = spec.identity
    assert "src/tau_skill_evolution/acquisition.py" in initial["files"]
    assert "prompts/analyzer-skillsbench.md" in initial["files"]
    assert "data/upstream/coevo-skills/meta_skills/skill-creator/SKILL.md" in initial["files"]
    assert "data/skillsbench/public-manifest.json" in initial["files"]
    assert "runtime/skillsbench-bubblewrap-lock.json" in initial["files"]
    (root / "key.env").write_text("SECRET=never-hashed\n")
    (root / "runs").mkdir()
    (root / "runs/result.json").write_text('{"utility":1}\n')
    assert spec.identity == initial
    source.write_text("# source v2\n")
    after_source = spec.identity
    assert after_source["identity_hash"] != initial["identity_hash"]
    meta.write_text("Changed authoring rules\n")
    assert spec.identity["identity_hash"] != after_source["identity_hash"]
    Journal(tmp_path / "journal", identity={"namespace": NAMESPACE})
    with pytest.raises(ValueError, match="identity differs"):
        Journal(tmp_path / "journal", identity=spec.identity)


def test_worker_config_has_separate_private_judge_model_and_public_runtime_paths():
    spec = load_spec()
    config = spec.worker_config()
    assert config["allowed_task_ids"] == list(spec.tasks)
    assert config["model"] == config["user_model"] == config["judge_model"] == "openai.gpt-5.5"
    assert config["api_base"] == "https://bedrock-mantle.us-east-1.api.aws/openai/v1"
    assert "digest" in config["docker"]
    assert "gold_documents" not in config and "expected_actions" not in config


def test_effective_region_is_bound_and_snapshot_has_no_implicit_default(tmp_path, monkeypatch):
    spec = load_spec(_copy_config(tmp_path, lambda v: v["provider"].update(region=None)))
    monkeypatch.delenv("AWS_REGION", raising=False)
    with pytest.raises(ValueError, match="missing_region"):
        _ = spec.provider_settings
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    initial = spec.identity
    monkeypatch.setenv("AWS_REGION", "us-east-2")
    assert (
        spec.provider_settings["api_base"] == "https://bedrock-mantle.us-east-2.api.aws/openai/v1"
    )
    assert spec.identity["identity_hash"] != initial["identity_hash"]
    monkeypatch.setenv("AWS_REGION", "eu-west-1")
    with pytest.raises(ValueError, match="unsupported_region"):
        _ = spec.provider_settings


def test_role_prompts_match_domain_capabilities_and_omit_quotes_by_default():
    spec = load_spec()
    analyzer = (spec.root / "prompts/analyzer.md").read_text()
    assert "next_action" not in analyzer and '{"kind":"read_only"' in analyzer
    assert "Omit quote by default" in analyzer
    assert all(field in analyzer for field in ("policies", "tools", "parameters", "preconditions"))
    sb = (spec.root / "prompts/analyzer-skillsbench.md").read_text()
    assert '{"kind":"read_only"' not in sb and '{"kind":"clarify"' not in sb
    assert "budgets are zero" in sb
    verifier = (spec.root / "prompts/verifier.md").read_text()
    assert "/public" not in verifier and "/bundle" in verifier


def test_preparing_another_domain_runtime_does_not_invalidate_a_checkpoint(tmp_path, monkeypatch):
    tau, sb = load_spec(), load_spec(SKILLSBENCH_CONFIG)
    monkeypatch.setattr(spec_module, "EXPERIMENT_ROOT", tmp_path)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    tau_lock = runtime / "image-lock.json"
    sb_lock = runtime / "skillsbench-bubblewrap-lock.json"
    tau_lock.write_text('{"revision": 1}')
    sb_lock.write_text('{"revision": 1}')
    tau_identity, sb_identity = tau.identity, sb.identity
    sb_lock.write_text('{"revision": 2}')
    assert tau.identity == tau_identity and sb.identity != sb_identity
    sb_identity = sb.identity
    tau_lock.write_text('{"revision": 2}')
    assert sb.identity == sb_identity and tau.identity != tau_identity
