"""Single-POST Bedrock Mantle clients and shared embedding token counters."""

from __future__ import annotations

import base64
import binascii
import contextlib
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

from .constants import (
    DEFAULT_MODEL,
    MESSAGES_MAX_OUTPUT_TOKENS,
    MESSAGES_MODEL,
    RESPONSES_MODELS,
)
from .core._canonical import canonical_json_sha256

# Loopback helper services (tokenizer, embeddings) are deterministic and side-effect
# free; only gateway/overload statuses are retried, never model requests.
RETRYABLE_LOCAL_HTTP_STATUSES = frozenset({502, 503, 504})


class ModelClient(Protocol):
    def complete(
        self,
        messages: Sequence[Mapping[str, Any]],
        *,
        tools: Sequence[Mapping[str, Any]] | None = None,
        seed: int | None = None,
        max_output_tokens: int | None = None,
    ) -> dict[str, Any]: ...


class ModelClientError(RuntimeError):
    def __init__(self, code: str, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


class InputTokenBudgetExceeded(ModelClientError):
    """Local admission rejected the request before its HTTP POST."""

    def __init__(self, input_tokens: int, max_input_tokens: int) -> None:
        super().__init__(
            "input_token_budget_exceeded",
            f"chat input exceeds pinned limit: observed={input_tokens}, limit={max_input_tokens}",
        )
        self.input_tokens = input_tokens
        self.max_input_tokens = max_input_tokens
        self.details = {
            "observed_input_tokens": input_tokens,
            "max_input_tokens": max_input_tokens,
        }


class CredentialError(ModelClientError):
    """A bearer credential could not be resolved before any request was built.

    Codes: ``credential_unavailable`` (token file missing/unreadable/malformed)
    and ``credential_expired``. Because no request left the host, callers abort
    the invocation and leave the operation unsent instead of sealing an unknown.
    """


def is_credential_error(error: BaseException) -> bool:
    """True when ``error`` or any wrapped cause is a :class:`CredentialError`."""
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, CredentialError):
            return True
        current = current.__cause__ or current.__context__
    return False


def authentication_status(error: BaseException) -> int | None:
    """Inspect wrapped failures without persisting provider bodies or credentials."""
    seen: set[int] = set()
    while id(error) not in seen:
        seen.add(id(error))
        status = getattr(error, "status", None)
        if status in (401, 403):
            return status
        parent = error.__cause__ or error.__context__
        if parent is None:
            break
        error = parent
    return None


class ChatTokenCounter(Protocol):
    """Estimate request size deterministically for experiment admission."""

    def count(
        self,
        messages: Sequence[Mapping[str, Any]],
        *,
        tools: Sequence[Mapping[str, Any]] | None = None,
        chat_template_kwargs: Mapping[str, Any] | None = None,
    ) -> int: ...


class VllmTextTokenCounter:
    """Count plain text with the same tokenizer served by the pinned vLLM model."""

    def __init__(
        self,
        endpoint: str,
        *,
        model: str,
        api_key: str = "tau-local-evaluation",
        timeout_seconds: float = 60.0,
        opener: Any | None = None,
        retry_attempts: int = 5,
        retry_backoff_seconds: float = 0.2,
    ) -> None:
        if not isinstance(endpoint, str) or not endpoint.strip() or timeout_seconds <= 0:
            raise ValueError("endpoint and timeout_seconds must be valid")
        if not isinstance(model, str) or not model.strip():
            raise ValueError("model must be a non-empty string")
        if isinstance(retry_attempts, bool) or not isinstance(retry_attempts, int):
            raise ValueError("retry_attempts must be an integer")
        if retry_attempts < 1 or retry_backoff_seconds < 0:
            raise ValueError("retry_attempts must be >= 1 and retry_backoff_seconds >= 0")
        self.retry_attempts = retry_attempts
        self.retry_backoff_seconds = float(retry_backoff_seconds)
        root = endpoint.rstrip("/")
        if root.endswith("/v1"):
            root = root[:-3]
        self.endpoint = f"{root}/tokenize"
        self.model = model
        self.api_key = api_key
        self.timeout_seconds = float(timeout_seconds)
        self._opener = opener or urllib.request.urlopen
        self.basis = "server_text_tokenizer"

    def __call__(self, text: str) -> int:
        if not isinstance(text, str):
            raise TypeError("text must be a string")
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(
                {
                    "model": self.model,
                    "prompt": text,
                    "add_special_tokens": False,
                },
                ensure_ascii=False,
                allow_nan=False,
            ).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        # Tokenizing is a deterministic local-service lookup with no side effects, so a
        # transient outage of the loopback service is retried briefly instead of
        # permanently sealing the surrounding journal operation as unknown.
        attempt = 0
        while True:
            try:
                with self._opener(request, timeout=self.timeout_seconds) as response:
                    decoded = json.loads(response.read())
                break
            except urllib.error.HTTPError as exc:
                attempt += 1
                if attempt < self.retry_attempts and exc.code in RETRYABLE_LOCAL_HTTP_STATUSES:
                    time.sleep(self.retry_backoff_seconds * 2 ** (attempt - 1))
                    continue
                raise ModelClientError(
                    "tokenize_http_error",
                    f"tokenizer service returned HTTP {exc.code}",
                    status=exc.code,
                ) from exc
            except (OSError, TimeoutError, urllib.error.URLError) as exc:
                attempt += 1
                if attempt < self.retry_attempts:
                    time.sleep(self.retry_backoff_seconds * 2 ** (attempt - 1))
                    continue
                raise ModelClientError("tokenize_transport_error", str(exc)) from exc
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ModelClientError(
                    "tokenize_invalid_json", "tokenizer service returned invalid JSON"
                ) from exc
        count = decoded.get("count") if isinstance(decoded, dict) else None
        if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
            raise ModelClientError(
                "tokenize_invalid_response", "tokenizer service returned no token count"
            )
        return count


