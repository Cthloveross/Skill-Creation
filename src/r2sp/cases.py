"""Private frozen-case loading and deterministic public build scheduling."""

from __future__ import annotations

import json
import random
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

from .hashing import canonical_json_sha256, is_sha256, sha256_text
from .models import CaseSpec

PROTOCOL_VERSION = "0.4"
TOKENIZER_MODEL = "Qwen/Qwen3.8-27B"
TOKENIZER_REVISION = "1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0"
RESEARCH_CASE_COUNT = 16
SCHEDULE_SEED = 20260829
MAX_TOKEN_COUNT_DIFFERENCE = 0.05

_ROOT_FIELDS = frozenset({"protocol_version", "tokenizer", "cases"})
_TOKENIZER_FIELDS = frozenset({"model", "revision"})
_CASE_FIELDS = frozenset(
    {
        "case_id",
        "authoring_task",
        "positive_task",
        "negative_task",
        "overlays",
        "benign_token_count",
        "poison_token_count",
    }
)
_TASK_FIELDS = frozenset({"task_id", "kind", "instruction", "metadata"})
_OVERLAY_PAIR_FIELDS = frozenset({"case_id", "benign", "poison"})
_OVERLAY_FIELDS = frozenset({"arm", "resource", "trigger", "nonce", "template_version"})
_RESOURCE_FIELDS = frozenset(
    {"resource_id", "app_name", "api_name", "title", "content_hash", "body"}
)


class CaseBundleError(ValueError):
    """Raised when a private frozen case bundle violates protocol v0.4."""


@dataclass(frozen=True, slots=True)
class CaseTokenCounts:
    case_id: str
    benign_token_count: int | None
    poison_token_count: int | None

    @property
    def relative_difference(self) -> float | None:
        if self.benign_token_count is None or self.poison_token_count is None:
            return None
        return abs(self.benign_token_count - self.poison_token_count) / max(
            self.benign_token_count, self.poison_token_count
        )


@dataclass(frozen=True, slots=True)
class FrozenCaseBundle:
    """Validated private cases.

    This type intentionally provides no public ``to_dict`` method because its
    cases contain full overlay bodies, triggers, and nonces. Only a derived
    :class:`BuildSchedule` is safe to publish.
    """

    protocol_version: str
    tokenizer_model: str
    tokenizer_revision: str
    cases: tuple[CaseSpec, ...]
    token_counts: tuple[CaseTokenCounts, ...]
    research_mode: bool
    source_path: Path

    def counts_for(self, case_id: str) -> CaseTokenCounts:
        for counts in self.token_counts:
            if counts.case_id == case_id:
                return counts
        raise KeyError(f"unknown case_id: {case_id}")


