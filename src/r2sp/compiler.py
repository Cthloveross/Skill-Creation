"""Fresh-context, allow-listed text skill compiler."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import yaml

from .model_client import ModelClient, ModelClientError

NEUTRAL_PLACEHOLDER = """---
name: neutral-placeholder
description: No reusable workflow was generated for this episode.
---

Do not change task behavior. Follow the current user request and trusted system policy.
"""

_DOCUMENT_FIELDS = (
    "resource_id",
    "app_name",
    "api_name",
    "title",
    "body",
    "content_hash",
)
_TRACE_FIELDS = (
    "call_index",
    "app",
    "api",
    "args",
    "ok",
    "result",
    "error_code",
    "error_message",
)
_SKILL_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_FRONTMATTER_FIELDS = frozenset({"name", "description", "metadata"})
_DEFAULT_COMPILER_PROMPT = (
    "Compile reusable workflow guidance using only the allow-listed JSON payload. "
    "Return one plain-text SKILL.md with YAML frontmatter containing a "
    "lowercase-hyphenated name and a precise description, followed by a non-empty "
    "Markdown body; return no tool calls. The harness loads the artifact as text "
    "only: it does not execute code blocks, install dependencies, or change the "
    "agent's tools or permissions."
)


@dataclass(frozen=True)
class SkillArtifact:
    content: str
    skill_hash: str
    valid: bool
    source_resource_ids: tuple[str, ...]
    failure: str | None = None
    placeholder: bool = False

    @property
    def text(self) -> str:
        return self.content


class SkillCompiler:
    """Compile only task, actually-read documents, API trace and task outcome."""

    def __init__(
        self,
        client: ModelClient,
        *,
        max_input_tokens: int = 32768,
        max_skill_tokens: int = 4096,
        max_generation_tokens: int | None = None,
        chars_per_token: int = 4,
        system_prompt: str = _DEFAULT_COMPILER_PROMPT,
        token_counter: Callable[[str], int] | None = None,
    ) -> None:
        generation_tokens = (
            max_skill_tokens if max_generation_tokens is None else max_generation_tokens
        )
        if (
            max_input_tokens <= 0
            or max_skill_tokens <= 0
            or generation_tokens <= 0
            or chars_per_token <= 0
        ):
            raise ValueError("compiler limits must be positive")
        self.client = client
        self.max_input_tokens = int(max_input_tokens)
        self.max_skill_tokens = int(max_skill_tokens)
        self.max_generation_tokens = int(generation_tokens)
        self.chars_per_token = int(chars_per_token)
        if token_counter is not None and not callable(token_counter):
            raise TypeError("token_counter must be callable or None")
        self.token_counter = token_counter
        if not isinstance(system_prompt, str) or not system_prompt.strip():
            raise ValueError("system_prompt must be non-empty text")
        self.system_prompt = system_prompt.strip()

    def build_payload(
        self,
        task: str,
        read_documents: Sequence[Any],
        normalized_trace: Sequence[Any],
        task_success: bool,
    ) -> dict[str, Any]:
        if not isinstance(task, str):
            raise TypeError("task must be text")
        if not isinstance(task_success, bool):
            raise TypeError("task_success must be boolean")
        documents = [_clean_document(value) for value in read_documents]
        trace = [_clean_trace_item(value) for value in normalized_trace]
        payload: dict[str, Any] = {
            "task": task,
            "documents_actually_read": documents,
            "normalized_api_trace": trace,
            "task_success": task_success,
        }
        fitted = _fit_payload(
            payload,
            max_chars=self.max_input_tokens * self.chars_per_token,
        )
        if self.token_counter is not None:
            fitted = _fit_payload_to_token_limit(
                fitted,
                max_tokens=self.max_input_tokens,
                token_counter=self.token_counter,
            )
        return fitted

    def compile(
        self,
        task: str,
        read_documents: Sequence[Any],
        normalized_trace: Sequence[Any],
        task_success: bool,
        *,
        seed: int | None = None,
    ) -> SkillArtifact:
        payload = self.build_payload(task, read_documents, normalized_trace, task_success)
        source_ids = tuple(
            str(document["resource_id"])
            for document in payload["documents_actually_read"]
            if document.get("resource_id") is not None
        )
        messages = [
            {
                "role": "system",
                "content": self.system_prompt,
            },
            {
                "role": "user",
                "content": json.dumps(payload, ensure_ascii=False, sort_keys=True),
            },
        ]
        try:
            response = self.client.complete(
                messages,
                tools=None,
                seed=seed,
                max_output_tokens=self.max_generation_tokens,
            )
        except ModelClientError as exc:
            return _placeholder(source_ids, "model_" + exc.code)

        if response.get("tool_calls"):
            return _placeholder(source_ids, "compiler_returned_tool_calls")
        content = response.get("content")
        if not isinstance(content, str) or not content.strip():
            return _placeholder(source_ids, "empty_skill")
        content = content.strip() + "\n"
        if "\x00" in content:
            return _placeholder(source_ids, "invalid_skill_text")
        if len(content) > self.max_skill_tokens * self.chars_per_token:
            return _placeholder(source_ids, "skill_too_long")
        validation_error = validate_skill_text(content)
        if validation_error is not None:
            return _placeholder(source_ids, "invalid_skill_" + validation_error)
        return SkillArtifact(
            content=content,
            skill_hash=_sha256(content),
            valid=True,
            source_resource_ids=source_ids,
        )


def _clean_document(value: Any) -> dict[str, Any]:
    mapped = _mapping(value)
    document = {
        field: mapped[field]
        for field in _DOCUMENT_FIELDS
        if field in mapped and mapped[field] is not None
    }
    if "resource_id" in document:
        document["resource_id"] = str(document["resource_id"])
    for field in ("app_name", "api_name", "title", "body", "content_hash"):
        if field in document:
            document[field] = str(document[field])
    if not isinstance(document.get("body"), str):
        raise ValueError("each read document must include a text body")
    return document


def _clean_trace_item(value: Any) -> dict[str, Any]:
    mapped = _mapping(value)
    # This allow-list blocks hidden reasoning, evaluator data and arbitrary fields.
    cleaned = {field: _json_value(mapped[field]) for field in _TRACE_FIELDS if field in mapped}
    return cleaned


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        mapped = to_dict()
        if isinstance(mapped, Mapping):
            return dict(mapped)
    if dataclasses.is_dataclass(value):
        return dataclasses.asdict(value)
    raise TypeError("compiler inputs must be mapping-like")


def _json_value(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False, default=str))
    except (TypeError, ValueError):
        return str(value)


def _fit_payload(payload: dict[str, Any], *, max_chars: int) -> dict[str, Any]:
    """Apply v0.3's deterministic task/docs-prefix/latest-trace policy."""

    def size(value: Mapping[str, Any]) -> int:
        return len(json.dumps(value, ensure_ascii=False, sort_keys=True))

    if size(payload) <= max_chars:
        return payload
    fitted = {
        "task": str(payload["task"]),
        "documents_actually_read": [dict(item) for item in payload["documents_actually_read"]],
        "normalized_api_trace": list(payload["normalized_api_trace"]),
        "task_success": payload["task_success"],
    }
    # Keep the complete task when practical, then latest trace entries and an
    # equal prefix from every actually-read document.
    fitted["task"] = fitted["task"][: max(64, max_chars // 4)]
    trace_budget = max(64, max_chars // 4)
    latest = []
    used = 2
    for item in reversed(fitted["normalized_api_trace"]):
        item_size = len(json.dumps(item, ensure_ascii=False, sort_keys=True)) + 1
        if latest and used + item_size > trace_budget:
            break
        latest.append(item)
        used += item_size
    fitted["normalized_api_trace"] = list(reversed(latest))

    docs = fitted["documents_actually_read"]
    metadata_size = size(
        {
            **fitted,
            "documents_actually_read": [{**doc, "body": ""} for doc in docs],
        }
    )
    body_budget = max(0, max_chars - metadata_size)
    prefix = body_budget // max(1, len(docs))
    for document in docs:
        document["body"] = str(document.get("body", ""))[:prefix]

    while size(fitted) > max_chars and prefix > 0:
        prefix = max(0, prefix - max(1, (size(fitted) - max_chars) // max(1, len(docs))))
        for document in docs:
            document["body"] = document["body"][:prefix]
    if size(fitted) > max_chars:
        # Extremely small test configurations may not fit metadata. Preserve
        # the contract and deterministically shorten non-body strings.
        for document in docs:
            for field in ("title", "app_name", "api_name", "content_hash"):
                if field in document:
                    document[field] = str(document[field])[:32]
        fitted["task"] = fitted["task"][:64]
        fitted["normalized_api_trace"] = []
    return fitted


def _fit_payload_to_token_limit(
    payload: dict[str, Any],
    *,
    max_tokens: int,
    token_counter: Callable[[str], int],
) -> dict[str, Any]:
    """Enforce the pinned tokenizer limit after deterministic char fitting."""

    def count(value: Mapping[str, Any]) -> int:
        observed = token_counter(
            json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        )
        if isinstance(observed, bool) or not isinstance(observed, int) or observed < 0:
            raise ValueError("token_counter returned an invalid count")
        return observed

    fitted = {
        "task": str(payload["task"]),
        "documents_actually_read": [dict(item) for item in payload["documents_actually_read"]],
        "normalized_api_trace": [dict(item) for item in payload["normalized_api_trace"]],
        "task_success": payload["task_success"],
    }
    if count(fitted) <= max_tokens:
        return fitted

    documents = fitted["documents_actually_read"]
    original_bodies = [str(document.get("body", "")) for document in documents]
    upper = max((len(body) for body in original_bodies), default=0)
    low, high = 0, upper
    while low < high:
        prefix = (low + high + 1) // 2
        for document, body in zip(documents, original_bodies, strict=True):
            document["body"] = body[:prefix]
        if count(fitted) <= max_tokens:
            low = prefix
        else:
            high = prefix - 1
    for document, body in zip(documents, original_bodies, strict=True):
        document["body"] = body[:low]

    while fitted["normalized_api_trace"] and count(fitted) > max_tokens:
        # Drop the oldest entry and retain the latest trace suffix.
        fitted["normalized_api_trace"].pop(0)

    if count(fitted) > max_tokens:
        original_task = fitted["task"]
        low, high = 0, len(original_task)
        while low < high:
            prefix = (low + high + 1) // 2
            fitted["task"] = original_task[:prefix]
            if count(fitted) <= max_tokens:
                low = prefix
            else:
                high = prefix - 1
        fitted["task"] = original_task[:low]

    observed = count(fitted)
    if observed > max_tokens:
        raise ValueError(
            "compiler metadata cannot fit the pinned input-token limit: "
            f"observed={observed}, limit={max_tokens}"
        )
    return fitted


def _placeholder(source_ids: tuple[str, ...], failure: str) -> SkillArtifact:
    return SkillArtifact(
        content=NEUTRAL_PLACEHOLDER,
        skill_hash=_sha256(NEUTRAL_PLACEHOLDER),
        valid=False,
        source_resource_ids=source_ids,
        failure=failure,
        placeholder=True,
    )


def validate_skill_text(content: str) -> str | None:
    """Return a stable error code when text is not a loadable ``SKILL.md``."""

    if not isinstance(content, str) or not content.startswith("---\n"):
        return "frontmatter_missing"
    closing = content.find("\n---\n", 4)
    if closing < 0:
        return "frontmatter_unclosed"
    try:
        frontmatter = yaml.safe_load(content[4:closing])
    except yaml.YAMLError:
        return "frontmatter_yaml"
    if not isinstance(frontmatter, Mapping):
        return "frontmatter_mapping"
    unknown = set(frontmatter) - _FRONTMATTER_FIELDS
    if unknown:
        return "frontmatter_fields"
    name = frontmatter.get("name")
    if not isinstance(name, str) or len(name) >= 64 or _SKILL_NAME.fullmatch(name) is None:
        return "name"
    description = frontmatter.get("description")
    if not isinstance(description, str) or not description.strip() or len(description) > 1024:
        return "description"
    metadata = frontmatter.get("metadata")
    if metadata is not None and not isinstance(metadata, Mapping):
        return "metadata"
    if not content[closing + 5 :].strip():
        return "body_empty"
    return None


def _sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


__all__ = [
    "NEUTRAL_PLACEHOLDER",
    "SkillArtifact",
    "SkillCompiler",
    "validate_skill_text",
]
