"""SkillsBench v8 document conditions preserve source and chunk provenance."""

import hashlib
import json
import shutil
import struct
from types import SimpleNamespace

import pytest
from tau_skill_evolution import skillsbench, skillsbench_attack
from tau_skill_evolution.artifacts import atomic_json
from tau_skill_evolution.constants import EXPERIMENT_ROOT
from tau_skill_evolution.core._canonical import canonical_json_bytes, canonical_json_sha256
from tau_skill_evolution.dense import (
    DENSE_CACHE_SCHEMA_VERSION,
    DENSE_DOCUMENT_FORMAT,
    DENSE_MAX_INPUT_TOKENS,
    DENSE_NORMALIZATION,
    DENSE_POOLING,
    DENSE_SIMILARITY,
    DENSE_SNIPPET_TOKENS,
    QUERY_INSTRUCTION,
)
from tau_skill_evolution.spec import SKILLSBENCH_ARMS, load_spec


class CharacterTokenizer:
    def encode(self, text, **_kwargs):
        return SimpleNamespace(
            ids=[ord(character) for character in text],
            offsets=[(index, index + 1) for index in range(len(text))],
        )

    def decode(self, tokens, **_kwargs):
        return "".join(chr(token) for token in tokens)


@pytest.fixture
def pool(tmp_path, monkeypatch):
    checkout = tmp_path / "upstream"
    files, targets = [], []
    for index in range(10):
        task = f"task-{index}"
        text = f"# Reference {index}\n\n" + (
            "Public technical background.\n" * (200 if not index else 2)
        )
        relative = f"artifacts/background_docs/{task}/reference.md"
        path = checkout / relative
        path.parent.mkdir(parents=True)
        path.write_text(text)
        document_id = f"{task}::background/reference.md"
        targets.append(document_id)
        files.append(
            {
                "document_id": document_id,
                "relative_path": "background/reference.md",
                "path": relative,
                "sha256": hashlib.sha256(text.encode()).hexdigest(),
                "kind": "text",
            }
        )
    source = SimpleNamespace(
        root=tmp_path,
        checkout=checkout,
        manifest={"manifest_hash": "fixture", "files": files},
        validate=lambda: None,
    )
    monkeypatch.setattr(skillsbench, "SkillsBenchSource", lambda _root: source)
    provenance = {
        profile: {
            "archive_path": f"DyMalSkill/{profile}/fixture/_injection.json",
            "record_sha256": hashlib.sha256((profile + "-record").encode()).hexdigest(),
            "inserted_text_sha256": hashlib.sha256((profile + "-source").encode()).hexdigest(),
            "adapted_template_sha256": hashlib.sha256(
                skillsbench_attack.adapted_template(profile).encode()
            ).hexdigest(),
        }
        for profile in skillsbench_attack.PROFILES
    }
    monkeypatch.setattr(skillsbench_attack, "source_templates", lambda _root: provenance)
    tokenizer = CharacterTokenizer()
    skillsbench.prepare_pool(tmp_path, tokenizer)
    spec = SimpleNamespace(
        root=tmp_path,
        namespace="skillsbench.skill-evolution.v8",
        tasks=tuple(f"task-{index}" for index in range(85)),
        arms=SKILLSBENCH_ARMS,
        values={
            "source": {
                "condition_manifest": "configs/skillsbench-dymal4-conditions.json",
            },
            "poison_sampling": {
                "seed": 20260904,
                "target_document_ids": targets[:9],
            },
            "embedding": {
                "model": "fixture/model",
                "revision": "fixture-revision",
                "dimension": 2,
                "max_length": DENSE_MAX_INPUT_TOKENS,
                "pooling": "last-token",
                "normalization": "float32-l2",
                "similarity": "exact-cosine",
                "query_instruct": "official",
                "reranker": False,
                "faiss": False,
                "endpoint": "http://127.0.0.1:18140/v1",
            },
        },
    )
    return source, tokenizer, spec


def _snapshot(directory):
    return {
        path.relative_to(directory).as_posix(): path.read_bytes()
        for path in directory.rglob("*")
        if path.is_file()
    }


def _pages(directory, manifest):
    return [json.loads((directory / record["file"]).read_text()) for record in manifest["pages"]]


