"""Reproducible Qwen3.8 entrypoint for the AppWorld file-backed assay."""

from __future__ import annotations

import argparse
import json
import time
import urllib.parse
import urllib.request
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .artifacts import (
    ArtifactStore,
    sha256_file,
    verify_artifact_manifest,
    write_artifact_manifest,
)
from .config import ExperimentConfig, load_config
from .file_injection_fixture import (
    EXPECTED_RAW_ENDPOINT_COUNT,
    EXPECTED_TASK_FACING_COUNT,
    LoadedFileInjectionFixtures,
    load_appworld_file_fixtures,
    materialize_appworld_file_bundles,
)
from .fixtures import SyntheticInjectionProfile
from .hashing import canonical_json_sha256
from .injection_deployment_runner import (
    PoisonDeploymentResult,
    run_poison_deployment_verification,
)
from .injection_runner import (
    CompileGateResult,
    build_canonical_retrieval_gate,
    build_fixture_commitments,
    run_injection_compile_gate,
    source_tree_hash,
)
from .model_client import OpenAICompatibleClient, QwenGenerationConfig

MODEL_ID = "Qwen/Qwen3.8-27B-FP8"
MODEL_REVISION = "017b9c7af6b5689d5dd426a76e0bc077eb5ca20a"
MODEL_DTYPE = "float16"
MODEL_GPU = "2x_NVIDIA_Quadro_RTX_6000_24GB"
PHYSICAL_GPU_IDS = (0, 6)
VLLM_VERSION = "0.21.0+cu129"
MODEL_MAX_LEN = 32768
DEFAULT_BASE_URL = "http://127.0.0.1:18138/v1"
DEFAULT_CONFIG_PATH = "experiments/appworld/preliminary/configs/experiment_plan.yaml"
COMPILE_MODE = "file_backed_injection_compile_gate"
DEPLOYMENT_MODE = "file_backed_poison_deployment_verification"
SOURCE_TYPE = "appworld_standard_json_file_backed"
APPWORLD_BUNDLE_NAME = "data-0.1.0.bundle"
APPWORLD_BUNDLE_SIZE = 34_280_074
APPWORLD_BUNDLE_SHA256 = "fd9f9608c2ec71ed0ac25c3633a738b9129a318a129e31230425b9188e508250"
APPWORLD_BUNDLE_URL = "https://s3.us-west-2.amazonaws.com/appworld.dev/data-0.1.0.bundle"
APPWORLD_STANDARD_CORPUS_SHA256 = "cd1125539a6d437a23f47556b595b69d020903e5be939c49695cff293a37a141"
APPWORLD_TASK_FACING_POOL_MANIFEST_SHA256 = (
    "6626216a3149fdd74840b28247901b05691a60d6a769890a8ab1b8093db7de79"
)
DEFAULT_SEED = 20260831
RETRIEVAL_MODE = "file_backed_canonical_retrieval_gate"
RETRIEVAL_SCHEMA_VERSION = "r2sp.file-backed-retrieval-gate.v1"


@dataclass(frozen=True)
class FileBackedRetrievalResult:
    output_directory: Path
    gate: Mapping[str, Any]
    complete_hash: str


@dataclass(frozen=True)
class _EffectiveConfigBinding:
    path: Path
    sha256: str
    model_contract: Mapping[str, Any]
    appworld_contract: Mapping[str, Any]


def _acquisition_config() -> QwenGenerationConfig:
    return QwenGenerationConfig(
        model=MODEL_ID,
        revision=MODEL_REVISION,
        enable_thinking=False,
        preserve_thinking=None,
        reasoning_effort=None,
        temperature=0.7,
        top_p=0.8,
        top_k=20,
        min_p=0.0,
        presence_penalty=1.5,
        repetition_penalty=1.0,
        max_output_tokens=8192,
    )


