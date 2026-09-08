"""Small stateless OpenAI-compatible client used only by the tau pipeline."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Protocol

from .constants import MODEL_ID, MODEL_REVISION


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


class ChatTokenCounter(Protocol):
    """Count the exact server-rendered tokens for one chat request."""

    def count(
        self,
        messages: Sequence[Mapping[str, Any]],
        *,
        tools: Sequence[Mapping[str, Any]] | None = None,
        chat_template_kwargs: Mapping[str, Any] | None = None,
    ) -> int: ...


class VllmChatTokenCounter:
    """Use the serving model's pinned tokenizer through vLLM's ``/tokenize`` API."""

    def __init__(
        self,
        endpoint: str,
        *,
        model: str,
        api_key: str = "tau-local-evaluation",
        timeout_seconds: float = 60.0,
        opener: Any | None = None,
    ) -> None:
        if not isinstance(endpoint, str) or not endpoint.strip() or timeout_seconds <= 0:
            raise ValueError("endpoint and timeout_seconds must be valid")
        if not isinstance(model, str) or not model.strip():
            raise ValueError("model must be a non-empty string")
        root = endpoint.rstrip("/")
        if root.endswith("/v1"):
            root = root[:-3]
        self.endpoint = f"{root}/tokenize"
        self.model = model
        self.api_key = api_key
        self.timeout_seconds = float(timeout_seconds)
        self._opener = opener or urllib.request.urlopen
        self.basis = "server_chat_template"

    def count(
        self,
        messages: Sequence[Mapping[str, Any]],
        *,
        tools: Sequence[Mapping[str, Any]] | None = None,
        chat_template_kwargs: Mapping[str, Any] | None = None,
    ) -> int:
        normalized = [dict(message) for message in messages]
        if any(
            message.get("role") not in {"system", "user", "assistant", "tool"}
            for message in normalized
        ):
            raise ValueError("messages must use supported OpenAI roles")
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": normalized,
            "add_generation_prompt": True,
        }
        if tools is not None:
            payload["tools"] = [dict(tool) for tool in tools]
        if chat_template_kwargs is not None:
            payload["chat_template_kwargs"] = dict(chat_template_kwargs)
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with self._opener(request, timeout=self.timeout_seconds) as response:
                decoded = json.loads(response.read())
        except urllib.error.HTTPError as exc:
            raise ModelClientError(
                "tokenize_http_error",
                f"tokenizer service returned HTTP {exc.code}",
                status=exc.code,
            ) from exc
        except (OSError, TimeoutError, urllib.error.URLError) as exc:
            raise ModelClientError("tokenize_transport_error", str(exc)) from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ModelClientError(
                "tokenize_invalid_json", "tokenizer service returned invalid JSON"
            ) from exc
        count = decoded.get("count") if isinstance(decoded, dict) else None
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ModelClientError(
                "tokenize_invalid_response", "tokenizer service returned no token count"
            )
        return count


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
    ) -> None:
        if not isinstance(endpoint, str) or not endpoint.strip() or timeout_seconds <= 0:
            raise ValueError("endpoint and timeout_seconds must be valid")
        if not isinstance(model, str) or not model.strip():
            raise ValueError("model must be a non-empty string")
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
        try:
            with self._opener(request, timeout=self.timeout_seconds) as response:
                decoded = json.loads(response.read())
        except urllib.error.HTTPError as exc:
            raise ModelClientError(
                "tokenize_http_error",
                f"tokenizer service returned HTTP {exc.code}",
                status=exc.code,
            ) from exc
        except (OSError, TimeoutError, urllib.error.URLError) as exc:
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

    Some hosted APIs, including DeepSeek's public endpoint, do not expose a
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


@dataclass(frozen=True)
class GenerationConfig:
    model: str = MODEL_ID
    revision: str = MODEL_REVISION
    temperature: float = 0.7
    top_p: float = 0.8
    top_k: int = 20
    min_p: float = 0.0
    presence_penalty: float = 1.5
    repetition_penalty: float = 1.0
    enable_thinking: bool = False
    preserve_thinking: bool | None = None
    reasoning_effort: str | None = None
    max_output_tokens: int = 4096
    max_input_tokens: int | None = None
    transport: str = "local-vllm"


class OpenAICompatibleClient:
    """No conversation cache: every call contains its complete fresh context."""

    def __init__(
        self,
        endpoint: str = "http://127.0.0.1:18138/v1",
        *,
        config: GenerationConfig | None = None,
        api_key: str = "tau-local-evaluation",
        timeout_seconds: float = 300.0,
        opener: Any | None = None,
        token_counter: ChatTokenCounter | None = None,
    ) -> None:
        if not endpoint or timeout_seconds <= 0:
            raise ValueError("endpoint and timeout_seconds must be valid")
        self.endpoint = endpoint.rstrip("/")
        if not self.endpoint.endswith("/chat/completions"):
            self.endpoint += (
                "/chat/completions" if self.endpoint.endswith("/v1") else "/v1/chat/completions"
            )
        self.config = config or GenerationConfig()
        self.api_key = api_key
        self.timeout_seconds = float(timeout_seconds)
        self._opener = opener or urllib.request.urlopen
        self._token_counter = token_counter
        self._usage_history: list[dict[str, Any]] = []

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(endpoint={self.endpoint!r}, "
            f"model={self.config.model!r}, api_key=<redacted>)"
        )

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
        normalized: list[dict[str, Any]] = []
        for message in messages:
            if not isinstance(message, Mapping) or message.get("role") not in {
                "system",
                "user",
                "assistant",
                "tool",
            }:
                raise ValueError("messages must use supported OpenAI roles")
            normalized.append(dict(message))
        limit = self.config.max_output_tokens if max_output_tokens is None else max_output_tokens
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise ValueError("max_output_tokens must be positive")
        if self.config.transport not in {"local-vllm", "deepseek"}:
            raise ValueError("generation transport is not supported")
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": normalized,
            "max_tokens": limit,
        }
        chat_template_kwargs: dict[str, Any] | None
        if self.config.transport == "local-vllm":
            payload.update(
                {
                    "temperature": self.config.temperature,
                    "top_p": self.config.top_p,
                    "top_k": self.config.top_k,
                    "min_p": self.config.min_p,
                    "presence_penalty": self.config.presence_penalty,
                    "repetition_penalty": self.config.repetition_penalty,
                }
            )
            chat_template_kwargs = {"enable_thinking": self.config.enable_thinking}
            if self.config.preserve_thinking is not None:
                chat_template_kwargs["preserve_thinking"] = self.config.preserve_thinking
                if self.config.preserve_thinking:
                    chat_template_kwargs["clear_thinking"] = False
            payload["chat_template_kwargs"] = chat_template_kwargs
            if seed is not None:
                payload["seed"] = seed
        else:
            chat_template_kwargs = None
            payload["thinking"] = {"type": "enabled" if self.config.enable_thinking else "disabled"}
            # DeepSeek ignores sampling controls in thinking mode.  Omitting
            # them makes the wire request match the provider's documented API.
            if not self.config.enable_thinking:
                payload["temperature"] = self.config.temperature
        if self.config.reasoning_effort is not None and self.config.enable_thinking:
            payload["reasoning_effort"] = self.config.reasoning_effort
        if tools is not None:
            payload["tools"] = [dict(tool) for tool in tools]
            payload["tool_choice"] = "auto"
        if self.config.max_input_tokens is not None:
            maximum = self.config.max_input_tokens
            if isinstance(maximum, bool) or not isinstance(maximum, int) or maximum <= 0:
                raise ValueError("max_input_tokens must be positive")
            if self._token_counter is None:
                raise ValueError("max_input_tokens requires a pinned chat token counter")
            observed = self._token_counter.count(
                normalized,
                tools=tools,
                chat_template_kwargs=chat_template_kwargs,
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
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with self._opener(request, timeout=self.timeout_seconds) as response:
                decoded = json.loads(response.read())
        except urllib.error.HTTPError as exc:
            raise ModelClientError(
                "http_error", f"model service returned HTTP {exc.code}", status=exc.code
            ) from exc
        except (OSError, TimeoutError, urllib.error.URLError) as exc:
            raise ModelClientError("transport_error", str(exc)) from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ModelClientError("invalid_json", "model service returned invalid JSON") from exc
        choices = decoded.get("choices") if isinstance(decoded, dict) else None
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise ModelClientError("invalid_response", "model response has no choice")
        message = choices[0].get("message")
        if not isinstance(message, dict):
            raise ModelClientError("invalid_response", "model response has no message")
        usage = decoded.get("usage")
        if isinstance(usage, Mapping):
            self._usage_history.append(_sanitized_usage(usage))
        result = dict(message)
        finish_reason = choices[0].get("finish_reason")
        if isinstance(finish_reason, str):
            result["finish_reason"] = finish_reason
        return result


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
