#!/usr/bin/env python3
"""Preflight, create, evaluate, or run the sealed full-document experiment."""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager, nullcontext
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
EXPERIMENT_ROOT = Path(__file__).resolve().parents[1]
BASE_CONFIG_PATH = EXPERIMENT_ROOT / "configs" / "experiment.yaml"
FORMAL_CONFIG_PATH = EXPERIMENT_ROOT / "configs" / "deepseek-v4-flash-formal.yaml"
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from r2sp_tau_knowledge.deepseek_v4_flash_formal import (  # noqa: E402
    DEEPSEEK_V4_FLASH_FORMAL_API_MODEL,
    DEEPSEEK_V4_FLASH_FORMAL_PROFILE,
    DeepSeekV4FlashFormalSpec,
    load_deepseek_v4_flash_formal_spec,
)
from r2sp_tau_knowledge.full_doc_experiment import (  # noqa: E402
    FullDocCreationRunner,
    FullDocEvaluationRunner,
)
from r2sp_tau_knowledge.full_doc_live import (  # noqa: E402
    FullDocOfficialCreationBackend,
    FullDocOfficialEvaluationBackend,
)
from r2sp_tau_knowledge.full_doc_records import (  # noqa: E402
    FullDocRecordError,
)
from r2sp_tau_knowledge.full_doc_records import (  # noqa: E402
    verify_creation_run as _verify_creation_run_unconfined,
)
from r2sp_tau_knowledge.full_doc_records import (  # noqa: E402
    verify_evaluation_run as _verify_evaluation_run_unconfined,
)
from r2sp_tau_knowledge.full_doc_services import (  # noqa: E402
    DEFAULT_HF_HOME,
    FullDocAssetPaths,
    FullDocInfrastructureError,
    FullDocRuntimeLock,
    FullDocServiceSupervisor,
    assert_api_embedding_final_gate,
    check_api_embedding_preflight,
    check_full_doc_preflight,
    inspect_gpu0,
    port_is_free,
)
from r2sp_tau_knowledge.full_doc_spec import (  # noqa: E402
    canonical_spec_identity_sha256,
    load_experiment_spec,
)
from r2sp_tau_knowledge.model import (  # noqa: E402
    GenerationConfig,
    OpenAICompatibleClient,
    SerializedChatTokenCounter,
    VllmTextTokenCounter,
)

_RUNTIME_PROFILES = (DEEPSEEK_V4_FLASH_FORMAL_PROFILE,)
_KEY_FILE = REPOSITORY_ROOT / "key.env"
_KEY_LINE = re.compile(r"DeepSeek\s*=\s*([^\s#]+)")


def _confined_path(
    path: Path,
    root: Path,
    label: str,
    *,
    allow_root: bool = False,
) -> Path:
    """Resolve an artifact path and keep it inside this experiment namespace."""

    boundary = root.resolve()
    candidate = Path(path).expanduser().resolve()
    if not candidate.is_relative_to(boundary) or (candidate == boundary and not allow_root):
        raise FullDocRecordError(f"{label} must remain under {boundary}")
    return candidate


def _creation_root(spec: Any) -> Path:
    return (spec.paths.runs_root / "creation").resolve()


def _evaluation_root(spec: Any) -> Path:
    return (spec.paths.runs_root / "evaluation").resolve()


def verify_creation_run(
    path: Path,
    spec: Any,
    *,
    expected_complete_sha256: str | None = None,
    expected_run_identity: Mapping[str, Any] | None = None,
) -> Any:
    """Verify only creation artifacts produced in this experiment directory."""

    confined = _confined_path(path, _creation_root(spec), "creation run")
    return _verify_creation_run_unconfined(
        confined,
        spec,
        expected_complete_sha256=expected_complete_sha256,
        expected_run_identity=expected_run_identity,
    )


def verify_evaluation_run(
    path: Path,
    spec: Any,
    creation: Any,
    *,
    expected_complete_sha256: str | None = None,
) -> Any:
    """Verify only evaluation artifacts produced in this experiment directory."""

    confined = _confined_path(path, _evaluation_root(spec), "evaluation run")
    return _verify_evaluation_run_unconfined(
        confined,
        spec,
        creation,
        expected_complete_sha256=expected_complete_sha256,
    )


def _confine_result_path(args: argparse.Namespace, spec: Any) -> None:
    value = getattr(args, "result_path", None)
    if value is None:
        return
    try:
        args.result_path = _confined_path(value, spec.paths.runs_root, "result path")
    except FullDocRecordError:
        # The generic CLI error path must not write to the rejected destination.
        args.result_path = None
        raise


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")


def _runtime_profile_name(args: argparse.Namespace) -> str:
    value = getattr(args, "runtime_profile", DEEPSEEK_V4_FLASH_FORMAL_PROFILE)
    if value not in _RUNTIME_PROFILES:
        raise FullDocInfrastructureError("runtime profile is not registered")
    return value


def _runtime_specs(
    args: argparse.Namespace,
) -> tuple[Any, Any, DeepSeekV4FlashFormalSpec | None]:
    base = load_experiment_spec(BASE_CONFIG_PATH)
    if _runtime_profile_name(args) != DEEPSEEK_V4_FLASH_FORMAL_PROFILE:
        raise FullDocInfrastructureError("runtime profile is not registered")
    profile = load_deepseek_v4_flash_formal_spec(FORMAL_CONFIG_PATH, base=base)
    runtime = profile.runtime_spec(base)
    _confine_result_path(args, runtime)
    return base, runtime, profile


