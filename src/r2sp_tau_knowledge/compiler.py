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

from .constants import EXPERIMENT_ROOT
from .model import ModelClient, ModelClientError

_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_ALLOWED_FRONTMATTER = {"name", "description", "metadata"}


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
        self.system_prompt = prompt_path.read_text(encoding="utf-8")

    def build_payload(
        self,
        *,
        first_user_utterance: str,
        opened_pages: Sequence[Any],
        task_id: str,
        task_success: bool,
        public_trace: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not isinstance(first_user_utterance, str) or not first_user_utterance.strip():
            raise ValueError("first_user_utterance is required")
        if not isinstance(task_id, str) or not task_id:
            raise ValueError("task_id is required")
        if not isinstance(task_success, bool):
            raise TypeError("task_success must be bool")
        documents: list[dict[str, str]] = []
        seen: set[str] = set()
        for item in opened_pages:
            clean = _page(item)
            if clean["page_id"] not in seen:
                seen.add(clean["page_id"])
                documents.append(clean)
        payload: dict[str, Any] = {
            "task": first_user_utterance,
            "documents_actually_read": documents,
            "official_result": {"task_id": task_id, "task_success": task_success},
        }
        if self.include_public_trace:
            if not isinstance(public_trace, Mapping):
                raise ValueError("public_trace is required when include_public_trace=true")
            payload["public_trace"] = json.loads(
                json.dumps(public_trace, ensure_ascii=False, allow_nan=False)
            )
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, allow_nan=False)
        if len(encoded) > self.max_input_tokens * self.chars_per_token:
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
                max_output_tokens=self.max_skill_tokens,
            )
        except ModelClientError as exc:
            return self._invalid(source_ids, f"model_{exc.code}")
        if response.get("tool_calls"):
            return self._invalid(source_ids, "compiler_returned_tool_calls")
        text = response.get("content")
        if not isinstance(text, str) or not text.strip():
            return self._invalid(source_ids, "empty_skill")
        text = text.strip() + "\n"
        if len(text) > self.max_skill_tokens * self.chars_per_token:
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
