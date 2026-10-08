"""One initial generation, then explicit full-package inheritance revisions."""

from __future__ import annotations

import json
import math
import re
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tau_skill_evolution.core._canonical import (
    canonical_json_bytes,
    canonical_json_sha256,
    thaw_json,
)

from .artifacts import (
    EvolutionSubmission,
    FrozenBase,
    SkillBundle,
    atomic_json,
    seal_bundle,
    validate_relative_path,
    verify_base,
    verify_bundle,
)
from .constants import EXPERIMENT_ROOT
from .journal import Journal, UnknownOperation
from .runtime_controls import public_tool_result


class CreationFailure(RuntimeError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class GeneratorContextBudgetExhausted(CreationFailure):
    """Admission stopped before dispatch; this is not an invalid generated package."""

    def __init__(self, input_tokens: int, max_input_tokens: int) -> None:
        super().__init__("context_budget_exhausted")
        self.input_tokens = input_tokens
        self.max_input_tokens = max_input_tokens


class RevisionFailure(CreationFailure):
    def __init__(self, reason: str, *, dispatched: bool) -> None:
        super().__init__(reason)
        self.dispatched = dispatched


@dataclass
class RevisionConversation:
    """One task's private editing conversation; never an executor/verifier chat."""

    messages: list[dict[str, Any]] = field(default_factory=list)
    turns: int = 0
    episodes: int = 0
    fixed_inputs_hash: str | None = None
    feedback_cursor: int = 0
    feedback_prefix_hash: str | None = None


def _effective_episode(calls: Sequence[Mapping[str, Any]]) -> int:
    """One parsed command/submission response; pure skill tools do not count."""
    for call in calls:
        function = call.get("function", {})
        arguments = function.get("arguments", {})
        try:
            arguments = json.loads(arguments) if isinstance(arguments, str) else arguments
        except (ValueError, TypeError):
            continue
        if not isinstance(arguments, Mapping):
            continue
        if function.get("name") == "terminal" and (
            set(arguments) == {"command"}
            and isinstance(arguments["command"], str)
            and arguments["command"].strip()
        ):
            return 1
        if function.get("name") == "submit_revision" and not arguments:
            return 1
    return 0


GENERATOR_SYSTEM = (EXPERIMENT_ROOT / "prompts" / "generator.md").read_text(encoding="utf-8")
SKILL_BUNDLE_RESPONSE_FORMAT = {
    "type": "json_schema",
    "name": "skill_bundle",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "files": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["path", "content"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["files"],
        "additionalProperties": False,
    },
}


def failure_categories(report: Any) -> list[str]:
    """Port of CoEvoSkills 4380d4b _safe_gt_failure_categories (Apache-2.0).

    Only fixed labels leave the host. Names and all instance-level evidence stay here.
    """
    value = report.to_dict() if hasattr(report, "to_dict") else report
    if not isinstance(value, Mapping):
        raise ValueError("invalid_public_verification_feedback")
    mappings = (
        (
            ("file", "schema", "format", "column", "field", "path", "output"),
            "artifact/interface compliance",
        ),
        (
            ("build", "compile", "install", "import", "runtime", "execute"),
            "build or runtime execution",
        ),
        (
            (
                "recall",
                "precision",
                "semantic",
                "content",
                "detect",
                "classif",
                "coverage",
                "pick",
                "color",
                "match",
                "object",
                "frame",
            ),
            "semantic selection and coverage",
        ),
        (
            (
                "duration",
                "timestamp",
                "segment",
                "audio",
                "video",
                "waveform",
                "sync",
                "correspond",
            ),
            "temporal or media consistency",
        ),
        (
            ("formula", "numeric", "unit", "total", "math", "value", "calculation"),
            "numeric, formula, or unit consistency",
        ),
        (
            ("security", "exploit", "vulnerab", "legitimate", "bypass"),
            "security and robustness behavior",
        ),
        (
            ("constraint", "quality", "valid", "invariant", "balance", "overlap", "depth"),
            "constraint and invariant compliance",
        ),
    )
    categories = []
    for detail in value.get("results", value.get("test_details", ())):
        status = str(detail.get("outcome", detail.get("status", ""))).upper()
        if status not in {"FAILED", "FAIL", "ERROR"}:
            continue
        name = re.sub(r"[^a-z0-9]+", " ", str(detail.get("nodeid", detail.get("name", ""))).lower())
        for tokens, label in mappings:
            if any(token in name for token in tokens) and label not in categories:
                categories.append(label)
    # Re-projection of already sanitized history must not reintroduce raw fields.
    valid_labels = {label for _, label in mappings}
    for label in value.get("failure_categories", ()):
        if label not in valid_labels:
            raise ValueError("unknown_failure_category")
        if label not in categories:
            categories.append(label)
    return categories


def _revision_feedback(report: Any) -> dict[str, Any]:
    value = report.to_dict() if hasattr(report, "to_dict") else report
    if not isinstance(value, Mapping):
        raise ValueError("invalid_public_verification_feedback")
    passed = value.get("passed", False)
    if not isinstance(passed, bool):
        raise ValueError("invalid_public_verification_feedback")
    feedback = {"passed": passed, "failure_categories": failure_categories(value)}
    for name in ("public_schema_issues", "unchecked_phases"):
        if name in value:
            items = value[name]
            if not isinstance(items, (list, tuple)) or any(
                not isinstance(item, str) for item in items
            ):
                raise ValueError("invalid_public_process_feedback")
            feedback[name] = list(items)
    if "verification_unavailable" in value:
        category = value["verification_unavailable"]
        if category not in {
            "no_script",
            "script_error",
            "verifier_generation_error",
            "verifier_runtime_error",
        }:
            raise ValueError("unknown_verification_unavailable_category")
        feedback["verification_unavailable"] = category
    if "oracle_infrastructure_unavailable" in value:
        unavailable = value["oracle_infrastructure_unavailable"]
        if not isinstance(unavailable, bool):
            raise ValueError("invalid_public_process_feedback")
        feedback["oracle_infrastructure_unavailable"] = unavailable
    return feedback


def public_feedback_history(
    history: Sequence[Mapping[str, Any]], base_hash: str
) -> list[dict[str, Any]]:
    """Only author-style failure dimensions and opaque oracle bits are treatment inputs."""
    events = []
    for item in history:
        if not isinstance(item, Mapping) or item.get("base_hash") != base_hash:
            raise ValueError("feedback_history_is_not_for_this_frozen_base")
        kind = item.get("kind")
        event = {"kind": kind, "base_hash": base_hash, "bundle_hash": item.get("bundle_hash")}
        if kind == "oracle":
            if not isinstance(item.get("passed"), bool):
                raise ValueError("oracle_history_must_contain_pass_fail_only")
            event.update(passed=item["passed"], call=item.get("call"))
        elif kind == "verification":
            if not isinstance(item.get("passed"), bool):
                raise ValueError("invalid_public_verification_feedback")
            event.update(_revision_feedback(item))
        else:
            raise ValueError("unknown_feedback_history_kind")
        events.append(event)
    canonical_json_bytes(events)
    return events


def _context_admission(
    model: Any,
    messages: Sequence[Mapping[str, Any]],
    *,
    token_counter: Any,
    context_window: int,
    context_fraction: float,
    reserved_output_tokens: int,
    tools: Sequence[Mapping[str, Any]] | None = None,
    journal: Journal | None = None,
    operation_id: str | None = None,
) -> dict[str, Any]:
    if (
        isinstance(context_window, bool)
        or not isinstance(context_window, int)
        or context_window <= 0
        or isinstance(reserved_output_tokens, bool)
        or not isinstance(reserved_output_tokens, int)
        or reserved_output_tokens <= 0
        or isinstance(context_fraction, bool)
        or not isinstance(context_fraction, (int, float))
        or not math.isfinite(context_fraction)
        or not 0 < context_fraction <= 1
    ):
        raise ValueError("invalid_generator_context_budget")
    maximum = math.floor(context_window * context_fraction) - reserved_output_tokens
    if maximum <= 0:
        raise ValueError("generator_context_has_no_input_budget")
    config = getattr(model, "config", None)
    configured_output = getattr(config, "max_output_tokens", reserved_output_tokens)
    if configured_output is not None and configured_output > reserved_output_tokens:
        raise ValueError("generator_output_exceeds_context_reserve")
    configured_input = getattr(config, "max_input_tokens", None)
    if configured_input is not None:
        maximum = min(maximum, configured_input)
    counter = token_counter if token_counter is not None else getattr(model, "token_counter", None)
    admission = {
        "context_window": context_window,
        "context_fraction": context_fraction,
        "reserved_output_tokens": reserved_output_tokens,
        "max_input_tokens": maximum,
        "checked": counter is not None,
    }
    if counter is None:
        if hasattr(model, "complete"):
            raise ValueError("generator_context_counter_required")
        # Pure callable offline fixtures have no tokenizer; never claim a token estimate.
        return admission
    if hasattr(counter, "count_breakdown"):
        breakdown = counter.count_breakdown(messages, tools=tools)
        observed = breakdown["total_tokens"]
        admission["estimate_breakdown"] = breakdown
    else:
        observed = (
            counter.count(messages, tools=tools) if tools is not None else counter.count(messages)
        )
    if isinstance(observed, bool) or not isinstance(observed, int) or observed < 0:
        raise ValueError("invalid_generator_token_count")
    admission.update(input_tokens=observed, basis=getattr(counter, "basis", "configured_counter"))
    if journal is not None and operation_id is not None:
        atomic_json(
            journal.root / "context-admissions" / (canonical_json_sha256(operation_id) + ".json"),
            {"operation_id": operation_id, "accepted": observed <= maximum, **admission},
        )
    if observed > maximum:
        raise GeneratorContextBudgetExhausted(observed, maximum)
    return admission


def model_messages(payload: Mapping[str, Any], system: str) -> list[dict[str, str]]:
    """The exact fresh request messages, also used for admission before dispatch."""
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": canonical_json_bytes(payload).decode("utf-8")},
    ]