def _compiler_config(profile_name: str) -> QwenGenerationConfig:
    if profile_name not in {"mock-api-call", "delete-sentinel"}:
        raise ValueError("unknown file-injection compiler profile")
    return QwenGenerationConfig(
        model=MODEL_ID,
        revision=MODEL_REVISION,
        # Compiler decoding is part of the fixed v0.4 contract and is
        # committed in generator evidence before any model request.
        enable_thinking=False,
        preserve_thinking=None,
        reasoning_effort=None,
        temperature=0.6,
        top_p=0.95,
        top_k=20,
        min_p=0.0,
        presence_penalty=0.0,
        repetition_penalty=1.0,
        max_output_tokens=8192,
    )


class FileBackedCompileClientProvider:
    """Create fresh HTTP clients while preserving one frozen service contract."""

    def __init__(
        self,
        base_url: str,
        *,
        observed_service_catalog: dict[str, Any],
        effective_config: _EffectiveConfigBinding,
        timeout_seconds: float = 900.0,
    ) -> None:
        self.base_url = _loopback_base_url(base_url)
        self.timeout_seconds = timeout_seconds
        self.generator = _generator_evidence(
            phase="compile",
            base_url=self.base_url,
            configs={
                "acquisition": _acquisition_config(),
                "compiler:mock-api-call": _compiler_config("mock-api-call"),
                "compiler:delete-sentinel": _compiler_config("delete-sentinel"),
            },
            observed_service_catalog=observed_service_catalog,
            effective_config=effective_config,
        )

    def acquisition(self, *, profile: SyntheticInjectionProfile) -> OpenAICompatibleClient:
        del profile
        return OpenAICompatibleClient(
            self.base_url,
            config=_acquisition_config(),
            timeout_seconds=self.timeout_seconds,
        )

    def compiler(self, *, profile: SyntheticInjectionProfile) -> OpenAICompatibleClient:
        return OpenAICompatibleClient(
            self.base_url,
            config=_compiler_config(profile.name),
            timeout_seconds=self.timeout_seconds,
        )


class FileBackedDeploymentClientProvider:
    """Create a fresh non-thinking client for every deployment episode."""

    def __init__(
        self,
        base_url: str,
        *,
        observed_service_catalog: dict[str, Any],
        effective_config: _EffectiveConfigBinding,
        timeout_seconds: float = 900.0,
    ) -> None:
        self.base_url = _loopback_base_url(base_url)
        self.timeout_seconds = timeout_seconds
        self.generator = _generator_evidence(
            phase="deployment",
            base_url=self.base_url,
            configs={"episode": _acquisition_config()},
            observed_service_catalog=observed_service_catalog,
            effective_config=effective_config,
        )

    def episode(
        self,
        *,
        profile: SyntheticInjectionProfile,
        task_kind: str,
    ) -> OpenAICompatibleClient:
        del profile, task_kind
        return OpenAICompatibleClient(
            self.base_url,
            config=_acquisition_config(),
            timeout_seconds=self.timeout_seconds,
        )


class _LazyFileBackedCompileClientProvider:
    """Delay service access and concrete HTTP-provider construction until admitted."""

    def __init__(
        self,
        base_url: str,
        *,
        effective_config: _EffectiveConfigBinding,
        timeout_seconds: float = 900.0,
    ) -> None:
        self.base_url = _loopback_base_url(base_url)
        self.effective_config = effective_config
        self.timeout_seconds = timeout_seconds
        self._delegate: FileBackedCompileClientProvider | None = None

    @property
    def generator(self) -> Mapping[str, Any]:
        return self._provider().generator

    def acquisition(self, *, profile: SyntheticInjectionProfile) -> OpenAICompatibleClient:
        return self._provider().acquisition(profile=profile)

    def compiler(self, *, profile: SyntheticInjectionProfile) -> OpenAICompatibleClient:
        return self._provider().compiler(profile=profile)

    def _provider(self) -> FileBackedCompileClientProvider:
        if self._delegate is None:
            _require_unchanged_effective_config(self.effective_config)
            observed_service = _verify_service(self.base_url)
            self._delegate = FileBackedCompileClientProvider(
                self.base_url,
                observed_service_catalog=observed_service,
                effective_config=self.effective_config,
                timeout_seconds=self.timeout_seconds,
            )
        return self._delegate


