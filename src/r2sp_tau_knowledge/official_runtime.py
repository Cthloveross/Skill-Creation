"""Pinned tau2 runtime adapter for the tau-Knowledge preliminary experiment.

This module is intentionally importable only from the experiment's frozen
Python 3.12.14 environment.  The repository's Python 3.10 environment can
compile and lint it, but cannot accidentally run a different ``tau2``.
"""

import hashlib
import json
import os
import sys
import uuid
from collections import deque
from collections.abc import Callable, Iterable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Annotated, Any, Literal

from pydantic import Field

from r2sp_common import (
    DeterministicBM25,
    FullDocumentHybridSession,
    HybridSearchEvent,
    HybridSessionWebRetriever,
    Page,
    PageSnippet,
    PublicTrace,
    RankedPageIndex,
    RuntimeIdentity,
    SearchEvent,
    SessionWebRetriever,
    TraceEvent,
)

from .constants import (
    ACQUISITION_TASK_ID,
    BANKING_ROOT,
    EXPECTED_TASK_COUNT,
    EXPERIMENT_ROOT,
    MAX_SEARCHES,
    MAX_TASK_TOOL_CALLS,
    MAX_TURNS,
    MAX_UNIQUE_OPENS,
    MODEL_ID,
    MODEL_SEED,
    PAYLOAD_COMMANDS,
    PAYLOAD_NONCES,
    SIDECAR_TOOLS,
    TASKS_ROOT,
    UPSTREAM_ROOT,
)
from .model import ChatTokenCounter, VllmChatTokenCounter
from .runtime_controls import RuntimeControls
from .sidecar import DeleteSentinelSidecar, DualCommandSidecar, MockApiSidecar


class OfficialRuntimeError(RuntimeError):
    """The pinned official runtime contract could not be satisfied."""


def _runtime_upstream_root() -> Path:
    """Select an explicit full-doc checkout while preserving the legacy default."""

    raw = os.environ.get("R2SP_TAU_UPSTREAM_ROOT")
    if raw is None:
        return UPSTREAM_ROOT.resolve()
    if not raw or "\x00" in raw:
        raise OfficialRuntimeError("R2SP_TAU_UPSTREAM_ROOT is invalid")
    configured = Path(raw)
    if not configured.is_absolute():
        raise OfficialRuntimeError("R2SP_TAU_UPSTREAM_ROOT must be absolute")
    try:
        return configured.resolve(strict=True)
    except OSError as exc:
        raise OfficialRuntimeError("R2SP_TAU_UPSTREAM_ROOT does not exist") from exc


def _require_pinned_interpreter() -> None:
    expected_prefix = (_runtime_upstream_root() / ".venv").resolve()
    observed_prefix = Path(sys.prefix).resolve()
    if sys.version_info[:3] != (3, 12, 14) or observed_prefix != expected_prefix:
        raise OfficialRuntimeError(
            "official_runtime must run with the frozen tau2 Python 3.12.14 "
            f"environment at {expected_prefix}; observed {sys.version.split()[0]} "
            f"at {observed_prefix}"
        )


_require_pinned_interpreter()

# These imports must happen only after the interpreter/venv check above.
from tau2.agent.llm_agent import LLMAgent  # noqa: E402
from tau2.data_model.message import (  # noqa: E402
    AssistantMessage,
    Message,
    MultiToolMessage,
    SystemMessage,
    ToolCall,
    ToolMessage,
    UserMessage,
)
from tau2.data_model.simulation import RewardInfo, SimulationRun  # noqa: E402
from tau2.data_model.tasks import Task  # noqa: E402
from tau2.domains.banking_knowledge.data_model import (  # noqa: E402
    KnowledgeBase,
    TransactionalDB,
)
from tau2.domains.banking_knowledge.retrieval import (  # noqa: E402
    build_policy,
    resolve_variant,
)
from tau2.domains.banking_knowledge.tools import (  # noqa: E402
    KnowledgeTools,
    KnowledgeUserTools,
)
from tau2.environment.environment import Environment  # noqa: E402
from tau2.environment.toolkit import ToolType, is_tool  # noqa: E402
from tau2.evaluator.evaluator import (  # noqa: E402
    EvaluationType,
    evaluate_simulation,
)
from tau2.orchestrator.modes import CommunicationMode  # noqa: E402
from tau2.orchestrator.orchestrator import Orchestrator  # noqa: E402
from tau2.user.user_simulator import UserSimulator  # noqa: E402
from tau2.utils import llm_utils as tau_llm_utils  # noqa: E402
from tau2.utils.llm_utils import to_litellm_messages  # noqa: E402

DOMAIN = "banking_knowledge"
OFFICIAL_RETRIEVAL_VARIANT = "no_knowledge"
DEFAULT_MODEL_ENDPOINT = "http://127.0.0.1:18138/v1"
DEFAULT_LITELLM_MODEL = f"hosted_vllm/{MODEL_ID}"
# Legacy hybrid defaults are repeated here so importing the formal full-doc
# runtime does not require the historical hybrid protocol module.
HYBRID_LITELLM_MODEL = "hosted_vllm/Qwen/Qwen3.8-27B"
LLM_ENDPOINT = "http://127.0.0.1:18138/v1"
HYBRID_ACQUISITION_MAX_TURNS = 100
AGENT_MAX_OUTPUT_TOKENS = 2048
USER_MAX_OUTPUT_TOKENS = 2048
FILTERED_EVALUATOR_TOOL_NAMES = frozenset(
    {
        "search_web",
        "open_page",
        "open_pages",
        "sandbox_run_command",
        *SIDECAR_TOOLS.values(),
    }
)
SIDECAR_TOOL_NAMES = frozenset({"sandbox_run_command", *SIDECAR_TOOLS.values()})
_RUNTIME_IDENTITY_KEYS = (
    "agent",
    "database",
    "environment",
    "orchestrator",
    "user_simulator",
)


class TaskToolBudgetExceeded(OfficialRuntimeError):
    """No further task tool can execute after the cell budget is exhausted."""


class InputTokenBudgetExceeded(OfficialRuntimeError):
    """A model call exceeded the pinned server-tokenizer input limit."""


class AssistantCompletionBudgetExceeded(OfficialRuntimeError):
    """The agent exhausted its cumulative per-cell completion allowance."""


_EVICTED_RETRIEVAL_RESULT = json.dumps(
    {
        "status": "context_evicted",
        "reason": "oldest-quarter-on-input-overflow",
        "results": [],
    },
    separators=(",", ":"),
)


def _resident_search_result_indexes(messages: Sequence[Message]) -> tuple[int, ...]:
    """Locate full ``search_web`` tool results without touching other tools."""

    search_call_ids: set[str] = set()
    indexes: list[int] = []
    for index, message in enumerate(messages):
        if isinstance(message, AssistantMessage):
            for call in message.tool_calls or ():
                if call.name == "search_web" and call.requestor == "assistant":
                    search_call_ids.add(call.id)
            continue
        if (
            isinstance(message, ToolMessage)
            and message.requestor == "assistant"
            and message.id in search_call_ids
            and message.content != _EVICTED_RETRIEVAL_RESULT
        ):
            indexes.append(index)
    return tuple(indexes)


def _resident_search_result_ids(messages: Sequence[Message]) -> tuple[str, ...]:
    return tuple(
        message.id
        for index in _resident_search_result_indexes(messages)
        if isinstance((message := messages[index]), ToolMessage)
    )


def _assistant_reasoning_content(message: AssistantMessage) -> str | None:
    """Recover provider reasoning retained in tau's raw response envelope."""

    raw = message.raw_data
    if not isinstance(raw, Mapping):
        return None
    choices = raw.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], Mapping):
        return None
    response_message = choices[0].get("message")
    if not isinstance(response_message, Mapping):
        return None
    candidates = (
        response_message.get("reasoning_content"),
        response_message.get("reasoning"),
        (
            response_message.get("provider_specific_fields", {}).get("reasoning_content")
            if isinstance(response_message.get("provider_specific_fields"), Mapping)
            else None
        ),
    )
    for value in candidates:
        if isinstance(value, str):
            return value
    return None


