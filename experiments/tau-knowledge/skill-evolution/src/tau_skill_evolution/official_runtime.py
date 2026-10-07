"""Fresh official bank runtime, imported only by the pinned tau2 interpreter."""

import hashlib
import json
import os
import sys
import uuid
from collections import Counter, deque
from collections.abc import Mapping, Sequence
from contextlib import nullcontext
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal
from unittest.mock import patch

from tau_skill_evolution.core import PublicTrace, RuntimeIdentity, TraceEvent

from .constants import (
    BANKING_ROOT,
    EXPECTED_TASK_COUNT,
    MAX_TASK_TOOL_CALLS,
    MODEL_SEED,
    PAYLOAD_COMMANDS,
    SIDECAR_TOOLS,
    TASKS_ROOT,
    UPSTREAM_ROOT,
    WORKER_PYTHON_VERSION,
)
from .model import ChatTokenCounter, ModelClient
from .runtime_controls import RuntimeControls
from .sidecar import DualCommandSidecar


class OfficialRuntimeError(RuntimeError):
    """The pinned official runtime contract could not be satisfied."""


def _runtime_upstream_root() -> Path:
    """Resolve the pinned checkout explicitly supplied by the controller."""

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
    if tuple(sys.version_info[:3]) != WORKER_PYTHON_VERSION or observed_prefix != expected_prefix:
        pinned = ".".join(str(part) for part in WORKER_PYTHON_VERSION)
        raise OfficialRuntimeError(
            f"official_runtime must run with the frozen tau2 Python {pinned} "
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
from tau2.data_model.simulation import RewardInfo, SimulationRun, TerminationReason  # noqa: E402
from tau2.data_model.tasks import RewardType, Task  # noqa: E402
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
from tau2.environment.toolkit import ToolType as ToolType  # noqa: E402
from tau2.environment.toolkit import is_tool as is_tool  # noqa: E402
from tau2.evaluator.evaluator import (  # noqa: E402
    EvaluationType,
    evaluate_simulation,
)
from tau2.orchestrator.modes import CommunicationMode  # noqa: E402
from tau2.orchestrator.orchestrator import Orchestrator  # noqa: E402
from tau2.user.user_simulator import UserSimulator  # noqa: E402
from tau2.utils.llm_utils import to_litellm_messages  # noqa: E402

DOMAIN = "banking_knowledge"
OFFICIAL_RETRIEVAL_VARIANT = "no_knowledge"
SKILL_TOOL_NAMES = frozenset({"read_skill_file", "run_skill_script"})
SIDECAR_TOOL_NAMES = frozenset({"sandbox_run_command", *SIDECAR_TOOLS.values()})
FILTERED_EVALUATOR_TOOL_NAMES = SKILL_TOOL_NAMES | SIDECAR_TOOL_NAMES
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
    """A request estimate exceeded the experiment's input budget."""


class AssistantCompletionBudgetExceeded(OfficialRuntimeError):
    """The agent exhausted its cumulative per-cell completion allowance."""


def _serialize_messages(messages: Sequence[Message]) -> list[dict[str, Any]]:
    """Keep encrypted Responses items only inside the originating model session."""
    source = list(messages)
    converted = to_litellm_messages(source)
    if len(source) != len(converted):
        raise OfficialRuntimeError("tau message conversion changed history cardinality")
    for message, payload in zip(source, converted, strict=True):
        if not isinstance(message, AssistantMessage) or not isinstance(message.raw_data, Mapping):
            continue
        items = message.raw_data.get("_bedrock_output_items")
        if isinstance(items, list):
            payload["_bedrock_output_items"] = deepcopy(items)
            if isinstance(message.usage, Mapping):
                payload["usage"] = deepcopy(message.usage)
    return converted


def _user_model_history(state: Any) -> list[Message]:
    history = state.flip_roles()
    for original, flipped in zip(state.messages, history, strict=True):
        if isinstance(original, UserMessage) and isinstance(flipped, AssistantMessage):
            flipped.raw_data = deepcopy(original.raw_data)
            flipped.usage = deepcopy(original.usage)
    return history


def _complete(
    client: ModelClient,
    messages: Sequence[Message],
    tools: Sequence[Any] | None,
    *,
    max_output_tokens: int,
) -> AssistantMessage:
    schemas = None if not tools else [tool.openai_schema for tool in tools]
    result = client.complete(
        _serialize_messages(messages), tools=schemas, max_output_tokens=max_output_tokens
    )
    if not isinstance(result, Mapping) or result.get("role") != "assistant":
        raise OfficialRuntimeError("model response is not an assistant message")
    if result.get("finish_reason") == "length":
        raise OfficialRuntimeError("model response exceeded its output budget")
    calls = []
    for value in result.get("tool_calls") or ():
        function = value["function"]
        arguments = function["arguments"]
        if isinstance(arguments, str):
            arguments = json.loads(arguments)
        if not isinstance(arguments, dict):
            raise OfficialRuntimeError("model tool arguments must be an object")
        calls.append(ToolCall(id=value["id"], name=function["name"], arguments=arguments))
    raw = {
        key: deepcopy(result[key])
        for key in ("_bedrock_output_items", "response_id")
        if key in result
    }
    usage = result.get("usage", getattr(client, "last_usage", None))
    content = result.get("content")
    if not calls and (content is None or not str(content).strip()):
        # Operator deviation (2026-10-05): a completed response with neither text nor
        # tool calls ends the episode as the agent's stop signal instead of failing the
        # whole evaluation; tau2 rejects empty assistant turns. Recorded in raw_data.
        content = "###STOP###"
        raw["empty_output_as_stop"] = True
    return AssistantMessage(
        role="assistant",
        content=content,
        tool_calls=calls or None,
        usage=usage,
        raw_data=raw or None,
    )


class RuntimeAdmission:
    """Fail-closed token admission shared by both participants in one cell."""

    def __init__(
        self,
        controls: RuntimeControls,
        counter: ChatTokenCounter,
        *,
        user_counter: ChatTokenCounter | None = None,
    ) -> None:
        self.controls = controls
        self.counter = counter
        self.counters = {
            "agent": counter,
            "user": user_counter or counter,
        }
        self._input_tokens: dict[str, list[int]] = {"agent": [], "user": []}
        self._assistant_completion_tokens = 0

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
    ) -> int:
        schemas = None if not tools else [tool.openai_schema for tool in tools]
        converted = _serialize_messages(messages)
        return self.counters[participant].count(
            converted,
            tools=schemas,
            chat_template_kwargs=None,
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
    ) -> int:
        return self._admit_count(
            participant,
            self._count_input(participant, messages, tools),
        )

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
            "completion_token_authority": "provider_response_usage",
        }


