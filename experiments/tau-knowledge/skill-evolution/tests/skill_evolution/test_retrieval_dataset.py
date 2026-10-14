"""Frozen acquisitions are portable and independent of consumer models."""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
from types import SimpleNamespace

import pytest
from tau_skill_evolution import skillsbench
from tau_skill_evolution import skillsbench_whole_documents as whole
from tau_skill_evolution.artifacts import FrozenBase, atomic_json, load_base, seal_base
from tau_skill_evolution.core import Page
from tau_skill_evolution.core._canonical import canonical_json_sha256 as digest
from tau_skill_evolution.dense import DenseIndex
from tau_skill_evolution.retrieval_dataset import load_catalog, write_catalog
from tau_skill_evolution.skillsbench_attack import acquisition_exposure, source_document_metrics
from tau_skill_evolution.spec import SKILLSBENCH_CONFIG, load_spec
from tau_skill_evolution.workflow import Workflow


@pytest.fixture
def dataset(tmp_path, monkeypatch):
    root = tmp_path / "experiment"
    root.mkdir()
    source_values = {
        "corpus_manifest": "data/skillsbench/public-manifest.json",
        "condition_manifest": "configs/conditions.json",
    }
    for relative in (
        "data/skillsbench/source-tree.json",
        "data/skillsbench/source-manifest.json",
        *source_values.values(),
    ):
        atomic_json(root / relative, {"pinned": relative})
    (root / "prompts").mkdir()
    (root / "prompts/analyzer.md").write_text("Original Analyzer prompt")
    (root / "prompts/generator.md").write_text("Generate a Skill")
    checkout = root / "checkout"
    checkout.mkdir()
    input_body = "READ OBSERVATION BODY MUST STAY PRIVATE"
    document_body = "WHOLE DOCUMENT BODY STAYS PRIVATE"
    (checkout / "input.txt").write_text(input_body)
    (checkout / "guide.md").write_text(document_body)

    class Source:
        def __init__(self, _root):
            self.checkout = checkout
            self.manifest = {
                "manifest_hash": "pinned-source",
                "files": [
                    {
                        "task_id": "task-a",
                        "path": "input.txt",
                        "relative_path": "environment/input.txt",
                        "sha256": hashlib.sha256(input_body.encode()).hexdigest(),
                    },
                    {
                        "task_id": "task-a",
                        "path": "guide.md",
                        "relative_path": "background/guide.md",
                        "document_id": "task-a::background/guide.md",
                        "sha256": hashlib.sha256(document_body.encode()).hexdigest(),
                    },
                ],
            }

        def public_inputs(self, task):
            return {
                "task_id": task,
                "opening": "FULL TASK OPENING STAYS PRIVATE",
                "workspace": {"directory": "/data"},
            }

        def task(self, task):
            return {
                "opening": self.public_inputs(task)["opening"],
                "public_input_manifest": self.manifest["files"],
                "environment": {"workdir": "/data"},
            }

    class View:
        def __init__(self, source, task):
            pass

        def read(self, tool, arguments):
            assert tool == "read_input_file"
            return {"path": arguments["path"], "content": (checkout / "input.txt").read_text()}

        def close(self):
            pass

    monkeypatch.setattr(skillsbench, "SkillsBenchSource", Source)
    monkeypatch.setattr(skillsbench, "SkillsBenchInputView", View)
    original_directory = root / "prepared-original-condition-pool"
    original_manifest = {"corpus_hash": "original", "pages": []}
    atomic_json(original_directory / "manifest.json", original_manifest)
    monkeypatch.setattr(whole, "selected_pool", lambda *_: original_directory)
    monkeypatch.setattr(whole, "validate_pool", lambda *_args, **_kwargs: original_manifest)
    values = copy.deepcopy(load_spec(SKILLSBENCH_CONFIG).values)
    values["source"] = source_values
    values["matrix"]["arms"] = ["benign", "credential-exfil-5"]
    for role in values["roles"].values():
        role.pop("prompt", None)
    condition = {"condition_id": "benign", "profile": None, "level": 0, "target_document_ids": []}

    def spec(model="producer-gpt"):
        return SimpleNamespace(
            root=root,
            values=values,
            experiment="skillsbench",
            namespace="skillsbench.skill-evolution.v8",
            tasks=("task-a", "task-b"),
            arms=("benign", "credential-exfil-5"),
            cells=(
                ("task-a", "benign"),
                ("task-b", "benign"),
                ("task-a", "credential-exfil-5"),
                ("task-b", "credential-exfil-5"),
            ),
            identity={"provider": {"model": model}, "identity_hash": digest(model)},
            condition=lambda arm: (
                condition if arm == "benign" else {**condition, "condition_id": arm}
            ),
        )

    page = {
        "page_id": "task-a::background/guide.md",
        "source_document_id": "task-a::background/guide.md",
        "title": "task-a::background/guide.md",
        "body": document_body,
        "source_poisoned": False,
        "payload_present": False,
        "full_payload_present": False,
    }
    page["content_sha256"] = hashlib.sha256(page["body"].encode()).hexdigest()
    pool, manifest = whole.prepare_pool(spec(), Source(root), "benign")
    descriptors = [{k: page[k] for k in ("page_id", "title", "content_sha256")}]
    dense_dir = root / "data/skillsbench/whole-documents-dense" / manifest["corpus_hash"]

    class Tokenizer:
        model_id, revision, dimensions = "fixed-embedding", "pinned", 2

        def input_token_ids(self, text):
            return tuple(range(len(text.split())))

        def content_token_offsets(self, text):
            return tuple((index, index + 1) for index in range(len(text)))

    class Embeddings:
        model_id, revision, dimensions, pooling = "fixed-embedding", "pinned", 2, "last_token"

        def embed_documents(self, texts):
            return [(1.0, 0.0) for text in texts]

        def embed_query(self, query):
            pytest.fail("reuse does not embed queries")

    index = DenseIndex.build(
        [Page(page["page_id"], page["title"], page["body"])],
        client=Embeddings(),
        tokenizer=Tokenizer(),
        max_input_tokens=8192,
    )
    dense = index.save_cache(dense_dir)
    contract = {
        "task_id": "task-a",
        "condition_id": "benign",
        "retrieval": {
            "condition": condition,
            "document_unit": "source_document",
            "chunking": False,
            "pool_path": str(pool.relative_to(root)),
            "pool_manifest_sha256": hashlib.sha256(
                (pool / "manifest.json").read_bytes()
            ).hexdigest(),
            "corpus_hash": manifest["corpus_hash"],
            "source_manifest_hash": "pinned-source",
            "original_corpus_hash": "original",
            "original_pool_manifest_sha256": manifest["original_pool_manifest_sha256"],
            "page_count": 1,
            "source_documents": 1,
            "page_set_hash": digest(descriptors),
            "payload_document_count": 0,
            "full_payload_document_count": 0,
            "dense_manifest_sha256": hashlib.sha256(
                (dense_dir / "manifest.json").read_bytes()
            ).hexdigest(),
            "dense_contract": index.manifest,
            "dense_vectors": dense["vectors"],
            "dense_manifest_payload_sha256": dense["manifest_payload_sha256"],
            "embedding": {
                "endpoint": "http://127.0.0.1:18141/v1",
                "model": "fixed-embedding",
                "revision": "pinned",
                "dimensions": 2,
                "max_input_tokens": 8192,
            },
        },
    }
    public = Source(root).public_inputs("task-a")
    public.update(
        clarifications=[],
        read_only_observations=[
            {
                "tool": "read_input_file",
                "arguments": {"path": "/data/input.txt"},
                "status": "ok",
                "result": {"path": "/data/input.txt", "content": input_body},
            }
        ],
    )
    base = FrozenBase(
        ({"document_id": page["page_id"], "title": page["title"], "content": page["body"]},),
        public,
        ({"requirement": "Public facts", "document_id": page["page_id"]},),
        "sufficient",
        17,
    )
    producer = Workflow(spec(), tmp_path / "retrieve", counter=len)
    directory, journal = producer._cell("task-a", "benign")
    seal_base(directory / "base", base)
    journal.dispatch("retrieval-corpus-contract", contract, lambda: contract, external=False)
    exposure = source_document_metrics(
        acquisition_exposure([page["page_id"]], {page["page_id"]: page})
    )
    metrics = {
        "task_id": "task-a",
        "condition_id": "benign",
        "arm": "benign",
        "status": "MEASURED",
        "base_hash": base.base_hash,
        "retrieval_unit": "source_document",
        "retrieval_contract": contract,
        "pool_hash": manifest["corpus_hash"],
        "model_input_host_metadata_absent": True,
        "selected_document_ids": [page["page_id"]],
        "pool": {"indexed_documents": exposure},
        "frozen_base": exposure,
        "retrieval_return_occurrences": exposure,
        "analyzer_visible_occurrences": exposure,
        "analyzer_request_count": 2,
        "search_call_count": 1,
        "searches": [{"index": 0, "results": [{"document_id": page["page_id"]}]}],
        "analyzer_requests": [
            {"index": 0, "visible_document_ids": []},
            {"index": 1, "visible_document_ids": [page["page_id"]]},
        ],
    }
    atomic_json(directory / "probe-result.json", metrics)
    catalog = write_catalog(producer, spec().tasks, ("benign",))
    return SimpleNamespace(
        root=root,
        producer=producer,
        spec=spec,
        base=base,
        catalog=catalog,
        directory=directory,
        dense_dir=dense_dir,
        pool=pool,
        tmp=tmp_path,
    )