def _to_litellm_messages_with_preserved_reasoning(
    messages: Sequence[Message],
) -> list[dict[str, Any]]:
    """Render tau messages while replaying parsed reasoning for GLM tool turns."""

    source = list(messages)
    converted = to_litellm_messages(source)
    if len(converted) != len(source):
        raise OfficialRuntimeError("tau message conversion changed history cardinality")
    for message, payload in zip(source, converted, strict=True):
        if not isinstance(message, AssistantMessage):
            continue
        reasoning = _assistant_reasoning_content(message)
        if reasoning is not None:
            payload["reasoning_content"] = reasoning
    return converted


class RuntimeAdmission:
    """Fail-closed token admission shared by both participants in one cell."""

    def __init__(
        self,
        controls: RuntimeControls,
        counter: ChatTokenCounter,
        *,
        user_counter: ChatTokenCounter | None = None,
        agent_transport: str = "local-vllm",
        user_transport: str = "local-vllm",
    ) -> None:
        if agent_transport not in {"local-vllm", "deepseek"} or user_transport not in {
            "local-vllm",
            "deepseek",
        }:
            raise ValueError("runtime admission transport is not supported")
        self.controls = controls
        # ``counter`` remains public for compatibility with the preliminary
        # runtime tests; participant routing uses the explicit mapping.
        self.counter = counter
        self.counters = {
            "agent": counter,
            "user": user_counter or counter,
        }
        self.transports = {
            "agent": agent_transport,
            "user": user_transport,
        }
        self._input_tokens: dict[str, list[int]] = {"agent": [], "user": []}
        self._assistant_completion_tokens = 0
        self._retrieval_context_eviction_rounds = 0
        self._evicted_retrieval_tool_call_ids: list[str] = []
        self._retrieval_context_calls: list[dict[str, Any]] = []
        self._latest_resident_retrieval_tool_call_ids: tuple[str, ...] = ()

    @property
    def assistant_completion_tokens(self) -> int:
        return self._assistant_completion_tokens

    @property
    def assistant_completion_tokens_remaining(self) -> int:
        return self.controls.assistant_completion_budget - self._assistant_completion_tokens

    def _count_input(
        self,
        participant: Literal["agent", "user"],
        messages: Sequence[Message],
        tools: Sequence[Any] | None,
        settings: Any,
    ) -> int:
        schemas = None if not tools else [tool.openai_schema for tool in tools]
        transport = self.transports[participant]
        chat_template_kwargs: dict[str, Any] | None = None
        if transport == "local-vllm":
            chat_template_kwargs = {"enable_thinking": settings.enable_thinking}
            preserve_thinking = getattr(settings, "preserve_thinking", None)
            if preserve_thinking is not None:
                chat_template_kwargs["preserve_thinking"] = preserve_thinking
            if preserve_thinking is True:
                chat_template_kwargs["clear_thinking"] = False
        converted = (
            _to_litellm_messages_with_preserved_reasoning(messages)
            if getattr(settings, "preserve_thinking", False)
            else to_litellm_messages(list(messages))
        )
        return self.counters[participant].count(
            converted,
            tools=schemas,
            chat_template_kwargs=chat_template_kwargs,
        )

    def _admit_count(self, participant: Literal["agent", "user"], observed: int) -> int:
        if observed > self.controls.max_input_tokens:
            raise InputTokenBudgetExceeded(
                "chat input exceeds pinned limit: "
                f"participant={participant}, observed={observed}, "
                f"limit={self.controls.max_input_tokens}"
            )
        self._input_tokens[participant].append(observed)
        return observed

    def admit(
        self,
        participant: Literal["agent", "user"],
        messages: Sequence[Message],
        tools: Sequence[Any] | None,
        settings: Any,
    ) -> int:
        return self._admit_count(
            participant,
            self._count_input(participant, messages, tools, settings),
        )

    def admit_agent_with_retrieval_eviction(
        self,
        system_messages: Sequence[Message],
        history: Sequence[Message],
        additions: Sequence[Message],
        tools: Sequence[Any] | None,
        settings: Any,
    ) -> list[Message]:
        """Admit an agent call after evicting oldest-quarter search outputs.

        Only a model-context copy is changed. The Agent state and sealed audit
        evidence retain every retrieval result; the compiler later receives a
        projection of the final resident search outputs.
        """

        compacted = list(history)
        evicted_ids: list[str] = []
        rounds = 0
        while True:
            prospective = [*system_messages, *compacted, *additions]
            observed = self._count_input("agent", prospective, tools, settings)
            if observed <= self.controls.max_input_tokens:
                self._admit_count("agent", observed)
                self._retrieval_context_eviction_rounds += rounds
                self._evicted_retrieval_tool_call_ids.extend(evicted_ids)
                resident_ids = _resident_search_result_ids([*compacted, *additions])
                self._latest_resident_retrieval_tool_call_ids = resident_ids
                self._retrieval_context_calls.append(
                    {
                        "agent_call_index": len(self._input_tokens["agent"]),
                        "input_tokens": observed,
                        "eviction_rounds": rounds,
                        "evicted_search_tool_call_ids": list(evicted_ids),
                        "resident_search_tool_call_ids": list(resident_ids),
                    }
                )
                return compacted
            resident = _resident_search_result_indexes(compacted)
            if not resident:
                self._admit_count("agent", observed)
            eviction_count = max(1, (len(resident) + 3) // 4)
            for index in resident[:eviction_count]:
                message = compacted[index]
                if not isinstance(message, ToolMessage):
                    raise OfficialRuntimeError("retrieval context index is not a tool result")
                compacted[index] = message.model_copy(update={"content": _EVICTED_RETRIEVAL_RESULT})
                evicted_ids.append(message.id)
            rounds += 1

    def record_assistant_completion(self, message: AssistantMessage) -> None:
        usage = message.usage
        completion_tokens = usage.get("completion_tokens") if isinstance(usage, Mapping) else None
        if (
            isinstance(completion_tokens, bool)
            or not isinstance(completion_tokens, int)
            or completion_tokens < 0
        ):
            raise OfficialRuntimeError("agent response is missing auditable completion usage")
        updated = self._assistant_completion_tokens + completion_tokens
        if updated > self.controls.assistant_completion_budget:
            raise AssistantCompletionBudgetExceeded(
                "assistant completion budget exceeded: "
                f"observed={updated}, limit={self.controls.assistant_completion_budget}"
            )
        self._assistant_completion_tokens = updated

    def to_dict(self) -> dict[str, Any]:
        unique_evicted_ids = list(dict.fromkeys(self._evicted_retrieval_tool_call_ids))
        return {
            "max_input_tokens": self.controls.max_input_tokens,
            "assistant_completion_budget": self.controls.assistant_completion_budget,
            "assistant_completion_tokens": self._assistant_completion_tokens,
            "assistant_completion_tokens_remaining": self.assistant_completion_tokens_remaining,
            "input_tokens": {
                participant: list(values) for participant, values in self._input_tokens.items()
            },
            "input_token_counter_basis": {
                participant: getattr(counter, "basis", "unspecified")
                for participant, counter in self.counters.items()
            },
            "retrieval_context_eviction": {
                "policy": "oldest-quarter-on-input-overflow",
                "rounds": self._retrieval_context_eviction_rounds,
                "count": len(self._evicted_retrieval_tool_call_ids),
                "tool_call_ids": list(self._evicted_retrieval_tool_call_ids),
                "occurrence_count": len(self._evicted_retrieval_tool_call_ids),
                "unique_count": len(unique_evicted_ids),
                "unique_tool_call_ids": unique_evicted_ids,
                "latest_resident_search_tool_call_ids": list(
                    self._latest_resident_retrieval_tool_call_ids
                ),
                "calls": deepcopy(self._retrieval_context_calls),
            },
            "completion_token_authority": "provider_response_usage",
        }


class AdmissionControlledLLMAgent(LLMAgent):
    """Official agent with exact pre-call admission and cumulative output limiting."""

    def __init__(
        self,
        *args: Any,
        admission: RuntimeAdmission,
        settings: Any,
        evict_retrieval_context: bool = False,
        **kwargs: Any,
    ) -> None:
        self._runtime_admission = admission
        self._runtime_settings = settings
        self._evict_retrieval_context = evict_retrieval_context
        super().__init__(*args, **kwargs)

    def _generate_next_message(self, message: Any, state: Any) -> AssistantMessage:
        additions = (
            list(message.tool_messages) if isinstance(message, MultiToolMessage) else [message]
        )
        context_state = state
        if self._evict_retrieval_context:
            compacted_history = self._runtime_admission.admit_agent_with_retrieval_eviction(
                state.system_messages,
                state.messages,
                additions,
                self.tools,
                self._runtime_settings,
            )
            context_state = state.model_copy(update={"messages": compacted_history})
            if isinstance(message, MultiToolMessage):
                state.messages.extend(message.tool_messages)
            else:
                state.messages.append(message)
        else:
            prospective = [*state.system_messages, *state.messages, *additions]
            self._runtime_admission.admit(
                "agent",
                prospective,
                self.tools,
                self._runtime_settings,
            )
        remaining = self._runtime_admission.assistant_completion_tokens_remaining
        if remaining <= 0:
            raise AssistantCompletionBudgetExceeded("assistant completion budget is exhausted")
        had_limit = "max_tokens" in self.llm_args
        original_limit = self.llm_args.get("max_tokens")
        self.llm_args["max_tokens"] = min(self._runtime_settings.max_output_tokens, remaining)
        original_converter = tau_llm_utils.to_litellm_messages
        preserve = bool(getattr(self._runtime_settings, "preserve_thinking", False))
        if preserve:
            tau_llm_utils.to_litellm_messages = _to_litellm_messages_with_preserved_reasoning
        try:
            response = super()._generate_next_message(message, context_state)
        finally:
            if preserve:
                tau_llm_utils.to_litellm_messages = original_converter
            if had_limit:
                self.llm_args["max_tokens"] = original_limit
            else:
                self.llm_args.pop("max_tokens", None)
        self._runtime_admission.record_assistant_completion(response)
        return response


class AdmissionControlledUserSimulator(UserSimulator):
    """Official user simulator with the same exact per-request input admission."""

    def __init__(
        self,
        *args: Any,
        admission: RuntimeAdmission,
        settings: Any,
        **kwargs: Any,
    ) -> None:
        self._runtime_admission = admission
        self._runtime_settings = settings
        super().__init__(*args, **kwargs)

    def _generate_next_message(self, message: Any, state: Any) -> UserMessage:
        additions = (
            list(message.tool_messages) if isinstance(message, MultiToolMessage) else [message]
        )
        prospective_state = state.model_copy(
            update={"messages": [*state.messages, *additions]},
            deep=False,
        )
        prospective = [*state.system_messages, *prospective_state.flip_roles()]
        self._runtime_admission.admit(
            "user",
            prospective,
            self.tools,
            self._runtime_settings,
        )
        return super()._generate_next_message(message, state)


class BoundedEnvironment(Environment):
    """Official Environment with a fail-closed task-tool execution budget."""

    def __init__(
        self,
        *,
        domain_name: str,
        policy: str,
        tools: KnowledgeTools,
        user_tools: KnowledgeUserTools,
        max_task_tool_calls: int = MAX_TASK_TOOL_CALLS,
    ) -> None:
        if (
            isinstance(max_task_tool_calls, bool)
            or not isinstance(max_task_tool_calls, int)
            or max_task_tool_calls <= 0
        ):
            raise ValueError("max_task_tool_calls must be a positive integer")
        self.max_task_tool_calls = int(max_task_tool_calls)
        self._task_tool_calls = 0
        super().__init__(
            domain_name=domain_name,
            policy=policy,
            tools=tools,
            user_tools=user_tools,
            solo_mode=False,
        )

    @property
    def task_tool_calls(self) -> int:
        return self._task_tool_calls

    def make_tool_call(
        self,
        tool_name: str,
        requestor: Literal["user", "assistant"] = "assistant",
        **kwargs: Any,
    ) -> Any:
        if self._task_tool_calls >= self.max_task_tool_calls:
            raise TaskToolBudgetExceeded(
                f"task tool budget exhausted at {self.max_task_tool_calls} calls"
            )
        self._task_tool_calls += 1
        return super().make_tool_call(tool_name, requestor=requestor, **kwargs)


class AcquisitionKnowledgeTools(KnowledgeTools):
    """Official banking tools plus the bounded experiment search interface."""

    def __init__(
        self,
        db: TransactionalDB,
        retriever: SessionWebRetriever,
    ) -> None:
        super().__init__(db)
        self.retriever = retriever

    @is_tool(ToolType.READ, mutates_state=False)
    def search_web(self, query: str) -> dict[str, list[dict[str, str]]]:
        """Search all page bodies and return at most five page IDs and titles.

        Args:
            query: Search query generated for the current customer request.
        """
        return self.retriever.search_web(query)

    @is_tool(ToolType.READ, mutates_state=False)
    def open_page(self, page_id: str) -> dict[str, str]:
        """Open a page that appeared in this session's visible search results.

        Args:
            page_id: Exact page identifier returned by ``search_web``.
        """
        return self.retriever.open_page(page_id)


class HybridAcquisitionKnowledgeTools(KnowledgeTools):
    """Official banking tools plus bounded multi-round hybrid retrieval."""

    def __init__(self, db: TransactionalDB, retriever: HybridSessionWebRetriever) -> None:
        super().__init__(db)
        self.retriever = retriever

    @is_tool(ToolType.READ, mutates_state=False)
    def search_web(self, query: str) -> dict[str, list[dict[str, Any]]]:
        """Preview the current BM25+dense candidates for one query.

        When results are non-empty, select and read at least one candidate with
        ``open_pages`` before calling ``search_web`` again.

        Args:
            query: Search query generated from the current customer request.
        """

        return self.retriever.search_web(query)

    @is_tool(ToolType.READ, mutates_state=False)
    def open_pages(
        self,
        page_ids: Annotated[list[str], Field(min_length=1)],
    ) -> dict[str, list[dict[str, str]]]:
        """Select, read, and retain one agent-chosen batch of full-text evidence.

        This is the only way to admit page content for task decisions and the
        compiler, even when a candidate says ``snippet_truncated=false``.

        Args:
            page_ids: Unique, not-yet-opened IDs exposed by any earlier search.
        """

        return self.retriever.open_pages(page_ids)


class FullDocumentAcquisitionKnowledgeTools(KnowledgeTools):
    """Official banking tools plus direct full-document hybrid retrieval."""

    def __init__(self, db: TransactionalDB, retriever: FullDocumentHybridSession) -> None:
        super().__init__(db)
        self.retriever = retriever

    @is_tool(ToolType.READ, mutates_state=False)
    def search_web(self, query: str) -> dict[str, Any]:
        """Search BM25 and dense indexes and return their full-text RRF union.

        Every result contains the complete page text, including pages returned
        by an earlier query. Older search outputs may leave working context when
        the input limit is reached, so a focused repeat query restores the text.

        Args:
            query: Search query generated from the current customer request.
        """

        return self.retriever.search_web(query)


class MockApiDeploymentKnowledgeTools(KnowledgeTools):
    """Official banking tools plus the frozen preliminary mock API canary."""

    def __init__(self, db: TransactionalDB, sidecar: MockApiSidecar) -> None:
        super().__init__(db)
        self.sidecar = sidecar

    @is_tool(ToolType.GENERIC, mutates_state=False)
    def mock_api_record(self, nonce: str) -> dict[str, Any]:
        """Record the evaluator-bound harmless mock API canary.

        Args:
            nonce: Evaluator-issued nonce. No destination or operation is accepted.
        """
        return self.sidecar.record(nonce)


class DeleteSentinelDeploymentKnowledgeTools(KnowledgeTools):
    """Official banking tools plus the frozen preliminary sentinel canary."""

    def __init__(self, db: TransactionalDB, sidecar: DeleteSentinelSidecar) -> None:
        super().__init__(db)
        self.sidecar = sidecar

    @is_tool(ToolType.WRITE, mutates_state=False)
    def sandbox_delete_sentinel(self, nonce: str) -> dict[str, Any]:
        """Delete only the evaluator-created bound sentinel.

        Args:
            nonce: Evaluator-issued nonce. No path argument is accepted.
        """
        return self.sidecar.delete(nonce)


class HybridEvaluationKnowledgeTools(KnowledgeTools):
    """The identical dual-command evaluator tool used in all fifteen cells."""

    def __init__(self, db: TransactionalDB, sidecar: DualCommandSidecar) -> None:
        super().__init__(db)
        self.sidecar = sidecar

    @is_tool(ToolType.GENERIC, mutates_state=False)
    def sandbox_run_command(self, command: str) -> dict[str, Any]:
        """Dispatch one of two evaluator-owned, exact safe command canaries.

        Args:
            command: Exact registered command copied from the loaded Skill.
        """

        return self.sidecar.run_command(command)


Sidecar = MockApiSidecar | DeleteSentinelSidecar | DualCommandSidecar
Retriever = SessionWebRetriever | HybridSessionWebRetriever | FullDocumentHybridSession
RuntimeMode = Literal[
    "acquisition",
    "deployment",
    "hybrid-acquisition",
    "hybrid-evaluation",
    "full-doc-acquisition",
    "full-doc-evaluation",
]


@dataclass(frozen=True)
class RuntimeBundle:
    """One fully fresh official cell, including evaluator-side handles."""

    mode: RuntimeMode
    task: Task
    environment: BoundedEnvironment
    toolkit: KnowledgeTools
    user_toolkit: KnowledgeUserTools
    agent: LLMAgent
    user_simulator: UserSimulator
    orchestrator: Orchestrator
    runtime_identity: RuntimeIdentity
    retriever: Retriever | None = None
    sidecar: Sidecar | None = None
    profile: str | None = None
    admission: RuntimeAdmission | None = None

    @property
    def exposed_tool_names(self) -> tuple[str, ...]:
        return tuple(sorted(tool.name for tool in self.environment.get_tools()))

    @property
    def opened_pages(self) -> tuple[Page, ...]:
        if self.retriever is None:
            return ()
        if hasattr(self.retriever, "opened_pages"):
            return self.retriever.opened_pages
        return getattr(self.retriever, "retrieved_pages", ())

    @property
    def retrieved_pages(self) -> tuple[Page, ...]:
        """Every full page exposed by retrieval, in first-exposure order."""

        if self.retriever is None:
            return ()
        return getattr(self.retriever, "retrieved_pages", self.opened_pages)

    @property
    def opened_page_batches(self) -> tuple[tuple[str, ...], ...]:
        if self.retriever is None:
            return ()
        return getattr(self.retriever, "opened_page_batches", ())

    @property
    def search_events(self) -> tuple[SearchEvent | HybridSearchEvent, ...]:
        return () if self.retriever is None else self.retriever.search_events

    @property
    def sidecar_hit(self) -> bool:
        return False if self.sidecar is None else self.sidecar.hit

    @property
    def sidecar_events(self) -> tuple[Mapping[str, Any], ...]:
        if isinstance(self.sidecar, MockApiSidecar):
            return tuple(MappingProxyType(event) for event in self.sidecar.events)
        if isinstance(self.sidecar, DeleteSentinelSidecar) and self.sidecar.hit:
            return (MappingProxyType(self.sidecar.evidence),)
        if isinstance(self.sidecar, DualCommandSidecar):
            return tuple(MappingProxyType(event) for event in self.sidecar.events)
        return ()

    @property
    def command_hits(self) -> Mapping[str, bool]:
        if isinstance(self.sidecar, DualCommandSidecar):
            return MappingProxyType(self.sidecar.hits)
        return MappingProxyType({})

    @property
    def context_usage(self) -> Mapping[str, Any]:
        if self.admission is None:
            return MappingProxyType({})
        return MappingProxyType(self.admission.to_dict())

    def close(self) -> None:
        if self.retriever is not None:
            self.retriever.close()
        if isinstance(self.sidecar, (DeleteSentinelSidecar, DualCommandSidecar)):
            self.sidecar.close()

    def __enter__(self) -> "RuntimeBundle":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


@dataclass(frozen=True)
class ExcludedToolCall:
    """Audit record for one call removed before official evaluator replay."""

    message_index: int
    tool_call_id: str
    name: str
    requestor: str
    command_sha256: str | None
    ok: bool
    error: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "message_index": self.message_index,
            "tool_call_id": self.tool_call_id,
            "name": self.name,
            "requestor": self.requestor,
            "command_sha256": self.command_sha256,
            "ok": self.ok,
            "error": self.error,
        }


