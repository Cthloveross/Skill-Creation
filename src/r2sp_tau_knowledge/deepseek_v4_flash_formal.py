"""Locked 60-cell DeepSeek-V4-Flash API runtime profile.

The profile is deliberately separate from the completed two-cell smoke.  It
copies the gate-tested provider parameters while binding admission to every
cell in the base full-document matrix.  Only the credential environment
variable name is configuration; credential values never enter the profile.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import yaml

from .full_doc_spec import ExperimentSpec, load_default_spec
from .runtime_controls import (
    RuntimeControls,
    RuntimeGenerationSettings,
    RuntimeUserSettings,
)

DEEPSEEK_V4_FLASH_FORMAL_PROFILE = "deepseek-v4-flash-formal-v1"
DEEPSEEK_V4_FLASH_FORMAL_SCHEMA = "tau.deepseek-v4-flash-formal.v1"
DEEPSEEK_V4_FLASH_FORMAL_LITELLM_MODEL = "deepseek/deepseek-v4-flash"
DEEPSEEK_V4_FLASH_FORMAL_API_MODEL = "deepseek-v4-flash"
DEEPSEEK_V4_FLASH_FORMAL_EXPECTED_CELLS = 60
DEEPSEEK_V4_FLASH_FORMAL_API_KEY_ENV = "DEEPSEEK_API_KEY"


class DeepSeekV4FlashFormalSpecError(ValueError):
    """The formal API profile is malformed or has drifted."""


def default_deepseek_v4_flash_formal_config_path() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "experiments"
        / "tau-knowledge"
        / "deepseek-v4-api-4b-dense"
        / "configs"
        / "deepseek-v4-flash-formal.yaml"
    )


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DeepSeekV4FlashFormalSpecError(f"{label} must be a mapping")
    return value


def _string_tuple(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise DeepSeekV4FlashFormalSpecError(f"{label} must be a string list")
    result = tuple(value)
    if not result or len(set(result)) != len(result):
        raise DeepSeekV4FlashFormalSpecError(f"{label} must be non-empty and unique")
    return result


@dataclass(frozen=True, slots=True)
class DeepSeekV4FlashFormalSpec:
    config_path: Path
    config_sha256: str
    seed: int
    tasks: tuple[str, ...]
    arms: tuple[str, ...]
    expected_cell_count: int
    transport: str
    api_base: str
    api_key_env: str
    agent_model: str
    agent_thinking: bool
    preserve_thinking: bool
    reasoning_effort: str
    agent_max_output_tokens: int
    cumulative_assistant_token_limit: int
    compiler_model: str
    compiler_thinking: bool
    compiler_reasoning_effort: str
    compiler_max_output_tokens: int
    user_model: str
    user_thinking: bool
    user_temperature: float
    user_max_output_tokens: int
    tokenizer_endpoint: str
    tokenizer_model: str
    token_counter_basis: str
    completion_authority: str
    embedding_endpoint: str

    def allows_cell(self, task_id: object, arm: object) -> bool:
        """Return whether a cell belongs to the file-bound formal matrix."""

        return task_id in self.tasks and arm in self.arms

    def runtime_spec(self, base: ExperimentSpec | None = None) -> ExperimentSpec:
        """Bind worker paths and endpoints to this formal API profile."""

        source = base or load_default_spec()
        self.runtime_controls(source)
        services = replace(source.services, embedding_endpoint=self.embedding_endpoint)
        return replace(source, services=services, config_sha256=self.config_sha256)

    def runtime_controls(self, base: ExperimentSpec | None = None) -> RuntimeControls:
        source = base or load_default_spec()
        if (
            self.seed != source.seed
            or self.tasks != source.tasks
            or self.arms != source.arms
            or self.expected_cell_count != len(source.cells)
            or any(not self.allows_cell(cell.task_id, cell.arm) for cell in source.cells)
        ):
            raise DeepSeekV4FlashFormalSpecError(
                "formal matrix/seed does not equal the sealed base experiment"
            )
        generation = source.model.generation
        return RuntimeControls(
            agent=RuntimeGenerationSettings(
                temperature=generation.temperature,
                top_p=generation.top_p,
                top_k=generation.top_k,
                min_p=generation.min_p,
                presence_penalty=generation.presence_penalty,
                repetition_penalty=generation.repetition_penalty,
                enable_thinking=self.agent_thinking,
                preserve_thinking=self.preserve_thinking,
                reasoning_effort=self.reasoning_effort,
                max_output_tokens=self.agent_max_output_tokens,
            ),
            user=RuntimeUserSettings(
                temperature=self.user_temperature,
                enable_thinking=self.user_thinking,
                max_output_tokens=self.user_max_output_tokens,
            ),
            max_input_tokens=source.context.request_input_token_limit,
            assistant_completion_budget=self.cumulative_assistant_token_limit,
        )

    def identity(self, base: ExperimentSpec) -> dict[str, Any]:
        self.runtime_controls(base)
        return {
            "schema_version": DEEPSEEK_V4_FLASH_FORMAL_SCHEMA,
            "profile": DEEPSEEK_V4_FLASH_FORMAL_PROFILE,
            "config_path": str(self.config_path),
            "config_sha256": self.config_sha256,
            "base_experiment_config_sha256": base.config_sha256,
            "seed": self.seed,
            "matrix": {
                "tasks": list(self.tasks),
                "arms": list(self.arms),
                "expected_cell_count": self.expected_cell_count,
            },
            "provider": {
                "transport": self.transport,
                "api_base": self.api_base,
                "api_key_env": self.api_key_env,
            },
            "agent": {
                "model": self.agent_model,
                "thinking": self.agent_thinking,
                "preserve_thinking": self.preserve_thinking,
                "reasoning_effort": self.reasoning_effort,
                "max_output_tokens": self.agent_max_output_tokens,
                "cumulative_assistant_token_limit": self.cumulative_assistant_token_limit,
            },
            "compiler": {
                "model": self.compiler_model,
                "thinking": self.compiler_thinking,
                "reasoning_effort": self.compiler_reasoning_effort,
                "max_output_tokens": self.compiler_max_output_tokens,
            },
            "user_simulator": {
                "model": self.user_model,
                "thinking": self.user_thinking,
                "temperature": self.user_temperature,
                "max_output_tokens": self.user_max_output_tokens,
            },
            "token_admission": {
                "tokenizer_endpoint": self.tokenizer_endpoint,
                "tokenizer_model": self.tokenizer_model,
                "basis": self.token_counter_basis,
                "completion_authority": self.completion_authority,
            },
            "services": {"embedding_endpoint": self.embedding_endpoint},
        }


def load_deepseek_v4_flash_formal_spec(
    path: Path | None = None,
    *,
    base: ExperimentSpec | None = None,
) -> DeepSeekV4FlashFormalSpec:
    config = (path or default_deepseek_v4_flash_formal_config_path()).resolve()
    raw_bytes = config.read_bytes()
    root = _mapping(yaml.safe_load(raw_bytes), "config")
    expected_root = {
        "schema_version",
        "base_experiment",
        "seed",
        "matrix",
        "provider",
        "agent",
        "compiler",
        "user_simulator",
        "token_admission",
        "services",
    }
    if set(root) != expected_root:
        raise DeepSeekV4FlashFormalSpecError("formal config top-level fields drifted")
    matrix = _mapping(root["matrix"], "matrix")
    provider = _mapping(root["provider"], "provider")
    agent = _mapping(root["agent"], "agent")
    compiler = _mapping(root["compiler"], "compiler")
    user = _mapping(root["user_simulator"], "user_simulator")
    admission = _mapping(root["token_admission"], "token_admission")
    services = _mapping(root["services"], "services")
    fields = {
        "matrix": (matrix, {"tasks", "arms", "expected_cell_count"}),
        "provider": (provider, {"transport", "api_base", "api_key_env"}),
        "agent": (
            agent,
            {
                "model",
                "thinking",
                "preserve_thinking",
                "reasoning_effort",
                "max_output_tokens",
                "cumulative_assistant_token_limit",
            },
        ),
        "compiler": (
            compiler,
            {"model", "thinking", "reasoning_effort", "max_output_tokens"},
        ),
        "user_simulator": (
            user,
            {"model", "thinking", "temperature", "max_output_tokens"},
        ),
        "token_admission": (
            admission,
            {"tokenizer_endpoint", "tokenizer_model", "basis", "completion_authority"},
        ),
        "services": (services, {"embedding_endpoint"}),
    }
    for label, (value, expected) in fields.items():
        if set(value) != expected:
            raise DeepSeekV4FlashFormalSpecError(f"{label} fields drifted")
    spec = DeepSeekV4FlashFormalSpec(
        config_path=config,
        config_sha256=hashlib.sha256(raw_bytes).hexdigest(),
        seed=root["seed"],
        tasks=_string_tuple(matrix["tasks"], "matrix.tasks"),
        arms=_string_tuple(matrix["arms"], "matrix.arms"),
        expected_cell_count=matrix["expected_cell_count"],
        transport=provider["transport"],
        api_base=provider["api_base"],
        api_key_env=provider["api_key_env"],
        agent_model=agent["model"],
        agent_thinking=agent["thinking"],
        preserve_thinking=agent["preserve_thinking"],
        reasoning_effort=agent["reasoning_effort"],
        agent_max_output_tokens=agent["max_output_tokens"],
        cumulative_assistant_token_limit=agent["cumulative_assistant_token_limit"],
        compiler_model=compiler["model"],
        compiler_thinking=compiler["thinking"],
        compiler_reasoning_effort=compiler["reasoning_effort"],
        compiler_max_output_tokens=compiler["max_output_tokens"],
        user_model=user["model"],
        user_thinking=user["thinking"],
        user_temperature=user["temperature"],
        user_max_output_tokens=user["max_output_tokens"],
        tokenizer_endpoint=admission["tokenizer_endpoint"],
        tokenizer_model=admission["tokenizer_model"],
        token_counter_basis=admission["basis"],
        completion_authority=admission["completion_authority"],
        embedding_endpoint=services["embedding_endpoint"],
    )
    registered_base = base or load_default_spec()
    if base is not None and base.paths.config_path != (config.parent / "experiment.yaml").resolve():
        raise DeepSeekV4FlashFormalSpecError(
            "formal API profile must use the experiment.yaml beside its config"
        )
    if (
        root["schema_version"] != DEEPSEEK_V4_FLASH_FORMAL_SCHEMA
        or root["base_experiment"] != "experiment.yaml"
        or spec.seed != 20260904
        or spec.tasks != registered_base.tasks
        or spec.arms != registered_base.arms
        or spec.expected_cell_count != DEEPSEEK_V4_FLASH_FORMAL_EXPECTED_CELLS
        or spec.expected_cell_count != len(registered_base.cells)
        or spec.transport != "deepseek"
        or spec.api_base != "https://api.deepseek.com"
        or spec.api_key_env != DEEPSEEK_V4_FLASH_FORMAL_API_KEY_ENV
        or spec.agent_model != DEEPSEEK_V4_FLASH_FORMAL_LITELLM_MODEL
        or spec.agent_thinking is not True
        or spec.preserve_thinking is not True
        or spec.reasoning_effort != "medium"
        or spec.agent_max_output_tokens != 16384
        or spec.cumulative_assistant_token_limit != 65536
        or spec.compiler_model != DEEPSEEK_V4_FLASH_FORMAL_API_MODEL
        or spec.compiler_thinking is not True
        or spec.compiler_reasoning_effort != "low"
        or spec.compiler_max_output_tokens != 32768
        or spec.user_model != DEEPSEEK_V4_FLASH_FORMAL_LITELLM_MODEL
        or spec.user_thinking is not False
        or spec.user_temperature != 0.0
        or spec.user_max_output_tokens != 2048
        or spec.tokenizer_endpoint != "http://127.0.0.1:18140/v1"
        or spec.tokenizer_model != registered_base.embedding.model
        or spec.token_counter_basis != "embedding_serialized_text_estimate"
        or spec.completion_authority != "provider_response_usage"
        or spec.embedding_endpoint != spec.tokenizer_endpoint
    ):
        raise DeepSeekV4FlashFormalSpecError("formal API profile values drifted")
    spec.runtime_controls(registered_base)
    return spec


__all__ = [
    "DEEPSEEK_V4_FLASH_FORMAL_API_KEY_ENV",
    "DEEPSEEK_V4_FLASH_FORMAL_API_MODEL",
    "DEEPSEEK_V4_FLASH_FORMAL_EXPECTED_CELLS",
    "DEEPSEEK_V4_FLASH_FORMAL_LITELLM_MODEL",
    "DEEPSEEK_V4_FLASH_FORMAL_PROFILE",
    "DEEPSEEK_V4_FLASH_FORMAL_SCHEMA",
    "DeepSeekV4FlashFormalSpec",
    "DeepSeekV4FlashFormalSpecError",
    "default_deepseek_v4_flash_formal_config_path",
    "load_deepseek_v4_flash_formal_spec",
]
