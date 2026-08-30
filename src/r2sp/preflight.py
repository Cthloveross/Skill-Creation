"""Evidence-backed environment checks for the gated AppWorld/Qwen pilot."""

from __future__ import annotations

import importlib.metadata
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from .cases import (
    CaseBundleError,
    FrozenCaseBundle,
    build_overlay_attestation,
    load_frozen_cases,
    load_overlay_attestation,
)
from .config import ConfigValidationError, load_config
from .hashing import canonical_json_sha256, is_sha256, sha256_file
from .http_transport import no_redirect_urlopen
from .resource_pool import load_public_manifest, load_standard_api_docs

Gate = Literal["instrumentation", "research", "advisory"]
Mode = Literal["instrumentation", "research"]

_PROMPT_PATHS = (
    Path("experiments/pilot/prompts/agent_system.md"),
    Path("experiments/pilot/prompts/compiler_system.md"),
    Path("experiments/pilot/prompts/neutral_skill.md"),
)
_DEFAULT_LOCKFILES = (
    Path("requirements/appworld.lock"),
    Path("requirements/model-service.lock"),
)
_PLACEHOLDER_MARKERS = (
    "fill_after",
    "placeholder",
    "replace_me",
    "replace-me",
    "todo",
    "tbd",
    "not locked",
)


@dataclass(frozen=True)
class PreflightCheck:
    name: str
    ok: bool
    required: bool
    detail: str
    gate: Gate = "research"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PreflightReport:
    checks: tuple[PreflightCheck, ...]
    mode: Mode = "research"

    @property
    def instrumentation_ready(self) -> bool:
        return all(check.ok for check in self.checks if check.gate == "instrumentation")

    @property
    def research_ready(self) -> bool:
        return self.instrumentation_ready and all(
            check.ok for check in self.checks if check.gate == "research"
        )

    @property
    def ready(self) -> bool:
        return self.research_ready if self.mode == "research" else self.instrumentation_ready

    @property
    def failed_required(self) -> tuple[PreflightCheck, ...]:
        return tuple(check for check in self.checks if check.required and not check.ok)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "ready": self.ready,
            "instrumentation_ready": self.instrumentation_ready,
            "research_ready": self.research_ready,
            "checks": [check.to_dict() for check in self.checks],
        }


def _required(gate: Gate, mode: Mode) -> bool:
    return gate == "instrumentation" or (gate == "research" and mode == "research")


def _check(name: str, ok: bool, detail: str, gate: Gate, mode: Mode) -> PreflightCheck:
    return PreflightCheck(name, bool(ok), _required(gate, mode), detail, gate)


def _package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _package_git_revision(name: str) -> tuple[str | None, str]:
    """Read an installed VCS commit from the standard PEP 610 provenance record."""

    try:
        distribution = importlib.metadata.distribution(name)
        raw = distribution.read_text("direct_url.json")
    except importlib.metadata.PackageNotFoundError:
        return None, f"distribution {name!r} is not installed"
    except (OSError, UnicodeError) as exc:
        return None, f"cannot read {name!r} distribution provenance: {exc}"
    if raw is None:
        return None, "installed distribution has no PEP 610 direct_url.json provenance"
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, f"invalid PEP 610 direct_url.json: {exc.msg}"
    vcs = payload.get("vcs_info") if isinstance(payload, Mapping) else None
    commit = vcs.get("commit_id") if isinstance(vcs, Mapping) else None
    if not isinstance(commit, str) or re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        return None, "PEP 610 provenance does not contain a canonical 40-character commit_id"
    return commit, f"PEP 610 commit_id={commit}"


def _python_version_ok() -> bool:
    return sys.version_info >= (3, 11)


def _gpu_rows() -> tuple[list[tuple[str, int]], str | None]:
    command = [
        "nvidia-smi",
        "--query-gpu=name,memory.total",
        "--format=csv,noheader,nounits",
    ]
    try:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.SubprocessError) as exc:
        return [], str(exc)

    rows: list[tuple[str, int]] = []
    for line in completed.stdout.splitlines():
        if not line.strip():
            continue
        try:
            name, memory = line.rsplit(",", 1)
            rows.append((name.strip(), int(memory.strip())))
        except (ValueError, TypeError):
            return [], f"unparseable nvidia-smi row: {line!r}"
    return rows, None