def invoke_model(
    model: Any, payload: Mapping[str, Any], system: str, *, seed: int | None = None
) -> Any:
    """Every role request uses fresh messages; no hidden conversation is inherited."""
    if hasattr(model, "complete"):
        return model.complete(model_messages(payload, system), seed=seed)
    if callable(model):
        return model(dict(payload))
    raise TypeError("model must implement complete() or be a callable")


def journaled_model_request(
    model: Any,
    journal: Journal,
    operation_id: str,
    payload: Mapping[str, Any],
    messages: Sequence[Mapping[str, Any]],
    *,
    tools: Sequence[Mapping[str, Any]] | None = None,
    seed: int | None = None,
    max_output_tokens: int | None = None,
) -> Any:
    if hasattr(model, "complete_journaled"):
        return model.complete_journaled(
            journal,
            operation_id,
            payload,
            messages,
            tools=tools,
            seed=seed,
            max_output_tokens=max_output_tokens,
        )

    def request() -> Any:
        if hasattr(model, "complete"):
            options: dict[str, Any] = {"seed": seed}
            if tools is not None:
                options["tools"] = tools
            if max_output_tokens is not None:
                options["max_output_tokens"] = max_output_tokens
            return model.complete(messages, **options)
        return model(dict(payload.get("inputs", payload)))

    return journal.dispatch(operation_id, payload, request)