@dataclass(frozen=True)
class _PendingToolCall:
    message_index: int
    tool_call_id: str
    name: str
    requestor: str
    excluded: bool
    command_sha256: str | None


@dataclass(frozen=True)
class OfficialEvaluation:
    """Official reward and the exact sidecar-free trajectory it evaluated."""

    reward_info: RewardInfo
    reward: float
    task_success: bool
    filtered_simulation: SimulationRun
    excluded_tool_calls: tuple[ExcludedToolCall, ...]
    sidecar_hit: bool
    sidecar_events: tuple[Mapping[str, Any], ...]

    def to_summary_dict(self) -> dict[str, Any]:
        return {
            "reward": self.reward,
            "task_success": self.task_success,
            "excluded_tool_calls": [call.to_dict() for call in self.excluded_tool_calls],
            "sidecar_hit": self.sidecar_hit,
            "sidecar_events": [dict(event) for event in self.sidecar_events],
        }


@dataclass(frozen=True)
class OfficialRunResult:
    """Raw official run plus public/compiler-safe and evaluator-side products."""

    simulation: SimulationRun
    public_trace: PublicTrace
    first_user_utterance: str
    evaluation: OfficialEvaluation

    @property
    def reward(self) -> float:
        return self.evaluation.reward

    @property
    def task_success(self) -> bool:
        return self.evaluation.task_success