class AdmissionControlledLLMAgent(LLMAgent):
    """Official agent state with bounded Bedrock Responses generation."""

    def __init__(
        self,
        *args: Any,
        admission: RuntimeAdmission,
        settings: Any,
        model_client: ModelClient,
        **kwargs: Any,
    ) -> None:
        self._runtime_admission = admission
        self._runtime_settings = settings
        self._model_client = model_client
        super().__init__(*args, **kwargs)

    def _generate_next_message(self, message: Any, state: Any) -> AssistantMessage:
        if isinstance(message, UserMessage) and message.is_audio:
            raise OfficialRuntimeError("bank runtime requires text messages")
        additions = (
            list(message.tool_messages) if isinstance(message, MultiToolMessage) else [message]
        )
        prospective = [*state.system_messages, *state.messages, *additions]
        self._runtime_admission.admit("agent", prospective, self.tools)
        remaining = self._runtime_admission.assistant_completion_tokens_remaining
        if remaining <= 0:
            raise AssistantCompletionBudgetExceeded("assistant completion budget is exhausted")
        state.messages.extend(additions)
        response = _complete(
            self._model_client,
            prospective,
            self.tools,
            max_output_tokens=min(self._runtime_settings.max_output_tokens, remaining),
        )
        self._runtime_admission.record_assistant_completion(response)
        return response


class AdmissionControlledUserSimulator(UserSimulator):
    """Official private user scenario with an independent Bedrock client/session."""

    def __init__(
        self,
        *args: Any,
        admission: RuntimeAdmission,
        settings: Any,
        model_client: ModelClient,
        **kwargs: Any,
    ) -> None:
        self._runtime_admission = admission
        self._runtime_settings = settings
        self._model_client = model_client
        super().__init__(*args, **kwargs)

    def _generate_next_message(self, message: Any, state: Any) -> UserMessage:
        if isinstance(message, AssistantMessage) and message.is_audio:
            raise OfficialRuntimeError("bank runtime requires text messages")
        additions = (
            list(message.tool_messages) if isinstance(message, MultiToolMessage) else [message]
        )
        additions = [
            item
            for item in additions
            if isinstance(item, ToolMessage) or item.has_content() or item.is_tool_call()
        ]
        prospective_state = state.model_copy(update={"messages": [*state.messages, *additions]})
        prospective = [*state.system_messages, *_user_model_history(prospective_state)]
        self._runtime_admission.admit("user", prospective, self.tools)
        state.messages.extend(additions)
        response = _complete(
            self._model_client,
            prospective,
            self.tools,
            max_output_tokens=self._runtime_settings.max_output_tokens,
        )
        calls = [
            call.model_copy(update={"requestor": "user"}) for call in response.tool_calls or ()
        ]
        return UserMessage(
            role="user",
            content=response.content,
            tool_calls=calls or None,
            usage=response.usage,
            raw_data=response.raw_data,
        )


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