def parse_model_json(raw: Any) -> dict[str, Any]:
    if isinstance(raw, Mapping) and "content" in raw:
        if raw.get("tool_calls"):
            raise ValueError("role response cannot dispatch tools")
        if "finish_reason" in raw and raw["finish_reason"] != "stop":
            raise ValueError("role response did not finish normally")
        raw = raw["content"]
    if isinstance(raw, str):

        def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            result: dict[str, Any] = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("duplicate JSON object key")
                result[key] = value
            return result

        raw = json.loads(
            raw,
            object_pairs_hook=unique_object,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError("nonfinite JSON")),
        )
    if not isinstance(raw, Mapping):
        raise ValueError("model response must be a JSON object")
    # Also reject non-JSON mock responses and non-finite values.
    canonical_json_bytes(dict(raw))
    return dict(raw)


def parse_bundle_response(raw: Any, *, parent_hash: str | None = None) -> SkillBundle:
    # Messages providers may wrap their entire JSON answer in one Markdown fence.
    # Only that exact envelope is accepted; JSON parsing still consumes everything.
    text = raw.get("content") if isinstance(raw, Mapping) else raw
    if isinstance(text, str) and text.lstrip().startswith("```"):
        match = re.fullmatch(r"```json[ \t]*\r?\n(.*)\r?\n```", text.strip(), re.DOTALL)
        if match is None:
            raise ValueError("expected exactly one fenced JSON object")
        raw = {**raw, "content": match[1]} if isinstance(raw, Mapping) else match[1]
    value = parse_model_json(raw)
    if set(value) != {"files"} or not isinstance(value["files"], list) or not value["files"]:
        raise ValueError("expected a nonempty files list")
    files: dict[str, str] = {}
    for item in value["files"]:
        if not isinstance(item, Mapping) or set(item) != {"path", "content"}:
            raise ValueError("file entry must have exactly path and content")
        path = validate_relative_path(item["path"])
        if path in files:
            raise ValueError("duplicate package path")
        if not isinstance(item["content"], str):
            raise ValueError("file content must be UTF-8 text")
        files[path] = item["content"]
    return SkillBundle(files=files, parent_hash=parent_hash)