def _seal_dense(spec, directory):
    manifest = skillsbench.validate_pool(spec.root, directory=directory)
    pages = sorted(
        (json.loads((directory / record["file"]).read_text()) for record in manifest["pages"]),
        key=lambda page: page["page_id"],
    )
    embedding = spec.values["embedding"]
    descriptor = [
        {
            "page_id": page["page_id"],
            "title": page["title"],
            "content_sha256": page["content_sha256"],
        }
        for page in pages
    ]
    contract_pages = [
        {
            **record,
            "token_count": 1,
            "snippet": page["body"],
            "snippet_truncated": False,
        }
        for record, page in zip(descriptor, pages, strict=True)
    ]
    contract = {
        "model_id": embedding["model"],
        "model_revision": embedding["revision"],
        "tokenizer_id": embedding["model"],
        "tokenizer_revision": embedding["revision"],
        "pooling": DENSE_POOLING,
        "normalization": DENSE_NORMALIZATION,
        "similarity": DENSE_SIMILARITY,
        "dimensions": embedding["dimension"],
        "max_input_tokens": DENSE_MAX_INPUT_TOKENS,
        "snippet_tokens": DENSE_SNIPPET_TOKENS,
        "query_instruction": QUERY_INSTRUCTION,
        "document_format": DENSE_DOCUMENT_FORMAT,
        "whole_document": True,
        "chunking": False,
        "reranker": False,
        "approximate_index": False,
        "page_count": len(pages),
        "corpus_hash": canonical_json_sha256(descriptor),
        "pages": contract_pages,
    }
    vectors = b"".join(struct.pack("<2f", 1.0, 0.0) for _ in pages)
    vector_record = {
        "filename": "vectors.f32",
        "dtype": "float32",
        "endianness": "little",
        "shape": [len(pages), embedding["dimension"]],
        "size_bytes": len(vectors),
        "sha256": hashlib.sha256(vectors).hexdigest(),
    }
    unsigned = {
        "schema_version": DENSE_CACHE_SCHEMA_VERSION,
        "format": "r2sp_tau_dense_cache",
        "contract": contract,
        "vectors": vector_record,
    }
    sealed = {
        **unsigned,
        "manifest_payload_sha256": canonical_json_sha256(unsigned),
    }
    target = spec.root / "data/skillsbench/dense" / manifest["corpus_hash"]
    target.mkdir(parents=True)
    (target / "vectors.f32").write_bytes(vectors)
    (target / "manifest.json").write_bytes(canonical_json_bytes(sealed) + b"\n")
    return target


def test_frozen_source_records_preserve_archive_provenance():
    sources = skillsbench_attack.source_templates(EXPERIMENT_ROOT)
    assert tuple(sources) == skillsbench_attack.PROFILES
    conditions = json.loads(
        (EXPERIMENT_ROOT / "configs/skillsbench-dymal4-conditions.json").read_text()
    )
    assert sources == conditions["source_records"]
    directory = EXPERIMENT_ROOT / "injections/skillsbench/source"
    assert {path.stem for path in directory.glob("*.json")} == set(skillsbench_attack.PROFILES)
    for profile, provenance in sources.items():
        raw = (directory / f"{profile}.json").read_bytes()
        assert hashlib.sha256(raw).hexdigest() == provenance["record_sha256"]
        text = json.loads(raw)["inserted_text"]
        assert hashlib.sha256(text.encode()).hexdigest() == provenance["inserted_text_sha256"]
    rendered = "\n".join(
        skillsbench_attack.adapted_payload(profile, "A public reference")
        for profile in skillsbench_attack.PROFILES
    ).lower()
    for forbidden in skillsbench_attack._FORBIDDEN:
        assert forbidden not in rendered
    detail = skillsbench_attack.validate_condition_design(
        load_spec(EXPERIMENT_ROOT / "configs/skillsbench.yaml")
    )
    assert detail["source_archive_sha256"] == skillsbench_attack.SOURCE_ARCHIVE_SHA256
    assert detail["conditions"] == 9


def test_source_records_work_without_zip(tmp_path):
    root = tmp_path / "experiments/tau-knowledge/skill-evolution"
    shutil.copytree(EXPERIMENT_ROOT / "injections/skillsbench", root / "injections/skillsbench")
    assert not (tmp_path / skillsbench_attack.SOURCE_ARCHIVE).exists()
    assert skillsbench_attack.source_templates(root) == skillsbench_attack.source_templates(
        EXPERIMENT_ROOT
    )


