"""Pinned official adapter for benign batch acquisition and ordinary banking utility.

No historical matrix, substituted corpus, provider extension, or action sidecar
is constructed by this module.
"""

import os
import sys
import uuid
from collections import deque
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import Field

from r2sp_common import Page, PublicTrace, RuntimeIdentity, TraceEvent

from .batch_constants import (
    AGENT_MAX_OUTPUT_TOKENS,
    BANKING_ROOT,
    EXPECTED_TASK_COUNT,
    EXPERIMENT_ROOT,
    MAX_SEARCHES,
    MAX_TASK_TOOL_CALLS,
    MAX_TURNS,
    SELECTION_K,
    TASKS_ROOT,
    UPSTREAM_ROOT,
    USER_SIMULATOR_MAX_OUTPUT_TOKENS,
    VISIBLE_TOP_K,
)
from .hybrid_retrieval import DenseEmbeddingBackend, HybridSearchEvent, HybridSessionRetriever


class OfficialRuntimeError(RuntimeError):
    """The pinned benign runtime contract could not be satisfied."""


def _require_pinned_interpreter() -> None:
    expected_prefix = (UPSTREAM_ROOT / ".venv").resolve()
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

DOMAIN = "banking_knowledge"
OFFICIAL_RETRIEVAL_VARIANT = "no_knowledge"
RuntimeMode = Literal["acquisition", "deployment"]
FILTERED_EVALUATOR_TOOL_NAMES = frozenset({"search_web", "select_docs", "open_page"})
ExactPageSelection = Annotated[
    list[str],
    Field(min_length=SELECTION_K, max_length=SELECTION_K, json_schema_extra={"uniqueItems": True}),
]
_RUNTIME_IDENTITY_KEYS = ("agent", "database", "environment", "orchestrator", "user_simulator")


class TaskToolBudgetExceeded(OfficialRuntimeError):
    """No further task tool can execute after the cell budget is exhausted."""


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
        retriever: HybridSessionRetriever,
    ) -> None:
        super().__init__(db)
        self.retriever = retriever

    @is_tool(ToolType.READ, mutates_state=False)
    def search_web(self, query: str) -> dict[str, list[dict[str, str]]]:
        """Search all page bodies and return the top ten IDs, titles, and bodies.

        Args:
            query: Search query generated for the current customer request.
        """
        return self.retriever.search_web(query)

    @is_tool(ToolType.READ, mutates_state=False)
    def select_docs(self, page_ids: ExactPageSelection) -> dict[str, list[dict[str, str]]]:
        """Select the configured number of exposed pages and read their bodies once.

        Args:
            page_ids: Unique page identifiers returned by ``search_web``.
        """
        return self.retriever.select_docs(page_ids)


@dataclass(frozen=True)
class RuntimeBundle:
    """One fresh task runtime, with retrieval attached only during acquisition."""

    mode: RuntimeMode
    task: Task
    environment: BoundedEnvironment
    toolkit: KnowledgeTools
    user_toolkit: KnowledgeUserTools
    agent: LLMAgent
    user_simulator: UserSimulator
    orchestrator: Orchestrator
    runtime_identity: RuntimeIdentity
    retriever: HybridSessionRetriever | None = None

    @property
    def exposed_tool_names(self) -> tuple[str, ...]:
        return tuple(sorted(tool.name for tool in self.environment.get_tools()))

    @property
    def opened_pages(self) -> tuple[Page, ...]:
        return () if self.retriever is None else self.retriever.opened_pages

    @property
    def search_events(self) -> tuple[HybridSearchEvent, ...]:
        return () if self.retriever is None else self.retriever.search_events

    @property
    def selection_complete(self) -> bool:
        return False if self.retriever is None else self.retriever.selection_complete

    def close(self) -> None:
        if self.retriever is not None:
            self.retriever.close()

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

    def to_dict(self) -> dict[str, Any]:
        return {
            "message_index": self.message_index,
            "tool_call_id": self.tool_call_id,
            "name": self.name,
            "requestor": self.requestor,
        }