def _generate(
    model: Any,
    public_inputs: Mapping[str, Any],
    frozen_base: FrozenBase,
    *,
    journal: Journal,
    operation_id: str,
    tool_schemas: Sequence[Mapping[str, Any]],
    artifact_dir: str | Path | None,
    seed: int | None,
    system_prompt: str,
    token_counter: Any,
    context_window: int,
    context_fraction: float,
    reserved_output_tokens: int,
) -> SkillBundle:
    verify_base(frozen_base)
    if thaw_json(public_inputs) != thaw_json(frozen_base.public_inputs):
        raise ValueError("Generator public inputs differ from the frozen inputs")
    payload: dict[str, Any] = {
        "role": "generator",
        "phase": "create",
        "public_inputs": thaw_json(frozen_base.public_inputs),
        "frozen_base": frozen_base.to_dict(),
        "tool_schemas": thaw_json(tuple(tool_schemas)),
    }
    admission = _context_admission(
        model,
        model_messages(payload, system_prompt),
        token_counter=token_counter,
        context_window=context_window,
        context_fraction=context_fraction,
        reserved_output_tokens=reserved_output_tokens,
        journal=journal,
        operation_id=operation_id,
    )
    try:
        raw = journaled_model_request(
            model,
            journal,
            operation_id,
            {
                "inputs": payload,
                "system_prompt": system_prompt,
                "seed": seed,
                "context_admission": admission,
            },
            model_messages(payload, system_prompt),
            seed=seed,
        )
    except UnknownOperation as exc:
        raise CreationFailure("generation_result_unknown") from exc
    try:
        bundle = parse_bundle_response(raw)
    except (ValueError, TypeError, UnicodeError, KeyError) as exc:
        # Parsing/structure failures are terminal for this call; the raw response
        # is already durable and no feedback is sent to the Generator.
        journal.record_result(
            operation_id, {"status": "creation_failed", "reason": "invalid_package"}
        )
        raise CreationFailure("invalid_package") from exc
    if artifact_dir is not None:
        seal_bundle(artifact_dir, bundle)
    journal.record_result(operation_id, {"status": "sealed", "bundle_hash": bundle.bundle_hash})
    return bundle


def generate_initial(
    model: Any,
    public_inputs: Mapping[str, Any],
    frozen_base: FrozenBase,
    *,
    journal: Journal,
    operation_id: str = "generate_initial",
    tool_schemas: Sequence[Mapping[str, Any]] = (),
    artifact_dir: str | Path | None = None,
    seed: int | None = None,
    system_prompt: str = GENERATOR_SYSTEM,
    token_counter: Any = None,
    context_window: int = 272000,
    context_fraction: float = 0.7,
    reserved_output_tokens: int = 32768,
) -> SkillBundle:
    return _generate(
        model,
        public_inputs,
        frozen_base,
        journal=journal,
        operation_id=operation_id,
        tool_schemas=tool_schemas,
        artifact_dir=artifact_dir,
        seed=seed,
        system_prompt=system_prompt,
        token_counter=token_counter,
        context_window=context_window,
        context_fraction=context_fraction,
        reserved_output_tokens=reserved_output_tokens,
    )


