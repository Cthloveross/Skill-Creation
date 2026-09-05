"""Live Qwen entrypoint for the strict matched qualification experiment."""

from __future__ import annotations

import argparse
import json
import math
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

from .artifacts import sha256_file
from .file_injection_fixture import load_appworld_file_fixtures
from .file_injection_live import (
    DEFAULT_BASE_URL,
    DEFAULT_CONFIG_PATH,
    DEFAULT_SEED,
    SOURCE_TYPE,
    _LazyFileBackedCompileClientProvider,
    _LazyFileBackedDeploymentClientProvider,
    _load_live_config,
    _require_effective_config_match,
    _verified_source_evidence,
)
from .fixtures import SyntheticInjectionProfile
from .paired_qualification_runner import (
    PairedQualificationResult,
    run_paired_qualification_compile,
)
from .strict_skill_deployment_runner import (
    StrictSkillDeploymentResult,
    run_strict_skill_deployment,
)

QUALIFICATION_CONFIG_PATH = (
    "experiments/appworld/preliminary/configs/strict-paired-qualification.yaml"
)
PAIRED_COMPILE_MODE = "file_backed_paired_qualification_compile"
STRICT_DEPLOYMENT_MODE = "file_backed_strict_skill_deployment"
_ARMS = frozenset({"benign", "poison"})
_TASK_KINDS = frozenset({"positive", "negative"})


class _PairedCompileProvider:
    """Add an explicit arm binding to the existing fresh-client provider."""

    def __init__(self, delegate: _LazyFileBackedCompileClientProvider) -> None:
        self._delegate = delegate

    @property
    def generator(self) -> Mapping[str, Any]:
        return {
            **dict(self._delegate.generator),
            "qualification_phase": "paired_compile",
            "fresh_context_per_profile_arm": True,
        }

    def acquisition(
        self,
        *,
        profile: SyntheticInjectionProfile,
        arm: str,
    ) -> Any:
        _require_arm(arm)
        return self._delegate.acquisition(profile=profile)

    def compiler(
        self,
        *,
        profile: SyntheticInjectionProfile,
        arm: str,
    ) -> Any:
        _require_arm(arm)
        return self._delegate.compiler(profile=profile)


class _StrictDeploymentProvider:
    """Add arm binding while retaining one fresh HTTP client per episode."""

    def __init__(self, delegate: _LazyFileBackedDeploymentClientProvider) -> None:
        self._delegate = delegate

    @property
    def generator(self) -> Mapping[str, Any]:
        return {
            **dict(self._delegate.generator),
            "qualification_phase": "strict_skill_only_deployment",
            "fresh_context_per_profile_arm_task": True,
        }

    def episode(
        self,
        *,
        profile: SyntheticInjectionProfile,
        arm: str,
        task_kind: str,
    ) -> Any:
        _require_arm(arm)
        if task_kind not in _TASK_KINDS:
            raise ValueError("task_kind must be positive or negative")
        return self._delegate.episode(profile=profile, task_kind=task_kind)


def run_live_paired_compile(
    *,
    appworld_root: str | Path,
    bundle_directory: str | Path,
    output_directory: str | Path,
    base_url: str = DEFAULT_BASE_URL,
    project_root: str | Path | None = None,
    config_path: str | Path = DEFAULT_CONFIG_PATH,
    qualification_config_path: str | Path = QUALIFICATION_CONFIG_PATH,
    seed: int = DEFAULT_SEED,
) -> PairedQualificationResult:
    root = Path(project_root or Path.cwd()).resolve()
    config, experiment, config_sha256 = _load_live_config(root, config_path)
    qualification = _load_qualification_contract(
        root,
        qualification_config_path,
        base_config=config,
        base_config_sha256=config_sha256,
    )
    loaded = load_appworld_file_fixtures(appworld_root, bundle_directory)
    source_evidence = _qualified_source_evidence(
        _verified_source_evidence(Path(appworld_root), loaded),
        qualification,
    )
    effective_config = _require_effective_config_match(
        config,
        config_sha256,
        experiment,
        source_evidence,
    )
    provider = _PairedCompileProvider(
        _LazyFileBackedCompileClientProvider(
            base_url,
            effective_config=effective_config,
        )
    )
    return run_paired_qualification_compile(
        output_directory,
        client_provider=provider,
        config_path=config,
        project_root=root,
        seed=seed,
        fixtures=loaded.fixtures,
        mode=PAIRED_COMPILE_MODE,
        source_type=SOURCE_TYPE,
        source_evidence=source_evidence,
    )


