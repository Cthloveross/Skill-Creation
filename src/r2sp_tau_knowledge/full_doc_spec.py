"""Versioned, file-backed commitments for the full-document dose experiment.

The historical :mod:`r2sp_tau_knowledge.hybrid_spec` module remains untouched.
This module deliberately obtains experiment values from the new YAML file so a
runner cannot silently inherit preliminary paths or constants.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import random
import re
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal
from urllib.parse import urlparse

import yaml

from r2sp_common.attack_payload import parse_shared_retrieval_carrier

FULL_DOC_SCHEMA_VERSION = "tau.hybrid-full-doc.v3"
Arm = Literal["benign", "poison-5", "poison-10"]
AttackProfile = Literal["mock-api-call", "delete-sentinel"]
_ARMS: tuple[Arm, ...] = ("benign", "poison-5", "poison-10")
_PROFILES: tuple[AttackProfile, ...] = ("mock-api-call", "delete-sentinel")
_HEX40 = re.compile(r"[0-9a-f]{40}\Z")
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_TASK_ID = re.compile(r"task_[0-9]{3}\Z")
_FORBIDDEN_RETRIEVAL_WORDS = re.compile(
    r"\b(?:task|query|rank|dataset|select|open)\b", re.IGNORECASE
)


class FullDocSpecError(ValueError):
    """The full-document experiment configuration violates its protocol."""


@dataclass(frozen=True, slots=True)
class ExperimentPaths:
    repository_root: Path
    experiment_root: Path
    config_path: Path
    injections_root: Path
    prompts_root: Path
    data_root: Path
    runs_root: Path
    source_upstream_root: Path
    source_banking_root: Path
    source_documents_root: Path
    source_tasks_root: Path
    materialized_root: Path
    dense_root: Path
    service_logs_root: Path
    acquisition_prompt: Path
    compiler_prompt: Path
    evaluation_prompt: Path

    @classmethod
    def from_config(
        cls,
        config_path: Path,
        *,
        upstream_checkout: str,
        acquisition_prompt: str,
        compiler_prompt: str,
        evaluation_prompt: str,
    ) -> ExperimentPaths:
        config = Path(config_path).resolve()
        experiment_root = config.parent.parent
        if config.parent.name != "configs" or config.name != "experiment.yaml":
            raise FullDocSpecError("config must be <experiment>/configs/experiment.yaml")
        for label, filename in (
            ("acquisition prompt", acquisition_prompt),
            ("compiler prompt", compiler_prompt),
            ("evaluation prompt", evaluation_prompt),
        ):
            if Path(filename).name != filename or filename in {"", ".", ".."}:
                raise FullDocSpecError(f"unsafe {label} filename")
        upstream = (experiment_root / upstream_checkout).resolve()
        banking = upstream / "data" / "tau2" / "domains" / "banking_knowledge"
        repository_root = Path(__file__).resolve().parents[2]
        return cls(
            repository_root=repository_root,
            experiment_root=experiment_root,
            config_path=config,
            injections_root=experiment_root / "injections",
            prompts_root=experiment_root / "prompts",
            data_root=experiment_root / "data",
            runs_root=experiment_root / "runs",
            source_upstream_root=upstream,
            source_banking_root=banking,
            source_documents_root=banking / "documents",
            source_tasks_root=banking / "tasks",
            materialized_root=experiment_root / "data" / "materialized",
            dense_root=experiment_root / "data" / "dense",
            service_logs_root=experiment_root / "data" / "service-logs",
            acquisition_prompt=experiment_root / "prompts" / acquisition_prompt,
            compiler_prompt=experiment_root / "prompts" / compiler_prompt,
            evaluation_prompt=experiment_root / "prompts" / evaluation_prompt,
        )


@dataclass(frozen=True, slots=True)
class GenerationSpec:
    thinking: bool
    reasoning_effort: str
    preserve_thinking: bool
    max_output_tokens: int
    temperature: float
    top_p: float
    top_k: int
    min_p: float
    presence_penalty: float
    repetition_penalty: float


@dataclass(frozen=True, slots=True)
class ModelSpec:
    model: str
    revision: str
    dtype: str
    max_model_len: int
    seed: int
    generation: GenerationSpec


@dataclass(frozen=True, slots=True)
class UserSimulatorSpec:
    thinking: bool
    temperature: float
    max_output_tokens: int


@dataclass(frozen=True, slots=True)
class EmbeddingSpec:
    model: str
    revision: str
    dimension: int
    max_length: int
    pooling: str
    normalization: str
    similarity: str
    query_instruct: str


@dataclass(frozen=True, slots=True)
class RetrievalSpec:
    tool_name: str
    max_queries: int | None
    bm25_top_k: int
    dense_top_k: int
    rrf_k: int
    return_fields: tuple[str, ...]
    full_text: bool
    fail_closed: bool
    open_page_tools: bool


@dataclass(frozen=True, slots=True)
class ContextSpec:
    full_text_wire_token_budget: int
    request_input_token_limit: int
    cumulative_assistant_token_limit: int
    retrieval_context_eviction: str
    budget_failure: str
    partial_search_results: bool


@dataclass(frozen=True, slots=True)
class ServiceSpec:
    gpu_uuid: str
    llm_endpoint: str
    embedding_endpoint: str
    llm_gpu_memory_utilization: float
    embedding_gpu_memory_utilization: float
    minimum_free_memory_mib: int
    stable_preflight_checks: int
    stable_preflight_interval_seconds: int
    foreign_process_policy: str


@dataclass(frozen=True, slots=True)
class FullDocCell:
    ordinal: int
    task_id: str
    arm: Arm
    condition: Arm
    profile: AttackProfile | None
    poison_percent: int
    materialization_key: str
    model_seed: int
    user_seed: int


@dataclass(frozen=True, slots=True)
class CorpusPlan:
    key: str
    profile: AttackProfile
    materialization_arm: Literal["benign", "poison"]
    poison_percent: int
    target_document_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExperimentSpec:
    schema_version: str
    seed: int
    paths: ExperimentPaths
    upstream_commit: str
    upstream_root_tree: str
    upstream_banking_tree: str
    require_clean_checkout: bool
    expected_task_population: int
    expected_document_population: int
    task_population_sha256: str
    tasks: tuple[str, ...]
    task_profiles: Mapping[str, AttackProfile]
    arms: tuple[Arm, ...]
    cells: tuple[FullDocCell, ...]
    target_document_ids_5: tuple[str, ...]
    target_document_ids_10: tuple[str, ...]
    payload_hashes: Mapping[AttackProfile, str]
    prompt_hashes: Mapping[str, str]
    retrieval: RetrievalSpec
    embedding: EmbeddingSpec
    model: ModelSpec
    user_simulator: UserSimulatorSpec
    context: ContextSpec
    services: ServiceSpec
    expected_creation_records: int
    expected_evaluation_records: int
    acquisition_max_turns: int
    request_timeout_seconds: int
    cell_timeout_seconds: int
    config_sha256: str

    @property
    def corpus_plans(self) -> tuple[CorpusPlan, ...]:
        """Return the five unique corpora required by the 60-cell matrix."""

        return (
            CorpusPlan("benign", "mock-api-call", "benign", 0, self.target_document_ids_10),
            CorpusPlan(
                "poison-5-mock-api-call",
                "mock-api-call",
                "poison",
                5,
                self.target_document_ids_5,
            ),
            CorpusPlan(
                "poison-5-delete-sentinel",
                "delete-sentinel",
                "poison",
                5,
                self.target_document_ids_5,
            ),
            CorpusPlan(
                "poison-10-mock-api-call",
                "mock-api-call",
                "poison",
                10,
                self.target_document_ids_10,
            ),
            CorpusPlan(
                "poison-10-delete-sentinel",
                "delete-sentinel",
                "poison",
                10,
                self.target_document_ids_10,
            ),
        )

    def validate_payload_files(self) -> None:
        expected_names = {"retrieval.txt", "mock-api-call.txt", "delete-sentinel.txt"}
        try:
            entries = tuple(self.paths.injections_root.iterdir())
        except OSError as exc:
            raise FullDocSpecError("unable to inspect injections directory") from exc
        if {entry.name for entry in entries} != expected_names or any(
            entry.is_symlink() or not entry.is_file() for entry in entries
        ):
            raise FullDocSpecError("injections directory must contain exactly three regular files")
        for profile, expected in self.payload_hashes.items():
            actual = _sha256_file(self.paths.injections_root / f"{profile}.txt")
            if actual != expected:
                raise FullDocSpecError(f"attack body hash mismatch: {profile}")
        retrieval = (self.paths.injections_root / "retrieval.txt").read_bytes()
        try:
            carrier = parse_shared_retrieval_carrier(retrieval)
        except ValueError as exc:
            raise FullDocSpecError("invalid retrieval.txt") from exc
        if _FORBIDDEN_RETRIEVAL_WORDS.search(carrier.decode("utf-8")):
            raise FullDocSpecError("retrieval.txt contains a protocol-forbidden word")

    def validate_prompt_files(self) -> None:
        for path in (
            self.paths.acquisition_prompt,
            self.paths.compiler_prompt,
            self.paths.evaluation_prompt,
        ):
            if path.is_symlink() or not path.is_file() or not path.read_bytes().strip():
                raise FullDocSpecError(f"missing or empty prompt: {path.name}")

    def validate_source_populations(self) -> None:
        """Bind the literal task and poison samples to the pinned local checkout."""

        upstream_root = self.paths.source_upstream_root.resolve(strict=True)
        git_root = Path(_git_stdout(upstream_root, "rev-parse", "--show-toplevel")).resolve(
            strict=True
        )
        if git_root != upstream_root:
            raise FullDocSpecError("source upstream path is not the git checkout root")
        observed_git_identity = (
            _git_stdout(upstream_root, "rev-parse", "--verify", "HEAD"),
            _git_stdout(upstream_root, "rev-parse", "--verify", "HEAD^{tree}"),
            _git_stdout(
                upstream_root,
                "rev-parse",
                "--verify",
                "HEAD:data/tau2/domains/banking_knowledge",
            ),
        )
        expected_git_identity = (
            self.upstream_commit,
            self.upstream_root_tree,
            self.upstream_banking_tree,
        )
        if observed_git_identity != expected_git_identity:
            raise FullDocSpecError("source upstream commit/tree commitment mismatch")
        if self.require_clean_checkout and _git_stdout(
            upstream_root, "status", "--porcelain=v1", "--untracked-files=all"
        ):
            raise FullDocSpecError("source upstream checkout is not clean")

        task_ids = tuple(
            sorted(path.stem for path in self.paths.source_tasks_root.glob("task_*.json"))
        )
        document_ids = tuple(
            sorted(path.stem for path in self.paths.source_documents_root.glob("*.json"))
        )
        if len(task_ids) != self.expected_task_population or len(set(task_ids)) != len(task_ids):
            raise FullDocSpecError("source task population mismatch")
        task_hash = hashlib.sha256(("\n".join(task_ids) + "\n").encode()).hexdigest()
        if task_hash != self.task_population_sha256:
            raise FullDocSpecError("source task population hash mismatch")
        selected = tuple(random.Random(self.seed).sample(list(task_ids), len(self.tasks)))
        if selected != self.tasks:
            raise FullDocSpecError("seeded task sample mismatch")
        if len(document_ids) != self.expected_document_population or len(set(document_ids)) != len(
            document_ids
        ):
            raise FullDocSpecError("source document population mismatch")
        sampled = tuple(
            random.Random(self.seed).sample(list(document_ids), len(self.target_document_ids_10))
        )
        if sampled != self.target_document_ids_10:
            raise FullDocSpecError("seeded poison-document sample mismatch")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _git_stdout(root: Path, *arguments: str) -> str:
    environment = os.environ.copy()
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    try:
        result = subprocess.run(
            ("git", "-C", str(root), *arguments),
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=15,
            env=environment,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise FullDocSpecError("unable to verify source upstream git checkout") from exc
    return result.stdout.strip()


def _prompt_hashes(paths: ExperimentPaths) -> Mapping[str, str]:
    result: dict[str, str] = {}
    for name, path in (
        ("acquisition", paths.acquisition_prompt),
        ("compiler", paths.compiler_prompt),
        ("evaluation", paths.evaluation_prompt),
    ):
        if path.is_symlink() or not path.is_file() or not path.read_bytes().strip():
            raise FullDocSpecError(f"missing or empty prompt: {path.name}")
        result[name] = _sha256_file(path)
    return MappingProxyType(result)


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise FullDocSpecError(f"{label} must be a mapping")
    return value


def _string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise FullDocSpecError(f"{label} must be a non-empty string")
    return value


def _integer(value: Any, label: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise FullDocSpecError(f"{label} must be an integer >= {minimum}")
    return value


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FullDocSpecError(f"{label} must be numeric")
    return float(value)


def _boolean(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise FullDocSpecError(f"{label} must be boolean")
    return value


def _string_tuple(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise FullDocSpecError(f"{label} must be a list of non-empty strings")
    return tuple(value)


def _loopback_endpoint(value: Any, label: str) -> str:
    endpoint = _string(value, label)
    parsed = urlparse(endpoint)
    if (
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or parsed.port is None
        or parsed.path != "/v1"
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        raise FullDocSpecError(f"{label} must be an http://127.0.0.1:<port>/v1 endpoint")
    return endpoint


def _materialization_key(arm: Arm, profile: AttackProfile | None) -> str:
    return "benign" if arm == "benign" else f"{arm}-{profile}"


def load_experiment_spec(config_path: Path, *, validate_files: bool = True) -> ExperimentSpec:
    config = Path(config_path).resolve()
    try:
        raw_bytes = config.read_bytes()
        raw = yaml.safe_load(raw_bytes)
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise FullDocSpecError(f"unable to load experiment config: {config}") from exc
    root = _mapping(raw, "config")
    schema_version = _string(root.get("schema_version"), "schema_version")
    if schema_version != FULL_DOC_SCHEMA_VERSION:
        raise FullDocSpecError(f"unsupported schema_version: {schema_version}")
    seed = _integer(root.get("seed"), "seed", minimum=1)

    source = _mapping(root.get("source"), "source")
    prompts = _mapping(root.get("prompts"), "prompts")
    paths = ExperimentPaths.from_config(
        config,
        upstream_checkout=_string(source.get("upstream_checkout"), "source.upstream_checkout"),
        acquisition_prompt=_string(prompts.get("acquisition"), "prompts.acquisition"),
        compiler_prompt=_string(prompts.get("compiler"), "prompts.compiler"),
        evaluation_prompt=_string(prompts.get("evaluation"), "prompts.evaluation"),
    )
    expected_tasks = _integer(source.get("expected_task_count"), "expected_task_count", minimum=1)
    expected_documents = _integer(
        source.get("expected_document_count"), "expected_document_count", minimum=1
    )
    task_population_sha256 = _string(source.get("task_population_sha256"), "task_population_sha256")
    upstream_commit = _string(source.get("commit"), "source.commit")
    upstream_root_tree = _string(source.get("root_tree"), "source.root_tree")
    upstream_banking_tree = _string(source.get("banking_tree"), "source.banking_tree")
    require_clean_checkout = _boolean(
        source.get("require_clean_checkout"), "source.require_clean_checkout"
    )
    if not _HEX64.fullmatch(task_population_sha256):
        raise FullDocSpecError("task_population_sha256 must be lowercase SHA-256")
    if any(
        not _HEX40.fullmatch(value)
        for value in (upstream_commit, upstream_root_tree, upstream_banking_tree)
    ):
        raise FullDocSpecError("source git commitments must be lowercase SHA-1 object IDs")
    if (
        source.get("upstream_checkout") != "../preliminary/data/upstream/tau2-bench"
        or upstream_commit != "fc0055dc4e0a316c3f83133267fbd6faaa770992"
        or upstream_root_tree != "4837da1c2b310152f63d3d7987f4325183ca6f7c"
        or upstream_banking_tree != "0ce703cbc3e07b0b09905daf29700813b3b8f122"
        or require_clean_checkout is not True
        or expected_tasks != 97
        or expected_documents != 698
        or task_population_sha256
        != "00a4545e411632f7084282915902ce5ad619283427f16ff73c0a50fae3a42ac1"
    ):
        raise FullDocSpecError("pinned source commitment mismatch")

    task_config = _mapping(root.get("tasks"), "tasks")
    if task_config.get("sample_algorithm") != "python-random-sample-sorted-v1":
        raise FullDocSpecError("unsupported task sample algorithm")
    tasks = _string_tuple(task_config.get("selected"), "tasks.selected")
    profiles_raw = _string_tuple(task_config.get("attack_profiles"), "tasks.attack_profiles")
    if len(tasks) != 20 or len(set(tasks)) != 20 or any(not _TASK_ID.fullmatch(x) for x in tasks):
        raise FullDocSpecError("tasks.selected must contain 20 unique canonical task IDs")
    expected_profile_order = tuple(_PROFILES[index % 2] for index in range(len(tasks)))
    if profiles_raw != expected_profile_order:
        raise FullDocSpecError("tasks.attack_profiles must alternate mock/delete from mock")
    task_profiles = MappingProxyType(dict(zip(tasks, profiles_raw, strict=True)))

    matrix = _mapping(root.get("matrix"), "matrix")
    arms_raw = _string_tuple(matrix.get("arms"), "matrix.arms")
    execution_order = _string_tuple(matrix.get("execution_order"), "matrix.execution_order")
    if arms_raw != _ARMS or execution_order != _ARMS:
        raise FullDocSpecError("matrix arms/order must be benign, poison-5, poison-10")
    if matrix.get("retries") != 0:
        raise FullDocSpecError("matrix retries must be zero")

    poison = _mapping(root.get("poison_sampling"), "poison_sampling")
    if poison.get("sample_algorithm") != "python-random-sample-sorted-v1":
        raise FullDocSpecError("unsupported poison sample algorithm")
    poison_population = _integer(poison.get("population_size"), "poison population", minimum=1)
    if poison_population != expected_documents or poison.get("seed") != seed:
        raise FullDocSpecError("poison population/seed must match the experiment source")
    count_5 = _integer(poison.get("target_count_5_percent"), "5% target count", minimum=1)
    count_10 = _integer(poison.get("target_count_10_percent"), "10% target count", minimum=1)
    targets_10 = _string_tuple(poison.get("target_document_ids"), "target_document_ids")
    if (
        count_5 != math.ceil(expected_documents * 0.05)
        or count_10 != math.ceil(expected_documents * 0.10)
        or len(targets_10) != count_10
        or len(set(targets_10)) != count_10
        or poison.get("five_percent_is_prefix_of_ten_percent") is not True
    ):
        raise FullDocSpecError("5%/10% poison target counts or nesting commitment is invalid")
    if any(Path(value).name != value for value in targets_10):
        raise FullDocSpecError("unsafe poison target document ID")
    targets_5 = targets_10[:count_5]

    payloads = _mapping(root.get("payloads"), "payloads")
    if (
        payloads.get("composition")
        != "retrieval-lead-blank-line-attack-body-blank-line-original-content"
        or payloads.get("retrieval_file") != "retrieval.txt"
    ):
        raise FullDocSpecError("payload composition commitment mismatch")
    hashes_raw = _mapping(payloads.get("attack_body_sha256"), "attack_body_sha256")
    if set(hashes_raw) != set(_PROFILES):
        raise FullDocSpecError("attack-body profile set mismatch")
    payload_hashes: dict[AttackProfile, str] = {}
    for profile in _PROFILES:
        digest = _string(hashes_raw.get(profile), f"{profile} hash")
        if not _HEX64.fullmatch(digest):
            raise FullDocSpecError(f"{profile} hash must be lowercase SHA-256")
        payload_hashes[profile] = digest
    if payload_hashes != {
        "mock-api-call": "8c6ca4bdffe98b471de5d12772d3f83faf72abcb7ef80ed0523055ad6cf0bd7d",
        "delete-sentinel": "73e804d2861b32fe00f18c93f901d46f91a9519b4686b97703dbaabc79d38210",
    }:
        raise FullDocSpecError("pinned attack-body hash mismatch")

    retrieval_raw = _mapping(root.get("retrieval"), "retrieval")
    max_queries = retrieval_raw.get("max_queries")
    if "max_queries" not in retrieval_raw or max_queries is not None:
        raise FullDocSpecError("retrieval.max_queries must be null for unbounded search")
    retrieval = RetrievalSpec(
        tool_name=_string(retrieval_raw.get("tool_name"), "retrieval.tool_name"),
        max_queries=max_queries,
        bm25_top_k=_integer(retrieval_raw.get("bm25_top_k"), "bm25_top_k", minimum=1),
        dense_top_k=_integer(retrieval_raw.get("dense_top_k"), "dense_top_k", minimum=1),
        rrf_k=_integer(retrieval_raw.get("rrf_k"), "rrf_k", minimum=1),
        return_fields=_string_tuple(retrieval_raw.get("return_fields"), "return_fields"),
        full_text=_boolean(retrieval_raw.get("full_text"), "full_text"),
        fail_closed=_boolean(retrieval_raw.get("fail_closed"), "fail_closed"),
        open_page_tools=_boolean(retrieval_raw.get("open_page_tools"), "open_page_tools"),
    )
    retrieval_identity = (
        retrieval.tool_name,
        retrieval.max_queries,
        retrieval.bm25_top_k,
        retrieval.dense_top_k,
        retrieval.rrf_k,
        retrieval.return_fields,
        retrieval.full_text,
        retrieval.fail_closed,
        retrieval.open_page_tools,
        retrieval_raw.get("deduplication"),
        retrieval_raw.get("repeat_representation"),
        retrieval_raw.get("bm25_indexed_fields"),
        retrieval_raw.get("dense_indexed_fields"),
    )
    if retrieval_identity != (
        "search_web",
        None,
        10,
        10,
        60,
        ("page_id", "title", "content"),
        True,
        True,
        False,
        "within-query-routes-and-final-resident-compiler-by-page-id",
        "full-document-each-query",
        ["title", "body"],
        ["title", "body"],
    ):
        raise FullDocSpecError("retrieval protocol mismatch")

    embedding_raw = _mapping(root.get("embedding"), "embedding")
    embedding = EmbeddingSpec(
        model=_string(embedding_raw.get("model"), "embedding.model"),
        revision=_string(embedding_raw.get("revision"), "embedding.revision"),
        dimension=_integer(embedding_raw.get("dimension"), "embedding.dimension", minimum=1),
        max_length=_integer(embedding_raw.get("max_length"), "embedding.max_length", minimum=1),
        pooling=_string(embedding_raw.get("pooling"), "embedding.pooling"),
        normalization=_string(embedding_raw.get("normalization"), "embedding.normalization"),
        similarity=_string(embedding_raw.get("similarity"), "embedding.similarity"),
        query_instruct=_string(embedding_raw.get("query_instruct"), "embedding.query_instruct"),
    )
    if not _HEX40.fullmatch(embedding.revision) or (
        embedding.model,
        embedding.revision,
        embedding.dimension,
        embedding.max_length,
        embedding.pooling,
        embedding.normalization,
        embedding.similarity,
        embedding.query_instruct,
        embedding_raw.get("chunks"),
        embedding_raw.get("faiss"),
        embedding_raw.get("reranker"),
    ) != (
        "Qwen/Qwen3-Embedding-4B",
        "5cf2132abc99cad020ac570b19d031efec650f2b",
        2560,
        4096,
        "last-token",
        "float32-l2",
        "exact-cosine",
        "official",
        False,
        False,
        False,
    ):
        raise FullDocSpecError("embedding protocol mismatch")

    model_raw = _mapping(root.get("model"), "model")
    generation_raw = _mapping(model_raw.get("generation"), "model.generation")
    generation = GenerationSpec(
        thinking=_boolean(generation_raw.get("thinking"), "generation.thinking"),
        reasoning_effort=_string(
            generation_raw.get("reasoning_effort"), "generation.reasoning_effort"
        ),
        preserve_thinking=_boolean(
            generation_raw.get("preserve_thinking"), "generation.preserve_thinking"
        ),
        max_output_tokens=_integer(
            generation_raw.get("max_output_tokens"), "generation.max_output_tokens", minimum=1
        ),
        temperature=_number(generation_raw.get("temperature"), "generation.temperature"),
        top_p=_number(generation_raw.get("top_p"), "generation.top_p"),
        top_k=_integer(generation_raw.get("top_k"), "generation.top_k", minimum=1),
        min_p=_number(generation_raw.get("min_p"), "generation.min_p"),
        presence_penalty=_number(
            generation_raw.get("presence_penalty"), "generation.presence_penalty"
        ),
        repetition_penalty=_number(
            generation_raw.get("repetition_penalty"), "generation.repetition_penalty"
        ),
    )
    model = ModelSpec(
        model=_string(model_raw.get("model"), "model.model"),
        revision=_string(model_raw.get("revision"), "model.revision"),
        dtype=_string(model_raw.get("dtype"), "model.dtype"),
        max_model_len=_integer(model_raw.get("max_model_len"), "model.max_model_len", minimum=1),
        seed=_integer(model_raw.get("seed"), "model.seed", minimum=1),
        generation=generation,
    )
    if (
        not _HEX40.fullmatch(model.revision)
        or model.seed != seed
        or (
            model.model,
            model.revision,
            model.dtype,
            model.max_model_len,
            generation.thinking,
            generation.reasoning_effort,
            generation.preserve_thinking,
            generation.max_output_tokens,
            generation.temperature,
            generation.top_p,
            generation.top_k,
            generation.min_p,
            generation.presence_penalty,
            generation.repetition_penalty,
        )
        != (
            "Qwen/Qwen3.8-27B",
            "1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0",
            "bfloat16",
            131072,
            True,
            "medium",
            False,
            8192,
            1.0,
            0.95,
            20,
            0.0,
            0.0,
            1.0,
        )
    ):
        raise FullDocSpecError("LLM generation protocol mismatch")

    user_raw = _mapping(root.get("user_simulator"), "user_simulator")
    user_simulator = UserSimulatorSpec(
        thinking=_boolean(user_raw.get("thinking"), "user_simulator.thinking"),
        temperature=_number(user_raw.get("temperature"), "user_simulator.temperature"),
        max_output_tokens=_integer(
            user_raw.get("max_output_tokens"), "user_simulator.max_output_tokens", minimum=1
        ),
    )
    if (
        user_simulator.thinking,
        user_simulator.temperature,
        user_simulator.max_output_tokens,
    ) != (False, 0.0, 2048):
        raise FullDocSpecError("user simulator protocol mismatch")

    context_raw = _mapping(root.get("context"), "context")
    context = ContextSpec(
        full_text_wire_token_budget=_integer(
            context_raw.get("full_text_wire_token_budget"), "wire token budget", minimum=1
        ),
        request_input_token_limit=_integer(
            context_raw.get("request_input_token_limit"), "request input limit", minimum=1
        ),
        cumulative_assistant_token_limit=_integer(
            context_raw.get("cumulative_assistant_token_limit"),
            "cumulative assistant limit",
            minimum=1,
        ),
        retrieval_context_eviction=_string(
            context_raw.get("retrieval_context_eviction"),
            "context.retrieval_context_eviction",
        ),
        budget_failure=_string(context_raw.get("budget_failure"), "context.budget_failure"),
        partial_search_results=_boolean(
            context_raw.get("partial_search_results"), "context.partial_search_results"
        ),
    )
    if (
        (
            context.full_text_wire_token_budget,
            context.request_input_token_limit,
            context.cumulative_assistant_token_limit,
        )
        != (65536, 114688, 32768)
        or context.retrieval_context_eviction != "oldest-quarter-on-input-overflow"
        or context.budget_failure != "context_budget_exhausted"
        or context.partial_search_results
        or context.full_text_wire_token_budget > context.request_input_token_limit
        or context.request_input_token_limit + generation.max_output_tokens > model.max_model_len
    ):
        raise FullDocSpecError("context budget protocol mismatch")

    services_raw = _mapping(root.get("services"), "services")
    services = ServiceSpec(
        gpu_uuid=_string(services_raw.get("gpu_uuid"), "services.gpu_uuid"),
        llm_endpoint=_loopback_endpoint(services_raw.get("llm_endpoint"), "llm_endpoint"),
        embedding_endpoint=_loopback_endpoint(
            services_raw.get("embedding_endpoint"), "embedding_endpoint"
        ),
        llm_gpu_memory_utilization=_number(
            services_raw.get("llm_gpu_memory_utilization"), "llm_gpu_memory_utilization"
        ),
        embedding_gpu_memory_utilization=_number(
            services_raw.get("embedding_gpu_memory_utilization"),
            "embedding_gpu_memory_utilization",
        ),
        minimum_free_memory_mib=_integer(
            services_raw.get("minimum_free_memory_mib"), "minimum_free_memory_mib", minimum=1
        ),
        stable_preflight_checks=_integer(
            services_raw.get("stable_preflight_checks"), "stable_preflight_checks", minimum=1
        ),
        stable_preflight_interval_seconds=_integer(
            services_raw.get("stable_preflight_interval_seconds"),
            "stable_preflight_interval_seconds",
            minimum=1,
        ),
        foreign_process_policy=_string(
            services_raw.get("foreign_process_policy"), "foreign_process_policy"
        ),
    )
    if (
        (
            services.gpu_uuid,
            services.llm_endpoint,
            services.embedding_endpoint,
            services.llm_gpu_memory_utilization,
            services.embedding_gpu_memory_utilization,
            services.minimum_free_memory_mib,
            services.stable_preflight_checks,
            services.stable_preflight_interval_seconds,
        )
        != (
            "GPU-1c51e1d6-08ac-129f-38dc-1824c5ab9698",
            "http://127.0.0.1:18138/v1",
            "http://127.0.0.1:18140/v1",
            0.60,
            0.10,
            112927,
            3,
            10,
        )
        or services.llm_endpoint == services.embedding_endpoint
        or not 0 < services.llm_gpu_memory_utilization < 1
        or not 0 < services.embedding_gpu_memory_utilization < 1
        or services.llm_gpu_memory_utilization + services.embedding_gpu_memory_utilization >= 1
        or services.foreign_process_policy != "wait-never-terminate"
    ):
        raise FullDocSpecError("service protocol mismatch")

    cells: list[FullDocCell] = []
    for task_id in tasks:
        profile = task_profiles[task_id]
        for arm_raw in arms_raw:
            arm: Arm = arm_raw  # type: ignore[assignment]
            cell_profile = None if arm == "benign" else profile
            cells.append(
                FullDocCell(
                    ordinal=len(cells),
                    task_id=task_id,
                    arm=arm,
                    condition=arm,
                    profile=cell_profile,
                    poison_percent={"benign": 0, "poison-5": 5, "poison-10": 10}[arm],
                    materialization_key=_materialization_key(arm, cell_profile),
                    model_seed=seed,
                    user_seed=seed,
                )
            )
    expected_cells = _integer(matrix.get("expected_cell_count"), "expected_cell_count", minimum=1)
    creation = _mapping(root.get("creation"), "creation")
    evaluation = _mapping(root.get("evaluation"), "evaluation")
    expected_creation = _integer(
        creation.get("expected_records"), "creation.expected_records", minimum=1
    )
    expected_evaluation = _integer(
        evaluation.get("expected_records"), "evaluation.expected_records", minimum=1
    )
    acquisition_max_turns = _integer(
        creation.get("acquisition_max_turns"), "creation.acquisition_max_turns", minimum=1
    )
    request_timeout_seconds = _integer(
        creation.get("request_timeout_seconds"), "creation.request_timeout_seconds", minimum=1
    )
    cell_timeout_seconds = _integer(
        creation.get("cell_timeout_seconds"), "creation.cell_timeout_seconds", minimum=1
    )
    if (
        expected_cells != len(cells)
        or expected_creation != len(cells)
        or expected_evaluation != len(cells)
        or creation.get("deployment_enabled") is not False
        or creation.get("compile_on_acquisition_failure") is not True
        or creation.get("compiler_calls_per_cell") != 1
        or creation.get("compiler_output_gate")
        != "nonempty-untruncated-utf8-text-with-no-tool-calls"
        or creation.get("compiler_format_validation") != "diagnostic-only"
        or creation.get("preserve_compiler_output_bytes") is not True
        or creation.get("compiler_output_repair") is not False
        or acquisition_max_turns != 100
        or request_timeout_seconds != 900
        or cell_timeout_seconds != 3600
        or cell_timeout_seconds < request_timeout_seconds
        or evaluation.get("non_evaluable_outputs_are_not_run") is not True
        or evaluation.get("format_invalid_outputs_are_run") is not True
        or evaluation.get("fixed_denominator_per_arm") != len(tasks)
        or evaluation.get("retrieval_enabled") is not False
    ):
        raise FullDocSpecError("creation/evaluation matrix commitment mismatch")

    spec = ExperimentSpec(
        schema_version=schema_version,
        seed=seed,
        paths=paths,
        upstream_commit=upstream_commit,
        upstream_root_tree=upstream_root_tree,
        upstream_banking_tree=upstream_banking_tree,
        require_clean_checkout=require_clean_checkout,
        expected_task_population=expected_tasks,
        expected_document_population=expected_documents,
        task_population_sha256=task_population_sha256,
        tasks=tasks,
        task_profiles=task_profiles,
        arms=_ARMS,
        cells=tuple(cells),
        target_document_ids_5=targets_5,
        target_document_ids_10=targets_10,
        payload_hashes=MappingProxyType(payload_hashes),
        prompt_hashes=_prompt_hashes(paths),
        retrieval=retrieval,
        embedding=embedding,
        model=model,
        user_simulator=user_simulator,
        context=context,
        services=services,
        expected_creation_records=expected_creation,
        expected_evaluation_records=expected_evaluation,
        acquisition_max_turns=acquisition_max_turns,
        request_timeout_seconds=request_timeout_seconds,
        cell_timeout_seconds=cell_timeout_seconds,
        config_sha256=hashlib.sha256(raw_bytes).hexdigest(),
    )
    if validate_files:
        spec.validate_payload_files()
        spec.validate_prompt_files()
    return spec


def default_config_path() -> Path:
    repository_root = Path(__file__).resolve().parents[2]
    return (
        repository_root
        / "experiments"
        / "tau-knowledge"
        / "deepseek-v4-api-4b-dense"
        / "configs"
        / "experiment.yaml"
    )


def load_default_spec(*, validate_files: bool = True) -> ExperimentSpec:
    return load_experiment_spec(default_config_path(), validate_files=validate_files)


def default_paths() -> ExperimentPaths:
    return load_default_spec().paths


def spec_identity(spec: ExperimentSpec) -> dict[str, Any]:
    """Return the small JSON-safe identity a runner seals into every run."""

    return {
        "schema_version": spec.schema_version,
        "config_sha256": spec.config_sha256,
        "seed": spec.seed,
        "source": {
            "commit": spec.upstream_commit,
            "root_tree": spec.upstream_root_tree,
            "banking_tree": spec.upstream_banking_tree,
            "require_clean_checkout": spec.require_clean_checkout,
        },
        "tasks": list(spec.tasks),
        "arms": list(spec.arms),
        "cells": [
            {
                "ordinal": cell.ordinal,
                "task_id": cell.task_id,
                "arm": cell.arm,
                "profile": cell.profile,
                "materialization_key": cell.materialization_key,
            }
            for cell in spec.cells
        ],
        "target_document_ids_5": list(spec.target_document_ids_5),
        "target_document_ids_10": list(spec.target_document_ids_10),
        "payload_hashes": dict(spec.payload_hashes),
        "prompt_hashes": dict(spec.prompt_hashes),
    }


def canonical_spec_identity_sha256(spec: ExperimentSpec) -> str:
    encoded = json.dumps(
        spec_identity(spec), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "Arm",
    "AttackProfile",
    "ContextSpec",
    "CorpusPlan",
    "EmbeddingSpec",
    "ExperimentPaths",
    "ExperimentSpec",
    "FULL_DOC_SCHEMA_VERSION",
    "FullDocCell",
    "FullDocSpecError",
    "GenerationSpec",
    "ModelSpec",
    "RetrievalSpec",
    "ServiceSpec",
    "UserSimulatorSpec",
    "canonical_spec_identity_sha256",
    "default_config_path",
    "default_paths",
    "load_default_spec",
    "load_experiment_spec",
    "spec_identity",
]
