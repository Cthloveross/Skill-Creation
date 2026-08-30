"""Construction and content-addressing of the v0.3 AppWorld resource pool."""

from __future__ import annotations

import json
import unicodedata
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .hashing import canonical_json_sha256
from .models import PoolManifest, Resource, ResourceHeader

DEFAULT_EXCLUDED_HELPERS = frozenset({"apidocs", "supervisor"})


def _identifier_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in normalized if character.isalnum())


def make_resource_id(app_name: str, api_name: str) -> str:
    """Create a deterministic opaque ID without leaking document text."""

    digest = canonical_json_sha256({"app_name": app_name, "api_name": api_name})
    return f"res_{digest[:24]}"


@dataclass(frozen=True, slots=True)
class ResourcePool:
    """An immutable set of resources with a body-free public manifest."""

    resources: tuple[Resource, ...]

    def __post_init__(self) -> None:
        resources = tuple(sorted(self.resources, key=lambda item: item.resource_id))
        if any(not isinstance(resource, Resource) for resource in resources):
            raise TypeError("resources must contain only Resource objects")
        ids = [resource.resource_id for resource in resources]
        if len(ids) != len(set(ids)):
            raise ValueError("resource pool contains duplicate resource_id values")
        object.__setattr__(self, "resources", resources)

    def __len__(self) -> int:
        return len(self.resources)

    def __iter__(self) -> Iterator[Resource]:
        return iter(self.resources)

    def __contains__(self, resource_id: object) -> bool:
        return isinstance(resource_id, str) and any(
            resource.resource_id == resource_id for resource in self.resources
        )

    @property
    def manifest(self) -> PoolManifest:
        return PoolManifest.from_resources(self.resources)

    @property
    def public_headers(self) -> tuple[ResourceHeader, ...]:
        return self.manifest.resources

    def read_doc(self, resource_id: str) -> Resource:
        """Return the full document for an explicit ``read_doc`` call."""

        for resource in self.resources:
            if resource.resource_id == resource_id:
                return resource
        raise KeyError(f"unknown resource_id: {resource_id}")

    def with_overlay(self, overlay: Resource) -> ResourcePool:
        """Return a new acquisition pool containing one additional overlay."""

        if not isinstance(overlay, Resource):
            raise TypeError("overlay must be a Resource")
        return ResourcePool(self.resources + (overlay,))

    def without_resource(self, resource_id: str) -> ResourcePool:
        """Remove exactly one resource, failing closed if it is absent."""

        remaining = tuple(
            resource for resource in self.resources if resource.resource_id != resource_id
        )
        if len(remaining) == len(self.resources):
            raise KeyError(f"unknown resource_id: {resource_id}")
        return ResourcePool(remaining)

    def matches_manifest(self, manifest: PoolManifest) -> bool:
        return self.manifest.manifest_hash == manifest.manifest_hash


