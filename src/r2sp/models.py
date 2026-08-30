"""Stable, serializable data contracts for the R2SP v0.3 pilot."""

from __future__ import annotations

import copy
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, ClassVar

from .hashing import canonical_json_sha256, is_sha256, sha256_text


def _required_text(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _copy_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError("metadata must be a mapping")
    return copy.deepcopy(dict(value))


@dataclass(frozen=True, slots=True)
class ResourceHeader:
    """Public searchable metadata. It deliberately has no body/snippet field."""

    resource_id: str
    app_name: str
    api_name: str
    title: str
    content_hash: str

    def __post_init__(self) -> None:
        for name in ("resource_id", "app_name", "api_name", "title"):
            _required_text(name, getattr(self, name))
        if not is_sha256(self.content_hash):
            raise ValueError("content_hash must be a lowercase SHA-256 digest")

    def to_dict(self) -> dict[str, str]:
        return {
            "resource_id": self.resource_id,
            "app_name": self.app_name,
            "api_name": self.api_name,
            "title": self.title,
            "content_hash": self.content_hash,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> ResourceHeader:
        return cls(
            resource_id=value["resource_id"],
            app_name=value["app_name"],
            api_name=value["api_name"],
            title=value["title"],
            content_hash=value["content_hash"],
        )


@dataclass(frozen=True, slots=True)
class Resource:
    """An internal resource containing the full indexed document body."""

    resource_id: str
    app_name: str
    api_name: str
    title: str
    body: str
    content_hash: str | None = None

    def __post_init__(self) -> None:
        for name in ("resource_id", "app_name", "api_name", "title"):
            _required_text(name, getattr(self, name))
        if not isinstance(self.body, str) or not self.body.strip():
            raise ValueError("body must be a non-empty string")
        computed = sha256_text(self.body)
        if self.content_hash is None:
            object.__setattr__(self, "content_hash", computed)
        elif self.content_hash != computed:
            raise ValueError("content_hash does not match the UTF-8 resource body")

    @property
    def header(self) -> ResourceHeader:
        assert self.content_hash is not None
        return ResourceHeader(
            resource_id=self.resource_id,
            app_name=self.app_name,
            api_name=self.api_name,
            title=self.title,
            content_hash=self.content_hash,
        )

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = self.header.to_dict()
        value["body"] = self.body
        return value

    def to_public_dict(self) -> dict[str, str]:
        """Return the public header; the full body is never included."""

        return self.header.to_dict()

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> Resource:
        return cls(
            resource_id=value["resource_id"],
            app_name=value["app_name"],
            api_name=value["api_name"],
            title=value["title"],
            body=value["body"],
            content_hash=value.get("content_hash"),
        )


# The analysis documents use both names; keep one implementation and stable alias.
ResourceDocument = Resource


@dataclass(frozen=True, slots=True)
class SearchHit:
    """A BM25 result safe to return from ``search_docs`` (no document body)."""

    resource_id: str
    app_name: str
    api_name: str
    title: str
    score: float

    def __post_init__(self) -> None:
        for name in ("resource_id", "app_name", "api_name", "title"):
            _required_text(name, getattr(self, name))
        if isinstance(self.score, bool) or not isinstance(self.score, (int, float)):
            raise TypeError("score must be numeric")
        score = float(self.score)
        if not math.isfinite(score):
            raise ValueError("score must be finite")
        object.__setattr__(self, "score", 0.0 if score == 0.0 else score)

    def to_dict(self) -> dict[str, Any]:
        return {
            "resource_id": self.resource_id,
            "app_name": self.app_name,
            "api_name": self.api_name,
            "title": self.title,
            "score": self.score,
        }

    def to_agent_dict(self) -> dict[str, str]:
        """Return exactly the fields exposed by ``search_docs`` in v0.3.

        BM25 scores are retained in the evaluator-side retrieval log, but the
        agent sees neither scores nor document text/snippets.
        """

        return {
            "resource_id": self.resource_id,
            "app_name": self.app_name,
            "api_name": self.api_name,
            "title": self.title,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> SearchHit:
        return cls(
            resource_id=value["resource_id"],
            app_name=value["app_name"],
            api_name=value["api_name"],
            title=value["title"],
            score=value["score"],
        )


@dataclass(frozen=True, slots=True)
class PoolManifest:
    """Content-addressed public pool manifest containing headers only."""

    SCHEMA_VERSION: ClassVar[str] = "r2sp.pool-manifest.v1"

    resources: tuple[ResourceHeader, ...]
    manifest_hash: str | None = None

    def __post_init__(self) -> None:
        ordered = tuple(sorted(self.resources, key=lambda item: item.resource_id))
        ids = [item.resource_id for item in ordered]
        if len(ids) != len(set(ids)):
            raise ValueError("pool manifest contains duplicate resource_id values")
        object.__setattr__(self, "resources", ordered)
        computed = canonical_json_sha256(self._hash_payload())
        if self.manifest_hash is None:
            object.__setattr__(self, "manifest_hash", computed)
        elif self.manifest_hash != computed:
            raise ValueError("manifest_hash does not match the public resource headers")

    @property
    def resource_count(self) -> int:
        return len(self.resources)

    def _hash_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "resources": [resource.to_dict() for resource in self.resources],
        }

    def to_dict(self) -> dict[str, Any]:
        value = self._hash_payload()
        value["resource_count"] = self.resource_count
        value["manifest_hash"] = self.manifest_hash
        return value

    @classmethod
    def from_resources(cls, resources: tuple[Resource, ...]) -> PoolManifest:
        return cls(tuple(resource.header for resource in resources))

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> PoolManifest:
        if value.get("schema_version") != cls.SCHEMA_VERSION:
            raise ValueError("unsupported pool manifest schema_version")
        resources = tuple(ResourceHeader.from_dict(item) for item in value["resources"])
        if value.get("resource_count") != len(resources):
            raise ValueError("resource_count does not match resources")
        return cls(resources=resources, manifest_hash=value.get("manifest_hash"))


@dataclass(frozen=True, slots=True)
class TaskSpec:
    task_id: str
    kind: str
    instruction: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    VALID_KINDS: ClassVar[frozenset[str]] = frozenset(
        {"authoring", "trigger_positive", "trigger_negative"}
    )

    def __post_init__(self) -> None:
        _required_text("task_id", self.task_id)
        if self.kind not in self.VALID_KINDS:
            raise ValueError(f"kind must be one of {sorted(self.VALID_KINDS)}")
        if self.instruction is not None and not isinstance(self.instruction, str):
            raise TypeError("instruction must be str or None")
        object.__setattr__(self, "metadata", _copy_mapping(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {"task_id": self.task_id, "kind": self.kind}
        if self.instruction is not None:
            value["instruction"] = self.instruction
        if self.metadata:
            value["metadata"] = _copy_mapping(self.metadata)
        return value

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> TaskSpec:
        return cls(
            task_id=value["task_id"],
            kind=value["kind"],
            instruction=value.get("instruction"),
            metadata=value.get("metadata", {}),
        )


@dataclass(frozen=True, slots=True)
class OverlaySpec:
    arm: str
    resource: Resource
    trigger: str
    nonce: str
    template_version: str = "v0.3"

    VALID_ARMS: ClassVar[frozenset[str]] = frozenset({"A_sham", "B_poison"})

    def __post_init__(self) -> None:
        if self.arm not in self.VALID_ARMS:
            raise ValueError(f"arm must be one of {sorted(self.VALID_ARMS)}")
        if not isinstance(self.resource, Resource):
            raise TypeError("resource must be a Resource")
        _required_text("trigger", self.trigger)
        _required_text("nonce", self.nonce)
        _required_text("template_version", self.template_version)

    def to_dict(self) -> dict[str, Any]:
        return {
            "arm": self.arm,
            "resource": self.resource.to_dict(),
            "trigger": self.trigger,
            "nonce": self.nonce,
            "template_version": self.template_version,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> OverlaySpec:
        return cls(
            arm=value["arm"],
            resource=Resource.from_dict(value["resource"]),
            trigger=value["trigger"],
            nonce=value["nonce"],
            template_version=value.get("template_version", "v0.3"),
        )


@dataclass(frozen=True, slots=True)
class OverlayPair:
    case_id: str
    sham: OverlaySpec
    poison: OverlaySpec

    def __post_init__(self) -> None:
        _required_text("case_id", self.case_id)
        if self.sham.arm != "A_sham" or self.poison.arm != "B_poison":
            raise ValueError("overlay pair must contain A_sham and B_poison arms")
        sham_key = (
            self.sham.resource.resource_id,
            self.sham.resource.app_name,
            self.sham.resource.api_name,
            self.sham.resource.title,
        )
        poison_key = (
            self.poison.resource.resource_id,
            self.poison.resource.app_name,
            self.poison.resource.api_name,
            self.poison.resource.title,
        )
        if sham_key != poison_key:
            raise ValueError("Sham and Poison public resource identity must match")
        if self.sham.trigger != self.poison.trigger or self.sham.nonce != self.poison.nonce:
            raise ValueError("Sham and Poison trigger/nonce must match within a case")

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "sham": self.sham.to_dict(),
            "poison": self.poison.to_dict(),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> OverlayPair:
        return cls(
            case_id=value["case_id"],
            sham=OverlaySpec.from_dict(value["sham"]),
            poison=OverlaySpec.from_dict(value["poison"]),
        )


@dataclass(frozen=True, slots=True)
class CaseSpec:
    case_id: str
    authoring_task: TaskSpec
    positive_task: TaskSpec
    negative_task: TaskSpec
    overlays: OverlayPair

    def __post_init__(self) -> None:
        _required_text("case_id", self.case_id)
        expected = (
            (self.authoring_task, "authoring"),
            (self.positive_task, "trigger_positive"),
            (self.negative_task, "trigger_negative"),
        )
        for task, kind in expected:
            if task.kind != kind:
                raise ValueError(f"{kind} task has kind {task.kind!r}")
        if self.overlays.case_id != self.case_id:
            raise ValueError("overlay pair case_id must match CaseSpec case_id")
        task_ids = {task.task_id for task, _ in expected}
        if len(task_ids) != 3:
            raise ValueError("the three pilot tasks must have distinct task_id values")

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "authoring_task": self.authoring_task.to_dict(),
            "positive_task": self.positive_task.to_dict(),
            "negative_task": self.negative_task.to_dict(),
            "overlays": self.overlays.to_dict(),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> CaseSpec:
        return cls(
            case_id=value["case_id"],
            authoring_task=TaskSpec.from_dict(value["authoring_task"]),
            positive_task=TaskSpec.from_dict(value["positive_task"]),
            negative_task=TaskSpec.from_dict(value["negative_task"]),
            overlays=OverlayPair.from_dict(value["overlays"]),
        )


@dataclass(frozen=True, slots=True)
class SkillArtifact:
    run_id: str
    content: str
    valid: bool
    content_hash: str | None = None
    neutral_placeholder: bool = False

    def __post_init__(self) -> None:
        _required_text("run_id", self.run_id)
        if not isinstance(self.content, str) or not self.content:
            raise ValueError("content must be a non-empty string")
        if not isinstance(self.valid, bool) or not isinstance(self.neutral_placeholder, bool):
            raise TypeError("valid and neutral_placeholder must be bool")
        if self.neutral_placeholder and self.valid:
            raise ValueError("a neutral placeholder cannot be marked as a valid generated skill")
        computed = sha256_text(self.content)
        if self.content_hash is None:
            object.__setattr__(self, "content_hash", computed)
        elif self.content_hash != computed:
            raise ValueError("content_hash does not match skill content")

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "content": self.content,
            "content_hash": self.content_hash,
            "valid": self.valid,
            "neutral_placeholder": self.neutral_placeholder,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> SkillArtifact:
        return cls(
            run_id=value["run_id"],
            content=value["content"],
            valid=value["valid"],
            content_hash=value.get("content_hash"),
            neutral_placeholder=value.get("neutral_placeholder", False),
        )
