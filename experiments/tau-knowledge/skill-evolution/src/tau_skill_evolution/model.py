"""Stateless Bedrock Mantle GPT-5.x Responses client and shared embedding token counters."""

from __future__ import annotations

import contextlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

from .constants import DEFAULT_MODEL, SUPPORTED_MODELS

# Loopback helper services (tokenizer, embeddings) are deterministic and side-effect
# free; only gateway/overload statuses are retried, never model requests.
RETRYABLE_LOCAL_HTTP_STATUSES = frozenset({502, 503, 504})
# Model requests rejected with these statuses were not executed by the model (throttling
# or gateway/server failure), so re-sending them is not a second sample.
RETRYABLE_MODEL_HTTP_STATUSES = frozenset({429, 500, 502, 503, 504})


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
    """Estimate chat admission with a pinned plain-text tokenizer.

    Some hosted APIs do not expose a
    tokenizer route.  This adapter keeps admission deterministic by encoding
    the complete messages and tool schemas as canonical JSON and counting that
    text with a separately pinned local tokenizer.  Provider-reported usage is
    still authoritative for the cumulative completion budget.
    """

    def __init__(self, text_counter: Any, *, basis: str = "serialized_text_estimate") -> None:
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
        del chat_template_kwargs
        payload: dict[str, Any] = {
            "messages": [dict(message) for message in messages],
            "add_generation_prompt": True,
        }
        if tools is not None:
            payload["tools"] = [dict(tool) for tool in tools]
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
        return observed


@dataclass(frozen=True, slots=True)
class GenerationConfig:
    model: str = DEFAULT_MODEL
    reasoning_effort: str | None = "medium"
    max_output_tokens: int = 16384
    max_input_tokens: int | None = None
    transport: str = "bedrock-responses"
    response_format: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.model not in SUPPORTED_MODELS or self.transport != "bedrock-responses":
            raise ValueError(
                "only Bedrock Mantle Responses models "
                + " / ".join(SUPPORTED_MODELS)
                + " are supported"
            )
        if self.reasoning_effort not in {None, "none", "low", "medium", "high", "xhigh"}:
            raise ValueError("invalid GPT-5.x reasoning effort")
        if self.response_format is not None and not isinstance(self.response_format, Mapping):
            raise ValueError("response_format must be a mapping")
        for name in ("max_output_tokens", "max_input_tokens"):
            value = getattr(self, name)
            if value is None and name == "max_input_tokens":
                continue
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")


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
    if not text and not calls and finish_reason != "length":
        if output == [] and decoded["status"] == "completed":
            # GPT-5.6 Terra deterministically returns a completed response with no
            # output items when it has nothing further to say (observed after
            # transfer_to_human_agents). That is an empty assistant message, not a
            # provider failure; the official runtime decides how the episode ends.
            text = [""]
        else:
            raise ModelClientError("invalid_response", "Bedrock response has no assistant output")
    raw_usage = decoded.get("usage")
    if not isinstance(raw_usage, Mapping):
        raise ModelClientError("invalid_response", "Bedrock response has no usage accounting")
    usage = _sanitized_usage(raw_usage)
    if "input_tokens" in usage:
        usage["prompt_tokens"] = usage["input_tokens"]
    if "output_tokens" in usage:
        usage["completion_tokens"] = usage["output_tokens"]
    return {
        "role": "assistant",
        "content": "\n".join(text) if text else None,
        "tool_calls": calls,
        "finish_reason": finish_reason,
        "usage": usage,
        "response_id": decoded.get("id"),
        "_bedrock_output_items": deepcopy(output),
    }