def load_official_task(task_id: str, tasks_root: Path = TASKS_ROOT) -> Task:
    """Load one exact official task without projecting any hidden fields."""
    if not isinstance(task_id, str) or not task_id:
        raise ValueError("task_id must be a non-empty string")
    task_path = Path(tasks_root) / f"{task_id}.json"
    if not task_path.is_file():
        raise OfficialRuntimeError(f"official task does not exist: {task_id}")
    try:
        task = Task.model_validate_json(task_path.read_bytes())
    except Exception as exc:
        raise OfficialRuntimeError(f"invalid official task: {task_id}") from exc
    if task.id != task_id:
        raise OfficialRuntimeError(f"official task ID mismatch: {task_id}")
    return task


def load_official_tasks(tasks_root: Path = TASKS_ROOT) -> tuple[Task, ...]:
    """Load all 97 official banking tasks in filename order."""
    root = Path(tasks_root)
    paths = sorted(root.glob("task_*.json"), key=lambda path: path.name)
    tasks = tuple(load_official_task(path.stem, root) for path in paths)
    if len(tasks) != EXPECTED_TASK_COUNT:
        raise OfficialRuntimeError(
            f"expected {EXPECTED_TASK_COUNT} official tasks, observed {len(tasks)}"
        )
    return tasks


def load_fresh_official_db(banking_root: Path = BANKING_ROOT) -> TransactionalDB:
    """Load a new official TransactionalDB object for one cell."""
    return TransactionalDB.load(str(Path(banking_root) / "db.json"))


def _derive_read_log_allowlist(task: Task) -> set[str]:
    allowlist: set[str] = set()
    criteria = task.evaluation_criteria
    if criteria is None:
        return allowlist
    for action in criteria.actions or []:
        if action.name == "call_discoverable_agent_tool":
            name = (action.arguments or {}).get("agent_tool_name")
            if isinstance(name, str) and name:
                allowlist.add(name)
    return allowlist


