from __future__ import annotations

import json

import pytest
from tau_skill_evolution.artifacts import (
    EvolutionSubmission,
    FrozenBase,
    SkillBundle,
    load_base,
    load_bundle,
    normalize_document,
    seal_base,
    seal_bundle,
    validate_relative_path,
    verify_base,
    verify_bundle,
)


def test_frozen_base_binds_exact_public_inputs_documents_and_evidence(tmp_path):
    document = {"page_id": "a", "title": "Policy", "body": "café\n"}
    public = {"opening_message": "Please help", "observations": [{"ok": True}]}
    base = FrozenBase((document,), public, ({"document_id": "a", "requirement": "policy"},))
    document["body"] = "changed"
    public["observations"][0]["ok"] = False
    assert base.documents[0]["content"] == "café\n"
    assert base.public_inputs["observations"][0]["ok"] is True
    seal_base(tmp_path / "base.json", base)
    assert load_base(tmp_path / "base.json") == base
    assert verify_base(base) == base
    for field in ("content", "title"):
        damaged = base.to_dict()
        damaged["documents"][0][field] += "tamper"
        with pytest.raises(ValueError, match="hash"):
            FrozenBase.from_dict(damaged)
    damaged = base.to_dict()
    damaged["public_inputs"]["opening_message"] = "new"
    with pytest.raises(ValueError, match="hash"):
        FrozenBase.from_dict(damaged)
    damaged = base.to_dict()
    damaged["evidence"][0]["requirement"] = "new"
    with pytest.raises(ValueError, match="hash"):
        FrozenBase.from_dict(damaged)


def test_document_admission_requires_full_text_and_valid_exact_hash():
    with pytest.raises(ValueError, match="full"):
        normalize_document({"page_id": "a", "title": "Policy"})
    with pytest.raises(ValueError, match="hash"):
        normalize_document(
            {"page_id": "a", "title": "Policy", "content": "ok", "content_hash": "0" * 64}
        )


@pytest.mark.parametrize(
    "path",
    [
        "../SKILL.md",
        "/SKILL.md",
        "scripts/../bad.py",
        "scripts//bad.py",
        "scripts/./bad.py",
        "scripts/bad.sh",
        "manifest.json",
        "scripts",
        "scripts\\bad.py",
        "references/bad\x00",
        "C:/bad",
        "references/a/",
    ],
)
def test_unsafe_package_paths_rejected(path):
    with pytest.raises(ValueError):
        validate_relative_path(path)


def test_package_hash_covers_helpers_and_references_and_restores_exact_bytes(tmp_path):
    files = {
        "SKILL.md": "instructions\n",
        "scripts/main.py": "this can have syntax errors!",
        "scripts/helpers/__init__.py": "",
        "references/policy.txt": "café\n",
    }
    bundle = SkillBundle(files)
    files["references/policy.txt"] = "changed"
    path = seal_bundle(tmp_path / "s0", bundle)
    assert load_bundle(path) == bundle
    assert verify_bundle(bundle) == bundle
    for name in ("SKILL.md", "scripts/main.py", "references/policy.txt"):
        original = (path / name).read_bytes()
        (path / name).write_bytes(original + b"tamper")
        with pytest.raises(ValueError, match="hash"):
            load_bundle(path)
        (path / name).write_bytes(original)
    child = SkillBundle(dict(bundle.files), parent_hash=bundle.bundle_hash)
    assert child.bundle_hash == bundle.bundle_hash
    assert child.parent_hash == bundle.bundle_hash
    with pytest.raises(TypeError):
        bundle.files["SKILL.md"] = "changed"


def test_sealed_package_rejects_extra_files_symlinks_and_special_files(tmp_path):
    bundle = SkillBundle({"SKILL.md": "ok", "references/a.txt": "ok"})
    path = seal_bundle(tmp_path / "s0", bundle)
    (path / "references/extra.txt").write_text("extra")
    with pytest.raises(ValueError, match="hash"):
        load_bundle(path)
    (path / "references/extra.txt").unlink()
    (path / "references/a.txt").unlink()
    (path / "references/a.txt").symlink_to(tmp_path / "external")
    with pytest.raises(ValueError, match="special|symlink"):
        load_bundle(path)


def test_seals_never_replace_different_artifacts_and_reject_old_protocol(tmp_path):
    base = FrozenBase((), {"opening_message": "a"})
    seal_base(tmp_path / "base.json", base)
    with pytest.raises(ValueError, match="replace"):
        seal_base(tmp_path / "base.json", FrozenBase((), {"opening_message": "b"}))
    path = seal_bundle(tmp_path / "s0", SkillBundle({"SKILL.md": "a"}))
    with pytest.raises(ValueError, match="replace"):
        seal_bundle(path, SkillBundle({"SKILL.md": "b"}))
    damaged = json.loads((tmp_path / "base.json").read_text())
    damaged["protocol"] = "old"
    (tmp_path / "base.json").write_text(json.dumps(damaged))
    with pytest.raises(ValueError, match="protocol"):
        load_base(tmp_path / "base.json")


def test_file_directory_path_collision_rejected():
    with pytest.raises(ValueError, match="both"):
        SkillBundle({"SKILL.md": "ok", "references/a": "file", "references/a/b": "nested"})


def test_submission_binds_package_execution_and_public_snapshot():
    bundle = SkillBundle({"SKILL.md": "instructions"})
    trace = {"events": [{"status": "completed"}]}
    submission = EvolutionSubmission(bundle, trace, "learning-episode", 3, initial=True)
    trace["events"][0]["status"] = "tampered"
    assert submission.public_trace["events"][0]["status"] == "completed"
    assert EvolutionSubmission.from_dict(submission.to_dict()) == submission
    for key, value in (
        ("execution_id", "other"),
        ("operation_cursor", 4),
        ("bundle_hash", "0" * 64),
    ):
        altered = submission.to_dict()
        altered["public_trace"][key] = value
        with pytest.raises(ValueError, match="binding"):
            EvolutionSubmission.from_dict(altered)
    altered = submission.to_dict()
    altered["public_trace"]["events"][0]["status"] = "other"
    with pytest.raises(ValueError, match="hash"):
        EvolutionSubmission.from_dict(altered)
