"""Fresh-context compiler with an exact, auditable input allowlist."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .batch_constants import (
    COMPILER_MAX_INPUT_TOKENS,
    COMPILER_MAX_OUTPUT_TOKENS,
    COMPILER_MAX_SKILL_TOKENS,
    EXPERIMENT_ROOT,
    SELECTION_K,
)
from .batch_model import ModelClient, ModelClientError

_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_ALLOWED_FRONTMATTER = {"name", "description", "metadata"}
_ACQUISITION_TRACE_SCHEMA = "r2sp.compiler-acquisition-trace.v1"
_SEARCH_RESULT_REDACTION = (
    "[search_web output redacted; selected documents are provided separately]"
)
_SELECTION_RESULT_REDACTION = (
    "[select_docs output redacted; selected documents are provided separately]"
)
_FORBIDDEN_TRACE_FIELDS = {
    "db_snapshot",
    "gold",
    "gold_actions",
    "official_result",
    "official_reward",
    "required_documents",
    "reasoning_content",
    "reward",
    "reward_breakdown",
    "scenario",
    "task_id",
    "task_success",
}


@dataclass(frozen=True)
class TauSkillArtifact:
    text: str
    skill_sha256: str
    valid: bool
    source_page_ids: tuple[str, ...]
    failure: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "skill_sha256": self.skill_sha256,
            "valid": self.valid,
            "source_page_ids": list(self.source_page_ids),
            "failure": self.failure,
        }


def validate_skill_text(text: str) -> str | None:
    if not isinstance(text, str) or not text.strip():
        return "empty"
    if "\x00" in text or not text.startswith("---\n"):
        return "frontmatter_missing"
    end = text.find("\n---\n", 4)
    if end < 0:
        return "frontmatter_unterminated"
    try:
        metadata = yaml.safe_load(text[4:end])
    except yaml.YAMLError:
        return "frontmatter_yaml"
    if not isinstance(metadata, dict) or set(metadata) - _ALLOWED_FRONTMATTER:
        return "frontmatter_fields"
    if not isinstance(metadata.get("name"), str) or _NAME_RE.fullmatch(metadata["name"]) is None:
        return "name"
    if not isinstance(metadata.get("description"), str) or not metadata["description"].strip():
        return "description"
    if not text[end + 5 :].strip():
        return "body"
    return None


def _page(page: Any) -> dict[str, str]:
    if isinstance(page, Mapping):
        value = dict(page)
    elif hasattr(page, "to_open_dict"):
        value = page.to_open_dict()
    elif hasattr(page, "to_page_mapping"):
        value = page.to_page_mapping()
    else:
        raise TypeError("opened pages must be mappings or Page-like values")
    page_id = value.get("page_id")
    title = value.get("title")
    body = value.get("body")
    content_sha256 = value.get("content_sha256", value.get("content_hash"))
    if not all(isinstance(item, str) and item for item in (page_id, title, body, content_sha256)):
        raise ValueError("opened page missing required public fields")
    observed = hashlib.sha256(body.encode("utf-8")).hexdigest()
    if content_sha256 != observed:
        raise ValueError("opened page content hash mismatch")
    return {
        "page_id": page_id,
        "title": title,
        "body": body,
        "content_sha256": content_sha256,
    }


def _forbidden_trace_field(name: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", name.casefold()).strip("_")
    compact = normalized.replace("_", "")
    return (
        normalized in _FORBIDDEN_TRACE_FIELDS
        or normalized.startswith(("evaluator_", "gold_", "hidden_"))
        or normalized.endswith(("_evaluator", "_gold"))
        or compact
        in {
            "dbsnapshot",
            "evaluator",
            "gold",
            "goldactions",
            "hidden",
            "officialresult",
            "officialreward",
            "requireddocuments",
            "reasoningcontent",
            "reward",
            "rewardbreakdown",
            "scenario",
            "taskid",
            "tasksuccess",
        }
    )


def _sanitize_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: _sanitize_json(item)
            for key, item in value.items()
            if isinstance(key, str) and not _forbidden_trace_field(key)
        }
    if isinstance(value, list):
        return [_sanitize_json(item) for item in value]
    return value


def _sanitize_tool_content(value: Any) -> Any:
    """Remove hidden JSON fields while preserving a visible business-tool result."""

    if not isinstance(value, str):
        return _sanitize_json(value)
    try:
        decoded = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return value
    if not isinstance(decoded, (dict, list)):
        return value
    return json.dumps(
        _sanitize_json(decoded),
        ensure_ascii=False,
        sort_keys=True,
        allow_nan=False,
    )


def _sanitize_tool_call(value: Mapping[str, Any]) -> dict[str, Any]:
    name = value.get("name")
    clean: dict[str, Any] = {}
    for key in ("id", "name", "requestor"):
        item = value.get(key)
        if isinstance(item, str) and item:
            clean[key] = item

    arguments = value.get("arguments")
    if isinstance(arguments, Mapping):
        safe_arguments = _sanitize_json(arguments)
        if name == "search_web":
            safe_arguments = (
                {"query": safe_arguments["query"]}
                if isinstance(safe_arguments.get("query"), str)
                else {}
            )
        elif name == "select_docs":
            safe_arguments = (
                {"page_ids": safe_arguments["page_ids"]}
                if isinstance(safe_arguments.get("page_ids"), list)
                else {}
            )
        clean["arguments"] = safe_arguments
    return clean


def _direct_tool_call_payload(value: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize the compact tool-call form used by scripted trajectories."""

    name = value.get("name")
    if not isinstance(name, str) or not name:
        return {}
    if isinstance(value.get("arguments"), Mapping):
        return _sanitize_tool_call(value)

    clean = {
        key: _sanitize_json(item)
        for key, item in value.items()
        if isinstance(key, str) and not _forbidden_trace_field(key)
    }
    if name == "search_web":
        return {
            **{key: clean[key] for key in ("id", "name", "requestor") if key in clean},
            **({"query": clean["query"]} if isinstance(clean.get("query"), str) else {}),
        }
    if name == "select_docs":
        return {
            **{key: clean[key] for key in ("id", "name", "requestor") if key in clean},
            **({"page_ids": clean["page_ids"]} if isinstance(clean.get("page_ids"), list) else {}),
        }
    return clean


