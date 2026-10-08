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


def _codex_plan_provider(values):
    pinned = values["runtime"]["codex"]
    values["provider"] = {
        "model": "gpt-6.1-sol",
        "transport": "codex-plan",
        "binary": "/opt/codex-0.160.1/codex",
        "version": pinned["version"],
        "binary_sha256": pinned["binary_sha256"],
    }


def test_full_tau_matrix_preserves_legacy_profiles_poison_sample_and_source():
    spec = load_spec()
    assert spec.experiment == "tau" and spec.namespace == "tau.skill-evolution.v4"
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
    assert spec.values["evolution"] == {
        "max_revisions": 15,
        "max_oracles": 5,
        "max_oracle_errors": 5,
        "revision_timeout_seconds": 3600,
    }
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
    assert spec.experiment == "skillsbench" and spec.namespace == "skillsbench.skill-evolution.v6"
    assert spec.values["runtime"]["executor"] == "author-codex"
    assert spec.arms == ("benign",) and spec.targets("benign") == ()
    assert spec.profile(spec.tasks[0]) == "benign"
    assert spec.values["acquisition"]["max_reads"] == 0
    assert spec.values["acquisition"]["max_clarifications"] == 0
    assert spec.values["roles"]["analyzer"]["prompt"] == "analyzer-skillsbench.md"
    assert spec.values["embedding"]["chunk_tokens"] == 2048
    assert spec.values["embedding"]["chunk_overlap_tokens"] == 128
    assert spec.values["source"]["runtime_lock"] == (
        "runtime/skillsbench-docker-{task_id}-v4-lock.json"
    )
    with pytest.raises(ValueError, match="arm"):
        spec.targets("poison-5")


def test_skillsbench_author_budgets_do_not_keep_extra_revision_or_post_caps():
    spec = load_spec(SKILLSBENCH_CONFIG)
    assert spec.namespace == "skillsbench.skill-evolution.v6"
    assert spec.values["evolution"] == {
        "max_surrogate_retries": 15,
        "max_oracles": 5,
        "max_oracle_errors": 5,
        "timeout_multiplier": 5,
        "timeout_seconds": 7200,
    }
    generator, runtime = spec.values["roles"]["generator"], spec.values["runtime"]
    assert generator["max_episodes"] == 120 and "max_turns" not in generator
    assert runtime["max_turns"] is None and "episode_timeout_seconds" not in runtime
    assert "evolution_timeout_seconds" not in runtime["codex"]
    assert runtime["codex"]["evaluation_timeout_seconds"] == 7200
    assert all(role["max_output_tokens"] is None for role in spec.values["roles"].values())
    assert "prompt" not in spec.values["roles"]["verifier"]


@pytest.mark.parametrize(
    "folder,model",
    [
        ("full-85-gpt56-v6", "openai.gpt-5.6-terra"),
        ("full-85-opus48-v6", "anthropic.claude-opus-4-8"),
    ],
)
def test_new_author_handoff_configs_preserve_the_old_population_and_models(folder, model):
    root = EXPERIMENT_ROOT / "runs/skillsbench"
    old = load_spec(root / folder.replace("-v6", "-v4") / "config.yaml")
    new = load_spec(root / folder / "config.yaml")
    assert new.namespace == "skillsbench.skill-evolution.v6"
    assert old.namespace == "skillsbench.skill-evolution.v4"
    assert old.tasks == new.tasks and old.values["source"] == new.values["source"]
    for name in ("provider", "retrieval", "embedding", "acquisition", "matrix_commitment"):
        assert old.values[name] == new.values[name]
    assert new.values["provider"]["model"] == model


@pytest.mark.parametrize(
    "mutate",
    [
        lambda v: v["evolution"].update(max_revisions=15),
        lambda v: v["evolution"].update(revision_timeout_seconds=3600),
        lambda v: v["evolution"].update(max_surrogate_retries=True),
        lambda v: v["evolution"].update(max_surrogate_retries=16),
        lambda v: v["evolution"].update(max_surrogate_retries=14),
        lambda v: v["evolution"].update(max_oracles=4),
        lambda v: v["evolution"].update(max_oracle_errors=4),
        lambda v: v["evolution"].update(timeout_multiplier=True),
        lambda v: v["evolution"].update(timeout_multiplier=2),
        lambda v: v["evolution"].update(timeout_seconds=0),
        lambda v: v["roles"]["generator"].update(max_turns=120),
        lambda v: v["roles"]["generator"].update(max_episodes=121),
        lambda v: v["runtime"].update(max_turns=100),
        lambda v: v["runtime"].update(episode_timeout_seconds=3600),
        lambda v: v["runtime"]["codex"].update(evolution_timeout_seconds=3000),
        lambda v: v["roles"]["verifier"].update(prompt="verifier-skillsbench.md"),
    ],
)
def test_skillsbench_v6_rejects_legacy_caps_and_invalid_author_limits(tmp_path, mutate):
    with pytest.raises(ValueError):
        load_spec(_copy_config(tmp_path, mutate, SKILLSBENCH_CONFIG))