def consumer(dataset, *, path="consumer", model="different-generator"):
    calls = []

    def model_factory(role):
        assert role == "generator", "reused bases must never invoke Analyzer"
        calls.append(role)
        return lambda payload: {"files": [{"path": "SKILL.md", "content": "Use public facts"}]}

    def no_corpus(*args):
        pytest.fail("reused bases must never construct a retriever")

    workflow = Workflow(
        dataset.spec(model),
        dataset.tmp / path,
        bases_from=dataset.producer.root / "catalog.json",
        counter=len,
        bank_factory=lambda task: SimpleNamespace(tool_schemas=[]),
        model_factory=model_factory,
        corpus_factory=no_corpus,
    )
    return workflow, calls


def test_partial_catalog_reuses_base_across_models_without_analyzer(dataset):
    assert dataset.catalog["status"] == "PARTIAL"
    assert dataset.catalog["sealed_cell_count"] == 1
    workflow, calls = consumer(dataset)
    workflow.create((("task-a", "benign"),))
    directory, journal = workflow._cell("task-a", "benign")
    assert journal.response("creation")["status"] == "CREATED"
    assert load_base(directory / "base").to_dict() == dataset.base.to_dict()
    assert calls == ["generator"]
    assert journal.response("import-acquisition")["calls_performed_here"] == {
        "analyzer": 0,
        "search": 0,
        "read_only": 0,
        "clarify": 0,
    }
    assert workflow.trial_id != dataset.producer.trial_id
    assert not any(
        json.loads(path.read_text())["operation_id"].startswith("acquisition/")
        for path in journal.root.glob("*/request.json")
    )
    acquisition = workflow.report()["cases"][0]["acquisition"]
    assert acquisition["payload_exposure"]["stages"]["analyzer_visible"]["status"] == "MEASURED"
    assert acquisition["calls_performed_here"]["analyzer"] == 0


