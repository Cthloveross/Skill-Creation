"""Small stateless OpenAI-compatible client used only by the tau pipeline."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
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
        self.endpoint = endpoint.rstrip("/")
        if not self.endpoint.endswith("/chat/completions"):
            self.endpoint += (
                "/chat/completions" if self.endpoint.endswith("/v1") else "/v1/chat/completions"
            )
        self.config = config or GenerationConfig()
        self.api_key = api_key
        self.timeout_seconds = float(timeout_seconds)
        self._opener = opener or urllib.request.urlopen

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
            "chat_template_kwargs": {"enable_thinking": self.config.enable_thinking},
        }
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
        return message
