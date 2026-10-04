"""Bedrock Responses generation budgets for one fresh bank episode."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


def _positive_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


@dataclass(frozen=True, slots=True)
class RuntimeGenerationSettings:
    reasoning_effort: str
    max_output_tokens: int

    def __post_init__(self) -> None:
        _positive_int("max_output_tokens", self.max_output_tokens)
        if self.reasoning_effort not in {"none", "low", "medium", "high", "xhigh"}:
            raise ValueError("reasoning_effort is invalid")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> RuntimeGenerationSettings:
        if not isinstance(value, Mapping) or set(value) != {
            "reasoning_effort",
            "max_output_tokens",
        }:
            raise ValueError("generation settings fields do not match the locked schema")
        return cls(**value)

    def to_dict(self) -> dict[str, Any]:
        return {
            "reasoning_effort": self.reasoning_effort,
            "max_output_tokens": self.max_output_tokens,
        }


@dataclass(frozen=True, slots=True)
class RuntimeControls:
    agent: RuntimeGenerationSettings
    user: RuntimeGenerationSettings
    max_input_tokens: int
    assistant_completion_budget: int

    def __post_init__(self) -> None:
        _positive_int("max_input_tokens", self.max_input_tokens)
        _positive_int("assistant_completion_budget", self.assistant_completion_budget)
        if self.agent.max_output_tokens > self.assistant_completion_budget:
            raise ValueError("agent max_output_tokens exceeds the per-cell completion budget")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> RuntimeControls:
        if not isinstance(value, Mapping) or set(value) != {
            "agent",
            "user",
            "max_input_tokens",
            "assistant_completion_budget",
        }:
            raise ValueError("runtime control fields do not match the locked schema")
        return cls(
            agent=RuntimeGenerationSettings.from_dict(value["agent"]),
            user=RuntimeGenerationSettings.from_dict(value["user"]),
            max_input_tokens=value["max_input_tokens"],
            assistant_completion_budget=value["assistant_completion_budget"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent.to_dict(),
            "user": self.user.to_dict(),
            "max_input_tokens": self.max_input_tokens,
            "assistant_completion_budget": self.assistant_completion_budget,
        }