def _looks_like_retrieval_result(payload: Mapping[str, Any]) -> str | None:
    if "results" in payload:
        return "search_web"
    if "documents" in payload:
        return "select_docs"
    content = payload.get("content")
    if not isinstance(content, str):
        return None
    try:
        decoded = json.loads(content)
    except json.JSONDecodeError:
        return None
    if isinstance(decoded, Mapping):
        if "results" in decoded:
            return "search_web"
        if "documents" in decoded:
            return "select_docs"
    return None


def sanitize_acquisition_trace(public_trace: Mapping[str, Any]) -> dict[str, Any]:
    """Return a detached compiler-safe view of an acquisition trajectory.

    The participant conversation, tool requests, and ordinary business-tool outputs
    remain visible. Retrieval outputs are removed because they may contain any of the
    corpus documents; the compiler receives the exact selected documents through the
    separate ``documents_actually_read`` field.
    """

    if not isinstance(public_trace, Mapping):
        raise TypeError("public_trace must be a mapping")
    # Round-tripping first both validates the JSON boundary and guarantees that the
    # returned trace shares no mutable containers with the acquisition artifact.
    detached = json.loads(json.dumps(public_trace, ensure_ascii=False, allow_nan=False))
    raw_events = detached.get("events")
    if not isinstance(raw_events, list):
        raise ValueError("public_trace.events must be a list")

    tool_names_by_id: dict[str, str] = {}
    anonymous_tool_names: list[str] = []
    events: list[dict[str, Any]] = []
    for raw_event in raw_events:
        if not isinstance(raw_event, Mapping):
            raise ValueError("public_trace events must be mappings")
        actor = raw_event.get("actor")
        kind = raw_event.get("kind")
        payload = raw_event.get("payload", {})
        if actor not in {"user", "assistant", "tool"}:
            continue
        if not isinstance(kind, str) or not kind or not isinstance(payload, Mapping):
            raise ValueError("public_trace event fields are invalid")

        clean_payload: dict[str, Any]
        if actor in {"user", "assistant"} and kind == "message":
            clean_payload = {}
            content = payload.get("content")
            if isinstance(content, str):
                clean_payload["content"] = content
            calls = payload.get("tool_calls")
            if isinstance(calls, list):
                clean_calls = [
                    _sanitize_tool_call(call) for call in calls if isinstance(call, Mapping)
                ]
                clean_calls = [call for call in clean_calls if call.get("name")]
                if clean_calls:
                    clean_payload["tool_calls"] = clean_calls
                    for call in clean_calls:
                        name = call["name"]
                        call_id = call.get("id")
                        if isinstance(call_id, str):
                            tool_names_by_id[call_id] = name
                        else:
                            anonymous_tool_names.append(name)
        elif actor in {"user", "assistant"} and kind == "tool_call":
            clean_payload = _direct_tool_call_payload(payload)
            name = clean_payload.get("name")
            call_id = clean_payload.get("id")
            if isinstance(name, str):
                if isinstance(call_id, str):
                    tool_names_by_id[call_id] = name
                else:
                    anonymous_tool_names.append(name)
        elif actor == "tool" and kind == "tool_result":
            result_id = payload.get("id")
            name = payload.get("name")
            if not isinstance(name, str) and isinstance(result_id, str):
                name = tool_names_by_id.get(result_id)
            if not isinstance(name, str) and anonymous_tool_names:
                name = anonymous_tool_names.pop(0)
            if not isinstance(name, str):
                name = _looks_like_retrieval_result(payload)

            if name in {"search_web", "select_docs"}:
                clean_payload = {
                    key: _sanitize_json(payload[key])
                    for key in ("id", "requestor", "error")
                    if key in payload
                }
                clean_payload["content"] = (
                    _SEARCH_RESULT_REDACTION
                    if name == "search_web"
                    else _SELECTION_RESULT_REDACTION
                )
            else:
                clean_payload = _sanitize_json(payload)
                if "content" in clean_payload:
                    clean_payload["content"] = _sanitize_tool_content(clean_payload["content"])
        else:
            # Unknown participant event shapes are excluded instead of becoming an
            # accidental path for hidden runtime or evaluator state.
            continue

        events.append(
            {
                "sequence": len(events),
                "actor": actor,
                "kind": kind,
                "payload": clean_payload,
            }
        )

    return {"schema_version": _ACQUISITION_TRACE_SCHEMA, "events": events}