def _load_deepseek_key(path: Path = _KEY_FILE) -> str:
    metadata = path.lstat()
    mode = stat.S_IMODE(metadata.st_mode)
    if not stat.S_ISREG(metadata.st_mode) or path.is_symlink() or metadata.st_uid != os.getuid():
        raise FullDocInfrastructureError("key.env must be an owner-controlled regular file")
    if mode & ~0o600 or not mode & stat.S_IRUSR:
        raise FullDocInfrastructureError(
            "key.env permissions must be no wider than 0600 and owner-readable"
        )
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise FullDocInfrastructureError("key.env must be UTF-8") from exc
    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if len(lines) != 1:
        raise FullDocInfrastructureError("key.env must contain exactly one DeepSeek assignment")
    match = _KEY_LINE.fullmatch(lines[0])
    if match is None:
        raise FullDocInfrastructureError("key.env must contain only `DeepSeek = <credential>`")
    value = match.group(1)
    if len(value) < 20 or len(value) > 512 or any(ord(character) < 33 for character in value):
        raise FullDocInfrastructureError("DeepSeek credential has an invalid shape")
    return value


@contextmanager
def _worker_credential(profile: DeepSeekV4FlashFormalSpec, value: str) -> Iterator[None]:
    previous = os.environ.get(profile.api_key_env)
    os.environ[profile.api_key_env] = value
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(profile.api_key_env, None)
        else:
            os.environ[profile.api_key_env] = previous


def _deepseek_provider_identity(
    profile: DeepSeekV4FlashFormalSpec,
    key: str,
) -> dict[str, Any]:
    request = urllib.request.Request(
        profile.api_base.rstrip("/") + "/models",
        headers={"Authorization": f"Bearer {key}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            value = json.loads(response.read(1024 * 1024))
    except (
        OSError,
        TimeoutError,
        urllib.error.URLError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
        raise FullDocInfrastructureError("DeepSeek models endpoint is unavailable") from exc
    records = value.get("data") if isinstance(value, Mapping) else None
    ids = sorted(
        item["id"]
        for item in records or []
        if isinstance(item, Mapping) and isinstance(item.get("id"), str)
    )
    if DEEPSEEK_V4_FLASH_FORMAL_API_MODEL not in ids:
        raise FullDocInfrastructureError("DeepSeek-V4-Flash is unavailable to this credential")
    return {
        "transport": "deepseek",
        "api_base": profile.api_base,
        "requested_model": DEEPSEEK_V4_FLASH_FORMAL_API_MODEL,
        "resolved_model": DEEPSEEK_V4_FLASH_FORMAL_API_MODEL,
    }


def _api_compiler_client(
    spec: Any,
    profile: DeepSeekV4FlashFormalSpec,
    key: str,
) -> OpenAICompatibleClient:
    generation = spec.model.generation
    counter = SerializedChatTokenCounter(
        VllmTextTokenCounter(
            profile.tokenizer_endpoint,
            model=profile.tokenizer_model,
            timeout_seconds=spec.request_timeout_seconds,
        ),
        basis=profile.token_counter_basis,
    )
    return OpenAICompatibleClient(
        profile.api_base,
        api_key=key,
        config=GenerationConfig(
            model=profile.compiler_model,
            temperature=generation.temperature,
            top_p=generation.top_p,
            top_k=generation.top_k,
            min_p=generation.min_p,
            presence_penalty=generation.presence_penalty,
            repetition_penalty=generation.repetition_penalty,
            enable_thinking=profile.compiler_thinking,
            preserve_thinking=profile.preserve_thinking,
            reasoning_effort=profile.compiler_reasoning_effort,
            max_output_tokens=profile.compiler_max_output_tokens,
            max_input_tokens=spec.context.request_input_token_limit,
            transport="deepseek",
        ),
        timeout_seconds=spec.request_timeout_seconds,
        token_counter=counter,
    )


def _assert_secret_absent(root: Path, secret: str) -> dict[str, Any]:
    needle = secret.encode()
    scanned = 0
    for path in sorted(root.rglob("*")):
        if path.is_file():
            scanned += 1
            if needle in path.read_bytes():
                raise FullDocRecordError("credential material appeared in an experiment artifact")
    return {"status": "PASS", "files_scanned": scanned, "credential_occurrences": 0}


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    ).encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            descriptor = -1
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary_name and Path(temporary_name).exists():
            Path(temporary_name).unlink()


def _emit(value: dict[str, Any], *, result_path: Path | None = None) -> None:
    payload = {"timestamp": _timestamp(), **value}
    if result_path is not None:
        _atomic_json(result_path, payload)
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True), flush=True)


def _runtime_lock(spec: Any) -> Path:
    return spec.paths.data_root / "gpu0-runtime.lock"


def _asset_paths(args: argparse.Namespace, spec: Any) -> FullDocAssetPaths:
    defaults = FullDocAssetPaths.defaults(spec.paths.repository_root)
    return FullDocAssetPaths(
        vllm=(args.vllm or defaults.vllm).resolve(),
        hf_home=(args.hf_home or defaults.hf_home).resolve(),
    )


def _deferred(spec: Any, phase: str, evidence: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "status": "DEFERRED",
        "phase": phase,
        "experiment_config_sha256": spec.config_sha256,
        "evidence": evidence,
    }
    path = spec.paths.runs_root / "deferred" / f"{phase}-{_timestamp()}.json"
    _atomic_json(path, payload)
    return {**payload, "evidence_path": str(path)}


def _preflight_once(
    spec: Any,
    paths: FullDocAssetPaths,
    *,
    require_embedding: bool,
    api_profile: DeepSeekV4FlashFormalSpec | None = None,
) -> Any:
    if api_profile is not None:
        if not require_embedding:
            raise FullDocInfrastructureError(
                "the DeepSeek formal runtime requires its tokenizer service"
            )
        return check_api_embedding_preflight(
            spec,
            paths,
            runtime_lock=_runtime_lock(spec),
        )
    return check_full_doc_preflight(
        spec,
        paths,
        require_embedding=require_embedding,
        runtime_lock=_runtime_lock(spec),
    )