@pytest.mark.parametrize("name,number", [("max_turns", 29), ("diagnosis_turns", 7)])
def test_v5_rejects_verifier_overrides_ignored_by_pinned_author(tmp_path, name, number):
    with pytest.raises(ValueError, match="pinned author verifier"):
        load_spec(
            _copy_config(
                tmp_path,
                lambda value: value["roles"]["verifier"].update({name: number}),
                SKILLSBENCH_CONFIG,
            )
        )


@pytest.mark.parametrize(
    "source",
    [DEFAULT_CONFIG, EXPERIMENT_ROOT / "runs/skillsbench/full-85-gpt56-v4/config.yaml"],
)
def test_tau_and_v4_keep_their_configured_verifier_limits(tmp_path, source):
    spec = load_spec(
        _copy_config(
            tmp_path,
            lambda value: value["roles"]["verifier"].update(max_turns=29, diagnosis_turns=7),
            source,
        )
    )
    assert spec.values["roles"]["verifier"]["max_turns"] == 29
    assert spec.values["roles"]["verifier"]["diagnosis_turns"] == 7


@pytest.mark.parametrize(
    "path",
    [
        "runtime/skillsbench-docker-{unknown}-lock.json",
        "runtime/skillsbench-docker-{task_id}-{task_id}-lock.json",
        "runtime/skillsbench-docker-{task_id}-{unknown}-lock.json",
        "runtime/skillsbench-bubblewrap-{task_id}-lock.json",
    ],
)
def test_skillsbench_rejects_unsupported_runtime_lock_templates(tmp_path, path):
    with pytest.raises(ValueError, match="runtime lock only supports"):
        load_spec(
            _copy_config(
                tmp_path,
                lambda value: value["source"].update(runtime_lock=path),
                SKILLSBENCH_CONFIG,
            )
        )


def test_author_codex_cannot_use_a_historical_namespace(tmp_path):
    with pytest.raises(ValueError, match="Codex requires.*v4"):
        load_spec(
            _copy_config(
                tmp_path,
                lambda value: value.update(schema_version="skillsbench.skill-evolution.v2"),
                SKILLSBENCH_CONFIG,
            )
        )


def test_codex_cli_digest_must_be_a_real_hex_digest(tmp_path):
    with pytest.raises(ValueError, match="binary hash"):
        load_spec(
            _copy_config(
                tmp_path,
                lambda value: value["runtime"]["codex"].update(binary_sha256="z" * 64),
                SKILLSBENCH_CONFIG,
            )
        )


@pytest.mark.parametrize("problem", [None, "missing-pair", "hash", "missing-gpt56"])
def test_codex_code_mode_companion_configuration(tmp_path, problem):
    def change(value):
        codex = value["runtime"]["codex"]
        if problem != "missing-gpt56":
            codex.update(code_mode_host_binary="/pinned/codex-code-mode-host")
        if problem not in {"missing-pair", "missing-gpt56"}:
            codex.update(code_mode_host_sha256="z" * 64 if problem == "hash" else "a" * 64)
        if problem == "missing-gpt56":
            value["provider"]["model"] = "openai.gpt-5.6-terra"

    path = _copy_config(tmp_path, change, SKILLSBENCH_CONFIG)
    if problem:
        with pytest.raises(ValueError, match="Codex|code-mode"):
            load_spec(path)
    else:
        spec = load_spec(path)
        assert spec.values["runtime"]["codex"]["code_mode_host_sha256"] == "a" * 64


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
        assert generator["reasoning_effort"] == "high" and generator["max_output_tokens"] is None
        assert generator["max_input_tokens"] == int(272000 * 0.7) - 32768 == 157632
        assert spec.values["runtime"]["controls"]["max_input_tokens"] == 114688
        assert spec.values["roles"]["analyzer"]["max_input_tokens"] == 114688