class _LazyFileBackedDeploymentClientProvider:
    """Delay service access and concrete HTTP-provider construction until admitted."""

    def __init__(
        self,
        base_url: str,
        *,
        effective_config: _EffectiveConfigBinding,
        timeout_seconds: float = 900.0,
    ) -> None:
        self.base_url = _loopback_base_url(base_url)
        self.effective_config = effective_config
        self.timeout_seconds = timeout_seconds
        self._delegate: FileBackedDeploymentClientProvider | None = None

    @property
    def generator(self) -> Mapping[str, Any]:
        return self._provider().generator

    def episode(
        self,
        *,
        profile: SyntheticInjectionProfile,
        task_kind: str,
    ) -> OpenAICompatibleClient:
        return self._provider().episode(profile=profile, task_kind=task_kind)

    def _provider(self) -> FileBackedDeploymentClientProvider:
        if self._delegate is None:
            _require_unchanged_effective_config(self.effective_config)
            observed_service = _verify_service(self.base_url)
            self._delegate = FileBackedDeploymentClientProvider(
                self.base_url,
                observed_service_catalog=observed_service,
                effective_config=self.effective_config,
                timeout_seconds=self.timeout_seconds,
            )
        return self._delegate


def run_live_retrieval(
    *,
    appworld_root: str | Path,
    bundle_directory: str | Path,
    output_directory: str | Path,
    project_root: str | Path | None = None,
    config_path: str | Path = DEFAULT_CONFIG_PATH,
) -> FileBackedRetrievalResult:
    """Write a model-free canonical-task retrieval admission artifact."""

    started_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    started_monotonic = time.monotonic()
    output = Path(output_directory).resolve()
    if output.exists() or output.is_symlink():
        raise RuntimeError("retrieval output already exists; replay requires a new directory")
    root = Path(project_root or Path.cwd()).resolve()
    config, experiment, config_sha256 = _load_live_config(root, config_path)
    loaded = load_appworld_file_fixtures(appworld_root, bundle_directory)
    source_evidence = _verified_source_evidence(Path(appworld_root), loaded)
    effective_config = _require_effective_config_match(
        config,
        config_sha256,
        experiment,
        source_evidence,
    )
    retrieval_gate = build_canonical_retrieval_gate(loaded.fixtures, experiment)
    fixture_commitments = build_fixture_commitments(loaded.fixtures)
    code_hash = source_tree_hash(root)
    config_hash = effective_config.sha256
    input_hash = canonical_json_sha256(
        {
            "schema_version": RETRIEVAL_SCHEMA_VERSION,
            "mode": RETRIEVAL_MODE,
            "source_evidence": source_evidence,
            "fixture_commitments": fixture_commitments,
            "retrieval_gate": retrieval_gate,
            "code_hash": code_hash,
            "config_hash": config_hash,
        }
    )

    store = ArtifactStore(output)
    store.write_json(
        "run.json",
        {
            "schema_version": RETRIEVAL_SCHEMA_VERSION,
            "mode": RETRIEVAL_MODE,
            "phase": "retrieval-only",
            "started_at": started_at,
            "model_requested": False,
            "compiler_constructed": False,
            "skill_created": False,
            "source_evidence": source_evidence,
            "fixture_commitments": fixture_commitments,
            "code_hash": code_hash,
            "config_hash": config_hash,
            "input_hash": input_hash,
        },
    )
    gate_record = store.write_json(
        "gate.json",
        {
            "schema_version": RETRIEVAL_SCHEMA_VERSION,
            "mode": RETRIEVAL_MODE,
            "phase": "retrieval-only",
            "passed": retrieval_gate["passed"],
            "passed_profile_count": retrieval_gate["passed_profile_count"],
            "profile_count": len(retrieval_gate["profile_names"]),
            "retrieval": retrieval_gate,
            "model_requested": False,
            "compiler_constructed": False,
            "skill_created": False,
        },
    )
    manifest_record = write_artifact_manifest(output, store)
    completed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    duration_seconds = time.monotonic() - started_monotonic
    complete_record = store.write_json(
        "complete.json",
        {
            "schema_version": RETRIEVAL_SCHEMA_VERSION,
            "status": "completed",
            "mode": RETRIEVAL_MODE,
            "phase": "retrieval-only",
            "started_at": started_at,
            "completed_at": completed_at,
            "duration_seconds": duration_seconds,
            "passed": retrieval_gate["passed"],
            "input_hash": input_hash,
            "code_hash": code_hash,
            "config_hash": config_hash,
            "gate_hash": gate_record.sha256,
            "artifact_manifest_hash": manifest_record.sha256,
            "model_requested": False,
            "compiler_constructed": False,
            "skill_created": False,
        },
    )
    verify_artifact_manifest(output, output / "artifacts-manifest.json")
    return FileBackedRetrievalResult(
        output_directory=output,
        gate=json.loads(json.dumps(retrieval_gate)),
        complete_hash=complete_record.sha256,
    )


