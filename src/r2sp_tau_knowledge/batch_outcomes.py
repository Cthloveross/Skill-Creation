"""Stage outcomes shared by the independent v2 batch backends."""

from dataclasses import dataclass, field
from typing import Any

from r2sp_common import RunStatus, RuntimeIdentity


@dataclass(frozen=True)
class AcquisitionOutcome:
    status: RunStatus
    task_success: bool
    first_user_utterance: str | None
    opened_pages: tuple[dict[str, str], ...] = ()
    selection_complete: bool = False
    public_trace: dict[str, Any] = field(default_factory=dict)
    search_evidence: tuple[dict[str, Any], ...] = ()
    runtime_identity: RuntimeIdentity | None = None
    official_reward: float | None = None
    error: str | None = None


@dataclass(frozen=True)
class CompilationOutcome:
    status: RunStatus
    skill_text: str
    skill_sha256: str
    valid: bool
    compiler_input: dict[str, Any]
    error: str | None = None


@dataclass(frozen=True)
class DeploymentOutcome:
    status: RunStatus
    task_id: str
    task_success: bool
    canary_hit: bool
    canary_events: tuple[dict[str, Any], ...]
    official_reward: float | None
    runtime_identity: RuntimeIdentity
    exposed_tool_names: tuple[str, ...]
    official_trajectory: dict[str, Any] = field(default_factory=dict)
    sidecar_trajectory: tuple[dict[str, Any], ...] = ()
    error: str | None = None
