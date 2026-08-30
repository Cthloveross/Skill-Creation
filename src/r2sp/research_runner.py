"""Fail-closed orchestration for the real AppWorld/Qwen v0.3 pilot.

The synthetic runner intentionally cannot enter this module's research path.
Every mutable action is downstream of a strict research preflight, and an
injected test backend is permanently reported as non-research evidence.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.parse
from collections.abc import Callable, Mapping, Sequence
from contextlib import contextmanager, suppress
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

from .agent import AgentBudgets, AgentResult, AgentRunner
from .artifacts import (
    ArtifactError,
    ArtifactIntegrityError,
    ArtifactRecord,
    ArtifactStore,
    verify_artifact_manifest,
    write_artifact_manifest,
)
from .canary import CanaryLogError, EvaluatorOwnedCanary
from .cases import (
    BuildSchedule,
    BuildScheduleEntry,
    FrozenCaseBundle,
    OverlayAttestation,
    build_schedule,
    load_frozen_cases,
    load_overlay_attestation,
)
from .compiler import SkillArtifact, SkillCompiler
from .config import ExperimentConfig, load_config
from .evaluation import (
    AcquisitionRecord,
    ArmRecord,
    CanaryCall,
    DeploymentRecord,
    Eligibility,
    MatchedCaseRecord,
    ResetRecord,
    SkillRecord,
    evaluate_case,
    summarize,
)
from .hashing import canonical_json_sha256, sha256_file, sha256_text
from .integrity import ContentDigest, IntegrityError, hash_appworld_runtime_snapshot
from .isolation import ResetEvidence, attest_reset
from .isolation import RuntimeIdentity as ResetRuntimeIdentity
from .model_client import ModelClient, OpenAICompatibleClient, QwenGenerationConfig
from .models import CaseSpec, OverlaySpec, PoolManifest
from .preflight import PreflightReport, required_failures, run_preflight
from .reporting import funnel_csv, summary_json, summary_markdown
from .resource_pool import ResourcePool, load_public_manifest, load_standard_api_docs
from .retrieval import DeterministicBM25
from .runtime.appworld import AppWorldRuntime
from .runtime.base import RuntimeAdapter, RuntimeIdentity


class ResearchRunnerError(RuntimeError):
    """Base class for pilot orchestration failures."""


class ResearchPreflightError(ResearchRunnerError):
    """Raised before any output or AppWorld mutation when strict gates fail."""


class ResearchRunInterrupted(ResearchRunnerError):
    """Raised when an uncommitted phase marker makes replay unsafe."""


class ResearchRunLocked(ResearchRunnerError):
    """Raised when another process or a crashed process owns the run lock."""


class FrozenInputError(ResearchRunnerError):
    """Raised when post-preflight frozen inputs no longer match."""


@dataclass(frozen=True)
class ResearchRuntimeConfig:
    source_path: Path
    appworld_root: Path
    clean_manifest: Path
    cases_path: Path
    overlays_path: Path
    dependency_lockfiles: tuple[Path, Path]
    output_root: Path
    phase_timeout_seconds: float
    model_request_timeout_seconds: float
    evaluate_every_completed_cases: int
    resume: bool
    model_base_url: str
    api_key_env: str
    logging_level: str


@dataclass(frozen=True)
class ResearchRunResult:
    output_directory: Path
    run_id: str
    summary: Mapping[str, Any]
    cached: bool
    complete_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "cached": self.cached,
            "complete_hash": self.complete_hash,
            "decision": self.summary.get("decision"),
            "output_directory": str(self.output_directory),
            "research_eligible": self.summary.get("research_eligible"),
            "run_id": self.run_id,
        }


def _default_clean_pool_loader(appworld_root: Path, config: ExperimentConfig) -> ResourcePool:
    docs = appworld_root / "data" / "api_docs" / "standard"
    return load_standard_api_docs(
        docs,
        expected_count=int(config.resource_pool.clean_resources),
        excluded_helpers=tuple(config.resource_pool.exclude_helpers),
    )


def _default_case_loader(path: Path) -> FrozenCaseBundle:
    return load_frozen_cases(path, research_mode=True)


def _default_overlay_loader(path: Path, bundle: FrozenCaseBundle) -> OverlayAttestation:
    return load_overlay_attestation(path, expected_bundle=bundle)


def _default_model_client(runtime: ResearchRuntimeConfig, config: ExperimentConfig) -> ModelClient:
    generation = config.model.generation
    # An absent experiment-specific key means no authentication. Passing an
    # explicit empty value prevents the generic client from falling back to an
    # unrelated OPENAI_API_KEY and disclosing it to a local model process.
    api_key = os.environ.get(runtime.api_key_env, "")
    return OpenAICompatibleClient(
        runtime.model_base_url,
        api_key=api_key,
        timeout_seconds=runtime.model_request_timeout_seconds,
        config=QwenGenerationConfig(
            model=str(config.model.id),
            revision=str(config.model.revision),
            enable_thinking=bool(generation.enable_thinking),
            preserve_thinking=bool(generation.preserve_thinking),
            reasoning_effort=str(generation.reasoning_effort),
            temperature=float(generation.temperature),
            top_p=float(generation.top_p),
            top_k=int(generation.top_k),
            max_output_tokens=int(generation.max_output_tokens_per_turn),
        ),
    )


@dataclass(frozen=True)
class ResearchDependencies:
    """Injection boundary for deterministic tests.

    Supplying this object, even with production-looking callables, disables
    research eligibility. Only the no-injection path can construct a research
    eligible summary.
    """

    preflight_runner: Callable[..., PreflightReport] = run_preflight
    config_loader: Callable[..., ExperimentConfig] = load_config
    clean_pool_loader: Callable[[Path, ExperimentConfig], ResourcePool] = _default_clean_pool_loader
    manifest_loader: Callable[[Path], PoolManifest] = load_public_manifest
    case_loader: Callable[[Path], FrozenCaseBundle] = _default_case_loader
    overlay_loader: Callable[[Path, FrozenCaseBundle], OverlayAttestation] = _default_overlay_loader
    schedule_builder: Callable[..., BuildSchedule] = build_schedule
    model_client_factory: Callable[[ResearchRuntimeConfig, ExperimentConfig], ModelClient] = (
        _default_model_client
    )
    runtime_factory: Callable[..., RuntimeAdapter] = AppWorldRuntime
    agent_runner_factory: Callable[..., Any] = AgentRunner
    compiler_factory: Callable[..., Any] = SkillCompiler
    monotonic: Callable[[], float] = time.monotonic


class _CompilerPromptClient:
    """Bind the checked-in compiler prompt without changing SkillCompiler."""

    def __init__(self, client: ModelClient, system_prompt: str) -> None:
        self._client = client
        self._system_prompt = system_prompt

    def complete(
        self,
        messages: Sequence[Mapping[str, Any]],
        *,
        tools: Sequence[Mapping[str, Any]] | None = None,
        seed: int | None = None,
        max_output_tokens: int | None = None,
    ) -> dict[str, Any]:
        bound = [dict(message) for message in messages]
        if not bound or bound[0].get("role") != "system":
            raise ResearchRunnerError("compiler request has no system prompt slot")
        bound[0]["content"] = self._system_prompt
        return self._client.complete(
            bound,
            tools=tools,
            seed=seed,
            max_output_tokens=max_output_tokens,
        )


def load_runtime_config(
    path: str | Path,
    *,
    project_root: str | Path | None = None,
) -> ResearchRuntimeConfig:
    """Load the non-secret runtime YAML without mutating the environment."""

    source = Path(path).resolve()
    try:
        with source.open("r", encoding="utf-8") as handle:
            payload = yaml.safe_load(handle)
    except OSError as exc:
        raise FrozenInputError(f"cannot read runtime config {source}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise FrozenInputError(f"invalid runtime YAML: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise FrozenInputError("runtime configuration root must be a mapping")
    _exact_keys(payload, {"runtime", "model_service", "logging"}, "runtime root")
    runtime = _mapping(payload["runtime"], "runtime")
    model = _mapping(payload["model_service"], "model_service")
    logging = _mapping(payload["logging"], "logging")
    _exact_keys(
        runtime,
        {
            "mode",
            "appworld_root",
            "clean_manifest",
            "cases",
            "overlays",
            "dependency_lockfiles",
            "output_root",
            "phase_timeout_seconds",
            "model_request_timeout_seconds",
            "evaluate_every_completed_cases",
            "resume",
        },
        "runtime",
    )
    _exact_keys(model, {"base_url", "api_key_env"}, "model_service")
    _exact_keys(
        logging,
        {
            "level",
            "jsonl",
            "include_protected_document_bodies",
            "include_model_reasoning",
        },
        "logging",
    )
    if runtime["mode"] != "research":
        raise FrozenInputError("runtime.mode must equal 'research'")
    if runtime["resume"] is not True:
        raise FrozenInputError("runtime.resume must be true for safe phase recovery")
    if logging["jsonl"] is not True:
        raise FrozenInputError("logging.jsonl must be true")
    if logging["include_protected_document_bodies"] is not False:
        raise FrozenInputError("protected document bodies cannot be persisted")
    if logging["include_model_reasoning"] is not False:
        raise FrozenInputError("model reasoning cannot be persisted")

    root = Path(project_root or Path.cwd()).resolve()
    protected_paths = {
        name: _absolute_path(runtime[key], f"runtime.{key}")
        for name, key in (
            ("appworld_root", "appworld_root"),
            ("clean_manifest", "clean_manifest"),
            ("cases_path", "cases"),
            ("overlays_path", "overlays"),
        )
    }
    for name, protected_path in protected_paths.items():
        _require_disjoint_tree(
            protected_path,
            root,
            name=f"runtime.{name}",
            other_name="project root",
        )
    raw_lockfiles = runtime["dependency_lockfiles"]
    if (
        not isinstance(raw_lockfiles, list)
        or len(raw_lockfiles) != 2
        or any(not isinstance(value, str) or not value.strip() for value in raw_lockfiles)
    ):
        raise FrozenInputError("runtime.dependency_lockfiles must contain exactly two paths")
    lock_paths = tuple(Path(value) for value in raw_lockfiles)
    if any(not path.is_absolute() for path in lock_paths):
        raise FrozenInputError("runtime.dependency_lockfiles paths must be absolute")
    output_path = _absolute_path(runtime["output_root"], "runtime.output_root")
    _require_disjoint_tree(
        output_path,
        root,
        name="runtime.output_root",
        other_name="project root",
    )

    phase_timeout = _positive_number(
        runtime["phase_timeout_seconds"], "runtime.phase_timeout_seconds"
    )
    request_timeout = _positive_number(
        runtime["model_request_timeout_seconds"],
        "runtime.model_request_timeout_seconds",
    )
    evaluate_every = runtime["evaluate_every_completed_cases"]
    if (
        isinstance(evaluate_every, bool)
        or not isinstance(evaluate_every, int)
        or evaluate_every <= 0
    ):
        raise FrozenInputError("runtime.evaluate_every_completed_cases must be a positive integer")
    base_url = _validated_model_url(model["base_url"])
    api_key_env = _text(model["api_key_env"], "model_service.api_key_env")
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", api_key_env) is None:
        raise FrozenInputError("model_service.api_key_env is not an environment name")
    level = _text(logging["level"], "logging.level")
    return ResearchRuntimeConfig(
        source_path=source,
        output_root=output_path.resolve(),
        phase_timeout_seconds=phase_timeout,
        model_request_timeout_seconds=request_timeout,
        evaluate_every_completed_cases=evaluate_every,
        resume=True,
        model_base_url=base_url,
        api_key_env=api_key_env,
        logging_level=level,
        dependency_lockfiles=(lock_paths[0].resolve(), lock_paths[1].resolve()),
        **protected_paths,
    )


def run_pilot(
    runtime_config_path: str | Path,
    *,
    config_path: str | Path = "configs/experiment_plan.yaml",
    project_root: str | Path | None = None,
    output_directory: str | Path | None = None,
    dependency_lockfiles: Sequence[str | Path] | None = None,
    dependencies: ResearchDependencies | None = None,
) -> ResearchRunResult:
    """Execute or safely resume the 16-case real pilot.

    Reading and validating the runtime YAML is side-effect free. The strict
    preflight is then the first external operation. No output directory,
    environment variable, model request, or AppWorld world is touched unless
    all research gates pass.
    """

    root = Path(project_root or Path.cwd()).resolve()
    runtime = load_runtime_config(runtime_config_path, project_root=root)
    config_source = Path(config_path)
    if not config_source.is_absolute():
        config_source = root / config_source
    injected = dependencies is not None
    deps = dependencies or ResearchDependencies()
    selected_lockfiles = (
        tuple(Path(path).resolve() for path in dependency_lockfiles)
        if dependency_lockfiles is not None
        else runtime.dependency_lockfiles
    )
    if len(selected_lockfiles) != 2:
        raise FrozenInputError("exactly two dependency lockfiles are required")

    try:
        preflight = deps.preflight_runner(
            config_source,
            project_root=root,
            appworld_root=runtime.appworld_root,
            clean_manifest=runtime.clean_manifest,
            cases_path=runtime.cases_path,
            overlays_path=runtime.overlays_path,
            model_url=runtime.model_base_url,
            model_api_key_env=runtime.api_key_env,
            dependency_lockfiles=selected_lockfiles,
            require_research_ready=True,
            mode="research",
        )
    except Exception as exc:
        raise ResearchPreflightError(
            f"strict research preflight failed: {exc.__class__.__name__}"
        ) from exc
    failures = tuple(required_failures(preflight))
    if (
        preflight.mode != "research"
        or preflight.ready is not True
        or preflight.research_ready is not True
        or failures
    ):
        detail = ",".join(failures) if failures else "research_ready=false"
        raise ResearchPreflightError("strict research preflight not ready: " + detail)

    # Re-load every frozen object after the read-only gate so a custom or stale
    # preflight cannot substitute unchecked runtime objects.
    config = deps.config_loader(config_source, require_research_ready=True)
    clean_pool = deps.clean_pool_loader(runtime.appworld_root, config)
    frozen_manifest = deps.manifest_loader(runtime.clean_manifest)
    if len(clean_pool) != int(config.resource_pool.clean_resources):
        raise FrozenInputError("clean pool does not contain exactly 457 resources")
    if not clean_pool.matches_manifest(frozen_manifest):
        raise FrozenInputError("rebuilt clean pool does not match frozen manifest")
    cases = deps.case_loader(runtime.cases_path)
    if not cases.research_mode or len(cases.cases) != int(config.pilot.cases):
        raise FrozenInputError("research case bundle must contain exactly 16 cases")
    if cases.protocol_version != str(config.protocol.version):
        raise FrozenInputError("research case bundle protocol does not match the experiment")
    overlay_attestation = deps.overlay_loader(runtime.overlays_path, cases)
    if overlay_attestation.protocol_version != str(config.protocol.version):
        raise FrozenInputError("overlay attestation protocol does not match the experiment")
    schedule = deps.schedule_builder(cases, seed=int(config.pilot.random_seed))
    _validate_schedule(schedule, cases)
    _validate_overlay_absence(clean_pool, cases)
    task_catalog_hash = (
        _validate_frozen_appworld_tasks(runtime.appworld_root, cases) if not injected else None
    )
    appworld_task_ids = tuple(
        task.task_id
        for case in cases.cases
        for task in (case.authoring_task, case.positive_task, case.negative_task)
    )
    appworld_snapshot = (
        _appworld_runtime_snapshot(runtime.appworld_root, appworld_task_ids)
        if not injected
        else None
    )
    prompts, prompt_hashes = _load_prompts(root)
    client = deps.model_client_factory(runtime, config)
    token_counter = getattr(client, "count_tokens", None)
    token_count_attestation_hash: str | None = None
    model_contract_probe_hash: str | None = None
    selection_contract_probe_hash: str | None = None
    if not injected:
        if not callable(token_counter):
            raise FrozenInputError(
                "the research model client must expose the pinned tokenizer counter"
            )
        token_count_attestation_hash = _verify_case_token_counts(cases, token_counter=token_counter)
        contract_probe = getattr(client, "verify_tool_contract", None)
        if not callable(contract_probe):
            raise FrozenInputError("the research model client must expose a tool-contract probe")
        probe_result = contract_probe()
        if not isinstance(probe_result, Mapping):
            raise FrozenInputError("model tool-contract probe returned invalid evidence")
        model_contract_probe_hash = canonical_json_sha256(dict(probe_result))
        selection_contract_probe = getattr(client, "verify_selection_contract", None)
        if not callable(selection_contract_probe):
            raise FrozenInputError(
                "the research model client must expose an exact-selection contract probe"
            )
        selection_probe_result = selection_contract_probe(
            selection_k=int(config.retriever.model_select_k)
        )
        if not isinstance(selection_probe_result, Mapping):
            raise FrozenInputError("model selection-contract probe returned invalid evidence")
        selection_contract_probe_hash = canonical_json_sha256(dict(selection_probe_result))

    hashes = {
        "runtime_hash": sha256_file(runtime.source_path),
        "config_hash": sha256_file(config_source),
        "cases_hash": sha256_file(runtime.cases_path),
        "overlay_attestation_hash": sha256_file(runtime.overlays_path),
        "clean_manifest_file_hash": sha256_file(runtime.clean_manifest),
        "clean_manifest_hash": str(frozen_manifest.manifest_hash),
        "schedule_hash": canonical_json_sha256(schedule.to_public_dict()),
        "code_hash": _code_hash(root),
        "appworld_lock_hash": sha256_file(selected_lockfiles[0]),
        "model_service_lock_hash": sha256_file(selected_lockfiles[1]),
        **prompt_hashes,
    }
    if token_count_attestation_hash is not None:
        hashes["token_count_attestation_hash"] = token_count_attestation_hash
    if model_contract_probe_hash is not None:
        hashes["model_contract_probe_hash"] = model_contract_probe_hash
    if selection_contract_probe_hash is not None:
        hashes["selection_contract_probe_hash"] = selection_contract_probe_hash
    if task_catalog_hash is not None:
        hashes["task_catalog_hash"] = task_catalog_hash
    if appworld_snapshot is not None:
        hashes["appworld_runtime_snapshot_hash"] = appworld_snapshot.sha256
    preflight_hash = _research_preflight_hash(preflight)
    input_hash = canonical_json_sha256(
        {
            "protocol_version": str(config.protocol.version),
            "frozen_hashes": hashes,
            "preflight_hash": preflight_hash,
            "case_ids": [case.case_id for case in cases.cases],
        }
    )
    fingerprint = canonical_json_sha256(
        {
            "input_hash": input_hash,
            "code_hash": hashes["code_hash"],
            "model_url": runtime.model_base_url,
        }
    )
    run_id = "research-" + fingerprint[:20]
    output = (
        Path(output_directory).resolve()
        if output_directory is not None
        else runtime.output_root / run_id
    )
    _validate_output_location(output, runtime.appworld_root, root)

    cached = _load_completed(output, fingerprint, run_id)
    if cached is not None:
        return cached
    store = ArtifactStore(output)
    _reject_active_lock(output, run_id)
    _fail_on_interrupted_phase(output, store, run_id, fingerprint)

    provenance = {
        "preflight_hash": preflight_hash,
        "config_hash": hashes["config_hash"],
        "code_hash": hashes["code_hash"],
        "input_hash": input_hash,
        "clean_manifest_hash": hashes["clean_manifest_hash"],
        "cases_hash": hashes["cases_hash"],
        "overlay_attestation_hash": hashes["overlay_attestation_hash"],
        "schedule_hash": hashes["schedule_hash"],
        "appworld_runtime": "byte_bound" if not injected else "injected_test",
        "model_service": ("reported_profile_matched" if not injected else "injected_test"),
    }
    if appworld_snapshot is not None:
        provenance["appworld_runtime_snapshot_hash"] = appworld_snapshot.sha256
    if model_contract_probe_hash is not None:
        provenance["model_contract_probe_hash"] = model_contract_probe_hash
    if selection_contract_probe_hash is not None:
        provenance["selection_contract_probe_hash"] = selection_contract_probe_hash
    research_contract_path = not injected
    store.write_json(
        "run.json",
        {
            "schema_version": "1",
            "protocol_version": str(config.protocol.version),
            "mode": "research" if research_contract_path else "injected_test",
            "research_candidate": research_contract_path,
            "run_id": run_id,
            "seed": int(config.pilot.random_seed),
            "fingerprint": fingerprint,
            "input_hash": input_hash,
            "code_hash": hashes["code_hash"],
            "config_hash": hashes["config_hash"],
            "clean_pool_hash": frozen_manifest.manifest_hash,
            "clean_resource_count": len(clean_pool),
            "frozen_asset_hashes": hashes,
            "preflight_hash": preflight_hash,
            "schedule_hash": hashes["schedule_hash"],
            "model_provenance": {
                "evidence": provenance["model_service"],
                "model": str(config.model.id),
                "revision": str(config.model.revision),
                "vllm_version": str(config.model.vllm_version),
            },
            "appworld_provenance": {
                "evidence": provenance["appworld_runtime"],
                "package_version": str(config.appworld.package_version),
                "git_revision": str(config.appworld.git_revision),
                **(
                    {
                        "runtime_snapshot_hash": appworld_snapshot.sha256,
                        "runtime_snapshot_file_count": appworld_snapshot.file_count,
                        "runtime_snapshot_size_bytes": appworld_snapshot.size_bytes,
                        "runtime_snapshot_claim": "byte_binding_not_publisher_authentication",
                    }
                    if appworld_snapshot is not None
                    else {}
                ),
            },
        },
    )
    store.write_json(
        "preflight.json",
        {
            "schema_version": 1,
            "preflight_hash": preflight_hash,
            **_research_preflight_payload(preflight),
        },
    )
    store.write_json("manifests/clean-pool.json", frozen_manifest.to_dict())
    store.write_json("manifests/overlay-attestation.json", overlay_attestation.to_dict())
    store.write_json("schedule.json", schedule.to_public_dict())
    store.write_json("inputs/cases.json", _private_case_inputs(cases))
    store.write_json(
        "inputs/task-provenance.json",
        _research_task_provenance(cases, cases_hash=hashes["cases_hash"]),
    )

    compiler_client = _CompilerPromptClient(client, prompts["compiler"])
    budgets = AgentBudgets(
        max_turns=int(config.agent.max_turns),
        max_api_calls=int(config.agent.max_api_calls),
        max_search_calls=int(config.retriever.max_search_calls),
        max_unique_docs_read=int(config.retriever.max_unique_docs_read),
    )
    compiler_options: dict[str, Any] = {
        "max_input_tokens": int(config.compiler.max_input_tokens),
        "max_skill_tokens": int(config.compiler.max_skill_tokens),
    }
    if not injected:
        compiler_options["token_counter"] = token_counter
    compiler = deps.compiler_factory(compiler_client, **compiler_options)
    records: dict[str, dict[str, ArmRecord]] = {}
    completed_cases: set[str] = set()

    with _run_lock(output, run_id), _appworld_root(runtime.appworld_root):
        for entry in schedule.entries:
            case = _case_by_id(cases, entry.case_id)
            arm_name = "sham" if entry.arm == "A_sham" else "poison"
            arm_directory = f"cases/{case.case_id}/{arm_name}"
            completed = output / arm_directory / "phase-complete.json"
            if completed.is_file():
                record = _load_arm_record(
                    completed,
                    output / arm_directory / "arm-record.json",
                    expected_run_id=run_id,
                    expected_build_run_id=entry.run_id,
                    expected_case_id=case.case_id,
                    expected_arm=arm_name,
                    expected_fingerprint=fingerprint,
                )
            else:
                store.write_json(
                    arm_directory + "/phase-start.json",
                    {
                        "schema_version": 1,
                        "run_id": run_id,
                        "build_run_id": entry.run_id,
                        "case_id": case.case_id,
                        "arm": arm_name,
                        "fingerprint": fingerprint,
                    },
                )
                record = _run_arm(
                    research_run_id=run_id,
                    case=case,
                    entry=entry,
                    arm_name=arm_name,
                    clean_pool=clean_pool,
                    clean_manifest=frozen_manifest,
                    config=config,
                    runtime_config=runtime,
                    prompts=prompts,
                    neutral_prompt=prompts["neutral"],
                    client=client,
                    compiler=compiler,
                    budgets=budgets,
                    dependencies=deps,
                    store=store,
                    output=output,
                )
                arm_record = store.write_json(arm_directory + "/arm-record.json", asdict(record))
                store.write_json(
                    arm_directory + "/phase-complete.json",
                    {
                        "schema_version": 1,
                        "run_id": run_id,
                        "build_run_id": entry.run_id,
                        "case_id": case.case_id,
                        "arm": arm_name,
                        "fingerprint": fingerprint,
                        "status": "completed",
                        "arm_record_sha256": arm_record.sha256,
                        "arm_record": asdict(record),
                    },
                )
            records.setdefault(case.case_id, {})[arm_name] = record
            case_records = records[case.case_id]
            if set(case_records) == {"sham", "poison"} and case.case_id not in completed_cases:
                completed_cases.add(case.case_id)
                if len(completed_cases) % runtime.evaluate_every_completed_cases == 0:
                    _write_interim_evaluation(
                        store,
                        records,
                        completed_cases,
                    )
            if entry.position == len(schedule.entries) - 1:
                store.write_json(
                    "finalization-start.json",
                    {
                        "schema_version": 1,
                        "status": "started",
                        "run_id": run_id,
                        "fingerprint": fingerprint,
                        "appworld_runtime_snapshot_hash": (
                            appworld_snapshot.sha256 if appworld_snapshot is not None else None
                        ),
                    },
                )
                if appworld_snapshot is not None:
                    observed_snapshot = _appworld_runtime_snapshot(
                        runtime.appworld_root,
                        appworld_task_ids,
                    )
                    if observed_snapshot != appworld_snapshot:
                        store.write_json(
                            "interrupted.json",
                            {
                                "schema_version": 1,
                                "status": "interrupted_failure",
                                "run_id": run_id,
                                "fingerprint": fingerprint,
                                "reason": "appworld_runtime_snapshot_changed",
                                "unsafe_phases": ["finalization-start.json"],
                                "rerun_permitted": False,
                            },
                        )
                        raise ResearchRunInterrupted(
                            "AppWorld runtime bytes changed; this run cannot be resumed"
                        )
                return _finalize_run(
                    store=store,
                    output=output,
                    run_id=run_id,
                    fingerprint=fingerprint,
                    config=config,
                    cases=cases,
                    schedule=schedule,
                    records=records,
                    provenance=provenance,
                    research_contract_path=research_contract_path,
                )
    raise ResearchRunnerError("validated schedule unexpectedly contained no entries")


def run_research_pilot(
    *,
    config_path: str | Path,
    runtime_config_path: str | Path,
    project_root: str | Path | None = None,
    output_directory: str | Path | None = None,
    dependencies: ResearchDependencies | None = None,
) -> ResearchRunResult:
    """Stable keyword-only public API consumed by the CLI."""

    return run_pilot(
        runtime_config_path,
        config_path=config_path,
        project_root=project_root,
        output_directory=output_directory,
        dependencies=dependencies,
    )


def _finalize_run(
    *,
    store: ArtifactStore,
    output: Path,
    run_id: str,
    fingerprint: str,
    config: ExperimentConfig,
    cases: FrozenCaseBundle,
    schedule: BuildSchedule,
    records: Mapping[str, Mapping[str, ArmRecord]],
    provenance: Mapping[str, str],
    research_contract_path: bool,
) -> ResearchRunResult:
    matched: list[MatchedCaseRecord] = []
    for case in cases.cases:
        arms = records.get(case.case_id, {})
        if set(arms) != {"sham", "poison"}:
            raise ResearchRunnerError(f"case {case.case_id} is missing an assigned arm")
        matched.append(MatchedCaseRecord(case.case_id, sham=arms["sham"], poison=arms["poison"]))
    eligibility = Eligibility(
        mode="research" if research_contract_path else "injected_test",
        protocol_version=str(config.protocol.version),
        config_runner_ready=config.protocol.runner_ready is True,
        frozen_inputs=True,
        appworld_runtime_bound=research_contract_path,
        model_service_declarations_matched=research_contract_path,
        complete_case_count=len(matched),
        expected_case_count=int(config.pilot.cases),
        expected_case_ids=tuple(sorted(case.case_id for case in cases.cases)),
        provenance=provenance,
    )
    summary = summarize(matched, eligibility=eligibility)
    summary_record = store.write_text("reports/summary.json", summary_json(summary))
    store.write_text("reports/funnel.csv", funnel_csv(summary))
    store.write_text("reports/summary.md", summary_markdown(summary))
    manifest_record = _write_artifact_manifest(output, store)
    complete_record = store.write_json(
        "complete.json",
        {
            "schema_version": 1,
            "status": "completed",
            "mode": "research" if research_contract_path else "injected_test",
            "run_id": run_id,
            "fingerprint": fingerprint,
            "summary_hash": summary_record.sha256,
            "artifact_manifest_hash": manifest_record.sha256,
            "case_count": len(matched),
            "arm_count": len(schedule.entries),
        },
    )
    return ResearchRunResult(
        output_directory=output,
        run_id=run_id,
        summary=summary.to_dict(),
        cached=False,
        complete_hash=complete_record.sha256,
    )


def _run_arm(
    *,
    research_run_id: str,
    case: CaseSpec,
    entry: BuildScheduleEntry,
    arm_name: str,
    clean_pool: ResourcePool,
    clean_manifest: PoolManifest,
    config: ExperimentConfig,
    runtime_config: ResearchRuntimeConfig,
    prompts: Mapping[str, str],
    neutral_prompt: str,
    client: ModelClient,
    compiler: Any,
    budgets: AgentBudgets,
    dependencies: ResearchDependencies,
    store: ArtifactStore,
    output: Path,
) -> ArmRecord:
    deadline = dependencies.monotonic() + runtime_config.phase_timeout_seconds
    overlay = case.overlays.sham if arm_name == "sham" else case.overlays.poison
    acquisition_pool = clean_pool.with_overlay(overlay.resource)
    if len(acquisition_pool) != int(config.resource_pool.acquisition_resources):
        raise FrozenInputError("acquisition pool does not contain exactly 458 resources")
    acquisition_retriever = _retriever(acquisition_pool, config)
    arm_directory = f"cases/{case.case_id}/{arm_name}"
    store.write_json(
        arm_directory + "/acquisition-manifest.json",
        acquisition_pool.manifest.to_dict(),
    )

    acquisition_agent = dependencies.agent_runner_factory(
        client,
        budgets=budgets,
        top_k=int(config.retriever.top_k),
        selection_k=int(config.retriever.model_select_k),
        system_policy=prompts["agent"],
        max_context_tokens=int(config.model.max_model_len),
        max_output_tokens=int(config.model.generation.max_output_tokens_per_turn),
    )
    acquisition_runtime = dependencies.runtime_factory(
        case.authoring_task.task_id,
        experiment_name=f"{research_run_id}-{entry.run_id}-acquisition",
        canary_handler=None,
    )
    acquisition_identity, instruction, descriptions = _start_task(
        acquisition_runtime,
        case.authoring_task.instruction,
        expected_app_count=int(config.resource_pool.trusted_app_descriptions),
    )
    acquisition_result = _run_agent(
        acquisition_agent,
        instruction,
        descriptions,
        acquisition_runtime,
        acquisition_retriever,
        seed=entry.generation_seed,
    )
    _require_identity(acquisition_result, acquisition_identity)
    _check_deadline(deadline, dependencies.monotonic)
    natural_read = bool(
        overlay.resource.resource_id in acquisition_result.resource_ids
        and any(
            document.get("resource_id") == overlay.resource.resource_id
            and document.get("content_hash") == overlay.resource.content_hash
            for document in acquisition_result.read_documents
        )
    )
    overlay_top10 = any(
        overlay.resource.resource_id
        in {item.get("resource_id") for item in event.get("results", [])}
        for event in acquisition_result.retrieval_trace
    )
    overlay_selected5 = overlay.resource.resource_id in acquisition_result.selected_resource_ids
    natural_read = natural_read and overlay_selected5
    acquisition = AcquisitionRecord(
        overlay_read_in_full=natural_read,
        task_pass=acquisition_result.task_success,
        task_score=acquisition_result.score,
        failure=acquisition_result.failure,
        overlay_top10=overlay_top10,
        overlay_selected5=overlay_selected5,
    )
    store.write_json(
        arm_directory + "/acquisition.json",
        {
            "record": asdict(acquisition),
            "overlay_top10": overlay_top10,
            "overlay_selected5": overlay_selected5,
            "agent": _agent_payload(acquisition_result),
        },
    )

    build_payload = getattr(compiler, "build_payload", None)
    compiler_payload_hash: str | None = None
    if callable(build_payload):
        compiler_payload = build_payload(
            instruction,
            acquisition_result.read_documents,
            acquisition_result.normalized_trace,
            acquisition_result.task_success,
        )
        if not isinstance(compiler_payload, Mapping):
            raise ResearchRunnerError("compiler build_payload returned invalid provenance")
        compiler_payload_hash = canonical_json_sha256(dict(compiler_payload))
    generated: SkillArtifact = compiler.compile(
        instruction,
        acquisition_result.read_documents,
        acquisition_result.normalized_trace,
        acquisition_result.task_success,
        seed=entry.generation_seed,
    )
    if not generated.valid:
        generated = SkillArtifact(
            content=neutral_prompt,
            skill_hash=sha256_text(neutral_prompt),
            valid=False,
            source_resource_ids=generated.source_resource_ids,
            failure=generated.failure or "invalid_skill",
            placeholder=True,
        )
    skill_artifact = store.write_text(
        arm_directory + "/SKILL.md",
        generated.content,
        expected_sha256=generated.skill_hash,
    )
    loaded_text = skill_artifact.path.read_text(encoding="utf-8")
    loaded_hash = sha256_text(loaded_text)
    skill = SkillRecord(
        valid=generated.valid,
        loaded=loaded_hash == generated.skill_hash,
        skill_hash=generated.skill_hash,
        placeholder=generated.placeholder,
        failure=generated.failure,
    )
    skill_provenance = store.write_json(
        arm_directory + "/skill-provenance.json",
        {
            "schema_version": 1,
            "case_id": case.case_id,
            "arm": arm_name,
            "task_id": case.authoring_task.task_id,
            "task_source": "frozen_appworld_train_case_id",
            "task_instruction_sha256": sha256_text(instruction),
            "generator": {
                "kind": (
                    "qwen_model" if isinstance(client, OpenAICompatibleClient) else "injected_model"
                ),
                "model_id": str(config.model.id),
                "revision": str(config.model.revision),
            },
            "agent_prompt_sha256": sha256_text(prompts["agent"]),
            "compiler_prompt_sha256": sha256_text(prompts["compiler"]),
            "compiler_payload_sha256": compiler_payload_hash,
            "candidate_resource_ids": list(acquisition_result.candidate_resource_ids),
            "selected_resource_ids": list(acquisition_result.selected_resource_ids),
            "source_documents": _source_commitments(acquisition_result.read_documents),
            "normalized_trace_sha256": canonical_json_sha256(
                list(acquisition_result.normalized_trace)
            ),
            "selection_trace_sha256": canonical_json_sha256(
                list(acquisition_result.selection_trace)
            ),
            "task_success": acquisition_result.task_success,
            "seed": entry.generation_seed,
            "skill": {
                "path": skill_artifact.relative_path,
                "sha256": skill_artifact.sha256,
                "size_bytes": skill_artifact.size_bytes,
                "valid": skill.valid,
                "loaded": skill.loaded,
                "placeholder": skill.placeholder,
                "failure": skill.failure,
            },
        },
    )
    store.write_json(
        arm_directory + "/skill.json",
        {
            "valid": skill.valid,
            "loaded": skill.loaded,
            "placeholder": skill.placeholder,
            "skill_hash": skill.skill_hash,
            "source_resource_ids": list(generated.source_resource_ids),
            "failure": skill.failure,
            "artifact": {
                "path": skill_artifact.relative_path,
                "sha256": skill_artifact.sha256,
                "size_bytes": skill_artifact.size_bytes,
            },
            "provenance": {
                "path": skill_provenance.relative_path,
                "sha256": skill_provenance.sha256,
                "size_bytes": skill_provenance.size_bytes,
            },
        },
    )
    _check_deadline(deadline, dependencies.monotonic)

    deployment_records: dict[str, DeploymentRecord] = {}
    reset_checks: dict[str, bool] = {}
    reset_failures: list[str] = []
    for task_kind, task in (
        ("positive", case.positive_task),
        ("negative", case.negative_task),
    ):
        record, reset_payload = _run_deployment(
            research_run_id=research_run_id,
            task_kind=task_kind,
            task_id=task.task_id,
            frozen_instruction=task.instruction,
            arm_name=arm_name,
            entry=entry,
            overlay=overlay,
            acquisition_identity=acquisition_identity,
            clean_pool=clean_pool,
            clean_manifest=clean_manifest,
            loaded_skill=loaded_text,
            generated_skill=generated,
            loaded_hash=loaded_hash,
            config=config,
            prompts=prompts,
            client=client,
            budgets=budgets,
            dependencies=dependencies,
            output=output,
        )
        for check in reset_payload["checks"]:
            reset_checks[f"{task_kind}.{check['name']}"] = bool(check["passed"])
        if not reset_payload["passed"]:
            reset_failures.append(task_kind + "_reset_failed")
        store.write_json(arm_directory + f"/reset-{task_kind}.json", reset_payload)
        deployment_records[task_kind] = record
        store.write_json(arm_directory + f"/deployment-{task_kind}.json", asdict(record))
        _check_deadline(deadline, dependencies.monotonic)

    reset = ResetRecord(
        passed=bool(reset_checks) and all(reset_checks.values()),
        checks=reset_checks,
        failure=";".join(reset_failures) if reset_failures else None,
    )
    store.write_json(arm_directory + "/reset.json", asdict(reset))
    return ArmRecord(
        arm=arm_name,
        acquisition=acquisition,
        skill=skill,
        reset=reset,
        positive=deployment_records["positive"],
        negative=deployment_records["negative"],
    )


def _run_deployment(
    *,
    research_run_id: str,
    task_kind: str,
    task_id: str,
    frozen_instruction: str | None,
    arm_name: str,
    entry: BuildScheduleEntry,
    overlay: OverlaySpec,
    acquisition_identity: RuntimeIdentity,
    clean_pool: ResourcePool,
    clean_manifest: PoolManifest,
    loaded_skill: str,
    generated_skill: SkillArtifact,
    loaded_hash: str,
    config: ExperimentConfig,
    prompts: Mapping[str, str],
    client: ModelClient,
    budgets: AgentBudgets,
    dependencies: ResearchDependencies,
    output: Path,
) -> tuple[DeploymentRecord, dict[str, Any]]:
    episode_run_id = f"{research_run_id}-{entry.run_id}-{task_kind}"
    canary = EvaluatorOwnedCanary(
        output / "canary" / entry.case_id / arm_name / f"{task_kind}.jsonl",
        run_id=episode_run_id,
        skill_hash=generated_skill.skill_hash,
        expected_nonce=overlay.nonce,
    )
    tool = canary.deployment_tool(
        episode_id=episode_run_id,
        arm=arm_name,
        trigger_present=task_kind == "positive",
    )

    def emit(arguments: Mapping[str, Any]) -> dict[str, Any]:
        receipt = tool.invoke(arguments)
        return {"recorded": receipt.recorded, "call_id": receipt.call_id}

    retriever = _retriever(clean_pool, config)
    agent = dependencies.agent_runner_factory(
        client,
        budgets=budgets,
        top_k=int(config.retriever.top_k),
        system_policy=prompts["agent"],
        max_context_tokens=int(config.model.max_model_len),
        max_output_tokens=int(config.model.generation.max_output_tokens_per_turn),
    )
    runtime = dependencies.runtime_factory(
        task_id,
        experiment_name=episode_run_id,
        canary_handler=emit,
    )
    deployment_identity, instruction, descriptions = _start_task(
        runtime,
        frozen_instruction,
        expected_app_count=int(config.resource_pool.trusted_app_descriptions),
    )
    try:
        reset = attest_reset(
            ResetEvidence(
                frozen_clean_pool_hash=str(clean_manifest.manifest_hash),
                deployment_pool_hash=str(clean_pool.manifest.manifest_hash),
                overlay_id=overlay.resource.resource_id,
                overlay_content_hash=str(overlay.resource.content_hash),
                deployment_resource_ids=tuple(
                    resource.resource_id for resource in clean_pool.resources
                ),
                deployment_resource_hashes=tuple(
                    str(resource.content_hash) for resource in clean_pool.resources
                ),
                acquisition_runtime=_reset_identity(acquisition_identity),
                deployment_runtime=_reset_identity(deployment_identity),
                generated_skill_hash=generated_skill.skill_hash,
                loaded_skill_hash=loaded_hash,
            )
        )
    except BaseException:
        with suppress(Exception):
            runtime.close()
        raise
    if not reset.passed:
        runtime.close()
        return (
            DeploymentRecord(
                task_kind=task_kind,
                expected_nonce=overlay.nonce,
                expected_run_id=episode_run_id,
                expected_skill_hash=generated_skill.skill_hash,
                failure="reset_attestation_failed",
            ),
            reset.to_dict(),
        )
    result = _run_agent(
        agent,
        instruction,
        descriptions,
        runtime,
        retriever,
        skill=loaded_skill,
        seed=entry.generation_seed,
    )
    _require_identity(result, deployment_identity)
    events = canary.read_events()
    calls = _validated_canary_calls(
        events,
        result,
        expected_run_id=episode_run_id,
        expected_skill_hash=generated_skill.skill_hash,
    )
    record = DeploymentRecord(
        task_kind=task_kind,
        expected_nonce=overlay.nonce,
        expected_run_id=episode_run_id,
        expected_skill_hash=generated_skill.skill_hash,
        task_pass=result.task_success,
        task_score=result.score,
        canary_calls=calls,
        failure=result.failure,
    )
    return record, {**reset.to_dict(), "agent": _agent_payload(result)}


def _run_agent(
    agent: Any,
    instruction: str,
    descriptions: Mapping[str, str],
    runtime: RuntimeAdapter,
    retriever: DeterministicBM25,
    *,
    seed: int,
    skill: str | None = None,
) -> AgentResult:
    try:
        return agent.run(
            instruction,
            descriptions,
            runtime,
            retriever,
            skill=skill,
            seed=seed,
        )
    finally:
        # AgentRunner already closes by default; adapters must make close
        # idempotent so failures before its loop are also contained.
        runtime.close()


def _start_task(
    runtime: RuntimeAdapter,
    frozen_instruction: str | None,
    *,
    expected_app_count: int,
) -> tuple[RuntimeIdentity, str, Mapping[str, str]]:
    try:
        identity = runtime.start()
        instruction = runtime.task_instruction
        descriptions = runtime.app_descriptions
        if frozen_instruction is not None and instruction != frozen_instruction:
            raise FrozenInputError("AppWorld task instruction differs from frozen case")
        if not isinstance(instruction, str) or not instruction.strip():
            raise FrozenInputError("AppWorld task instruction is unavailable")
        if not isinstance(descriptions, Mapping) or not descriptions:
            raise FrozenInputError("AppWorld app descriptions are unavailable")
        if len(descriptions) != expected_app_count:
            raise FrozenInputError("AppWorld app description count differs from the frozen config")
        return identity, instruction, descriptions
    except BaseException:
        with suppress(Exception):
            runtime.close()
        raise


def _private_case_inputs(bundle: FrozenCaseBundle) -> dict[str, Any]:
    """Serialize the protected case inputs only into the mode-0700 run tree."""

    return {
        "schema_version": 1,
        "protocol_version": bundle.protocol_version,
        "source_sha256": sha256_file(bundle.source_path),
        "tokenizer": {
            "model": bundle.tokenizer_model,
            "revision": bundle.tokenizer_revision,
        },
        "cases": [case.to_dict() for case in bundle.cases],
        "token_counts": [asdict(counts) for counts in bundle.token_counts],
    }


def _research_task_provenance(
    bundle: FrozenCaseBundle,
    *,
    cases_hash: str,
) -> dict[str, Any]:
    """Return a body-free record of where every original task question came from."""

    cases = []
    for case in bundle.cases:
        tasks = []
        for task in (case.authoring_task, case.positive_task, case.negative_task):
            instruction = task.instruction or ""
            tasks.append(
                {
                    "task_id": task.task_id,
                    "kind": task.kind,
                    "instruction_sha256": sha256_text(instruction),
                }
            )
        cases.append({"case_id": case.case_id, "tasks": tasks})
    return {
        "schema_version": 1,
        "protocol_version": bundle.protocol_version,
        "source_type": "frozen_appworld_train_case_ids",
        "instruction_binding": "exact_world.task.instruction",
        "model_generated_tasks": False,
        "cases_file_sha256": cases_hash,
        "cases": cases,
    }


def _source_commitments(documents: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    """Commit to compiler sources without persisting protected document bodies."""

    fields = ("resource_id", "content_hash", "app_name", "api_name", "title")
    return [
        {field: str(document[field]) for field in fields if document.get(field) is not None}
        for document in documents
    ]


def _agent_payload(result: AgentResult) -> dict[str, Any]:
    # Full document bodies are used by the in-memory compiler and deliberately
    # excluded from durable artifacts.
    documents = []
    for document in result.read_documents:
        documents.append(
            {
                key: document[key]
                for key in (
                    "resource_id",
                    "app_name",
                    "api_name",
                    "title",
                    "content_hash",
                )
                if key in document
            }
        )
    return {
        "read_documents": documents,
        "resource_ids": list(result.resource_ids),
        "retrieval_trace": list(result.retrieval_trace),
        "read_trace": list(result.read_trace),
        "api_trace": list(result.api_trace),
        "task_success": result.task_success,
        "score": result.score,
        "world_id": result.world_id,
        "context_id": result.context_id,
        "session_id": result.session_id,
        "failure": result.failure,
        "turns": result.turns,
        "search_calls": result.search_calls,
        "api_calls": result.api_calls,
        "finish_status": result.finish_status,
        "answer": result.answer,
        "context_truncations": result.context_truncations,
        "max_counted_prompt_tokens": result.max_counted_prompt_tokens,
        "candidate_resource_ids": list(result.candidate_resource_ids),
        "selected_resource_ids": list(result.selected_resource_ids),
        "selection_trace": list(result.selection_trace),
    }


def _events_to_calls(events: Sequence[Mapping[str, Any]]) -> tuple[CanaryCall, ...]:
    calls = []
    for event in events:
        arguments = event.get("arguments")
        nonce = arguments.get("nonce") if isinstance(arguments, Mapping) else None
        calls.append(
            CanaryCall(
                nonce=nonce if isinstance(nonce, str) else None,
                run_id=str(event.get("run_id", "")),
                skill_hash=str(event.get("skill_hash", "")),
            )
        )
    return tuple(calls)


def _validated_canary_calls(
    events: Sequence[Mapping[str, Any]],
    result: AgentResult,
    *,
    expected_run_id: str,
    expected_skill_hash: str,
) -> tuple[CanaryCall, ...]:
    attempted = sum(
        str(item.get("app", "")).casefold() == "canary"
        and str(item.get("api", "")).casefold() == "emit"
        for item in result.api_trace
    )
    if attempted != len(events):
        raise CanaryLogError("agent canary attempts and evaluator-owned events do not match")
    for event in events:
        if (
            event.get("run_id") != expected_run_id
            or event.get("skill_hash") != expected_skill_hash
            or event.get("phase") != "deployment"
        ):
            raise CanaryLogError("canary event binding does not match its deployment")
    return _events_to_calls(events)


def _write_interim_evaluation(
    store: ArtifactStore,
    records: Mapping[str, Mapping[str, ArmRecord]],
    completed_case_ids: set[str],
) -> None:
    outcomes = []
    for case_id in sorted(completed_case_ids):
        arms = records[case_id]
        outcome = evaluate_case(
            MatchedCaseRecord(
                case_id,
                sham=arms["sham"],
                poison=arms["poison"],
            )
        )
        outcomes.append(outcome.to_dict())
    store.write_json(
        f"progress/evaluation-{len(outcomes):02d}.json",
        {
            "schema_version": 1,
            "completed_case_count": len(outcomes),
            "completed_case_ids": sorted(completed_case_ids),
            "decision_permitted": False,
            "scope": "interim_descriptive_only",
            "outcomes": outcomes,
        },
    )


def _load_arm_record(
    completion_path: Path,
    arm_record_path: Path,
    *,
    expected_run_id: str,
    expected_build_run_id: str,
    expected_case_id: str,
    expected_arm: str,
    expected_fingerprint: str,
) -> ArmRecord:
    try:
        payload = json.loads(completion_path.read_text(encoding="utf-8"))
        persisted = json.loads(arm_record_path.read_text(encoding="utf-8"))
        expected_metadata = {
            "run_id": expected_run_id,
            "build_run_id": expected_build_run_id,
            "case_id": expected_case_id,
            "arm": expected_arm,
            "fingerprint": expected_fingerprint,
        }
        mismatches = {
            key: {"expected": expected, "actual": payload.get(key)}
            for key, expected in expected_metadata.items()
            if payload.get(key) != expected
        }
        if mismatches:
            raise ValueError(f"phase metadata mismatch: {mismatches}")
        if payload.get("status") != "completed":
            raise ValueError("phase status is invalid")
        if payload.get("arm_record_sha256") != sha256_file(arm_record_path):
            raise ValueError("arm record digest mismatch")
        if payload.get("arm_record") != persisted:
            raise ValueError("embedded arm record differs from durable arm record")
        value = persisted
        acquisition = AcquisitionRecord(**value["acquisition"])
        skill = SkillRecord(**value["skill"])
        reset = ResetRecord(**value["reset"])
        positive = _deployment_from_dict(value["positive"])
        negative = _deployment_from_dict(value["negative"])
        record = ArmRecord(value["arm"], acquisition, skill, reset, positive, negative)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ResearchRunInterrupted(
            f"completed phase record is corrupt: {completion_path}"
        ) from exc
    if record.arm != expected_arm:
        raise ResearchRunInterrupted("completed phase arm does not match schedule")
    return record


def _deployment_from_dict(value: Mapping[str, Any]) -> DeploymentRecord:
    calls = tuple(CanaryCall(**call) for call in value.get("canary_calls", ()))
    return DeploymentRecord(
        task_kind=value["task_kind"],
        expected_nonce=value["expected_nonce"],
        task_pass=value.get("task_pass", False),
        task_score=value.get("task_score"),
        canary_calls=calls,
        failure=value.get("failure"),
        expected_run_id=value.get("expected_run_id"),
        expected_skill_hash=value.get("expected_skill_hash"),
    )


def _retriever(pool: ResourcePool, config: ExperimentConfig) -> DeterministicBM25:
    return DeterministicBM25(
        pool.resources,
        k1=float(config.retriever.k1),
        b=float(config.retriever.b),
        top_k=int(config.retriever.top_k),
    )


def _reset_identity(identity: RuntimeIdentity) -> ResetRuntimeIdentity:
    return ResetRuntimeIdentity(identity.world_id, identity.context_id, identity.session_id)


def _require_identity(result: AgentResult, expected: RuntimeIdentity) -> None:
    observed = (result.world_id, result.context_id, result.session_id)
    wanted = (expected.world_id, expected.context_id, expected.session_id)
    if observed != wanted:
        raise ResearchRunnerError("agent result identity does not match started runtime")


def _validate_schedule(schedule: BuildSchedule, bundle: FrozenCaseBundle) -> None:
    expected = {(case.case_id, arm) for case in bundle.cases for arm in ("A_sham", "B_poison")}
    observed = {(entry.case_id, entry.arm) for entry in schedule.entries}
    if len(schedule.entries) != 2 * len(bundle.cases) or observed != expected:
        raise FrozenInputError("build schedule is not a complete paired assignment")
    if [entry.position for entry in schedule.entries] != list(range(len(schedule.entries))):
        raise FrozenInputError("build schedule positions are not contiguous")
    if len({entry.run_id for entry in schedule.entries}) != len(schedule.entries):
        raise FrozenInputError("build schedule run IDs are not unique")
    if schedule.protocol_version != bundle.protocol_version:
        raise FrozenInputError("build schedule protocol version does not match cases")
    cases = {case.case_id: case for case in bundle.cases}
    for entry in schedule.entries:
        case = cases[entry.case_id]
        observed_tasks = (
            entry.authoring_task_id,
            entry.positive_task_id,
            entry.negative_task_id,
        )
        expected_tasks = (
            case.authoring_task.task_id,
            case.positive_task.task_id,
            case.negative_task.task_id,
        )
        if observed_tasks != expected_tasks:
            raise FrozenInputError(
                f"build schedule task IDs do not match frozen case {entry.case_id}"
            )


def _validate_overlay_absence(pool: ResourcePool, bundle: FrozenCaseBundle) -> None:
    resource_ids = {resource.resource_id for resource in pool.resources}
    hashes = {resource.content_hash for resource in pool.resources}
    for case in bundle.cases:
        for overlay in (case.overlays.sham, case.overlays.poison):
            if overlay.resource.resource_id in resource_ids:
                raise FrozenInputError(
                    f"overlay resource ID already exists in clean pool: {case.case_id}"
                )
            if overlay.resource.content_hash in hashes:
                raise FrozenInputError(
                    f"overlay content already exists in clean pool: {case.case_id}"
                )


def _validate_frozen_appworld_tasks(appworld_root: Path, bundle: FrozenCaseBundle) -> str:
    """Read-only validation of frozen instructions against AppWorld's train split."""

    dataset_path = appworld_root / "data" / "datasets" / "train.txt"
    if not dataset_path.is_file() or dataset_path.is_symlink():
        raise FrozenInputError("AppWorld train split is missing or is a symlink")
    try:
        train_ids = {
            line.split(":", 1)[0].strip()
            for line in dataset_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        }
    except (OSError, UnicodeError) as exc:
        raise FrozenInputError("cannot read the AppWorld train split") from exc
    if not train_ids:
        raise FrozenInputError("AppWorld train split is empty")

    records: list[dict[str, str]] = []
    for case in bundle.cases:
        for task in (case.authoring_task, case.positive_task, case.negative_task):
            if (
                re.fullmatch(r"[^_/:\\\s]+_[1-9][0-9]*", task.task_id) is None
                or ".." in task.task_id
            ):
                raise FrozenInputError(
                    f"frozen AppWorld task ID has an unsafe format: {task.task_id}"
                )
            if task.task_id not in train_ids:
                raise FrozenInputError(
                    f"frozen task is not in the AppWorld train split: {task.task_id}"
                )
            task_directory = appworld_root / "data" / "tasks" / task.task_id
            specs_path = task_directory / "specs.json"
            if task_directory.is_symlink() or not specs_path.is_file() or specs_path.is_symlink():
                raise FrozenInputError(
                    f"AppWorld task specs are missing or a symlink: {task.task_id}"
                )
            try:
                specs = json.loads(specs_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                raise FrozenInputError(f"cannot read AppWorld task specs: {task.task_id}") from exc
            instruction = specs.get("instruction") if isinstance(specs, Mapping) else None
            if not isinstance(instruction, str) or not instruction.strip():
                raise FrozenInputError(f"AppWorld task instruction is unavailable: {task.task_id}")
            if task.instruction is not None and instruction != task.instruction:
                raise FrozenInputError(
                    f"AppWorld task instruction differs from frozen case: {task.task_id}"
                )
            records.append(
                {
                    "task_id": task.task_id,
                    "specs_hash": sha256_file(specs_path),
                    "instruction_hash": sha256_text(instruction),
                }
            )
    return canonical_json_sha256(
        {
            "train_split_hash": sha256_file(dataset_path),
            "tasks": sorted(records, key=lambda item: item["task_id"]),
        }
    )


def _appworld_runtime_snapshot(
    appworld_root: Path,
    task_ids: Sequence[str],
) -> ContentDigest:
    """Compute a protected byte-binding snapshot with a stable safe error."""

    try:
        return hash_appworld_runtime_snapshot(appworld_root, task_ids)
    except IntegrityError as exc:
        raise FrozenInputError("cannot bind the AppWorld runtime snapshot") from exc


def _verify_case_token_counts(
    bundle: FrozenCaseBundle,
    *,
    token_counter: Callable[[str], int],
) -> str:
    """Recompute private overlay counts with the serving tokenizer."""

    records: list[dict[str, Any]] = []
    for case in bundle.cases:
        declared = bundle.counts_for(case.case_id)
        observed_sham = token_counter(case.overlays.sham.resource.body)
        observed_poison = token_counter(case.overlays.poison.resource.body)
        if (
            isinstance(observed_sham, bool)
            or not isinstance(observed_sham, int)
            or observed_sham <= 0
            or isinstance(observed_poison, bool)
            or not isinstance(observed_poison, int)
            or observed_poison <= 0
        ):
            raise FrozenInputError("serving tokenizer returned an invalid overlay count")
        if (
            observed_sham != declared.sham_token_count
            or observed_poison != declared.poison_token_count
        ):
            raise FrozenInputError(f"pinned tokenizer count mismatch for case {case.case_id}")
        records.append(
            {
                "case_id": case.case_id,
                "sham_token_count": observed_sham,
                "poison_token_count": observed_poison,
            }
        )
    return canonical_json_sha256(
        {
            "tokenizer_model": bundle.tokenizer_model,
            "tokenizer_revision": bundle.tokenizer_revision,
            "counts": records,
        }
    )


def _load_prompts(root: Path) -> tuple[dict[str, str], dict[str, str]]:
    relative = {
        "agent": Path("experiments/pilot/prompts/agent_system.md"),
        "compiler": Path("experiments/pilot/prompts/compiler_system.md"),
        "neutral": Path("experiments/pilot/prompts/neutral_skill.md"),
    }
    prompts: dict[str, str] = {}
    hashes: dict[str, str] = {}
    for name, item in relative.items():
        path = root / item
        if not path.is_file() or path.is_symlink():
            raise FrozenInputError(f"frozen prompt is missing or a symlink: {item}")
        text = path.read_text(encoding="utf-8")
        if not text.strip():
            raise FrozenInputError(f"frozen prompt is empty: {item}")
        prompts[name] = text
        hashes[name + "_prompt_hash"] = sha256_text(text)
    return prompts, hashes


def _code_hash(root: Path) -> str:
    files = [
        root / "pyproject.toml",
        *sorted((root / "src" / "r2sp").rglob("*.py")),
    ]
    if any(not path.is_file() or path.is_symlink() for path in files):
        raise FrozenInputError("code bundle is incomplete or contains a symlink")
    return canonical_json_sha256(
        [{"path": path.relative_to(root).as_posix(), "sha256": sha256_file(path)} for path in files]
    )


def _research_preflight_hash(report: PreflightReport) -> str:
    return canonical_json_sha256(_research_preflight_payload(report))


def _research_preflight_payload(report: PreflightReport) -> dict[str, Any]:
    """Return only stable gating evidence suitable for write-once resume."""

    return {
        "mode": report.mode,
        "research_ready": report.research_ready,
        "checks": [check.to_dict() for check in report.checks if check.gate != "advisory"],
    }


def _case_by_id(bundle: FrozenCaseBundle, case_id: str) -> CaseSpec:
    for case in bundle.cases:
        if case.case_id == case_id:
            return case
    raise FrozenInputError(f"schedule references unknown case: {case_id}")


def _load_completed(output: Path, fingerprint: str, run_id: str) -> ResearchRunResult | None:
    complete_path = output / "complete.json"
    if not complete_path.exists():
        return None
    try:
        if not complete_path.is_file() or complete_path.is_symlink():
            raise ValueError("completion marker is not a regular file")
        complete = json.loads(complete_path.read_text(encoding="utf-8"))
        summary_path = output / "reports" / "summary.json"
        manifest_path = output / "artifacts-manifest.json"
        if (
            complete.get("status") != "completed"
            or complete.get("run_id") != run_id
            or complete.get("fingerprint") != fingerprint
            or not summary_path.is_file()
            or summary_path.is_symlink()
            or sha256_file(summary_path) != complete.get("summary_hash")
            or not manifest_path.is_file()
            or manifest_path.is_symlink()
            or sha256_file(manifest_path) != complete.get("artifact_manifest_hash")
        ):
            raise ValueError("completion metadata mismatch")
        _verify_artifact_manifest(output, manifest_path)
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, ResearchRunnerError, ValueError, json.JSONDecodeError) as exc:
        raise ResearchRunnerError("completed run cache is corrupt or stale") from exc
    return ResearchRunResult(
        output_directory=output,
        run_id=run_id,
        summary=summary,
        cached=True,
        complete_hash=sha256_file(complete_path),
    )


