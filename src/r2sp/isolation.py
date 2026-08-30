"""Fail-closed reset attestation for acquisition/deployment isolation."""

from __future__ import annotations

import json
from collections.abc import Collection
from dataclasses import dataclass
from secrets import compare_digest
from typing import Any


class ResetAttestationError(RuntimeError):
    """Raised when a reset does not satisfy every required invariant."""


@dataclass(frozen=True)
class RuntimeIdentity:
    """Identifiers that must be replaced across the reset boundary."""

    world_id: str
    context_id: str
    session_id: str

    def __post_init__(self) -> None:
        for name in ("world_id", "context_id", "session_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{name} must be a non-empty string")


@dataclass(frozen=True)
class ResetEvidence:
    """Complete evidence required to attest one hard reset.

    ``deployment_resource_ids`` and ``deployment_resource_hashes`` must be the
    complete inventories of the rebuilt deployment pool, not only top-k
    retrieval results.
    """

    frozen_clean_pool_hash: str
    deployment_pool_hash: str
    overlay_id: str
    overlay_content_hash: str
    deployment_resource_ids: Collection[str]
    deployment_resource_hashes: Collection[str]
    acquisition_runtime: RuntimeIdentity
    deployment_runtime: RuntimeIdentity
    generated_skill_hash: str
    loaded_skill_hash: str

    def __post_init__(self) -> None:
        text_fields = (
            "frozen_clean_pool_hash",
            "deployment_pool_hash",
            "overlay_id",
            "overlay_content_hash",
            "generated_skill_hash",
            "loaded_skill_hash",
        )
        for name in text_fields:
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{name} must be a non-empty string")

        resource_ids = frozenset(self.deployment_resource_ids)
        resource_hashes = frozenset(
            _normalize_digest(value) for value in self.deployment_resource_hashes
        )
        if any(not isinstance(value, str) or not value for value in resource_ids):
            raise ValueError("deployment_resource_ids must contain non-empty strings")
        object.__setattr__(self, "deployment_resource_ids", resource_ids)
        object.__setattr__(self, "deployment_resource_hashes", resource_hashes)


@dataclass(frozen=True)
class ResetCheck:
    name: str
    passed: bool
    expected: Any
    observed: Any

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "expected": self.expected,
            "observed": self.observed,
        }


@dataclass(frozen=True)
class ResetAttestation:
    """Auditable result containing every mandatory reset check."""

    checks: tuple[ResetCheck, ...]

    @property
    def passed(self) -> bool:
        return bool(self.checks) and all(check.passed for check in self.checks)

    @property
    def failed_checks(self) -> tuple[ResetCheck, ...]:
        return tuple(check for check in self.checks if not check.passed)

    def require_passed(self) -> None:
        if not self.passed:
            names = ", ".join(check.name for check in self.failed_checks)
            raise ResetAttestationError(f"reset attestation failed: {names}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
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


def _normalize_digest(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("hash values must be non-empty strings")
    return value.strip().lower()


def _hashes_equal(left: str, right: str) -> bool:
    return compare_digest(_normalize_digest(left), _normalize_digest(right))


def attest_reset(evidence: ResetEvidence) -> ResetAttestation:
    """Evaluate all hard-reset invariants without short-circuiting.

    All checks are returned so a failed run retains a complete audit record.
    The caller must invoke :meth:`ResetAttestation.require_passed` before a run
    can be counted as full-chain success.
    """

    clean_hash_matches = _hashes_equal(
        evidence.frozen_clean_pool_hash, evidence.deployment_pool_hash
    )
    normalized_overlay_hash = _normalize_digest(evidence.overlay_content_hash)
    normalized_generated_hash = _normalize_digest(evidence.generated_skill_hash)
    normalized_loaded_hash = _normalize_digest(evidence.loaded_skill_hash)

    checks = (
        ResetCheck(
            name="clean_pool_hash_matches",
            passed=clean_hash_matches,
            expected=_normalize_digest(evidence.frozen_clean_pool_hash),
            observed=_normalize_digest(evidence.deployment_pool_hash),
        ),
        ResetCheck(
            name="overlay_id_absent",
            passed=evidence.overlay_id not in evidence.deployment_resource_ids,
            expected="absent",
            observed=(
                "present" if evidence.overlay_id in evidence.deployment_resource_ids else "absent"
            ),
        ),
        ResetCheck(
            name="overlay_content_hash_absent",
            passed=(normalized_overlay_hash not in evidence.deployment_resource_hashes),
            expected="absent",
            observed=(
                "present"
                if normalized_overlay_hash in evidence.deployment_resource_hashes
                else "absent"
            ),
        ),
        ResetCheck(
            name="world_id_fresh",
            passed=(evidence.deployment_runtime.world_id != evidence.acquisition_runtime.world_id),
            expected="different from acquisition",
            observed=evidence.deployment_runtime.world_id,
        ),
        ResetCheck(
            name="context_id_fresh",
            passed=(
                evidence.deployment_runtime.context_id != evidence.acquisition_runtime.context_id
            ),
            expected="different from acquisition",
            observed=evidence.deployment_runtime.context_id,
        ),
        ResetCheck(
            name="session_id_fresh",
            passed=(
                evidence.deployment_runtime.session_id != evidence.acquisition_runtime.session_id
            ),
            expected="different from acquisition",
            observed=evidence.deployment_runtime.session_id,
        ),
        ResetCheck(
            name="skill_hash_matches",
            passed=compare_digest(normalized_generated_hash, normalized_loaded_hash),
            expected=normalized_generated_hash,
            observed=normalized_loaded_hash,
        ),
    )
    return ResetAttestation(checks=checks)


__all__ = [
    "ResetAttestation",
    "ResetAttestationError",
    "ResetCheck",
    "ResetEvidence",
    "RuntimeIdentity",
    "attest_reset",
]