@pytest.mark.parametrize("change", ["missing", "tampered"])
def test_source_records_fail_closed_without_archive_fallback(tmp_path, change):
    root = tmp_path / "experiments/tau-knowledge/skill-evolution"
    shutil.copytree(EXPERIMENT_ROOT / "injections/skillsbench", root / "injections/skillsbench")
    target = root / "injections/skillsbench/source/credential_abuse.json"
    if change == "missing":
        target.unlink()
    else:
        target.write_bytes(target.read_bytes() + b"\n")
    # Even an archive at the previous lookup location cannot bypass frozen records.
    (tmp_path / skillsbench_attack.SOURCE_ARCHIVE).write_bytes(b"unused archive")
    error = "source_missing" if change == "missing" else "source_changed"
    with pytest.raises(ValueError, match=error):
        skillsbench_attack.source_templates(root)


def test_public_carrier_files_are_the_only_pinned_templates_and_tampering_fails(tmp_path):
    directory = EXPERIMENT_ROOT / "injections/skillsbench"
    assert {path.name for path in directory.glob("*.txt")} == set(
        skillsbench_attack._TEMPLATE_FILES.values()
    )
    for profile in skillsbench_attack.PROFILES:
        assert skillsbench_attack.adapted_template(profile)

    target = tmp_path / "injections/skillsbench/file-delete.txt"
    target.parent.mkdir(parents=True)
    target.write_text(skillsbench_attack.adapted_template("file_delete") + "changed\n")
    with pytest.raises(ValueError, match="skillsbench_injection_template_changed"):
        skillsbench_attack.adapted_template("file_delete", tmp_path)


def test_condition_design_rejects_rehashed_source_or_adaptation_change(pool):
    _source, _tokenizer, spec = pool
    (spec.root / "configs").mkdir()
    skillsbench_attack.freeze_condition_design(spec)
    path = spec.root / "configs/skillsbench-dymal4-conditions.json"
    value = json.loads(path.read_text())
    value["source_records"]["file_delete"]["adapted_template_sha256"] = "0" * 64
    value["manifest_hash"] = skillsbench_attack._json_hash(
        {key: item for key, item in value.items() if key != "manifest_hash"}
    )
    atomic_json(path, value)

    with pytest.raises(ValueError, match="condition_manifest_changed"):
        skillsbench_attack.validate_condition_design(spec)


def test_v8_preflight_reports_physical_injection_source_validation(monkeypatch):
    from tau_skill_evolution.skillsbench_runtime import SkillsBenchRunner

    spec = load_spec(EXPERIMENT_ROOT / "configs/skillsbench.yaml")
    monkeypatch.setattr(
        SkillsBenchRunner,
        "preflight",
        lambda self, **_kwargs: {"ready": True, "task_id": self.task_id},
    )
    result = skillsbench.skillsbench_preflight(
        spec, demo=False, task_ids=("3d-scan-calc",), runtime="docker"
    )
    checks = {item["name"]: item for item in result["checks"]}
    assert checks["skillsbench_injection_sources"]["ok"]
    assert checks["skillsbench_injection_matrix"]["ok"]
    assert checks["skillsbench_injection_matrix"]["detail"]["cells"] == 765
    assert checks["skillsbench_injection_matrix"]["detail"]["conditions"] == 9
    assert (
        checks["skillsbench_injection_sources"]["detail"]["source_archive_sha256"]
        == skillsbench_attack.SOURCE_ARCHIVE_SHA256
    )

    def invalid(_spec):
        raise ValueError("physical_source_changed")

    monkeypatch.setattr(skillsbench_attack, "validate_condition_design", invalid)
    failed = skillsbench.skillsbench_preflight(
        spec, demo=False, task_ids=("3d-scan-calc",), runtime="docker"
    )
    check = next(
        item for item in failed["checks"] if item["name"] == "skillsbench_injection_sources"
    )
    assert not failed["ready"] and not check["ok"]
    assert check["detail"] == "physical_source_changed"