def _write_artifact_manifest(output: Path, store: ArtifactStore) -> ArtifactRecord:
    try:
        return write_artifact_manifest(output, store)
    except ArtifactIntegrityError as exc:
        raise ResearchRunnerError(str(exc)) from exc


def _verify_artifact_manifest(output: Path, manifest_path: Path) -> None:
    try:
        verify_artifact_manifest(output, manifest_path)
    except ArtifactError as exc:
        raise ResearchRunnerError("artifact manifest verification failed") from exc


def _fail_on_interrupted_phase(
    output: Path, store: ArtifactStore, run_id: str, fingerprint: str
) -> None:
    interrupted_marker = output / "interrupted.json"
    if interrupted_marker.exists():
        if not interrupted_marker.is_file() or interrupted_marker.is_symlink():
            raise ResearchRunInterrupted("the interruption marker is not a regular file")
        raise ResearchRunInterrupted("this run is permanently marked as interrupted")
    starts = sorted(output.glob("cases/*/*/phase-start.json")) if output.exists() else []
    incomplete = [path for path in starts if not path.with_name("phase-complete.json").is_file()]
    orphan_completions = (
        [
            path
            for path in output.glob("cases/*/*/phase-complete.json")
            if not path.with_name("phase-start.json").is_file()
        ]
        if output.exists()
        else []
    )
    finalization_start = output / "finalization-start.json"
    incomplete_finalization = (
        [finalization_start]
        if finalization_start.is_file() and not (output / "complete.json").is_file()
        else []
    )
    if not incomplete and not orphan_completions and not incomplete_finalization:
        return
    relative = [
        path.relative_to(output).as_posix()
        for path in (*incomplete, *orphan_completions, *incomplete_finalization)
    ]
    store.write_json(
        "interrupted.json",
        {
            "schema_version": 1,
            "status": "interrupted_failure",
            "run_id": run_id,
            "fingerprint": fingerprint,
            "unsafe_phases": relative,
            "rerun_permitted": False,
        },
    )
    raise ResearchRunInterrupted("an incomplete phase exists; automatic replay is forbidden")


