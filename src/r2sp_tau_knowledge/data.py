"""Strict loader and verifier for the pinned banking_knowledge snapshot."""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .constants import (
    BANKING_ROOT,
    BANKING_TREE,
    DOCUMENTS_ROOT,
    EXPECTED_DOCUMENT_COUNT,
    EXPECTED_TASK_COUNT,
    EXPERIMENT_ROOT,
    FIXED_FILE_SHA256,
    TASKS_ROOT,
    UPSTREAM_COMMIT,
    UPSTREAM_ROOT,
    UPSTREAM_ROOT_TREE,
)


class SnapshotError(RuntimeError):
    """The local upstream snapshot violates a pinned experiment invariant."""


@dataclass(frozen=True)
class KnowledgeDocument:
    page_id: str
    title: str
    body: str
    content_sha256: str
    source_path: Path

    def to_page_mapping(self) -> dict[str, str]:
        return {
            "page_id": self.page_id,
            "title": self.title,
            "body": self.body,
            "content_sha256": self.content_sha256,
        }


@dataclass(frozen=True)
class SnapshotReport:
    commit: str
    root_tree: str
    banking_tree: str
    document_count: int
    task_count: int
    file_count: int
    manifest_sha256: str


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        decoded = json.loads(path.read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SnapshotError(f"invalid JSON file: {path}") from exc
    if not isinstance(decoded, dict):
        raise SnapshotError(f"expected JSON object: {path}")
    return decoded


def load_documents(documents_root: Path = DOCUMENTS_ROOT) -> tuple[KnowledgeDocument, ...]:
    documents: list[KnowledgeDocument] = []
    seen: set[str] = set()
    for path in sorted(documents_root.glob("*.json"), key=lambda item: item.name):
        value = _load_json_object(path)
        if set(value) != {"id", "title", "content"}:
            raise SnapshotError(f"document schema mismatch: {path.name}")
        if not all(isinstance(value[key], str) for key in ("id", "title", "content")):
            raise SnapshotError(f"document fields must be strings: {path.name}")
        if value["id"] != path.stem:
            raise SnapshotError(f"document id/filename mismatch: {path.name}")
        if value["id"] in seen:
            raise SnapshotError(f"duplicate document id: {value['id']}")
        seen.add(value["id"])
        documents.append(
            KnowledgeDocument(
                page_id=value["id"],
                title=value["title"],
                body=value["content"],
                content_sha256=sha256_bytes(value["content"].encode("utf-8")),
                source_path=path,
            )
        )
    return tuple(documents)


def load_tasks(tasks_root: Path = TASKS_ROOT) -> dict[str, dict[str, Any]]:
    tasks: dict[str, dict[str, Any]] = {}
    for path in sorted(tasks_root.glob("task_*.json"), key=lambda item: item.name):
        value = _load_json_object(path)
        task_id = value.get("id")
        if not isinstance(task_id, str) or task_id != path.stem:
            raise SnapshotError(f"task id/filename mismatch: {path.name}")
        if task_id in tasks:
            raise SnapshotError(f"duplicate task id: {task_id}")
        tasks[task_id] = value
    return tasks


def build_file_manifest(root: Path = BANKING_ROOT) -> list[dict[str, Any]]:
    result = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        result.append(
            {
                "path": path.relative_to(root).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return result


def canonical_manifest_sha256(files: Iterable[dict[str, Any]]) -> str:
    encoded = json.dumps(list(files), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256_bytes(encoded.encode("utf-8"))


def upstream_manifest_document(root: Path = BANKING_ROOT) -> dict[str, Any]:
    """Return the tracked complete banking snapshot manifest."""

    files = build_file_manifest(root)
    return {
        "schema_version": 1,
        "upstream_release": "v1.0.1",
        "commit": UPSTREAM_COMMIT,
        "root_tree": UPSTREAM_ROOT_TREE,
        "banking_tree": BANKING_TREE,
        "document_count": EXPECTED_DOCUMENT_COUNT,
        "task_count": EXPECTED_TASK_COUNT,
        "file_count": len(files),
        "manifest_sha256": canonical_manifest_sha256(files),
        "files": files,
    }


def write_upstream_manifest(path: Path, root: Path = BANKING_ROOT) -> None:
    """Mechanically regenerate the tracked manifest from the pinned snapshot."""

    value = upstream_manifest_document(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def sparse_checkout_manifest_document(
    upstream_root: Path = UPSTREAM_ROOT,
) -> dict[str, Any]:
    """Manifest every tracked file materialized by the pinned sparse checkout."""

    try:
        result = subprocess.run(
            ["git", "-C", str(upstream_root), "ls-files", "-t", "-z"],
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SnapshotError("unable to enumerate sparse checkout") from exc
    files: list[dict[str, Any]] = []
    for entry in result.stdout.split(b"\0"):
        if not entry:
            continue
        marker, separator, raw_path = entry.partition(b" ")
        if separator != b" " or marker != b"H":
            continue
        relative = raw_path.decode("utf-8")
        path = upstream_root / relative
        if not path.is_file():
            raise SnapshotError(f"materialized tracked file missing: {relative}")
        files.append(
            {
                "path": relative,
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    files.sort(key=lambda item: item["path"])
    return {
        "schema_version": 1,
        "scope": "materialized_tracked_sparse_checkout",
        "commit": UPSTREAM_COMMIT,
        "root_tree": UPSTREAM_ROOT_TREE,
        "banking_tree": BANKING_TREE,
        "sparse_paths": [
            "src",
            "data/tau2/domains/banking_knowledge",
            "data/tau2/user_simulator",
        ],
        "file_count": len(files),
        "manifest_sha256": canonical_manifest_sha256(files),
        "files": files,
    }


def write_sparse_checkout_manifest(path: Path, upstream_root: Path = UPSTREAM_ROOT) -> None:
    value = sparse_checkout_manifest_document(upstream_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _git_output(root: Path, *arguments: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *arguments],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SnapshotError(f"unable to verify git snapshot: {' '.join(arguments)}") from exc
    return result.stdout.strip()


class TauKnowledgeSnapshot:
    """Read and verify all 97 tasks and all 698 documents."""

    def __init__(self, upstream_root: Path = UPSTREAM_ROOT) -> None:
        self.upstream_root = Path(upstream_root).resolve()
        self.banking_root = self.upstream_root / "data" / "tau2" / "domains" / "banking_knowledge"
        self.documents_root = self.banking_root / "documents"
        self.tasks_root = self.banking_root / "tasks"

    def documents(self) -> tuple[KnowledgeDocument, ...]:
        return load_documents(self.documents_root)

    def tasks(self) -> dict[str, dict[str, Any]]:
        return load_tasks(self.tasks_root)

    def task(self, task_id: str) -> dict[str, Any]:
        try:
            return self.tasks()[task_id]
        except KeyError as exc:
            raise SnapshotError(f"unknown task id: {task_id}") from exc

    def verify(self, *, verify_git: bool = True) -> SnapshotReport:
        if verify_git:
            commit = _git_output(self.upstream_root, "rev-parse", "HEAD")
            root_tree = _git_output(self.upstream_root, "rev-parse", "HEAD^{tree}")
            banking_tree = _git_output(
                self.upstream_root,
                "rev-parse",
                "HEAD:data/tau2/domains/banking_knowledge",
            )
            expected = (UPSTREAM_COMMIT, UPSTREAM_ROOT_TREE, BANKING_TREE)
            if (commit, root_tree, banking_tree) != expected:
                raise SnapshotError("upstream commit/tree commitment mismatch")
        else:
            commit, root_tree, banking_tree = UPSTREAM_COMMIT, UPSTREAM_ROOT_TREE, BANKING_TREE

        documents = self.documents()
        tasks = self.tasks()
        if len(documents) != EXPECTED_DOCUMENT_COUNT:
            raise SnapshotError(
                f"expected {EXPECTED_DOCUMENT_COUNT} documents, got {len(documents)}"
            )
        if len(tasks) != EXPECTED_TASK_COUNT:
            raise SnapshotError(f"expected {EXPECTED_TASK_COUNT} tasks, got {len(tasks)}")
        for relative, expected_hash in FIXED_FILE_SHA256.items():
            actual_hash = sha256_file(self.banking_root / relative)
            if actual_hash != expected_hash:
                raise SnapshotError(f"fixed file hash mismatch: {relative}")
        files = build_file_manifest(self.banking_root)
        return SnapshotReport(
            commit=commit,
            root_tree=root_tree,
            banking_tree=banking_tree,
            document_count=len(documents),
            task_count=len(tasks),
            file_count=len(files),
            manifest_sha256=canonical_manifest_sha256(files),
        )


def verify_tracked_snapshot(config_root: Path = EXPERIMENT_ROOT / "configs") -> dict[str, Any]:
    """Verify the complete pinned checkout against both tracked full-file manifests."""

    root = Path(config_root)
    report = TauKnowledgeSnapshot().verify(verify_git=True)
    banking = upstream_manifest_document()
    checkout = sparse_checkout_manifest_document()
    try:
        tracked_banking = json.loads((root / "upstream-manifest.json").read_bytes())
        tracked_checkout = json.loads((root / "upstream-checkout-manifest.json").read_bytes())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SnapshotError("unable to read tracked snapshot manifests") from exc
    if banking != tracked_banking:
        raise SnapshotError("banking snapshot differs from tracked full-file manifest")
    if checkout != tracked_checkout:
        raise SnapshotError("sparse checkout differs from tracked full-file manifest")
    return {
        "banking_files": report.file_count,
        "banking_manifest_sha256": report.manifest_sha256,
        "checkout_files": checkout["file_count"],
        "checkout_manifest_sha256": checkout["manifest_sha256"],
        "commit": report.commit,
        "documents": report.document_count,
        "tasks": report.task_count,
    }