def _wait_preflight(
    spec: Any,
    paths: FullDocAssetPaths,
    *,
    require_embedding: bool,
    wait: bool,
    poll_seconds: float,
    phase: str,
    result_path: Path | None,
    api_profile: DeepSeekV4FlashFormalSpec | None = None,
) -> Any | None:
    while True:
        report = _preflight_once(
            spec,
            paths,
            require_embedding=require_embedding,
            api_profile=api_profile,
        )
        if report.ready:
            return report
        payload = _deferred(spec, phase, report.to_dict())
        if not wait:
            _emit(payload, result_path=result_path)
            return None
        _emit(
            {
                **payload,
                "status": "WAITING_GPU",
                "next_poll_seconds": poll_seconds,
            },
            # Preserve a prior sealed SUCCESS result across an orphan-owner
            # overlap; the terminal child result alone owns result_path.
            result_path=None,
        )
        time.sleep(poll_seconds)


def _final_gate(
    spec: Any,
    preflight: Any,
    *,
    require_embedding: bool,
    api_profile: DeepSeekV4FlashFormalSpec | None = None,
) -> dict[str, Any]:
    if api_profile is not None:
        if not require_embedding:
            raise FullDocInfrastructureError(
                "the DeepSeek formal runtime requires its tokenizer service"
            )
        return assert_api_embedding_final_gate(spec, preflight).to_dict()
    observation = inspect_gpu0(spec.services.gpu_uuid)
    baseline = preflight.gpu.final
    endpoints = [spec.services.llm_endpoint]
    if require_embedding:
        endpoints.append(spec.services.embedding_endpoint)
    if (
        baseline is None
        or observation.uuid != baseline.uuid
        or observation.compute_pids != baseline.compute_pids
        or observation.memory_free_mib < spec.services.minimum_free_memory_mib
        or not all(port_is_free(endpoint) for endpoint in endpoints)
    ):
        raise FullDocInfrastructureError("GPU, PID, memory, or port state changed after preflight")
    return observation.to_dict()


def _commitment_execution_id(commitment: Any) -> str | None:
    if not isinstance(commitment, dict):
        return None
    run_identity = commitment.get("run_identity")
    services = run_identity.get("model_services") if isinstance(run_identity, dict) else None
    value = services.get("pipeline_execution_id") if isinstance(services, dict) else None
    return value if isinstance(value, str) and value else None


def _unsealed_creation(runs_root: Path, execution_id: str | None) -> Path | None:
    if not runs_root.is_dir():
        return None
    candidates: list[Path] = []
    for path in sorted(runs_root.glob("full-doc-create-*")):
        commitment_path = path / "commitment.json"
        if not path.is_dir() or not commitment_path.is_file() or (path / "complete.json").exists():
            continue
        try:
            commitment = json.loads(commitment_path.read_bytes())
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if execution_id is None or _commitment_execution_id(commitment) == execution_id:
            candidates.append(path)
    if len(candidates) > 1:
        raise FullDocRecordError("multiple unsealed creation runs require explicit selection")
    return candidates[0] if candidates else None


def _sealed_creation_for_execution(
    runs_root: Path,
    spec: Any,
    execution_id: str,
) -> Any | None:
    if not runs_root.is_dir():
        return None
    candidates: list[Any] = []
    for path in sorted(runs_root.glob("full-doc-create-*")):
        if not (path / "complete.json").is_file():
            continue
        try:
            sealed = verify_creation_run(path, spec)
        except (OSError, FullDocRecordError):
            continue
        if _commitment_execution_id(sealed.commitment) == execution_id:
            candidates.append(sealed)
    if len(candidates) > 1:
        raise FullDocRecordError("pipeline execution has multiple sealed creation runs")
    return candidates[0] if candidates else None