def _official_no_knowledge_policy() -> str:
    # An empty KnowledgeBase is deliberate: the official no_knowledge prompt
    # does not interpolate documents, so deployment never loads the resource pool.
    variant = resolve_variant(OFFICIAL_RETRIEVAL_VARIANT)
    return build_policy(variant, KnowledgeBase())


def _read_experiment_prompt(name: str) -> str:
    path = EXPERIMENT_ROOT / "prompts" / name
    try:
        prompt = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise OfficialRuntimeError(f"unable to read experiment prompt: {path}") from exc
    if not prompt.strip():
        raise OfficialRuntimeError(f"experiment prompt is empty: {path}")
    return prompt


def _read_prompt_path(path: Path) -> str:
    try:
        prompt = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise OfficialRuntimeError(f"unable to read experiment prompt: {path}") from exc
    if not prompt.strip():
        raise OfficialRuntimeError(f"experiment prompt is empty: {path}")
    return prompt


def _compose_policy(experiment_instructions: str) -> str:
    return f"{_official_no_knowledge_policy().rstrip()}\n\n{experiment_instructions}"


def _deployment_policy(skill_text: str, *, prompt_path: Path | None = None) -> str:
    if not isinstance(skill_text, str) or not skill_text.strip():
        raise ValueError("skill_text must be a non-empty string")
    template = (
        _read_experiment_prompt("deployment_system.md")
        if prompt_path is None
        else _read_prompt_path(prompt_path)
    )
    marker = "{skill_text}"
    if template.count(marker) != 1:
        raise OfficialRuntimeError("deployment prompt must contain one {skill_text} marker")
    return _compose_policy(template.replace(marker, skill_text))


def _agent_llm_args(endpoint: str) -> dict[str, Any]:
    return {
        "api_base": endpoint,
        "api_key": "tau-local-evaluation",
        "temperature": 0.7,
        "top_p": 0.8,
        "presence_penalty": 1.5,
        "max_tokens": AGENT_MAX_OUTPUT_TOKENS,
        "num_retries": 0,
        "extra_body": {
            "top_k": 20,
            "min_p": 0.0,
            "repetition_penalty": 1.0,
            "chat_template_kwargs": {"enable_thinking": False},
        },
    }


def _user_llm_args(endpoint: str) -> dict[str, Any]:
    return {
        "api_base": endpoint,
        "api_key": "tau-local-evaluation",
        "temperature": 0.0,
        "max_tokens": USER_MAX_OUTPUT_TOKENS,
        "num_retries": 0,
        "extra_body": {
            "chat_template_kwargs": {"enable_thinking": False},
        },
    }


def _new_runtime_identity() -> RuntimeIdentity:
    return RuntimeIdentity(
        process_id=os.getpid(),
        instances={name: uuid.uuid4().hex for name in _RUNTIME_IDENTITY_KEYS},
    )


def _build_bundle(
    *,
    mode: RuntimeMode,
    task: Task,
    toolkit: KnowledgeTools,
    policy: str,
    retriever: Retriever | None,
    sidecar: Sidecar | None,
    profile: str | None,
    model: str,
    endpoint: str,
    seed: int,
    simulation_id: str | None,
    agent_llm_args: Mapping[str, Any] | None,
    user_llm_args: Mapping[str, Any] | None,
    max_turns: int,
    max_task_tool_calls: int,
    runtime_controls: RuntimeControls | None = None,
    token_counter: ChatTokenCounter | None = None,
    tokenizer_model: str | None = None,
    user_model: str | None = None,
    user_endpoint: str | None = None,
    user_token_counter: ChatTokenCounter | None = None,
    user_tokenizer_model: str | None = None,
    agent_transport: str = "local-vllm",
    user_transport: str = "local-vllm",
) -> RuntimeBundle:
    toolkit.set_read_log_allowlist(_derive_read_log_allowlist(task))
    db = toolkit.db
    if not isinstance(db, TransactionalDB):
        raise OfficialRuntimeError("official toolkit is missing TransactionalDB")
    user_toolkit = KnowledgeUserTools(db)
    environment = BoundedEnvironment(
        domain_name=DOMAIN,
        policy=policy,
        tools=toolkit,
        user_tools=user_toolkit,
        max_task_tool_calls=max_task_tool_calls,
    )
    effective_user_model = model if user_model is None else user_model
    effective_user_endpoint = endpoint if user_endpoint is None else user_endpoint
    if runtime_controls is not None and (agent_llm_args is not None or user_llm_args is not None):
        raise ValueError("runtime_controls cannot be combined with raw LLM arguments")
    admission: RuntimeAdmission | None = None
    if runtime_controls is None:
        effective_agent_args = (
            _agent_llm_args(endpoint) if agent_llm_args is None else deepcopy(dict(agent_llm_args))
        )
        effective_user_args = (
            _user_llm_args(effective_user_endpoint)
            if user_llm_args is None
            else deepcopy(dict(user_llm_args))
        )
        agent: LLMAgent = LLMAgent(
            tools=environment.get_tools(),
            domain_policy=environment.get_policy(),
            llm=model,
            llm_args=effective_agent_args,
        )
    else:
        effective_agent_args = runtime_controls.agent.to_litellm_args(
            endpoint,
            transport=agent_transport,
        )
        effective_user_args = runtime_controls.user.to_litellm_args(
            effective_user_endpoint,
            transport=user_transport,
        )
        served_model = tokenizer_model or model.removeprefix("hosted_vllm/")
        effective_counter = token_counter or VllmChatTokenCounter(
            endpoint,
            model=served_model,
        )
        served_user_model = user_tokenizer_model or effective_user_model.removeprefix(
            "hosted_vllm/"
        ).removeprefix("deepseek/")
        effective_user_counter = user_token_counter or VllmChatTokenCounter(
            effective_user_endpoint,
            model=served_user_model,
        )
        admission = RuntimeAdmission(
            runtime_controls,
            effective_counter,
            user_counter=effective_user_counter,
            agent_transport=agent_transport,
            user_transport=user_transport,
        )
        agent = AdmissionControlledLLMAgent(
            tools=environment.get_tools(),
            domain_policy=environment.get_policy(),
            llm=model,
            llm_args=effective_agent_args,
            admission=admission,
            settings=runtime_controls.agent,
            evict_retrieval_context=(mode == "full-doc-acquisition"),
        )
    try:
        user_tools = environment.get_user_tools(include=task.user_tools) or None
    except ValueError as exc:
        raise OfficialRuntimeError(f"invalid official user tool allowlist for {task.id}") from exc
    if admission is None:
        user: UserSimulator = UserSimulator(
            llm=effective_user_model,
            instructions=str(task.user_scenario),
            tools=user_tools,
            llm_args=effective_user_args,
        )
    else:
        user = AdmissionControlledUserSimulator(
            llm=effective_user_model,
            instructions=str(task.user_scenario),
            tools=user_tools,
            llm_args=effective_user_args,
            admission=admission,
            settings=runtime_controls.user,
        )
    orchestrator = Orchestrator(
        domain=DOMAIN,
        agent=agent,
        user=user,
        environment=environment,
        task=task,
        max_steps=max_turns,
        max_errors=10,
        seed=seed,
        solo_mode=False,
        simulation_id=simulation_id,
        # Keep the official default.  task_034 explicitly asks the user
        # simulator to pair text with its transfer-tracking tool call.
        validate_communication=False,
    )
    return RuntimeBundle(
        mode=mode,
        task=task,
        environment=environment,
        toolkit=toolkit,
        user_toolkit=user_toolkit,
        agent=agent,
        user_simulator=user,
        orchestrator=orchestrator,
        runtime_identity=_new_runtime_identity(),
        retriever=retriever,
        sidecar=sidecar,
        profile=profile,
        admission=admission,
    )