@dataclass(frozen=True)
class OfficialEvaluation:
    """Official reward and the exact retrieval-free trajectory it evaluated."""

    reward_info: RewardInfo
    reward: float
    task_success: bool
    filtered_simulation: SimulationRun
    excluded_tool_calls: tuple[ExcludedToolCall, ...]


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


def load_official_task(task_id: str) -> Task:
    """Load one exact official task without projecting any hidden fields."""
    if not isinstance(task_id, str) or not task_id:
        raise ValueError("task_id must be a non-empty string")
    task_path = TASKS_ROOT / f"{task_id}.json"
    if not task_path.is_file():
        raise OfficialRuntimeError(f"official task does not exist: {task_id}")
    try:
        task = Task.model_validate_json(task_path.read_bytes())
    except Exception as exc:
        raise OfficialRuntimeError(f"invalid official task: {task_id}") from exc
    if task.id != task_id:
        raise OfficialRuntimeError(f"official task ID mismatch: {task_id}")
    return task


def load_official_tasks() -> tuple[Task, ...]:
    """Load all 97 official banking tasks in filename order."""
    paths = sorted(TASKS_ROOT.glob("task_*.json"), key=lambda path: path.name)
    tasks = tuple(load_official_task(path.stem) for path in paths)
    if len(tasks) != EXPECTED_TASK_COUNT:
        raise OfficialRuntimeError(
            f"expected {EXPECTED_TASK_COUNT} official tasks, observed {len(tasks)}"
        )
    return tasks


def load_fresh_official_db() -> TransactionalDB:
    """Load a new official TransactionalDB object for one cell."""
    return TransactionalDB.load(str(BANKING_ROOT / "db.json"))


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


def _compose_policy(experiment_instructions: str) -> str:
    return f"{_official_no_knowledge_policy().rstrip()}\n\n{experiment_instructions}"


def _deployment_policy(skill_text: str) -> str:
    if not isinstance(skill_text, str) or not skill_text.strip():
        raise ValueError("skill_text must be a non-empty string")
    template = _read_experiment_prompt("batch_deployment_system.md")
    marker = "{skill_text}"
    if template.count(marker) != 1:
        raise OfficialRuntimeError("deployment prompt must contain one {skill_text} marker")
    return _compose_policy(template.replace(marker, skill_text))


def _agent_llm_args(endpoint: str, seed: int) -> dict[str, Any]:
    return {
        "api_base": endpoint,
        "api_key": "tau-local-evaluation",
        "temperature": 1.0,
        "top_p": 0.95,
        "presence_penalty": 0.0,
        "reasoning_effort": "xhigh",
        "max_tokens": AGENT_MAX_OUTPUT_TOKENS,
        "num_retries": 0,
        "seed": seed,
        "extra_body": {
            "top_k": 20,
            "min_p": 0.0,
            "repetition_penalty": 1.0,
            "chat_template_kwargs": {
                "enable_thinking": True,
                "preserve_thinking": False,
            },
        },
    }


def _user_llm_args(endpoint: str, seed: int) -> dict[str, Any]:
    return {
        "api_base": endpoint,
        "api_key": "tau-local-evaluation",
        "temperature": 0.0,
        "max_tokens": USER_SIMULATOR_MAX_OUTPUT_TOKENS,
        "num_retries": 0,
        "seed": seed,
        "extra_body": {
            "chat_template_kwargs": {
                "enable_thinking": False,
                "preserve_thinking": False,
            },
        },
    }


def _new_runtime_identity() -> RuntimeIdentity:
    return RuntimeIdentity(
        process_id=os.getpid(),
        instances={name: uuid.uuid4().hex for name in _RUNTIME_IDENTITY_KEYS},
        execution_id=uuid.uuid4().hex,
        slurm_job_id=os.environ.get("SLURM_JOB_ID"),
        node_name=os.environ.get("SLURMD_NODENAME") or os.environ.get("HOSTNAME"),
    )