class SerializedChatTokenCounter:
    """Estimate native Responses input with a pinned local text tokenizer.

    Measured reasoning usage reserves space for opaque continuation items; it
    does not make this an exact provider context count. Completion accounting
    continues to use provider usage.
    """

    def __init__(
        self,
        text_counter: Any,
        *,
        basis: str = "responses_input_estimate_with_reasoning_reserve",
    ) -> None:
        if not callable(text_counter):
            raise TypeError("text_counter must be callable")
        if not isinstance(basis, str) or not basis.strip():
            raise ValueError("basis must be a non-empty string")
        self.text_counter = text_counter
        self.basis = basis

    def count(
        self,
        messages: Sequence[Mapping[str, Any]],
        *,
        tools: Sequence[Mapping[str, Any]] | None = None,
        chat_template_kwargs: Mapping[str, Any] | None = None,
    ) -> int:
        return self.count_breakdown(
            messages, tools=tools, chat_template_kwargs=chat_template_kwargs
        )["total_tokens"]

    def count_breakdown(
        self,
        messages: Sequence[Mapping[str, Any]],
        *,
        tools: Sequence[Mapping[str, Any]] | None = None,
        chat_template_kwargs: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        del chat_template_kwargs
        # Count the provider input once, not normalized response metadata and its
        # duplicated text/tool calls. Ciphertext is a transport encoding, so use
        # the response's measured reasoning tokens as a conservative reserve.
        # Missing usage keeps ciphertext in the estimate rather than charging zero.
        admission_messages = deepcopy(list(messages))
        reasoning_reserve = 0
        for message in admission_messages:
            preserved = message.get("_bedrock_output_items")
            if not isinstance(preserved, list) or not any(
                isinstance(item, Mapping)
                and item.get("type") == "reasoning"
                and item.get("encrypted_content")
                for item in preserved
            ):
                continue
            usage = message.get("usage") or {}
            if not isinstance(usage, Mapping):
                continue
            details = usage.get("output_tokens_details") or {}
            if not isinstance(details, Mapping):
                continue
            reserve = details.get("reasoning_tokens", usage.get("output_tokens"))
            if isinstance(reserve, bool) or not isinstance(reserve, int) or reserve < 0:
                continue
            reasoning_reserve += reserve
            for item in preserved:
                if isinstance(item, dict) and item.get("type") == "reasoning":
                    item.pop("encrypted_content", None)
        payload: dict[str, Any] = {"input": _response_input(admission_messages)}
        if tools is not None:
            payload["tools"] = _response_tools(tools)
        rendered = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        observed = self.text_counter(rendered)
        if isinstance(observed, bool) or not isinstance(observed, int) or observed < 0:
            raise ModelClientError(
                "tokenize_invalid_response", "text tokenizer returned no token count"
            )
        return {
            "total_tokens": observed + reasoning_reserve,
            "visible_tokens": observed,
            "reasoning_reserve": reasoning_reserve,
            "basis": self.basis,
        }


@dataclass(frozen=True, slots=True)
class GenerationConfig:
    model: str = DEFAULT_MODEL
    reasoning_effort: str | None = "medium"
    max_output_tokens: int | None = 16384
    max_input_tokens: int | None = None
    transport: str = "bedrock-responses"
    response_format: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if not (
            (self.model in RESPONSES_MODELS and self.transport == "bedrock-responses")
            or (self.model == MESSAGES_MODEL and self.transport == "bedrock-messages")
        ):
            raise ValueError("model and supported Bedrock Mantle transport must match")
        if self.reasoning_effort not in {None, "none", "low", "medium", "high", "xhigh"}:
            raise ValueError("invalid reasoning effort")
        if self.transport == "bedrock-messages" and self.reasoning_effort == "xhigh":
            raise ValueError("Opus 4.8 supports none/low/medium/high reasoning effort")
        if self.response_format is not None and not isinstance(self.response_format, Mapping):
            raise ValueError("response_format must be a mapping")
        for name in ("max_output_tokens", "max_input_tokens"):
            value = getattr(self, name)
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if (
            self.transport == "bedrock-messages"
            and self.max_output_tokens is not None
            and self.max_output_tokens > MESSAGES_MAX_OUTPUT_TOKENS
        ):
            raise ValueError("Opus 4.8 output exceeds its documented model maximum")


def bedrock_responses_endpoint(endpoint: str) -> str:
    """Require the documented GPT-5.x route; never switch model or cloud endpoint."""
    if not isinstance(endpoint, str):
        raise ValueError("a Bedrock Mantle endpoint must be configured")
    parsed = urlsplit(endpoint.rstrip("/"))
    if (
        parsed.scheme != "https"
        or not re.fullmatch(r"bedrock-mantle\.us-east-[12]\.api\.aws", parsed.netloc)
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/openai/v1", "/openai/v1/responses"}
    ):
        raise ValueError("GPT-5.x requires a supported Bedrock Mantle /openai/v1 endpoint")
    return f"https://{parsed.netloc}/openai/v1/responses"


def bedrock_messages_endpoint(endpoint: str) -> str:
    """Opus 4.8 uses the documented us-east-1 Mantle Messages route."""
    if not isinstance(endpoint, str):
        raise ValueError("a Bedrock Mantle endpoint must be configured")
    parsed = urlsplit(endpoint.rstrip("/"))
    if (
        parsed.scheme != "https"
        or parsed.netloc != "bedrock-mantle.us-east-1.api.aws"
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/anthropic/v1", "/anthropic/v1/messages"}
    ):
        raise ValueError("Opus 4.8 requires the us-east-1 Mantle /anthropic/v1 endpoint")
    return f"https://{parsed.netloc}/anthropic/v1/messages"


def _response_input(messages: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for message in messages:
        if not isinstance(message, Mapping) or message.get("role") not in {
            "system",
            "developer",
            "user",
            "assistant",
            "tool",
        }:
            raise ValueError("messages must use supported conversation roles")
        role = message["role"]
        preserved = message.get("_bedrock_output_items")
        if preserved is not None:
            if role != "assistant" or not isinstance(preserved, list) or not preserved:
                raise ValueError("Responses continuation belongs to an assistant message")
            if any(
                not isinstance(item, Mapping)
                or item.get("type") not in {"message", "reasoning", "function_call"}
                for item in preserved
            ):
                raise ValueError("invalid Responses continuation items")
            items.extend(deepcopy(preserved))
            continue
        content = message.get("content")
        if role == "tool":
            if not isinstance(message.get("tool_call_id"), str) or not message["tool_call_id"]:
                raise ValueError("tool result requires its original call ID")
            if not isinstance(content, str):
                raise ValueError("tool result must be text")
            items.append(
                {
                    "type": "function_call_output",
                    "call_id": message["tool_call_id"],
                    "output": content,
                }
            )
            continue
        if content is not None:
            if not isinstance(content, str):
                raise ValueError("the bank workflow supports text messages only")
            items.append({"role": "developer" if role == "system" else role, "content": content})
        for call in message.get("tool_calls", []) or []:
            function = call.get("function") if isinstance(call, Mapping) else None
            if (
                role != "assistant"
                or not isinstance(function, Mapping)
                or not all(
                    isinstance(value, str) and value
                    for value in (call.get("id"), function.get("name"))
                )
                or not isinstance(function.get("arguments"), str)
            ):
                raise ValueError("invalid function call in conversation")
            items.append(
                {
                    "type": "function_call",
                    "call_id": call["id"],
                    "name": function["name"],
                    "arguments": function["arguments"],
                }
            )
    return items


def _response_tools(tools: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for tool in tools:
        function = tool.get("function") if isinstance(tool, Mapping) else None
        if (
            not isinstance(tool, Mapping)
            or tool.get("type") != "function"
            or not isinstance(function, Mapping)
        ):
            raise ValueError("only host-controlled function tools are supported")
        if not isinstance(function.get("name"), str) or not function["name"]:
            raise ValueError("function tool requires a name")
        result.append(
            {
                "type": "function",
                **deepcopy(dict(function)),
                "strict": function.get("strict", False),
            }
        )
    return result


_THINKING_PREFIX = "anthropic-thinking-v1:"


def _anthropic_tool_map(tools: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Bind local Responses tools to deterministic, collision-checked API names."""
    result: dict[str, dict[str, Any]] = {}

    def add(tool: Mapping[str, Any], namespace: str | None = None) -> None:
        kind, name = tool.get("type"), tool.get("name")
        if (
            not isinstance(kind, str)
            or kind not in {"function", "custom"}
            or not isinstance(name, str)
            or not name
        ):
            raise ValueError("Messages supports only declared local function/custom tools")
        qualified = f"{namespace}.{name}" if namespace else name
        alias = "t_" + hashlib.sha256(f"{kind}:{qualified}".encode()).hexdigest()[:24]
        if alias in result:
            raise ValueError("duplicate or colliding tool declaration")
        description = tool.get("description") or ""
        if not isinstance(description, str):
            raise ValueError("tool description must be text")
        description = f"Local tool {qualified}. " + description
        if kind == "function":
            schema = tool.get("parameters")
            if not isinstance(schema, Mapping):
                raise ValueError("function tool requires its JSON parameter schema")
        else:
            fmt = tool.get("format") or {"type": "text"}
            if not isinstance(fmt, Mapping) or fmt.get("type") not in {"text", "grammar"}:
                raise ValueError("unsupported custom tool input format")
            if fmt["type"] == "grammar":
                if fmt.get("syntax") not in {"lark", "regex"} or not isinstance(
                    fmt.get("definition"), str
                ):
                    raise ValueError("custom tool grammar must be explicitly provided")
                description += "\nThe input string must match this grammar: " + json.dumps(fmt)
            schema = {
                "type": "object",
                "properties": {"input": {"type": "string"}},
                "required": ["input"],
                "additionalProperties": False,
            }
        result[alias] = {
            "name": name,
            "namespace": namespace,
            "kind": kind,
            "tool": {
                "name": alias,
                "description": description,
                "input_schema": deepcopy(dict(schema)),
            },
        }

    for tool in tools:
        if not isinstance(tool, Mapping):
            raise ValueError("tool declaration must be an object")
        if tool.get("type") == "namespace":
            name, inner = tool.get("name"), tool.get("tools")
            if not isinstance(name, str) or not name or not isinstance(inner, list):
                raise ValueError("namespace requires a name and local tools")
            for child in inner:
                if not isinstance(child, Mapping):
                    raise ValueError("namespace tool must be an object")
                add(child, name)
        else:
            add(tool)
    return result


def _messages_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list) or any(
        not isinstance(block, Mapping)
        or block.get("type") not in {"input_text", "output_text", "text"}
        or not isinstance(block.get("text"), str)
        for block in content
    ):
        raise ValueError("this Messages role requires text content")
    return "\n".join(block["text"] for block in content)


def _messages_content(content: Any) -> list[dict[str, Any]]:
    """Public user/tool observations may include inline or URL images; never fetch them."""
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    if not isinstance(content, list):
        raise ValueError("message content must be text or supported content blocks")
    result = []
    for block in content:
        if not isinstance(block, Mapping):
            raise ValueError("invalid content block")
        if block.get("type") in {"input_text", "output_text", "text"} and isinstance(
            block.get("text"), str
        ):
            result.append({"type": "text", "text": block["text"]})
            continue
        url = block.get("image_url")
        if block.get("type") != "input_image" or "file_id" in block or not isinstance(url, str):
            raise ValueError("unsupported image/file content block")
        inline = re.fullmatch(r"data:(image/(?:png|jpeg|gif|webp));base64,(.+)", url)
        if inline:
            try:
                if not base64.b64decode(inline[2], validate=True):
                    raise ValueError("empty image")
            except (ValueError, binascii.Error) as exc:
                raise ValueError("invalid inline image encoding") from exc
            source = {"type": "base64", "media_type": inline[1], "data": inline[2]}
        else:
            parsed = urlsplit(url)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or url.strip() != url
            ):
                raise ValueError("image source must be a supported data URI or HTTP(S) URL")
            source = {"type": "url", "url": url}
        result.append({"type": "image", "source": source})
    return result


def _validate_thinking(block: Any) -> dict[str, Any]:
    if not isinstance(block, Mapping):
        raise ValueError("invalid signed thinking continuation")
    kind = block.get("type")
    fields = ("thinking", "signature") if kind == "thinking" else ("data",)
    if (
        not isinstance(kind, str)
        or kind not in {"thinking", "redacted_thinking"}
        or any(not isinstance(block.get(field), str) for field in fields)
        or (kind == "thinking" and not block["signature"])
    ):
        raise ValueError("invalid signed thinking continuation")
    return deepcopy(dict(block))


def responses_to_anthropic(
    payload: Mapping[str, Any],
    *,
    model: str,
    reasoning_effort: str | None,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    """Translate local Responses input without server tools or lost thinking signatures.

    Structured JSON and free-text tool grammars are prompt constraints on this
    model, not server-enforced formats. The existing host validators remain final.
    """
    if model != MESSAGES_MODEL or reasoning_effort not in {None, "none", "low", "medium", "high"}:
        raise ValueError("unsupported Messages model or reasoning effort")
    if any(payload.get(name) for name in ("previous_response_id", "conversation", "background")):
        raise ValueError("Messages bridge requires the complete local conversation")
    limit = max_tokens if max_tokens is not None else payload.get("max_output_tokens")
    if limit is None:
        limit = MESSAGES_MAX_OUTPUT_TOKENS
    if (
        isinstance(limit, bool)
        or not isinstance(limit, int)
        or not 0 < limit <= MESSAGES_MAX_OUTPUT_TOKENS
    ):
        raise ValueError("Messages max_tokens exceeds the supported model range")
    tools = payload.get("tools") or []
    if not isinstance(tools, list):
        raise ValueError("tools must be a list")
    bindings = _anthropic_tool_map(tools)
    messages: list[dict[str, Any]] = []
    system: list[str] = []
    instructions = payload.get("instructions")
    if instructions is not None:
        if not isinstance(instructions, str):
            raise ValueError("instructions must be text")
        system.append(instructions)

    def append(role: str, block: dict[str, Any]) -> None:
        if messages and messages[-1]["role"] == role:
            messages[-1]["content"].append(block)
        else:
            messages.append({"role": role, "content": [block]})

    items = payload.get("input")
    if isinstance(items, str):
        items = [{"role": "user", "content": items}]
    if not isinstance(items, list):
        raise ValueError("Responses input must be text or a full input list")
    for item in items:
        if not isinstance(item, Mapping):
            raise ValueError("input item must be an object")
        kind = item.get("type", "message")
        if not isinstance(kind, str):
            raise ValueError("input item type must be a string")
        if kind == "message":
            role = item.get("role")
            if role in {"system", "developer"}:
                system.append(_messages_text(item.get("content")))
            elif role == "assistant":
                append(role, {"type": "text", "text": _messages_text(item.get("content"))})
            elif role == "user":
                for block in _messages_content(item.get("content")):
                    append(role, block)
            else:
                raise ValueError("unsupported message role")
        elif kind == "reasoning":
            opaque = item.get("encrypted_content")
            if not isinstance(opaque, str) or not opaque.startswith(_THINKING_PREFIX):
                raise ValueError("Messages cannot replay foreign or unsigned reasoning")
            try:
                block = json.loads(base64.b64decode(opaque[len(_THINKING_PREFIX) :], validate=True))
            except (ValueError, binascii.Error, UnicodeDecodeError) as exc:
                raise ValueError("invalid thinking encoding") from exc
            append("assistant", _validate_thinking(block))
        elif kind in {"function_call", "custom_tool_call"}:
            match = [
                (alias, binding)
                for alias, binding in bindings.items()
                if binding["name"] == item.get("name")
                and binding["namespace"] == item.get("namespace")
                and binding["kind"] == ("function" if kind == "function_call" else "custom")
            ]
            if len(match) != 1 or not isinstance(item.get("call_id"), str) or not item["call_id"]:
                raise ValueError("tool call does not match a declared local tool")
            if kind == "custom_tool_call":
                if not isinstance(item.get("input"), str):
                    raise ValueError("custom tool call requires text input")
                arguments = {"input": item["input"]}
            else:
                if not isinstance(item.get("arguments"), str):
                    raise ValueError("function call requires encoded JSON arguments")
                arguments = json.loads(item["arguments"])
                if not isinstance(arguments, Mapping):
                    raise ValueError("function call arguments must be an object")
            append(
                "assistant",
                {
                    "type": "tool_use",
                    "id": item["call_id"],
                    "name": match[0][0],
                    "input": deepcopy(arguments),
                },
            )
        elif kind in {"function_call_output", "custom_tool_call_output"}:
            if not isinstance(item.get("call_id"), str) or not item["call_id"]:
                raise ValueError("tool result requires its original call ID")
            append(
                "user",
                {
                    "type": "tool_result",
                    "tool_use_id": item["call_id"],
                    "content": (
                        item["output"]
                        if isinstance(item.get("output"), str)
                        else _messages_content(item.get("output"))
                    ),
                },
            )
        else:
            raise ValueError("unsupported server-side Responses input item")
    if not messages or messages[0]["role"] != "user":
        raise ValueError("Messages conversation must begin with a user input")
    text_config = payload.get("text") or {}
    if not isinstance(text_config, Mapping):
        raise ValueError("text configuration must be an object")
    fmt = text_config.get("format")
    if fmt is not None and not isinstance(fmt, Mapping):
        raise ValueError("response format must be an object")
    if fmt and fmt.get("type") != "text":
        if fmt.get("type") == "json_schema" and isinstance(fmt.get("schema"), Mapping):
            system.append(
                "Return only a JSON object matching this schema; no Markdown fences:\n"
                + json.dumps(fmt["schema"], ensure_ascii=False, allow_nan=False)
            )
        elif fmt.get("type") == "json_object":
            system.append("Return only a valid JSON object; no Markdown fences.")
        else:
            raise ValueError("unsupported structured response prompt constraint")
    result: dict[str, Any] = {
        "model": model,
        "max_tokens": limit,
        "messages": messages,
        "stream": False,
        "thinking": {"type": "disabled" if reasoning_effort == "none" else "adaptive"},
    }
    if reasoning_effort not in {None, "none"}:
        result["output_config"] = {"effort": reasoning_effort}
    if system:
        result["system"] = "\n\n".join(system)
    if bindings:
        result["tools"] = [binding["tool"] for binding in bindings.values()]
        choice = payload.get("tool_choice", "auto")
        if not isinstance(choice, str) or choice not in {"auto", "none"}:
            raise ValueError("Messages bridge supports auto/none local tool choice only")
        if choice == "none":
            result.pop("tools")
        else:
            result["tool_choice"] = {"type": "auto"}
            if payload.get("parallel_tool_calls") is False:
                result["tool_choice"]["disable_parallel_tool_use"] = True
    return result


def anthropic_to_responses(
    raw: Mapping[str, Any],
    *,
    tools: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Normalize a sealed Anthropic response; preserve signed reasoning opaquely."""
    if (
        not isinstance(raw, Mapping)
        or raw.get("type") != "message"
        or raw.get("role") != "assistant"
        or not isinstance(raw.get("id"), str)
        or not raw["id"]
        or not isinstance(raw.get("content"), list)
    ):
        raise ModelClientError("invalid_response", "invalid Anthropic message response")
    stop = raw.get("stop_reason")
    if stop == "refusal":
        raise ModelClientError("model_refusal", "Anthropic model refused the request")
    if not isinstance(stop, str) or stop not in {"end_turn", "tool_use", "max_tokens"}:
        raise ModelClientError("incomplete_response", "unsupported Anthropic termination reason")
    bindings = _anthropic_tool_map(tools)
    output: list[dict[str, Any]] = []
    calls = 0
    call_ids: set[str] = set()
    visible_text = False
    for index, block in enumerate(raw["content"]):
        if not isinstance(block, Mapping):
            raise ModelClientError("invalid_response", "malformed Anthropic content")
        kind, item_id = block.get("type"), f"{raw['id']}_{index}"
        if not isinstance(kind, str):
            raise ModelClientError("invalid_response", "Anthropic content type must be a string")
        if kind == "text" and isinstance(block.get("text"), str):
            visible_text = visible_text or bool(block["text"])
            output.append(
                {
                    "type": "message",
                    "id": item_id,
                    "role": "assistant",
                    "status": "completed",
                    "content": [{"type": "output_text", "text": block["text"], "annotations": []}],
                }
            )
        elif kind in {"thinking", "redacted_thinking"}:
            try:
                thinking = _validate_thinking(block)
            except ValueError as exc:
                raise ModelClientError(
                    "invalid_response", "invalid Anthropic thinking block"
                ) from exc
            opaque = base64.b64encode(json.dumps(thinking, ensure_ascii=False).encode()).decode()
            output.append(
                {
                    "type": "reasoning",
                    "id": item_id,
                    "summary": [],
                    "encrypted_content": _THINKING_PREFIX + opaque,
                }
            )
        elif kind == "tool_use":
            binding = (
                bindings.get(block.get("name")) if isinstance(block.get("name"), str) else None
            )
            if (
                binding is None
                or not isinstance(block.get("id"), str)
                or not block["id"]
                or block["id"] in call_ids
                or not isinstance(block.get("input"), Mapping)
            ):
                raise ModelClientError("invalid_response", "undeclared or malformed Anthropic tool")
            call_ids.add(block["id"])
            item = {
                "type": "function_call" if binding["kind"] == "function" else "custom_tool_call",
                "id": item_id,
                "call_id": block["id"],
                "name": binding["name"],
                "status": "completed",
            }
            if binding["namespace"]:
                item["namespace"] = binding["namespace"]
            if binding["kind"] == "custom":
                if set(block["input"]) != {"input"} or not isinstance(block["input"]["input"], str):
                    raise ModelClientError(
                        "invalid_response", "custom tool requires one text input"
                    )
                item["input"] = block["input"]["input"]
            else:
                item["arguments"] = json.dumps(block["input"], ensure_ascii=False, allow_nan=False)
            output.append(item)
            calls += 1
        else:
            raise ModelClientError("invalid_response", "unsupported Anthropic content block")
    if (stop == "tool_use" and not calls) or (stop == "end_turn" and calls):
        raise ModelClientError("invalid_response", "Anthropic stop reason contradicts tool output")
    if stop == "end_turn" and not visible_text:
        raise ModelClientError("invalid_response", "Anthropic response has no assistant output")
    usage = raw.get("usage")
    if not isinstance(usage, Mapping) or any(
        isinstance(usage.get(key), bool) or not isinstance(usage.get(key), int) or usage[key] < 0
        for key in ("input_tokens", "output_tokens")
    ):
        raise ModelClientError("invalid_response", "Anthropic usage accounting is missing")
    cache = [
        usage.get(key, 0) for key in ("cache_creation_input_tokens", "cache_read_input_tokens")
    ]
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in cache):
        raise ModelClientError("invalid_response", "invalid Anthropic cache usage")
    input_tokens = usage["input_tokens"] + sum(cache)
    result = {
        "id": raw["id"],
        "object": "response",
        "model": raw.get("model"),
        "status": "incomplete" if stop == "max_tokens" else "completed",
        "output": output,
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": usage["output_tokens"],
            "total_tokens": input_tokens + usage["output_tokens"],
            "input_tokens_details": {"cached_tokens": cache[1]},
            "anthropic_usage": _sanitized_usage(usage),
        },
    }
    if stop == "max_tokens":
        result["incomplete_details"] = {"reason": "max_output_tokens"}
    return result


def _assistant_response(decoded: Any) -> dict[str, Any]:
    if not isinstance(decoded, Mapping) or decoded.get("status") not in {"completed", "incomplete"}:
        raise ModelClientError("invalid_response", "Bedrock response is not a completed result")
    output = decoded.get("output")
    if not isinstance(output, list):
        raise ModelClientError("invalid_response", "Bedrock response has no output items")
    text: list[str] = []
    calls: list[dict[str, Any]] = []
    for item in output:
        if not isinstance(item, Mapping):
            raise ModelClientError("invalid_response", "Bedrock output item is malformed")
        if item.get("type") == "message":
            content = item.get("content")
            if item.get("role") != "assistant" or not isinstance(content, list):
                raise ModelClientError("invalid_response", "Bedrock message is malformed")
            for block in content:
                if not isinstance(block, Mapping):
                    raise ModelClientError("invalid_response", "Bedrock content is malformed")
                if block.get("type") == "output_text" and isinstance(block.get("text"), str):
                    text.append(block["text"])
                elif block.get("type") == "refusal":
                    raise ModelClientError("model_refusal", "Bedrock model refused the request")
                else:
                    raise ModelClientError("invalid_response", "Bedrock content is malformed")
        elif item.get("type") == "function_call":
            if not all(
                isinstance(item.get(key), str) and item[key] for key in ("call_id", "name")
            ) or not isinstance(item.get("arguments"), str):
                raise ModelClientError("invalid_response", "Bedrock function call is malformed")
            calls.append(
                {
                    "id": item["call_id"],
                    "type": "function",
                    "function": {"name": item["name"], "arguments": item["arguments"]},
                }
            )
        elif item.get("type") != "reasoning":
            raise ModelClientError("invalid_response", "unexpected server-side output item")
    finish_reason = "tool_calls" if calls else "stop"
    if decoded["status"] == "incomplete":
        details = decoded.get("incomplete_details")
        if not isinstance(details, Mapping) or details.get("reason") != "max_output_tokens":
            raise ModelClientError("incomplete_response", "Bedrock response did not complete")
        finish_reason = "length"
    empty_output = not any(text) and not calls and finish_reason != "length"
    # Operator deviation (2026-10-05/07): a completed response with no assistant output
    # is returned as an empty assistant turn (callers map it to a stop signal or a
    # creation failure) instead of a RECEIVED_INVALID seal that kills the worker.
    raw_usage = decoded.get("usage")
    if not isinstance(raw_usage, Mapping):
        raise ModelClientError("invalid_response", "Bedrock response has no usage accounting")
    usage = _sanitized_usage(raw_usage)
    if "input_tokens" in usage:
        usage["prompt_tokens"] = usage["input_tokens"]
    if "output_tokens" in usage:
        usage["completion_tokens"] = usage["output_tokens"]
    result = {
        "role": "assistant",
        "content": "\n".join(text) if text else ("" if empty_output else None),
        "tool_calls": calls,
        "finish_reason": finish_reason,
        "usage": usage,
        "response_id": decoded.get("id"),
        "_bedrock_output_items": deepcopy(output),
    }
    if empty_output:
        result["empty_output"] = True
    return result


class OpenAICompatibleClient:
    """Stateless Mantle client; each completion observes at most one model sample.

    Operator deviation from the strict single-POST rule (chosen 2026-10-05, kept for
    the 2026-10-07 Terra/Opus matrices): HTTP 429/5xx rejections, connection failures,
    ``status: failed`` bodies and at most ``timeout_retry_attempts`` client timeouts are
    re-sent after a backoff. Under hundreds of concurrent chains Bedrock Mantle rejected
    or hung about 1% of requests, which compounds to most chains without re-sends. A
    received 2xx result is never discarded or resampled; every retry is logged as a
    ``bedrock_retry`` event and the policy name is bound into the journal payload.
    """

    def __init__(
        self,
        endpoint: str,
        *,
        config: GenerationConfig | None = None,
        api_key: str | Callable[[], str] = "",
        timeout_seconds: float = 300.0,
        opener: Any | None = None,
        token_counter: ChatTokenCounter | None = None,
        usage_path: Path | None = None,
        usage_role: str | None = None,
        retry_attempts: int = 6,
        retry_backoff_seconds: float = 2.0,
        timeout_retry_attempts: int = 2,
    ) -> None:
        if not endpoint or timeout_seconds <= 0:
            raise ValueError("endpoint and timeout_seconds must be valid")
        if isinstance(retry_attempts, bool) or not isinstance(retry_attempts, int):
            raise ValueError("retry_attempts must be an integer")
        if retry_attempts < 1 or retry_backoff_seconds < 0:
            raise ValueError("retry_attempts must be >= 1 and retry_backoff_seconds >= 0")
        if (
            isinstance(timeout_retry_attempts, bool)
            or not isinstance(timeout_retry_attempts, int)
            or timeout_retry_attempts < 0
        ):
            raise ValueError("timeout_retry_attempts must be a non-negative integer")
        self.retry_attempts = retry_attempts
        self.retry_backoff_seconds = float(retry_backoff_seconds)
        self.timeout_retry_attempts = timeout_retry_attempts
        self.retry_events: list[dict[str, Any]] = []
        self.config = config or GenerationConfig()
        route = (
            bedrock_messages_endpoint
            if self.config.transport == "bedrock-messages"
            else bedrock_responses_endpoint
        )
        self.endpoint = route(endpoint)
        self.api_key = api_key
        self.timeout_seconds = float(timeout_seconds)
        self._opener = opener or urllib.request.urlopen
        self._token_counter = token_counter
        self._usage_history: list[dict[str, Any]] = []
        self._usage_path, self._usage_role = usage_path, usage_role

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(endpoint={self.endpoint!r}, "
            f"model={self.config.model!r}, api_key=<redacted>)"
        )

    @property
    def token_counter(self) -> ChatTokenCounter | None:
        return self._token_counter

    @property
    def usage_history(self) -> tuple[dict[str, Any], ...]:
        return tuple(deepcopy(item) for item in self._usage_history)

    @property
    def last_usage(self) -> dict[str, Any] | None:
        return None if not self._usage_history else deepcopy(self._usage_history[-1])

    def _prepare(
        self,
        messages: Sequence[Mapping[str, Any]],
        tools: Sequence[Mapping[str, Any]] | None,
        max_output_tokens: int | None,
    ) -> urllib.request.Request:
        token = self.api_key() if callable(self.api_key) else self.api_key
        normalized = _response_input(messages)
        limit = self.config.max_output_tokens if max_output_tokens is None else max_output_tokens
        if limit is not None and (
            isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0
        ):
            raise ValueError("max_output_tokens must be positive")
        payload: dict[str, Any] = {
            "model": self.config.model,
            "input": normalized,
            "store": False,
            "include": ["reasoning.encrypted_content"],
        }
        if limit is not None:
            payload["max_output_tokens"] = limit
        if self.config.reasoning_effort is not None:
            payload["reasoning"] = {"effort": self.config.reasoning_effort}
        if self.config.response_format is not None:
            payload["text"] = {"format": deepcopy(dict(self.config.response_format))}
        if tools is not None:
            payload["tools"] = _response_tools(tools)
            payload["tool_choice"] = "auto"
        if self.config.max_input_tokens is not None:
            if self._token_counter is None:
                raise ValueError("max_input_tokens requires a pinned chat token counter")
            observed = self._token_counter.count(messages, tools=tools, chat_template_kwargs=None)
            if observed > self.config.max_input_tokens:
                raise InputTokenBudgetExceeded(observed, self.config.max_input_tokens)
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        if self.config.transport == "bedrock-messages":
            payload = responses_to_anthropic(
                payload,
                model=self.config.model,
                reasoning_effort=self.config.reasoning_effort,
            )
            headers["anthropic-version"] = "2023-06-01"
        return urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )

    def _pause_before_retry(self, attempt: int, reason: str, headers: Any) -> None:
        self.retry_events.append(
            pause_before_retry(
                attempt,
                reason,
                headers,
                base_seconds=self.retry_backoff_seconds,
                context={"role": self._usage_role, "model": self.config.model},
            )
        )

    def _send(self, request: urllib.request.Request) -> tuple[int, bytes]:
        """Return the first observed provider response; re-send only unobserved failures."""
        attempt, timeouts = 1, 0
        while True:
            try:
                with self._opener(request, timeout=self.timeout_seconds) as response:
                    status, body = getattr(response, "status", 200), response.read()
            except urllib.error.HTTPError as exc:
                body = exc.read()
                if exc.code in RETRYABLE_MODEL_HTTP_STATUSES and attempt < self.retry_attempts:
                    self._pause_before_retry(attempt, f"http_{exc.code}", exc.headers)
                    attempt += 1
                    continue
                return exc.code, body
            except (OSError, urllib.error.URLError) as exc:
                if is_timeout(exc):
                    if timeouts < self.timeout_retry_attempts:
                        timeouts += 1
                        self._pause_before_retry(attempt, "timeout", None)
                        attempt += 1
                        continue
                elif attempt < self.retry_attempts:
                    reason = getattr(exc, "reason", exc)
                    self._pause_before_retry(attempt, type(reason).__name__, None)
                    attempt += 1
                    continue
                raise ModelClientError(
                    "transport_error", "model request returned no complete response"
                ) from exc
            decoded = decode_quietly(body) if 200 <= status < 300 else None
            failed = _server_failure_status(decoded)
            if failed is None and empty_completed_output(decoded):
                failed = "empty_output"
            if failed is not None and attempt < self.retry_attempts:
                self._pause_before_retry(attempt, failed, None)
                attempt += 1
                continue
            return status, body

    def _normalize(
        self,
        status: int,
        body: bytes,
        *,
        operation_key: str | None = None,
        tools: Sequence[Mapping[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if not 200 <= status < 300:
            raise ModelClientError(
                "http_error", f"model service returned HTTP {status}", status=status
            )
        try:
            decoded = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ModelClientError("invalid_json", "model service returned invalid JSON") from exc
        failed_status = _server_failure_status(decoded)
        if failed_status is not None:
            raise ModelClientError(
                "server_failed_response", f"model service reported {failed_status}"
            )
        try:
            if self.config.transport == "bedrock-messages":
                decoded = anthropic_to_responses(decoded, tools=_response_tools(tools or []))
            result = _assistant_response(decoded)
        except ModelClientError as exc:
            print(
                json.dumps(
                    {
                        "event": "bedrock_invalid_response",
                        "role": self._usage_role,
                        "model": self.config.model,
                        "code": exc.code,
                        **_response_shape(decoded),
                    }
                ),
                file=sys.stderr,
                flush=True,
            )
            raise
        self._usage_history.append(deepcopy(result["usage"]))
        if self._usage_path is not None:
            self._usage_path.parent.mkdir(parents=True, exist_ok=True)
            record = {
                "role": self._usage_role,
                "model": self.config.model,
                "usage": result["usage"],
                "response_id": result["response_id"],
                "attempts": 1,
            }
            if operation_key is not None:
                record["operation_key"] = operation_key
            descriptor = os.open(self._usage_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                os.write(descriptor, (json.dumps(record, allow_nan=False) + "\n").encode("utf-8"))
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        return result

    def complete(
        self,
        messages: Sequence[Mapping[str, Any]],
        *,
        tools: Sequence[Mapping[str, Any]] | None = None,
        seed: int | None = None,
        max_output_tokens: int | None = None,
    ) -> dict[str, Any]:
        del seed
        return self._normalize(
            *self._send(self._prepare(messages, tools, max_output_tokens)), tools=tools
        )

    def complete_journaled(
        self,
        journal: Any,
        operation_id: str,
        payload: Any,
        messages: Sequence[Mapping[str, Any]],
        *,
        tools: Sequence[Mapping[str, Any]] | None = None,
        seed: int | None = None,
        max_output_tokens: int | None = None,
    ) -> dict[str, Any]:
        status = journal.authentication_failure()
        if status is not None and not journal.dispatched(operation_id):
            raise ModelClientError(
                "authentication_failed", "earlier model authentication failed", status=status
            )
        binding = {
            "inputs": payload,
            "endpoint": self.endpoint,
            "config": asdict(self.config),
            "messages": list(messages),
            "tools": tools,
            "seed": seed,
            "max_output_tokens": max_output_tokens,
            "delivery_policy": TRANSPORT_RETRY_POLICY,
        }
        operation_key = canonical_json_sha256(
            {"journal": str(journal.root.resolve()), "operation_id": operation_id}
        )
        return journal.dispatch_raw(
            operation_id,
            binding,
            lambda: self._prepare(messages, tools, max_output_tokens),
            self._send,
            lambda status, body: self._normalize(
                status, body, operation_key=operation_key, tools=tools
            ),
        )


_FAILED_RESPONSE_STATUSES = frozenset({"failed", "cancelled", "queued", "in_progress"})
# HTTP rejections that prove the service produced no sample for the request.
RETRYABLE_MODEL_HTTP_STATUSES = frozenset({429, 500, 502, 503, 504})
TRANSPORT_RETRY_POLICY = "bounded_resend_of_unobserved_transport_failures_v1"


def empty_completed_output(decoded: Any) -> bool:
    """A completed Responses object with no output items at all (observed from Terra)."""
    return (
        isinstance(decoded, Mapping)
        and decoded.get("status") == "completed"
        and decoded.get("output") == []
    )


def decode_quietly(body: bytes) -> Any:
    """Decode a JSON body for inspection only; never raise."""
    try:
        return json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        return None


def is_timeout(exc: BaseException) -> bool:
    reason = getattr(exc, "reason", None)
    return isinstance(exc, TimeoutError) or isinstance(reason, TimeoutError)


_sleep: Callable[[float], None] = time.sleep


def pause_before_retry(
    attempt: int,
    reason: str,
    headers: Any,
    *,
    base_seconds: float,
    context: Mapping[str, Any],
    sleep: Callable[[float], None] | None = None,
) -> dict[str, Any]:
    """Log one operator-visible retry event (no payload, no credential) and back off."""
    retry_after = headers.get("Retry-After") if headers is not None else None
    delay = retry_delay_seconds(attempt, retry_after, base_seconds=base_seconds)
    event = {
        "event": "bedrock_retry",
        **dict(context),
        "attempt": attempt,
        "reason": reason,
        "delay_seconds": round(delay, 1),
    }
    print(json.dumps(event), file=sys.stderr, flush=True)
    (sleep or _sleep)(delay)
    return event


def _server_failure_status(decoded: Any) -> str | None:
    """Name the server-side failure carried by a 200 response, or None if it is a result."""
    if not isinstance(decoded, Mapping):
        return None
    status = decoded.get("status")
    if isinstance(status, str) and status in _FAILED_RESPONSE_STATUSES:
        return f"response_status_{status}"
    error = decoded.get("error")
    if isinstance(error, Mapping) and error:
        code = error.get("code") or error.get("type")
        return f"response_error_{code}" if isinstance(code, str) and code else "response_error"
    return None


def _response_shape(decoded: Any) -> dict[str, Any]:
    """Describe a response by status and item/content types only."""
    if not isinstance(decoded, Mapping):
        return {"decoded_type": type(decoded).__name__}
    shape: dict[str, Any] = {"status": decoded.get("status")}
    details = decoded.get("incomplete_details")
    if isinstance(details, Mapping):
        shape["incomplete_reason"] = details.get("reason")
    output = decoded.get("output")
    if isinstance(output, list):
        shape["output_types"] = [
            item.get("type") if isinstance(item, Mapping) else type(item).__name__
            for item in output
        ]
        shape["content_types"] = [
            block.get("type") if isinstance(block, Mapping) else type(block).__name__
            for item in output
            if isinstance(item, Mapping) and isinstance(item.get("content"), list)
            for block in item["content"]
        ]
        shape["message_roles"] = [
            item.get("role")
            for item in output
            if isinstance(item, Mapping) and item.get("type") == "message"
        ]
    else:
        shape["output_type"] = type(output).__name__
    shape["has_usage"] = isinstance(decoded.get("usage"), Mapping)
    return shape


def retry_delay_seconds(
    attempt: int,
    retry_after: str | None,
    *,
    base_seconds: float,
    cap_seconds: float = 60.0,
) -> float:
    """Exponential backoff honouring an integer Retry-After header when present."""
    if retry_after is not None:
        with contextlib.suppress(ValueError, TypeError):
            return min(max(float(retry_after), 0.0), cap_seconds)
    return min(base_seconds * 2 ** (attempt - 1), cap_seconds)


def _sanitized_usage(value: Mapping[str, Any]) -> dict[str, Any]:
    """Copy only numeric provider-usage fields into auditable client state."""

    result: dict[str, Any] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            continue
        if isinstance(item, Mapping):
            nested = _sanitized_usage(item)
            if nested:
                result[key] = nested
        elif isinstance(item, (int, float)) and not isinstance(item, bool):
            result[key] = item
    return result
