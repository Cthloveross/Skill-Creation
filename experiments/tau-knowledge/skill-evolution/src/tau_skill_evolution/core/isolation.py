"""Dataset-neutral, fail-closed reset attestation."""

from __future__ import annotations

import json
import re
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from secrets import compare_digest
from types import MappingProxyType
from typing import Any, ClassVar

from ._canonical import require_sha256

_IDENTITY_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class ResetAttestationError(RuntimeError):
    """Raised when any required reset invariant fails."""


def _names(name: str, values: Collection[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Collection):
        raise TypeError(f"{name} must be a collection of strings")
    result = tuple(values)
    if any(not isinstance(value, str) or not value for value in result):
        raise ValueError(f"{name} must contain non-empty strings")
    if len(result) != len(set(result)):
        raise ValueError(f"{name} must not contain duplicates")
    return result


@dataclass(frozen=True, slots=True)
class RuntimeIdentity:
    """Process and named runtime instances on one side of a reset boundary."""

    process_id: int
    instances: Mapping[str, str]

    def __post_init__(self) -> None:
        if (
            isinstance(self.process_id, bool)
            or not isinstance(self.process_id, int)
            or self.process_id <= 0
        ):
            raise ValueError("process_id must be a positive integer")
        if not isinstance(self.instances, Mapping) or not self.instances:
            raise ValueError("instances must be a non-empty mapping")
        normalized: dict[str, str] = {}
        for name, value in self.instances.items():
            if not isinstance(name, str) or _IDENTITY_NAME_RE.fullmatch(name) is None:
                raise ValueError("instance names must be lowercase identifiers")
            if not isinstance(value, str) or not value.strip():
                raise ValueError("instance IDs must be non-empty strings")
            normalized[name] = value
        object.__setattr__(self, "instances", MappingProxyType(normalized))

    def to_dict(self) -> dict[str, Any]:
        return {
            "process_id": self.process_id,
            "instances": dict(sorted(self.instances.items())),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> RuntimeIdentity:
        return cls(process_id=value["process_id"], instances=value["instances"])


@dataclass(frozen=True, slots=True)
class ResetEvidence:
    acquisition_runtime: RuntimeIdentity
    deployment_runtime: RuntimeIdentity
    generated_skill_hash: str
    loaded_skill_hash: str
    temporary_pool_destroyed: bool
    search_index_destroyed: bool
    acquisition_conversation_destroyed: bool
    acquisition_memory_destroyed: bool
    deployment_resource_pool_attached: bool
    deployment_memory_enabled: bool
    deployment_memory_empty: bool
    exposed_tool_names: Collection[str]
    forbidden_tool_names: Collection[str]
    acquisition_material_present: bool

    def __post_init__(self) -> None:
        if not isinstance(self.acquisition_runtime, RuntimeIdentity):
            raise TypeError("acquisition_runtime must be RuntimeIdentity")
        if not isinstance(self.deployment_runtime, RuntimeIdentity):
            raise TypeError("deployment_runtime must be RuntimeIdentity")
        require_sha256("generated_skill_hash", self.generated_skill_hash)
        require_sha256("loaded_skill_hash", self.loaded_skill_hash)
        for name in (
            "temporary_pool_destroyed",
            "search_index_destroyed",
            "acquisition_conversation_destroyed",
            "acquisition_memory_destroyed",
            "deployment_resource_pool_attached",
            "deployment_memory_enabled",
            "deployment_memory_empty",
            "acquisition_material_present",
        ):
            if not isinstance(getattr(self, name), bool):
                raise TypeError(f"{name} must be bool")
        object.__setattr__(
            self, "exposed_tool_names", _names("exposed_tool_names", self.exposed_tool_names)
        )
        object.__setattr__(
            self,
            "forbidden_tool_names",
            _names("forbidden_tool_names", self.forbidden_tool_names),
        )

    def to_init_dict(self) -> dict[str, Any]:
        """Return constructor-shaped data, useful for immutable test/adapter updates."""

        return {
            "acquisition_runtime": self.acquisition_runtime,
            "deployment_runtime": self.deployment_runtime,
            "generated_skill_hash": self.generated_skill_hash,
            "loaded_skill_hash": self.loaded_skill_hash,
            "temporary_pool_destroyed": self.temporary_pool_destroyed,
            "search_index_destroyed": self.search_index_destroyed,
            "acquisition_conversation_destroyed": self.acquisition_conversation_destroyed,
            "acquisition_memory_destroyed": self.acquisition_memory_destroyed,
            "deployment_resource_pool_attached": self.deployment_resource_pool_attached,
            "deployment_memory_enabled": self.deployment_memory_enabled,
            "deployment_memory_empty": self.deployment_memory_empty,
            "exposed_tool_names": self.exposed_tool_names,
            "forbidden_tool_names": self.forbidden_tool_names,
            "acquisition_material_present": self.acquisition_material_present,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.to_init_dict(),
            "acquisition_runtime": self.acquisition_runtime.to_dict(),
            "deployment_runtime": self.deployment_runtime.to_dict(),
            "exposed_tool_names": list(self.exposed_tool_names),
            "forbidden_tool_names": list(self.forbidden_tool_names),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> ResetEvidence:
        return cls(
            acquisition_runtime=RuntimeIdentity.from_dict(value["acquisition_runtime"]),
            deployment_runtime=RuntimeIdentity.from_dict(value["deployment_runtime"]),
            generated_skill_hash=value["generated_skill_hash"],
            loaded_skill_hash=value["loaded_skill_hash"],
            temporary_pool_destroyed=value["temporary_pool_destroyed"],
            search_index_destroyed=value["search_index_destroyed"],
            acquisition_conversation_destroyed=value["acquisition_conversation_destroyed"],
            acquisition_memory_destroyed=value["acquisition_memory_destroyed"],
            deployment_resource_pool_attached=value["deployment_resource_pool_attached"],
            deployment_memory_enabled=value["deployment_memory_enabled"],
            deployment_memory_empty=value["deployment_memory_empty"],
            exposed_tool_names=tuple(value["exposed_tool_names"]),
            forbidden_tool_names=tuple(value["forbidden_tool_names"]),
            acquisition_material_present=value["acquisition_material_present"],
        )


@dataclass(frozen=True, slots=True)
class ResetCheck:
    name: str
    passed: bool
    expected: Any
    observed: Any

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise ValueError("reset check name must be non-empty")
        if not isinstance(self.passed, bool):
            raise TypeError("reset check passed must be bool")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "expected": self.expected,
            "observed": self.observed,
        }


@dataclass(frozen=True, slots=True)
class ResetAttestation:
    SCHEMA_VERSION: ClassVar[str] = "r2sp.reset-attestation.v1"

    checks: tuple[ResetCheck, ...]

    def __post_init__(self) -> None:
        checks = tuple(self.checks)
        if not checks or any(not isinstance(check, ResetCheck) for check in checks):
            raise ValueError("checks must contain at least one ResetCheck")
        names = [check.name for check in checks]
        if len(names) != len(set(names)):
            raise ValueError("reset check names must be unique")
        object.__setattr__(self, "checks", checks)

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    @property
    def failed_checks(self) -> tuple[ResetCheck, ...]:
        return tuple(check for check in self.checks if not check.passed)

    def require_passed(self) -> None:
        if not self.passed:
            names = ", ".join(check.name for check in self.failed_checks)
            raise ResetAttestationError(f"reset attestation failed: {names}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "passed": self.passed,
            "checks": [check.to_dict() for check in self.checks],
        }

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )


def attest_reset(evidence: ResetEvidence) -> ResetAttestation:
    """Evaluate all reset invariants without short-circuiting."""

    if not isinstance(evidence, ResetEvidence):
        raise TypeError("evidence must be ResetEvidence")
    acquisition = evidence.acquisition_runtime
    deployment = evidence.deployment_runtime
    acquisition_keys = set(acquisition.instances)
    deployment_keys = set(deployment.instances)
    checks: list[ResetCheck] = [
        ResetCheck(
            "process_id_fresh",
            acquisition.process_id != deployment.process_id,
            "different from acquisition",
            deployment.process_id,
        ),
        ResetCheck(
            "runtime_identity_keys_match",
            acquisition_keys == deployment_keys,
            sorted(acquisition_keys),
            sorted(deployment_keys),
        ),
    ]
    for name in sorted(acquisition_keys | deployment_keys):
        acquisition_id = acquisition.instances.get(name)
        deployment_id = deployment.instances.get(name)
        checks.append(
            ResetCheck(
                f"{name}_id_fresh",
                acquisition_id is not None
                and deployment_id is not None
                and acquisition_id != deployment_id,
                "different from acquisition",
                deployment_id,
            )
        )
    checks.extend(
        (
            ResetCheck(
                "skill_hash_matches",
                compare_digest(evidence.generated_skill_hash, evidence.loaded_skill_hash),
                evidence.generated_skill_hash,
                evidence.loaded_skill_hash,
            ),
            ResetCheck(
                "temporary_pool_destroyed",
                evidence.temporary_pool_destroyed,
                True,
                evidence.temporary_pool_destroyed,
            ),
            ResetCheck(
                "search_index_destroyed",
                evidence.search_index_destroyed,
                True,
                evidence.search_index_destroyed,
            ),
            ResetCheck(
                "acquisition_conversation_destroyed",
                evidence.acquisition_conversation_destroyed,
                True,
                evidence.acquisition_conversation_destroyed,
            ),
            ResetCheck(
                "acquisition_memory_destroyed",
                evidence.acquisition_memory_destroyed,
                True,
                evidence.acquisition_memory_destroyed,
            ),
            ResetCheck(
                "deployment_resource_pool_absent",
                not evidence.deployment_resource_pool_attached,
                False,
                evidence.deployment_resource_pool_attached,
            ),
            ResetCheck(
                "deployment_memory_disabled",
                not evidence.deployment_memory_enabled,
                False,
                evidence.deployment_memory_enabled,
            ),
            ResetCheck(
                "deployment_memory_empty",
                evidence.deployment_memory_empty,
                True,
                evidence.deployment_memory_empty,
            ),
            ResetCheck(
                "forbidden_tools_absent",
                not (set(evidence.exposed_tool_names) & set(evidence.forbidden_tool_names)),
                [],
                sorted(set(evidence.exposed_tool_names) & set(evidence.forbidden_tool_names)),
            ),
            ResetCheck(
                "acquisition_material_absent",
                not evidence.acquisition_material_present,
                False,
                evidence.acquisition_material_present,
            ),
        )
    )
    return ResetAttestation(tuple(checks))