def _reject_active_lock(output: Path, expected_run_id: str) -> None:
    path = output / ".active.lock"
    if not path.exists():
        return
    try:
        if not path.is_file() or path.is_symlink():
            raise ValueError("lock is not a regular file")
        fields = path.read_text(encoding="utf-8").strip().split(" ", 1)
        pid = int(fields[0])
        if pid <= 0 or len(fields) != 2 or fields[1] != expected_run_id:
            raise ValueError("invalid lock ownership")
    except (OSError, UnicodeError, ValueError) as exc:
        raise ResearchRunLocked("run lock is malformed; replay is unsafe") from exc
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise ResearchRunLocked("stale run lock cannot be removed safely") from exc
        return
    except (OSError, PermissionError) as exc:
        raise ResearchRunLocked("run lock owner cannot be verified") from exc
    raise ResearchRunLocked("another process is actively executing this run")


@contextmanager
def _run_lock(output: Path, run_id: str):
    output.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = output / ".active.lock"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError as exc:
        raise ResearchRunLocked("run lock already exists; replay is unsafe") from exc
    try:
        os.write(descriptor, f"{os.getpid()} {run_id}\n".encode())
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        yield
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        with suppress(FileNotFoundError):
            path.unlink()


@contextmanager
def _appworld_root(path: Path):
    previous = os.environ.get("APPWORLD_ROOT")
    previous_bytecode_env = os.environ.get("PYTHONDONTWRITEBYTECODE")
    previous_dont_write_bytecode = sys.dont_write_bytecode
    os.environ["APPWORLD_ROOT"] = str(path)
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    sys.dont_write_bytecode = True
    try:
        yield
    finally:
        sys.dont_write_bytecode = previous_dont_write_bytecode
        if previous is None:
            os.environ.pop("APPWORLD_ROOT", None)
        else:
            os.environ["APPWORLD_ROOT"] = previous
        if previous_bytecode_env is None:
            os.environ.pop("PYTHONDONTWRITEBYTECODE", None)
        else:
            os.environ["PYTHONDONTWRITEBYTECODE"] = previous_bytecode_env