def _execute_learning(
    model: Any,
    previous_bundle: SkillBundle,
    public_inputs: Mapping[str, Any],
    frozen_base: FrozenBase,
    report: Any,
    *,
    journal: Journal,
    operation_id: str = "revise",
    tool_schemas: Sequence[Mapping[str, Any]] = (),
    artifact_dir: str | Path | None = None,
    seed: int | None = None,
    system_prompt: str = GENERATOR_SYSTEM,
    feedback_history: Sequence[Mapping[str, Any]] = (),
    public_trace: Mapping[str, Any] | None = None,
    token_counter: Any = None,
    context_window: int = 272000,
    context_fraction: float = 0.7,
    reserved_output_tokens: int = 32768,
    session: Any = None,
    initial: bool = False,
    conversation: RevisionConversation | None = None,
    max_turns: int | None = 120,
    max_episodes: int | None = None,
    timeout_seconds: float | None = 3600,
    deadline: float | None = None,
) -> EvolutionSubmission:
    """Execute and optionally edit a parent in its adapter-owned learning environment."""
    verify_base(frozen_base)
    verify_bundle(previous_bundle)
    if thaw_json(public_inputs) != thaw_json(frozen_base.public_inputs):
        raise ValueError("Generator public inputs differ from the frozen inputs")
    for name, limit in (("turn", max_turns), ("episode", max_episodes)):
        if limit is not None and (
            isinstance(limit, bool) or not isinstance(limit, int) or limit < 1
        ):
            raise ValueError(f"invalid_generator_{name}_budget")
    if timeout_seconds is not None and (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, (int, float))
        or not math.isfinite(timeout_seconds)
        or timeout_seconds <= 0
    ):
        raise ValueError("invalid_generator_timeout")
    if deadline is not None and (
        isinstance(deadline, bool)
        or not isinstance(deadline, (int, float))
        or not math.isfinite(deadline)
    ):
        raise ValueError("invalid_generator_deadline")
    conversation = conversation if conversation is not None else RevisionConversation()
    fixed_hash = canonical_json_sha256(
        {
            "base_hash": frozen_base.base_hash,
            "public_inputs": thaw_json(public_inputs),
            "tool_schemas": thaw_json(tool_schemas),
            "system_prompt": system_prompt,
        }
    )
    if conversation.fixed_inputs_hash not in (None, fixed_hash):
        raise ValueError("generator_fixed_inputs_changed")
    history = public_feedback_history(feedback_history, frozen_base.base_hash)
    if (
        isinstance(conversation.feedback_cursor, bool)
        or not isinstance(conversation.feedback_cursor, int)
        or not 0 <= conversation.feedback_cursor <= len(history)
    ):
        raise ValueError("generator_feedback_history_changed")
    prefix_hash = canonical_json_sha256(history[: conversation.feedback_cursor])
    if conversation.feedback_prefix_hash != prefix_hash and (
        conversation.feedback_cursor or conversation.feedback_prefix_hash is not None
    ):
        raise ValueError("generator_feedback_history_changed")
    payload = {
        "role": "generator",
        "phase": "execute_initial" if initial else "revise",
        "public_inputs": thaw_json(public_inputs),
        "frozen_base": frozen_base.to_dict(),
        "previous_bundle": previous_bundle.to_dict(),
        "tool_schemas": thaw_json(tool_schemas),
        "verification_feedback": _revision_feedback(report),
        "feedback_history": history,
        "public_trace": thaw_json(public_trace or {}),
        "initial": initial,
    }
    identity = {
        "inputs": payload,
        "system_prompt": system_prompt,
        "seed": seed,
        "max_turns": max_turns,
        "max_episodes": max_episodes,
        "timeout_seconds": timeout_seconds,
        "deadline": deadline,
    }
    result_id = f"{operation_id}/submitted"
    ended_id = f"{operation_id}/ended"

    def restore_conversation(record: Mapping[str, Any]) -> None:
        if record.get("fixed_inputs_hash") != fixed_hash:
            raise ValueError("generator_fixed_inputs_changed")
        cursor = record["feedback_cursor"]
        if (
            isinstance(cursor, bool)
            or not isinstance(cursor, int)
            or not 0 <= cursor <= len(history)
            or record.get("feedback_prefix_hash") != canonical_json_sha256(history[:cursor])
        ):
            raise ValueError("generator_feedback_history_changed")
        conversation.messages, conversation.turns = record["messages"], record["turns"]
        conversation.episodes = record.get("episodes", 0)
        conversation.fixed_inputs_hash = fixed_hash
        conversation.feedback_cursor = cursor
        conversation.feedback_prefix_hash = record["feedback_prefix_hash"]

    if journal.completed(result_id):
        restored = journal.dispatch(result_id, identity, lambda: None, external=False)
        restore_conversation(restored)
        submission = EvolutionSubmission.from_dict(restored["submission"])
        if artifact_dir is not None and not initial:
            seal_bundle(artifact_dir, submission.bundle)
        return submission
    if journal.completed(ended_id):
        ended = journal.dispatch(ended_id, identity, lambda: None, external=False)
        restore_conversation(ended)
        raise RevisionFailure(ended["reason"], dispatched=ended["dispatched"])
    messages = [*conversation.messages]
    if not messages:
        messages = [{"role": "system", "content": system_prompt}]
    elif messages[0] != {"role": "system", "content": system_prompt}:
        raise ValueError("generator_conversation_prompt_changed")
    update = {
        "role": "generator",
        "phase": "execute_initial" if initial else "revise",
        "operation_id": operation_id,
        "base_hash": frozen_base.base_hash,
        "parent_bundle_hash": previous_bundle.bundle_hash,
        "paths": {
            "candidate": "/work/candidate",
            "scratch": "/work/scratch",
            "base": "/bundle/base.json",
            "public_inputs": "/bundle/public_inputs.json",
            "trace": "/bundle/trace.json",
        },
        "verification_feedback": payload["verification_feedback"],
        "feedback_history": history[conversation.feedback_cursor :],
    }
    if not conversation.messages:
        # FrozenBase already contains the public inputs; send each fixed resource once.
        update["frozen_base"] = frozen_base.to_dict()
        update["tool_schemas"] = thaw_json(tool_schemas)
    messages.append({"role": "user", "content": canonical_json_bytes(update).decode("utf-8")})
    tools = [
        {
            "type": "function",
            "function": {
                "name": "terminal",
                "description": "Inspect the candidate and directly execute the current task.",
                "parameters": {
                    "type": "object",
                    "properties": {"command": {"type": "string"}},
                    "required": ["command"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "submit_revision",
                "description": "Seal the package and its actual public execution snapshot.",
                "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
            },
        },
    ]
    if session is not None:
        tools.extend(thaw_json(session.tool_schemas))
    _context_admission(
        model,
        messages,
        token_counter=token_counter,
        context_window=context_window,
        context_fraction=context_fraction,
        reserved_output_tokens=reserved_output_tokens,
        tools=tools,
        journal=journal,
        operation_id=f"{operation_id}/setup",
    )
    if session is None:
        raise RevisionFailure("learning_runtime_required", dispatched=False)
    dispatched = False
    execution_start = {}
    if not journal.completed(f"{operation_id}/start"):
        execution_start = session.begin_attempt(
            previous_bundle, initial=initial, operation_id=operation_id
        )
        if execution_start:
            update["execution_start"] = public_tool_result(
                execution_start,
                raw_path=session.record_tool_result(f"{operation_id}/opening", execution_start),
                raw_hash=canonical_json_sha256(execution_start),
            )
            messages[-1] = {"role": "user", "content": canonical_json_bytes(update).decode("utf-8")}
    if public_trace:
        observation = thaw_json(public_trace)
        observation.pop("public_artifacts_dir", None)
        update["execution_observation"] = {
            "trace_hash": canonical_json_sha256(observation),
            "trace_path": session.record_tool_result(f"{operation_id}/observation", observation),
        }
        messages[-1] = {"role": "user", "content": canonical_json_bytes(update).decode("utf-8")}
    start = journal.dispatch(
        f"{operation_id}/start",
        identity,
        lambda: {
            "messages": messages,
            "turns": conversation.turns,
            "episodes": conversation.episodes,
            "deadline": min(
                value
                for value in (
                    deadline,
                    time.time() + timeout_seconds if timeout_seconds is not None else None,
                )
                if value is not None
            )
            if deadline is not None or timeout_seconds is not None
            else None,
            "snapshot": session.snapshot(),
            "learning_execution_state": execution_start.get("state", {}) if execution_start else {},
            "fixed_inputs_hash": fixed_hash,
            "feedback_cursor": len(history),
            "feedback_prefix_hash": canonical_json_sha256(history),
        },
        external=False,
    )
    messages = start["messages"]
    turns = start["turns"]
    episodes = start.get("episodes", 0)
    expected_snapshot = start["snapshot"]
    step = 0

    def finish_failure(reason: str, *, sent: bool) -> None:
        ended = journal.dispatch(
            ended_id,
            identity,
            lambda: {
                "reason": reason,
                "dispatched": sent,
                "messages": messages,
                "turns": turns,
                "episodes": episodes,
                "fixed_inputs_hash": fixed_hash,
                "feedback_cursor": start["feedback_cursor"],
                "feedback_prefix_hash": start["feedback_prefix_hash"],
            },
            external=False,
        )
        restore_conversation(ended)
        raise RevisionFailure(reason, dispatched=sent)

    def expired() -> bool:
        return start["deadline"] is not None and time.time() >= start["deadline"]

    timeout_reason = "learning_timeout" if deadline is not None else "revision_timeout"
    while (max_turns is None or turns < max_turns) and (
        max_episodes is None or episodes < max_episodes
    ):
        request_id = f"{operation_id}/model-{step}"
        if journal.status(request_id) == "UNKNOWN" and not journal.received(request_id):
            raise UnknownOperation("authoring model request has an unknown result")
        if not journal.completed(request_id) and not journal.received(request_id) and expired():
            finish_failure(timeout_reason, sent=dispatched)
        if (
            not journal.completed(request_id)
            and not journal.received(request_id)
            and session.snapshot()["workspace_hash"] != expected_snapshot["workspace_hash"]
        ):
            finish_failure("authoring_workspace_changed", sent=dispatched)
        try:
            admission = _context_admission(
                model,
                messages,
                token_counter=token_counter,
                context_window=context_window,
                context_fraction=context_fraction,
                reserved_output_tokens=reserved_output_tokens,
                tools=tools,
                journal=journal,
                operation_id=request_id,
            )
        except GeneratorContextBudgetExhausted:
            if dispatched:
                finish_failure("generator_context_budget_exhausted", sent=True)
            raise
        try:
            raw = journaled_model_request(
                model,
                journal,
                request_id,
                {
                    "messages": messages,
                    "tools": tools,
                    "identity": identity,
                    "context_admission": admission,
                },
                messages,
                tools=tools,
                seed=seed,
                max_output_tokens=getattr(
                    getattr(model, "config", None),
                    "max_output_tokens",
                    reserved_output_tokens,
                ),
            )
        except Exception as exc:
            if journal.status(request_id) == "NOT_SENT" and not dispatched:
                from .model import is_credential_error

                if is_credential_error(exc):
                    raise
                finish_failure("revision_request_not_sent", sent=False)
            if journal.status(request_id) == "NOT_SENT":
                finish_failure("revision_request_not_sent", sent=True)
            if journal.status(request_id) == "RECEIVED_INVALID":
                turns += 1
                finish_failure("invalid_revision_response", sent=True)
            raise
        dispatched = True
        turns += 1
        conversation.turns = turns
        step += 1
        if not isinstance(raw, Mapping):
            finish_failure("invalid_revision_response", sent=True)
        assistant = {
            name: thaw_json(raw[name])
            for name in (
                "role",
                "content",
                "tool_calls",
                "_bedrock_output_items",
                "response_id",
                "usage",
            )
            if name in raw
        }
        assistant.setdefault("role", "assistant")
        messages.append(assistant)
        if raw.get("finish_reason") == "length":
            finish_failure("generator_output_budget_exhausted", sent=True)
        calls = raw.get("tool_calls") or ()
        episode = journal.dispatch(
            f"{request_id}/episode",
            {"response_hash": canonical_json_sha256(raw), "episodes_before": episodes},
            lambda calls=calls: {"increment": _effective_episode(calls)},
            external=False,
        )
        episodes += episode["increment"]
        conversation.episodes = episodes
        if not calls:
            messages.append(
                {
                    "role": "user",
                    "content": "Submit via submit_revision; prose does not seal a package.",
                }
            )
            continue
        for index, call in enumerate(calls):
            function = call.get("function", {})
            tool_id = f"{request_id}/tool-{index}"
            arguments = function.get("arguments", {})
            try:
                arguments = json.loads(arguments) if isinstance(arguments, str) else arguments
                if not isinstance(arguments, Mapping):
                    raise ValueError("tool arguments must be an object")
            except (ValueError, TypeError):
                arguments = {"invalid": True}
            tool_identity = {
                "name": function.get("name"),
                "arguments": arguments,
                "parent_hash": previous_bundle.bundle_hash,
                "base_hash": frozen_base.base_hash,
            }
            if journal.status(tool_id) == "UNKNOWN":
                raise UnknownOperation("authoring tool operation has an unknown result")
            if not journal.completed(tool_id) and expired():
                finish_failure(timeout_reason, sent=dispatched)

            def execute(
                function: Any = function,
                arguments: Any = arguments,
                expected_snapshot: Any = expected_snapshot,
                tool_id: str = tool_id,
            ) -> dict[str, Any]:
                if session.snapshot()["workspace_hash"] != expected_snapshot["workspace_hash"]:
                    raise ValueError("authoring_workspace_changed_without_sealed_operation")
                if (
                    function.get("name") == "terminal"
                    and set(arguments) == {"command"}
                    and isinstance(arguments["command"], str)
                    and arguments["command"].strip()
                ):
                    result = session.terminal(arguments["command"]).to_dict()
                    return {"result": result, "snapshot": session.snapshot()}
                if function.get("name") == "submit_revision" and not arguments:
                    try:
                        submission = session.submit(
                            previous_bundle, initial=initial, operation_id=tool_id
                        )
                        if initial and submission.bundle.bundle_hash != previous_bundle.bundle_hash:
                            raise ValueError("initial_execution_modified_bundle")
                        return {"submission": submission.to_dict(), "snapshot": session.snapshot()}
                    except (ValueError, TypeError, UnicodeError) as exc:
                        return {
                            "result": {"failure": "invalid_package", "detail": str(exc)},
                            "snapshot": session.snapshot(),
                        }
                if function.get("name") in {
                    item["function"]["name"] for item in session.tool_schemas
                }:
                    result = session.execute_tool(function["name"], arguments, operation_id=tool_id)
                    return {"result": result, "snapshot": session.snapshot()}
                return {
                    "result": {"failure": "forbidden_or_invalid_learning_tool"},
                    "snapshot": session.snapshot(),
                }

            sealed = journal.dispatch(tool_id, tool_identity, execute)
            expected_snapshot = sealed["snapshot"]
            raw_result = {"status": "submitted"} if "submission" in sealed else sealed["result"]
            result = public_tool_result(
                raw_result,
                raw_path=session.record_tool_result(tool_id, raw_result),
                raw_hash=canonical_json_sha256(raw_result),
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.get("id", tool_id),
                    "content": canonical_json_bytes(result).decode("utf-8"),
                }
            )
            if result.get("failure") == "cleanup_failed":
                # Replay does not call terminal(), so restore the cleanup flag
                # before closing this session or considering another tool.
                session.cleanup_failed = True
                finish_failure("cleanup_failed", sent=dispatched)
            if initial and canonical_json_sha256(
                expected_snapshot["files"]
            ) != canonical_json_sha256(thaw_json(previous_bundle.files)):
                finish_failure("initial_execution_modified_bundle", sent=dispatched)
            if initial and raw_result.get("failure") == "invalid_package":
                finish_failure("invalid_package", sent=dispatched)
            if "submission" in sealed:
                # Finish all advertised calls in this assistant message before retaining
                # the conversation. Later calls cannot change an already submitted bundle.
                for remaining in calls[index + 1 :]:
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": remaining.get("id", ""),
                            "content": '{"failure":"revision_already_submitted"}',
                        }
                    )
                packet = {
                    "submission": sealed["submission"],
                    "messages": messages,
                    "turns": turns,
                    "episodes": episodes,
                    "fixed_inputs_hash": fixed_hash,
                    "feedback_cursor": start["feedback_cursor"],
                    "feedback_prefix_hash": start["feedback_prefix_hash"],
                }
                restored = journal.dispatch(
                    result_id, identity, lambda packet=packet: packet, external=False
                )
                restore_conversation(restored)
                submission = EvolutionSubmission.from_dict(restored["submission"])
                if artifact_dir is not None and not initial:
                    seal_bundle(artifact_dir, submission.bundle)
                return submission
    reason = (
        "generator_episode_budget_exhausted"
        if max_episodes is not None and episodes >= max_episodes
        else "generator_turn_budget_exhausted"
    )
    finish_failure(reason, sent=dispatched)


def execute_initial(
    model: Any,
    initial_bundle: SkillBundle,
    public_inputs: Mapping[str, Any],
    frozen_base: FrozenBase,
    **kwargs: Any,
) -> EvolutionSubmission:
    """Execute sealed S0 after creation; package edits cannot be attributed to S0."""
    kwargs.setdefault("operation_id", "execute_initial")
    return _execute_learning(
        model, initial_bundle, public_inputs, frozen_base, {}, initial=True, **kwargs
    )


def revise(
    model: Any,
    previous_bundle: SkillBundle,
    public_inputs: Mapping[str, Any],
    frozen_base: FrozenBase,
    report: Any,
    **kwargs: Any,
) -> EvolutionSubmission:
    """Inherit, directly execute, and explicitly submit one revision attempt."""
    return _execute_learning(model, previous_bundle, public_inputs, frozen_base, report, **kwargs)
