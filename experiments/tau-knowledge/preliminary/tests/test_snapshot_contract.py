from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from r2sp_tau_knowledge.constants import (
    BANKING_ROOT,
    BANKING_TREE,
    EXPECTED_DOCUMENT_COUNT,
    EXPECTED_TASK_COUNT,
    EXPERIMENT_ROOT,
    FIXED_FILE_SHA256,
    MATERIALIZED_ROOT,
    PRELIMINARY_TASKS,
    TARGET_DOCUMENT_ID,
    UPSTREAM_COMMIT,
    UPSTREAM_ROOT,
    UPSTREAM_ROOT_TREE,
)
from r2sp_tau_knowledge.data import (
    TauKnowledgeSnapshot,
    build_file_manifest,
    canonical_manifest_sha256,
    sha256_file,
    sparse_checkout_manifest_document,
    verify_tracked_snapshot,
)

EXPECTED_TASK_KEYS = {
    "id",
    "description",
    "user_scenario",
    "initial_state",
    "evaluation_criteria",
    "annotations",
    "user_tools",
    "required_documents",
}

requires_local_snapshot = pytest.mark.skipif(
    not (UPSTREAM_ROOT / ".git").exists() or not BANKING_ROOT.is_dir(),
    reason="requires the ignored pinned tau2-bench checkout; run tau bootstrap first",
)


@requires_local_snapshot
def test_real_pinned_snapshot_has_all_documents_tasks_and_fixed_hashes() -> None:
    snapshot = TauKnowledgeSnapshot()
    report = snapshot.verify(verify_git=True)

    assert report.commit == UPSTREAM_COMMIT
    assert report.root_tree == UPSTREAM_ROOT_TREE
    assert report.banking_tree == BANKING_TREE
    assert report.document_count == EXPECTED_DOCUMENT_COUNT == 698
    assert report.task_count == EXPECTED_TASK_COUNT == 97

    documents = snapshot.documents()
    assert len(documents) == 698
    assert len({document.page_id for document in documents}) == 698
    assert any(document.page_id == TARGET_DOCUMENT_ID for document in documents)
    for document in documents:
        raw = json.loads(document.source_path.read_bytes())
        assert set(raw) == {"id", "title", "content"}
        assert document.source_path.stem == raw["id"] == document.page_id
        assert isinstance(raw["title"], str)
        assert isinstance(raw["content"], str)

    tasks = snapshot.tasks()
    assert len(tasks) == 97
    assert set(PRELIMINARY_TASKS) <= set(tasks)
    for task_id in PRELIMINARY_TASKS:
        task = tasks[task_id]
        assert set(task) == EXPECTED_TASK_KEYS
        assert task["id"] == task_id
        assert isinstance(task["description"], dict)
        assert isinstance(task["user_scenario"], dict)
        assert isinstance(task["evaluation_criteria"], dict)
        assert isinstance(task["user_tools"], list)
        assert isinstance(task["required_documents"], list)

    for relative_path, expected_hash in FIXED_FILE_SHA256.items():
        assert sha256_file(BANKING_ROOT / relative_path) == expected_hash


@requires_local_snapshot
def test_tracked_full_file_manifest_matches_snapshot() -> None:
    manifest_path = EXPERIMENT_ROOT / "configs" / "upstream-manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    actual_files = build_file_manifest(BANKING_ROOT)

    assert manifest["schema_version"] == 1
    assert manifest["commit"] == UPSTREAM_COMMIT
    assert manifest["root_tree"] == UPSTREAM_ROOT_TREE
    assert manifest["banking_tree"] == BANKING_TREE
    assert manifest["document_count"] == 698
    assert manifest["task_count"] == 97
    assert manifest["file_count"] == len(actual_files)
    assert manifest["files"] == actual_files
    assert manifest["manifest_sha256"] == canonical_manifest_sha256(actual_files)
    assert len({entry["path"] for entry in manifest["files"]}) == len(actual_files)


@requires_local_snapshot
def test_tracked_sparse_checkout_manifest_covers_source_data_and_prompts() -> None:
    manifest_path = EXPERIMENT_ROOT / "configs" / "upstream-checkout-manifest.json"
    tracked = json.loads(manifest_path.read_bytes())
    actual = sparse_checkout_manifest_document()

    assert tracked == actual
    assert tracked["file_count"] == 1127
    paths = {entry["path"] for entry in tracked["files"]}
    assert "src/tau2/orchestrator/orchestrator.py" in paths
    assert "data/tau2/domains/banking_knowledge/db.json" in paths
    assert "data/tau2/user_simulator/simulation_guidelines_tools.md" in paths


def test_manifest_path_is_inside_tracked_configuration_tree() -> None:
    expected = Path("experiments/tau-knowledge/preliminary/configs/upstream-manifest.json")
    assert (EXPERIMENT_ROOT / "configs" / "upstream-manifest.json").relative_to(
        EXPERIMENT_ROOT.parents[2]
    ) == expected


@requires_local_snapshot
def test_dataset_local_snapshot_verifier_checks_both_full_manifests() -> None:
    report = verify_tracked_snapshot()
    assert report["documents"] == 698
    assert report["tasks"] == 97
    assert report["banking_files"] == 815
    assert report["checkout_files"] == 1127


@requires_local_snapshot
def test_real_materialization_manifests_match_tracked_schema() -> None:
    manifests = sorted(MATERIALIZED_ROOT.glob("*/*/*/manifest.json"))
    if len(manifests) != 4:
        pytest.skip("requires all four ignored materializations")
    schema = json.loads((EXPERIMENT_ROOT / "schemas" / "materialization.schema.json").read_bytes())
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    for path in manifests:
        validator.validate(json.loads(path.read_bytes()))