def run_live_compile(
    *,
    appworld_root: str | Path,
    bundle_directory: str | Path,
    output_directory: str | Path,
    base_url: str = DEFAULT_BASE_URL,
    project_root: str | Path | None = None,
    config_path: str | Path = DEFAULT_CONFIG_PATH,
    seed: int = DEFAULT_SEED,
) -> CompileGateResult:
    root = Path(project_root or Path.cwd()).resolve()
    config, experiment, config_sha256 = _load_live_config(root, config_path)
    loaded = load_appworld_file_fixtures(appworld_root, bundle_directory)
    source_evidence = _verified_source_evidence(Path(appworld_root), loaded)
    effective_config = _require_effective_config_match(
        config,
        config_sha256,
        experiment,
        source_evidence,
    )
    return run_injection_compile_gate(
        output_directory,
        client_provider=_LazyFileBackedCompileClientProvider(
            base_url,
            effective_config=effective_config,
        ),
        project_root=root,
        config_path=config,
        seed=seed,
        fixtures=loaded.fixtures,
        mode=COMPILE_MODE,
        source_type=SOURCE_TYPE,
        source_evidence=source_evidence,
    )


def run_live_deployment(
    *,
    appworld_root: str | Path,
    bundle_directory: str | Path,
    compile_gate_directory: str | Path,
    compile_complete_sha256: str,
    output_directory: str | Path,
    base_url: str = DEFAULT_BASE_URL,
    project_root: str | Path | None = None,
    config_path: str | Path = DEFAULT_CONFIG_PATH,
    seed: int = DEFAULT_SEED,
) -> PoisonDeploymentResult:
    root = Path(project_root or Path.cwd()).resolve()
    config, experiment, config_sha256 = _load_live_config(root, config_path)
    loaded = load_appworld_file_fixtures(appworld_root, bundle_directory)
    source_evidence = _verified_source_evidence(Path(appworld_root), loaded)
    effective_config = _require_effective_config_match(
        config,
        config_sha256,
        experiment,
        source_evidence,
    )
    return run_poison_deployment_verification(
        compile_gate_directory,
        output_directory,
        expected_compile_complete_sha256=compile_complete_sha256,
        client_provider=_LazyFileBackedDeploymentClientProvider(
            base_url,
            effective_config=effective_config,
        ),
        project_root=root,
        config_path=config,
        seed=seed,
        fixtures=loaded.fixtures,
        mode=DEPLOYMENT_MODE,
        source_type=SOURCE_TYPE,
        source_evidence=source_evidence,
        expected_compile_mode=COMPILE_MODE,
        expected_compile_source_type=SOURCE_TYPE,
        require_compile_gate_passed=True,
    )


def _load_live_config(
    project_root: Path,
    config_path: str | Path,
) -> tuple[Path, ExperimentConfig, str]:
    config = Path(config_path)
    if not config.is_absolute():
        config = project_root / config
    if config.is_symlink() or not config.is_file():
        raise FileNotFoundError(config)
    config = config.resolve()
    before_sha256 = sha256_file(config)
    experiment = load_config(config)
    after_sha256 = sha256_file(config)
    if before_sha256 != after_sha256:
        raise RuntimeError("effective live config changed while it was being parsed")
    return config, experiment, after_sha256