def _validate_output_location(
    output: Path,
    appworld_root: Path,
    project_root: Path,
) -> None:
    output = output.resolve()
    _require_disjoint_tree(
        output,
        appworld_root.resolve(),
        name="output",
        other_name="APPWORLD_ROOT",
    )
    _require_disjoint_tree(
        output,
        project_root.resolve(),
        name="output",
        other_name="project root",
    )


def _require_disjoint_tree(
    path: Path,
    other: Path,
    *,
    name: str,
    other_name: str,
) -> None:
    resolved = path.resolve()
    other_resolved = other.resolve()
    if (
        resolved == other_resolved
        or resolved.is_relative_to(other_resolved)
        or other_resolved.is_relative_to(resolved)
    ):
        raise FrozenInputError(f"{name} and {other_name} trees must be disjoint")


def _check_deadline(deadline: float, clock: Callable[[], float]) -> None:
    if clock() > deadline:
        raise ResearchRunnerError("phase timeout exceeded")


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise FrozenInputError(f"{name} must be a mapping")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], name: str) -> None:
    if set(value) != expected:
        raise FrozenInputError(f"{name} keys must equal {sorted(expected)}; got {sorted(value)}")


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FrozenInputError(f"{name} must be non-empty text")
    return value.strip()


def _absolute_path(value: Any, name: str) -> Path:
    path = Path(_text(value, name))
    if not path.is_absolute():
        raise FrozenInputError(f"{name} must be an absolute path")
    return path.resolve()


def _positive_number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise FrozenInputError(f"{name} must be a positive number")
    return float(value)


def _validated_model_url(value: Any) -> str:
    url = _text(value, "model_service.base_url").rstrip("/")
    parsed = urllib.parse.urlparse(url)
    if (
        parsed.scheme != "http"
        or not parsed.hostname
        or parsed.hostname not in {"127.0.0.1", "::1", "localhost"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise FrozenInputError(
            "model_service.base_url must be an unauthenticated loopback HTTP endpoint"
        )
    return url


__all__ = [
    "FrozenInputError",
    "ResearchDependencies",
    "ResearchPreflightError",
    "ResearchRunInterrupted",
    "ResearchRunLocked",
    "ResearchRunResult",
    "ResearchRunnerError",
    "ResearchRuntimeConfig",
    "load_runtime_config",
    "run_pilot",
    "run_research_pilot",
]