def _models_endpoint(url: str) -> str:
    endpoint = url.rstrip("/")
    if not endpoint.endswith("/v1"):
        endpoint += "/v1"
    return endpoint + "/models"


def _fetch_model_record(
    url: str,
    expected_model: str,
    *,
    api_key: str | None = None,
) -> tuple[Mapping[str, Any] | None, str]:
    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = "Bearer " + api_key
    request = urllib.request.Request(_models_endpoint(url), headers=headers, method="GET")
    try:
        with no_redirect_urlopen(request, timeout=3) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, ValueError, json.JSONDecodeError) as exc:
        return None, f"model service unavailable: {exc}"
    if not isinstance(payload, Mapping) or not isinstance(payload.get("data"), list):
        return None, "model service /models payload is not an OpenAI-compatible object"

    records = [item for item in payload["data"] if isinstance(item, Mapping)]
    for item in records:
        if item.get("id") != expected_model:
            continue
        merged: dict[str, Any] = dict(item)
        for key in ("metadata", "r2sp_metadata"):
            metadata = item.get(key)
            if isinstance(metadata, Mapping):
                merged.update(metadata)
        top_level = payload.get("r2sp_metadata")
        if isinstance(top_level, Mapping):
            model_metadata = top_level.get(expected_model, top_level)
            if isinstance(model_metadata, Mapping):
                merged.update(model_metadata)
        merged["id"] = item["id"]
        return merged, f"reachable with model {expected_model}"
    returned = sorted(str(item["id"]) for item in records if isinstance(item.get("id"), str))
    return None, f"expected model {expected_model!r}; service returned {returned!r}"


def _model_url_is_remote(url: str) -> bool:
    hostname = (urllib.parse.urlparse(url).hostname or "").casefold()
    return hostname not in {"localhost", "127.0.0.1", "::1"}


def _metadata_value(metadata: Mapping[str, Any], *paths: tuple[str, ...]) -> Any:
    for path in paths:
        current: Any = metadata
        for component in path:
            if not isinstance(current, Mapping) or component not in current:
                break
            current = current[component]
        else:
            return current
    return None


def _mapping_matches(actual: Any, expected: Mapping[str, Any]) -> tuple[bool, str]:
    if not isinstance(actual, Mapping):
        return False, "missing mapping"
    mismatches = {
        key: {"expected": expected_value, "actual": actual.get(key)}
        for key, expected_value in expected.items()
        if actual.get(key) != expected_value
    }
    return (
        not mismatches,
        "matched" if not mismatches else json.dumps(mismatches, sort_keys=True),
    )


def _safe_path(path: str | Path | None, *, kind: str) -> tuple[Path | None, str]:
    if path is None:
        return None, "path not configured"
    candidate = Path(path)
    exists = candidate.is_dir() if kind == "directory" else candidate.is_file()
    if not exists:
        return None, f"missing {kind}: {candidate}"
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        return None, f"cannot resolve {candidate}: {exc}"
    return resolved, str(resolved)


def _overlaps_repository(path: Path, root: Path) -> bool:
    """Return whether a protected path is inside or contains the repository."""

    return path.is_relative_to(root) or root.is_relative_to(path)


def _artifact_hash(path: Path) -> tuple[str | None, str]:
    try:
        digest = sha256_file(path)
    except OSError as exc:
        return None, f"cannot hash {path}: {exc}"
    if not is_sha256(digest) or digest == "0" * 64:
        return None, f"invalid SHA-256 result for {path}"
    return digest, f"path={path}; sha256={digest}"


def _hash_group(root: Path, paths: Sequence[Path]) -> tuple[bool, str]:
    inventory: list[dict[str, str]] = []
    for relative in paths:
        path = root / relative
        if not path.is_file() or path.is_symlink():
            return False, f"missing regular non-symlink file: {path}"
        try:
            if path.stat().st_size == 0:
                return False, f"empty file: {path}"
            digest = sha256_file(path)
        except OSError as exc:
            return False, f"cannot read/hash {path}: {exc}"
        inventory.append({"path": relative.as_posix(), "sha256": digest})
    aggregate = canonical_json_sha256(inventory)
    return True, f"files={len(inventory)}; aggregate_sha256={aggregate}"


