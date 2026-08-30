"""Minimal OpenAI-compatible client for the pinned Qwen3.8 pilot model.

The module intentionally uses only the Python standard library.  This keeps the
experiment runner independent from the model-serving environment and makes the
HTTP boundary explicit and easy to audit.
"""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from .http_transport import no_redirect_urlopen

JsonMapping = Mapping[str, Any]


class ModelClient(Protocol):
    """Small interface consumed by the agent and skill compiler."""

    def complete(
        self,
        messages: Sequence[JsonMapping],
        *,
        tools: Sequence[JsonMapping] | None = None,
        seed: int | None = None,
        max_output_tokens: int | None = None,
    ) -> dict[str, Any]:
        """Return one OpenAI-format assistant message."""


@dataclass(frozen=True)
class QwenGenerationConfig:
    """The generation settings frozen by the current protocol."""

    model: str = "Qwen/Qwen3.8-27B"
    revision: str = "1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0"
    enable_thinking: bool = True
    preserve_thinking: bool = False
    reasoning_effort: str = "xhigh"
    temperature: float = 1.0
    top_p: float = 0.95
    top_k: int = 20
    max_output_tokens: int = 8192


class ModelClientError(RuntimeError):
    """Normalized model-service failure safe to persist in run metadata."""

    def __init__(self, code: str, message: str, *, status: int | None = None):
        super().__init__(message)
        self.code = code
        self.status = status