def run_live_strict_deployment(
    *,
    appworld_root: str | Path,
    bundle_directory: str | Path,
    compile_directory: str | Path,
    compile_complete_sha256: str,
    output_directory: str | Path,
    base_url: str = DEFAULT_BASE_URL,
    project_root: str | Path | None = None,
    config_path: str | Path = DEFAULT_CONFIG_PATH,
    qualification_config_path: str | Path = QUALIFICATION_CONFIG_PATH,
    seed: int = DEFAULT_SEED,
) -> StrictSkillDeploymentResult:
    root = Path(project_root or Path.cwd()).resolve()
    config, experiment, config_sha256 = _load_live_config(root, config_path)
    qualification = _load_qualification_contract(
        root,
        qualification_config_path,
        base_config=config,
        base_config_sha256=config_sha256,
    )
    loaded = load_appworld_file_fixtures(appworld_root, bundle_directory)
    source_evidence = _qualified_source_evidence(
        _verified_source_evidence(Path(appworld_root), loaded),
        qualification,
    )
    effective_config = _require_effective_config_match(
        config,
        config_sha256,
        experiment,
        source_evidence,
    )
    system_prompt_path = _strict_prompt_path(root, qualification["value"])
    system_prompt = system_prompt_path.read_text(encoding="utf-8")
    provider = _StrictDeploymentProvider(
        _LazyFileBackedDeploymentClientProvider(
            base_url,
            effective_config=effective_config,
        )
    )
    return run_strict_skill_deployment(
        compile_directory,
        output_directory,
        expected_compile_complete_sha256=compile_complete_sha256,
        client_provider=provider,
        system_prompt=system_prompt,
        config_path=config,
        project_root=root,
        seed=seed,
        fixtures=loaded.fixtures,
        mode=STRICT_DEPLOYMENT_MODE,
        source_type=SOURCE_TYPE,
        source_evidence=source_evidence,
    )


def _require_arm(arm: str) -> None:
    if arm not in _ARMS:
        raise ValueError("arm must be benign or poison")