def _execution_id_from_creation_path(path: Path) -> str | None:
    try:
        commitment = json.loads((path / "commitment.json").read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return _commitment_execution_id(commitment)


def _unsealed_evaluation(runs_root: Path, creation: Any) -> Path | None:
    if not runs_root.is_dir():
        return None
    candidates: list[Path] = []
    for path in sorted(runs_root.glob("full-doc-evaluate-*")):
        binding_path = path / "creation-binding.json"
        if not path.is_dir() or not binding_path.is_file() or (path / "complete.json").exists():
            continue
        try:
            binding = json.loads(binding_path.read_bytes())
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if (
            binding.get("creation_run") == str(creation.root.resolve())
            and binding.get("creation_complete_sha256") == creation.complete_sha256
        ):
            candidates.append(path)
    if len(candidates) > 1:
        raise FullDocRecordError("multiple unsealed evaluation runs require explicit selection")
    return candidates[0] if candidates else None


def _sealed_evaluation_for_creation(runs_root: Path, spec: Any, creation: Any) -> Any | None:
    if not runs_root.is_dir():
        return None
    candidates: list[Any] = []
    for path in sorted(runs_root.glob("full-doc-evaluate-*")):
        if not (path / "complete.json").is_file():
            continue
        try:
            sealed = verify_evaluation_run(path, spec, creation)
        except (OSError, FullDocRecordError):
            continue
        candidates.append(sealed)
    if len(candidates) > 1:
        raise FullDocRecordError("creation has multiple sealed evaluation runs")
    return candidates[0] if candidates else None


def _service_log_root(spec: Any, phase: str) -> Path:
    return spec.paths.service_logs_root / f"{phase}-{_timestamp()}"


def _create(args: argparse.Namespace) -> int:
    base_spec, spec, api_profile = _runtime_specs(args)
    canonical_runs_root = _creation_root(spec)
    runs_root = _confined_path(
        args.runs_root or canonical_runs_root,
        canonical_runs_root,
        "creation runs root",
        allow_root=True,
    )
    resume_path = (
        _confined_path(args.resume_run, runs_root, "creation resume run")
        if args.resume_run is not None
        else None
    )
    api_key = _load_deepseek_key() if api_profile is not None else None
    if resume_path is None and args.auto_resume:
        resume_path = _unsealed_creation(runs_root, args.execution_id)
    execution_id = args.execution_id
    if execution_id is None and resume_path is not None:
        execution_id = _execution_id_from_creation_path(resume_path)
    if execution_id is None:
        execution_id = f"standalone-{uuid.uuid4().hex}"
    if args.reuse_sealed_result:
        recovered = (
            _recover_creation_result(args.result_path, spec)
            if args.result_path is not None
            else None
        )
        if recovered is not None and _commitment_execution_id(recovered.commitment) != execution_id:
            recovered = None
        if recovered is None:
            recovered = _sealed_creation_for_execution(runs_root, spec, execution_id)
        if recovered is not None:
            _emit(
                {
                    "status": "SUCCESS",
                    "phase": "creation",
                    "creation_run": str(recovered.root),
                    "creation_complete_sha256": recovered.complete_sha256,
                    "evaluable_skills": sum(
                        item["status"] == "EVALUABLE" for item in recovered.skills
                    ),
                    "format_valid_skills": sum(
                        item.get("format_valid") is True for item in recovered.skills
                    ),
                    "trial_records": len(recovered.skills),
                    "recovered_sealed_result": True,
                    "pipeline_execution_id": execution_id,
                },
                result_path=args.result_path,
            )
            return 0
    paths = _asset_paths(args, spec)
    preflight = _wait_preflight(
        spec,
        paths,
        require_embedding=True,
        wait=args.wait_for_gpu,
        poll_seconds=args.poll_seconds,
        phase="creation-preflight",
        result_path=args.result_path,
        api_profile=api_profile,
    )
    if preflight is None:
        return 3
    if args.reuse_sealed_result:
        recovered = (
            _recover_creation_result(args.result_path, spec)
            if args.result_path is not None
            else None
        )
        if recovered is not None and _commitment_execution_id(recovered.commitment) != execution_id:
            recovered = None
        if recovered is None:
            recovered = _sealed_creation_for_execution(runs_root, spec, execution_id)
        if recovered is not None:
            _emit(
                {
                    "status": "SUCCESS",
                    "phase": "creation",
                    "creation_run": str(recovered.root),
                    "creation_complete_sha256": recovered.complete_sha256,
                    "evaluable_skills": sum(
                        item["status"] == "EVALUABLE" for item in recovered.skills
                    ),
                    "format_valid_skills": sum(
                        item.get("format_valid") is True for item in recovered.skills
                    ),
                    "trial_records": len(recovered.skills),
                    "recovered_sealed_result": True,
                    "pipeline_execution_id": execution_id,
                },
                result_path=args.result_path,
            )
            return 0
    log_root = _service_log_root(spec, "creation")
    provider_identity: dict[str, Any] | None = None
    credential_scan: dict[str, Any] | None = None
    try:
        credential_context = (
            _worker_credential(api_profile, api_key)
            if api_profile is not None and api_key is not None
            else nullcontext()
        )
        with credential_context:
            if api_profile is not None and api_key is not None:
                provider_identity = _deepseek_provider_identity(api_profile, api_key)
            with FullDocRuntimeLock(_runtime_lock(spec), gpu_uuid=spec.services.gpu_uuid):
                final_gpu = _final_gate(
                    spec,
                    preflight,
                    require_embedding=True,
                    api_profile=api_profile,
                )
                with FullDocServiceSupervisor(
                    spec,
                    paths,
                    log_root=log_root,
                    include_embedding=True,
                    include_llm=api_profile is None,
                ) as services:

                    def health(names: tuple[str, ...]) -> None:
                        services.ensure(names)
                        if api_profile is not None and api_key is not None:
                            _deepseek_provider_identity(api_profile, api_key)

                    backend_kwargs: dict[str, Any] = {}
                    if api_profile is not None and api_key is not None:
                        backend_kwargs = {
                            "compiler_client": _api_compiler_client(spec, api_profile, api_key),
                            "compiler_max_output_tokens": api_profile.compiler_max_output_tokens,
                            "runtime_profile": DEEPSEEK_V4_FLASH_FORMAL_PROFILE,
                            "requires_llm_service": False,
                            "expected_base_spec_identity_sha256": (
                                canonical_spec_identity_sha256(base_spec)
                            ),
                        }
                    backend = FullDocOfficialCreationBackend(
                        spec,
                        dense_builder_python=paths.python,
                        hf_home=paths.hf_home,
                        service_identity={
                            **services.identity(),
                            "pipeline_execution_id": execution_id,
                            "runtime_profile": _runtime_profile_name(args),
                            "runtime_profile_identity": (
                                api_profile.identity(base_spec) if api_profile is not None else None
                            ),
                            "provider": provider_identity,
                        },
                        health_hook=health,
                        **backend_kwargs,
                    )
                    run = FullDocCreationRunner(
                        spec,
                        backend,
                        runs_root=runs_root,
                    ).run(resume_path=resume_path)
                    service_history = list(services.operational_history)
            if api_key is not None:
                credential_scan = _assert_secret_absent(run.root, api_key)
    except FullDocInfrastructureError as exc:
        payload = _deferred(
            spec,
            "creation-runtime",
            {"reason": f"{type(exc).__name__}: {exc}", "service_logs": str(log_root)},
        )
        _emit(payload, result_path=args.result_path)
        return 3
    except Exception as exc:
        _emit(
            {
                "status": "INVALID",
                "phase": "creation",
                "reason": f"{type(exc).__name__}: {exc}",
                "service_logs": str(log_root),
            },
            result_path=args.result_path,
        )
        return 2
    _emit(
        {
            "status": "SUCCESS",
            "phase": "creation",
            "creation_run": str(run.root),
            "creation_complete_sha256": run.complete_sha256,
            "evaluable_skills": sum(item["status"] == "EVALUABLE" for item in run.skills),
            "format_valid_skills": sum(item.get("format_valid") is True for item in run.skills),
            "trial_records": len(run.skills),
            "pipeline_execution_id": execution_id,
            "runtime_profile": _runtime_profile_name(args),
            "provider": provider_identity,
            "credential_scan": credential_scan,
            "gpu": final_gpu,
            "service_logs": str(log_root),
            "owned_service_starts": service_history,
        },
        result_path=args.result_path,
    )
    return 0


def _evaluate(args: argparse.Namespace) -> int:
    base_spec, spec, api_profile = _runtime_specs(args)
    canonical_runs_root = _evaluation_root(spec)
    runs_root = _confined_path(
        args.runs_root or canonical_runs_root,
        canonical_runs_root,
        "evaluation runs root",
        allow_root=True,
    )
    resume_path = (
        _confined_path(args.resume_run, runs_root, "evaluation resume run")
        if args.resume_run is not None
        else None
    )
    api_key = _load_deepseek_key() if api_profile is not None else None
    try:
        creation = verify_creation_run(
            args.creation_run,
            spec,
            expected_complete_sha256=args.creation_complete_sha256,
        )
    except (OSError, FullDocRecordError) as exc:
        _emit(
            {"status": "INVALID", "phase": "evaluation-binding", "reason": str(exc)},
            result_path=args.result_path,
        )
        return 2
    if args.reuse_sealed_result:
        recovered = (
            _recover_evaluation_result(args.result_path, spec, creation)
            if args.result_path is not None
            else None
        )
        if recovered is None:
            recovered = _sealed_evaluation_for_creation(runs_root, spec, creation)
        if recovered is not None:
            _emit(
                {
                    "status": "SUCCESS",
                    "phase": "evaluation",
                    "evaluation_run": str(recovered.root),
                    "evaluation_complete_sha256": recovered.complete_sha256,
                    "creation_run": str(creation.root),
                    "creation_complete_sha256": creation.complete_sha256,
                    "trial_records": recovered.complete["trial_count"],
                    "metrics": recovered.metrics,
                    "recovered_sealed_result": True,
                },
                result_path=args.result_path,
            )
            return 0
    paths = _asset_paths(args, spec)
    preflight = _wait_preflight(
        spec,
        paths,
        require_embedding=api_profile is not None,
        wait=args.wait_for_gpu,
        poll_seconds=args.poll_seconds,
        phase="evaluation-preflight",
        result_path=args.result_path,
        api_profile=api_profile,
    )
    if preflight is None:
        return 3
    if args.reuse_sealed_result:
        recovered = (
            _recover_evaluation_result(args.result_path, spec, creation)
            if args.result_path is not None
            else None
        )
        if recovered is None:
            recovered = _sealed_evaluation_for_creation(runs_root, spec, creation)
        if recovered is not None:
            _emit(
                {
                    "status": "SUCCESS",
                    "phase": "evaluation",
                    "evaluation_run": str(recovered.root),
                    "evaluation_complete_sha256": recovered.complete_sha256,
                    "creation_run": str(creation.root),
                    "creation_complete_sha256": creation.complete_sha256,
                    "trial_records": recovered.complete["trial_count"],
                    "metrics": recovered.metrics,
                    "recovered_sealed_result": True,
                },
                result_path=args.result_path,
            )
            return 0
    if resume_path is None and args.auto_resume:
        resume_path = _unsealed_evaluation(runs_root, creation)
    log_root = _service_log_root(spec, "evaluation")
    provider_identity: dict[str, Any] | None = None
    credential_scan: dict[str, Any] | None = None
    try:
        credential_context = (
            _worker_credential(api_profile, api_key)
            if api_profile is not None and api_key is not None
            else nullcontext()
        )
        with credential_context:
            if api_profile is not None and api_key is not None:
                provider_identity = _deepseek_provider_identity(api_profile, api_key)
            with FullDocRuntimeLock(_runtime_lock(spec), gpu_uuid=spec.services.gpu_uuid):
                final_gpu = _final_gate(
                    spec,
                    preflight,
                    require_embedding=api_profile is not None,
                    api_profile=api_profile,
                )
                with FullDocServiceSupervisor(
                    spec,
                    paths,
                    log_root=log_root,
                    include_embedding=api_profile is not None,
                    include_llm=api_profile is None,
                ) as services:

                    def health(names: tuple[str, ...]) -> None:
                        services.ensure(names)
                        if api_profile is not None and api_key is not None:
                            _deepseek_provider_identity(api_profile, api_key)

                    backend_kwargs: dict[str, Any] = {}
                    if api_profile is not None:
                        backend_kwargs = {
                            "runtime_profile": DEEPSEEK_V4_FLASH_FORMAL_PROFILE,
                            "requires_llm_service": False,
                            "expected_base_spec_identity_sha256": (
                                canonical_spec_identity_sha256(base_spec)
                            ),
                        }
                    run = FullDocEvaluationRunner(
                        spec,
                        FullDocOfficialEvaluationBackend(
                            spec,
                            service_identity={
                                **services.identity(),
                                "runtime_profile": _runtime_profile_name(args),
                                "runtime_profile_identity": (
                                    api_profile.identity(base_spec)
                                    if api_profile is not None
                                    else None
                                ),
                                "provider": provider_identity,
                            },
                            health_hook=health,
                            **backend_kwargs,
                        ),
                        runs_root=runs_root,
                    ).run(
                        creation.root,
                        expected_complete_sha256=creation.complete_sha256,
                        resume_path=resume_path,
                    )
                    service_history = list(services.operational_history)
            if api_key is not None:
                credential_scan = _assert_secret_absent(run.root, api_key)
    except FullDocInfrastructureError as exc:
        payload = _deferred(
            spec,
            "evaluation-runtime",
            {"reason": f"{type(exc).__name__}: {exc}", "service_logs": str(log_root)},
        )
        _emit(payload, result_path=args.result_path)
        return 3
    except Exception as exc:
        _emit(
            {
                "status": "INVALID",
                "phase": "evaluation",
                "reason": f"{type(exc).__name__}: {exc}",
                "service_logs": str(log_root),
            },
            result_path=args.result_path,
        )
        return 2
    _emit(
        {
            "status": "SUCCESS",
            "phase": "evaluation",
            "evaluation_run": str(run.root),
            "evaluation_complete_sha256": run.complete_sha256,
            "creation_run": str(creation.root),
            "creation_complete_sha256": creation.complete_sha256,
            "trial_records": run.complete["trial_count"],
            "metrics": run.metrics,
            "runtime_profile": _runtime_profile_name(args),
            "provider": provider_identity,
            "credential_scan": credential_scan,
            "gpu": final_gpu,
            "service_logs": str(log_root),
            "owned_service_starts": service_history,
        },
        result_path=args.result_path,
    )
    return 0


def _preflight(args: argparse.Namespace) -> int:
    _base_spec, spec, api_profile = _runtime_specs(args)
    provider_identity: dict[str, Any] | None = None
    if api_profile is not None:
        api_key = _load_deepseek_key()
        provider_identity = _deepseek_provider_identity(api_profile, api_key)
    paths = _asset_paths(args, spec)
    require_embedding = args.phase == "creation" or api_profile is not None
    report = _preflight_once(
        spec,
        paths,
        require_embedding=require_embedding,
        api_profile=api_profile,
    )
    status = "SUCCESS" if report.ready else "DEFERRED"
    _emit(
        {
            "status": status,
            "phase": f"{args.phase}-preflight",
            "provider": provider_identity,
            **report.to_dict(),
        },
        result_path=args.result_path,
    )
    return 0 if report.ready else 3


def _child_common(args: argparse.Namespace) -> list[str]:
    # The pipeline parent owns GPU waiting and state transitions. Children must
    # return DEFERRED (exit 3) after one preflight attempt so the parent can
    # publish WAITING_GPU before retrying them.
    default_vllm = FullDocAssetPaths.defaults(REPOSITORY_ROOT).vllm
    values = [
        "--vllm",
        str(args.vllm.resolve()) if args.vllm else str(default_vllm),
        "--hf-home",
        str(args.hf_home.resolve()) if args.hf_home else str(DEFAULT_HF_HOME),
        "--poll-seconds",
        str(args.poll_seconds),
        "--runtime-profile",
        _runtime_profile_name(args),
    ]
    return values


def _read_result(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"{label} child did not publish a valid result") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"{label} child result is not an object")
    return value