def test_portable_recipe_reconstructs_exact_base_without_private_artifacts_or_index(dataset):
    catalog_text = (dataset.producer.root / "catalog.json").read_text()
    assert "WHOLE DOCUMENT BODY STAYS PRIVATE" not in catalog_text
    assert "READ OBSERVATION BODY MUST STAY PRIVATE" not in catalog_text
    assert "FULL TASK OPENING STAYS PRIVATE" not in catalog_text
    (dataset.directory / "base").unlink()
    shutil.rmtree(dataset.directory / "journal")
    (dataset.directory / "probe-result.json").unlink()
    shutil.rmtree(dataset.dense_dir)
    catalog = load_catalog(dataset.producer.root)
    catalog.validate(dataset.spec("other-model"), (("task-a", "benign"),))
    assert (
        catalog.materialize(dataset.spec(), "task-a", "benign").to_dict() == dataset.base.to_dict()
    )


def test_missing_whole_pool_rebuilds_from_prepared_source_data_without_index(dataset):
    shutil.rmtree(dataset.pool)
    shutil.rmtree(dataset.dense_dir)
    (dataset.directory / "base").unlink()
    catalog = load_catalog(dataset.producer.root)
    catalog.validate(dataset.spec(), (("task-a", "benign"),))
    assert dataset.pool.is_dir()
    assert not dataset.dense_dir.exists()
    assert (
        catalog.materialize(dataset.spec(), "task-a", "benign").base_hash == dataset.base.base_hash
    )


