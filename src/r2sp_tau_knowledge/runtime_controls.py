"""Serializable, additive model controls for long-context tau cells.

The legacy preliminary runtime does not construct these controls and therefore
keeps its frozen generation behavior.  New experiment workers pass an exact
mapping through :meth:`RuntimeControls.from_dict`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


def _positive_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _finite_number(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be numeric")
    normalized = float(value)
    if normalized != normalized or normalized in {float("inf"), float("-inf")}:
        raise ValueError(f"{name} must be finite")
    return normalized


@dataclass(frozen=True, slots=True)
class RuntimeGenerationSettings:
    """One participant's complete and auditable sampling configuration."""

    temperature: float
    top_p: float
    top_k: int
    min_p: float
    presence_penalty: float
    repetition_penalty: float
    enable_thinking: bool
    preserve_thinking: bool
    reasoning_effort: str | None
    max_output_tokens: int

    def __post_init__(self) -> None:
        for name in (
            "temperature",
            "top_p",
            "min_p",
            "presence_penalty",
            "repetition_penalty",
        ):
            object.__setattr__(self, name, _finite_number(name, getattr(self, name)))
        _positive_int("top_k", self.top_k)
        _positive_int("max_output_tokens", self.max_output_tokens)
        if not 0 <= self.top_p <= 1 or not 0 <= self.min_p <= 1:
            raise ValueError("top_p and min_p must be in [0, 1]")
        if not isinstance(self.enable_thinking, bool) or not isinstance(
            self.preserve_thinking, bool
        ):
            raise TypeError("thinking controls must be boolean")
        if self.reasoning_effort is not None and self.reasoning_effort not in {
            "low",
            "medium",
            "high",
            "xhigh",
        }:
            raise ValueError("reasoning_effort is invalid")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> RuntimeGenerationSettings:
        if not isinstance(value, Mapping):
            raise TypeError("generation settings must be a mapping")
        expected = {
            "temperature",
            "top_p",
            "top_k",
            "min_p",
            "presence_penalty",
            "repetition_penalty",
            "enable_thinking",
            "preserve_thinking",
            "reasoning_effort",
            "max_output_tokens",
        }
        if set(value) != expected:
            raise ValueError("generation settings fields do not match the locked schema")
        return cls(**{name: value[name] for name in expected})

    def to_dict(self) -> dict[str, Any]:
        return {
            "temperature": self.temperature,
            "top_p": self.top_p,
            "top_k": self.top_k,
            "min_p": self.min_p,
            "presence_penalty": self.presence_penalty,
            "repetition_penalty": self.repetition_penalty,
            "enable_thinking": self.enable_thinking,
            "preserve_thinking": self.preserve_thinking,
            "reasoning_effort": self.reasoning_effort,
            "max_output_tokens": self.max_output_tokens,
        }

    def to_litellm_args(
        self,
        endpoint: str,
        *,
        transport: str = "local-vllm",
    ) -> dict[str, Any]:
        if transport not in {"local-vllm", "deepseek"}:
            raise ValueError("generation transport is not supported")
        if transport == "deepseek":
            result: dict[str, Any] = {
                "api_base": endpoint,
                "max_tokens": self.max_output_tokens,
                "num_retries": 0,
                "extra_body": {"thinking": {"type": "enabled"}},
            }
            if self.reasoning_effort is not None:
                result["reasoning_effort"] = self.reasoning_effort
            return result
        chat_template_kwargs = {
            "enable_thinking": self.enable_thinking,
            "preserve_thinking": self.preserve_thinking,
        }
        # GLM's native chat template names preserved-thinking behavior
        # ``clear_thinking=false``.  Keep the existing Qwen flag for backwards
        # compatibility and add the GLM spelling only when preservation is
        # explicitly enabled.
        if self.preserve_thinking:
            chat_template_kwargs["clear_thinking"] = False
        result: dict[str, Any] = {
            "api_base": endpoint,
            "api_key": "tau-local-evaluation",
            "temperature": self.temperature,
            "top_p": self.top_p,
            "presence_penalty": self.presence_penalty,
            "max_tokens": self.max_output_tokens,
            "num_retries": 0,
            "extra_body": {
                "top_k": self.top_k,
                "min_p": self.min_p,
                "repetition_penalty": self.repetition_penalty,
                "chat_template_kwargs": chat_template_kwargs,
            },
        }
        if self.reasoning_effort is not None:
            result["reasoning_effort"] = self.reasoning_effort
        return result