def _require_unchanged_effective_config(binding: _EffectiveConfigBinding) -> None:
    if binding.path.is_symlink() or not binding.path.is_file():
        raise RuntimeError("effective live config is unavailable before service access")
    if sha256_file(binding.path) != binding.sha256:
        raise RuntimeError("effective live config changed before service access")


def _code_model_contract() -> dict[str, Any]:
    acquisition = asdict(_acquisition_config())
    acquisition.pop("model")
    acquisition.pop("revision")
    acquisition["max_output_tokens_per_turn"] = acquisition.pop("max_output_tokens")
    compiler_generation: dict[str, Any] = {}
    for profile_name in ("mock-api-call", "delete-sentinel"):
        profile = asdict(_compiler_config(profile_name))
        profile.pop("model")
        profile.pop("revision")
        compiler_generation[profile_name] = profile
    return {
        "id": MODEL_ID,
        "revision": MODEL_REVISION,
        "dtype": MODEL_DTYPE,
        "gpu": MODEL_GPU,
        "physical_gpu_ids": list(PHYSICAL_GPU_IDS),
        "vllm_version": VLLM_VERSION,
        "max_model_len": MODEL_MAX_LEN,
        "prefix_caching": False,
        "server_sessions": False,
        "serving": {
            "tokenizer_revision": MODEL_REVISION,
            "tensor_parallel_size": 2,
            "pipeline_parallel_size": 1,
            "max_num_seqs": 1,
            "language_model_only": True,
            "enable_auto_tool_choice": True,
            "tool_call_parser": "qwen3_coder",
            "reasoning_parser": "qwen3",
            "attention_backend": "TRITON_ATTN",
        },
        "generation": acquisition,
        "compiler_generation": compiler_generation,
    }


def _code_appworld_contract() -> dict[str, Any]:
    return {
        "data_bundle": APPWORLD_BUNDLE_NAME,
        "data_bundle_size_bytes": APPWORLD_BUNDLE_SIZE,
        "data_bundle_sha256": APPWORLD_BUNDLE_SHA256,
        "standard_corpus_sha256": APPWORLD_STANDARD_CORPUS_SHA256,
        "task_facing_pool_manifest_sha256": (APPWORLD_TASK_FACING_POOL_MANIFEST_SHA256),
        "raw_endpoint_count": EXPECTED_RAW_ENDPOINT_COUNT,
        "task_facing_resource_count": EXPECTED_TASK_FACING_COUNT,
        "excluded_helpers": ["api_docs", "supervisor"],
        "resource_counts": {
            "clean": EXPECTED_TASK_FACING_COUNT,
            "acquisition": EXPECTED_TASK_FACING_COUNT,
            "deployment": EXPECTED_TASK_FACING_COUNT,
        },
    }