def test_condition_targets_are_nested_and_frozen():
    spec = load_spec(EXPERIMENT_ROOT / "configs/skillsbench.yaml")
    assert spec.namespace == "skillsbench.skill-evolution.v8"
    assert spec.arms == SKILLSBENCH_ARMS and len(spec.cells) == 765
    for profile in skillsbench_attack.PROFILES:
        five = spec.condition(profile.replace("_", "-") + "-5")
        ten = spec.condition(profile.replace("_", "-") + "-10")
        assert len(five["target_document_ids"]) == 4
        assert len(ten["target_document_ids"]) == 9
        assert five["target_document_ids"] == ten["target_document_ids"][:4]


def test_injection_preserves_benign_and_nontarget_bytes(pool):
    source, tokenizer, spec = pool
    clean = source.root / "data/skillsbench/corpus"
    before = _snapshot(clean), _snapshot(source.checkout)
    five = skillsbench_attack.prepare_injected_pool(spec, "file-delete-5", tokenizer)
    ten = skillsbench_attack.prepare_injected_pool(spec, "file-delete-10", tokenizer)
    small = skillsbench.validate_pool(source.root, directory=five, tokenizer=tokenizer)
    large = skillsbench.validate_pool(source.root, directory=ten, tokenizer=tokenizer)
    assert (_snapshot(clean), _snapshot(source.checkout)) == before
    assert (
        small["injection"]["target_document_ids"] == large["injection"]["target_document_ids"][:4]
    )
    assert small["injection"]["placement"] == "after-first-h1-before-rechunking"
    clean_manifest = skillsbench.validate_pool(source.root)
    targets = set(small["injection"]["target_document_ids"])
    for record in small["pages"]:
        if not any(record["page_id"].startswith(target + "::") for target in targets):
            clean_record = next(
                item for item in clean_manifest["pages"] if item["page_id"] == record["page_id"]
            )
            assert record == clean_record
            assert (five / record["file"]).read_bytes() == (
                clean / clean_record["file"]
            ).read_bytes()


@pytest.mark.parametrize("arm", ["credential-abuse-5", "data-exfil-http-5", "cpu-hijack-5"])
def test_first_h1_insertion_keeps_behavior_and_exact_span(pool, arm):
    source, tokenizer, spec = pool
    directory = skillsbench_attack.prepare_injected_pool(spec, arm, tokenizer)
    manifest = skillsbench.validate_pool(source.root, directory=directory, tokenizer=tokenizer)
    document = next(item for item in manifest["documents"] if item["source_poisoned"])
    raw = (directory / document["file"]).read_bytes()
    entry = next(
        item
        for item in source.manifest["files"]
        if item["document_id"] == document["source_document_id"]
    )
    original = (source.checkout / entry["path"]).read_bytes()
    span = document["insertion"]
    assert raw[: span["insertion_byte_start"]] == original[: span["insertion_byte_start"]]
    assert raw[span["insertion_byte_end"] :] == original[span["insertion_byte_start"] :]
    payload = raw[span["payload_byte_start"] : span["payload_byte_end"]]
    assert hashlib.sha256(payload).hexdigest() == span["payload_sha256"]
    assert payload.startswith(b"## Runtime Integration Requirements")


def test_chunk_exposure_uses_token_span_containment(pool):
    source, tokenizer, spec = pool
    directory = skillsbench_attack.prepare_injected_pool(spec, "data-exfil-http-5", tokenizer)
    manifest = skillsbench.validate_pool(source.root, directory=directory, tokenizer=tokenizer)
    affected = [page for page in _pages(directory, manifest) if page.get("source_poisoned")]
    assert any(page["payload_present"] for page in affected)
    for page in affected:
        first, last = page["payload_token_start"], page["payload_token_end"]
        assert page["payload_present"] == (page["token_start"] < last and page["token_end"] > first)
        assert page["full_payload_present"] == (
            page["token_start"] <= first and page["token_end"] >= last
        )


