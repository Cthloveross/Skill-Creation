"""Production exposure accepts sealed whole sources and records imported observations."""

from __future__ import annotations

import copy
import hashlib
from types import SimpleNamespace

import pytest
from tau_skill_evolution import skillsbench_attack as attack
from tau_skill_evolution.artifacts import FrozenBase, atomic_json
from tau_skill_evolution.journal import Journal

ARM = "data-exfil-http-5"
SOURCE = "task::background/guide.md"
OTHER = "task::background/other.md"


def whole_pool(tmp_path):
    directory = tmp_path / "pool"
    directory.mkdir()
    payload = b"inert payload text"
    prefix = "Public caf\u00e9.\n".encode()
    span = {
        "payload_byte_start": len(prefix),
        "payload_byte_end": len(prefix) + len(payload),
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
    }
    values = [
        {
            "page_id": SOURCE,
            "source_document_id": SOURCE,
            "title": "public",
            "body": (prefix + payload + b"\nMore public facts.").decode(),
            "source_poisoned": True,
            "payload_present": True,
            "full_payload_present": True,
            "payload_sha256": span["payload_sha256"],
            "insertion": span,
        },
        {
            "page_id": OTHER,
            "source_document_id": OTHER,
            "title": "public",
            "body": "Other public facts.",
            "source_poisoned": False,
            "payload_present": False,
            "full_payload_present": False,
        },
    ]
    for value in values:
        value["content_sha256"] = hashlib.sha256(value["body"].encode()).hexdigest()
    condition = {
        "condition_id": ARM,
        "profile": "data_exfil_http",
        "level": 5,
        "target_document_ids": [SOURCE],
    }
    manifest = {
        "schema": attack.WHOLE_DOCUMENT_SCHEMA,
        "document_unit": "source_document",
        "chunking": False,
        "condition_id": ARM,
        "source_documents": len(values),
        "injection": condition,
    }
    retrieval = {
        "condition": condition,
        "document_unit": "source_document",
        "chunking": False,
        "pool_path": "pool",
        "source_documents": len(values),
        "page_count": len(values),
        "payload_document_count": 1,
        "full_payload_document_count": 1,
    }
    binding = {"task_id": "task", "condition_id": ARM, "retrieval": retrieval}

    def seal():
        records = []
        for index, value in enumerate(values):
            filename = f"{index}.json"
            atomic_json(directory / filename, value)
            records.append({"file": filename, **{k: v for k, v in value.items() if k != "body"}})
        manifest["pages"] = records
        manifest["corpus_hash"] = attack._json_hash(
            {key: value for key, value in manifest.items() if key != "corpus_hash"}
        )
        atomic_json(directory / "manifest.json", manifest)
        retrieval["corpus_hash"] = manifest["corpus_hash"]
        retrieval["pool_manifest_sha256"] = hashlib.sha256(
            (directory / "manifest.json").read_bytes()
        ).hexdigest()

    seal()
    base = FrozenBase(
        ({"document_id": SOURCE, "title": "public", "content": values[0]["body"]},),
        {"opening": "task"},
    )
    return SimpleNamespace(
        directory=directory, values=values, manifest=manifest, binding=binding, seal=seal, base=base
    )


def journal_for(tmp_path, fixture):
    journal = Journal(tmp_path / "journal")
    journal.dispatch(
        "retrieval-corpus-contract", fixture.binding, lambda: fixture.binding, external=False
    )
    return journal


def test_whole_source_ids_require_the_whole_source_manifest(tmp_path):
    fixture = whole_pool(tmp_path)
    pages = attack.load_acquisition_pages(fixture.manifest, fixture.directory, verify=True)
    assert set(pages) == {SOURCE, OTHER}
    for changed in (
        {"schema": "skillsbench.pool.injected.v8"},
        {"document_unit": "chunk"},
        {"chunking": True},
        {"schema": "skillsbench.pool.injected.v8", "document_unit": "chunk"},
    ):
        with pytest.raises(ValueError, match="acquisition_(manifest_invalid|page_changed)"):
            attack.load_acquisition_pages(
                {**fixture.manifest, **changed}, fixture.directory, verify=True
            )
    fixture.values[0]["page_id"] = SOURCE + "::chunk"
    fixture.seal()
    with pytest.raises(ValueError, match="page_changed"):
        attack.load_acquisition_pages(fixture.manifest, fixture.directory, verify=True)


