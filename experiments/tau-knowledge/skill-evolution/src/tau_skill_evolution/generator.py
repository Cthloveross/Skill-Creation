"""One initial generation, then explicit full-package inheritance revisions."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from tau_skill_evolution.core._canonical import canonical_json_bytes, thaw_json

from .artifacts import (
    FrozenBase,
    SkillBundle,
    seal_bundle,
    validate_relative_path,
    verify_base,
    verify_bundle,
)
from .constants import EXPERIMENT_ROOT
from .journal import Journal, UnknownOperation


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


def public_feedback_history(
    history: Sequence[Mapping[str, Any]], base_hash: str
) -> list[dict[str, Any]]:
    """Project host-owned same-task feedback; never repeat historical test source."""
    fields = (
        "test_version",
        "test_hash",
        "passed",
        "pass_rate",
        "diagnosis",
        "recommendations",
        "failure",
        "program_error",
    )
    result_fields = ("nodeid", "stage", "outcome", "exception", "xfail", "detail")
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
            if (
                not isinstance(item.get("passed"), bool)
                or isinstance(item.get("pass_rate"), bool)
                or not isinstance(item.get("pass_rate"), (int, float))
                or not math.isfinite(item["pass_rate"])
                or not 0 <= item["pass_rate"] <= 1
                or not isinstance(item.get("diagnosis", ""), str)
                or not isinstance(item.get("recommendations", ()), (list, tuple))
                or any(not isinstance(value, str) for value in item.get("recommendations", ()))
            ):
                raise ValueError("invalid_public_verification_feedback")
            event.update({name: thaw_json(item[name]) for name in fields if name in item})
            results = item.get("results", ())
            if not isinstance(results, (list, tuple)) or any(
                not isinstance(entry, Mapping) for entry in results
            ):
                raise ValueError("invalid_public_verification_results")
            event["results"] = [
                {name: thaw_json(entry[name]) for name in result_fields if name in entry}
                for entry in results
            ]
            if any(
                not isinstance(value, (str, bool, type(None)))
                for entry in event["results"]
                for value in entry.values()
            ):
                raise ValueError("invalid_public_verification_result_fields")
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
    if configured_output > reserved_output_tokens:
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
    observed = counter.count(messages)
    if isinstance(observed, bool) or not isinstance(observed, int) or observed < 0:
        raise ValueError("invalid_generator_token_count")
    admission.update(input_tokens=observed, basis=getattr(counter, "basis", "configured_counter"))
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
    previous_bundle: SkillBundle | None,
    report: Any,
    artifact_dir: str | Path | None,
    seed: int | None,
    system_prompt: str,
    feedback_history: Sequence[Mapping[str, Any]],
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
        "phase": "create" if previous_bundle is None else "revise",
        "public_inputs": thaw_json(frozen_base.public_inputs),
        "frozen_base": frozen_base.to_dict(),
        "tool_schemas": thaw_json(tuple(tool_schemas)),
    }
    if previous_bundle is not None:
        verify_bundle(previous_bundle)
        payload["previous_bundle"] = previous_bundle.to_dict()
        payload["verification_report"] = report.to_dict() if hasattr(report, "to_dict") else report
        payload["feedback_history"] = public_feedback_history(
            feedback_history, frozen_base.base_hash
        )
    elif feedback_history:
        raise ValueError("initial_generation_cannot_inherit_feedback_history")
    admission = _context_admission(
        model,
        model_messages(payload, system_prompt),
        token_counter=token_counter,
        context_window=context_window,
        context_fraction=context_fraction,
        reserved_output_tokens=reserved_output_tokens,
    )
    try:
        raw = journal.dispatch(
            operation_id,
            {
                "inputs": payload,
                "system_prompt": system_prompt,
                "seed": seed,
                "context_admission": admission,
            },
            lambda: invoke_model(model, payload, system_prompt, seed=seed),
        )
    except UnknownOperation as exc:
        raise CreationFailure("generation_result_unknown") from exc
    try:
        bundle = parse_bundle_response(
            raw, parent_hash=None if previous_bundle is None else previous_bundle.bundle_hash
        )
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
        previous_bundle=None,
        report=None,
        artifact_dir=artifact_dir,
        seed=seed,
        system_prompt=system_prompt,
        feedback_history=(),
        token_counter=token_counter,
        context_window=context_window,
        context_fraction=context_fraction,
        reserved_output_tokens=reserved_output_tokens,
    )


def revise(
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
        previous_bundle=previous_bundle,
        report=report,
        artifact_dir=artifact_dir,
        seed=seed,
        system_prompt=system_prompt,
        feedback_history=feedback_history,
        token_counter=token_counter,
        context_window=context_window,
        context_fraction=context_fraction,
        reserved_output_tokens=reserved_output_tokens,
    )
