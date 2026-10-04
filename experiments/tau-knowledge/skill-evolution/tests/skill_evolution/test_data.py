from __future__ import annotations

import hashlib
import json
import random

import pytest
from tau_skill_evolution.constants import EXPERIMENT_ROOT
from tau_skill_evolution.core.attack_payload import ATTACK_BODY_SHA256
from tau_skill_evolution.data import (
    TauKnowledgeSnapshot,
    build_file_manifest,
    canonical_manifest_sha256,
    load_documents,
    verify_tracked_snapshot,
)
from tau_skill_evolution.materialize import CorpusMaterializer, MaterializationError
from tau_skill_evolution.spec import load_spec


def test_pinned_source_manifest_and_complete_task_population_if_checkout_available():
    spec = load_spec()
    if not (spec.upstream / ".git").exists():
        pytest.skip("pinned ignored upstream checkout is not installed")
    snapshot = TauKnowledgeSnapshot(spec.upstream)
    report = snapshot.verify(verify_git=True)
    assert (report.document_count, report.task_count) == (698, 97)
    task_ids = sorted(snapshot.tasks())
    assert (
        hashlib.sha256(("\n".join(task_ids) + "\n").encode()).hexdigest()
        == spec.values["source"]["task_population_sha256"]
    )
    assert tuple(task_ids) == spec.tasks
    document_ids = sorted(document.page_id for document in snapshot.documents())
    assert tuple(random.Random(spec.values["seed"]).sample(document_ids, 70)) == spec.targets(
        "poison-10"
    )
    banking = json.loads((EXPERIMENT_ROOT / "configs" / "upstream-manifest.json").read_text())
    assert banking["files"] == build_file_manifest(snapshot.banking_root)
    assert verify_tracked_snapshot()["checkout_files"] == 1127


@pytest.mark.parametrize("profile", ["mock-api-call", "delete-sentinel"])
def test_fixed_payload_materialization_only_changes_nested_five_ten_content_sets(tmp_path, profile):
    spec = load_spec()
    source = tmp_path / "source"
    source.mkdir()
    ids = [*spec.targets("poison-10"), *(f"other-{index:03d}" for index in range(628))]
    originals = {}
    for identifier in ids:
        raw = json.dumps(
            {"id": identifier, "title": "Public policy", "content": f"café {identifier}\n"},
            ensure_ascii=False,
            indent=2,
        ).encode()
        (source / f"{identifier}.json").write_bytes(raw)
        originals[identifier] = raw
    materializer = CorpusMaterializer(
        source_documents=source,
        output_root=tmp_path / "out",
        injections_root=spec.root / "injections",
    )
    payload = materializer.snapshot_payloads()
    assert payload.profiles[profile].attack_body_sha256 == ATTACK_BODY_SHA256[profile]
    for arm, targets in (
        ("benign", spec.targets("poison-5")),
        ("poison", spec.targets("poison-5")),
        ("poison", spec.targets("poison-10")),
    ):
        result = materializer.materialize(
            profile, arm, payload_snapshot=payload, target_document_ids=targets
        )
        directory = result.output_root / "documents"
        assert len(load_documents(directory)) == 698
        assert result.corpus_sha256 == canonical_manifest_sha256(build_file_manifest(directory))
        for identifier in ids:
            raw = (directory / f"{identifier}.json").read_bytes()
            if arm == "benign" or identifier not in targets:
                assert raw == originals[identifier]
            else:
                previous, modified = json.loads(originals[identifier]), json.loads(raw)
                assert modified == {
                    **previous,
                    "content": payload.profiles[profile].composed_payload.decode()
                    + "\n\n"
                    + previous["content"],
                }
        assert (
            materializer.materialize(
                profile, arm, payload_snapshot=payload, target_document_ids=targets
            )
            == result
        )
    assert all(
        (source / f"{identifier}.json").read_bytes() == originals[identifier] for identifier in ids
    )
    target = directory / f"{targets[0]}.json"
    target.write_text("tampered")
    with pytest.raises(MaterializationError):
        materializer.materialize(
            profile, "poison", payload_snapshot=payload, target_document_ids=targets
        )