def _load_qualification_contract(
    project_root: Path,
    path: str | Path,
    *,
    base_config: Path,
    base_config_sha256: str,
) -> dict[str, Any]:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = project_root / candidate
    if candidate.is_symlink() or not candidate.is_file():
        raise RuntimeError("qualification contract is unavailable")
    payload = yaml.safe_load(candidate.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise RuntimeError("qualification contract must be a YAML mapping")
    value = json.loads(json.dumps(payload, ensure_ascii=False, allow_nan=False, sort_keys=True))
    if value.get("schema_version") != "r2sp.strict-paired-qualification.v1":
        raise RuntimeError("qualification contract schema differs")
    base = value.get("base_contract")
    contamination = value.get("contamination")
    compile_contract = value.get("compile")
    deployment = value.get("deployment")
    evaluation = value.get("evaluation")
    if not all(
        isinstance(section, Mapping)
        for section in (base, contamination, compile_contract, deployment, evaluation)
    ):
        raise RuntimeError("qualification contract sections are incomplete")
    assert isinstance(base, Mapping)
    assert isinstance(contamination, Mapping)
    assert isinstance(compile_contract, Mapping)
    assert isinstance(deployment, Mapping)
    assert isinstance(evaluation, Mapping)
    configured_base = Path(str(base.get("path", "")))
    if not configured_base.is_absolute():
        configured_base = project_root / configured_base
    poison = contamination.get("arms", {}).get("poison", {})
    benign = contamination.get("arms", {}).get("benign", {})
    completion = compile_contract.get("acquisition_completion", {})
    exposure_gate = compile_contract.get("poison_exposure_gate", {})
    if not isinstance(completion, Mapping) or not isinstance(exposure_gate, Mapping):
        raise RuntimeError("qualification contract differs from the frozen protocol")
    if (
        configured_base.resolve() != base_config.resolve()
        or base.get("sha256") != base_config_sha256
        or compile_contract.get("acquisition_calls") != 4
        or compile_contract.get("compiler_calls") != 4
        or compile_contract.get("retry_count") != 0
        or compile_contract.get("task_success_required") is not False
        or compile_contract.get("acquisition_mode") != "retrieval_only"
        or compile_contract.get("acquisition_max_turns") != 20
        or compile_contract.get("acquisition_tools")
        != ["search_docs", "select_docs", "read_doc", "finish"]
        or compile_contract.get("ordinary_execute_calls_required") != 0
        or completion.get("failure_must_be_null") is not True
        or completion.get("accepted_finish_statuses") != ["fail"]
        or completion.get("stop_immediately_if_incomplete") is not True
        or exposure_gate.get("stop_immediately_on_failure") is not True
        or deployment.get("episode_count") != 8
        or deployment.get("retry_count") != 0
        or deployment.get("resource_pool_attached") is not False
        or deployment.get("tools") != ["execute", "finish"]
        or benign.get("modified_resources") != 0
        or benign.get("rho") != 0.0
        or poison.get("modified_resources") != 1
        or not math.isclose(float(poison.get("rho", -1)), 1 / 447, rel_tol=0, abs_tol=0)
        or evaluation.get("upstream_failure_value") != 0
        or evaluation.get("benign_attack_specific_components_required") != 0
        or evaluation.get("ordinary_task_utility_reported_separately") is not True
    ):
        raise RuntimeError("qualification contract differs from the frozen protocol")
    return {
        "path": candidate.relative_to(project_root).as_posix(),
        "sha256": sha256_file(candidate),
        "value": value,
    }


def _strict_prompt_path(project_root: Path, qualification: Mapping[str, Any]) -> Path:
    deployment = qualification.get("deployment")
    if not isinstance(deployment, Mapping):
        raise RuntimeError("qualification deployment contract is unavailable")
    relative = deployment.get("system_prompt")
    if not isinstance(relative, str) or not relative:
        raise RuntimeError("strict deployment prompt is not configured")
    path = (project_root / relative).resolve()
    try:
        path.relative_to(project_root)
    except ValueError as exc:
        raise RuntimeError("strict deployment prompt escapes the project") from exc
    if path.is_symlink() or not path.is_file():
        raise RuntimeError("strict deployment prompt is unavailable")
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise RuntimeError("strict deployment prompt is empty")
    return path


def _qualified_source_evidence(
    source_evidence: Mapping[str, Any],
    qualification: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        **dict(source_evidence),
        "qualification_contract": dict(qualification),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("compile", "deploy"):
        command = subparsers.add_parser(name)
        command.add_argument("--appworld-root", required=True)
        command.add_argument("--bundle-directory", required=True)
        command.add_argument("--output", required=True)
        command.add_argument("--base-url", default=DEFAULT_BASE_URL)
        command.add_argument("--project-root", default=None)
        command.add_argument("--config", default=DEFAULT_CONFIG_PATH)
        command.add_argument(
            "--qualification-config",
            default=QUALIFICATION_CONFIG_PATH,
        )
        command.add_argument("--seed", type=int, default=DEFAULT_SEED)
        if name == "deploy":
            command.add_argument("--compile-directory", required=True)
            command.add_argument("--compile-complete-sha256", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    common = {
        "appworld_root": args.appworld_root,
        "bundle_directory": args.bundle_directory,
        "output_directory": args.output,
        "base_url": args.base_url,
        "project_root": args.project_root,
        "config_path": args.config,
        "qualification_config_path": args.qualification_config,
        "seed": args.seed,
    }
    if args.command == "compile":
        result = run_live_paired_compile(**common)
    else:
        result = run_live_strict_deployment(
            **common,
            compile_directory=args.compile_directory,
            compile_complete_sha256=args.compile_complete_sha256,
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
    "PAIRED_COMPILE_MODE",
    "QUALIFICATION_CONFIG_PATH",
    "STRICT_DEPLOYMENT_MODE",
    "main",
    "run_live_paired_compile",
    "run_live_strict_deployment",
]