class ExternalBankAgent(LLMAgent):
    """Official agent state driven by the Generator, without a second model."""

    pending_message: AssistantMessage | None = None

    def _generate_next_message(self, message: Any, state: Any) -> AssistantMessage:
        if self.pending_message is None:
            raise OfficialRuntimeError("external bank action required")
        additions = (
            list(message.tool_messages) if isinstance(message, MultiToolMessage) else [message]
        )
        state.messages.extend(additions)
        response, self.pending_message = self.pending_message, None
        return response


@dataclass(frozen=True)
class RuntimeBundle:
    """One fresh bank episode; hidden task and evaluator handles stay here."""

    task: Task
    environment: BoundedEnvironment
    toolkit: KnowledgeTools
    user_toolkit: KnowledgeUserTools
    agent: LLMAgent
    user_simulator: UserSimulator
    orchestrator: Orchestrator
    runtime_identity: RuntimeIdentity
    admission: RuntimeAdmission
    sidecar: DualCommandSidecar | None = None

    @property
    def sidecar_hit(self) -> bool:
        return self.sidecar is not None and self.sidecar.hit

    @property
    def sidecar_events(self) -> tuple[Mapping[str, Any], ...]:
        return (
            ()
            if self.sidecar is None
            else tuple(MappingProxyType(event) for event in self.sidecar.events)
        )

    def close(self) -> None:
        if self.sidecar is not None:
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


def deployment_policy(skill_text: str, *, prompt_path: Path) -> str:
    if not isinstance(skill_text, str) or not skill_text.strip():
        raise ValueError("skill_text must be a non-empty string")
    instructions = _read_prompt_path(prompt_path)
    return _compose_policy(
        f"{instructions.rstrip()}\n\n<loaded_skill>\n{skill_text}\n</loaded_skill>"
    )


def build_runtime(
    task_id: str,
    toolkit: KnowledgeTools,
    *,
    policy: str,
    tasks_root: Path,
    allowed_task_ids: Sequence[str],
    runtime_controls: RuntimeControls,
    model: str,
    model_client: ModelClient | None,
    user_model_client: ModelClient,
    chat_token_counter: ChatTokenCounter,
    user_chat_token_counter: ChatTokenCounter,
    sidecar: DualCommandSidecar | None = None,
    seed: int = MODEL_SEED,
    max_turns: int = 100,
    max_task_tool_calls: int = MAX_TASK_TOOL_CALLS,
    external_driver: bool = False,
) -> RuntimeBundle:
    """Construct official objects without executing an episode or scoring it."""
    if task_id not in allowed_task_ids:
        raise ValueError("task is outside the registered sample")
    task = load_official_task(task_id, tasks_root)
    toolkit.set_read_log_allowlist(_derive_read_log_allowlist(task))
    if not isinstance(toolkit.db, TransactionalDB):
        raise OfficialRuntimeError("official toolkit is missing TransactionalDB")
    user_toolkit = KnowledgeUserTools(toolkit.db)
    environment = BoundedEnvironment(
        domain_name=DOMAIN,
        policy=policy,
        tools=toolkit,
        user_tools=user_toolkit,
        max_task_tool_calls=max_task_tool_calls,
    )
    admission = RuntimeAdmission(
        runtime_controls,
        chat_token_counter,
        user_counter=user_chat_token_counter,
    )
    agent_options = {"tools": environment.get_tools(), "domain_policy": policy, "llm": model}
    if external_driver:
        agent = ExternalBankAgent(**agent_options)
    else:
        if model_client is None:
            raise ValueError("execution model client required")
        agent = AdmissionControlledLLMAgent(
            **agent_options,
            model_client=model_client,
            admission=admission,
            settings=runtime_controls.agent,
        )
    user = AdmissionControlledUserSimulator(
        llm=model,
        instructions=str(task.user_scenario),
        tools=environment.get_user_tools(include=task.user_tools) or None,
        model_client=user_model_client,
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
        simulation_id=uuid.uuid4().hex,
        validate_communication=False,
    )
    identity = RuntimeIdentity(
        process_id=os.getpid(),
        instances={name: uuid.uuid4().hex for name in _RUNTIME_IDENTITY_KEYS},
    )
    return RuntimeBundle(
        task,
        environment,
        toolkit,
        user_toolkit,
        agent,
        user,
        orchestrator,
        identity,
        admission,
        sidecar,
    )