class TauSkillCompiler:
    def __init__(
        self,
        client: ModelClient,
        *,
        include_public_trace: bool = False,
        max_input_tokens: int = COMPILER_MAX_INPUT_TOKENS,
        max_skill_tokens: int = COMPILER_MAX_SKILL_TOKENS,
        max_generation_tokens: int = COMPILER_MAX_OUTPUT_TOKENS,
        chars_per_token: int = 4,
        prompt_path: Path = EXPERIMENT_ROOT / "prompts" / "batch_compiler_system.md",
    ) -> None:
        if not all(
            isinstance(value, int) and not isinstance(value, bool) and value > 0
            for value in (
                max_input_tokens,
                max_skill_tokens,
                max_generation_tokens,
                chars_per_token,
            )
        ):
            raise ValueError("compiler limits must be positive integers")
        self.client = client
        self.include_public_trace = bool(include_public_trace)
        self.max_input_tokens = max_input_tokens
        self.max_skill_tokens = max_skill_tokens
        self.max_generation_tokens = max_generation_tokens
        self.chars_per_token = chars_per_token
        self.system_prompt = prompt_path.read_text(encoding="utf-8")

    def _count_tokens(self, text: str) -> int:
        counter = getattr(self.client, "count_tokens", None)
        if callable(counter):
            return int(counter(text))
        return (len(text) + self.chars_per_token - 1) // self.chars_per_token

    def build_payload(
        self,
        *,
        first_user_utterance: str,
        opened_pages: Sequence[Any],
        public_trace: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not isinstance(first_user_utterance, str) or not first_user_utterance.strip():
            raise ValueError("first_user_utterance is required")
        documents: list[dict[str, str]] = []
        seen: set[str] = set()
        for item in opened_pages:
            clean = _page(item)
            if clean["page_id"] not in seen:
                seen.add(clean["page_id"])
                documents.append(clean)
        if len(documents) != SELECTION_K:
            raise ValueError(f"compiler requires exactly {SELECTION_K} unique selected documents")
        payload: dict[str, Any] = {
            "task": first_user_utterance,
            "documents_actually_read": documents,
        }
        if self.include_public_trace:
            if not isinstance(public_trace, Mapping):
                raise ValueError("public_trace is required when include_public_trace=true")
            payload["acquisition_trace"] = sanitize_acquisition_trace(public_trace)
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, allow_nan=False)
        compiler_text = self.system_prompt + "\n" + encoded
        if self._count_tokens(compiler_text) > self.max_input_tokens:
            raise ValueError(
                "compiler payload exceeds fixed input budget; full pages are not truncated"
            )
        return payload

    def compile(self, *, seed: int | None = None, **inputs: Any) -> TauSkillArtifact:
        payload = self.build_payload(**inputs)
        source_ids = tuple(item["page_id"] for item in payload["documents_actually_read"])
        try:
            response = self.client.complete(
                [
                    {"role": "system", "content": self.system_prompt},
                    {
                        "role": "user",
                        "content": json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    },
                ],
                tools=None,
                seed=seed,
                max_output_tokens=self.max_generation_tokens,
            )
        except ModelClientError as exc:
            return self._invalid(source_ids, f"model_{exc.code}")
        if response.get("tool_calls"):
            return self._invalid(source_ids, "compiler_returned_tool_calls")
        text = response.get("content")
        if not isinstance(text, str) or not text.strip():
            return self._invalid(source_ids, "empty_skill")
        text = text.strip() + "\n"
        if self._count_tokens(text) > self.max_skill_tokens:
            return self._invalid(source_ids, "skill_too_long")
        error = validate_skill_text(text)
        if error is not None:
            return self._invalid(source_ids, f"invalid_skill_{error}")
        return TauSkillArtifact(
            text=text,
            skill_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            valid=True,
            source_page_ids=source_ids,
        )

    @staticmethod
    def _invalid(source_ids: tuple[str, ...], failure: str) -> TauSkillArtifact:
        return TauSkillArtifact(
            text="",
            skill_sha256=hashlib.sha256(b"").hexdigest(),
            valid=False,
            source_page_ids=source_ids,
            failure=failure,
        )