def _validate_code_bundle(root: Path) -> tuple[bool, str]:
    source = root / "src" / "r2sp"
    paths = [Path("pyproject.toml")]
    if source.is_dir():
        paths.extend(path.relative_to(root) for path in sorted(source.rglob("*.py")))
    if len(paths) == 1:
        return False, f"no Python source files under {source}"
    return _hash_group(root, paths)


def _logical_requirements(text: str) -> list[str]:
    logical: list[str] = []
    pending = ""
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        pending = f"{pending} {stripped}".strip()
        if pending.endswith("\\"):
            pending = pending[:-1].strip()
            continue
        logical.append(pending)
        pending = ""
    if pending:
        logical.append(pending)
    return logical


def _validate_lockfile(
    path: Path,
    package: str,
    version: str,
    *,
    vcs_revision: str | None = None,
) -> tuple[bool, str]:
    if not path.is_file() or path.is_symlink():
        return False, f"missing regular non-symlink lockfile: {path}"
    try:
        text = path.read_text(encoding="utf-8")
        digest = sha256_file(path)
    except (OSError, UnicodeError) as exc:
        return False, f"cannot read/hash {path}: {exc}"
    lowered = text.casefold()
    marker = next((item for item in _PLACEHOLDER_MARKERS if item in lowered), None)
    if not text.strip() or marker is not None:
        return False, f"empty or placeholder lockfile: {path} ({marker or 'empty'})"

    requirements = [item for item in _logical_requirements(text) if not item.startswith("--")]
    if len(requirements) < 2:
        return False, f"lockfile does not contain a transitive package set: {path}"

    vcs_pattern = None
    if vcs_revision is not None:
        vcs_pattern = re.compile(
            rf"^{re.escape(package)}\s*@\s*"
            rf"git\+https://github\.com/StonyBrookNLP/appworld\.git@"
            rf"{re.escape(vcs_revision)}(?:\s|$)",
            re.I,
        )
    vcs_direct = [item for item in requirements if vcs_pattern and vcs_pattern.search(item)]

    def is_exact_hash_pinned(item: str) -> bool:
        hashes = re.findall(r"--hash=sha256:([^\s\\]+)", item, flags=re.I)
        return (
            "==" in item
            and bool(hashes)
            and all(
                re.fullmatch(r"[0-9a-f]{64}", digest, flags=re.I) is not None and digest != "0" * 64
                for digest in hashes
            )
            and item.count("--hash=sha256:") == len(hashes)
            and not item.startswith(("-r", "-e"))
            and " @ " not in item
        )

    invalid = [
        item for item in requirements if item not in vcs_direct and not is_exact_hash_pinned(item)
    ]
    if invalid:
        return False, f"requirements must be exact, hash-pinned entries: {invalid[:3]!r}"
    if vcs_revision is not None:
        package_entries = [
            item
            for item in requirements
            if re.match(rf"^{re.escape(package)}(?:\s|\[|@|==)", item, flags=re.I)
        ]
        if len(vcs_direct) != 1 or package_entries != vcs_direct:
            return False, f"missing exact PEP 610 VCS direct pin for {package}@{vcs_revision}"
    else:
        direct = re.compile(
            rf"^{re.escape(package)}(?:\[[^]]+\])?=={re.escape(version)}(?:\s|\\|$)",
            re.I,
        )
        if not any(direct.search(item) for item in requirements):
            return False, f"missing exact direct pin {package}=={version}"
    return True, f"path={path.resolve()}; entries={len(requirements)}; sha256={digest}"


def _load_clean_manifest(
    path: Path | None,
    *,
    expected_count: int,
) -> tuple[Any | None, bool, str]:
    if path is None:
        return None, False, "path not configured"
    try:
        manifest = load_public_manifest(path)
        digest = sha256_file(path)
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        return None, False, f"invalid clean manifest: {exc}"
    zero_hashes = [
        resource.resource_id for resource in manifest.resources if resource.content_hash == "0" * 64
    ]
    ok = (
        manifest.resource_count == expected_count
        and manifest.manifest_hash != "0" * 64
        and not zero_hashes
    )
    detail = (
        f"resources={manifest.resource_count}/{expected_count}; "
        f"manifest_hash={manifest.manifest_hash}; file_sha256={digest}"
    )
    if zero_hashes:
        detail += f"; zero_content_hashes={zero_hashes[:3]!r}"
    return manifest, ok, detail