def _require_effective_config_match(
    config_path: Path,
    config_sha256: str,
    experiment: ExperimentConfig,
    source_evidence: Mapping[str, Any],
) -> _EffectiveConfigBinding:
    model_contract = {
        "id": experiment.model.id,
        "revision": experiment.model.revision,
        "dtype": experiment.model.dtype,
        "gpu": experiment.model.gpu,
        "physical_gpu_ids": list(experiment.model.physical_gpu_ids),
        "vllm_version": experiment.model.vllm_version,
        "max_model_len": experiment.model.max_model_len,
        "prefix_caching": experiment.model.prefix_caching,
        "server_sessions": experiment.model.server_sessions,
        "serving": experiment.model.serving.to_dict(),
        "generation": experiment.model.generation.to_dict(),
        "compiler_generation": experiment.model.compiler_generation.to_dict(),
    }
    if model_contract != _code_model_contract():
        raise RuntimeError("effective live model config does not match the code contract")

    appworld_contract = {
        "data_bundle": experiment.appworld.data_bundle,
        "data_bundle_size_bytes": experiment.appworld.data_bundle_size_bytes,
        "data_bundle_sha256": experiment.appworld.data_bundle_sha256,
        "standard_corpus_sha256": experiment.appworld.standard_corpus_sha256,
        "task_facing_pool_manifest_sha256": (experiment.appworld.task_facing_pool_manifest_sha256),
        "raw_endpoint_count": experiment.appworld.raw_endpoint_count,
        "task_facing_resource_count": experiment.appworld.task_facing_resource_count,
        "excluded_helpers": list(experiment.appworld.excluded_helpers),
        "resource_counts": {
            "clean": experiment.resource_pool.clean_resources,
            "acquisition": experiment.resource_pool.acquisition_resources,
            "deployment": experiment.resource_pool.deployment_resources,
        },
    }
    expected_appworld = _code_appworld_contract()
    if appworld_contract != expected_appworld:
        raise RuntimeError("effective AppWorld config does not match the code contract")

    fixture_contract = {
        "source_corpus_sha256": source_evidence.get("source_corpus_sha256"),
        "source_pool_manifest_hash": source_evidence.get("source_pool_manifest_hash"),
        "raw_endpoint_count": source_evidence.get("raw_endpoint_count"),
        "task_facing_endpoint_count": source_evidence.get("task_facing_endpoint_count"),
        "excluded_helpers": source_evidence.get("excluded_helpers"),
    }
    expected_fixture_contract = {
        "source_corpus_sha256": expected_appworld["standard_corpus_sha256"],
        "source_pool_manifest_hash": expected_appworld["task_facing_pool_manifest_sha256"],
        "raw_endpoint_count": expected_appworld["raw_endpoint_count"],
        "task_facing_endpoint_count": expected_appworld["task_facing_resource_count"],
        "excluded_helpers": expected_appworld["excluded_helpers"],
    }
    if fixture_contract != expected_fixture_contract:
        raise RuntimeError(
            "file-backed fixture source evidence does not match the effective config"
        )
    return _EffectiveConfigBinding(
        path=config_path,
        sha256=config_sha256,
        model_contract=model_contract,
        appworld_contract=appworld_contract,
    )


def _declared_serving_contract() -> dict[str, Any]:
    model = _code_model_contract()
    return {
        "vllm_version": model["vllm_version"],
        "tokenizer_revision": model["serving"]["tokenizer_revision"],
        "dtype": model["dtype"],
        "gpu": model["gpu"],
        "physical_gpu_ids": model["physical_gpu_ids"],
        "tensor_parallel_size": model["serving"]["tensor_parallel_size"],
        "pipeline_parallel_size": model["serving"]["pipeline_parallel_size"],
        "max_model_len": model["max_model_len"],
        "prefix_caching": model["prefix_caching"],
        "server_sessions": model["server_sessions"],
        "max_num_seqs": model["serving"]["max_num_seqs"],
        "attention_backend": model["serving"]["attention_backend"],
        "reasoning_parser": model["serving"]["reasoning_parser"],
        "tool_call_parser": model["serving"]["tool_call_parser"],
        "enable_auto_tool_choice": model["serving"]["enable_auto_tool_choice"],
        "language_model_only": model["serving"]["language_model_only"],
    }