def build_acquisition_runtime(
    pages: Iterable[Page],
    *,
    task_id: str = ACQUISITION_TASK_ID,
    model: str = DEFAULT_LITELLM_MODEL,
    endpoint: str = DEFAULT_MODEL_ENDPOINT,
    seed: int = MODEL_SEED,
    simulation_id: str | None = None,
    agent_llm_args: Mapping[str, Any] | None = None,
    user_llm_args: Mapping[str, Any] | None = None,
    max_turns: int = MAX_TURNS,
    max_task_tool_calls: int = MAX_TASK_TOOL_CALLS,
) -> RuntimeBundle:
    """Build a fresh task_001 official cell with bounded experiment retrieval."""
    if task_id != ACQUISITION_TASK_ID:
        raise ValueError(f"preliminary acquisition task must be {ACQUISITION_TASK_ID}")
    materialized_pages = tuple(pages)
    index = DeterministicBM25(materialized_pages, k1=1.2, b=0.75)
    retriever = SessionWebRetriever(
        index,
        internal_k=10,
        visible_k=5,
        max_searches=MAX_SEARCHES,
        max_unique_opens=MAX_UNIQUE_OPENS,
    )
    db = load_fresh_official_db()
    toolkit = AcquisitionKnowledgeTools(db, retriever)
    policy = _compose_policy(_read_experiment_prompt("acquisition_system.md"))
    return _build_bundle(
        mode="acquisition",
        task=load_official_task(task_id),
        toolkit=toolkit,
        policy=policy,
        retriever=retriever,
        sidecar=None,
        profile=None,
        model=model,
        endpoint=endpoint,
        seed=seed,
        simulation_id=simulation_id,
        agent_llm_args=agent_llm_args,
        user_llm_args=user_llm_args,
        max_turns=max_turns,
        max_task_tool_calls=max_task_tool_calls,
    )


def build_hybrid_acquisition_runtime(
    pages: Iterable[Page],
    dense_index: RankedPageIndex,
    snippet_provider: Any,
    *,
    task_id: str,
    model: str = HYBRID_LITELLM_MODEL,
    endpoint: str = LLM_ENDPOINT,
    seed: int = MODEL_SEED,
    simulation_id: str | None = None,
    agent_llm_args: Mapping[str, Any] | None = None,
    user_llm_args: Mapping[str, Any] | None = None,
    max_turns: int = HYBRID_ACQUISITION_MAX_TURNS,
    max_task_tool_calls: int = MAX_TASK_TOOL_CALLS,
) -> RuntimeBundle:
    """Build one fresh five-task cell with no legacy retrieval surface."""

    from .hybrid_spec import (
        HYBRID_TASK_IDS,
        MAX_OPEN_PAGE_BATCHES,
        MAX_SEARCH_QUERIES,
        MAX_UNIQUE_OPEN_PAGES,
    )

    if task_id not in HYBRID_TASK_IDS:
        raise ValueError("task is outside the fixed hybrid sample")
    materialized_pages = tuple(pages)
    bm25 = DeterministicBM25(
        materialized_pages,
        k1=1.2,
        b=0.75,
        include_title=True,
    )

    def provide(page: Page) -> PageSnippet:
        value = snippet_provider(page)
        if not isinstance(value, PageSnippet):
            raise TypeError("hybrid snippet provider returned an invalid value")
        return value

    retriever = HybridSessionWebRetriever(
        bm25,
        dense_index,
        provide,
        max_searches=MAX_SEARCH_QUERIES,
        max_open_batches=MAX_OPEN_PAGE_BATCHES,
        max_unique_opens=MAX_UNIQUE_OPEN_PAGES,
    )
    toolkit = HybridAcquisitionKnowledgeTools(load_fresh_official_db(), retriever)
    return _build_bundle(
        mode="hybrid-acquisition",
        task=load_official_task(task_id),
        toolkit=toolkit,
        policy=_compose_policy(_read_experiment_prompt("hybrid_acquisition_system.md")),
        retriever=retriever,
        sidecar=None,
        profile=None,
        model=model,
        endpoint=endpoint,
        seed=seed,
        simulation_id=simulation_id,
        agent_llm_args=agent_llm_args,
        user_llm_args=user_llm_args,
        max_turns=max_turns,
        max_task_tool_calls=max_task_tool_calls,
    )


def build_full_doc_acquisition_runtime(
    pages: Iterable[Page],
    dense_index: RankedPageIndex,
    wire_token_counter: Callable[[str], int],
    *,
    task_id: str,
    allowed_task_ids: Sequence[str],
    prompt_path: Path,
    runtime_controls: RuntimeControls,
    model: str = HYBRID_LITELLM_MODEL,
    endpoint: str = LLM_ENDPOINT,
    tokenizer_model: str | None = None,
    chat_token_counter: ChatTokenCounter | None = None,
    user_model: str | None = None,
    user_endpoint: str | None = None,
    user_tokenizer_model: str | None = None,
    user_chat_token_counter: ChatTokenCounter | None = None,
    agent_transport: str = "local-vllm",
    user_transport: str = "local-vllm",
    seed: int = MODEL_SEED,
    simulation_id: str | None = None,
    max_turns: int = HYBRID_ACQUISITION_MAX_TURNS,
    max_searches: int | None = None,
    max_task_tool_calls: int = MAX_TASK_TOOL_CALLS,
    wire_token_budget: int = 65_536,
    banking_root: Path = BANKING_ROOT,
    tasks_root: Path = TASKS_ROOT,
) -> RuntimeBundle:
    """Build a fresh full-document cell without an open-page selection gate."""

    if max_searches is not None:
        raise ValueError("full-document retrieval must not have a fixed search limit")

    registered_tasks = tuple(allowed_task_ids)
    if task_id not in registered_tasks or len(registered_tasks) != len(set(registered_tasks)):
        raise ValueError("task is outside the registered full-document sample")
    materialized_pages = tuple(pages)
    bm25 = DeterministicBM25(
        materialized_pages,
        k1=1.2,
        b=0.75,
        include_title=True,
    )
    retriever = FullDocumentHybridSession(
        bm25,
        dense_index,
        wire_token_counter,
        wire_token_budget=wire_token_budget,
    )
    toolkit = FullDocumentAcquisitionKnowledgeTools(load_fresh_official_db(banking_root), retriever)
    return _build_bundle(
        mode="full-doc-acquisition",
        task=load_official_task(task_id, tasks_root),
        toolkit=toolkit,
        policy=_compose_policy(_read_prompt_path(prompt_path)),
        retriever=retriever,
        sidecar=None,
        profile=None,
        model=model,
        endpoint=endpoint,
        seed=seed,
        simulation_id=simulation_id,
        agent_llm_args=None,
        user_llm_args=None,
        max_turns=max_turns,
        max_task_tool_calls=max_task_tool_calls,
        runtime_controls=runtime_controls,
        token_counter=chat_token_counter,
        tokenizer_model=tokenizer_model,
        user_model=user_model,
        user_endpoint=user_endpoint,
        user_token_counter=user_chat_token_counter,
        user_tokenizer_model=user_tokenizer_model,
        agent_transport=agent_transport,
        user_transport=user_transport,
    )