def test_gpt54_trial_can_select_medium_generator_effort_with_the_same_budgets(tmp_path):
    def configure(value):
        value["provider"]["model"] = "openai.gpt-5.4"
        value["roles"]["generator"]["reasoning_effort"] = "medium"

    spec = load_spec(_copy_config(tmp_path, configure, SKILLSBENCH_CONFIG))
    assert spec.values["roles"]["generator"]["reasoning_effort"] == "medium"
    assert spec.values["roles"]["generator"]["max_output_tokens"] is None
    assert spec.values["evolution"]["max_surrogate_retries"] == 15
    assert spec.values["evolution"]["max_oracles"] == 5


def test_author_codex_trial_can_omit_output_limits_without_changing_input_admission(tmp_path):
    def configure(value):
        value["provider"]["model"] = "openai.gpt-5.4"
        for role in value["roles"].values():
            role["max_output_tokens"] = None
        controls = value["runtime"]["controls"]
        controls["assistant_completion_budget"] = None
        for role in ("agent", "user"):
            controls[role]["max_output_tokens"] = None

    spec = load_spec(_copy_config(tmp_path, configure, SKILLSBENCH_CONFIG))
    generator = spec.values["roles"]["generator"]
    assert generator["reasoning_effort"] == "high"
    assert generator["max_output_tokens"] is None
    assert generator["max_input_tokens"] == 157632
    assert generator["max_episodes"] == 120
    assert spec.values["evolution"]["max_surrogate_retries"] == 15
    assert spec.values["evolution"]["max_oracles"] == 5