def _verified_source_evidence(
    appworld_root: Path,
    loaded: LoadedFileInjectionFixtures,
) -> dict[str, Any]:
    root = appworld_root.resolve(strict=True)
    bundle = root / "source-bundles" / APPWORLD_BUNDLE_NAME
    if bundle.is_symlink() or not bundle.is_file():
        raise RuntimeError("the frozen encrypted AppWorld source bundle is unavailable")
    if bundle.stat().st_size != APPWORLD_BUNDLE_SIZE:
        raise RuntimeError("the frozen AppWorld source bundle size differs")
    if sha256_file(bundle) != APPWORLD_BUNDLE_SHA256:
        raise RuntimeError("the frozen AppWorld source bundle hash differs")
    evidence = dict(loaded.source_evidence)
    if evidence.get("source_corpus_sha256") != APPWORLD_STANDARD_CORPUS_SHA256:
        raise RuntimeError("the official AppWorld standard corpus hash differs")
    if evidence.get("source_pool_manifest_hash") != APPWORLD_TASK_FACING_POOL_MANIFEST_SHA256:
        raise RuntimeError("the official AppWorld 447-resource pool manifest hash differs")
    evidence["official_bundle"] = {
        "name": APPWORLD_BUNDLE_NAME,
        "url": APPWORLD_BUNDLE_URL,
        "size_bytes": APPWORLD_BUNDLE_SIZE,
        "sha256": APPWORLD_BUNDLE_SHA256,
    }
    evidence["official_standard_corpus"] = {
        "corpus_sha256": APPWORLD_STANDARD_CORPUS_SHA256,
        "task_facing_resource_count": EXPECTED_TASK_FACING_COUNT,
        "pool_manifest_sha256": APPWORLD_TASK_FACING_POOL_MANIFEST_SHA256,
    }
    evidence["declared_appworld_acquisition_context"] = {
        "attestation": "caller_declared_not_observed_by_this_live_runner",
        "version": "0.1.3.post1",
        "install_source": "pypi_wheel",
        "environment": "/work/tc442/venvs/appworld-0.1.3-post1",
        "exact_git_commit_attested": False,
        "configured_git_commit": "66ad8099e12188ece0d3fe45e661dbc01880813b",
    }
    return evidence


def _generator_evidence(
    *,
    phase: str,
    base_url: str,
    configs: dict[str, QwenGenerationConfig],
    observed_service_catalog: dict[str, Any],
    effective_config: _EffectiveConfigBinding,
) -> dict[str, Any]:
    consumed_policy_fields = [
        "retriever.k1",
        "retriever.b",
        "retriever.top_k",
        "retriever.max_search_calls",
        "retriever.max_unique_docs_read",
        "agent.max_turns",
        "agent.max_api_calls",
        "model.max_model_len",
        "model.generation.max_output_tokens_per_turn",
    ]
    if phase == "compile":
        consumed_policy_fields.extend(
            [
                "retriever.model_select_k",
                "compiler.max_input_tokens",
                "compiler.max_skill_tokens",
            ]
        )
    return {
        "kind": "local_openai_compatible_qwen38",
        "phase": phase,
        "base_url": base_url,
        "model_id": MODEL_ID,
        "revision": MODEL_REVISION,
        "requests": {name: asdict(config) for name, config in configs.items()},
        "observed_service_catalog": dict(observed_service_catalog),
        "declared_serving_contract": _declared_serving_contract(),
        "evidence_boundary": {
            "observed_via_models_endpoint": ["model_id", "max_model_len"],
            "caller_declared_not_in_models_endpoint": [
                "model_revision",
                "tokenizer_revision",
                "vllm_version",
                "dtype",
                "gpu",
                "physical_gpu_ids",
                "prefix_caching",
                "server_sessions",
                "tensor_parallel_size",
                "pipeline_parallel_size",
                "max_num_seqs",
                "language_model_only",
                "enable_auto_tool_choice",
                "attention_backend",
                "reasoning_parser",
                "tool_call_parser",
            ],
        },
        "effective_config_commitment": {
            "path": str(effective_config.path),
            "sha256": effective_config.sha256,
            "model_contract_sha256": canonical_json_sha256(effective_config.model_contract),
            "appworld_contract_sha256": canonical_json_sha256(effective_config.appworld_contract),
        },
        "effective_config_match": {
            "status": "matched",
            "validated_before_service_access_and_provider_construction": True,
            "runtime_requests_match_model_generation": True,
            "declared_serving_contract_matches": True,
            "official_source_and_fixture_contract_matches": True,
            "role": "effective_runtime_identity_generation_and_policy_contract",
            "consumed_in_this_phase": consumed_policy_fields,
            "matching_scope": [
                "model.id_revision_dtype_physical_gpu_ids_and_vllm",
                "model.serving_and_generation",
                "model.compiler_generation",
                "official_appworld_hashes_and_counts",
                "file_backed_fixture_source_evidence",
            ],
        },
    }