def _recover_creation_result(path: Path, spec: Any) -> Any | None:
    if not path.is_file():
        return None
    try:
        value = _read_result(path, "creation")
    except (OSError, RuntimeError) as exc:
        raise FullDocRecordError("recorded creation result is unreadable") from exc
    if value.get("status") != "SUCCESS":
        return None
    run_path = value.get("creation_run")
    digest = value.get("creation_complete_sha256")
    if not isinstance(run_path, str) or not isinstance(digest, str):
        raise FullDocRecordError("recorded creation result anchor is incomplete")
    try:
        return verify_creation_run(
            Path(run_path),
            spec,
            expected_complete_sha256=digest,
        )
    except (OSError, FullDocRecordError) as exc:
        raise FullDocRecordError("recorded creation result anchor failed verification") from exc


def _recover_evaluation_result(path: Path, spec: Any, creation: Any) -> Any | None:
    if not path.is_file():
        return None
    try:
        value = _read_result(path, "evaluation")
    except (OSError, RuntimeError) as exc:
        raise FullDocRecordError("recorded evaluation result is unreadable") from exc
    if value.get("status") != "SUCCESS":
        return None
    if value.get("creation_complete_sha256") != creation.complete_sha256:
        return None
    run_path = value.get("evaluation_run")
    digest = value.get("evaluation_complete_sha256")
    if not isinstance(run_path, str) or not isinstance(digest, str):
        raise FullDocRecordError("recorded evaluation result anchor is incomplete")
    try:
        return verify_evaluation_run(
            Path(run_path),
            spec,
            creation,
            expected_complete_sha256=digest,
        )
    except (OSError, FullDocRecordError) as exc:
        raise FullDocRecordError("recorded evaluation result anchor failed verification") from exc


