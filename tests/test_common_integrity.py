from __future__ import annotations

import json
from pathlib import Path

import pytest

from r2sp_common import (
    CodeFingerprint,
    ResetAttestationError,
    ResetEvidence,
    RunStatus,
    RuntimeIdentity,
    attest_reset,
    fingerprint_code_roots,
    fingerprint_code_tree,
)


def test_run_status_has_fixed_denominator_semantics() -> None:
    assert RunStatus.SUCCESS.attempted
    assert RunStatus.BEHAVIORAL_FAIL.attempted
    assert not RunStatus.INVALID.attempted
    assert not RunStatus.DEFERRED.attempted
    assert not RunStatus.NOT_RUN_UPSTREAM.attempted
    assert RunStatus("BEHAVIORAL_FAIL") is RunStatus.BEHAVIORAL_FAIL
    assert RunStatus.SUCCESS.value == "SUCCESS"


def test_code_fingerprint_is_content_and_logical_path_stable(tmp_path: Path) -> None:
    first = tmp_path / "checkout-a"
    second = tmp_path / "checkout-b"
    for root in (first, second):
        (root / "nested").mkdir(parents=True)
        (root / "a.py").write_text("VALUE = 1\n", encoding="utf-8")
        (root / "nested" / "b.py").write_text("VALUE = 2\n", encoding="utf-8")
        (root / "ignored.txt").write_text("not code", encoding="utf-8")

    one = fingerprint_code_tree(first, label="common")
    two = fingerprint_code_tree(second, label="common")

    assert one == two
    assert one.digest == two.digest
    assert [item.logical_path for item in one.files] == ["common/a.py", "common/nested/b.py"]
    assert CodeFingerprint.from_dict(one.to_dict()) == one
    json.dumps(one.to_dict(), allow_nan=False)

    (second / "nested" / "b.py").write_text("VALUE = 3\n", encoding="utf-8")
    assert fingerprint_code_tree(second, label="common").digest != one.digest


def test_combined_code_fingerprint_namespaces_dataset_and_shared_code(tmp_path: Path) -> None:
    common = tmp_path / "common"
    adapter = tmp_path / "adapter"
    common.mkdir()
    adapter.mkdir()
    (common / "core.py").write_text("CORE = True\n", encoding="utf-8")
    (adapter / "runtime.py").write_text("DATASET = 'tau'\n", encoding="utf-8")

    fingerprint = fingerprint_code_roots({"common": common, "tau": adapter})

    assert [entry.logical_path for entry in fingerprint.files] == [
        "common/core.py",
        "tau/runtime.py",
    ]


def _valid_reset_evidence() -> ResetEvidence:
    return ResetEvidence(
        acquisition_runtime=RuntimeIdentity(
            process_id=100,
            instances={
                "runtime": "runtime-acq",
                "conversation": "conversation-acq",
                "database": "database-acq",
            },
        ),
        deployment_runtime=RuntimeIdentity(
            process_id=200,
            instances={
                "runtime": "runtime-deploy",
                "conversation": "conversation-deploy",
                "database": "database-deploy",
            },
        ),
        generated_skill_hash="a" * 64,
        loaded_skill_hash="a" * 64,
        temporary_pool_destroyed=True,
        search_index_destroyed=True,
        acquisition_conversation_destroyed=True,
        acquisition_memory_destroyed=True,
        deployment_resource_pool_attached=False,
        deployment_memory_enabled=False,
        deployment_memory_empty=True,
        exposed_tool_names=("transfer_money", "mock_api_record"),
        forbidden_tool_names=("search_web", "open_page", "KB_search"),
        acquisition_material_present=False,
    )


def test_reset_attestation_checks_process_ids_runtime_ids_memory_tools_and_skill() -> None:
    attestation = attest_reset(_valid_reset_evidence())

    assert attestation.passed
    assert attestation.failed_checks == ()
    attestation.require_passed()
    payload = attestation.to_dict()
    assert payload["schema_version"] == "r2sp.reset-attestation.v1"
    assert json.loads(attestation.to_json())["passed"] is True


def test_reset_attestation_reports_every_failure_without_short_circuiting() -> None:
    evidence = _valid_reset_evidence()
    failed = ResetEvidence(
        acquisition_runtime=evidence.acquisition_runtime,
        deployment_runtime=RuntimeIdentity(
            process_id=100,
            instances={
                "runtime": "runtime-acq",
                "conversation": "conversation-acq",
            },
        ),
        generated_skill_hash="a" * 64,
        loaded_skill_hash="b" * 64,
        temporary_pool_destroyed=False,
        search_index_destroyed=False,
        acquisition_conversation_destroyed=False,
        acquisition_memory_destroyed=False,
        deployment_resource_pool_attached=True,
        deployment_memory_enabled=True,
        deployment_memory_empty=False,
        exposed_tool_names=("search_web", "transfer_money"),
        forbidden_tool_names=("search_web", "open_page"),
        acquisition_material_present=True,
    )

    attestation = attest_reset(failed)

    assert not attestation.passed
    assert {
        "process_id_fresh",
        "runtime_identity_keys_match",
        "runtime_id_fresh",
        "conversation_id_fresh",
        "skill_hash_matches",
        "temporary_pool_destroyed",
        "search_index_destroyed",
        "acquisition_conversation_destroyed",
        "acquisition_memory_destroyed",
        "deployment_resource_pool_absent",
        "deployment_memory_disabled",
        "deployment_memory_empty",
        "forbidden_tools_absent",
        "acquisition_material_absent",
    }.issubset({check.name for check in attestation.failed_checks})
    with pytest.raises(ResetAttestationError):
        attestation.require_passed()


def test_reset_contract_rejects_non_sha_hash_and_duplicate_tool_names() -> None:
    evidence = _valid_reset_evidence()
    with pytest.raises(ValueError, match="generated_skill_hash"):
        ResetEvidence(
            **{
                **evidence.to_init_dict(),
                "generated_skill_hash": "not-a-hash",
            }
        )
    with pytest.raises(ValueError, match="exposed_tool_names"):
        ResetEvidence(
            **{
                **evidence.to_init_dict(),
                "exposed_tool_names": ("same", "same"),
            }
        )