def _record_to_resource(record: Mapping[str, Any]) -> Resource:
    try:
        app_name = str(record["app_name"])
        api_name = str(record["api_name"])
    except KeyError as exc:
        raise ValueError(f"resource record is missing {exc.args[0]!r}") from exc

    title = record.get("title") or record.get("name") or api_name
    body_value = record.get("body")
    if body_value is None:
        # Preserve the full standard API representation rather than indexing only
        # its short description. Canonical JSON makes the generated body stable.
        body_value = json.dumps(
            dict(record),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    elif not isinstance(body_value, str):
        body_value = json.dumps(
            body_value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    resource_id = record.get("resource_id") or make_resource_id(app_name, api_name)
    return Resource(
        resource_id=str(resource_id),
        app_name=app_name,
        api_name=api_name,
        title=str(title),
        body=body_value,
        content_hash=record.get("content_hash"),
    )


def build_clean_pool(
    records: Iterable[Resource | Mapping[str, Any]],
    *,
    expected_count: int = 457,
    excluded_helpers: Iterable[str] = DEFAULT_EXCLUDED_HELPERS,
) -> ResourcePool:
    """Build the frozen one-resource-per-endpoint clean pool.

    Helper apps/APIs are excluded case-insensitively before the exact count is
    checked. A caller may use a smaller ``expected_count`` only for tests/smoke
    fixtures; the checked-in research design requires 457.
    """

    if isinstance(expected_count, bool) or not isinstance(expected_count, int):
        raise TypeError("expected_count must be an integer")
    if expected_count < 0:
        raise ValueError("expected_count cannot be negative")
    excluded = {_identifier_key(str(name)) for name in excluded_helpers}
    resources: list[Resource] = []
    for item in records:
        resource = item if isinstance(item, Resource) else _record_to_resource(item)
        if (
            _identifier_key(resource.app_name) in excluded
            or _identifier_key(resource.api_name) in excluded
        ):
            continue
        resources.append(resource)

    pool = ResourcePool(tuple(resources))
    endpoints = [(resource.app_name, resource.api_name) for resource in pool]
    if len(endpoints) != len(set(endpoints)):
        raise ValueError("clean pool must contain one resource per app/API endpoint")
    if len(pool) != expected_count:
        raise ValueError(f"clean resource count must be exactly {expected_count}; got {len(pool)}")
    return pool


def _records_from_json(path: Path, payload: Any) -> Iterator[dict[str, Any]]:
    app_name = path.stem
    if isinstance(payload, list):
        for index, raw in enumerate(payload):
            if not isinstance(raw, Mapping):
                raise ValueError(f"{path}: item {index} must be a mapping")
            record = dict(raw)
            record.setdefault("app_name", app_name)
            if "api_name" not in record:
                candidate = record.get("name") or record.get("api")
                if not isinstance(candidate, str) or not candidate:
                    raise ValueError(f"{path}: item {index} has no api_name")
                record["api_name"] = candidate
            yield record
        return

    if not isinstance(payload, Mapping):
        raise ValueError(f"{path}: root must be a mapping or list")

    # Accept either {api_name: spec} or {"apis": {api_name: spec}}. This keeps
    # the loader useful for synthetic fixtures without weakening the final 457
    # resource count assertion.
    api_mapping: Any = payload.get("apis", payload)
    if not isinstance(api_mapping, Mapping):
        raise ValueError(f"{path}: APIs must be represented as a mapping")
    for api_name, raw in api_mapping.items():
        if not isinstance(raw, Mapping):
            raise ValueError(f"{path}: API {api_name!r} must be a mapping")
        record = dict(raw)
        record.setdefault("app_name", app_name)
        record.setdefault("api_name", str(api_name))
        yield record


def load_standard_api_docs(
    source_directory: str | Path,
    *,
    expected_count: int = 457,
    excluded_helpers: Iterable[str] = DEFAULT_EXCLUDED_HELPERS,
) -> ResourcePool:
    """Load ``data/api_docs/standard/*.json`` into the strict clean pool."""

    directory = Path(source_directory)
    if not directory.is_dir():
        raise FileNotFoundError(f"API documentation directory does not exist: {directory}")
    paths = tuple(sorted(directory.glob("*.json"), key=lambda item: item.name))
    if not paths:
        raise ValueError(f"no JSON API documentation files found in {directory}")

    records: list[dict[str, Any]] = []
    for path in paths:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        records.extend(_records_from_json(path, payload))
    return build_clean_pool(
        records,
        expected_count=expected_count,
        excluded_helpers=excluded_helpers,
    )


def write_public_manifest(pool: ResourcePool, path: str | Path) -> None:
    """Write only public headers and hashes; resource bodies are never emitted."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(pool.manifest.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def load_public_manifest(path: str | Path) -> PoolManifest:
    with Path(path).open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, Mapping):
        raise ValueError("pool manifest root must be a mapping")
    return PoolManifest.from_dict(payload)
