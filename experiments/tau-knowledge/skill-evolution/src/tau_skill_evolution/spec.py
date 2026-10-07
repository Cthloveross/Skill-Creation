"""Pinned configuration and provenance for τ-Knowledge and SkillsBench."""

from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .constants import (
    BANKING_TREE,
    DEFAULT_MODEL,
    EXPERIMENT_ROOT,
    MESSAGES_MODEL,
    RESPONSES_MODELS,
    UPSTREAM_COMMIT,
    UPSTREAM_ROOT_TREE,
)

# Historical wire-format tests and sealed artifacts still use v1. New method
# namespaces are deliberately different and cannot resume those checkpoints.
NAMESPACE = "tau.skill-evolution.v1"
NAMESPACES = {"tau": "tau.skill-evolution.v4", "skillsbench": "skillsbench.skill-evolution.v4"}
DEFAULT_CONFIG = EXPERIMENT_ROOT / "configs" / "experiment.yaml"
SKILLSBENCH_CONFIG = EXPERIMENT_ROOT / "configs" / "skillsbench.yaml"
ARMS = ("benign", "poison-5", "poison-10")
SKILLSBENCH_COMMIT = "4380d4bff673dd6e1d58e5babeb2aaa0fe527119"
SKILLSBENCH_TASK_POPULATION_SHA256 = (
    "1afe3b8bb2a9f1055ea7a341fee43d02245cc32ce8ae5f151cee226aa3119224"
)
POISON_SAMPLE_SHA256 = "798669a317ab9abb8215b996a9a586af58a81b3f32b83678768f2889cd225fe6"
# Default alias kept for existing imports; configs may select any SUPPORTED_MODELS entry.
BEDROCK_MODEL = DEFAULT_MODEL
BEDROCK_REGIONS = ("us-east-1", "us-east-2")
LEGACY_TASKS = (
    "task_019",
    "task_029",
    "task_056",
    "task_040",
    "task_070",
    "task_036",
    "task_068",
    "task_020",
    "task_002",
    "task_039",
    "task_092",
    "task_052",
    "task_101",
    "task_066",
    "task_072",
    "task_033",
    "task_074",
    "task_008",
    "task_093",
    "task_021",
)
ATTACK_PROFILES = ("mock-api-call", "delete-sentinel")
LEGACY_ATTACK_PROFILES = {
    task: ATTACK_PROFILES[index % 2] for index, task in enumerate(LEGACY_TASKS)
}


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    ).hexdigest()


def tau_attack_profiles(tasks: list[str]) -> list[str]:
    additional = [task for task in sorted(tasks) if task not in LEGACY_ATTACK_PROFILES]
    profiles = {task: ATTACK_PROFILES[index % 2] for index, task in enumerate(additional)}
    profiles.update(LEGACY_ATTACK_PROFILES)
    return [profiles[task] for task in tasks]