def _load_cases(
    path: Path | None,
    expected_count: int,
) -> tuple[FrozenCaseBundle | None, bool, str]:
    if path is None:
        return None, False, "path not configured"
    try:
        bundle = load_frozen_cases(path, research_mode=True)
        digest = sha256_file(path)
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        return None, False, f"invalid frozen cases: {exc}"
    ok = len(bundle.cases) == expected_count
    return bundle, ok, f"cases={len(bundle.cases)}/{expected_count}; file_sha256={digest}"


def overlay_attestation_payload(bundle: FrozenCaseBundle) -> dict[str, Any]:
    """Return the canonical hash-only overlay attestation wire payload."""

    return build_overlay_attestation(bundle).to_dict()


def _validate_overlay_attestation(
    path: Path | None,
    cases: FrozenCaseBundle | None,
) -> tuple[bool, str]:
    if path is None:
        return False, "path not configured"
    if cases is None:
        return False, "cannot validate overlays before the cases bundle"
    try:
        actual = load_overlay_attestation(path, expected_bundle=cases)
        file_digest = sha256_file(path)
    except (OSError, json.JSONDecodeError, CaseBundleError, TypeError, ValueError) as exc:
        return False, f"cannot read overlay attestation: {exc}"
    zero_hash = any(
        value == "0" * 64
        for entry in actual.cases
        for value in (
            entry.sham_content_hash,
            entry.poison_content_hash,
            entry.trigger_sha256,
            entry.nonce_sha256,
        )
    )
    if zero_hash:
        return False, "overlay attestation contains an all-zero placeholder digest"
    return (
        True,
        f"cases={len(cases.cases)}; bundle_hash={actual.bundle_hash}; file_sha256={file_digest}",
    )


def _find_data_bundle(appworld_root: Path | None, filename: str) -> Path | None:
    if appworld_root is None or not filename:
        return None
    candidates = (appworld_root / filename, appworld_root / "data" / filename)
    return next((path for path in candidates if path.is_file()), None)


def _select_mode(require_research_ready: bool, mode: Mode | None) -> Mode:
    if mode is None:
        return "research" if require_research_ready else "instrumentation"
    if mode not in ("instrumentation", "research"):
        raise ValueError("mode must be 'instrumentation' or 'research'")
    if require_research_ready and mode != "research":
        raise ValueError("require_research_ready=True conflicts with instrumentation mode")
    return mode


