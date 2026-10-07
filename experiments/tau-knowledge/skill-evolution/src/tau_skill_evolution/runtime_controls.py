"""Bedrock Responses generation controls for one fresh episode."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


def _positive_int(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def public_tool_result(
    result: Mapping[str, Any], *, raw_path: str, raw_hash: str, preview_bytes: int = 8192
) -> dict[str, Any]:
    """Project a sealed tool result into bounded previews and its readable raw reference."""
    remaining = _positive_int("preview_bytes", preview_bytes)
    if not isinstance(result, Mapping):
        raise TypeError("tool result must be a mapping")
    if not all(isinstance(value, str) and value for value in (raw_path, raw_hash)):
        raise ValueError("tool result requires a raw path and hash")
    metadata = (
        "status",
        "exit_code",
        "returncode",
        "failure",
        "elapsed_seconds",
        "duration_seconds",
        "wall_time_seconds",
        "runtime_seconds",
        "timed_out",
    )
    public = {key: result[key] for key in metadata if key in result}
    extra = {
        key: value
        for key, value in result.items()
        if key not in {*metadata, "output", "stdout", "stderr"}
    }
    output = result.get("output")
    stdout = result.get("stdout", "")
    stderr = result.get("stderr", "")
    json_output = extra or None
    if isinstance(output, Mapping):
        stdout = output.get("stdout", stdout)
        stderr = stderr or output.get("stderr", "")
        structured = {
            key: value for key, value in output.items() if key not in {"stdout", "stderr"}
        }
        if structured:
            json_output = {**extra, "output": structured} if extra else structured
    elif isinstance(output, str):
        stdout = output
    elif output is not None:
        json_output = {**extra, "output": output} if extra else output
    previews = {}
    truncated = False
    # Keep errors visible before verbose normal output consumes the shared budget.
    for key, value in (
        ("stderr", stderr),
        ("stdout", stdout),
        (
            "json_output",
            json.dumps(json_output, ensure_ascii=False, separators=(",", ":"))
            if json_output is not None
            else "",
        ),
    ):
        encoded = str(value or "").encode("utf-8", "replace")
        preview = encoded[:remaining].decode("utf-8", "ignore")
        remaining -= len(preview.encode("utf-8"))
        truncated = truncated or len(encoded) > len(preview.encode("utf-8"))
        previews[key] = preview
    return {
        **public,
        "output": {key: value for key, value in previews.items() if key != "stderr" and value},
        "stderr": previews["stderr"],
        "raw_path": raw_path,
        "raw_hash": raw_hash,
        "truncated": truncated,
    }


@dataclass(frozen=True, slots=True)
class RuntimeGenerationSettings:
    reasoning_effort: str
    max_output_tokens: int | None

    def __post_init__(self) -> None:
        if self.max_output_tokens is not None:
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
    assistant_completion_budget: int | None

    def __post_init__(self) -> None:
        _positive_int("max_input_tokens", self.max_input_tokens)
        if self.assistant_completion_budget is not None:
            _positive_int("assistant_completion_budget", self.assistant_completion_budget)
        if (
            self.agent.max_output_tokens is not None
            and self.assistant_completion_budget is not None
            and self.agent.max_output_tokens > self.assistant_completion_budget
        ):
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