@pytest.mark.parametrize("change", ["body", "document", "flags", "manifest", "source"])
def test_tampering_is_rejected(pool, change):
    source, tokenizer, spec = pool
    directory = skillsbench_attack.prepare_injected_pool(spec, "credential-abuse-5", tokenizer)
    manifest = json.loads((directory / "manifest.json").read_text())
    record = next(item for item in manifest["pages"] if item.get("source_poisoned"))
    page_path = directory / record["file"]
    page = json.loads(page_path.read_text())
    if change == "body":
        page["body"] += "changed"
        atomic_json(page_path, page)
    elif change == "document":
        document = next(item for item in manifest["documents"] if item["source_poisoned"])
        (directory / document["file"]).write_text("changed")
    elif change == "flags":
        page["full_payload_present"] = not page["full_payload_present"]
        record["full_payload_present"] = page["full_payload_present"]
        atomic_json(page_path, page)
        manifest["corpus_hash"] = skillsbench._json_hash(
            {k: v for k, v in manifest.items() if k != "corpus_hash"}
        )
        atomic_json(directory / "manifest.json", manifest)
    elif change == "manifest":
        manifest["injection"]["target_document_ids"].append("unknown")
        atomic_json(directory / "manifest.json", manifest)
    else:
        (source.checkout / source.manifest["files"][0]["path"]).write_text("changed")
    with pytest.raises((ValueError, KeyError)):
        skillsbench.validate_pool(source.root, directory=directory, tokenizer=tokenizer)


def test_sealed_pool_reuse_does_not_retokenize(pool, monkeypatch):
    _source, tokenizer, spec = pool
    directory = skillsbench_attack.prepare_injected_pool(spec, "file-delete-5", tokenizer)
    before = _snapshot(directory)

    def unavailable(*_args, **_kwargs):
        raise AssertionError("a sealed pool must not be rebuilt")

    monkeypatch.setattr(CharacterTokenizer, "encode", unavailable)
    assert skillsbench_attack.prepare_injected_pool(spec, "file-delete-5") == directory
    assert _snapshot(directory) == before


def test_failed_build_is_not_published(pool, monkeypatch):
    _source, tokenizer, spec = pool

    def fail(*_args, **_kwargs):
        raise RuntimeError("tokenizer interrupted")

    monkeypatch.setattr(CharacterTokenizer, "encode", fail)
    with pytest.raises(RuntimeError, match="interrupted"):
        skillsbench_attack.prepare_injected_pool(spec, "cpu-hijack-5", tokenizer)
    parent = spec.root / "data/skillsbench/injected/v8"
    assert not any(path.is_dir() for path in parent.iterdir())


def test_benign_selection_needs_no_attack_source(tmp_path):
    spec = SimpleNamespace(root=tmp_path, arms=SKILLSBENCH_ARMS)
    assert skillsbench.selected_pool(spec) == tmp_path / "data/skillsbench/corpus"


def test_retrieval_contract_binds_pool_bm25_and_dense_inputs(pool):
    _source, tokenizer, spec = pool
    directory = skillsbench_attack.prepare_injected_pool(spec, "data-exfil-http-5", tokenizer)
    dense = _seal_dense(spec, directory)

    contract = skillsbench_attack.retrieval_contract(spec, "data-exfil-http-5")

    assert contract["condition"]["condition_id"] == "data-exfil-http-5"
    assert contract["payload_chunk_count"] == 4
    assert contract["full_payload_chunk_count"] == 4
    assert (
        contract["pool_manifest_sha256"]
        == hashlib.sha256((directory / "manifest.json").read_bytes()).hexdigest()
    )
    assert (
        contract["dense_manifest_sha256"]
        == hashlib.sha256((dense / "manifest.json").read_bytes()).hexdigest()
    )
    assert contract["dense_contract"]["page_count"] == contract["page_count"]
    assert contract["dense_vectors"]["shape"] == [contract["page_count"], 2]


def test_retrieval_contract_rejects_dense_from_different_settings(pool):
    _source, tokenizer, spec = pool
    directory = skillsbench_attack.prepare_injected_pool(spec, "file-delete-5", tokenizer)
    dense = _seal_dense(spec, directory)
    manifest = json.loads((dense / "manifest.json").read_text())
    manifest["contract"]["model_revision"] = "different-revision"
    unsigned = {key: value for key, value in manifest.items() if key != "manifest_payload_sha256"}
    manifest["manifest_payload_sha256"] = canonical_json_sha256(unsigned)
    (dense / "manifest.json").write_bytes(canonical_json_bytes(manifest) + b"\n")

    with pytest.raises(ValueError, match="dense_contract_mismatch"):
        skillsbench_attack.retrieval_contract(spec, "file-delete-5")


