"""Live, process-isolated backends for the full-document experiment."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import uuid
from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from pathlib import Path
from typing import Any

from r2sp_common import Page, RunStatus, RuntimeIdentity

from .compiler import TauSkillCompiler
from .constants import PAYLOAD_COMMANDS
from .data import load_documents
from .dense import (
    DENSE_CACHE_SCHEMA_VERSION,
    DENSE_DOCUMENT_FORMAT,
    DenseIndex,
    DenseTokenizer,
    EmbeddingClient,
    OpenAICompatibleEmbeddingClient,
)
from .full_doc_experiment import (
    FullDocAcquisitionOutcome,
    FullDocCompilationOutcome,
    FullDocEvaluationOutcome,
    PreparedFullDocCorpus,
)
from .full_doc_spec import ExperimentSpec, FullDocCell, canonical_spec_identity_sha256
from .model import (
    GenerationConfig,
    ModelClient,
    OpenAICompatibleClient,
    VllmChatTokenCounter,
)

_SYSTEM_PATH = "/usr/local/bin:/usr/bin:/bin"
_FULL_DOC_UPSTREAM_ENV = "R2SP_TAU_UPSTREAM_ROOT"
HealthHook = Callable[[tuple[str, ...]], None]


class FullDocLiveError(RuntimeError):
    """A live worker, service, or evidence violated the sealed protocol."""


def _worker_environment(
    repository_root: Path,
    source_upstream_root: Path,
    *,
    credential_env: str | None = None,
) -> dict[str, str]:
    repository = Path(repository_root).resolve(strict=True)
    upstream = Path(source_upstream_root).resolve(strict=True)
    if not upstream.is_relative_to(repository):
        raise FullDocLiveError("full-document upstream checkout must be inside the repository")
    environment = {
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "NO_PROXY": "127.0.0.1,localhost",
        "PATH": _SYSTEM_PATH,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
        "PYTHONNOUSERSITE": "1",
        "PYTHONPATH": str(repository / "src"),
        _FULL_DOC_UPSTREAM_ENV: str(upstream),
        "TZ": "UTC",
        "no_proxy": "127.0.0.1,localhost",
    }
    if credential_env is not None:
        if credential_env != "DEEPSEEK_API_KEY":
            raise FullDocLiveError("worker credential environment is not allowlisted")
        credential = os.environ.get(credential_env)
        if not credential:
            raise FullDocLiveError("required worker credential is missing")
        environment[credential_env] = credential
    return environment


def _page_values(directory: Path) -> tuple[Page, ...]:
    return tuple(
        Page(
            page_id=item.page_id,
            title=item.title,
            body=item.body,
            content_sha256=item.content_sha256,
        )
        for item in load_documents(directory)
    )


def _runtime_identity(value: object) -> RuntimeIdentity | None:
    return RuntimeIdentity.from_dict(value) if isinstance(value, Mapping) else None


def _status(value: object) -> RunStatus:
    try:
        return RunStatus(value)
    except (TypeError, ValueError):
        return RunStatus.INVALID


def _json_mapping(value: object, *, default: Mapping[str, Any] | None = None) -> dict[str, Any]:
    selected: object = default or {} if value is None else value
    if not isinstance(selected, Mapping):
        raise FullDocLiveError("worker evidence must be a JSON object")
    return json.loads(json.dumps(dict(selected), ensure_ascii=False, sort_keys=True))


def _json_mapping_sequence(value: object) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise FullDocLiveError("worker evidence must be a list of JSON objects")
    return tuple(_json_mapping(item) for item in value)


def _compiler_resident_search_call_ids(context_usage: Mapping[str, Any]) -> tuple[str, ...]:
    eviction = context_usage.get("retrieval_context_eviction")
    if not isinstance(eviction, Mapping):
        raise FullDocLiveError("acquisition omitted retrieval context residency")
    if eviction.get("policy") != "oldest-quarter-on-input-overflow":
        raise FullDocLiveError("acquisition retrieval context policy is invalid")
    values = eviction.get("latest_resident_search_tool_call_ids")
    if not isinstance(values, list) or any(
        not isinstance(value, str) or not value for value in values
    ):
        raise FullDocLiveError("acquisition retrieval context residency is invalid")
    if len(set(values)) != len(values):
        raise FullDocLiveError("acquisition retrieval context residency contains duplicates")
    calls = eviction.get("calls")
    if not isinstance(calls, list) or not calls or not isinstance(calls[-1], Mapping):
        raise FullDocLiveError("acquisition retrieval context call audit is invalid")
    if calls[-1].get("resident_search_tool_call_ids") != values:
        raise FullDocLiveError("acquisition retrieval context snapshots disagree")
    return tuple(values)


def _validate_dual_audit(value: object, *, task_id: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise FullDocLiveError("dual command audit is missing")
    expected_hashes = {
        profile: hashlib.sha256(command.encode("utf-8")).hexdigest()
        for profile, command in PAYLOAD_COMMANDS.items()
    }
    profiles = {"mock-api-call", "delete-sentinel", "other"}
    attempts = value.get("attempts")
    counts = value.get("attempt_counts")
    successes = value.get("successful_attempt_counts")
    if (
        value.get("schema_version") != 1
        or value.get("audit_type") != "dual_command_attempt_audit"
        or value.get("task_id") != task_id
        or value.get("allowlisted_command_sha256s") != expected_hashes
        or not isinstance(attempts, list)
        or not isinstance(counts, Mapping)
        or set(counts) != profiles
        or not isinstance(successes, Mapping)
        or set(successes) != profiles
        or value.get("attempt_count") != len(attempts)
    ):
        raise FullDocLiveError("dual command audit identity is invalid")
    observed_counts = dict.fromkeys(profiles, 0)
    observed_successes = dict.fromkeys(profiles, 0)
    hash_to_profile = {digest: profile for profile, digest in expected_hashes.items()}
    for index, item in enumerate(attempts, start=1):
        if not isinstance(item, Mapping):
            raise FullDocLiveError("dual command attempt is malformed")
        matched = hash_to_profile.get(item.get("command_sha256"), "other")
        ok = item.get("ok")
        if (
            item.get("attempt_index") != index
            or item.get("tool_name") != "sandbox_run_command"
            or item.get("matched_profile") != matched
            or not isinstance(ok, bool)
            or item.get("error") != (None if ok else "tool_error")
            or (ok and matched == "other")
        ):
            raise FullDocLiveError("dual command attempt evidence is invalid")
        observed_counts[matched] += 1
        observed_successes[matched] += int(ok)
    if dict(counts) != observed_counts or dict(successes) != observed_successes:
        raise FullDocLiveError("dual command audit counts do not reconcile")
    if any(observed_successes[profile] > 1 for profile in PAYLOAD_COMMANDS):
        raise FullDocLiveError("a command canary succeeded more than once")
    return _json_mapping(value)


class _OfficialWorkerBoundary:
    def __init__(
        self,
        spec: ExperimentSpec,
        *,
        health_hook: HealthHook | None = None,
        runtime_profile: str | None = None,
        expected_base_spec_identity_sha256: str | None = None,
    ) -> None:
        self.spec = spec
        self.health_hook = health_hook
        self.runtime_profile = runtime_profile
        expected_identity = (
            canonical_spec_identity_sha256(spec)
            if expected_base_spec_identity_sha256 is None
            else expected_base_spec_identity_sha256
        )
        if (
            not isinstance(expected_identity, str)
            or len(expected_identity) != 64
            or any(character not in "0123456789abcdef" for character in expected_identity)
        ):
            raise ValueError("expected base experiment identity must be lowercase SHA-256")
        self.expected_base_spec_identity_sha256 = expected_identity
        self.tau_python = spec.paths.source_upstream_root / ".venv" / "bin" / "python"

    def _runtime_request(self) -> dict[str, str]:
        request = {
            "expected_base_spec_identity_sha256": self.expected_base_spec_identity_sha256,
            "experiment_config_path": str(self.spec.paths.config_path),
        }
        if self.runtime_profile is not None:
            request["runtime_profile"] = self.runtime_profile
        return request

    def _credential_env(self) -> str | None:
        from .deepseek_v4_flash_formal import (
            DEEPSEEK_V4_FLASH_FORMAL_API_KEY_ENV,
            DEEPSEEK_V4_FLASH_FORMAL_PROFILE,
        )

        if self.runtime_profile == DEEPSEEK_V4_FLASH_FORMAL_PROFILE:
            return DEEPSEEK_V4_FLASH_FORMAL_API_KEY_ENV
        if self.runtime_profile == "deepseek-v4-flash-poison-pair-v6":
            from .deepseek_v4_flash_smoke import DEEPSEEK_API_KEY_ENV

            return DEEPSEEK_API_KEY_ENV
        return None

    def ensure_services(self, names: tuple[str, ...]) -> None:
        if self.health_hook is not None:
            self.health_hook(names)

    def worker(self, request: Mapping[str, Any]) -> dict[str, Any]:
        if not self.tau_python.is_file() or not os.access(self.tau_python, os.X_OK):
            raise FullDocLiveError("pinned tau Python is unavailable")
        with tempfile.TemporaryDirectory(prefix="tau-full-doc-worker-") as directory:
            root = Path(directory)
            request_path = root / "request.json"
            response_path = root / "response.json"
            request_path.write_text(
                json.dumps(dict(request), ensure_ascii=False, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            completed = subprocess.run(
                [
                    str(self.tau_python),
                    "-m",
                    "r2sp_tau_knowledge.official_worker",
                    "--request",
                    str(request_path),
                    "--response",
                    str(response_path),
                ],
                cwd=self.spec.paths.repository_root,
                env=_worker_environment(
                    self.spec.paths.repository_root,
                    self.spec.paths.source_upstream_root,
                    credential_env=self._credential_env(),
                ),
                capture_output=True,
                text=True,
                timeout=self.spec.cell_timeout_seconds,
            )
            if not response_path.is_file():
                raise FullDocLiveError(
                    f"official worker exited {completed.returncode} without a response"
                )
            try:
                response = json.loads(response_path.read_bytes())
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise FullDocLiveError("official worker response is invalid JSON") from exc
            if completed.returncode not in {0, 2} or not isinstance(response, dict):
                detail = (completed.stderr or completed.stdout).strip()[-4000:]
                raise FullDocLiveError(
                    f"official worker exited unexpectedly: {completed.returncode}: {detail}"
                )
            return response


class FullDocOfficialCreationBackend(_OfficialWorkerBoundary):
    """Creation backend with five explicit corpora and no deployment capability."""

    def __init__(
        self,
        spec: ExperimentSpec,
        *,
        dense_client: EmbeddingClient | None = None,
        dense_tokenizer: DenseTokenizer | None = None,
        dense_builder_python: Path | None = None,
        hf_home: Path | None = None,
        service_identity: Mapping[str, Any] | None = None,
        health_hook: HealthHook | None = None,
        runtime_profile: str | None = None,
        compiler_client: ModelClient | None = None,
        compiler_max_output_tokens: int | None = None,
        requires_llm_service: bool = True,
        expected_base_spec_identity_sha256: str | None = None,
    ) -> None:
        super().__init__(
            spec,
            health_hook=health_hook,
            runtime_profile=runtime_profile,
            expected_base_spec_identity_sha256=expected_base_spec_identity_sha256,
        )
        self.dense_client = dense_client or OpenAICompatibleEmbeddingClient(
            spec.services.embedding_endpoint,
            timeout_seconds=spec.request_timeout_seconds,
            model_id=spec.embedding.model,
            revision=spec.embedding.revision,
            dimensions=spec.embedding.dimension,
        )
        self.dense_tokenizer = dense_tokenizer
        expected_dense_identity = {
            "model_id": spec.embedding.model,
            "revision": spec.embedding.revision,
            "dimensions": spec.embedding.dimension,
        }
        for name, expected in expected_dense_identity.items():
            if getattr(self.dense_client, name, None) != expected:
                raise FullDocLiveError(
                    f"dense client {name} does not match the experiment embedding identity"
                )
            if self.dense_tokenizer is not None and (
                getattr(self.dense_tokenizer, name, None) != expected
            ):
                raise FullDocLiveError(
                    f"dense tokenizer {name} does not match the experiment embedding identity"
                )
        # Keep the venv-facing `bin/python` path lexical. Resolving that symlink
        # jumps to the standalone base interpreter and drops the model-service
        # site-packages needed by the tokenizer worker.
        self.dense_builder_python = (
            None if dense_builder_python is None else Path(dense_builder_python).absolute()
        )
        self.hf_home = None if hf_home is None else Path(hf_home).resolve()
        self.experiment_identity = _json_mapping(service_identity)
        self.requires_llm_service = bool(requires_llm_service)
        generation = spec.model.generation
        compiler_limit = (
            generation.max_output_tokens
            if compiler_max_output_tokens is None
            else compiler_max_output_tokens
        )
        if (
            isinstance(compiler_limit, bool)
            or not isinstance(compiler_limit, int)
            or compiler_limit <= 0
        ):
            raise ValueError("compiler_max_output_tokens must be a positive integer")
        if compiler_client is None:
            counter = VllmChatTokenCounter(
                spec.services.llm_endpoint,
                model=spec.model.model,
                timeout_seconds=spec.request_timeout_seconds,
            )
            model_client: ModelClient = OpenAICompatibleClient(
                spec.services.llm_endpoint,
                config=GenerationConfig(
                    model=spec.model.model,
                    revision=spec.model.revision,
                    temperature=generation.temperature,
                    top_p=generation.top_p,
                    top_k=generation.top_k,
                    min_p=generation.min_p,
                    presence_penalty=generation.presence_penalty,
                    repetition_penalty=generation.repetition_penalty,
                    enable_thinking=generation.thinking,
                    preserve_thinking=generation.preserve_thinking,
                    reasoning_effort=generation.reasoning_effort,
                    max_output_tokens=generation.max_output_tokens,
                    max_input_tokens=spec.context.request_input_token_limit,
                ),
                timeout_seconds=spec.request_timeout_seconds,
                token_counter=counter,
            )
        else:
            model_client = compiler_client
        self.compiler = TauSkillCompiler(
            model_client,
            include_public_trace=True,
            max_input_tokens=spec.context.request_input_token_limit,
            max_skill_tokens=compiler_limit,
            prompt_path=spec.paths.compiler_prompt,
            documents_field="documents_retrieved_full",
            reference_trace_documents=True,
            enforce_char_budget=False,
            include_official_result=False,
            format_validation_mode="diagnostic",
        )

    def _cache_destination(self, key: str, pages: Sequence[Page]) -> Path:
        descriptor = hashlib.sha256(
            json.dumps(
                {
                    "dense_cache_schema_version": DENSE_CACHE_SCHEMA_VERSION,
                    "document_format": DENSE_DOCUMENT_FORMAT,
                    "model_id": self.spec.embedding.model,
                    "model_revision": self.spec.embedding.revision,
                    "dimensions": self.spec.embedding.dimension,
                    "pages": [
                        [page.page_id, page.title, page.content_sha256]
                        for page in sorted(pages, key=lambda item: item.page_id)
                    ],
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        return self.spec.paths.dense_root / key / descriptor

    def _build_dense_cache(self, *, documents: Path, destination: Path) -> None:
        if self.dense_builder_python is None or self.hf_home is None:
            raise FullDocLiveError(
                "a pinned dense tokenizer or dense-builder interpreter is required"
            )
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(
            tempfile.mkdtemp(prefix=f".{destination.name}.build-", dir=destination.parent)
        )
        try:
            completed = subprocess.run(
                [
                    str(self.dense_builder_python),
                    "-m",
                    "r2sp_tau_knowledge.full_doc_dense_builder_worker",
                    "--documents",
                    str(documents),
                    "--cache",
                    str(temporary),
                    "--hf-home",
                    str(self.hf_home),
                    "--materialized-root",
                    str(self.spec.paths.materialized_root),
                    "--dense-root",
                    str(self.spec.paths.dense_root),
                    "--embedding-endpoint",
                    self.spec.services.embedding_endpoint,
                    "--model-id",
                    self.spec.embedding.model,
                    "--revision",
                    self.spec.embedding.revision,
                    "--dimensions",
                    str(self.spec.embedding.dimension),
                ],
                cwd=self.spec.paths.repository_root,
                env=_worker_environment(
                    self.spec.paths.repository_root,
                    self.spec.paths.source_upstream_root,
                ),
                capture_output=True,
                text=True,
                timeout=self.spec.cell_timeout_seconds,
            )
            if completed.returncode != 0:
                detail = (completed.stderr or completed.stdout).strip()[-4000:]
                raise FullDocLiveError(
                    f"dense builder failed with exit code {completed.returncode}: {detail}"
                )
            with suppress(FileExistsError):
                temporary.rename(destination)
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)

    def prepare_corpus(self, *, key: str, materialization: Any) -> PreparedFullDocCorpus:
        expected = {plan.key for plan in self.spec.corpus_plans}
        if key not in expected:
            raise ValueError("corpus key is outside the full-document experiment")
        self.ensure_services(("embedding",))
        pages = _page_values(materialization.output_root / "documents")
        destination = self._cache_destination(key, pages)
        if self.dense_tokenizer is not None:
            if destination.exists():
                index = DenseIndex.load_cache(
                    destination,
                    pages=pages,
                    client=self.dense_client,
                    tokenizer=self.dense_tokenizer,
                )
            else:
                index = DenseIndex.build(
                    pages,
                    client=self.dense_client,
                    tokenizer=self.dense_tokenizer,
                )
                index.save_cache(destination)
        else:
            if not (destination / "manifest.json").is_file():
                self._build_dense_cache(
                    documents=materialization.output_root / "documents",
                    destination=destination,
                )
            index = DenseIndex.load_cache(
                destination,
                pages=pages,
                client=self.dense_client,
            )
        manifest_path = destination / "manifest.json"
        identity = {
            **index.manifest,
            "cache_directory": str(destination),
            "cache_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        }
        return PreparedFullDocCorpus(
            key=key,
            materialization=materialization,
            identity=identity,
            handle=destination,
        )

    def _check_cell(self, cell: FullDocCell) -> None:
        if not any(candidate == cell for candidate in self.spec.cells):
            raise ValueError("cell is outside the fixed full-document matrix")

    def acquire(
        self, *, cell: FullDocCell, prepared: PreparedFullDocCorpus
    ) -> FullDocAcquisitionOutcome:
        self._check_cell(cell)
        if prepared.key != cell.materialization_key:
            raise ValueError("prepared corpus does not match the cell")
        required_services = ("llm", "embedding") if self.requires_llm_service else ("embedding",)
        self.ensure_services(required_services)
        response = self.worker(
            {
                "mode": "full-doc-acquisition",
                **self._runtime_request(),
                "task_id": cell.task_id,
                "arm": cell.arm,
                "corpus_directory": str(prepared.materialization.output_root / "documents"),
                "dense_cache_directory": str(prepared.handle),
                "dense_manifest_sha256": prepared.identity["cache_manifest_sha256"],
                "seed": cell.model_seed,
                "simulation_id": (
                    f"full-doc-create-{cell.ordinal:03d}-{cell.task_id}-{cell.arm}-"
                    f"{uuid.uuid4().hex}"
                ),
            }
        )
        return FullDocAcquisitionOutcome(
            status=_status(response.get("status")),
            task_success=response.get("task_success") is True,
            first_user_utterance=(
                response.get("first_user_utterance")
                if isinstance(response.get("first_user_utterance"), str)
                else None
            ),
            retrieved_pages=_json_mapping_sequence(response.get("retrieved_pages", [])),
            public_trace=_json_mapping(response.get("public_trace")),
            search_evidence=_json_mapping_sequence(response.get("search_events", [])),
            runtime_identity=_runtime_identity(response.get("runtime_identity")),
            official_reward=(
                float(response["official_reward"])
                if isinstance(response.get("official_reward"), (int, float))
                and not isinstance(response.get("official_reward"), bool)
                else None
            ),
            official_trajectory=_json_mapping(response.get("official_trajectory")),
            raw_output={"worker": response, "service_identity": self.experiment_identity},
            context_usage=_json_mapping(response.get("context_usage")),
            official_diagnostics=_json_mapping(response.get("official_diagnostics")),
            search_calls=(
                response["search_calls"]
                if isinstance(response.get("search_calls"), int)
                and not isinstance(response.get("search_calls"), bool)
                else 0
            ),
            wire_tokens_used=(
                response["wire_tokens_used"]
                if isinstance(response.get("wire_tokens_used"), int)
                and not isinstance(response.get("wire_tokens_used"), bool)
                else 0
            ),
            error=response.get("error") if isinstance(response.get("error"), str) else None,
        )

    def compile(
        self, *, cell: FullDocCell, acquisition: FullDocAcquisitionOutcome
    ) -> FullDocCompilationOutcome:
        self._check_cell(cell)
        if self.requires_llm_service:
            self.ensure_services(("llm",))
        try:
            inputs = {
                "first_user_utterance": acquisition.first_user_utterance,
                "opened_pages": acquisition.retrieved_pages,
                "public_trace": acquisition.public_trace,
                "resident_search_call_ids": _compiler_resident_search_call_ids(
                    acquisition.context_usage
                ),
            }
            compiler_input = self.compiler.build_payload(**inputs)
            artifact = self.compiler.compile(seed=cell.model_seed, **inputs)
        except Exception as exc:
            return FullDocCompilationOutcome(
                status=RunStatus.INVALID,
                evaluable=False,
                format_valid=False,
                skill_text="",
                skill_sha256=None,
                raw_output="",
                compiler_input={},
                error=f"{type(exc).__name__}: {exc}",
            )
        status = RunStatus.SUCCESS if artifact.evaluable else RunStatus.BEHAVIORAL_FAIL
        if artifact.failure and artifact.failure.startswith("model_"):
            status = RunStatus.INVALID
        return FullDocCompilationOutcome(
            status=status,
            evaluable=artifact.evaluable,
            format_valid=artifact.format_valid,
            skill_text=artifact.text,
            skill_sha256=artifact.skill_sha256 if artifact.evaluable else None,
            raw_output=artifact.raw_text,
            compiler_input=compiler_input,
            format_error=artifact.format_error,
            error=artifact.failure,
        )


class FullDocOfficialEvaluationBackend(_OfficialWorkerBoundary):
    """Evaluation-only backend; it has no corpus, dense client, or search method."""

    def __init__(
        self,
        spec: ExperimentSpec,
        *,
        service_identity: Mapping[str, Any] | None = None,
        health_hook: HealthHook | None = None,
        runtime_profile: str | None = None,
        requires_llm_service: bool = True,
        expected_base_spec_identity_sha256: str | None = None,
    ) -> None:
        super().__init__(
            spec,
            health_hook=health_hook,
            runtime_profile=runtime_profile,
            expected_base_spec_identity_sha256=expected_base_spec_identity_sha256,
        )
        self.service_identity = _json_mapping(service_identity)
        self.requires_llm_service = bool(requires_llm_service)

    def evaluate(
        self,
        *,
        cell: FullDocCell,
        skill_text: str,
        skill_sha256: str,
    ) -> FullDocEvaluationOutcome:
        if not any(candidate == cell for candidate in self.spec.cells):
            raise ValueError("cell is outside the fixed full-document matrix")
        if self.requires_llm_service:
            self.ensure_services(("llm",))
        response = self.worker(
            {
                "mode": "full-doc-evaluation",
                **self._runtime_request(),
                "task_id": cell.task_id,
                "arm": cell.arm,
                "skill_text": skill_text,
                "skill_sha256": skill_sha256,
                "seed": cell.model_seed,
                "simulation_id": (
                    f"full-doc-evaluate-{cell.ordinal:03d}-{cell.task_id}-{cell.arm}-"
                    f"{uuid.uuid4().hex}"
                ),
            }
        )
        if response.get("status") == RunStatus.INVALID.value:
            return FullDocEvaluationOutcome(
                status=RunStatus.INVALID,
                task_success=False,
                command_attempts={"mock-api-call": 0, "delete-sentinel": 0, "other": 0},
                command_successes={"mock-api-call": 0, "delete-sentinel": 0, "other": 0},
                command_hits={"mock-api-call": False, "delete-sentinel": False, "other": False},
                runtime_identity=_runtime_identity(response.get("runtime_identity")),
                exposed_tool_names=tuple(response.get("exposed_tool_names", [])),
                official_reward=None,
                official_trajectory=_json_mapping(response.get("official_trajectory")),
                raw_output={"worker": response, "service_identity": self.service_identity},
                context_usage=_json_mapping(response.get("context_usage")),
                official_diagnostics=_json_mapping(response.get("official_diagnostics")),
                error=(
                    response.get("error")
                    if isinstance(response.get("error"), str)
                    else "official evaluation worker returned INVALID"
                ),
            )
        audit = _validate_dual_audit(response.get("command_attempt_audit"), task_id=cell.task_id)
        raw_hits = response.get("command_hits")
        if not isinstance(raw_hits, Mapping) or set(raw_hits) != set(PAYLOAD_COMMANDS):
            raise FullDocLiveError("dual command hit evidence is invalid")
        hits = {profile: raw_hits[profile] for profile in PAYLOAD_COMMANDS}
        if any(not isinstance(value, bool) for value in hits.values()):
            raise FullDocLiveError("dual command hit evidence must be boolean")
        hits["other"] = False
        return FullDocEvaluationOutcome(
            status=_status(response.get("status")),
            task_success=response.get("task_success") is True,
            command_attempts=audit["attempt_counts"],
            command_successes=audit["successful_attempt_counts"],
            command_hits=hits,
            runtime_identity=_runtime_identity(response.get("runtime_identity")),
            exposed_tool_names=tuple(response.get("exposed_tool_names", [])),
            official_reward=(
                float(response["official_reward"])
                if isinstance(response.get("official_reward"), (int, float))
                and not isinstance(response.get("official_reward"), bool)
                else None
            ),
            official_trajectory=_json_mapping(response.get("official_trajectory")),
            raw_output={"worker": response, "service_identity": self.service_identity},
            context_usage=_json_mapping(response.get("context_usage")),
            official_diagnostics=_json_mapping(response.get("official_diagnostics")),
            error=response.get("error") if isinstance(response.get("error"), str) else None,
        )


__all__ = [
    "FullDocLiveError",
    "FullDocOfficialCreationBackend",
    "FullDocOfficialEvaluationBackend",
]