def run_preflight(
    config_path: str | Path,
    *,
    project_root: str | Path | None = None,
    appworld_root: str | Path | None = None,
    clean_manifest: str | Path | None = None,
    cases_path: str | Path | None = None,
    overlays_path: str | Path | None = None,
    model_url: str | None = None,
    model_api_key_env: str | None = None,
    dependency_lockfiles: Sequence[str | Path] | None = None,
    require_research_ready: bool = True,
    mode: Mode | None = None,
) -> PreflightReport:
    """Inspect immutable evidence without downloading data or mutating services."""

    selected_mode = _select_mode(require_research_ready, mode)
    root = Path(project_root or Path.cwd()).resolve()
    checks: list[PreflightCheck] = []

    try:
        config = load_config(config_path)
    except (OSError, ConfigValidationError) as exc:
        checks.append(_check("config_v02_valid", False, str(exc), "instrumentation", selected_mode))
        return PreflightReport(tuple(checks), selected_mode)
    checks.append(
        _check(
            "config_v02_valid",
            config.design_valid,
            str(Path(config_path).resolve()),
            "instrumentation",
            selected_mode,
        )
    )

    runner_ready = config.protocol.runner_ready is True
    checks.append(
        _check(
            "config_runner_ready",
            runner_ready,
            f"runner_ready={config.protocol.runner_ready!r}",
            "research",
            selected_mode,
        )
    )

    safety = config.safety
    safety_contract = bool(
        safety.isolated_local_environment is True
        and safety.harmless_canary_only is True
        and safety.real_accounts_credentials_or_network_callbacks is False
        and safety.public_resource_injection is False
        and safety.destructive_or_self_propagating_actions is False
    )
    checks.append(
        _check(
            "safety_policy_contract",
            safety_contract,
            "configured local/no-op/no credentials/no public injection/no propagation",
            "instrumentation",
            selected_mode,
        )
    )

    prompt_ok, prompt_detail = _hash_group(root, _PROMPT_PATHS)
    checks.append(
        _check(
            "prompt_bundle_hashable",
            prompt_ok,
            prompt_detail,
            "instrumentation",
            selected_mode,
        )
    )
    code_ok, code_detail = _validate_code_bundle(root)
    checks.append(
        _check(
            "code_bundle_hashable",
            code_ok,
            code_detail,
            "instrumentation",
            selected_mode,
        )
    )

    checks.append(
        _check(
            "appworld_python",
            _python_version_ok(),
            f"{platform.python_implementation()} {platform.python_version()}; required=3.11+",
            "research",
            selected_mode,
        )
    )
    expected_appworld = str(config.appworld.package_version)
    actual_appworld = _package_version("appworld")
    checks.append(
        _check(
            "appworld_package",
            actual_appworld == expected_appworld,
            f"expected={expected_appworld}; actual={actual_appworld or 'missing'}",
            "research",
            selected_mode,
        )
    )
    expected_appworld_revision = str(config.appworld.git_revision)
    actual_appworld_revision, appworld_revision_detail = _package_git_revision("appworld")
    checks.append(
        _check(
            "appworld_git_revision",
            actual_appworld_revision == expected_appworld_revision,
            f"expected={expected_appworld_revision}; {appworld_revision_detail}",
            "research",
            selected_mode,
        )
    )

    configured_appworld_root = appworld_root or os.environ.get("APPWORLD_ROOT")
    appworld_path, appworld_detail = _safe_path(configured_appworld_root, kind="directory")
    checks.append(
        _check(
            "appworld_root",
            appworld_path is not None,
            appworld_detail,
            "research",
            selected_mode,
        )
    )
    outside_repository = False
    if appworld_path is not None:
        outside_repository = not _overlaps_repository(appworld_path, root)
    checks.append(
        _check(
            "protected_data_outside_repository",
            outside_repository,
            str(appworld_path) if appworld_path else "AppWorld root unavailable",
            "research",
            selected_mode,
        )
    )

    docs_path = appworld_path / "data" / "api_docs" / "standard" if appworld_path else None
    docs_ok = docs_path is not None and docs_path.is_dir()
    checks.append(
        _check(
            "appworld_standard_docs",
            docs_ok,
            str(docs_path) if docs_ok else f"missing directory: {docs_path}",
            "research",
            selected_mode,
        )
    )

    configured_data_hash = str(config.appworld.data_bundle_sha256)
    data_hash_frozen = is_sha256(configured_data_hash) and configured_data_hash != "0" * 64
    checks.append(
        _check(
            "data_bundle_hash_configured",
            data_hash_frozen,
            configured_data_hash,
            "research",
            selected_mode,
        )
    )
    data_path = _find_data_bundle(appworld_path, str(config.appworld.data_bundle))
    actual_data_hash, actual_data_detail = (
        _artifact_hash(data_path) if data_path is not None else (None, "data bundle file missing")
    )
    checks.append(
        _check(
            "data_bundle_hash_matches",
            bool(data_hash_frozen and actual_data_hash == configured_data_hash),
            f"expected={configured_data_hash}; {actual_data_detail}",
            "research",
            selected_mode,
        )
    )

    manifest_path, manifest_path_detail = _safe_path(clean_manifest, kind="file")
    manifest, manifest_ok, manifest_detail = _load_clean_manifest(
        manifest_path,
        expected_count=int(config.resource_pool.clean_resources),
    )
    checks.append(
        _check(
            "clean_manifest_content",
            manifest_path is not None and manifest_ok,
            manifest_detail if manifest_path is not None else manifest_path_detail,
            "research",
            selected_mode,
        )
    )

    docs_match = False
    docs_match_detail = "clean docs or manifest unavailable"
    if docs_ok and manifest is not None:
        try:
            rebuilt_pool = load_standard_api_docs(
                docs_path,
                expected_count=int(config.resource_pool.clean_resources),
                excluded_helpers=tuple(config.resource_pool.exclude_helpers),
            )
            docs_match = rebuilt_pool.manifest.manifest_hash == manifest.manifest_hash
            docs_match_detail = (
                f"rebuilt={rebuilt_pool.manifest.manifest_hash}; frozen={manifest.manifest_hash}"
            )
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            docs_match_detail = f"cannot rebuild clean pool: {exc}"
    checks.append(
        _check(
            "clean_manifest_matches_docs",
            docs_match,
            docs_match_detail,
            "research",
            selected_mode,
        )
    )

    cases_file, cases_path_detail = _safe_path(cases_path, kind="file")
    case_bundle, cases_ok, cases_detail = _load_cases(cases_file, int(config.pilot.cases))
    appworld_case_count_matches = case_bundle is not None and len(case_bundle.cases) == int(
        config.appworld.train_pilot_cases
    )
    checks.append(
        _check(
            "case_bundle_content",
            bool(cases_file is not None and cases_ok and appworld_case_count_matches),
            cases_detail if cases_file is not None else cases_path_detail,
            "research",
            selected_mode,
        )
    )

    overlay_file, overlay_path_detail = _safe_path(overlays_path, kind="file")
    overlay_ok, overlay_detail = _validate_overlay_attestation(overlay_file, case_bundle)
    checks.append(
        _check(
            "overlay_attestation_content",
            overlay_file is not None and overlay_ok,
            overlay_detail if overlay_file is not None else overlay_path_detail,
            "research",
            selected_mode,
        )
    )

    protected_paths = {
        "appworld_root": appworld_path,
        "clean_manifest": manifest_path,
        "cases": cases_file,
        "overlays": overlay_file,
    }
    protected_inside = [
        name
        for name, path in protected_paths.items()
        if path is not None and _overlaps_repository(path, root)
    ]
    protected_paths_ok = all(path is not None for path in protected_paths.values()) and not (
        protected_inside
    )
    checks.append(
        _check(
            "protected_inputs_outside_repository",
            protected_paths_ok,
            (
                "all protected inputs resolve outside the repository"
                if protected_paths_ok
                else "missing_or_inside="
                + ",".join(
                    sorted(
                        name
                        for name, path in protected_paths.items()
                        if path is None or name in protected_inside
                    )
                )
            ),
            "research",
            selected_mode,
        )
    )

    lock_paths = tuple(
        Path(path) if Path(path).is_absolute() else root / Path(path)
        for path in (dependency_lockfiles or _DEFAULT_LOCKFILES)
    )
    lock_expectations = (
        ("appworld", expected_appworld, str(config.appworld.git_revision)),
        ("vllm", str(config.model.vllm_version), None),
    )
    if len(lock_paths) != len(lock_expectations):
        checks.append(
            _check(
                "dependency_lockfiles",
                False,
                f"expected exactly two lockfiles; got {len(lock_paths)}",
                "research",
                selected_mode,
            )
        )
    else:
        for index, (path, (package, version, vcs_revision)) in enumerate(
            zip(lock_paths, lock_expectations, strict=True)
        ):
            ok, detail = _validate_lockfile(
                path,
                package,
                version,
                vcs_revision=vcs_revision,
            )
            checks.append(
                _check(
                    f"dependency_lockfile_{index + 1}_{package}",
                    ok,
                    detail,
                    "research",
                    selected_mode,
                )
            )

    expected_model = str(config.model.id)
    if model_url:
        if (
            model_api_key_env is not None
            and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", model_api_key_env) is None
        ):
            record, service_detail = None, "model API key environment name is invalid"
        else:
            api_key = os.environ.get(model_api_key_env) if model_api_key_env else None
            record, service_detail = _fetch_model_record(
                model_url,
                expected_model,
                api_key=api_key,
            )
    else:
        record, service_detail = None, "model URL not configured"
    checks.append(
        _check(
            "model_service_identity",
            record is not None and record.get("id") == expected_model,
            service_detail,
            "research",
            selected_mode,
        )
    )

    expected_metadata: tuple[tuple[str, Any, tuple[tuple[str, ...], ...]], ...] = (
        (
            "model_revision_reported",
            str(config.model.revision),
            (("revision",), ("model_revision",)),
        ),
        ("model_dtype_reported", str(config.model.dtype), (("dtype",),)),
    )
    for name, expected, paths in expected_metadata:
        actual = _metadata_value(record, *paths) if record is not None else None
        checks.append(
            _check(
                name,
                actual == expected,
                f"endpoint declaration: expected={expected!r}; actual={actual!r}",
                "research",
                selected_mode,
            )
        )

    actual_generation = (
        _metadata_value(record, ("generation",), ("generation_config",))
        if record is not None
        else None
    )
    generation_ok, generation_detail = _mapping_matches(
        actual_generation,
        config.model.generation.to_dict(),
    )
    checks.append(
        _check(
            "model_generation_reported",
            generation_ok,
            f"endpoint declaration: {generation_detail}",
            "research",
            selected_mode,
        )
    )
    expected_runtime = {
        "max_model_len": config.model.max_model_len,
        "prefix_caching": config.model.prefix_caching,
        "server_sessions": config.model.server_sessions,
        **config.model.serving.to_dict(),
    }
    actual_runtime = (
        _metadata_value(record, ("runtime",), ("runtime_config",)) if record is not None else None
    )
    runtime_ok, runtime_detail = _mapping_matches(actual_runtime, expected_runtime)
    checks.append(
        _check(
            "model_runtime_reported",
            runtime_ok,
            f"endpoint declaration: {runtime_detail}",
            "research",
            selected_mode,
        )
    )

    remote_model = bool(model_url and _model_url_is_remote(model_url))
    expected_vllm = str(config.model.vllm_version)
    expected_gpu = str(config.model.gpu)
    metadata_vllm = _metadata_value(record, ("vllm_version",)) if record else None
    metadata_gpu = _metadata_value(record, ("gpu",), ("hardware", "gpu")) if record else None
    endpoint_stack_reported_consistent = (
        metadata_vllm == expected_vllm and metadata_gpu == expected_gpu
    )
    if remote_model:
        execution_stack_ok = endpoint_stack_reported_consistent
        execution_stack_detail = (
            "remote endpoint declarations: "
            f"vllm={metadata_vllm!r}/{expected_vllm!r}; "
            f"gpu={metadata_gpu!r}/{expected_gpu!r}"
        )
    else:
        gpu_rows, gpu_error = _gpu_rows()
        eligible = [
            (name, memory)
            for name, memory in gpu_rows
            if "H200" in name.upper() and memory >= 140_000
        ]
        local_gpu_matches_config = expected_gpu == "NVIDIA_H200_141GB" and bool(eligible)
        execution_stack_ok = endpoint_stack_reported_consistent and local_gpu_matches_config
        execution_stack_detail = (
            "loopback endpoint declarations plus local nvidia-smi probe: "
            f"vllm={metadata_vllm!r}/{expected_vllm!r}; "
            f"gpu={metadata_gpu!r}/{expected_gpu!r}; "
            f"eligible_gpu={eligible!r}; visible={gpu_rows!r}; error={gpu_error!r}; "
            "runner environment is intentionally not used to infer model-service packages"
        )
    checks.append(
        _check(
            "model_execution_stack_reported_consistent",
            execution_stack_ok,
            execution_stack_detail,
            "research",
            selected_mode,
        )
    )

    try:
        free_bytes = shutil.disk_usage(root).free
        disk_ok = free_bytes >= 100 * 1024**3
        disk_detail = (
            f"{free_bytes / 1024**3:.1f} GiB free; keep model/data caches outside repository"
        )
    except OSError as exc:
        disk_ok, disk_detail = False, f"cannot inspect disk: {exc}"
    checks.append(_check("free_disk_headroom", disk_ok, disk_detail, "advisory", selected_mode))
    return PreflightReport(tuple(checks), selected_mode)


def format_preflight(report: PreflightReport) -> str:
    lines = [
        f"mode: {report.mode}",
        f"ready: {str(report.ready).lower()}",
        f"instrumentation_ready: {str(report.instrumentation_ready).lower()}",
        f"research_ready: {str(report.research_ready).lower()}",
    ]
    for check in report.checks:
        marker = "PASS" if check.ok else ("FAIL" if check.required else "WARN")
        lines.append(f"[{marker}] {check.name} ({check.gate}): {check.detail}")
    return "\n".join(lines)


def required_failures(report: PreflightReport) -> Iterable[str]:
    return (check.name for check in report.failed_required)


__all__ = [
    "PreflightCheck",
    "PreflightReport",
    "format_preflight",
    "overlay_attestation_payload",
    "required_failures",
    "run_preflight",
]
