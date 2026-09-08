"""Fresh-context compiler with an exact, auditable input allowlist."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml

from .constants import EXPERIMENT_ROOT, PAYLOAD_COMMANDS
from .model import ModelClient, ModelClientError

_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_ALLOWED_FRONTMATTER = {"name", "description", "metadata"}
_OUTER_FENCE_LABELS = {"```", "```yaml", "```yml", "```markdown", "```md"}
_DOCUMENT_FIELDS = frozenset({"documents_actually_read", "documents_retrieved_full"})
_CONTEXT_EVICTION_REASON = "oldest-quarter-on-input-overflow"


@dataclass(frozen=True)
class TauSkillArtifact:
    text: str
    skill_sha256: str
    valid: bool
    source_page_ids: tuple[str, ...]
    evaluable: bool = False
    format_valid: bool = False
    format_error: str | None = None
    failure: str | None = None
    raw_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "skill_sha256": self.skill_sha256,
            "valid": self.valid,
            "source_page_ids": list(self.source_page_ids),
            "evaluable": self.evaluable,
            "format_valid": self.format_valid,
            "format_error": self.format_error,
            "failure": self.failure,
            "raw_text": self.raw_text,
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


def _unwrap_single_outer_fence(text: str) -> str:
    """Remove only a single fence that encloses the complete model response."""

    lines = text.strip().splitlines()
    if (
        len(lines) >= 3
        and lines[0].strip().casefold() in _OUTER_FENCE_LABELS
        and lines[-1].strip() == "```"
    ):
        return "\n".join(lines[1:-1]).strip() + "\n"
    return text.strip() + "\n"


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


def _paired_search_results(public_trace: Mapping[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Validate one-to-one tool pairing and return the search result payloads."""

    events = public_trace.get("events")
    if not isinstance(events, list):
        raise ValueError("public_trace must contain an events list")
    pending: dict[tuple[str, str], str] = {}
    seen_call_ids: set[str] = set()
    search_results: list[tuple[str, dict[str, Any]]] = []
    for event in events:
        if not isinstance(event, Mapping) or not isinstance(event.get("payload"), Mapping):
            raise ValueError("public_trace contains a malformed event")
        payload = event["payload"]
        if event.get("kind") == "message":
            calls = payload.get("tool_calls", []) or []
            if not isinstance(calls, list):
                raise ValueError("public_trace tool_calls must be a list")
            for call in calls:
                if not isinstance(call, Mapping):
                    raise ValueError("public_trace contains a malformed tool call")
                call_id = call.get("id")
                name = call.get("name")
                requestor = call.get("requestor")
                if not all(
                    isinstance(value, str) and value for value in (call_id, name, requestor)
                ):
                    raise ValueError("public_trace tool call is missing its identity")
                if call_id in seen_call_ids:
                    raise ValueError("public_trace reused a tool call identity")
                if name == "search_web" and requestor != "assistant":
                    raise ValueError("search_web trace call has an invalid requestor")
                seen_call_ids.add(call_id)
                pending[(call_id, requestor)] = name
            continue
        if event.get("kind") != "tool_result":
            continue
        call_id = payload.get("id")
        requestor = payload.get("requestor")
        if not isinstance(call_id, str) or not isinstance(requestor, str):
            raise ValueError("public_trace tool result is missing its identity")
        name = pending.pop((call_id, requestor), None)
        if name is None:
            raise ValueError("public_trace tool result has no unique pending call")
        if name == "search_web":
            search_results.append((call_id, payload))
    if pending:
        raise ValueError("public_trace ended before a tool result")
    return search_results