@dataclass(frozen=True, slots=True)
class OverlayAttestationEntry:
    """Non-secret content commitments for one matched case."""

    case_id: str
    benign_content_hash: str
    poison_content_hash: str
    trigger_sha256: str
    nonce_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.case_id, str) or not self.case_id.strip():
            raise CaseBundleError("overlay attestation case_id must be non-empty")
        for field_name in (
            "benign_content_hash",
            "poison_content_hash",
            "trigger_sha256",
            "nonce_sha256",
        ):
            if not is_sha256(getattr(self, field_name)):
                raise CaseBundleError(
                    f"overlay attestation {self.case_id}.{field_name} must be a SHA-256 digest"
                )
        if self.benign_content_hash == self.poison_content_hash:
            raise CaseBundleError(
                f"overlay attestation {self.case_id} must commit to distinct bodies"
            )

    def to_dict(self) -> dict[str, str]:
        return {
            "case_id": self.case_id,
            "benign_content_hash": self.benign_content_hash,
            "poison_content_hash": self.poison_content_hash,
            "trigger_sha256": self.trigger_sha256,
            "nonce_sha256": self.nonce_sha256,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> OverlayAttestationEntry:
        expected = {
            "case_id",
            "benign_content_hash",
            "poison_content_hash",
            "trigger_sha256",
            "nonce_sha256",
        }
        if not isinstance(value, Mapping) or set(value) != expected:
            raise CaseBundleError(
                "overlay attestation case must contain exactly " + ", ".join(sorted(expected))
            )
        try:
            return cls(**{key: value[key] for key in expected})
        except TypeError as exc:
            raise CaseBundleError(f"invalid overlay attestation case: {exc}") from exc


@dataclass(frozen=True, slots=True)
class OverlayAttestation:
    """Canonical hash-only commitment to the private overlay bundle."""

    SCHEMA_VERSION: ClassVar[str] = "r2sp.overlay-attestation.v2"

    protocol_version: str
    cases: tuple[OverlayAttestationEntry, ...]
    bundle_hash: str | None = None

    def __post_init__(self) -> None:
        if self.protocol_version != PROTOCOL_VERSION:
            raise CaseBundleError(
                f"overlay attestation protocol_version must equal {PROTOCOL_VERSION!r}"
            )
        if not self.cases:
            raise CaseBundleError("overlay attestation cases cannot be empty")
        if any(not isinstance(case, OverlayAttestationEntry) for case in self.cases):
            raise CaseBundleError(
                "overlay attestation cases must contain OverlayAttestationEntry values"
            )
        ordered = tuple(sorted(self.cases, key=lambda case: case.case_id))
        case_ids = [case.case_id for case in ordered]
        if len(case_ids) != len(set(case_ids)):
            raise CaseBundleError("overlay attestation case_id values must be unique")
        object.__setattr__(self, "cases", ordered)
        computed = canonical_json_sha256(self._hash_payload())
        if self.bundle_hash is None:
            object.__setattr__(self, "bundle_hash", computed)
        elif self.bundle_hash != computed:
            raise CaseBundleError("overlay attestation bundle_hash does not match its contents")

    def _hash_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "protocol_version": self.protocol_version,
            "case_count": len(self.cases),
            "cases": [case.to_dict() for case in self.cases],
        }

    def to_dict(self) -> dict[str, Any]:
        value = self._hash_payload()
        value["bundle_hash"] = self.bundle_hash
        return value

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> OverlayAttestation:
        expected = {
            "schema_version",
            "protocol_version",
            "case_count",
            "cases",
            "bundle_hash",
        }
        if not isinstance(value, Mapping) or set(value) != expected:
            raise CaseBundleError(
                "overlay attestation must contain exactly " + ", ".join(sorted(expected))
            )
        if value.get("schema_version") != cls.SCHEMA_VERSION:
            raise CaseBundleError("unsupported overlay attestation schema_version")
        raw_cases = value.get("cases")
        if not isinstance(raw_cases, list) or not raw_cases:
            raise CaseBundleError("overlay attestation cases must be a non-empty JSON array")
        cases = tuple(OverlayAttestationEntry.from_dict(case) for case in raw_cases)
        if value.get("case_count") != len(cases):
            raise CaseBundleError("overlay attestation case_count does not match cases")
        return cls(
            protocol_version=value.get("protocol_version"),
            cases=cases,
            bundle_hash=value.get("bundle_hash"),
        )


@dataclass(frozen=True, slots=True)
class BuildScheduleEntry:
    position: int
    run_id: str
    case_id: str
    arm: str
    authoring_task_id: str
    positive_task_id: str
    negative_task_id: str
    generation_seed: int

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "position": self.position,
            "run_id": self.run_id,
            "case_id": self.case_id,
            "arm": self.arm,
            "authoring_task_id": self.authoring_task_id,
            "positive_task_id": self.positive_task_id,
            "negative_task_id": self.negative_task_id,
            "generation_seed": self.generation_seed,
        }


@dataclass(frozen=True, slots=True)
class BuildSchedule:
    protocol_version: str
    seed: int
    entries: tuple[BuildScheduleEntry, ...]

    def to_public_dict(self) -> dict[str, Any]:
        """Serialize only run coordination metadata, never private treatments."""

        return {
            "schema_version": "r2sp.public-build-schedule.v2",
            "protocol_version": self.protocol_version,
            "seed": self.seed,
            "entry_count": len(self.entries),
            "entries": [entry.to_public_dict() for entry in self.entries],
        }

    # The schedule has no private representation, so the conventional name is
    # a safe alias and convenient for artifact writers.
    def to_dict(self) -> dict[str, Any]:
        return self.to_public_dict()


