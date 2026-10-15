"""Sealed, model-independent SkillsBench whole-document acquisition datasets."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .artifacts import FrozenBase, atomic_json, load_base, seal_base
from .core._canonical import canonical_json_sha256, thaw_json

SCHEMA = "skillsbench.retrieval-dataset.v1"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _inside(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or Path(relative).is_absolute():
        raise ValueError("retrieval_dataset_path_invalid")
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("retrieval_dataset_path_invalid")
    return path


def _source_binding(spec: Any) -> dict[str, Any]:
    paths = {
        "source_tree": "data/skillsbench/source-tree.json",
        "source_manifest": "data/skillsbench/source-manifest.json",
        "public_manifest": spec.values["source"]["corpus_manifest"],
        "condition_manifest": spec.values["source"]["condition_manifest"],
    }
    return {name: {"path": path, "sha256": _sha(spec.root / path)} for name, path in paths.items()}


def _task_binding(source: Any, task: str, *, verify: bool = False) -> dict[str, Any]:
    task_inputs = source.task(task)
    if verify:
        for entry in source.manifest["files"]:
            if entry["task_id"] == task:
                path = _inside(source.checkout, entry["path"])
                if (source.checkout / entry["path"]).is_symlink() or _sha(path) != entry["sha256"]:
                    raise ValueError("retrieval_dataset_task_source_changed")
    return {
        "task_id": task,
        "instruction_sha256": hashlib.sha256(task_inputs["opening"].encode()).hexdigest(),
        "public_inputs_hash": canonical_json_sha256(source.public_inputs(task)),
        "public_input_manifest_hash": canonical_json_sha256(task_inputs["public_input_manifest"]),
        "environment_hash": canonical_json_sha256(task_inputs["environment"]),
    }


def _opening(base: FrozenBase) -> dict[str, Any]:
    public = thaw_json(base.public_inputs)
    public.pop("read_only_observations", None)
    if public.pop("clarifications", []):
        raise ValueError("retrieval_dataset_skillsbench_clarifications_invalid")
    return public


def _recipe(base: FrozenBase) -> dict[str, Any]:
    reads = []
    for observation in thaw_json(base.public_inputs).get("read_only_observations", []):
        result = {
            key: value for key, value in observation.items() if key not in {"tool", "arguments"}
        }
        item = {
            "tool": observation["tool"],
            "arguments": observation["arguments"],
            "response_hash": canonical_json_sha256(result),
        }
        if result.get("status") == "error":
            item["error"] = result["error"]
        reads.append(item)
    return {
        "documents": [
            {key: document[key] for key in ("document_id", "title", "content_hash")}
            for document in base.documents
        ],
        "read_only_observations": reads,
        "evidence": thaw_json(base.evidence),
        "stop_reason": base.stop_reason,
        "token_count": base.token_count,
        "base_hash": base.base_hash,
    }


def _producer(workflow: Any, journal: Any) -> dict[str, Any]:
    if journal.completed("acquisition-seed"):
        seed = journal.response("acquisition-seed")
        return {
            "identity": seed["producer_identity"],
            "acquisition": seed["producer_acquisition"],
            "source_run": seed["source_run"],
        }
    return {
        "identity": _read(journal.root / "identity.json")["identity"],
        "acquisition": {
            "provider": workflow.experiment_identity["provider"],
            "analyzer": workflow.spec.values["roles"]["analyzer"],
            "prompt_sha256": hashlib.sha256(workflow._prompt("analyzer").encode()).hexdigest(),
            "budgets": workflow.spec.values["acquisition"],
            "retrieval": workflow.spec.values["retrieval"],
        },
    }


def _seal_catalog(value: dict[str, Any]) -> dict[str, Any]:
    return {**value, "catalog_hash": canonical_json_sha256(value)}


def write_catalog(workflow: Any, tasks: Sequence[str], arms: Sequence[str]) -> dict[str, Any]:
    """Checkpoint completed acquisitions; a partial catalog permits explicit cell reuse.

    ``catalog.json`` carries recipes that reconstruct exactly the same bases from
    pinned public data when private local bases are absent. It contains no document
    bodies, successful input observations, or raw model requests.
    """
    from .journal import Journal
    from .skillsbench import SkillsBenchSource
    from .skillsbench_attack import load_acquisition_pages, validate_imported_acquisition

    spec, root = workflow.spec, workflow.root
    if spec.experiment != "skillsbench":
        raise ValueError("retrieval_dataset_requires_skillsbench")
    expected = [(task, arm) for task in tasks for arm in arms]
    if len(set(expected)) != len(expected) or set(expected) - set(spec.cells):
        raise ValueError("retrieval_dataset_matrix_invalid")
    source = SkillsBenchSource(spec.root)
    entries = []
    task_bindings = {}
    pools = {}
    for task, arm in expected:
        directory = root / "cells" / task / arm
        base_path = directory / "base"
        if (
            not (base_path.exists() or base_path.is_symlink())
            or not (directory / "probe-result.json").is_file()
        ):
            continue
        cell_identity = _read(directory / "journal/identity.json")["identity"]
        journal = Journal(directory / "journal", identity=cell_identity)
        base, metrics = load_base(directory / "base"), _read(directory / "probe-result.json")
        if metrics.get("status") != "MEASURED":
            continue
        contract = journal.response("retrieval-corpus-contract")
        if (
            metrics.get("base_hash") != base.base_hash
            or metrics.get("task_id") != task
            or metrics.get("condition_id") != arm
            or metrics.get("retrieval_unit") != "source_document"
            or metrics.get("retrieval_contract") != contract
            or contract.get("task_id") != task
            or contract.get("condition_id") != arm
            or contract["retrieval"].get("document_unit") != "source_document"
            or contract["retrieval"].get("condition") != spec.condition(arm)
            or _opening(base) != source.public_inputs(task)
        ):
            raise ValueError("retrieval_dataset_acquisition_mismatch")
        task_bindings.setdefault(task, _task_binding(source, task))
        entry = {
            "task_id": task,
            "condition_id": arm,
            "base_hash": base.base_hash,
            "base_path": str((directory / "base").relative_to(root)),
            "probe_result_path": str((directory / "probe-result.json").relative_to(root)),
            "probe_result_sha256": _sha(directory / "probe-result.json"),
            "task_binding": task_bindings[task],
            "condition": spec.condition(arm),
            "retrieval_contract": contract,
            "producer": _producer(workflow, journal),
            "recipe": _recipe(base),
            "source_metrics": metrics,
        }
        entry["entry_hash"] = canonical_json_sha256(entry)
        retrieval = contract["retrieval"]
        pool_key = canonical_json_sha256(retrieval)
        if pool_key not in pools:
            pool = _inside(spec.root, retrieval["pool_path"])
            if _sha(pool / "manifest.json") != retrieval["pool_manifest_sha256"]:
                raise ValueError("retrieval_dataset_pool_changed")
            pools[pool_key] = load_acquisition_pages(
                _read(pool / "manifest.json"), pool, verify=True
            )
        validate_imported_acquisition(
            base,
            {
                **{
                    name: entry[name]
                    for name in (
                        "task_id",
                        "condition_id",
                        "base_hash",
                        "entry_hash",
                        "producer",
                        "source_metrics",
                    )
                },
                "document_unit": "source_document",
                "source_catalog": "catalog.json",
                "catalog_hash": "0" * 64,
                "calls_performed_here": {"analyzer": 0, "search": 0, "read_only": 0, "clarify": 0},
            },
            pools[pool_key],
            contract,
        )
        entries.append(entry)
    present = {(entry["task_id"], entry["condition_id"]) for entry in entries}
    common = {
        "schema": SCHEMA,
        "namespace": spec.namespace,
        "document_unit": "source_document",
        "status": "COMPLETE" if len(present) == len(expected) else "PARTIAL",
        "expected_cell_count": len(expected),
        "sealed_cell_count": len(entries),
        "acquisition_origin_counts": {
            "reused": sum("source_run" in entry["producer"] for entry in entries),
            "new": sum("source_run" not in entry["producer"] for entry in entries),
        },
        "tasks": list(tasks),
        "arms": list(arms),
        "missing_cells": [list(cell) for cell in expected if cell not in present],
        "source_binding": _source_binding(spec),
    }
    catalog = _seal_catalog({**common, "entries": entries})
    atomic_json(root / "catalog.json", catalog)
    return catalog


class RetrievalDataset:
    def __init__(self, path: Path, value: dict[str, Any]):
        self.path, self.value = path.resolve(), value
        self.entries = {
            (entry["task_id"], entry["condition_id"]): entry for entry in value["entries"]
        }
        if len(self.entries) != len(value["entries"]):
            raise ValueError("retrieval_dataset_duplicate_cell")

    @property
    def identity(self) -> dict[str, Any]:
        return {
            "source_catalog": str(self.path),
            "catalog_hash": self.value["catalog_hash"],
            "base_hashes": {
                f"{task}/{arm}": entry["base_hash"] for (task, arm), entry in self.entries.items()
            },
        }

    def _unchanged(self) -> None:
        if _read(self.path) != self.value:
            raise ValueError("retrieval_dataset_catalog_changed")

    def validate(self, spec: Any, cells: Sequence[tuple[str, str]]) -> None:
        """Validate every requested cell before any consumer model is dispatched."""
        from .skillsbench import SkillsBenchSource
        from .skillsbench_attack import validate_imported_acquisition

        self._unchanged()
        if spec.experiment != "skillsbench" or self.value["namespace"] != spec.namespace:
            raise ValueError("retrieval_dataset_namespace_mismatch")
        if self.value["source_binding"] != _source_binding(spec):
            raise ValueError("retrieval_dataset_source_mismatch")
        source = SkillsBenchSource(spec.root)
        checked_tasks, checked_contracts = {}, {}
        for task, arm in cells:
            if (task, arm) not in self.entries or (task, arm) not in spec.cells:
                raise ValueError(f"retrieval_dataset_cell_missing:{task}/{arm}")
            entry = self.entries[task, arm]
            if entry["condition"] != spec.condition(arm):
                raise ValueError("retrieval_dataset_condition_mismatch")
            if task not in checked_tasks:
                checked_tasks[task] = _task_binding(source, task, verify=True)
            if checked_tasks[task] != entry["task_binding"]:
                raise ValueError("retrieval_dataset_task_mismatch")
            contract = entry["retrieval_contract"]
            if contract.get("task_id") != task or contract.get("condition_id") != arm:
                raise ValueError("retrieval_dataset_contract_mismatch")
            retrieval_hash = canonical_json_sha256(contract["retrieval"])
            if retrieval_hash not in checked_contracts:
                checked_contracts[retrieval_hash] = self._validate_retrieval(
                    spec, arm, contract["retrieval"]
                )
            base = self.materialize(spec, task, arm, source=source)
            pages = checked_contracts[retrieval_hash]
            if any(
                document["document_id"] not in pages
                or document["content_hash"] != pages[document["document_id"]]["content_sha256"]
                for document in base.documents
            ):
                raise ValueError("retrieval_dataset_base_outside_pool")
            validate_imported_acquisition(base, self._import_record(entry), pages, contract)

    @staticmethod
    def _validate_retrieval(
        spec: Any, arm: str, retrieval: Mapping[str, Any]
    ) -> dict[str, dict[str, Any]]:
        from .core import Page
        from .dense import DenseIndex, OpenAICompatibleEmbeddingClient
        from .skillsbench_attack import load_acquisition_pages

        if (
            retrieval.get("document_unit") != "source_document"
            or retrieval.get("chunking") is not False
            or retrieval.get("condition") != spec.condition(arm)
        ):
            raise ValueError("retrieval_dataset_condition_mismatch")
        directory = _inside(spec.root, retrieval["pool_path"])
        if not directory.exists():
            from .skillsbench import SkillsBenchSource
            from .skillsbench_whole_documents import prepare_pool

            try:
                rebuilt, _ = prepare_pool(spec, SkillsBenchSource(spec.root), arm)
            except (OSError, ModuleNotFoundError) as exc:
                raise ValueError("retrieval_dataset_prepared_source_data_required") from exc
            if rebuilt.resolve() != directory:
                raise ValueError("retrieval_dataset_pool_changed")
        manifest = _read(directory / "manifest.json")
        if (
            _sha(directory / "manifest.json") != retrieval["pool_manifest_sha256"]
            or manifest["corpus_hash"] != retrieval["corpus_hash"]
            or manifest["corpus_hash"]
            != canonical_json_sha256({k: v for k, v in manifest.items() if k != "corpus_hash"})
            or manifest.get("condition_id") != arm
        ):
            raise ValueError("retrieval_dataset_pool_changed")
        pages = load_acquisition_pages(manifest, directory, verify=True)
        descriptors = [
            {key: page[key] for key in ("page_id", "title", "content_sha256")}
            for page in pages.values()
        ]
        if (
            len(pages) != retrieval["page_count"]
            or len(pages) != retrieval["source_documents"]
            or len(pages) != manifest["source_documents"]
            or canonical_json_sha256(descriptors) != retrieval["page_set_hash"]
            or retrieval["source_manifest_hash"] != manifest["source_manifest_hash"]
            or retrieval["original_corpus_hash"] != manifest["original_corpus_hash"]
            or retrieval["original_pool_manifest_sha256"]
            != manifest["original_pool_manifest_sha256"]
        ):
            raise ValueError("retrieval_dataset_pool_changed")
        cache = spec.root / "data/skillsbench/whole-documents-dense" / manifest["corpus_hash"]
        # The producer's exact index hashes stay bound even on a clean checkout
        # where no index is needed to replay an already selected base.
        if not cache.exists():
            return pages
        dense = _read(cache / "manifest.json")
        embedding = retrieval["embedding"]
        index = DenseIndex.load_cache(
            cache,
            (
                Page(page["page_id"], page["title"], page["body"], page["content_sha256"])
                for page in pages.values()
            ),
            client=OpenAICompatibleEmbeddingClient(
                embedding["endpoint"],
                model_id=embedding["model"],
                revision=embedding["revision"],
                dimensions=embedding["dimensions"],
            ),
            expected_manifest_sha256=retrieval["dense_manifest_sha256"],
            max_input_tokens=embedding["max_input_tokens"],
        )
        if (
            index.manifest != retrieval["dense_contract"]
            or dense["vectors"] != retrieval["dense_vectors"]
            or dense["manifest_payload_sha256"] != retrieval["dense_manifest_payload_sha256"]
        ):
            raise ValueError("retrieval_dataset_index_changed")
        return pages

    def materialize(self, spec: Any, task: str, arm: str, *, source: Any = None) -> FrozenBase:
        """Load a private base or replay its public recipe without model/retrieval calls."""
        from .skillsbench import SkillsBenchInputView, SkillsBenchSource
        from .skillsbench_attack import load_acquisition_pages

        entry = self.entries[task, arm]
        local_base = None
        if "base_path" in entry:
            _inside(self.path.parent, entry["base_path"])
            local_base = self.path.parent / entry["base_path"]
        if local_base is not None and (local_base.exists() or local_base.is_symlink()):
            base = load_base(local_base)
        else:
            source = source or SkillsBenchSource(spec.root)
            recipe = entry["recipe"]
            directory = _inside(spec.root, entry["retrieval_contract"]["retrieval"]["pool_path"])
            pages = load_acquisition_pages(
                _read(directory / "manifest.json"), directory, verify=True
            )
            public = source.public_inputs(task)
            public.update(clarifications=[], read_only_observations=[])
            view = SkillsBenchInputView(source, task)
            try:
                for read in recipe["read_only_observations"]:
                    try:
                        response = {
                            "status": "ok",
                            "result": view.read(read["tool"], read["arguments"]),
                        }
                    except (OSError, ValueError, PermissionError) as exc:
                        response = {"status": "error", "error": str(exc)}
                    if canonical_json_sha256(response) != read["response_hash"]:
                        raise ValueError("retrieval_dataset_observation_changed")
                    public["read_only_observations"].append(
                        {"tool": read["tool"], "arguments": read["arguments"], **response}
                    )
            finally:
                view.close()
            documents = []
            for document in recipe["documents"]:
                page = pages[document["document_id"]]
                documents.append({**document, "content": page["body"]})
            base = FrozenBase(
                tuple(documents),
                public,
                tuple(recipe["evidence"]),
                recipe["stop_reason"],
                recipe["token_count"],
                recipe["base_hash"],
            )
        if base.base_hash != entry["base_hash"] or _recipe(base) != entry["recipe"]:
            raise ValueError("retrieval_dataset_base_changed")
        source = source or SkillsBenchSource(spec.root)
        if _opening(base) != source.public_inputs(task):
            raise ValueError("retrieval_dataset_public_inputs_changed")
        metrics = entry["source_metrics"]
        if (
            metrics.get("base_hash") != base.base_hash
            or metrics.get("task_id") != task
            or metrics.get("condition_id") != arm
            or metrics.get("status") != "MEASURED"
            or metrics.get("retrieval_contract") != entry["retrieval_contract"]
        ):
            raise ValueError("retrieval_dataset_metrics_changed")
        if "probe_result_path" in entry:
            path = _inside(self.path.parent, entry["probe_result_path"])
            if path.exists() and (
                _sha(path) != entry["probe_result_sha256"] or _read(path) != metrics
            ):
                raise ValueError("retrieval_dataset_metrics_changed")
        return base

    def _import_record(self, entry: dict[str, Any]) -> dict[str, Any]:
        return {
            "catalog_hash": self.value["catalog_hash"],
            "entry_hash": entry["entry_hash"],
            "source_catalog": str(self.path),
            "task_id": entry["task_id"],
            "condition_id": entry["condition_id"],
            "base_hash": entry["base_hash"],
            "document_unit": "source_document",
            "producer": entry["producer"],
            "source_metrics": entry["source_metrics"],
            "calls_performed_here": {"analyzer": 0, "search": 0, "read_only": 0, "clarify": 0},
        }

    def import_base(
        self, spec: Any, task: str, arm: str, destination: Path, journal: Any
    ) -> FrozenBase:
        self._unchanged()
        entry = self.entries[task, arm]
        base = self.materialize(spec, task, arm)
        provenance = self._import_record(entry)
        journal.dispatch("import-acquisition", provenance, lambda: provenance, external=False)
        contract = entry["retrieval_contract"]
        journal.dispatch("retrieval-corpus-contract", contract, lambda: contract, external=False)
        journal.dispatch("collect-base", {}, base.to_dict, external=False)
        seal_base(destination, base)
        return base


def load_catalog(path: Path) -> RetrievalDataset:
    path = Path(path)
    if path.is_dir():
        path = path / "catalog.json"
    value = _read(path)
    if (
        value.get("schema") != SCHEMA
        or value.get("document_unit") != "source_document"
        or value.get("catalog_hash")
        != canonical_json_sha256({k: v for k, v in value.items() if k != "catalog_hash"})
    ):
        raise ValueError("retrieval_dataset_catalog_invalid")
    for entry in value["entries"]:
        if entry.get("entry_hash") != canonical_json_sha256(
            {k: v for k, v in entry.items() if k != "entry_hash"}
        ):
            raise ValueError("retrieval_dataset_entry_invalid")
    return RetrievalDataset(path, value)


def resolve_catalog(
    path: Path | RetrievalDataset | None = None, *, run_dir: Path | None = None
) -> RetrievalDataset | None:
    """Resolve an explicit catalog or the immutable binding of an existing consumer."""
    binding = None
    if run_dir is not None:
        identity_path = Path(run_dir) / "journal/identity.json"
        if identity_path.is_file():
            binding = _read(identity_path)["identity"].get("frozen_bases")
    if path is None and binding is not None:
        path = binding["source_catalog"]
    if path is None:
        return None
    catalog = path if isinstance(path, RetrievalDataset) else load_catalog(path)
    if binding is not None and catalog.identity != binding:
        raise ValueError("retrieval_dataset_catalog_changed")
    return catalog