@dataclass(frozen=True)
class ExperimentSpec:
    path: Path
    values: dict[str, Any]

    @property
    def root(self) -> Path:
        # Config snapshots may live under runs or outside this directory; all
        # source/data paths belong to this experiment, never the snapshot parent.
        return EXPERIMENT_ROOT

    @property
    def experiment(self) -> str:
        return self.values["experiment"]

    @property
    def namespace(self) -> str:
        return self.values["schema_version"]

    @property
    def arms(self) -> tuple[str, ...]:
        return tuple(self.values["matrix"]["arms"])

    @property
    def upstream(self) -> Path:
        return (self.root / self.values["source"]["upstream_checkout"]).resolve()

    @property
    def tasks(self) -> tuple[str, ...]:
        return tuple(self.values["tasks"]["selected"])

    @property
    def cells(self) -> tuple[tuple[str, str], ...]:
        return tuple((task, arm) for task in self.tasks for arm in self.arms)

    def profile(self, task: str) -> str:
        if self.experiment == "skillsbench":
            if task not in self.tasks:
                raise ValueError("task is outside the configured matrix")
            return "benign"
        return self.values["tasks"]["attack_profiles"][self.tasks.index(task)]

    def targets(self, arm: str) -> tuple[str, ...]:
        if arm not in self.arms:
            raise ValueError("arm is outside the configured matrix")
        if self.experiment == "skillsbench" or arm == "benign":
            return ()
        count = {"poison-5": 35, "poison-10": 70}[arm]
        return tuple(self.values["poison_sampling"]["target_document_ids"][:count])

    @property
    def provider_settings(self) -> dict[str, Any]:
        provider = dict(self.values["provider"])
        region = provider.get("region") or os.environ.get(provider["region_env"])
        if not region:
            raise ValueError(f"missing_region: set provider.region or {provider['region_env']}")
        if region not in BEDROCK_REGIONS:
            raise ValueError("unsupported_region: Bedrock Mantle requires us-east-1/us-east-2")
        if provider["model"] == MESSAGES_MODEL and region != "us-east-1":
            raise ValueError("unsupported_region: Opus 4.8 Mantle requires us-east-1")
        route = "anthropic" if provider["transport"] == "bedrock-messages" else "openai"
        provider.update(
            region=region, api_base=f"https://bedrock-mantle.{region}.api.aws/{route}/v1"
        )
        return provider

    @property
    def identity(self) -> dict[str, Any]:
        runtime_locks = sorted((self.root / "runtime").glob("*lock*"))
        runtime_locks = [
            path
            for path in runtime_locks
            if path.name.startswith("skillsbench") == (self.experiment == "skillsbench")
        ]
        files = [
            *sorted((self.root / "src" / "tau_skill_evolution").rglob("*.py")),
            *sorted((self.root / "prompts").glob("*.md")),
            *sorted((self.root / "meta").rglob("*.md")),
            *runtime_locks,
        ]
        if self.experiment == "tau":
            files.extend(sorted((self.root / "injections").glob("*.txt")))
            files.extend(
                self.root / "configs" / name
                for name in (
                    "upstream-manifest.json",
                    "upstream-checkout-manifest.json",
                )
            )
        else:
            files.extend(
                self.root / "data" / "skillsbench" / name
                for name in ("source-tree.json", "source-manifest.json", "corpus/manifest.json")
            )
            if self.namespace == "skillsbench.skill-evolution.v4":
                files.extend(
                    self.root / "src/tau_skill_evolution/author" / name
                    for name in ("SOURCE.json", "LICENSE")
                )
        source = self.values["source"]
        files.append(self.root / source["corpus_manifest"])
        selected_lock = source["runtime_lock"]
        if self.experiment == "skillsbench" and "{task_id}" in selected_lock:
            files.extend(
                self.root / selected_lock.replace("{task_id}", task) for task in self.tasks
            )
        else:
            files.append(self.root / selected_lock)
        meta = self.upstream / "meta_skills" / "skill-creator"
        if self.experiment == "skillsbench":
            files.extend(sorted(path for path in meta.rglob("*") if path.is_file()))
        hashes: dict[str, str | None] = {
            "config": hashlib.sha256(self.path.read_bytes()).hexdigest()
        }
        for path in files:
            hashes[str(path.relative_to(self.root))] = (
                hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
            )
        provider = self.values["provider"]
        resolved = {
            "model": provider["model"],
            "transport": provider["transport"],
            "region": provider.get("region") or os.environ.get(provider["region_env"]),
        }
        binding = {
            "experiment": self.experiment,
            "namespace": self.namespace,
            "files": hashes,
            "provider": resolved,
        }
        return {**binding, "identity_hash": digest(binding)}

    def worker_config(self, *, runtime: str = "docker") -> dict[str, Any]:
        if runtime not in {"docker", "workspace", "bubblewrap-demo"}:
            raise ValueError("unsupported runtime")
        settings, provider = self.values["runtime"], self.provider_settings
        embedding = self.values["embedding"]
        config = {
            "experiment": self.experiment,
            "runtime_controls": settings["controls"],
            "model": provider["model"],
            "user_model": provider["model"],
            "judge_model": provider["model"],
            "transport": provider["transport"],
            "region": provider["region"],
            "api_base": provider["api_base"],
            "api_key_env": provider["api_key_env"],
            "tokenizer_endpoint": embedding["endpoint"],
            "tokenizer_model": embedding["model"],
            "token_counter_basis": "embedding_responses_input_estimate_with_reasoning_reserve",
            "request_timeout_seconds": settings["request_timeout_seconds"],
            "episode_timeout_seconds": settings["episode_timeout_seconds"],
            "max_turns": settings["max_turns"],
            "max_task_tool_calls": settings["max_task_tool_calls"],
            "seed": self.values["seed"],
            "allowed_task_ids": list(self.tasks),
        }
        if runtime == "docker":
            config["docker"] = {
                **json.loads((self.root / "runtime" / "image-lock.json").read_text()),
                "dependency_lock": str(self.root / "runtime" / "requirements.lock"),
            }
        else:
            config["sandbox"] = {
                "backend": runtime,
                "runtime_lock": str(self.root / "runtime" / "bubblewrap-lock.json"),
            }
        if self.experiment == "tau":
            banking = self.upstream / "data" / "tau2" / "domains" / "banking_knowledge"
            config.update(
                banking_root=str(banking),
                tasks_root=str(banking / "tasks"),
                deployment_prompt_path=str(self.root / "prompts" / "execution.md"),
            )
        else:
            config.update(
                upstream_root=str(self.upstream),
                tasks_root=str(self.upstream / "tasks"),
                corpus_manifest=str(self.root / self.values["source"]["corpus_manifest"]),
                runtime_lock=str(self.root / self.values["source"]["runtime_lock"]),
            )
        return config