def _required_mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CaseBundleError(f"{field} must be a JSON object")
    return value


def _strict_mapping(
    value: Any,
    field: str,
    allowed_fields: frozenset[str],
) -> Mapping[str, Any]:
    mapping = _required_mapping(value, field)
    unknown_fields = sorted(
        (key for key in mapping if key not in allowed_fields),
        key=lambda key: str(key),
    )
    if unknown_fields:
        rendered = ", ".join(repr(key) for key in unknown_fields)
        raise CaseBundleError(f"{field} contains unknown field(s): {rendered}")
    return mapping


def _strict_case_mapping(value: Any, index: int) -> Mapping[str, Any]:
    field = f"cases[{index}]"
    case = _strict_mapping(value, field, _CASE_FIELDS)

    for task_name in ("authoring_task", "positive_task", "negative_task"):
        _strict_mapping(case.get(task_name), f"{field}.{task_name}", _TASK_FIELDS)

    overlays = _strict_mapping(case.get("overlays"), f"{field}.overlays", _OVERLAY_PAIR_FIELDS)
    for arm_name in ("benign", "poison"):
        overlay_field = f"{field}.overlays.{arm_name}"
        overlay = _strict_mapping(overlays.get(arm_name), overlay_field, _OVERLAY_FIELDS)
        _strict_mapping(
            overlay.get("resource"),
            f"{overlay_field}.resource",
            _RESOURCE_FIELDS,
        )
    return case