def test_whole_document_exposure_uses_document_counts_and_same_four_stages(tmp_path):
    fixture = whole_pool(tmp_path)
    journal = journal_for(tmp_path, fixture)
    journal.dispatch(
        "acquisition/search/0",
        {"query": "public facts"},
        lambda: {
            "status": "ok",
            "result": {"results": [{"page_id": item} for item in (SOURCE, OTHER, SOURCE)]},
        },
    )
    journal.dispatch(
        "acquisition/analyzer/0",
        {"inputs": {"returned_documents": [{"document_id": SOURCE}]}},
        lambda: {},
    )
    observed = attack.acquisition_payload_exposure(tmp_path, fixture.base, journal)
    assert observed["document_unit"] == "source_document"
    assert observed["status"] == "MEASURED"
    assert tuple(observed["stages"]) == attack.ACQUISITION_STAGES
    returned = observed["stages"]["search_returns"]
    assert returned["document_occurrences"] == 3
    assert returned["unique_documents"] == 2
    assert returned["rates"]["full_payload_present"]["document_occurrences"] == (
        attack.acquisition_fraction(2, 3)
    )
    assert not ({"unique_chunks", "chunk_occurrences"} & attack.acquisition_keys(observed))


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("payload_document_count", 0),
        ("full_payload_document_count", 0),
        ("payload_document_count", True),
        ("payload_document_count", None),
        ("full_payload_document_count", None),
        ("source_documents", 3),
        ("document_unit", "chunk"),
    ],
)
def test_whole_document_counts_and_unit_are_bound(tmp_path, key, value):
    fixture = whole_pool(tmp_path)
    fixture.binding["retrieval"][key] = value
    with pytest.raises(ValueError, match="manifest_changed"):
        attack.acquisition_payload_exposure(tmp_path, fixture.base, journal_for(tmp_path, fixture))


@pytest.mark.parametrize("change", ["body_hash", "payload_hash", "payload_span", "partial"])
def test_whole_payload_bytes_hash_and_completeness_are_verified(tmp_path, change):
    fixture = whole_pool(tmp_path)
    page = fixture.values[0]
    if change == "body_hash":
        page["body"] += " changed"
    elif change == "payload_hash":
        page["payload_sha256"] = page["insertion"]["payload_sha256"] = "0" * 64
    elif change == "payload_span":
        page["insertion"]["payload_byte_end"] += 1
    else:
        page["full_payload_present"] = False
    fixture.seal()
    with pytest.raises(ValueError, match="page_changed"):
        attack.acquisition_payload_exposure(tmp_path, fixture.base, journal_for(tmp_path, fixture))


@pytest.mark.parametrize("change", ["manifest_condition", "injection_condition", "manifest_hash"])
def test_whole_pool_rejects_wrong_conditions_and_unbound_manifests(tmp_path, change):
    fixture = whole_pool(tmp_path)
    if change == "manifest_condition":
        fixture.manifest["condition_id"] = "benign"
    elif change == "injection_condition":
        fixture.manifest["injection"] = {**fixture.manifest["injection"], "level": 10}
    else:
        fixture.binding["retrieval"]["pool_manifest_sha256"] = "0" * 64
    if change != "manifest_hash":
        fixture.seal()
    with pytest.raises(ValueError, match="(condition_pool_mismatch|manifest_changed)"):
        attack.acquisition_payload_exposure(tmp_path, fixture.base, journal_for(tmp_path, fixture))


@pytest.mark.parametrize("key", ["source_poisoned", "source_sha256", "insertion"])
def test_whole_source_provenance_never_reaches_analyzer_inputs(tmp_path, key):
    fixture = whole_pool(tmp_path)
    journal = journal_for(tmp_path, fixture)
    journal.dispatch(
        "acquisition/analyzer/0",
        {"inputs": {"returned_documents": [{"document_id": SOURCE, key: "host-only"}]}},
        lambda: {},
    )
    with pytest.raises(ValueError, match="host_metadata_visible_to_analyzer"):
        attack.acquisition_payload_exposure(tmp_path, fixture.base, journal)