def _build_bundle(
    *,
    mode: RuntimeMode,
    task: Task,
    toolkit: KnowledgeTools,
    policy: str,
    retriever: HybridSessionRetriever | None,
    model: str,
    endpoint: str,
    seed: int,
    simulation_id: str | None,
    agent_llm_args: Mapping[str, Any] | None,
    user_llm_args: Mapping[str, Any] | None,
    max_turns: int,
    max_task_tool_calls: int,
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
    effective_agent_args = (
        _agent_llm_args(endpoint, seed)
        if agent_llm_args is None
        else deepcopy(dict(agent_llm_args))
    )
    effective_user_args = (
        _user_llm_args(endpoint, seed) if user_llm_args is None else deepcopy(dict(user_llm_args))
    )
    agent = LLMAgent(
        tools=environment.get_tools(),
        domain_policy=environment.get_policy(),
        llm=model,
        llm_args=effective_agent_args,
    )
    try:
        user_tools = environment.get_user_tools(include=task.user_tools) or None
    except ValueError as exc:
        raise OfficialRuntimeError(f"invalid official user tool allowlist for {task.id}") from exc
    user = UserSimulator(
        llm=model,
        instructions=str(task.user_scenario),
        tools=user_tools,
        llm_args=effective_user_args,
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
    )


def build_benign_batch_runtime(
    *,
    mode: RuntimeMode,
    task_id: str,
    model: str,
    endpoint: str,
    seed: int,
    skill_text: str | None = None,
    simulation_id: str | None = None,
    dense_embedder: DenseEmbeddingBackend | None = None,
) -> RuntimeBundle:
    """Build the v2 benign workflow with no profile or sidecar action tools.

    Acquisition reads only the verified official snapshot. Deployment accepts
    only the current task and Skill, and attaches ordinary banking tools.
    """
    from .data import load_documents, verify_tracked_snapshot

    if mode not in {"acquisition", "deployment"}:
        raise ValueError("batch runtime mode must be acquisition or deployment")
    if (
        not isinstance(task_id, str)
        or len(task_id) != 8
        or not task_id.startswith("task_")
        or not task_id[5:].isascii()
        or not task_id[5:].isdigit()
    ):
        raise ValueError("batch task ID is invalid")
    verify_tracked_snapshot()
    task = load_official_task(task_id)
    db = load_fresh_official_db()
    retriever = None
    if mode == "acquisition":
        if skill_text is not None:
            raise ValueError("batch acquisition cannot receive a Skill")
        if dense_embedder is None:
            from .dense_client import HttpCachedDenseEmbedder

            dense_embedder = HttpCachedDenseEmbedder(
                os.environ.get("R2SP_TAU_DENSE_ENDPOINT", "http://127.0.0.1:18139"),
                cache_root=Path(os.environ["R2SP_TAU_DENSE_CACHE_ROOT"]),
            )
            dense_embedder.health()
        pages = tuple(
            Page(
                page_id=document.page_id,
                title=document.title,
                body=document.body,
                content_sha256=document.content_sha256,
            )
            for document in load_documents()
        )
        retriever = HybridSessionRetriever.from_pages(
            pages,
            dense_embedder,
            top_k=VISIBLE_TOP_K,
            max_searches=MAX_SEARCHES,
            selection_k=SELECTION_K,
        )
        toolkit = AcquisitionKnowledgeTools(db, retriever)
        policy = _compose_policy(_read_experiment_prompt("batch_acquisition_system.md"))
    else:
        if not isinstance(skill_text, str) or not skill_text.strip():
            raise ValueError("batch deployment requires non-empty Skill text")
        if dense_embedder is not None:
            raise ValueError("batch deployment cannot attach retrieval")
        toolkit = KnowledgeTools(db)
        policy = _deployment_policy(skill_text)
    return _build_bundle(
        mode=mode,
        task=task,
        toolkit=toolkit,
        policy=policy,
        retriever=retriever,
        model=f"hosted_vllm/{model}",
        endpoint=endpoint,
        seed=seed,
        simulation_id=simulation_id,
        agent_llm_args=None,
        user_llm_args=None,
        max_turns=MAX_TURNS,
        max_task_tool_calls=MAX_TASK_TOOL_CALLS,
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


def normalize_public_trace(messages: Sequence[Message]) -> PublicTrace:
    """Normalize only participant-visible fields; omit raw model and task state."""
    events: list[TraceEvent] = []

    def add(actor: str, kind: str, payload: dict[str, Any]) -> None:
        events.append(TraceEvent(len(events), actor, kind, payload))

    for message in messages:
        if isinstance(message, SystemMessage):
            # System prompts may contain policies. They are not execution-trajectory events.
            continue
        if isinstance(message, (AssistantMessage, UserMessage)):
            payload: dict[str, Any] = {}
            if isinstance(message.content, str) and message.content:
                payload["content"] = message.content
            if message.tool_calls is not None:
                payload["tool_calls"] = [
                    {
                        "id": call.id,
                        "name": call.name,
                        "arguments": deepcopy(call.arguments),
                        "requestor": call.requestor,
                    }
                    for call in message.tool_calls
                ]
            add(message.role, "message", payload)
        elif isinstance(message, ToolMessage):
            add(
                "tool",
                "tool_result",
                {
                    "id": message.id,
                    "content": message.content,
                    "requestor": message.requestor,
                    "error": message.error,
                },
            )
        elif isinstance(message, MultiToolMessage):
            for tool_message in message.tool_messages:
                add(
                    "tool",
                    "tool_result",
                    {
                        "id": tool_message.id,
                        "content": tool_message.content,
                        "requestor": tool_message.requestor,
                        "error": tool_message.error,
                    },
                )
        else:
            raise OfficialRuntimeError(f"unsupported official message type: {type(message)}")
    return PublicTrace(tuple(events))


def _filter_trajectory(
    messages: Sequence[Message],
) -> tuple[list[Message], tuple[ExcludedToolCall, ...]]:
    filtered: list[Message] = []
    excluded: list[ExcludedToolCall] = []
    pending: deque[tuple[str, str, bool]] = deque()

    def consume_tool_message(message: ToolMessage) -> None:
        if not pending:
            filtered.append(deepcopy(message))
            return
        expected_id, expected_requestor, should_exclude = pending.popleft()
        if message.id != expected_id or message.requestor != expected_requestor:
            raise OfficialRuntimeError(
                "tool result does not match the preceding official tool-call order"
            )
        if not should_exclude:
            filtered.append(deepcopy(message))

    for message_index, message in enumerate(messages):
        if isinstance(message, (AssistantMessage, UserMessage)):
            if pending:
                raise OfficialRuntimeError("participant message arrived before tool results")
            if message.tool_calls is None:
                copied = deepcopy(message)
                copied.raw_data = None
                filtered.append(copied)
                continue
            retained_calls: list[ToolCall] = []
            for call in message.tool_calls:
                should_exclude = call.name in FILTERED_EVALUATOR_TOOL_NAMES
                pending.append((call.id, call.requestor, should_exclude))
                if should_exclude:
                    excluded.append(
                        ExcludedToolCall(
                            message_index=message_index,
                            tool_call_id=call.id,
                            name=call.name,
                            requestor=call.requestor,
                        )
                    )
                else:
                    retained_calls.append(deepcopy(call))
            copied = deepcopy(message)
            copied.tool_calls = retained_calls or None
            # Provider response envelopes duplicate tool calls under raw_data.
            # They are never evaluator inputs, so remove them from the filtered
            # replay rather than retaining an unfiltered second representation.
            copied.raw_data = None
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
    """Remove retrieval calls and their exact results for official replay."""
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
    """Run the pinned official evaluator on a retrieval-free copy."""
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