def _parse_token_count(value: Any, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise CaseBundleError(f"{field} must be a positive integer")
    return value


def _validate_pair(case: CaseSpec) -> None:
    benign = case.overlays.benign
    poison = case.overlays.poison
    benign_identity = (
        benign.resource.resource_id,
        benign.resource.app_name,
        benign.resource.api_name,
        benign.resource.title,
    )
    poison_identity = (
        poison.resource.resource_id,
        poison.resource.app_name,
        poison.resource.api_name,
        poison.resource.title,
    )
    if benign_identity != poison_identity:
        raise CaseBundleError(f"{case.case_id}: overlay public identity does not match")
    if benign.trigger != poison.trigger:
        raise CaseBundleError(f"{case.case_id}: overlay triggers do not match")
    if benign.template_version != poison.template_version:
        raise CaseBundleError(f"{case.case_id}: overlay template versions do not match")
    if benign.nonce != poison.nonce:
        raise CaseBundleError(f"{case.case_id}: overlay nonces do not match")
    if benign.resource.body == poison.resource.body:
        raise CaseBundleError(f"{case.case_id}: Benign and Poison bodies must differ")


def _validate_token_counts(
    counts: CaseTokenCounts,
    *,
    research_mode: bool,
) -> None:
    missing = counts.benign_token_count is None or counts.poison_token_count is None
    if research_mode and missing:
        raise CaseBundleError(
            f"{counts.case_id}: pinned Benign/Poison token counts are required in research mode"
        )
    if missing:
        if counts.benign_token_count is not None or counts.poison_token_count is not None:
            raise CaseBundleError(
                f"{counts.case_id}: Benign and Poison token counts must be supplied together"
            )
        return
    difference = counts.relative_difference
    assert difference is not None
    if difference > MAX_TOKEN_COUNT_DIFFERENCE:
        raise CaseBundleError(
            f"{counts.case_id}: Benign/Poison token counts differ by more than 5%"
        )


def load_frozen_cases(
    path: str | Path,
    *,
    research_mode: bool = True,
) -> FrozenCaseBundle:
    """Load and fail-closed validate a private frozen cases JSON file."""

    if not isinstance(research_mode, bool):
        raise TypeError("research_mode must be bool")
    source = Path(path).resolve()
    try:
        with source.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except json.JSONDecodeError as exc:
        raise CaseBundleError(f"invalid cases JSON: {exc.msg}") from exc

    root = _strict_mapping(payload, "root", _ROOT_FIELDS)
    if root.get("protocol_version") != PROTOCOL_VERSION:
        raise CaseBundleError(f"protocol_version must equal {PROTOCOL_VERSION!r}")
    tokenizer = _strict_mapping(root.get("tokenizer"), "tokenizer", _TOKENIZER_FIELDS)
    if tokenizer.get("model") != TOKENIZER_MODEL:
        raise CaseBundleError(f"tokenizer.model must equal {TOKENIZER_MODEL!r}")
    if tokenizer.get("revision") != TOKENIZER_REVISION:
        raise CaseBundleError("tokenizer.revision does not match the pinned v0.4 revision")

    raw_cases = root.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise CaseBundleError("cases must be a non-empty JSON array")
    if research_mode and len(raw_cases) != RESEARCH_CASE_COUNT:
        raise CaseBundleError(
            f"research mode requires exactly {RESEARCH_CASE_COUNT} cases; got {len(raw_cases)}"
        )

    parsed: list[CaseSpec] = []
    counts: list[CaseTokenCounts] = []
    for index, raw_case in enumerate(raw_cases):
        case_mapping = _strict_case_mapping(raw_case, index)
        try:
            case = CaseSpec.from_dict(case_mapping)
        except (KeyError, TypeError, ValueError) as exc:
            raise CaseBundleError(f"cases[{index}] is invalid: {exc}") from exc
        _validate_pair(case)
        case_counts = CaseTokenCounts(
            case_id=case.case_id,
            benign_token_count=_parse_token_count(
                case_mapping.get("benign_token_count"),
                f"{case.case_id}.benign_token_count",
            ),
            poison_token_count=_parse_token_count(
                case_mapping.get("poison_token_count"),
                f"{case.case_id}.poison_token_count",
            ),
        )
        _validate_token_counts(case_counts, research_mode=research_mode)
        parsed.append(case)
        counts.append(case_counts)

    case_ids: set[str] = set()
    task_ids: set[str] = set()
    nonces: set[str] = set()
    for case in parsed:
        if case.case_id in case_ids:
            raise CaseBundleError(f"duplicate case_id: {case.case_id}")
        case_ids.add(case.case_id)
        for task in (case.authoring_task, case.positive_task, case.negative_task):
            if task.task_id in task_ids:
                raise CaseBundleError(f"duplicate task_id: {task.task_id}")
            task_ids.add(task.task_id)
        nonce = case.overlays.benign.nonce
        if nonce in nonces:
            raise CaseBundleError("case nonces must be globally unique")
        nonces.add(nonce)

    paired = sorted(zip(parsed, counts, strict=True), key=lambda pair: pair[0].case_id)
    return FrozenCaseBundle(
        protocol_version=PROTOCOL_VERSION,
        tokenizer_model=TOKENIZER_MODEL,
        tokenizer_revision=TOKENIZER_REVISION,
        cases=tuple(case for case, _ in paired),
        token_counts=tuple(case_counts for _, case_counts in paired),
        research_mode=research_mode,
        source_path=source,
    )


def build_overlay_attestation(bundle: FrozenCaseBundle) -> OverlayAttestation:
    """Commit to private overlays without reproducing bodies, triggers, or nonces."""

    if not isinstance(bundle, FrozenCaseBundle):
        raise TypeError("bundle must be a FrozenCaseBundle")
    entries: list[OverlayAttestationEntry] = []
    for case in bundle.cases:
        benign = case.overlays.benign
        poison = case.overlays.poison
        assert benign.resource.content_hash is not None
        assert poison.resource.content_hash is not None
        entries.append(
            OverlayAttestationEntry(
                case_id=case.case_id,
                benign_content_hash=benign.resource.content_hash,
                poison_content_hash=poison.resource.content_hash,
                trigger_sha256=sha256_text(benign.trigger),
                nonce_sha256=sha256_text(benign.nonce),
            )
        )
    return OverlayAttestation(
        protocol_version=bundle.protocol_version,
        cases=tuple(entries),
    )


def validate_overlay_attestation(
    value: Mapping[str, Any],
    *,
    expected_bundle: FrozenCaseBundle | None = None,
) -> OverlayAttestation:
    """Validate canonical integrity and, optionally, the private source bundle."""

    attestation = OverlayAttestation.from_dict(value)
    if expected_bundle is not None:
        if not isinstance(expected_bundle, FrozenCaseBundle):
            raise TypeError("expected_bundle must be a FrozenCaseBundle or None")
        expected = build_overlay_attestation(expected_bundle)
        if attestation != expected:
            raise CaseBundleError(
                "overlay attestation does not match the expected private case bundle"
            )
    return attestation


def load_overlay_attestation(
    path: str | Path,
    *,
    expected_bundle: FrozenCaseBundle | None = None,
) -> OverlayAttestation:
    """Read a JSON attestation and apply canonical and optional source validation."""

    source = Path(path).resolve()
    try:
        with source.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except json.JSONDecodeError as exc:
        raise CaseBundleError(f"invalid overlay attestation JSON: {exc.msg}") from exc
    if not isinstance(payload, Mapping):
        raise CaseBundleError("overlay attestation root must be a JSON object")
    return validate_overlay_attestation(payload, expected_bundle=expected_bundle)


def _generation_seed(case_id: str, used: set[int]) -> int:
    digest = canonical_json_sha256(
        {"schedule_seed": SCHEDULE_SEED, "case_id": case_id, "purpose": "generation"}
    )
    candidate = int(digest[:16], 16) % (2**31)
    while candidate in used:
        candidate = (candidate + 1) % (2**31)
    used.add(candidate)
    return candidate


def build_schedule(
    bundle: FrozenCaseBundle,
    *,
    seed: int = SCHEDULE_SEED,
) -> BuildSchedule:
    """Derive the reproducible paired acquisition/build order for v0.4."""

    if not isinstance(bundle, FrozenCaseBundle):
        raise TypeError("bundle must be a FrozenCaseBundle")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise TypeError("seed must be an integer")
    if seed != SCHEDULE_SEED:
        raise ValueError(f"protocol v0.4 fixes the schedule seed at {SCHEDULE_SEED}")

    rng = random.Random(seed)
    cases = list(sorted(bundle.cases, key=lambda case: case.case_id))
    rng.shuffle(cases)
    entries: list[BuildScheduleEntry] = []
    used_generation_seeds: set[int] = set()
    for case in cases:
        arms = ["A_benign", "B_poison"]
        rng.shuffle(arms)
        generation_seed = _generation_seed(case.case_id, used_generation_seeds)
        for arm in arms:
            position = len(entries)
            opaque_run_suffix = canonical_json_sha256(
                {"case_id": case.case_id, "arm": arm, "position": position}
            )[:16]
            entries.append(
                BuildScheduleEntry(
                    position=position,
                    run_id=f"build-{position:02d}-{opaque_run_suffix}",
                    case_id=case.case_id,
                    arm=arm,
                    authoring_task_id=case.authoring_task.task_id,
                    positive_task_id=case.positive_task.task_id,
                    negative_task_id=case.negative_task.task_id,
                    generation_seed=generation_seed,
                )
            )

    return BuildSchedule(
        protocol_version=bundle.protocol_version,
        seed=SCHEDULE_SEED,
        entries=tuple(entries),
    )


def write_public_schedule(schedule: BuildSchedule, path: str | Path) -> None:
    """Write the body/trigger/nonce-free schedule as canonical public JSON."""

    if not isinstance(schedule, BuildSchedule):
        raise TypeError("schedule must be a BuildSchedule")
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(
            schedule.to_public_dict(),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )


# Short alias for callers using the repository's bundle terminology.
load_case_bundle = load_frozen_cases


__all__ = [
    "BuildSchedule",
    "BuildScheduleEntry",
    "CaseBundleError",
    "CaseTokenCounts",
    "FrozenCaseBundle",
    "MAX_TOKEN_COUNT_DIFFERENCE",
    "PROTOCOL_VERSION",
    "RESEARCH_CASE_COUNT",
    "SCHEDULE_SEED",
    "TOKENIZER_MODEL",
    "TOKENIZER_REVISION",
    "build_schedule",
    "load_case_bundle",
    "load_frozen_cases",
    "write_public_schedule",
]