def load_spec(path: Path = DEFAULT_CONFIG) -> ExperimentSpec:
    path = Path(path).resolve()
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("experiment") not in NAMESPACES:
        raise ValueError("configuration must select tau or skillsbench")
    experiment = value["experiment"]
    namespaces = {NAMESPACES[experiment]}
    if experiment == "skillsbench":
        # Historical config snapshots remain readable, with their own frozen identity.
        namespaces.add("skillsbench.skill-evolution.v2")
    if value.get("schema_version") not in namespaces:
        raise ValueError("configuration namespace does not match the current experiment method")
    source, tasks = value["source"], value["tasks"]["selected"]
    if not isinstance(tasks, list) or any(not isinstance(task, str) for task in tasks):
        raise ValueError("selected task IDs must be a list of strings")
    count = 97 if experiment == "tau" else 85
    if len(tasks) != count or len(set(tasks)) != count or tasks != sorted(tasks):
        raise ValueError(f"experiment requires all {count} unique tasks in sorted order")
    expected_arms = ARMS if experiment == "tau" else ("benign",)
    if tuple(value["matrix"]["arms"]) != expected_arms or value["matrix"]["retries"] != 0:
        raise ValueError("arm order/retry policy changed")
    if experiment == "tau":
        if (source["commit"], source["root_tree"], source["banking_tree"]) != (
            UPSTREAM_COMMIT,
            UPSTREAM_ROOT_TREE,
            BANKING_TREE,
        ):
            raise ValueError("upstream commitment changed")
        if (source["expected_task_count"], source["expected_document_count"]) != (97, 698):
            raise ValueError("upstream population changed")
        manifest = json.loads((EXPERIMENT_ROOT / "configs" / "upstream-manifest.json").read_text())
        population = sorted(
            Path(item["path"]).stem
            for item in manifest["files"]
            if item["path"].startswith("tasks/") and item["path"].endswith(".json")
        )
        if tasks != population:
            raise ValueError("τ tasks differ from the pinned population")
        profiles, targets = (
            value["tasks"]["attack_profiles"],
            value["poison_sampling"]["target_document_ids"],
        )
        if profiles != tau_attack_profiles(tasks):
            raise ValueError("legacy attack profiles or alternating additional profiles changed")
        if len(targets) != 70 or len(set(targets)) != 70:
            raise ValueError("poison document sample must contain seventy unique IDs")
        if digest(targets) != POISON_SAMPLE_SHA256:
            raise ValueError("the original seventy-document poison sample changed")
        commitment = {
            "seed": value["seed"],
            "tasks": tasks,
            "profiles": profiles,
            "targets": targets,
        }
        expected_checkout = "data/upstream/tau2-bench"
    else:
        if source["commit"] != SKILLSBENCH_COMMIT or source["expected_task_count"] != 85:
            raise ValueError("SkillsBench source commitment or population changed")
        if (
            digest(tasks) != source["task_population_sha256"]
            or digest(tasks) != SKILLSBENCH_TASK_POPULATION_SHA256
        ):
            raise ValueError("SkillsBench tasks differ from the pinned population")
        if value["acquisition"]["max_clarifications"] or value["acquisition"]["max_reads"]:
            raise ValueError("SkillsBench acquisition cannot clarify or query bank tools")
        commitment = {
            "seed": value["seed"],
            "tasks": tasks,
            "arms": ["benign"],
            "commit": source["commit"],
        }
        expected_checkout = "data/upstream/coevo-skills"
    if digest(commitment) != value["matrix_commitment"]:
        raise ValueError("task or poison sample differs from the frozen matrix")
    if source["upstream_checkout"] != expected_checkout:
        raise ValueError("upstream checkout must reside under the current experiment")
    for name in ("corpus_manifest", "runtime_lock"):
        target = Path(source[name])
        if target.is_absolute() or ".." in target.parts:
            raise ValueError("source manifest/runtime paths must remain inside the experiment")
        if "{" in str(target) or "}" in str(target):
            literal = str(target).replace("{task_id}", "")
            if (
                experiment != "skillsbench"
                or name != "runtime_lock"
                or str(target).count("{task_id}") != 1
                or "{" in literal
                or "}" in literal
                or not target.name.startswith("skillsbench-docker-")
            ):
                raise ValueError("runtime lock only supports the SkillsBench {task_id} template")
    retrieval = value["retrieval"]
    if (retrieval["bm25_top_k"], retrieval["dense_top_k"], retrieval["rrf_k"]) != (10, 10, 60):
        raise ValueError("hybrid retrieval parameters changed")
    if not retrieval["full_text"] or not retrieval["fail_closed"]:
        raise ValueError("retrieval must return full text and fail closed")
    provider = value["provider"]
    if not (
        (
            provider.get("model") in RESPONSES_MODELS
            and provider.get("transport") == "bedrock-responses"
        )
        or (
            provider.get("model") == MESSAGES_MODEL
            and provider.get("transport") == "bedrock-messages"
        )
    ):
        raise ValueError("model and supported Bedrock Mantle transport must match")
    if set(provider) != {"model", "transport", "region", "region_env", "api_key_env"}:
        raise ValueError("provider fields must use the Bedrock Mantle configuration")
    if provider["region"] is not None and provider["region"] not in BEDROCK_REGIONS:
        raise ValueError("unsupported GPT-5.x Bedrock region")
    if provider["model"] == MESSAGES_MODEL and provider["region"] not in {None, "us-east-1"}:
        raise ValueError("unsupported_region: Opus 4.8 Mantle requires us-east-1")
    if not all(
        isinstance(provider[name], str) and provider[name] for name in ("region_env", "api_key_env")
    ):
        raise ValueError("provider environment names must be nonempty")
    if value["embedding"]["vllm"] != "data/embedding/.venv/bin/vllm":
        raise ValueError("embedding runtime must reside under the current experiment")
    if experiment == "skillsbench" and (
        value["embedding"].get("chunks"),
        value["embedding"].get("chunk_tokens"),
        value["embedding"].get("chunk_overlap_tokens"),
    ) != (True, 2048, 128):
        raise ValueError(
            "SkillsBench public corpus requires 2048-token chunks with 128-token overlap"
        )
    from .runtime_controls import RuntimeControls

    RuntimeControls.from_dict(value["runtime"]["controls"])
    executor = value["runtime"].get("executor", "local-tools")
    if executor not in {"local-tools", "author-codex"}:
        raise ValueError("unsupported execution agent")
    controls = value["runtime"]["controls"]
    if executor != "author-codex" and (
        controls["assistant_completion_budget"] is None
        or any(controls[role]["max_output_tokens"] is None for role in ("agent", "user"))
    ):
        raise ValueError("null runtime output limits require the author Codex execution agent")
    if executor == "author-codex" and value["schema_version"] != "skillsbench.skill-evolution.v4":
        raise ValueError("author Codex requires the SkillsBench v4 namespace")
    if value["schema_version"] == "skillsbench.skill-evolution.v4":
        if executor != "author-codex":
            raise ValueError("SkillsBench v4 requires the author Codex execution agent")
        codex = value["runtime"].get("codex", {})
        required_codex = {
            "binary",
            "version",
            "binary_sha256",
            "evolution_timeout_seconds",
            "evaluation_timeout_seconds",
        }
        companion_fields = {"code_mode_host_binary", "code_mode_host_sha256"}
        if not (
            required_codex <= set(codex) <= required_codex | companion_fields
            and set(codex) & companion_fields in (set(), companion_fields)
        ):
            raise ValueError("Codex binary and both episode budgets must be explicit")
        if value["provider"]["model"] == "openai.gpt-5.6-terra" and not (
            companion_fields <= set(codex)
        ):
            raise ValueError("GPT-5.6 requires the pinned Codex code-mode companion")
        if not all(isinstance(codex[name], str) and codex[name] for name in ("binary", "version")):
            raise ValueError("Codex binary/version must be nonempty")
        pinned_hash = codex["binary_sha256"]
        if (
            not isinstance(pinned_hash, str)
            or len(pinned_hash) != 64
            or any(character not in "0123456789abcdef" for character in pinned_hash)
        ):
            raise ValueError("Codex binary hash must be pinned")
        if companion_fields <= set(codex):
            host_binary, host_hash = codex["code_mode_host_binary"], codex["code_mode_host_sha256"]
            if not isinstance(host_binary, str) or not host_binary:
                raise ValueError("Codex code-mode companion binary must be explicit")
            if (
                not isinstance(host_hash, str)
                or len(host_hash) != 64
                or any(character not in "0123456789abcdef" for character in host_hash)
            ):
                raise ValueError("Codex code-mode companion hash must be pinned")
        for name in ("evolution_timeout_seconds", "evaluation_timeout_seconds"):
            number = codex[name]
            if isinstance(number, bool) or not isinstance(number, int) or number <= 0:
                raise ValueError("Codex episode budgets must be positive integers")
    confidence = value["acquisition"]["min_document_confidence"]
    if (
        isinstance(confidence, bool)
        or not isinstance(confidence, (int, float))
        or not 0 <= confidence <= 1
    ):
        raise ValueError("acquisition.min_document_confidence must be between zero and one")
    limits = {
        "acquisition": {
            "max_searches": 30,
            "max_clarifications": 4,
            "max_reads": 10,
            "base_token_limit": 32768,
            "max_steps": 50,
        },
        "evolution": {
            "max_revisions": 15,
            "max_oracles": 5,
            "max_oracle_errors": 5,
            "revision_timeout_seconds": 3600,
        },
    }
    for group, caps in limits.items():
        for name, maximum in caps.items():
            number = value[group][name]
            minimum = 0 if name in ("max_clarifications", "max_reads") else 1
            if (
                isinstance(number, bool)
                or not isinstance(number, int)
                or not minimum <= number <= maximum
            ):
                raise ValueError(f"{group}.{name} must be between {minimum} and {maximum}")
    generator = value["roles"]["generator"]
    for name, maximum in (("max_turns", 120),):
        number = generator[name]
        if isinstance(number, bool) or not isinstance(number, int) or not 1 <= number <= maximum:
            raise ValueError(f"generator.{name} must be between 1 and {maximum}")
    verifier = value["roles"]["verifier"]
    for name, maximum in (("max_turns", 30), ("diagnosis_turns", 8)):
        number = verifier[name]
        if isinstance(number, bool) or not isinstance(number, int) or not 1 <= number <= maximum:
            raise ValueError(f"verifier.{name} must be between 1 and {maximum}")
    if generator["reasoning_effort"] not in ("medium", "high"):
        raise ValueError("Generator reasoning effort must be medium or high")
    for role in value["roles"].values():
        output_limit = role["max_output_tokens"]
        if output_limit is not None and (
            isinstance(output_limit, bool) or not isinstance(output_limit, int) or output_limit <= 0
        ):
            raise ValueError("role max_output_tokens must be positive or null")
    if (generator["context_window"], generator["context_beta"]) != (272000, 0.7):
        raise ValueError("Generator must use the fixed context budget")
    if generator["max_output_tokens"] not in (None, 32768):
        raise ValueError("Generator output limit must be 32768 or null")
    expected_input = math.floor(generator["context_window"] * generator["context_beta"]) - 32768
    if generator["max_input_tokens"] != expected_input:
        raise ValueError("Generator input budget differs from the fixed context admission reserve")
    return ExperimentSpec(path, value)