class OpenAICompatibleClient:
    """POST chat-completion requests to a local OpenAI-compatible server."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:18000/v1",
        *,
        api_key: str | None = None,
        config: QwenGenerationConfig | None = None,
        timeout_seconds: float = 120.0,
        opener: Any | None = None,
    ) -> None:
        if not isinstance(base_url, str) or not base_url.strip():
            raise ValueError("base_url must be a non-empty string")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.base_url = base_url.rstrip("/")
        # Authentication is an explicit property of this model-service client.
        # Implicitly borrowing OPENAI_API_KEY could disclose an unrelated
        # external credential to a loopback or user-configured service.
        self.api_key = api_key
        self.config = config or QwenGenerationConfig()
        self.timeout_seconds = float(timeout_seconds)
        self._opener = opener or no_redirect_urlopen

    @property
    def endpoint(self) -> str:
        if self.base_url.endswith("/chat/completions"):
            return self.base_url
        if self.base_url.endswith("/v1"):
            return self.base_url + "/chat/completions"
        return self.base_url + "/v1/chat/completions"

    @property
    def tokenize_endpoint(self) -> str:
        if self.base_url.endswith("/v1"):
            return self.base_url[:-3] + "/tokenize"
        if self.base_url.endswith("/chat/completions"):
            prefix = self.base_url[: -len("/chat/completions")]
            return (prefix[:-3] if prefix.endswith("/v1") else prefix) + "/tokenize"
        return self.base_url + "/tokenize"

    def build_payload(
        self,
        messages: Sequence[JsonMapping],
        *,
        tools: Sequence[JsonMapping] | None = None,
        seed: int | None = None,
        max_output_tokens: int | None = None,
    ) -> dict[str, Any]:
        if not isinstance(messages, Sequence) or isinstance(messages, (str, bytes)):
            raise TypeError("messages must be a sequence of mappings")
        normalized_messages = []
        for message in messages:
            if not isinstance(message, Mapping):
                raise TypeError("each message must be a mapping")
            role = message.get("role")
            if role not in {"system", "user", "assistant", "tool"}:
                raise ValueError("message role is invalid")
            normalized_messages.append(dict(message))

        output_limit = (
            self.config.max_output_tokens if max_output_tokens is None else int(max_output_tokens)
        )
        if output_limit <= 0:
            raise ValueError("max_output_tokens must be positive")

        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": normalized_messages,
            "temperature": self.config.temperature,
            "top_p": self.config.top_p,
            "top_k": self.config.top_k,
            "max_tokens": output_limit,
            "reasoning_effort": self.config.reasoning_effort,
            "chat_template_kwargs": {
                "enable_thinking": self.config.enable_thinking,
                "preserve_thinking": self.config.preserve_thinking,
            },
        }
        if seed is not None:
            if isinstance(seed, bool) or not isinstance(seed, int):
                raise TypeError("seed must be an integer")
            payload["seed"] = seed
        if tools is not None:
            if not isinstance(tools, Sequence) or isinstance(tools, (str, bytes)):
                raise TypeError("tools must be a sequence")
            payload["tools"] = [dict(tool) for tool in tools]
            payload["tool_choice"] = "auto"
        return payload

    def complete(
        self,
        messages: Sequence[JsonMapping],
        *,
        tools: Sequence[JsonMapping] | None = None,
        seed: int | None = None,
        max_output_tokens: int | None = None,
    ) -> dict[str, Any]:
        payload = self.build_payload(
            messages,
            tools=tools,
            seed=seed,
            max_output_tokens=max_output_tokens,
        )
        decoded = self._post_json(self.endpoint, payload)
        choices = decoded.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ModelClientError("invalid_response", "model response has no choices")
        first = choices[0]
        if not isinstance(first, Mapping) or not isinstance(first.get("message"), Mapping):
            raise ModelClientError("invalid_response", "model response has no assistant message")
        return dict(first["message"])

    def count_tokens(self, text: str) -> int:
        """Count raw prompt tokens with the tokenizer loaded by vLLM."""

        if not isinstance(text, str):
            raise TypeError("token-count input must be text")
        decoded = self._post_json(
            self.tokenize_endpoint,
            {"model": self.config.model, "prompt": text, "add_special_tokens": False},
        )
        count = decoded.get("count")
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            tokens = decoded.get("tokens")
            if not isinstance(tokens, list):
                raise ModelClientError(
                    "invalid_response", "tokenizer response has no valid token count"
                )
            count = len(tokens)
        return count

    def verify_tool_contract(self) -> dict[str, Any]:
        """Exercise the configured Qwen reasoning/tool parsers before a run."""

        tool = {
            "type": "function",
            "function": {
                "name": "finish",
                "description": "Return the fixed probe result.",
                "parameters": {
                    "type": "object",
                    "properties": {"status": {"type": "string"}},
                    "required": ["status"],
                    "additionalProperties": False,
                },
            },
        }
        payload = self.build_payload(
            [
                {
                    "role": "system",
                    "content": "Call the provided finish tool exactly once.",
                },
                {"role": "user", "content": "Finish with status probe-ok."},
            ],
            tools=[tool],
            seed=20260829,
            max_output_tokens=128,
        )
        payload["tool_choice"] = {
            "type": "function",
            "function": {"name": "finish"},
        }
        decoded = self._post_json(self.endpoint, payload)
        choices = decoded.get("choices")
        message = (
            choices[0].get("message")
            if isinstance(choices, list) and len(choices) == 1 and isinstance(choices[0], Mapping)
            else None
        )
        if not isinstance(message, Mapping):
            raise ModelClientError(
                "contract_probe_failed", "tool-contract probe has no assistant message"
            )
        calls = message.get("tool_calls")
        if not isinstance(calls, list) or len(calls) != 1:
            raise ModelClientError(
                "contract_probe_failed", "tool parser did not return exactly one tool call"
            )
        call = calls[0]
        function = call.get("function") if isinstance(call, Mapping) else None
        if not isinstance(function, Mapping) or function.get("name") != "finish":
            raise ModelClientError(
                "contract_probe_failed", "tool parser returned the wrong function"
            )
        arguments = function.get("arguments")
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = None
        if not isinstance(arguments, Mapping) or arguments.get("status") != "probe-ok":
            raise ModelClientError(
                "contract_probe_failed", "tool parser returned invalid arguments"
            )
        visible = message.get("content")
        if isinstance(visible, str) and any(
            marker in visible.casefold() for marker in ("<think>", "</think>")
        ):
            raise ModelClientError(
                "contract_probe_failed", "reasoning markup leaked into visible content"
            )
        reasoning = message.get("reasoning_content")
        if reasoning is not None and not isinstance(reasoning, str):
            raise ModelClientError(
                "contract_probe_failed", "reasoning parser returned an invalid field"
            )
        return {
            "function": "finish",
            "arguments_valid": True,
            "reasoning_markup_hidden": True,
        }

    def verify_selection_contract(self, *, selection_k: int = 5) -> dict[str, Any]:
        """Force and validate the exact-cardinality document-selection tool contract."""

        if isinstance(selection_k, bool) or not isinstance(selection_k, int) or selection_k <= 0:
            raise ValueError("selection_k must be a positive integer")
        candidates = [f"candidate-{index}" for index in range(selection_k)]
        tool = {
            "type": "function",
            "function": {
                "name": "select_docs",
                "description": (
                    f"Select exactly {selection_k} unique resource IDs from retrieved candidates."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "resource_ids": {
                            "type": "array",
                            "items": {"type": "string", "minLength": 1},
                            "minItems": selection_k,
                            "maxItems": selection_k,
                            "uniqueItems": True,
                        }
                    },
                    "required": ["resource_ids"],
                    "additionalProperties": False,
                },
            },
        }
        payload = self.build_payload(
            [
                {
                    "role": "system",
                    "content": "Call select_docs exactly once with all supplied candidate IDs.",
                },
                {
                    "role": "user",
                    "content": json.dumps({"candidate_resource_ids": candidates}),
                },
            ],
            tools=[tool],
            seed=20260829,
            max_output_tokens=256,
        )
        payload["tool_choice"] = {
            "type": "function",
            "function": {"name": "select_docs"},
        }
        decoded = self._post_json(self.endpoint, payload)
        choices = decoded.get("choices")
        message = (
            choices[0].get("message")
            if isinstance(choices, list) and len(choices) == 1 and isinstance(choices[0], Mapping)
            else None
        )
        calls = message.get("tool_calls") if isinstance(message, Mapping) else None
        call = calls[0] if isinstance(calls, list) and len(calls) == 1 else None
        function = call.get("function") if isinstance(call, Mapping) else None
        arguments = function.get("arguments") if isinstance(function, Mapping) else None
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = None
        resource_ids = arguments.get("resource_ids") if isinstance(arguments, Mapping) else None
        valid = bool(
            isinstance(function, Mapping)
            and function.get("name") == "select_docs"
            and isinstance(resource_ids, list)
            and len(resource_ids) == selection_k
            and all(isinstance(item, str) and item for item in resource_ids)
            and len(set(resource_ids)) == selection_k
            and resource_ids == candidates
        )
        if not valid:
            raise ModelClientError(
                "selection_contract_probe_failed",
                "selection parser did not return the exact unique candidate IDs",
            )
        return {
            "function": "select_docs",
            "arguments_valid": True,
            "selection_k": selection_k,
            "resource_ids": list(resource_ids),
        }

    def _post_json(self, endpoint: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = "Bearer " + self.api_key
        request = urllib.request.Request(endpoint, data=data, headers=headers, method="POST")

        try:
            response = self._opener(request, timeout=self.timeout_seconds)
            if hasattr(response, "__enter__"):
                with response as opened:
                    raw = opened.read()
            else:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            detail = _http_error_detail(exc)
            suffix = (": " + detail) if detail else ""
            raise ModelClientError(
                "http_error",
                f"model service returned HTTP {exc.code}{suffix}",
                status=exc.code,
            ) from None
        except (urllib.error.URLError, TimeoutError) as exc:
            reason = getattr(exc, "reason", None)
            code = "timeout" if isinstance(exc, (TimeoutError, socket.timeout)) else "unavailable"
            if isinstance(reason, (TimeoutError, socket.timeout)):
                code = "timeout"
            raise ModelClientError(code, "model service is unavailable") from None
        except OSError:
            raise ModelClientError("transport_error", "model service transport failed") from None

        try:
            decoded = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ModelClientError(
                "invalid_response", "model service returned invalid JSON"
            ) from None
        if not isinstance(decoded, Mapping):
            raise ModelClientError("invalid_response", "model response must be an object")
        return decoded


def _http_error_detail(exc: urllib.error.HTTPError) -> str:
    """Extract a short server error without ever including headers or credentials."""

    try:
        raw = exc.read(4096)
        decoded = json.loads(raw.decode("utf-8"))
        if isinstance(decoded, Mapping):
            error = decoded.get("error")
            value = error.get("message") if isinstance(error, Mapping) else error
            if isinstance(value, str):
                return " ".join(value.split())[:300]
    except Exception:
        return ""
    return ""


__all__ = [
    "ModelClient",
    "ModelClientError",
    "OpenAICompatibleClient",
    "QwenGenerationConfig",
]