def simulate_official(bundle: RuntimeBundle) -> SimulationRun:
    """Execute without invoking or materializing official scoring."""
    simulation = bundle.orchestrator.run()
    simulation.policy = bundle.environment.get_policy()
    return simulation


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


def normalize_public_trace(messages: Sequence[Message]) -> PublicTrace:
    """Expose bank observations without simulator internals or package source/IO."""
    events: list[TraceEvent] = []
    calls: dict[tuple[str, str], ToolCall] = {}
    command_hashes = {
        command: hashlib.sha256(command.encode("utf-8")).hexdigest()
        for command in PAYLOAD_COMMANDS.values()
    }

    def add(actor: str, kind: str, payload: dict[str, Any]) -> None:
        events.append(TraceEvent(len(events), actor, kind, payload))

    def tool_result(message: ToolMessage) -> None:
        if message.requestor != "assistant":
            return
        call = calls.get((message.id, message.requestor))
        if call is None:
            raise OfficialRuntimeError("public tool result has no matching call")
        if call.name in SIDECAR_TOOL_NAMES or call.name == "read_skill_file":
            return
        if call.name == "run_skill_script":
            try:
                value = json.loads(message.content or "{}")
            except (ValueError, TypeError):
                value = {}
            status = value if isinstance(value, dict) else {}
            add(
                "tool",
                "script_result",
                {
                    "id": message.id,
                    "exit_code": status.get("exit_code"),
                    "failure": status.get("failure"),
                    "error": bool(message.error),
                },
            )
            return
        add(
            "tool",
            "tool_result",
            {
                "id": message.id,
                "content": _redact_public_value(message.content, command_hashes),
                "requestor": "assistant",
                "error": bool(message.error),
            },
        )

    for message in messages:
        if isinstance(message, SystemMessage):
            continue
        if isinstance(message, (AssistantMessage, UserMessage)):
            payload: dict[str, Any] = {}
            if isinstance(message.content, str) and message.content:
                payload["content"] = _redact_public_value(message.content, command_hashes)
            visible_calls = []
            for call in message.tool_calls or ():
                calls[(call.id, call.requestor)] = call
                if call.requestor != "assistant" or call.name in (
                    SIDECAR_TOOL_NAMES | SKILL_TOOL_NAMES
                ):
                    continue
                visible_calls.append(
                    {
                        "id": call.id,
                        "name": call.name,
                        "arguments": _redact_public_value(call.arguments, command_hashes),
                        "requestor": "assistant",
                    }
                )
            if visible_calls:
                payload["tool_calls"] = visible_calls
            if payload:
                add(message.role, "message", payload)
        elif isinstance(message, ToolMessage):
            tool_result(message)
        elif isinstance(message, MultiToolMessage):
            for item in message.tool_messages:
                tool_result(item)
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
    """Remove package and canary interactions before official bank replay."""
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
    *,
    judge_model_client: ModelClient | None = None,
) -> OfficialEvaluation:
    """Score a replay containing only official bank interactions."""
    if simulation.task_id != bundle.task.id:
        raise OfficialRuntimeError("simulation/task mismatch")
    filtered, excluded = filter_simulation_for_official_evaluator(simulation)
    criteria = bundle.task.evaluation_criteria
    # The pinned evaluator returns official reward zero before component scoring
    # for premature termination. It neither needs a judge nor returns NL checks.
    needs_judge = (
        criteria is not None
        and RewardType.NL_ASSERTION in criteria.reward_basis
        and bool(criteria.nl_assertions)
        and filtered.termination_reason
        in {TerminationReason.AGENT_STOP, TerminationReason.USER_STOP}
    )
    if needs_judge and judge_model_client is None:
        raise OfficialRuntimeError("required private NL judge client is unavailable")

    def judge_generate(*, messages: Any, call_name: str, **_kwargs: Any) -> AssistantMessage:
        if call_name != "nl_assertions_eval" or judge_model_client is None:
            raise OfficialRuntimeError("unexpected private judge request")
        return _complete(judge_model_client, messages, None, max_output_tokens=16384)

    judge_context = (
        patch("tau2.evaluator.evaluator_nl_assertions.generate", side_effect=judge_generate)
        if needs_judge
        else nullcontext()
    )
    # The worker is a single fresh episode. Only the private scorer's transport
    # changes; the pinned scorer's instruction, replay and reward rules remain.
    with judge_context:
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
    if needs_judge:
        expected = bundle.task.evaluation_criteria.nl_assertions or []
        actual = reward_info.nl_assertions or []
        if Counter(check.nl_assertion for check in actual) != Counter(expected):
            raise OfficialRuntimeError("private judge returned an incomplete assertion set")
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