class OpenAICompatibleClient:
    """No conversation cache: every call contains its complete fresh context."""

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
        self.timeout_retry_attempts = timeout_retry_attempts
        self.endpoint = bedrock_responses_endpoint(endpoint)
        self.config = config or GenerationConfig()
        # Either a static bearer token or a resolver re-read before every request
        # (refreshable token files). Never rendered by __repr__ or usage logs.
        self.api_key = api_key
        self.timeout_seconds = float(timeout_seconds)
        self._opener = opener or urllib.request.urlopen
        self._token_counter = token_counter
        self._usage_history: list[dict[str, Any]] = []
        self._usage_path, self._usage_role = usage_path, usage_role
        self.retry_attempts = retry_attempts
        self.retry_backoff_seconds = float(retry_backoff_seconds)
        self.retry_events: list[dict[str, Any]] = []

    def _pause_before_retry(self, attempt: int, reason: str, headers: Any) -> None:
        retry_after = headers.get("Retry-After") if headers is not None else None
        delay = retry_delay_seconds(attempt, retry_after, base_seconds=self.retry_backoff_seconds)
        event = {
            "event": "bedrock_retry",
            "role": self._usage_role,
            "model": self.config.model,
            "attempt": attempt,
            "reason": reason,
            "delay_seconds": round(delay, 1),
        }
        self.retry_events.append(event)
        # Operational visibility only; no payload or credential is ever logged.
        print(json.dumps(event), file=sys.stderr, flush=True)
        time.sleep(delay)

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
        """Return provider token accounting without exposing request credentials."""

        return tuple(deepcopy(item) for item in self._usage_history)

    @property
    def last_usage(self) -> dict[str, Any] | None:
        return None if not self._usage_history else deepcopy(self._usage_history[-1])

    def complete(
        self,
        messages: Sequence[Mapping[str, Any]],
        *,
        tools: Sequence[Mapping[str, Any]] | None = None,
        seed: int | None = None,
        max_output_tokens: int | None = None,
    ) -> dict[str, Any]:
        # Resolve the credential first: a CredentialError (missing/expired token
        # file) must surface before any request is built or journaled as sent.
        token = self.api_key() if callable(self.api_key) else self.api_key
        normalized = _response_input(messages)
        limit = self.config.max_output_tokens if max_output_tokens is None else max_output_tokens
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise ValueError("max_output_tokens must be positive")
        payload: dict[str, Any] = {
            "model": self.config.model,
            "input": normalized,
            "max_output_tokens": limit,
            "store": False,
            "include": ["reasoning.encrypted_content"],
        }
        if self.config.reasoning_effort is not None:
            payload["reasoning"] = {"effort": self.config.reasoning_effort}
        if self.config.response_format is not None:
            payload["text"] = {"format": deepcopy(dict(self.config.response_format))}
        if tools is not None:
            payload["tools"] = _response_tools(tools)
            payload["tool_choice"] = "auto"
        if self.config.max_input_tokens is not None:
            maximum = self.config.max_input_tokens
            if isinstance(maximum, bool) or not isinstance(maximum, int) or maximum <= 0:
                raise ValueError("max_input_tokens must be positive")
            if self._token_counter is None:
                raise ValueError("max_input_tokens requires a pinned chat token counter")
            observed = self._token_counter.count(
                messages,
                tools=tools,
                chat_template_kwargs=None,
            )
            if observed > maximum:
                raise ModelClientError(
                    "input_token_budget_exceeded",
                    f"chat input exceeds pinned limit: observed={observed}, limit={maximum}",
                )
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        # Retry policy: only failures that prove the model did not produce an observed
        # sample are retried (HTTP 429/5xx rejections, connection failures).  Timeouts
        # are never retried because the service may have completed the request; they
        # stay unknown for the journal exactly as before.  A rejected request is not a
        # resample, so this does not change the one-shot semantics of any stage.
        attempt = 1
        timeouts = 0
        while True:
            try:
                with self._opener(request, timeout=self.timeout_seconds) as response:
                    decoded = json.loads(response.read())
                failed_status = _server_failure_status(decoded)
                if failed_status is not None:
                    # HTTP 200 carrying a failed/unfinished response object: the service
                    # produced no sample, so this is a server failure, not a result.
                    if attempt < self.retry_attempts:
                        self._pause_before_retry(attempt, failed_status, None)
                        attempt += 1
                        continue
                    raise ModelClientError(
                        "server_failed_response", f"model service reported {failed_status}"
                    )
                break
            except urllib.error.HTTPError as exc:
                if exc.code in RETRYABLE_MODEL_HTTP_STATUSES and attempt < self.retry_attempts:
                    self._pause_before_retry(attempt, f"http_{exc.code}", exc.headers)
                    attempt += 1
                    continue
                raise ModelClientError(
                    "http_error", f"model service returned HTTP {exc.code}", status=exc.code
                ) from exc
            except TimeoutError as exc:
                if timeouts < self.timeout_retry_attempts:
                    # Deviation from the original no-resend rule, chosen by the operator on
                    # 2026-10-05: Bedrock Mantle left ~1% of requests hanging under load.
                    # The first sample was never observed, so the retry is the first
                    # observed sample; duplicate server-side work is the only cost.
                    timeouts += 1
                    self._pause_before_retry(attempt, "timeout", None)
                    attempt += 1
                    continue
                raise ModelClientError(
                    "transport_error", "model request returned no valid response"
                ) from exc
            except (OSError, urllib.error.URLError) as exc:
                reason = getattr(exc, "reason", None)
                if isinstance(reason, TimeoutError):
                    if timeouts < self.timeout_retry_attempts:
                        timeouts += 1
                        self._pause_before_retry(attempt, "timeout", None)
                        attempt += 1
                        continue
                    raise ModelClientError(
                        "transport_error", "model request returned no valid response"
                    ) from exc
                if attempt >= self.retry_attempts:
                    raise ModelClientError(
                        "transport_error", "model request returned no valid response"
                    ) from exc
                self._pause_before_retry(attempt, type(exc).__name__, None)
                attempt += 1
                continue
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ModelClientError(
                    "invalid_json", "model service returned invalid JSON"
                ) from exc
        try:
            result = _assistant_response(decoded)
        except ModelClientError as exc:
            # Shape-only diagnostics (statuses and item/content types, never text) so an
            # unexpected provider response can be recognised from the run logs.
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
                "attempts": attempt,
            }
            encoded = (json.dumps(record, allow_nan=False) + "\n").encode("utf-8")
            descriptor = os.open(self._usage_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            try:
                os.write(descriptor, encoded)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        return result


_FAILED_RESPONSE_STATUSES = frozenset({"failed", "cancelled", "queued", "in_progress"})


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