def test_malformed_producer_exposure_rejects_before_generator(dataset):
    value = copy.deepcopy(dataset.catalog)
    entry = value["entries"][0]
    entry["source_metrics"]["analyzer_visible_occurrences"]["unique_documents"] = 999
    entry["entry_hash"] = digest({k: v for k, v in entry.items() if k != "entry_hash"})
    value["catalog_hash"] = digest({k: v for k, v in value.items() if k != "catalog_hash"})
    atomic_json(dataset.producer.root / "catalog.json", value)
    (dataset.directory / "probe-result.json").unlink()
    workflow, calls = consumer(dataset)
    with pytest.raises(ValueError, match="import_exposure_changed"):
        workflow.create((("task-a", "benign"),))
    assert calls == []


@pytest.mark.parametrize("cell", [("task-b", "benign"), ("task-a", "credential-exfil-5")])
def test_missing_or_unseen_condition_rejects_before_any_generator(dataset, cell):
    workflow, calls = consumer(dataset)
    with pytest.raises(ValueError, match="retrieval_dataset_cell_missing"):
        workflow.create((("task-a", "benign"), cell))
    assert calls == []


@pytest.mark.parametrize(
    "target",
    [
        "source",
        "base",
        "base-directory",
        "base-symlink",
        "base-dangling-symlink",
        "pool",
        "index",
        "condition",
    ],
)
def test_tampering_rejects_before_generator(dataset, target):
    workflow, calls = consumer(dataset)
    if target == "source":
        (dataset.root / "checkout/input.txt").write_text("changed task input")
    elif target == "base":
        (dataset.directory / "base").write_text("{}")
    elif target.startswith("base-"):
        base_path = dataset.directory / "base"
        base_path.unlink()
        if target == "base-directory":
            base_path.mkdir()
            atomic_json(base_path / "base.json", dataset.base.to_dict())
        else:
            destination = dataset.producer.root / "base-copy"
            if target == "base-symlink":
                seal_base(destination, dataset.base)
            base_path.symlink_to(destination)
    elif target == "pool":
        manifest = json.loads((dataset.pool / "manifest.json").read_text())
        atomic_json(dataset.pool / manifest["pages"][0]["file"], {"body": "changed"})
    elif target == "index":
        (dataset.dense_dir / "vectors.f32").write_bytes(b"changed")
    else:
        workflow.spec.condition = lambda arm: {"condition_id": arm, "level": 100}
    with pytest.raises((ValueError, RuntimeError, KeyError)):
        workflow.create((("task-a", "benign"),))
    assert calls == []


def test_resume_rejects_replaced_catalog_and_auto_recovers_original_binding(dataset):
    workflow, _ = consumer(dataset)
    resumed = Workflow(dataset.spec("different-generator"), workflow.root, counter=len)
    assert resumed.bases_from.identity == workflow.bases_from.identity
    value = copy.deepcopy(dataset.catalog)
    value["status"] = "COMPLETE"
    value["catalog_hash"] = digest({k: v for k, v in value.items() if k != "catalog_hash"})
    atomic_json(dataset.producer.root / "catalog.json", value)
    with pytest.raises(ValueError, match="identity differs"):
        Workflow(dataset.spec("different-generator"), workflow.root, counter=len)


def test_catalog_hash_rejects_unsealed_edit(dataset):
    value = copy.deepcopy(dataset.catalog)
    value["entries"][0]["base_hash"] = "0" * 64
    atomic_json(dataset.producer.root / "catalog.json", value)
    with pytest.raises(ValueError, match="catalog_invalid"):
        load_catalog(dataset.producer.root)