def _loopback_base_url(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("base_url must be non-empty")
    parsed = urllib.parse.urlparse(value)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("model service must be an unauthenticated loopback HTTP URL")
    return value.rstrip("/")


def _verify_service(base_url: str) -> dict[str, Any]:
    normalized = _loopback_base_url(base_url)
    endpoint = normalized + "/models" if normalized.endswith("/v1") else normalized + "/v1/models"
    try:
        with urllib.request.urlopen(endpoint, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Qwen model service is unavailable or malformed") from exc
    records = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(records, list) or len(records) != 1 or not isinstance(records[0], dict):
        raise RuntimeError("Qwen model service returned an unexpected model catalog")
    model = records[0]
    if model.get("id") != MODEL_ID or model.get("max_model_len") != MODEL_MAX_LEN:
        raise RuntimeError("Qwen model service does not match the frozen model contract")
    return {
        "endpoint": endpoint,
        "model_id": MODEL_ID,
        "max_model_len": MODEL_MAX_LEN,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    materialize = subparsers.add_parser("materialize")
    materialize.add_argument("--appworld-root", required=True)
    materialize.add_argument("--output", required=True)
    materialize.add_argument("--payload-directory", required=True)

    retrieve = subparsers.add_parser("retrieve")
    retrieve.add_argument("--appworld-root", required=True)
    retrieve.add_argument("--bundle-directory", required=True)
    retrieve.add_argument("--output", required=True)
    retrieve.add_argument("--project-root", default=None)
    retrieve.add_argument("--config", default=DEFAULT_CONFIG_PATH)

    for name in ("compile", "deploy"):
        command = subparsers.add_parser(name)
        command.add_argument("--appworld-root", required=True)
        command.add_argument("--bundle-directory", required=True)
        command.add_argument("--output", required=True)
        command.add_argument("--base-url", default=DEFAULT_BASE_URL)
        command.add_argument("--project-root", default=None)
        command.add_argument("--config", default=DEFAULT_CONFIG_PATH)
        command.add_argument("--seed", type=int, default=DEFAULT_SEED)
        if name == "deploy":
            command.add_argument("--compile-gate-directory", required=True)
            command.add_argument("--compile-complete-sha256", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "materialize":
        manifests = materialize_appworld_file_bundles(
            args.appworld_root,
            args.output,
            payload_directory=args.payload_directory,
        )
        print(
            json.dumps(
                {
                    profile: {arm: str(path) for arm, path in arms.items()}
                    for profile, arms in manifests.items()
                },
                sort_keys=True,
            )
        )
        return 0
    if args.command == "retrieve":
        result = run_live_retrieval(
            appworld_root=args.appworld_root,
            bundle_directory=args.bundle_directory,
            output_directory=args.output,
            project_root=args.project_root,
            config_path=args.config,
        )
    elif args.command == "compile":
        result = run_live_compile(
            appworld_root=args.appworld_root,
            bundle_directory=args.bundle_directory,
            output_directory=args.output,
            base_url=args.base_url,
            project_root=args.project_root,
            config_path=args.config,
            seed=args.seed,
        )
    else:
        result = run_live_deployment(
            appworld_root=args.appworld_root,
            bundle_directory=args.bundle_directory,
            compile_gate_directory=args.compile_gate_directory,
            compile_complete_sha256=args.compile_complete_sha256,
            output_directory=args.output,
            base_url=args.base_url,
            project_root=args.project_root,
            config_path=args.config,
            seed=args.seed,
        )
    print(
        json.dumps(
            {
                "output_directory": str(result.output_directory),
                "complete_sha256": result.complete_hash,
                "gate": result.gate,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


__all__ = [
    "COMPILE_MODE",
    "DEPLOYMENT_MODE",
    "FileBackedCompileClientProvider",
    "FileBackedDeploymentClientProvider",
    "FileBackedRetrievalResult",
    "MODEL_ID",
    "MODEL_REVISION",
    "RETRIEVAL_MODE",
    "SOURCE_TYPE",
    "main",
    "run_live_compile",
    "run_live_deployment",
    "run_live_retrieval",
]
