"""Small stateless OpenAI-compatible client used only by the tau pipeline."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from .batch_constants import MODEL_ID, MODEL_REVISION


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


@dataclass(frozen=True)
class GenerationConfig:
    model: str = MODEL_ID
    revision: str = MODEL_REVISION
    temperature: float = 1.0
    top_p: float = 0.95
    top_k: int = 20
    min_p: float = 0.0
    presence_penalty: float = 0.0
    repetition_penalty: float = 1.0
    enable_thinking: bool = True
    preserve_thinking: bool = False
    reasoning_effort: str | None = "xhigh"
    max_output_tokens: int = 4096


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
    ) -> None:
        if not endpoint or timeout_seconds <= 0:
            raise ValueError("endpoint and timeout_seconds must be valid")
        self.base_endpoint = endpoint.rstrip("/")
        self.endpoint = self.base_endpoint
        if not self.endpoint.endswith("/chat/completions"):
            self.endpoint += (
                "/chat/completions" if self.endpoint.endswith("/v1") else "/v1/chat/completions"
            )
        self.base_endpoint = self.endpoint.removesuffix("/chat/completions")
        self.config = config or GenerationConfig()
        self.api_key = api_key
        self.timeout_seconds = float(timeout_seconds)
        self._opener = opener or urllib.request.urlopen
        self.last_response_metadata: dict[str, Any] = {}

    def count_tokens(self, text: str) -> int:
        """Count exact model tokens through vLLM's tokenizer endpoint."""

        if not isinstance(text, str):
            raise TypeError("tokenizer input must be text")
        request = urllib.request.Request(
            # vLLM's tokenizer is outside the OpenAI-compatible /v1 router.
            self.base_endpoint.removesuffix("/v1") + "/tokenize",
            data=json.dumps(
                {"model": self.config.model, "prompt": text},
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
        except Exception as exc:
            raise ModelClientError("tokenizer_error", "model tokenizer endpoint failed") from exc
        count = decoded.get("count") if isinstance(decoded, dict) else None
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            tokens = decoded.get("tokens") if isinstance(decoded, dict) else None
            if not isinstance(tokens, list):
                raise ModelClientError("tokenizer_error", "tokenizer response has no count")
            count = len(tokens)
        return count

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
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": normalized,
            "temperature": self.config.temperature,
            "top_p": self.config.top_p,
            "top_k": self.config.top_k,
            "min_p": self.config.min_p,
            "presence_penalty": self.config.presence_penalty,
            "repetition_penalty": self.config.repetition_penalty,
            "max_tokens": limit,
            "chat_template_kwargs": {
                "enable_thinking": self.config.enable_thinking,
                "preserve_thinking": self.config.preserve_thinking,
            },
        }
        if self.config.reasoning_effort is not None:
            payload["reasoning_effort"] = self.config.reasoning_effort
        if seed is not None:
            payload["seed"] = seed
        if tools is not None:
            payload["tools"] = [dict(tool) for tool in tools]
            payload["tool_choice"] = "auto"
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        started = time.monotonic()
        self.last_response_metadata = {}
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
        finish_reason = choices[0].get("finish_reason")
        usage = decoded.get("usage")
        self.last_response_metadata = {
            "duration_seconds": time.monotonic() - started,
            "finish_reason": finish_reason,
            "usage": {
                key: value
                for key, value in (usage.items() if isinstance(usage, dict) else ())
                if key in {"prompt_tokens", "completion_tokens", "total_tokens"}
                and isinstance(value, int)
                and not isinstance(value, bool)
                and value >= 0
            },
        }
        if finish_reason == "length":
            raise ModelClientError(
                "finish_reason_length",
                "model response exhausted its fixed output budget",
            )
        if finish_reason not in {None, "stop", "tool_calls"}:
            raise ModelClientError(
                "finish_reason_invalid",
                f"model returned unsupported finish_reason: {finish_reason!r}",
            )
        message = choices[0].get("message")
        if not isinstance(message, dict):
            raise ModelClientError("invalid_response", "model response has no message")
        # Provider-private reasoning may be present in ``message``.  Callers either
        # consume the visible content immediately (compiler) or explicitly strip
        # it at the Tau agent boundary; it is never copied into public artifacts.
        return message