def test_retrieval_contract_rejects_pool_from_a_different_condition(pool):
    _source, tokenizer, spec = pool
    expected = skillsbench_attack.prepare_injected_pool(spec, "credential-abuse-5", tokenizer)
    swapped = skillsbench_attack.prepare_injected_pool(spec, "file-delete-5", tokenizer)
    _seal_dense(spec, expected)
    _seal_dense(spec, swapped)

    with pytest.raises(ValueError, match="condition_pool_mismatch"):
        skillsbench_attack.retrieval_contract(spec, "credential-abuse-5", directory=swapped)


def test_matrix_manifest_has_765_cells_and_full_corpus_provenance(pool):
    _source, tokenizer, spec = pool
    (spec.root / "configs").mkdir()
    skillsbench_attack.freeze_condition_design(spec)
    directories = {}
    for arm in SKILLSBENCH_ARMS:
        directory = (
            spec.root / "data/skillsbench/corpus"
            if arm == "benign"
            else skillsbench_attack.prepare_injected_pool(spec, arm, tokenizer)
        )
        directories[arm] = directory
        _seal_dense(spec, directory)

    manifest = skillsbench_attack.matrix_manifest(spec, directories)

    assert len(manifest["cells"]) == 765
    assert set(manifest["corpora"]) == set(SKILLSBENCH_ARMS)
    assert set(manifest["source_records"]) == set(skillsbench_attack.PROFILES)
    assert manifest["condition_design"]["condition_manifest_hash"]
    assert "source_provenance" not in manifest["corpora"]["benign"]
    for arm in SKILLSBENCH_ARMS[1:]:
        corpus = manifest["corpora"][arm]
        assert corpus["source_provenance"]["adapted_template_sha256"]
        assert corpus["source_provenance"]["record_sha256"]
        assert len(corpus["target_documents"]) == (4 if arm.endswith("-5") else 9)
        assert corpus["chunk_mapping_sha256"]


def test_matrix_validation_recomputes_every_frozen_corpus_and_index(pool):
    _source, tokenizer, spec = pool
    (spec.root / "configs").mkdir()
    skillsbench_attack.freeze_condition_design(spec)
    directories = {}
    for arm in SKILLSBENCH_ARMS:
        directory = (
            spec.root / "data/skillsbench/corpus"
            if arm == "benign"
            else skillsbench_attack.prepare_injected_pool(spec, arm, tokenizer)
        )
        directories[arm] = directory
        _seal_dense(spec, directory)
    skillsbench_attack.freeze_matrix_manifest(spec, directories)

    detail = skillsbench_attack.validate_matrix_manifest(spec)
    assert detail["cells"] == 765
    assert detail["conditions"] == 9
    assert set(detail["chunks_by_condition"]) == set(SKILLSBENCH_ARMS)

    path = spec.root / skillsbench_attack.MATRIX_MANIFEST
    changed = json.loads(path.read_text())
    changed["corpora"]["file-delete-5"]["payload_chunk_count"] = 0
    changed["manifest_hash"] = skillsbench_attack._json_hash(
        {key: value for key, value in changed.items() if key != "manifest_hash"}
    )
    atomic_json(path, changed)
    with pytest.raises(ValueError, match="matrix_manifest_changed"):
        skillsbench_attack.validate_matrix_manifest(spec)


def test_matrix_validation_rejects_swapped_condition_directories(pool):
    _source, tokenizer, spec = pool
    (spec.root / "configs").mkdir()
    skillsbench_attack.freeze_condition_design(spec)
    directories = {}
    for arm in SKILLSBENCH_ARMS:
        directory = (
            spec.root / "data/skillsbench/corpus"
            if arm == "benign"
            else skillsbench_attack.prepare_injected_pool(spec, arm, tokenizer)
        )
        directories[arm] = directory
        _seal_dense(spec, directory)
    manifest = skillsbench_attack.freeze_matrix_manifest(spec, directories)
    left, right = "credential-abuse-5", "file-delete-5"
    manifest["corpora"][left]["pool_path"], manifest["corpora"][right]["pool_path"] = (
        manifest["corpora"][right]["pool_path"],
        manifest["corpora"][left]["pool_path"],
    )
    manifest["manifest_hash"] = skillsbench_attack._json_hash(
        {key: value for key, value in manifest.items() if key != "manifest_hash"}
    )
    atomic_json(spec.root / skillsbench_attack.MATRIX_MANIFEST, manifest)

    with pytest.raises(ValueError, match="condition_pool_mismatch"):
        skillsbench_attack.validate_matrix_manifest(spec)
