"""Non-research integration probe for a local OpenAI-compatible model service."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from typing import Any

from .agent import AgentBudgets, AgentRunner
from .compiler import SkillCompiler
from .model_client import ModelClient, OpenAICompatibleClient, QwenGenerationConfig
from .model_gateway import parse_loopback_backend
from .models import Resource
from .preflight import _fetch_model_record
from .retrieval import DeterministicBM25
from .runtime.base import FinishResult, RuntimeAdapter, RuntimeIdentity, RuntimeObservation

_COMPILER_OUTPUT_TOKEN_CEILING = 4096
_COMPILER_CONTEXT_RESERVE_TOKENS = 512


@dataclass(frozen=True)
class ModelProbeCheck:
    name: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class ModelProbeReport:
    checks: tuple[ModelProbeCheck, ...]

    @property
    def ready(self) -> bool:
        return all(check.ok for check in self.checks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": "model_service_instrumentation",
            "ready": self.ready,
            "research_eligible": False,
            "checks": [asdict(check) for check in self.checks],
        }


class _ProbeRuntime(RuntimeAdapter):
    def __init__(self) -> None:
        self._identity: RuntimeIdentity | None = None

    @property
    def identity(self) -> RuntimeIdentity | None:
        return self._identity

    def start(self) -> RuntimeIdentity:
        self._identity = RuntimeIdentity("probe-world", "probe-context", "probe-session")
        return self._identity

    def execute(self, app: str, api: str, args: Mapping[str, Any]) -> RuntimeObservation:
        expected = {"label": "r2sp", "payload": {"value": 1}}
        if app == "probe" and api == "noop" and dict(args) == expected:
            return RuntimeObservation(app, api, dict(args), True, {"accepted": True})
        return RuntimeObservation(
            app,
            api,
            dict(args),
            False,
            error_code="probe_execute_disabled",
            error_message="the model-service probe exposes no application mutations",
        )

    def finish(self, status: str, answer: str) -> FinishResult:
        return FinishResult(
            status,
            answer,
            task_success=status == "success",
            score=1.0 if status == "success" else 0.0,
        )

    def close(self) -> None:
        return None


def run_model_service_probe(
    *,
    base_url: str,
    model_id: str = "Qwen/Qwen3.8-27B",
    revision: str = "1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0",
    api_key: str | None = None,
    timeout_seconds: float = 300.0,
    max_model_len: int = 16384,
    client: ModelClient | None = None,
    record_fetcher: Callable[..., tuple[Mapping[str, Any] | None, str]] | None = None,
) -> ModelProbeReport:
    """Exercise identity, tokenizer, parsers, agent loop, and compiler.

    This is deliberately an instrumentation probe. It does not inspect model
    weights and cannot make an RTX/FP16 service research-equivalent to the
    frozen H200/BF16 protocol.
    """

    if not isinstance(max_model_len, int) or isinstance(max_model_len, bool):
        raise ValueError("max_model_len must be an integer")
    if max_model_len < 2048:
        raise ValueError("max_model_len must be at least 2048")
    parse_loopback_backend(base_url)
    selected_client = client or OpenAICompatibleClient(
        base_url,
        api_key=api_key,
        timeout_seconds=timeout_seconds,
        config=QwenGenerationConfig(
            model=model_id,
            revision=revision,
            max_output_tokens=512,
        ),
    )
    checks: list[ModelProbeCheck] = []

    fetch = record_fetcher or _fetch_model_record
    try:
        record, detail = fetch(base_url, model_id, api_key=api_key)
        identity_ok = record is not None and record.get("id") == model_id
        checks.append(ModelProbeCheck("model_identity", identity_ok, detail))
    except Exception as exc:  # external probe boundary
        checks.append(ModelProbeCheck("model_identity", False, exc.__class__.__name__))

    token_counter = getattr(selected_client, "count_tokens", None)
    try:
        if not callable(token_counter):
            raise TypeError("client has no tokenizer probe")
        count = token_counter("R2SP tokenizer probe")
        token_ok = isinstance(count, int) and not isinstance(count, bool) and count > 0
        checks.append(ModelProbeCheck("tokenizer", token_ok, f"count={count!r}"))
    except Exception as exc:  # external probe boundary
        checks.append(ModelProbeCheck("tokenizer", False, exc.__class__.__name__))

    try:
        message = selected_client.complete(
            [
                {"role": "system", "content": "Reply with a short plain-text acknowledgement."},
                {"role": "user", "content": "Model-service integration probe."},
            ],
            seed=20260829,
            max_output_tokens=64,
        )
        content = message.get("content") if isinstance(message, Mapping) else None
        ordinary_ok = isinstance(content, str) and bool(content.strip())
        checks.append(
            ModelProbeCheck(
                "ordinary_completion",
                ordinary_ok,
                "non_empty_content" if ordinary_ok else "missing_content",
            )
        )
    except Exception as exc:  # external probe boundary
        checks.append(ModelProbeCheck("ordinary_completion", False, exc.__class__.__name__))

    contract_probe = getattr(selected_client, "verify_tool_contract", None)
    try:
        if not callable(contract_probe):
            raise TypeError("client has no tool-contract probe")
        evidence = contract_probe()
        contract_ok = isinstance(evidence, Mapping) and evidence.get("arguments_valid") is True
        checks.append(
            ModelProbeCheck(
                "reasoning_and_tool_parser",
                contract_ok,
                "forced_finish_valid" if contract_ok else "invalid_contract_evidence",
            )
        )
    except Exception as exc:  # external probe boundary
        checks.append(ModelProbeCheck("reasoning_and_tool_parser", False, exc.__class__.__name__))

    selection_probe = getattr(selected_client, "verify_selection_contract", None)
    try:
        if not callable(selection_probe):
            raise TypeError("client has no selection-contract probe")
        evidence = selection_probe(selection_k=5)
        selection_ok = bool(
            isinstance(evidence, Mapping)
            and evidence.get("arguments_valid") is True
            and evidence.get("selection_k") == 5
        )
        checks.append(
            ModelProbeCheck(
                "exact_five_selection_parser",
                selection_ok,
                "select_docs_exact_five_valid" if selection_ok else "invalid_selection_evidence",
            )
        )
    except Exception as exc:  # external probe boundary
        checks.append(ModelProbeCheck("exact_five_selection_parser", False, exc.__class__.__name__))

    document = Resource(
        resource_id="probe-calendar-doc",
        app_name="probe",
        api_name="noop",
        title="No-side-effect nested-argument probe",
        body=(
            "Call probe.noop with exactly "
            '{"label":"r2sp","payload":{"value":1}}. This changes no state.'
        ),
    )
    agent_result = None
    try:
        agent_result = AgentRunner(
            selected_client,
            budgets=AgentBudgets(
                max_turns=8,
                max_api_calls=2,
                max_search_calls=4,
                max_unique_docs_read=2,
            ),
            top_k=1,
            max_context_tokens=max_model_len,
            max_output_tokens=512,
            context_reserve_tokens=512,
        ).run(
            (
                "Search for the no-side-effect nested-argument probe, read the returned document, "
                "call execute exactly as documented, then call finish with status success."
            ),
            {"probe": "Local no-side-effect parser probe."},
            _ProbeRuntime(),
            DeterministicBM25((document,), top_k=1),
            seed=20260829,
        )
        agent_ok = bool(
            agent_result.finish_status == "success"
            and document.resource_id in agent_result.resource_ids
            and len(agent_result.api_trace) == 1
            and agent_result.api_trace[0].get("app") == "probe"
            and agent_result.api_trace[0].get("api") == "noop"
            and agent_result.api_trace[0].get("args") == {"label": "r2sp", "payload": {"value": 1}}
            and agent_result.api_trace[0].get("ok") is True
            and agent_result.failure is None
        )
        checks.append(
            ModelProbeCheck(
                "agent_four_tool_loop",
                agent_ok,
                (
                    f"finish={agent_result.finish_status!r}; "
                    f"reads={len(agent_result.resource_ids)}; "
                    f"api_calls={len(agent_result.api_trace)}; failure={agent_result.failure!r}"
                ),
            )
        )
    except Exception as exc:  # external probe boundary
        checks.append(ModelProbeCheck("agent_four_tool_loop", False, exc.__class__.__name__))

    try:
        if agent_result is None:
            raise RuntimeError("agent probe did not produce compiler input")
        compiler_output_tokens = min(
            _COMPILER_OUTPUT_TOKEN_CEILING,
            max_model_len // 2,
        )
        compiler_input_tokens = min(
            2048,
            max_model_len - compiler_output_tokens - _COMPILER_CONTEXT_RESERVE_TOKENS,
        )
        compiler = SkillCompiler(
            selected_client,
            max_input_tokens=compiler_input_tokens,
            max_skill_tokens=compiler_output_tokens,
            token_counter=token_counter if callable(token_counter) else None,
        )
        artifact = compiler.compile(
            "Create the local calendar event described by the user.",
            agent_result.read_documents,
            agent_result.normalized_trace,
            agent_result.task_success,
            seed=20260829,
        )
        compiler_ok = artifact.valid and not artifact.placeholder
        checks.append(
            ModelProbeCheck(
                "skill_compiler",
                compiler_ok,
                "valid_skill" if compiler_ok else (artifact.failure or "invalid_skill"),
            )
        )
    except Exception as exc:  # external probe boundary
        checks.append(ModelProbeCheck("skill_compiler", False, exc.__class__.__name__))

    return ModelProbeReport(tuple(checks))


__all__ = [
    "ModelProbeCheck",
    "ModelProbeReport",
    "run_model_service_probe",
]