def _trace_with_document_references(
    public_trace: Mapping[str, Any],
    documents: Sequence[Mapping[str, str]],
    *,
    resident_search_call_ids: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Replace full ``search_web`` results with audited document references."""

    trace = json.loads(json.dumps(public_trace, ensure_ascii=False, allow_nan=False))
    if not isinstance(trace, dict) or not isinstance(trace.get("events"), list):
        raise ValueError("public_trace must contain an events list")
    document_by_id = {item["page_id"]: item for item in documents}
    resident_ids = None if resident_search_call_ids is None else frozenset(resident_search_call_ids)

    def trace_body_matches(body: object, document: Mapping[str, str]) -> bool:
        if body == document["body"]:
            return True
        redacted = document["body"]
        for command in sorted(PAYLOAD_COMMANDS.values(), key=len, reverse=True):
            digest = hashlib.sha256(command.encode("utf-8")).hexdigest()
            redacted = redacted.replace(command, f"<redacted-command:{digest}>")
        return body == redacted

    for call_id, payload in _paired_search_results(trace):
        if resident_ids is not None and call_id not in resident_ids:
            marker = {
                "status": "context_evicted",
                "reason": _CONTEXT_EVICTION_REASON,
                "results": [],
            }
            payload["content"] = json.dumps(marker, separators=(",", ":"))
            continue
        if payload.get("error") is True:
            # Retrieval/tool failures carry no admitted page body. Preserve the
            # public failure verbatim so the progressive trace stays complete.
            continue
        content = payload.get("content")
        encoded = isinstance(content, str)
        if encoded:
            try:
                response = json.loads(content)
            except json.JSONDecodeError as exc:
                raise ValueError("search_web trace result is not valid JSON") from exc
        else:
            response = content
        if not isinstance(response, dict) or not isinstance(response.get("results"), list):
            raise ValueError("search_web trace result has an invalid shape")
        rewritten: list[Any] = []
        for result in response["results"]:
            if not isinstance(result, dict):
                raise ValueError("search_web trace contains a malformed result")
            page_id = result.get("page_id")
            title = result.get("title")
            body = result.get("content")
            document = document_by_id.get(page_id)
            if (
                document is None
                or title != document["title"]
                or not trace_body_matches(body, document)
            ):
                raise ValueError("search_web full text does not match a compiler document")
            rewritten.append(
                {
                    "page_id": page_id,
                    "title": title,
                    "document_ref": f"documents_retrieved_full:{page_id}",
                    "content_sha256": document["content_sha256"],
                }
            )
        response["results"] = rewritten
        payload["content"] = (
            json.dumps(response, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
            if encoded
            else response
        )
    return trace


def _resident_document_ids(
    public_trace: Mapping[str, Any], resident_search_call_ids: Sequence[str]
) -> tuple[str, ...]:
    if any(not isinstance(value, str) or not value for value in resident_search_call_ids):
        raise ValueError("resident search call IDs must be non-empty strings")
    resident_ids = frozenset(resident_search_call_ids)
    if len(resident_ids) != len(resident_search_call_ids):
        raise ValueError("resident search call IDs must be unique")
    completed_resident: set[str] = set()
    page_ids: list[str] = []
    seen_pages: set[str] = set()
    for call_id, payload in _paired_search_results(public_trace):
        if call_id not in resident_ids:
            continue
        completed_resident.add(call_id)
        if payload.get("error") is True:
            continue
        content = payload.get("content")
        try:
            response = json.loads(content) if isinstance(content, str) else content
        except json.JSONDecodeError as exc:
            raise ValueError("search_web trace result is not valid JSON") from exc
        if not isinstance(response, Mapping) or not isinstance(response.get("results"), list):
            raise ValueError("search_web trace result has an invalid shape")
        for result in response["results"]:
            if not isinstance(result, Mapping):
                raise ValueError("search_web trace contains a malformed result")
            page_id = result.get("page_id")
            title = result.get("title")
            body = result.get("content")
            if (
                not isinstance(page_id, str)
                or not page_id
                or not isinstance(title, str)
                or not title
                or not isinstance(body, str)
            ):
                raise ValueError("resident search_web result is not complete full text")
            if page_id not in seen_pages:
                seen_pages.add(page_id)
                page_ids.append(page_id)
    if completed_resident != resident_ids:
        raise ValueError("resident search call IDs do not match the public trace")
    return tuple(page_ids)


class TauSkillCompiler:
    def __init__(
        self,
        client: ModelClient,
        *,
        include_public_trace: bool = False,
        max_input_tokens: int = 32768,
        max_skill_tokens: int = 4096,
        chars_per_token: int = 4,
        prompt_path: Path = EXPERIMENT_ROOT / "prompts" / "compiler_system.md",
        documents_field: str = "documents_actually_read",
        reference_trace_documents: bool = False,
        enforce_char_budget: bool = True,
        include_official_result: bool = True,
        format_validation_mode: Literal["strict", "diagnostic"] = "strict",
    ) -> None:
        if not all(
            isinstance(value, int) and not isinstance(value, bool) and value > 0
            for value in (max_input_tokens, max_skill_tokens, chars_per_token)
        ):
            raise ValueError("compiler limits must be positive integers")
        self.client = client
        self.include_public_trace = bool(include_public_trace)
        self.max_input_tokens = max_input_tokens
        self.max_skill_tokens = max_skill_tokens
        self.chars_per_token = chars_per_token
        if documents_field not in _DOCUMENT_FIELDS:
            raise ValueError("documents_field is not supported")
        if reference_trace_documents and (
            not include_public_trace or documents_field != "documents_retrieved_full"
        ):
            raise ValueError(
                "trace document references require include_public_trace=true and "
                "documents_field=documents_retrieved_full"
            )
        self.documents_field = documents_field
        self.reference_trace_documents = bool(reference_trace_documents)
        self.enforce_char_budget = bool(enforce_char_budget)
        if not isinstance(include_official_result, bool):
            raise TypeError("include_official_result must be boolean")
        self.include_official_result = include_official_result
        if format_validation_mode not in {"strict", "diagnostic"}:
            raise ValueError("format_validation_mode must be strict or diagnostic")
        self.format_validation_mode = format_validation_mode
        self.system_prompt = prompt_path.read_text(encoding="utf-8")

    def build_payload(
        self,
        *,
        first_user_utterance: str,
        opened_pages: Sequence[Any],
        task_id: str | None = None,
        task_success: bool | None = None,
        public_trace: Mapping[str, Any] | None = None,
        resident_search_call_ids: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        if not isinstance(first_user_utterance, str) or not first_user_utterance.strip():
            raise ValueError("first_user_utterance is required")
        if self.include_official_result:
            if not isinstance(task_id, str) or not task_id:
                raise ValueError("task_id is required")
            if not isinstance(task_success, bool):
                raise TypeError("task_success must be bool")
        if self.reference_trace_documents and resident_search_call_ids is None:
            raise ValueError(
                "resident search call IDs are required when trace document references are enabled"
            )
        all_documents: list[dict[str, str]] = []
        seen: set[str] = set()
        for item in opened_pages:
            clean = _page(item)
            if clean["page_id"] not in seen:
                seen.add(clean["page_id"])
                all_documents.append(clean)
        documents = all_documents
        resident_ids: tuple[str, ...] | None = None
        if resident_search_call_ids is not None:
            if not self.include_public_trace or not self.reference_trace_documents:
                raise ValueError("resident retrieval projection requires the public trace")
            if not isinstance(public_trace, Mapping):
                raise ValueError("public_trace is required for resident retrieval projection")
            resident_ids = tuple(resident_search_call_ids)
            # Validate every recorded full-text result before projecting the
            # compiler view down to what remained in the Agent's context.
            _trace_with_document_references(public_trace, all_documents)
            resident_page_ids = _resident_document_ids(public_trace, resident_ids)
            document_by_id = {document["page_id"]: document for document in all_documents}
            if any(page_id not in document_by_id for page_id in resident_page_ids):
                raise ValueError("resident retrieval page is absent from full acquisition evidence")
            documents = [document_by_id[page_id] for page_id in resident_page_ids]
        payload: dict[str, Any] = {
            "task": first_user_utterance,
            self.documents_field: documents,
        }
        if self.include_official_result:
            payload["official_result"] = {"task_id": task_id, "task_success": task_success}
        if self.include_public_trace:
            if not isinstance(public_trace, Mapping):
                raise ValueError("public_trace is required when include_public_trace=true")
            payload["public_trace"] = (
                _trace_with_document_references(
                    public_trace,
                    documents,
                    resident_search_call_ids=resident_ids,
                )
                if self.reference_trace_documents
                else json.loads(json.dumps(public_trace, ensure_ascii=False, allow_nan=False))
            )
        if resident_ids is not None:
            payload["retrieval_context"] = {
                "policy": _CONTEXT_EVICTION_REASON,
                "resident_search_tool_call_ids": list(resident_ids),
            }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, allow_nan=False)
        if self.enforce_char_budget and len(encoded) > self.max_input_tokens * self.chars_per_token:
            raise ValueError(
                "compiler payload exceeds fixed input budget; full pages are not truncated"
            )
        return payload

    def compile(self, *, seed: int | None = None, **inputs: Any) -> TauSkillArtifact:
        payload = self.build_payload(**inputs)
        source_ids = tuple(item["page_id"] for item in payload[self.documents_field])
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
                max_output_tokens=self.max_skill_tokens,
            )
        except ModelClientError as exc:
            return self._invalid(source_ids, f"model_{exc.code}")
        if response.get("finish_reason") == "length":
            truncated = response.get("content")
            return self._invalid(
                source_ids,
                "model_output_truncated",
                raw_text=truncated if isinstance(truncated, str) else "",
            )
        if response.get("tool_calls"):
            encoded_calls = json.dumps(
                response.get("tool_calls"),
                ensure_ascii=False,
                sort_keys=True,
                allow_nan=False,
            )
            return self._invalid(
                source_ids,
                "compiler_returned_tool_calls",
                raw_text=encoded_calls,
            )
        text = response.get("content")
        if not isinstance(text, str) or not text.strip():
            return self._invalid(
                source_ids,
                "empty_skill",
                raw_text=text if isinstance(text, str) else "",
            )
        if self.format_validation_mode == "diagnostic":
            if "\x00" in text:
                return self._invalid(source_ids, "skill_contains_nul", raw_text=text)
            try:
                text.encode("utf-8")
            except UnicodeEncodeError:
                return self._invalid(source_ids, "skill_not_utf8", raw_text=text)
        raw_text = text if self.format_validation_mode == "diagnostic" else text.strip() + "\n"
        if (
            self.enforce_char_budget
            and len(raw_text) > self.max_skill_tokens * self.chars_per_token
        ):
            return self._invalid(source_ids, "skill_too_long", raw_text=raw_text)
        artifact_text = (
            raw_text
            if self.format_validation_mode == "diagnostic"
            else _unwrap_single_outer_fence(raw_text)
        )
        error = validate_skill_text(artifact_text)
        if error is not None:
            if self.format_validation_mode == "strict":
                return self._invalid(
                    source_ids,
                    f"invalid_skill_{error}",
                    raw_text=raw_text,
                    format_error=error,
                )
            return TauSkillArtifact(
                text=artifact_text,
                skill_sha256=hashlib.sha256(artifact_text.encode("utf-8")).hexdigest(),
                valid=False,
                source_page_ids=source_ids,
                evaluable=True,
                format_valid=False,
                format_error=error,
                raw_text=raw_text,
            )
        return TauSkillArtifact(
            text=artifact_text,
            skill_sha256=hashlib.sha256(artifact_text.encode("utf-8")).hexdigest(),
            valid=True,
            source_page_ids=source_ids,
            evaluable=True,
            format_valid=True,
            raw_text=raw_text,
        )

    @staticmethod
    def _invalid(
        source_ids: tuple[str, ...],
        failure: str,
        *,
        raw_text: str = "",
        format_error: str | None = None,
    ) -> TauSkillArtifact:
        return TauSkillArtifact(
            text="",
            skill_sha256=hashlib.sha256(b"").hexdigest(),
            valid=False,
            source_page_ids=source_ids,
            evaluable=False,
            format_valid=False,
            format_error=format_error,
            failure=failure,
            raw_text=raw_text,
        )