def _run_pipeline_child(
    command: list[str],
    *,
    result_path: Path,
    label: str,
    wait_for_gpu: bool,
    poll_seconds: float,
    state_path: Path,
    state: dict[str, Any],
) -> tuple[subprocess.CompletedProcess[bytes], dict[str, Any]]:
    while True:
        completed = subprocess.run(command, cwd=REPOSITORY_ROOT)
        result = _read_result(result_path, label)
        if completed.returncode != 3 or not wait_for_gpu:
            return completed, result
        _atomic_json(
            state_path,
            {
                **state,
                "status": "WAITING_GPU",
                "waiting_phase": label,
                "updated_at": _timestamp(),
                "result": result,
            },
        )
        time.sleep(poll_seconds)


def _pipeline(args: argparse.Namespace) -> int:
    _base_spec, spec, api_profile = _runtime_specs(args)
    background_root = (spec.paths.runs_root / "background").resolve()
    state_path = _confined_path(
        args.state_path or background_root / "pipeline-state.json",
        background_root,
        "pipeline state",
    )
    state: dict[str, Any] = {}
    if state_path.is_file():
        try:
            loaded = json.loads(state_path.read_bytes())
            state = loaded if isinstance(loaded, dict) else {}
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            state = {}
    if state.get("status") == "COMPLETE":
        try:
            creation_run = state["creation_run"]
            creation_hash = state["creation_complete_sha256"]
            evaluation_run = state["evaluation_run"]
            evaluation_hash = state["evaluation_complete_sha256"]
            if not all(
                isinstance(value, str)
                for value in (creation_run, creation_hash, evaluation_run, evaluation_hash)
            ):
                raise FullDocRecordError("pipeline state is missing sealed-result hashes")
            creation = verify_creation_run(
                Path(creation_run),
                spec,
                expected_complete_sha256=creation_hash,
            )
            evaluation = verify_evaluation_run(
                Path(evaluation_run),
                spec,
                creation,
                expected_complete_sha256=evaluation_hash,
            )
            if state.get("metrics") != evaluation.metrics:
                raise FullDocRecordError("pipeline state metrics do not match the evaluation")
        except (KeyError, OSError, FullDocRecordError) as exc:
            raise FullDocRecordError(
                "recorded COMPLETE pipeline state failed sealed verification"
            ) from exc
        else:
            _emit({**state, "status": "SUCCESS", "phase": "pipeline"})
            return 0

    recorded_profile = state.get("runtime_profile")
    if recorded_profile is not None and recorded_profile != _runtime_profile_name(args):
        raise FullDocRecordError("pipeline state belongs to a different runtime profile")
    recorded_profile_sha256 = state.get("runtime_profile_config_sha256")
    expected_profile_sha256 = (
        api_profile.config_sha256 if api_profile is not None else spec.config_sha256
    )
    if recorded_profile_sha256 is not None and recorded_profile_sha256 != expected_profile_sha256:
        raise FullDocRecordError("pipeline runtime profile config changed")

    execution_id = state.get("pipeline_execution_id")
    if not isinstance(execution_id, str) or not execution_id:
        execution_id = f"pipeline-{uuid.uuid4().hex}"
    for stale_field in ("result", "reason", "waiting_phase"):
        state.pop(stale_field, None)
    state = {
        **state,
        "schema_version": spec.schema_version,
        "status": "RUNNING_CREATION",
        "pipeline_pid": os.getpid(),
        "pipeline_execution_id": execution_id,
        "runtime_profile": _runtime_profile_name(args),
        "runtime_profile_config_sha256": (expected_profile_sha256),
        "updated_at": _timestamp(),
    }
    _atomic_json(state_path, state)
    work_root = state_path.parent
    create_result_path = work_root / "create-result.json"
    creation_path: Path | None = None
    creation_hash: str | None = None
    existing = state.get("creation_run")
    expected_existing_hash = state.get("creation_complete_sha256")
    if existing is not None or expected_existing_hash is not None:
        if not isinstance(existing, str) or not isinstance(expected_existing_hash, str):
            raise FullDocRecordError("pipeline creation anchor is incomplete")
        try:
            sealed = verify_creation_run(
                Path(existing),
                spec,
                expected_complete_sha256=expected_existing_hash,
            )
        except (OSError, FullDocRecordError) as exc:
            raise FullDocRecordError("pipeline creation anchor failed verification") from exc
        if _commitment_execution_id(sealed.commitment) != execution_id:
            raise FullDocRecordError("pipeline creation anchor has the wrong execution id")
        creation_path = sealed.root
        creation_hash = sealed.complete_sha256
    if creation_path is None:
        sealed = _recover_creation_result(create_result_path, spec)
        if sealed is not None and _commitment_execution_id(sealed.commitment) == execution_id:
            creation_path = sealed.root
            creation_hash = sealed.complete_sha256
    if creation_path is None:
        sealed = _sealed_creation_for_execution(
            spec.paths.runs_root / "creation",
            spec,
            execution_id,
        )
        if sealed is not None:
            creation_path = sealed.root
            creation_hash = sealed.complete_sha256
    if creation_path is None:
        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "create",
            "--auto-resume",
            "--reuse-sealed-result",
            "--execution-id",
            execution_id,
            "--result-path",
            str(create_result_path),
            *_child_common(args),
        ]
        completed, result = _run_pipeline_child(
            command,
            result_path=create_result_path,
            label="creation",
            wait_for_gpu=args.wait_for_gpu,
            poll_seconds=args.poll_seconds,
            state_path=state_path,
            state=state,
        )
        if completed.returncode != 0 or result.get("status") != "SUCCESS":
            _atomic_json(
                state_path,
                {
                    **state,
                    "status": "CREATION_FAILED",
                    "updated_at": _timestamp(),
                    "result": result,
                },
            )
            return completed.returncode or 2
        sealed = _recover_creation_result(create_result_path, spec)
        if sealed is None or _commitment_execution_id(sealed.commitment) != execution_id:
            _atomic_json(
                state_path,
                {
                    **state,
                    "status": "CREATION_FAILED",
                    "updated_at": _timestamp(),
                    "result": result,
                    "reason": "creation child result failed sealed verification",
                },
            )
            return 2
        creation_path = sealed.root
        creation_hash = sealed.complete_sha256
    assert creation_hash is not None
    state = {
        **state,
        "status": "RUNNING_EVALUATION",
        "creation_run": str(creation_path),
        "creation_complete_sha256": creation_hash,
        "updated_at": _timestamp(),
    }
    _atomic_json(state_path, state)

    evaluation_result_path = work_root / "evaluation-result.json"
    creation = verify_creation_run(
        creation_path,
        spec,
        expected_complete_sha256=creation_hash,
    )
    sealed_evaluation = None
    existing_evaluation = state.get("evaluation_run")
    expected_evaluation_hash = state.get("evaluation_complete_sha256")
    if existing_evaluation is not None or expected_evaluation_hash is not None:
        if not isinstance(existing_evaluation, str) or not isinstance(
            expected_evaluation_hash, str
        ):
            raise FullDocRecordError("pipeline evaluation anchor is incomplete")
        try:
            sealed_evaluation = verify_evaluation_run(
                Path(existing_evaluation),
                spec,
                creation,
                expected_complete_sha256=expected_evaluation_hash,
            )
        except (OSError, FullDocRecordError) as exc:
            raise FullDocRecordError("pipeline evaluation anchor failed verification") from exc
    if sealed_evaluation is None:
        sealed_evaluation = _recover_evaluation_result(
            evaluation_result_path,
            spec,
            creation,
        )
    if sealed_evaluation is not None:
        completed_state = {
            **state,
            "status": "COMPLETE",
            "evaluation_run": str(sealed_evaluation.root),
            "evaluation_complete_sha256": sealed_evaluation.complete_sha256,
            "metrics": sealed_evaluation.metrics,
            "updated_at": _timestamp(),
        }
        _atomic_json(state_path, completed_state)
        _emit({**completed_state, "status": "SUCCESS", "phase": "pipeline"})
        return 0
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "evaluate",
        "--creation-run",
        str(creation_path),
        "--creation-complete-sha256",
        creation_hash,
        "--auto-resume",
        "--reuse-sealed-result",
        "--result-path",
        str(evaluation_result_path),
        *_child_common(args),
    ]
    completed, result = _run_pipeline_child(
        command,
        result_path=evaluation_result_path,
        label="evaluation",
        wait_for_gpu=args.wait_for_gpu,
        poll_seconds=args.poll_seconds,
        state_path=state_path,
        state=state,
    )
    if completed.returncode != 0 or result.get("status") != "SUCCESS":
        _atomic_json(
            state_path,
            {**state, "status": "EVALUATION_FAILED", "updated_at": _timestamp(), "result": result},
        )
        return completed.returncode or 2
    sealed_evaluation = _recover_evaluation_result(
        evaluation_result_path,
        spec,
        creation,
    )
    if sealed_evaluation is None:
        _atomic_json(
            state_path,
            {
                **state,
                "status": "EVALUATION_FAILED",
                "updated_at": _timestamp(),
                "result": result,
                "reason": "evaluation child result failed sealed verification",
            },
        )
        return 2
    completed_state = {
        **state,
        "status": "COMPLETE",
        "evaluation_run": str(sealed_evaluation.root),
        "evaluation_complete_sha256": sealed_evaluation.complete_sha256,
        "metrics": sealed_evaluation.metrics,
        "updated_at": _timestamp(),
    }
    _atomic_json(state_path, completed_state)
    _emit({**completed_state, "status": "SUCCESS", "phase": "pipeline"})
    return 0


