"""Command-line entry points for the R2SP feasibility pilot."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .artifacts import ArtifactStore, sha256_file
from .cases import build_overlay_attestation, build_schedule, load_frozen_cases
from .config import ConfigValidationError, load_config
from .hashing import is_sha256
from .preflight import format_preflight, run_preflight
from .resource_pool import load_standard_api_docs, write_public_manifest
from .runner import RunnerError, run_synthetic_smoke


class CliError(RuntimeError):
    """An expected command-line failure with a concise user-facing message."""


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="r2sp",
        description="R2SP AppWorld x Qwen3.8 feasibility-pilot runner",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser(
        "validate-config", help="validate the frozen v0.3 experiment contract"
    )
    validate.add_argument("--config", type=Path, required=True)
    validate.add_argument(
        "--research-ready",
        action="store_true",
        help="also require runner_ready and a non-placeholder data digest",
    )
    validate.set_defaults(handler=_validate_config)

    preflight = subparsers.add_parser(
        "preflight", help="check environment and frozen inputs without running tasks"
    )
    preflight.add_argument("--config", type=Path, required=True)
    preflight.add_argument("--runtime-config", type=Path)
    preflight.add_argument("--project-root", type=Path, default=Path.cwd())
    preflight.add_argument("--appworld-root", type=Path)
    preflight.add_argument("--clean-manifest", type=Path)
    preflight.add_argument("--cases", type=Path)
    preflight.add_argument("--overlays", type=Path)
    preflight.add_argument("--model-url")
    preflight.add_argument(
        "--model-api-key-env",
        help="environment variable containing the model-service API key",
    )
    preflight.add_argument(
        "--dependency-lockfile",
        type=Path,
        action="append",
        dest="dependency_lockfiles",
        help="repeat exactly twice to override the default AppWorld/model lock paths",
    )
    preflight.add_argument(
        "--research-ready",
        action="store_true",
        help="make every real-run prerequisite a hard requirement",
    )
    preflight.add_argument("--json", action="store_true", dest="as_json")
    preflight.set_defaults(handler=_preflight)

    manifest = subparsers.add_parser(
        "build-manifest", help="build the body-free clean resource manifest"
    )
    manifest.add_argument("--source", type=Path, required=True)
    manifest.add_argument("--output", type=Path, required=True)
    manifest.add_argument("--expected-count", type=int, default=457)
    manifest.set_defaults(handler=_build_manifest)

    freeze = subparsers.add_parser(
        "freeze-pilot", help="validate private cases and emit a non-sensitive build schedule"
    )
    freeze.add_argument("--cases", type=Path, required=True)
    freeze.add_argument("--output", type=Path, required=True)
    freeze.add_argument(
        "--overlay-attestation",
        type=Path,
        help="hash-only attestation path (default: next to the public schedule)",
    )
    freeze.add_argument(
        "--instrumentation",
        action="store_true",
        help="allow fewer than 16 cases and missing pinned token counts",
    )
    freeze.set_defaults(handler=_freeze_pilot)

    smoke = subparsers.add_parser(
        "smoke", help="run the deterministic non-scientific end-to-end fixture"
    )
    smoke.add_argument("--output", type=Path, required=True)
    smoke.add_argument("--config", type=Path, default=Path("configs/experiment_plan.yaml"))
    smoke.add_argument("--project-root", type=Path, default=Path.cwd())
    smoke.set_defaults(handler=_smoke)

    model_smoke = subparsers.add_parser(
        "run-model-smoke",
        help="run the non-research synthetic full chain with a loopback model service",
    )
    model_smoke.add_argument("--output", type=Path, required=True)
    model_smoke.add_argument("--config", type=Path, default=Path("configs/experiment_plan.yaml"))
    model_smoke.add_argument("--project-root", type=Path, default=Path.cwd())
    model_smoke.add_argument("--base-url", default="http://127.0.0.1:18000/v1")
    model_smoke.add_argument("--model-id", default="Qwen/Qwen3.8-27B")
    model_smoke.add_argument(
        "--revision",
        default="1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0",
    )
    model_smoke.add_argument("--api-key-env", default="R2SP_MODEL_API_KEY")
    model_smoke.add_argument("--timeout-seconds", type=float, default=300.0)
    model_smoke.add_argument("--max-model-len", type=int, default=65536)
    model_smoke.add_argument("--max-agent-turns", type=int, default=16)
    model_smoke.set_defaults(handler=_run_model_smoke)

    pilot = subparsers.add_parser(
        "run-pilot", help="run the real 16-case pilot after a strict research preflight"
    )
    pilot.add_argument("--config", type=Path, required=True)
    pilot.add_argument("--runtime-config", type=Path, required=True)
    pilot.add_argument("--project-root", type=Path, default=Path.cwd())
    pilot.set_defaults(handler=_run_pilot)

    gateway = subparsers.add_parser(
        "serve-model-gateway",
        help="serve a loopback proxy that adds declared R2SP metadata to vLLM",
    )
    gateway.add_argument("--config", type=Path, required=True)
    gateway.add_argument("--backend-url", default="http://127.0.0.1:18001")
    gateway.add_argument("--host", default="127.0.0.1")
    gateway.add_argument("--port", type=int, default=18000)
    gateway.add_argument("--timeout-seconds", type=float, default=300.0)
    gateway.set_defaults(handler=_serve_model_gateway)

    probe = subparsers.add_parser(
        "probe-model-service",
        help="run a non-research tokenizer/parser/agent/compiler service probe",
    )
    probe.add_argument("--base-url", default="http://127.0.0.1:18000/v1")
    probe.add_argument("--model-id", default="Qwen/Qwen3.8-27B")
    probe.add_argument(
        "--revision",
        default="1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0",
    )
    probe.add_argument("--api-key-env", default="R2SP_MODEL_API_KEY")
    probe.add_argument("--timeout-seconds", type=float, default=300.0)
    probe.add_argument("--max-model-len", type=int, default=16384)
    probe.set_defaults(handler=_probe_model_service)

    report = subparsers.add_parser(
        "report", help="verify and print an immutable completed-run report"
    )
    report.add_argument("--run-directory", type=Path, required=True)
    report.add_argument(
        "--expected-complete-sha256",
        required=True,
        help="external complete.json digest returned by smoke or run-pilot",
    )
    report.add_argument("--format", choices=("json", "markdown", "csv"), default="json")
    report.set_defaults(handler=_report)
    return parser


def _preflight_arguments(args: argparse.Namespace) -> dict[str, Any]:
    runtime = None
    if args.runtime_config is not None:
        # A runtime file is an execution contract, even when used only for
        # preflight. Parse it through the same fail-closed validator as the
        # real runner instead of extracting a few convenient YAML fields.
        from .research_runner import load_runtime_config

        runtime = load_runtime_config(
            args.runtime_config,
            project_root=args.project_root,
        )

    lockfiles = args.dependency_lockfiles
    if lockfiles is None and runtime is not None:
        lockfiles = runtime.dependency_lockfiles
    if lockfiles is not None and (
        not isinstance(lockfiles, (list, tuple))
        or len(lockfiles) != 2
        or any(not isinstance(path, (str, Path)) for path in lockfiles)
    ):
        raise CliError("dependency_lockfiles must contain exactly two paths")
    return {
        "project_root": args.project_root,
        "appworld_root": args.appworld_root
        if args.appworld_root is not None
        else runtime.appworld_root
        if runtime is not None
        else None,
        "clean_manifest": args.clean_manifest
        if args.clean_manifest is not None
        else runtime.clean_manifest
        if runtime is not None
        else None,
        "cases_path": args.cases
        if args.cases is not None
        else runtime.cases_path
        if runtime is not None
        else None,
        "overlays_path": args.overlays
        if args.overlays is not None
        else runtime.overlays_path
        if runtime is not None
        else None,
        "model_url": args.model_url
        if args.model_url is not None
        else runtime.model_base_url
        if runtime is not None
        else None,
        "model_api_key_env": args.model_api_key_env
        if args.model_api_key_env is not None
        else runtime.api_key_env
        if runtime is not None
        else None,
        "dependency_lockfiles": lockfiles,
        "require_research_ready": args.research_ready,
    }


def _validate_config(args: argparse.Namespace) -> int:
    config = load_config(args.config, require_research_ready=args.research_ready)
    print(json.dumps(config.validation.to_dict(), sort_keys=True))
    return 0


def _preflight(args: argparse.Namespace) -> int:
    report = run_preflight(args.config, **_preflight_arguments(args))
    if args.as_json:
        print(json.dumps(report.to_dict(), sort_keys=True))
    else:
        print(format_preflight(report))
    return 0 if report.ready else 1


def _build_manifest(args: argparse.Namespace) -> int:
    pool = load_standard_api_docs(args.source, expected_count=args.expected_count)
    write_public_manifest(pool, args.output)
    print(
        json.dumps(
            {
                "manifest": str(args.output.resolve()),
                "manifest_hash": pool.manifest.manifest_hash,
                "resource_count": len(pool),
            },
            sort_keys=True,
        )
    )
    return 0


def _freeze_pilot(args: argparse.Namespace) -> int:
    bundle = load_frozen_cases(args.cases, research_mode=not args.instrumentation)
    schedule = build_schedule(bundle)
    attestation = build_overlay_attestation(bundle)
    schedule_path = args.output.resolve()
    attestation_path = (
        args.overlay_attestation.resolve()
        if args.overlay_attestation is not None
        else schedule_path.with_name("overlay-attestation.json")
    )
    if schedule_path.parent != attestation_path.parent:
        ArtifactStore(schedule_path.parent).write_json(
            schedule_path.name, schedule.to_public_dict()
        )
        ArtifactStore(attestation_path.parent).write_json(
            attestation_path.name, attestation.to_dict()
        )
    else:
        store = ArtifactStore(schedule_path.parent)
        store.write_json(schedule_path.name, schedule.to_public_dict())
        store.write_json(attestation_path.name, attestation.to_dict())
    print(
        json.dumps(
            {
                "attestation": str(attestation_path),
                "attestation_hash": sha256_file(attestation_path),
                "case_count": len(bundle.cases),
                "entry_count": len(schedule.entries),
                "schedule": str(schedule_path),
                "schedule_hash": sha256_file(schedule_path),
            },
            sort_keys=True,
        )
    )
    return 0


def _smoke(args: argparse.Namespace) -> int:
    result = run_synthetic_smoke(
        args.output,
        config_path=args.config,
        project_root=args.project_root,
    )
    print(
        json.dumps(
            {
                "cached": result.cached,
                "complete_hash": result.complete_hash,
                "decision": result.summary["decision"],
                "output_directory": str(result.output_directory),
                "research_eligible": result.summary["research_eligible"],
            },
            sort_keys=True,
        )
    )
    return 0


def _run_model_smoke(args: argparse.Namespace) -> int:
    from .runner import run_model_backed_synthetic

    api_key = os.environ.get(args.api_key_env) if args.api_key_env else None
    result = run_model_backed_synthetic(
        args.output,
        base_url=args.base_url,
        model_id=args.model_id,
        revision=args.revision,
        api_key=api_key,
        timeout_seconds=args.timeout_seconds,
        max_model_len=args.max_model_len,
        max_agent_turns=args.max_agent_turns,
        config_path=args.config,
        project_root=args.project_root,
    )
    print(
        json.dumps(
            {
                "cached": result.cached,
                "complete_hash": result.complete_hash,
                "decision": result.summary["decision"],
                "mode": result.summary["mode"],
                "output_directory": str(result.output_directory),
                "research_eligible": result.summary["research_eligible"],
            },
            sort_keys=True,
        )
    )
    return 0


def _run_pilot(args: argparse.Namespace) -> int:
    # Kept as a lazy import so core validation and smoke runs never import the
    # protected AppWorld integration path.
    from .research_runner import run_research_pilot

    result = run_research_pilot(
        config_path=args.config,
        runtime_config_path=args.runtime_config,
        project_root=args.project_root,
    )
    print(json.dumps(result.to_dict(), sort_keys=True))
    return 0


def _serve_model_gateway(args: argparse.Namespace) -> int:
    from .model_gateway import serve_model_gateway

    config = load_config(args.config)
    metadata = {
        "revision": str(config.model.revision),
        "dtype": str(config.model.dtype),
        "generation": config.model.generation.to_dict(),
        "runtime": {
            "max_model_len": config.model.max_model_len,
            "prefix_caching": config.model.prefix_caching,
            "server_sessions": config.model.server_sessions,
            **config.model.serving.to_dict(),
        },
        "vllm_version": str(config.model.vllm_version),
        "gpu": str(config.model.gpu),
        "evidence_scope": "caller_declared_not_weight_or_process_proof",
    }
    try:
        serve_model_gateway(
            backend_url=args.backend_url,
            model_id=str(config.model.id),
            metadata=metadata,
            host=args.host,
            port=args.port,
            timeout_seconds=args.timeout_seconds,
        )
    except KeyboardInterrupt:
        return 0
    return 0


def _probe_model_service(args: argparse.Namespace) -> int:
    from .model_probe import run_model_service_probe

    api_key = os.environ.get(args.api_key_env) if args.api_key_env else None
    report = run_model_service_probe(
        base_url=args.base_url,
        model_id=args.model_id,
        revision=args.revision,
        api_key=api_key,
        timeout_seconds=args.timeout_seconds,
        max_model_len=args.max_model_len,
    )
    print(json.dumps(report.to_dict(), sort_keys=True))
    return 0 if report.ready else 1


def _report(args: argparse.Namespace) -> int:
    root = args.run_directory.resolve()
    run_record_path = root / "run.json"
    completion_path = root / "complete.json"
    if not run_record_path.is_file() or run_record_path.is_symlink():
        raise CliError(f"run record is missing: {run_record_path}")
    if not completion_path.is_file() or completion_path.is_symlink():
        raise CliError(f"run is incomplete: {completion_path} is missing")
    expected_complete = args.expected_complete_sha256
    if not is_sha256(expected_complete):
        raise CliError("--expected-complete-sha256 must be a lowercase SHA-256 digest")
    if sha256_file(completion_path) != expected_complete:
        raise CliError("complete.json does not match the external expected digest")
    try:
        run_record = json.loads(run_record_path.read_text(encoding="utf-8"))
        completion = json.loads(completion_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CliError(f"invalid run or completion record: {exc}") from exc
    run_mode = run_record.get("mode") if isinstance(run_record, dict) else None
    if run_mode not in {
        "synthetic_smoke",
        "synthetic_model_smoke",
        "injected_test",
        "research",
    }:
        raise CliError("run record has an invalid mode")
    if completion.get("status") != "completed":
        raise CliError("run completion record does not have completed status")
    completion_mode = completion.get("mode")
    if completion_mode is not None and completion_mode != run_mode:
        raise CliError("run and completion modes do not match")
    suffix, hash_key = {
        "json": ("summary.json", "summary_hash"),
        "markdown": ("summary.md", "markdown_hash"),
        "csv": ("funnel.csv", "csv_hash"),
    }[args.format]
    report_path = root / "reports" / suffix
    if not report_path.is_file() or report_path.is_symlink():
        raise CliError(f"report is missing: {report_path}")
    manifest_hash = completion.get("artifact_manifest_hash")
    if run_mode in {"synthetic_model_smoke", "injected_test", "research"} and manifest_hash is None:
        raise CliError(f"{run_mode} output requires a complete artifact manifest")
    if manifest_hash is not None:
        manifest_path = root / "artifacts-manifest.json"
        if (
            not isinstance(manifest_hash, str)
            or not manifest_path.is_file()
            or manifest_path.is_symlink()
            or sha256_file(manifest_path) != manifest_hash
        ):
            raise CliError("artifact manifest digest does not match complete.json")
        # Keep protected AppWorld integration imports out of unrelated commands.
        from .research_runner import ResearchRunnerError, _verify_artifact_manifest

        try:
            _verify_artifact_manifest(root, manifest_path)
        except ResearchRunnerError as exc:
            raise CliError("completed run artifact manifest verification failed") from exc
    else:
        expected_hash = completion.get(hash_key)
        if not isinstance(expected_hash, str) or sha256_file(report_path) != expected_hash:
            raise CliError(f"{suffix} digest does not match complete.json")
    try:
        report = report_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise CliError(f"cannot read report: {report_path}") from exc
    sys.stdout.write(report)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except (
        CliError,
        ConfigValidationError,
        FileNotFoundError,
        RunnerError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


__all__ = ["CliError", "main"]