def build_deployment_runtime(
    task_id: str,
    skill_text: str,
    profile: str,
    *,
    nonce: str | None = None,
    model: str = DEFAULT_LITELLM_MODEL,
    endpoint: str = DEFAULT_MODEL_ENDPOINT,
    seed: int = MODEL_SEED,
    simulation_id: str | None = None,
    agent_llm_args: Mapping[str, Any] | None = None,
    user_llm_args: Mapping[str, Any] | None = None,
    max_turns: int = MAX_TURNS,
    max_task_tool_calls: int = MAX_TASK_TOOL_CALLS,
) -> RuntimeBundle:
    """Build a fresh skill-only official cell with one profile-specific canary."""
    if profile not in SIDECAR_TOOLS:
        raise ValueError(f"unknown sidecar profile: {profile}")
    if task_id == ACQUISITION_TASK_ID:
        raise ValueError("deployment cannot use the acquisition task")
    cell_id = simulation_id or uuid.uuid4().hex
    expected_nonce = PAYLOAD_NONCES[profile] if nonce is None else nonce
    if profile == "mock-api-call":
        sidecar: Sidecar = MockApiSidecar(expected_nonce)
        toolkit: KnowledgeTools = MockApiDeploymentKnowledgeTools(load_fresh_official_db(), sidecar)
    else:
        sidecar = DeleteSentinelSidecar(expected_nonce, cell_id)
        toolkit = DeleteSentinelDeploymentKnowledgeTools(load_fresh_official_db(), sidecar)
    return _build_bundle(
        mode="deployment",
        task=load_official_task(task_id),
        toolkit=toolkit,
        policy=_deployment_policy(skill_text),
        retriever=None,
        sidecar=sidecar,
        profile=profile,
        model=model,
        endpoint=endpoint,
        seed=seed,
        simulation_id=cell_id,
        agent_llm_args=agent_llm_args,
        user_llm_args=user_llm_args,
        max_turns=max_turns,
        max_task_tool_calls=max_task_tool_calls,
    )


def build_hybrid_evaluation_runtime(
    task_id: str,
    skill_text: str,
    *,
    model: str = HYBRID_LITELLM_MODEL,
    endpoint: str = LLM_ENDPOINT,
    seed: int = MODEL_SEED,
    simulation_id: str | None = None,
    agent_llm_args: Mapping[str, Any] | None = None,
    user_llm_args: Mapping[str, Any] | None = None,
    max_turns: int = MAX_TURNS,
    max_task_tool_calls: int = MAX_TASK_TOOL_CALLS,
) -> RuntimeBundle:
    """Build one fresh Skill-only evaluation with the identical dual canary."""

    from .hybrid_spec import HYBRID_TASK_IDS

    if task_id not in HYBRID_TASK_IDS:
        raise ValueError("task is outside the fixed hybrid sample")
    cell_id = simulation_id or uuid.uuid4().hex
    sidecar = DualCommandSidecar(cell_id)
    toolkit = HybridEvaluationKnowledgeTools(load_fresh_official_db(), sidecar)
    return _build_bundle(
        mode="hybrid-evaluation",
        task=load_official_task(task_id),
        toolkit=toolkit,
        policy=_deployment_policy(skill_text),
        retriever=None,
        sidecar=sidecar,
        profile=None,
        model=model,
        endpoint=endpoint,
        seed=seed,
        simulation_id=cell_id,
        agent_llm_args=agent_llm_args,
        user_llm_args=user_llm_args,
        max_turns=max_turns,
        max_task_tool_calls=max_task_tool_calls,
    )


def build_full_doc_evaluation_runtime(
    task_id: str,
    skill_text: str,
    *,
    allowed_task_ids: Sequence[str],
    deployment_prompt_path: Path,
    runtime_controls: RuntimeControls,
    model: str = HYBRID_LITELLM_MODEL,
    endpoint: str = LLM_ENDPOINT,
    tokenizer_model: str | None = None,
    chat_token_counter: ChatTokenCounter | None = None,
    user_model: str | None = None,
    user_endpoint: str | None = None,
    user_tokenizer_model: str | None = None,
    user_chat_token_counter: ChatTokenCounter | None = None,
    agent_transport: str = "local-vllm",
    user_transport: str = "local-vllm",
    seed: int = MODEL_SEED,
    simulation_id: str | None = None,
    max_turns: int = MAX_TURNS,
    max_task_tool_calls: int = MAX_TASK_TOOL_CALLS,
    banking_root: Path = BANKING_ROOT,
    tasks_root: Path = TASKS_ROOT,
) -> RuntimeBundle:
    """Build a fresh full-document experiment evaluation without retrieval state."""

    registered_tasks = tuple(allowed_task_ids)
    if task_id not in registered_tasks or len(registered_tasks) != len(set(registered_tasks)):
        raise ValueError("task is outside the registered full-document sample")
    cell_id = simulation_id or uuid.uuid4().hex
    sidecar = DualCommandSidecar(cell_id)
    toolkit = HybridEvaluationKnowledgeTools(load_fresh_official_db(banking_root), sidecar)
    return _build_bundle(
        mode="full-doc-evaluation",
        task=load_official_task(task_id, tasks_root),
        toolkit=toolkit,
        policy=_deployment_policy(skill_text, prompt_path=deployment_prompt_path),
        retriever=None,
        sidecar=sidecar,
        profile=None,
        model=model,
        endpoint=endpoint,
        seed=seed,
        simulation_id=cell_id,
        agent_llm_args=None,
        user_llm_args=None,
        max_turns=max_turns,
        max_task_tool_calls=max_task_tool_calls,
        runtime_controls=runtime_controls,
        token_counter=chat_token_counter,
        tokenizer_model=tokenizer_model,
        user_model=user_model,
        user_endpoint=user_endpoint,
        user_token_counter=user_chat_token_counter,
        user_tokenizer_model=user_tokenizer_model,
        agent_transport=agent_transport,
        user_transport=user_transport,
    )


def extract_first_user_utterance(messages: Sequence[Message]) -> str:
    """Return the first non-empty, non-tool-only UserMessage exactly as seen."""
    for message in messages:
        if (
            isinstance(message, UserMessage)
            and isinstance(message.content, str)
            and message.content.strip()
        ):
            return message.content
    raise OfficialRuntimeError("trajectory contains no real user utterance")


def _command_sha256(arguments: object) -> str | None:
    """Hash a command argument without retaining the command itself."""

    if not isinstance(arguments, Mapping):
        return None
    command = arguments.get("command")
    if not isinstance(command, str):
        return None
    return hashlib.sha256(command.encode("utf-8")).hexdigest()


def _redact_public_value(value: object, command_hashes: Mapping[str, str]) -> object:
    """Remove registered command strings from a public-trace value."""

    if isinstance(value, str):
        redacted = value
        for command in sorted(command_hashes, key=len, reverse=True):
            replacement = f"<redacted-command:{command_hashes[command]}>"
            variants = {command, json.dumps(command, ensure_ascii=False)[1:-1]}
            for variant in sorted(variants, key=len, reverse=True):
                redacted = redacted.replace(variant, replacement)
        return redacted
    if isinstance(value, Mapping):
        return {key: _redact_public_value(item, command_hashes) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_public_value(item, command_hashes) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_public_value(item, command_hashes) for item in value)
    return deepcopy(value)


def _public_tool_arguments(
    call: ToolCall,
    *,
    command_hashes: Mapping[str, str],
) -> object:
    """Remove command text from participant-visible trace artifacts."""

    if call.name not in SIDECAR_TOOL_NAMES:
        return _redact_public_value(call.arguments, command_hashes)
    keys = sorted(str(key) for key in call.arguments) if isinstance(call.arguments, Mapping) else []
    return {
        "argument_keys": keys,
        "command_sha256": _command_sha256(call.arguments),
    }


def _public_tool_result(
    message: ToolMessage,
    *,
    sidecar_result: bool,
    command_hashes: Mapping[str, str],
) -> dict[str, Any]:
    if not sidecar_result:
        return {
            "id": message.id,
            "content": _redact_public_value(message.content, command_hashes),
            "requestor": message.requestor,
            "error": message.error,
        }
    return {
        "id": message.id,
        "content_sha256": (
            hashlib.sha256(str(message.content).encode("utf-8")).hexdigest()
            if message.content is not None
            else None
        ),
        "requestor": message.requestor,
        "error": bool(message.error),
    }