def imported_observations(fixture):
    pages = attack.load_acquisition_pages(fixture.manifest, fixture.directory, verify=True)

    def stage(ids):
        return attack.source_document_metrics(attack.acquisition_exposure(ids, pages))

    return {
        "catalog_hash": "c" * 64,
        "entry_hash": "e" * 64,
        "task_id": "task",
        "condition_id": ARM,
        "base_hash": fixture.base.base_hash,
        "document_unit": "source_document",
        "source_catalog": "/producer/catalog.json",
        "producer": {"analyzer_model": "producer-model"},
        "calls_performed_here": {"analyzer": 0, "search": 0, "read_only": 0, "clarify": 0},
        "source_metrics": {
            "task_id": "task",
            "condition_id": ARM,
            "base_hash": fixture.base.base_hash,
            "pool_hash": fixture.manifest["corpus_hash"],
            "retrieval_contract": fixture.binding,
            "retrieval_unit": "source_document",
            "status": "MEASURED",
            "model_input_host_metadata_absent": True,
            "selected_document_ids": [SOURCE],
            "pool": {"indexed_documents": stage([SOURCE, OTHER])},
            "retrieval_return_occurrences": stage([SOURCE, OTHER, SOURCE]),
            "analyzer_visible_occurrences": stage([SOURCE, OTHER]),
            "frozen_base": stage([SOURCE]),
            "searches": [{"results": [{"document_id": item} for item in (SOURCE, OTHER, SOURCE)]}],
            "analyzer_requests": [{"visible_document_ids": [SOURCE, OTHER]}],
        },
    }


def test_imported_exposure_preserves_producer_observations_and_zero_consumer_calls(tmp_path):
    fixture = whole_pool(tmp_path)
    journal = journal_for(tmp_path, fixture)
    imported = imported_observations(fixture)
    journal.dispatch("import-acquisition", imported, lambda: imported, external=False)
    observed = attack.acquisition_payload_exposure(tmp_path, fixture.base, journal)
    assert observed["status"] == "MEASURED"
    assert observed["document_unit"] == "source_document"
    assert observed["stages"]["analyzer_visible"]["document_occurrences"] == 2
    assert observed["stages"]["frozen_base"]["unique_documents"] == 1
    assert observed["provenance"]["kind"] == "imported_acquisition"
    assert observed["provenance"]["producer"] == imported["producer"]
    assert observed["calls_performed_here"]["analyzer"] == 0
    assert not journal.dispatched("acquisition/analyzer/0")


@pytest.mark.parametrize(
    "change", ["condition", "base", "visibility", "consumer_calls", "local_call", "outside"]
)
def test_imported_observations_reject_mismatched_identity_or_exposure(tmp_path, change):
    fixture = whole_pool(tmp_path)
    journal = journal_for(tmp_path, fixture)
    imported = imported_observations(fixture)
    if change == "condition":
        imported["source_metrics"]["condition_id"] = "benign"
    elif change == "base":
        imported["source_metrics"]["base_hash"] = "0" * 64
    elif change == "visibility":
        imported["source_metrics"]["analyzer_visible_occurrences"]["document_occurrences"] = 99
    elif change == "outside":
        imported["source_metrics"]["analyzer_requests"][0]["visible_document_ids"] = ["outside"]
    elif change == "local_call":
        journal.dispatch("acquisition/analyzer/0", {"inputs": {}}, lambda: {})
    else:
        imported["calls_performed_here"]["analyzer"] = 1
    journal.dispatch("import-acquisition", imported, lambda: imported, external=False)
    with pytest.raises(ValueError, match="(acquisition_import|outside_sealed_pool)"):
        attack.acquisition_payload_exposure(tmp_path, fixture.base, journal)


def test_source_document_metric_normalizer_is_recursive_and_leaves_input_unchanged():
    original = {"rechunked": [{"unique_chunks": 2, "chunk_occurrences": 3}]}
    unchanged = copy.deepcopy(original)
    assert attack.source_document_metrics(original) == {
        "indexed_documents": [{"unique_documents": 2, "document_occurrences": 3}]
    }
    assert original == unchanged