@pytest.mark.parametrize("field", ["agent", "user", "assistant_completion_budget"])
def test_local_bank_runtime_cannot_select_unsupported_null_limits(tmp_path, field):
    def configure(value):
        controls = value["runtime"]["controls"]
        if field == "assistant_completion_budget":
            controls[field] = None
        else:
            controls[field]["max_output_tokens"] = None

    with pytest.raises(ValueError, match="null runtime output limits"):
        load_spec(_copy_config(tmp_path, configure))


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
        lambda v: v["roles"]["generator"].update(reasoning_effort="invalid"),
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
    shutil.copytree(
        EXPERIMENT_ROOT / "src/tau_skill_evolution/author",
        source.parent / "author",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
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


def test_v6_identity_binds_byte_preserved_verifier_sources_and_prompts(tmp_path, monkeypatch):
    root = tmp_path / "resources"
    root.mkdir()
    author = root / "src/tau_skill_evolution/author"
    prompt = (
        author / "coevo/libs/terminus_agent/evolution/prompt_templates/independent_verifier.txt"
    )
    prompt.parent.mkdir(parents=True)
    prompt.write_bytes(b"Author prompt\r\n")
    manifest = author / "VERIFIER_SOURCE.json"
    prompt_relative = prompt.relative_to(author).as_posix()
    manifest.write_text(json.dumps({"commit": "pinned", "files": {prompt_relative: {}}}))
    monkeypatch.setattr(spec_module, "EXPERIMENT_ROOT", root)
    spec = load_spec(_copy_config(tmp_path, source=SKILLSBENCH_CONFIG))
    initial = spec.identity
    prompt_key = str(prompt.relative_to(root))
    manifest_key = str(manifest.relative_to(root))
    assert initial["files"][prompt_key] == hashlib.sha256(prompt.read_bytes()).hexdigest()
    assert initial["files"][manifest_key] == hashlib.sha256(manifest.read_bytes()).hexdigest()
    prompt.write_bytes(b"Author prompt\n")
    assert spec.identity["identity_hash"] != initial["identity_hash"]
    after_prompt = spec.identity
    manifest.write_text(json.dumps({"commit": "different", "files": {prompt_relative: {}}}))
    assert spec.identity["identity_hash"] != after_prompt["identity_hash"]


def test_worker_config_has_separate_private_judge_model_and_public_runtime_paths():
    spec = load_spec()
    config = spec.worker_config()
    assert config["allowed_task_ids"] == list(spec.tasks)
    assert config["model"] == config["user_model"] == config["judge_model"] == "openai.gpt-5.4"
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


def test_opus_configuration_selects_messages_and_binds_effective_region(tmp_path, monkeypatch):
    spec = load_spec(
        _copy_config(
            tmp_path,
            lambda value: value["provider"].update(
                model="anthropic.claude-opus-4-8", transport="bedrock-messages", region=None
            ),
        )
    )
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    assert (
        spec.provider_settings["api_base"]
        == "https://bedrock-mantle.us-east-1.api.aws/anthropic/v1"
    )
    initial = spec.identity
    monkeypatch.setenv("AWS_REGION", "us-east-2")
    with pytest.raises(ValueError, match="Opus 4.8"):
        _ = spec.provider_settings
    assert initial["provider"]["model"] == "anthropic.claude-opus-4-8"


@pytest.mark.parametrize(
    "provider",
    [
        {"model": "anthropic.claude-opus-4-8", "transport": "bedrock-responses"},
        {"model": "openai.gpt-5.6-terra", "transport": "bedrock-messages"},
        {
            "model": "anthropic.claude-opus-4-8",
            "transport": "bedrock-messages",
            "region": "us-east-2",
        },
    ],
)
def test_provider_rejects_wrong_transport_and_opus_region(tmp_path, provider):
    with pytest.raises(ValueError):
        load_spec(_copy_config(tmp_path, lambda value: value["provider"].update(provider)))


def test_codex_plan_is_an_explicit_credential_free_skillsbench_trial(tmp_path, monkeypatch):
    spec = load_spec(_copy_config(tmp_path, _codex_plan_provider, SKILLSBENCH_CONFIG))
    monkeypatch.delenv("AWS_REGION", raising=False)
    provider = spec.provider_settings
    assert provider["api_base"] == "http://127.0.0.1/codex-plan"
    assert "api_key_env" not in provider and "region" not in provider
    assert len(spec.tasks) == 85 and len(spec.cells) == 85
    identity = spec.identity["provider"]
    assert identity["model"] == "gpt-6.1-sol"
    assert identity["initial_creation"] == "one_codex_turn"
    assert identity["underlying_http_requests"] == "NOT_OBSERVABLE"
    assert identity["credential_source"] == "local_codex_chatgpt_login"
    assert identity["bedrock_equivalent"] is False
    assert identity["binary_sha256"] == provider["binary_sha256"]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda v: v["provider"].update(model="gpt-5.4"),
        lambda v: v["provider"].update(binary="codex"),
        lambda v: v["provider"].update(version="0.162.0"),
        lambda v: v["provider"].update(binary_sha256="0" * 64),
        lambda v: v["provider"].update(api_key_env="AWS_BEARER_TOKEN_BEDROCK"),
        lambda v: v.update(schema_version="skillsbench.skill-evolution.v4"),
    ],
)
def test_codex_plan_rejects_silent_model_or_pin_changes(tmp_path, mutate):
    def configure(values):
        _codex_plan_provider(values)
        mutate(values)

    with pytest.raises(ValueError, match="Codex plan"):
        load_spec(_copy_config(tmp_path, configure, SKILLSBENCH_CONFIG))


def test_tau_does_not_accept_codex_plan_transport(tmp_path):
    def configure(values):
        values["provider"] = {
            "model": "gpt-6.1-sol",
            "transport": "codex-plan",
            "binary": "/opt/codex/codex",
            "version": "0.160.1",
            "binary_sha256": "0" * 64,
        }

    with pytest.raises(ValueError, match="SkillsBench v6"):
        load_spec(_copy_config(tmp_path, configure))


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
    assert "/bundle/public_inputs.json" in verifier and "terminal" in verifier


def test_preparing_another_domain_runtime_does_not_invalidate_a_checkpoint(tmp_path, monkeypatch):
    tau, sb = load_spec(), load_spec(SKILLSBENCH_CONFIG)
    shutil.copytree(
        EXPERIMENT_ROOT / "src/tau_skill_evolution/author",
        tmp_path / "src/tau_skill_evolution/author",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
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


def test_workspace_worker_config_does_not_require_a_docker_image_lock(tmp_path, monkeypatch):
    spec = load_spec()
    monkeypatch.setattr(spec_module, "EXPERIMENT_ROOT", tmp_path)
    config = spec.worker_config(runtime="workspace")
    assert "docker" not in config
    assert config["sandbox"] == {
        "backend": "workspace",
        "runtime_lock": str(tmp_path / "runtime/bubblewrap-lock.json"),
    }