@dataclass(frozen=True, slots=True)
class RuntimeUserSettings:
    """The deliberately small, deterministic user-simulator configuration."""

    temperature: float
    enable_thinking: bool
    max_output_tokens: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "temperature",
            _finite_number("temperature", self.temperature),
        )
        if not isinstance(self.enable_thinking, bool):
            raise TypeError("enable_thinking must be boolean")
        _positive_int("max_output_tokens", self.max_output_tokens)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> RuntimeUserSettings:
        if not isinstance(value, Mapping):
            raise TypeError("user settings must be a mapping")
        expected = {"temperature", "enable_thinking", "max_output_tokens"}
        if set(value) != expected:
            raise ValueError("user settings fields do not match the locked schema")
        return cls(**{name: value[name] for name in expected})

    def to_dict(self) -> dict[str, Any]:
        return {
            "temperature": self.temperature,
            "enable_thinking": self.enable_thinking,
            "max_output_tokens": self.max_output_tokens,
        }

    def to_litellm_args(
        self,
        endpoint: str,
        *,
        transport: str = "local-vllm",
    ) -> dict[str, Any]:
        if transport not in {"local-vllm", "deepseek"}:
            raise ValueError("user transport is not supported")
        if transport == "deepseek":
            return {
                "api_base": endpoint,
                "temperature": self.temperature,
                "max_tokens": self.max_output_tokens,
                "num_retries": 0,
                "extra_body": {"thinking": {"type": "disabled"}},
            }
        return {
            "api_base": endpoint,
            "api_key": "tau-local-evaluation",
            "temperature": self.temperature,
            "max_tokens": self.max_output_tokens,
            "num_retries": 0,
            "extra_body": {
                "chat_template_kwargs": {
                    "enable_thinking": self.enable_thinking,
                }
            },
        }


@dataclass(frozen=True, slots=True)
class RuntimeControls:
    """Long-context admission and generation controls for one fresh cell."""

    agent: RuntimeGenerationSettings
    user: RuntimeUserSettings
    max_input_tokens: int
    assistant_completion_budget: int

    def __post_init__(self) -> None:
        _positive_int("max_input_tokens", self.max_input_tokens)
        _positive_int("assistant_completion_budget", self.assistant_completion_budget)
        if self.agent.max_output_tokens > self.assistant_completion_budget:
            raise ValueError("agent max_output_tokens exceeds the per-cell completion budget")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> RuntimeControls:
        if not isinstance(value, Mapping):
            raise TypeError("runtime controls must be a mapping")
        expected = {
            "agent",
            "user",
            "max_input_tokens",
            "assistant_completion_budget",
        }
        if set(value) != expected:
            raise ValueError("runtime control fields do not match the locked schema")
        return cls(
            agent=RuntimeGenerationSettings.from_dict(value["agent"]),
            user=RuntimeUserSettings.from_dict(value["user"]),
            max_input_tokens=value["max_input_tokens"],
            assistant_completion_budget=value["assistant_completion_budget"],
        )

    @classmethod
    def from_experiment_spec(cls, spec: Any) -> RuntimeControls:
        """Project the full-document YAML spec without importing its module."""

        generation = spec.model.generation
        user = spec.user_simulator
        context = spec.context
        return cls(
            agent=RuntimeGenerationSettings(
                temperature=generation.temperature,
                top_p=generation.top_p,
                top_k=generation.top_k,
                min_p=generation.min_p,
                presence_penalty=generation.presence_penalty,
                repetition_penalty=generation.repetition_penalty,
                enable_thinking=generation.thinking,
                preserve_thinking=generation.preserve_thinking,
                reasoning_effort=generation.reasoning_effort,
                max_output_tokens=generation.max_output_tokens,
            ),
            user=RuntimeUserSettings(
                temperature=user.temperature,
                enable_thinking=user.thinking,
                max_output_tokens=user.max_output_tokens,
            ),
            max_input_tokens=context.request_input_token_limit,
            assistant_completion_budget=context.cumulative_assistant_token_limit,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent.to_dict(),
            "user": self.user.to_dict(),
            "max_input_tokens": self.max_input_tokens,
            "assistant_completion_budget": self.assistant_completion_budget,
        }