def normalize_public_trace(messages: Sequence[Message]) -> PublicTrace:
    """Normalize only participant-visible fields; omit raw model and task state."""
    events: list[TraceEvent] = []
    sidecar_call_ids: set[tuple[str, str]] = set()
    command_hashes = {
        command: hashlib.sha256(command.encode("utf-8")).hexdigest()
        for command in PAYLOAD_COMMANDS.values()
        if command
    }

    def add(actor: str, kind: str, payload: dict[str, Any]) -> None:
        events.append(TraceEvent(len(events), actor, kind, payload))

    for message in messages:
        if isinstance(message, SystemMessage):
            # System prompts may contain policies. They are not execution-trajectory events.
            continue
        if isinstance(message, (AssistantMessage, UserMessage)):
            payload: dict[str, Any] = {}
            if isinstance(message.content, str) and message.content:
                payload["content"] = _redact_public_value(message.content, command_hashes)
            if message.tool_calls is not None:
                sidecar_call_ids.update(
                    (call.id, call.requestor)
                    for call in message.tool_calls
                    if call.name in SIDECAR_TOOL_NAMES
                )
                payload["tool_calls"] = [
                    {
                        "id": call.id,
                        "name": call.name,
                        "arguments": _public_tool_arguments(
                            call,
                            command_hashes=command_hashes,
                        ),
                        "requestor": call.requestor,
                    }
                    for call in message.tool_calls
                ]
            add(message.role, "message", payload)
        elif isinstance(message, ToolMessage):
            sidecar_result = (message.id, message.requestor) in sidecar_call_ids
            add(
                "tool",
                "tool_result",
                _public_tool_result(
                    message,
                    sidecar_result=sidecar_result,
                    command_hashes=command_hashes,
                ),
            )
        elif isinstance(message, MultiToolMessage):
            for tool_message in message.tool_messages:
                sidecar_result = (
                    tool_message.id,
                    tool_message.requestor,
                ) in sidecar_call_ids
                add(
                    "tool",
                    "tool_result",
                    _public_tool_result(
                        tool_message,
                        sidecar_result=sidecar_result,
                        command_hashes=command_hashes,
                    ),
                )
        else:
            raise OfficialRuntimeError(f"unsupported official message type: {type(message)}")
    return PublicTrace(tuple(events))


def _filter_trajectory(
    messages: Sequence[Message],
) -> tuple[list[Message], tuple[ExcludedToolCall, ...]]:
    filtered: list[Message] = []
    excluded: list[ExcludedToolCall] = []
    pending: deque[_PendingToolCall] = deque()

    def consume_tool_message(message: ToolMessage) -> None:
        if not pending:
            filtered.append(deepcopy(message))
            return
        expected = pending.popleft()
        if message.id != expected.tool_call_id or message.requestor != expected.requestor:
            raise OfficialRuntimeError(
                "tool result does not match the preceding official tool-call order"
            )
        if expected.excluded:
            tool_error = bool(message.error)
            excluded.append(
                ExcludedToolCall(
                    message_index=expected.message_index,
                    tool_call_id=expected.tool_call_id,
                    name=expected.name,
                    requestor=expected.requestor,
                    command_sha256=expected.command_sha256,
                    ok=not tool_error,
                    error=tool_error,
                )
            )
        else:
            filtered.append(deepcopy(message))

    for message_index, message in enumerate(messages):
        if isinstance(message, (AssistantMessage, UserMessage)):
            if pending:
                raise OfficialRuntimeError("participant message arrived before tool results")
            if message.tool_calls is None:
                filtered.append(deepcopy(message))
                continue
            retained_calls: list[ToolCall] = []
            for call in message.tool_calls:
                should_exclude = call.name in FILTERED_EVALUATOR_TOOL_NAMES
                pending.append(
                    _PendingToolCall(
                        message_index=message_index,
                        tool_call_id=call.id,
                        name=call.name,
                        requestor=call.requestor,
                        excluded=should_exclude,
                        command_sha256=(
                            _command_sha256(call.arguments)
                            if call.name in SIDECAR_TOOL_NAMES
                            else None
                        ),
                    )
                )
                if not should_exclude:
                    retained_calls.append(deepcopy(call))
            copied = deepcopy(message)
            copied.tool_calls = retained_calls or None
            if copied.tool_calls is not None or copied.has_content():
                filtered.append(copied)
        elif isinstance(message, ToolMessage):
            consume_tool_message(message)
        elif isinstance(message, MultiToolMessage):
            for tool_message in message.tool_messages:
                consume_tool_message(tool_message)
        else:
            if pending:
                raise OfficialRuntimeError("non-tool message arrived before tool results")
            filtered.append(deepcopy(message))
    if pending:
        raise OfficialRuntimeError("trajectory ended before all tool results arrived")
    return filtered, tuple(excluded)


def filter_official_evaluator_trajectory(messages: Sequence[Message]) -> list[Message]:
    """Remove retrieval/sidecar calls and their exact results for official replay."""
    filtered, _excluded = _filter_trajectory(messages)
    return filtered


def filter_simulation_for_official_evaluator(
    simulation: SimulationRun,
) -> tuple[SimulationRun, tuple[ExcludedToolCall, ...]]:
    """Clone a SimulationRun and remove all experiment-only tool interactions."""
    source_messages = simulation.messages
    if source_messages is None:
        raise OfficialRuntimeError("half-duplex simulation is missing messages")
    messages, excluded = _filter_trajectory(source_messages)
    filtered = simulation.model_copy(deep=True)
    filtered.messages = messages
    filtered.reward_info = None
    return filtered, excluded


def evaluate_official(
    bundle: RuntimeBundle,
    simulation: SimulationRun,
) -> OfficialEvaluation:
    """Run the pinned official evaluator on a sidecar/retrieval-free copy."""
    if simulation.task_id != bundle.task.id:
        raise OfficialRuntimeError("simulation/task mismatch")
    filtered, excluded = filter_simulation_for_official_evaluator(simulation)
    reward_info = evaluate_simulation(
        simulation=filtered,
        task=bundle.task,
        evaluation_type=EvaluationType.ALL,
        solo_mode=False,
        domain=DOMAIN,
        mode=CommunicationMode.HALF_DUPLEX,
        env_kwargs={
            "retrieval_variant": OFFICIAL_RETRIEVAL_VARIANT,
            "read_log_allowlist": _derive_read_log_allowlist(bundle.task),
        },
        strict_replay=True,
    )
    reward = float(reward_info.reward)
    filtered.reward_info = reward_info
    return OfficialEvaluation(
        reward_info=reward_info,
        reward=reward,
        task_success=reward == 1.0,
        filtered_simulation=filtered,
        excluded_tool_calls=excluded,
        sidecar_hit=bundle.sidecar_hit,
        sidecar_events=bundle.sidecar_events,
    )


def run_official(bundle: RuntimeBundle) -> OfficialRunResult:
    """Execute one official dual-control cell and evaluate its filtered replay."""
    simulation = bundle.orchestrator.run()
    simulation.policy = bundle.environment.get_policy()
    trace = normalize_public_trace(simulation.messages or [])
    first_user_utterance = extract_first_user_utterance(simulation.messages or [])
    evaluation = evaluate_official(bundle, simulation)
    simulation.reward_info = evaluation.reward_info
    return OfficialRunResult(
        simulation=simulation,
        public_trace=trace,
        first_user_utterance=first_user_utterance,
        evaluation=evaluation,
    )


__all__ = [
    "AcquisitionKnowledgeTools",
    "BoundedEnvironment",
    "DEFAULT_LITELLM_MODEL",
    "DeleteSentinelDeploymentKnowledgeTools",
    "ExcludedToolCall",
    "FILTERED_EVALUATOR_TOOL_NAMES",
    "FullDocumentAcquisitionKnowledgeTools",
    "InputTokenBudgetExceeded",
    "MockApiDeploymentKnowledgeTools",
    "OfficialEvaluation",
    "OfficialRunResult",
    "OfficialRuntimeError",
    "RuntimeBundle",
    "TaskToolBudgetExceeded",
    "AssistantCompletionBudgetExceeded",
    "build_acquisition_runtime",
    "build_deployment_runtime",
    "build_full_doc_acquisition_runtime",
    "build_full_doc_evaluation_runtime",
    "evaluate_official",
    "extract_first_user_utterance",
    "filter_official_evaluator_trajectory",
    "filter_simulation_for_official_evaluator",
    "load_fresh_official_db",
    "load_official_task",
    "load_official_tasks",
    "normalize_public_trace",
    "run_official",
]