def _path(value: str) -> Path:
    return Path(value).expanduser()


def _common(parser: argparse.ArgumentParser, *, wait: bool = True) -> None:
    parser.add_argument("--vllm", type=_path)
    parser.add_argument("--hf-home", type=_path)
    parser.add_argument("--result-path", type=_path)
    parser.add_argument(
        "--runtime-profile",
        choices=_RUNTIME_PROFILES,
        default=DEEPSEEK_V4_FLASH_FORMAL_PROFILE,
    )
    if wait:
        parser.add_argument("--wait-for-gpu", action="store_true")
        parser.add_argument("--poll-seconds", type=float, default=30.0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    preflight = subparsers.add_parser("preflight")
    preflight.add_argument("--phase", choices=("creation", "evaluation"), default="creation")
    _common(preflight, wait=False)
    preflight.set_defaults(handler=_preflight)

    create = subparsers.add_parser("create")
    _common(create)
    create.add_argument("--runs-root", type=_path)
    create.add_argument("--resume-run", type=_path)
    create.add_argument("--auto-resume", action="store_true")
    create.add_argument("--reuse-sealed-result", action="store_true")
    create.add_argument("--execution-id")
    create.set_defaults(handler=_create)

    evaluate = subparsers.add_parser("evaluate")
    _common(evaluate)
    evaluate.add_argument("--creation-run", type=_path, required=True)
    evaluate.add_argument("--creation-complete-sha256", required=True)
    evaluate.add_argument("--runs-root", type=_path)
    evaluate.add_argument("--resume-run", type=_path)
    evaluate.add_argument("--auto-resume", action="store_true")
    evaluate.add_argument("--reuse-sealed-result", action="store_true")
    evaluate.set_defaults(handler=_evaluate)

    pipeline = subparsers.add_parser("pipeline")
    _common(pipeline)
    pipeline.add_argument("--state-path", type=_path)
    pipeline.set_defaults(handler=_pipeline)

    args = parser.parse_args()
    if hasattr(args, "poll_seconds") and args.poll_seconds <= 0:
        parser.error("--poll-seconds must be positive")
    try:
        return args.handler(args)
    except (FullDocInfrastructureError, FullDocRecordError, OSError) as exc:
        _emit(
            {
                "status": "INVALID",
                "phase": args.command,
                "reason": f"{type(exc).__name__}: {exc}",
            },
            result_path=getattr(args, "result_path", None),
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
