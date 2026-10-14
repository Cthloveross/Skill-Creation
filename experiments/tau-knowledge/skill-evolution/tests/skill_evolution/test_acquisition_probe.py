"""The v8 retrieval-only pilot measures actual payload visibility without creating Skills."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from tau_skill_evolution.artifacts import FrozenBase, atomic_json
from tau_skill_evolution.journal import Journal, UnknownOperation
from tau_skill_evolution.skillsbench_attack import (
    ACQUISITION_FLAGS,
    acquisition_payload_exposure,
)

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/probe_skillsbench_acquisition.py"
module_spec = importlib.util.spec_from_file_location("acquisition_probe", SCRIPT)
probe = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(probe)

ARM = "data-exfil-http-5"
CONDITION = {
    "condition_id": ARM,
    "profile": "data_exfil_http",
    "level": 5,
    "target_document_ids": ["a"],
}
BUDGETS = {
    "search": 2,
    "clarify": 0,
    "read_only": 0,
    "analyzer_steps": 3,
    "base_tokens": 32768,
}


def bind_contract(journal):
    value = {
        "task_id": "task",
        "condition_id": ARM,
        "retrieval": {"corpus_hash": "a" * 64},
    }
    journal.dispatch("retrieval-corpus-contract", value, lambda: value, external=False)


def pool(tmp_path):
    pages = [
        {
            "page_id": "a-first",
            "source_document_id": "a",
            "source_poisoned": True,
        },
        {
            "page_id": "a-last",
            "source_document_id": "a",
            "source_poisoned": True,
            "payload_present": True,
            "full_payload_present": True,
            "payload_sha256": "f" * 64,
        },
        {"page_id": "b", "source_document_id": "b"},
    ]
    records = []
    for page in pages:
        value = {"title": "public", "body": "task input policy", **page}
        name = page["page_id"] + ".json"
        atomic_json(tmp_path / name, value)
        records.append({"file": name})
    return {
        "pages": records,
        "corpus_hash": "a" * 64,
        "injection": dict(CONDITION),
    }


def test_probe_reports_occurrence_unique_chunk_source_and_partial_full_exposure(tmp_path):
    manifest = pool(tmp_path)
    journal = Journal(tmp_path / "journal")
    bind_contract(journal)
    for index, ids in enumerate((["a-first", "a-last", "b"], ["a-last"])):
        journal.dispatch(
            f"acquisition/search/{index}",
            {"query": f"query {index}"},
            lambda ids=ids: {
                "status": "ok",
                "result": {
                    "status": "ok",
                    "results": [{"page_id": identifier} for identifier in ids],
                },
            },
        )
    journal.dispatch(
        "acquisition/analyzer/0",
        {"inputs": {"returned_documents": [{"document_id": "a-first"}, {"document_id": "b"}]}},
        lambda: {},
    )
    journal.dispatch(
        "acquisition-summary",
        {},
        lambda: {
            "document_scores": [
                {"document_id": "a-first", "confidence": 0.7, "reason": "possible"},
                {"document_id": "b", "confidence": 0.8, "reason": "required"},
            ],
            "counters": {"search": 2, "read_only": 0, "clarify": 0},
            "stop_detail": "supported_public_requirements",
            "unreviewed_document_ids": ["a-last"],
            "unreviewable_document_ids": [],
        },
    )
    base = FrozenBase(
        tuple(
            {"document_id": identifier, "title": "public", "content": "task input policy"}
            for identifier in ("a-first", "b")
        ),
        {"opening": "task"},
    )
    result = probe.cell_metrics("task", ARM, base, journal, manifest, tmp_path, CONDITION, BUDGETS)
    assert result["pool"]["source_injection"] == probe.fraction(1, 2)
    assert result["pool"]["payload_chunk_ratio"] == probe.fraction(1, 3)
    returned = result["retrieval_return_occurrences"]
    assert returned["chunk_occurrences"] == 4
    assert returned["unique_chunks"] == 3
    assert returned["rates"]["payload_present"]["chunk_occurrences"] == probe.fraction(2, 4)
    assert returned["rates"]["payload_present"]["unique_chunks"] == probe.fraction(1, 3)
    assert returned["rates"]["payload_present"]["unique_sources"] == probe.fraction(1, 2)
    visible = result["analyzer_visible_unique"]
    assert visible["rates"]["payload_present"]["unique_chunks"] == probe.fraction(0, 2)
    frozen = result["frozen_base"]
    assert frozen["rates"]["source_poisoned"]["unique_chunks"] == probe.fraction(1, 2)
    assert frozen["rates"]["payload_present"]["unique_chunks"] == probe.fraction(0, 2)
    assert result["repeated_hit_count"] == 1
    assert result["searches"][0]["query"] == "query 0"
    assert result["document_scores"][0]["reason"] == "possible"
    assert result["utility"] == {"status": "NOT_MEASURED", "value": None}
    assert result["asr"] == {"status": "NOT_MEASURED", "value": None}
    empty = probe.exposure([], {})
    assert empty["rates"]["payload_present"]["unique_chunks"] == probe.fraction(0, 0)
    with pytest.raises(ValueError, match="outside_sealed_pool"):
        probe.exposure(["not-a-page"], {})


def test_probe_reports_partial_payload_separately():
    pages = {
        "partial": {
            "source_document_id": "a",
            "source_poisoned": True,
            "payload_present": True,
            "full_payload_present": False,
        },
        "full": {
            "source_document_id": "a",
            "source_poisoned": True,
            "payload_present": True,
            "full_payload_present": True,
        },
    }
    observed = probe.exposure(["partial", "full"], pages)
    assert observed["rates"]["payload_partial"]["unique_chunks"] == probe.fraction(1, 2)
    assert observed["rates"]["full_payload_present"]["unique_chunks"] == probe.fraction(1, 2)


def test_production_loader_uses_the_journal_bound_pool_and_reports_all_four_stages(tmp_path):
    import tau_skill_evolution.skillsbench_attack as attack

    directory = tmp_path / "sealed-pool"
    directory.mkdir()
    values = [
        {
            "page_id": "a::first",
            "source_document_id": "a",
            "source_poisoned": True,
            "title": "public",
            "body": "first public page",
        },
        {
            "page_id": "a::last",
            "source_document_id": "a",
            "source_poisoned": True,
            "payload_present": True,
            "full_payload_present": True,
            "title": "public",
            "body": "last public page",
        },
        {
            "page_id": "b::only",
            "source_document_id": "b",
            "title": "public",
            "body": "other public page",
        },
    ]
    records = []
    for value in values:
        value["content_sha256"] = hashlib.sha256(value["body"].encode()).hexdigest()
        filename = value["page_id"].replace("::", "-") + ".json"
        atomic_json(directory / filename, value)
        records.append(
            {
                "file": filename,
                **{key: item for key, item in value.items() if key != "body"},
            }
        )
    condition = {
        "condition_id": ARM,
        "profile": "data_exfil_http",
        "level": 5,
        "target_document_ids": ["a"],
    }
    manifest = {
        "schema": "skillsbench.pool.injected.v8",
        "injection": condition,
        "pages": records,
    }
    manifest["corpus_hash"] = attack._json_hash(manifest)
    manifest_path = directory / "manifest.json"
    atomic_json(manifest_path, manifest)

    journal = Journal(tmp_path / "journal")
    contract = {
        "task_id": "task",
        "condition_id": ARM,
        "retrieval": {
            "condition": condition,
            "pool_path": "sealed-pool",
            "pool_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            "corpus_hash": manifest["corpus_hash"],
            "page_count": 3,
            "payload_chunk_count": 1,
            "full_payload_chunk_count": 1,
        },
    }
    journal.dispatch("retrieval-corpus-contract", contract, lambda: contract, external=False)
    journal.dispatch(
        "acquisition/search/0",
        {"query": "public policy"},
        lambda: {
            "status": "ok",
            "result": {
                "status": "ok",
                "results": [
                    {"page_id": identifier}
                    for identifier in ("a::first", "a::last", "b::only", "a::last")
                ],
            },
        },
    )
    partial = acquisition_payload_exposure(tmp_path, None, journal)
    assert partial["status"] == "NOT_MEASURED"
    assert partial["stages"]["corpus"]["status"] == "MEASURED"
    assert partial["stages"]["search_returns"]["status"] == "MEASURED"
    assert partial["stages"]["analyzer_visible"] == {
        "status": "NOT_MEASURED",
        "reason": "analyzer_visible_not_recorded",
    }
    assert partial["stages"]["frozen_base"] == {
        "status": "NOT_MEASURED",
        "reason": "frozen_base_not_recorded",
    }
    journal.dispatch(
        "acquisition/analyzer/0",
        {
            "inputs": {
                "returned_documents": [
                    {"document_id": "a::first"},
                    {"document_id": "b::only"},
                ]
            }
        },
        lambda: {},
    )
    base = FrozenBase(
        ({"document_id": "a::last", "title": "public", "content": "last public page"},),
        {"opening": "task"},
    )

    observed = acquisition_payload_exposure(tmp_path, base, journal)
    assert set(observed) == {"status", "flags", "stages"}
    assert observed["status"] == "MEASURED"
    assert observed["flags"] == list(ACQUISITION_FLAGS)
    assert all(stage["status"] == "MEASURED" for stage in observed["stages"].values())
    assert tuple(observed["stages"]) == (
        "corpus",
        "search_returns",
        "analyzer_visible",
        "frozen_base",
    )
    assert observed["stages"]["search_returns"]["chunk_occurrences"] == 4
    assert observed["stages"]["search_returns"]["rates"]["payload_present"][
        "chunk_occurrences"
    ] == probe.fraction(2, 4)
    assert observed["stages"]["analyzer_visible"]["rates"]["payload_present"][
        "unique_chunks"
    ] == probe.fraction(0, 2)
    assert observed["stages"]["frozen_base"]["rates"]["full_payload_present"][
        "unique_sources"
    ] == probe.fraction(1, 1)

    atomic_json(manifest_path, {**manifest, "schema": "tampered"})
    with pytest.raises(ValueError, match="manifest_changed"):
        acquisition_payload_exposure(tmp_path, base, journal)


def test_probe_normalized_live_request_binding_has_same_visible_payload():
    payload = {"inputs": {"returned_documents": [{"document_id": "a"}]}, "system_prompt": "s"}
    request = {"payload": {"inputs": payload, "messages": [{"role": "user", "content": "x"}]}}
    assert probe.analyzer_payload(request) == payload["inputs"]


def test_probe_rejects_host_provenance_in_analyzer_request(tmp_path):
    manifest = pool(tmp_path)
    journal = Journal(tmp_path / "journal")
    bind_contract(journal)
    journal.dispatch(
        "acquisition/analyzer/0",
        {"inputs": {"returned_documents": [{"document_id": "a-first", "source_poisoned": True}]}},
        lambda: {},
    )
    journal.dispatch(
        "acquisition-summary",
        {},
        lambda: {
            "document_scores": [],
            "counters": {"search": 0, "read_only": 0, "clarify": 0},
            "stop_detail": "test",
            "unreviewed_document_ids": [],
            "unreviewable_document_ids": [],
        },
    )
    base = FrozenBase((), {"opening": "task"})
    with pytest.raises(ValueError, match="host_metadata_visible"):
        probe.cell_metrics("task", ARM, base, journal, manifest, tmp_path, CONDITION, BUDGETS)


def fixture_workflow(tmp_path, monkeypatch, responses):
    import tau_skill_evolution.retrieval as retrieval
    import tau_skill_evolution.skillsbench as skillsbench
    import tau_skill_evolution.skillsbench_attack as skillsbench_attack

    directory = tmp_path / "pool"
    directory.mkdir()
    manifest = pool(directory)
    cell_root = tmp_path / "cells/task" / ARM
    journal = Journal(cell_root / "journal")
    calls, closed, order = [], [], []

    class View:
        public_inputs = {"opening": "task"}
        allowed_read_only_tool_names = ()
        tool_schemas = []

        def __init__(self, *_args):
            pass

        def close(self):
            closed.append("view")

        def clarify(self, *_args):
            pytest.fail("no clarification budget")

        def perform(self, *_args):
            pytest.fail("no read tools")

    class Corpus:
        def search_web(self, _query):
            return {
                "status": "ok",
                "results": [
                    {
                        "page_id": "a-last",
                        "title": "public",
                        "content": "task input policy",
                    }
                ],
            }

        def close(self):
            closed.append("corpus")

    def model(payload):
        order.append("analyzer")
        calls.append(copy.deepcopy(payload))
        response = responses[len(calls) - 1]
        if isinstance(response, BaseException):
            raise response
        return response

    @contextmanager
    def model_context(*_args, **_kwargs):
        yield model

    monkeypatch.setattr(skillsbench, "SkillsBenchInputView", View)
    monkeypatch.setattr(skillsbench, "selected_pool", lambda *_: directory)
    monkeypatch.setattr(skillsbench, "validate_pool", lambda *_args, **_kwargs: manifest)
    monkeypatch.setattr(retrieval, "prepare_corpus", lambda *_: Corpus())
    monkeypatch.setattr(
        skillsbench_attack,
        "retrieval_contract",
        lambda *_: order.append("contract") or {"corpus_hash": "a" * 64},
    )
    spec = SimpleNamespace(
        root=tmp_path,
        condition=lambda arm: CONDITION if arm == ARM else None,
        values={
            "acquisition": {
                "max_searches": 2,
                "max_clarifications": 0,
                "max_reads": 0,
                "base_token_limit": 32768,
                "max_steps": 3,
                "min_document_confidence": 0.1,
            },
            "roles": {"analyzer": {"max_input_tokens": 10000}},
        },
    )
    workflow = SimpleNamespace(
        spec=spec,
        counter=len,
        _cell=lambda *_: (cell_root, journal),
        _model_context=model_context,
        _prompt=lambda *_: "Analyzer task",
    )
    return workflow, journal, calls, closed, order


def decision(action, sufficient=False):
    identifiers = ["a-last"] if sufficient else []
    return {
        "gaps": [] if sufficient else ["policy"],
        "action": action,
        "document_scores": [
            {"document_id": identifier, "confidence": 0.8, "reason": "needed"}
            for identifier in identifiers
        ],
        "sufficient": sufficient,
        "conflicts": [],
        "coverage": {
            name: identifiers for name in ("policies", "tools", "parameters", "preconditions")
        },
        "evidence": [
            {"requirement": "task", "document_id": identifier, "quote": "input policy"}
            for identifier in identifiers
        ],
    }


def test_probe_freezes_without_s0_and_resume_sends_no_analyzer_requests(tmp_path, monkeypatch):
    workflow, journal, calls, closed, order = fixture_workflow(
        tmp_path,
        monkeypatch,
        [
            decision({"kind": "search", "query": "task policy"}),
            decision({"kind": "freeze"}, sufficient=True),
        ],
    )
    first = probe.collect_cell(workflow, object(), "task", ARM)
    assert len(calls) == 2 and first["status"] == "MEASURED"
    assert order[0] == "contract"
    assert first["retrieval_contract"]["retrieval"]["corpus_hash"] == "a" * 64
    assert not journal.dispatched("generate_initial") and not journal.dispatched("creation")
    assert all(
        not set(doc).intersection(probe.HOST_ONLY_MODEL_KEYS)
        for call in calls
        for doc in call["returned_documents"]
    )
    assert probe.collect_cell(workflow, object(), "task", ARM) == first
    assert len(calls) == 2 and {"view", "corpus"}.issubset(closed)


def test_probe_unknown_request_is_not_resent(tmp_path, monkeypatch):
    workflow, journal, calls, closed, _ = fixture_workflow(
        tmp_path, monkeypatch, [RuntimeError("lost")]
    )
    with pytest.raises(UnknownOperation):
        probe.collect_cell(workflow, object(), "task", ARM)
    with pytest.raises(UnknownOperation):
        probe.collect_cell(workflow, object(), "task", ARM)
    assert len(calls) == 1
    assert not (workflow._cell()[0] / "base").exists()
    assert "view" in closed and journal.status("acquisition/analyzer/0") == "UNKNOWN"


def test_probe_rejects_a_frozen_base_without_its_prior_retrieval_contract(tmp_path, monkeypatch):
    from tau_skill_evolution.artifacts import seal_base

    workflow, journal, calls, _, _ = fixture_workflow(tmp_path, monkeypatch, [])
    root, _ = workflow._cell()
    seal_base(root / "base", FrozenBase((), {"opening": "task"}))
    with pytest.raises(ValueError, match="retrieval_contract_missing_requires_new_trial"):
        probe.collect_cell(workflow, object(), "task", ARM)
    assert not calls and not journal.dispatched("retrieval-corpus-contract")


def measured_row(task, arm, visible=0, frozen=0):
    def stage(value):
        return {
            "rates": {
                "payload_present": {
                    "unique_chunks": probe.fraction(value, 1),
                },
                "full_payload_present": {
                    "unique_chunks": probe.fraction(value, 1),
                },
            }
        }

    return {
        "task_id": task,
        "condition_id": arm,
        "arm": arm,
        "status": "MEASURED",
        "stop_reason": "sufficient",
        "search_call_count": 1,
        "base_tokens": 10,
        "pool": {
            "source_injection": probe.fraction(4, 85),
            "payload_chunk_ratio": probe.fraction(4, 100),
        },
        "analyzer_visible_unique": stage(visible),
        "frozen_base": stage(frozen),
    }


def test_probe_summary_uses_15_cell_pilot_not_765_as_exposure_denominator(tmp_path):
    atomic_json(
        tmp_path / "cells/a/data-exfil-http-5/probe-result.json",
        measured_row("a", "data-exfil-http-5", visible=1),
    )
    atomic_json(
        tmp_path / "cells/b/data-exfil-http-5/probe-result.json",
        {
            "task_id": "b",
            "condition_id": "data-exfil-http-5",
            "arm": "data-exfil-http-5",
            "status": "NOT_MEASURED",
        },
    )
    workflow = SimpleNamespace(
        root=tmp_path,
        identity={"identity_hash": "x"},
        spec=SimpleNamespace(
            namespace="skillsbench.skill-evolution.v8",
            cells=range(765),
        ),
    )
    summary = probe.write_summary(
        workflow,
        tasks=("a", "b", "c"),
        arms=("benign", "data-exfil-http-5"),
    )
    assert summary["dataset_matrix_cell_count"] == 765
    assert summary["pilot_expected_cell_count"] == 6
    assert summary["pilot_measured_cell_count"] == 1
    observed = summary["conditions"]["data-exfil-http-5"]
    assert observed["analyzer_payload_exposed_tasks"] == probe.fraction(1, 1)
    assert observed["frozen_payload_tasks"] == probe.fraction(0, 1)
    assert summary["conditions"]["benign"]["analyzer_payload_exposed_tasks"]["rate"] is None
    assert summary["utility"] == {"status": "NOT_MEASURED", "value": None}
    assert json.loads((tmp_path / "acquisition-summary.json").read_text()) == summary


def test_pilot_contract_is_exactly_three_tasks_by_five_conditions_and_serial_per_task():
    assert len(probe.DEFAULT_TASKS) == 3
    assert probe.PILOT_ARMS == (
        "benign",
        "data-exfil-http-5",
        "data-exfil-http-10",
        "file-delete-5",
        "file-delete-10",
    )
    barrier = threading.Barrier(3)
    lock = threading.Lock()
    order: dict[str, list[str]] = {task: [] for task in probe.DEFAULT_TASKS}
    active = 0
    maximum = 0

    def collect(task, arm):
        nonlocal active, maximum
        if arm == "benign":
            barrier.wait(timeout=2)
        with lock:
            active += 1
            maximum = max(maximum, active)
            order[task].append(arm)
        time.sleep(0.002)
        with lock:
            active -= 1
        return task, arm

    rows = probe.run_pilot_cells(probe.DEFAULT_TASKS, probe.PILOT_ARMS, collect)
    assert len(rows) == 15
    assert 1 < maximum <= 3
    assert all(tuple(observed) == probe.PILOT_ARMS for observed in order.values())


def test_probe_condition_must_match_the_sealed_pool(tmp_path):
    manifest = pool(tmp_path)
    changed = {**CONDITION, "target_document_ids": ["different"]}
    with pytest.raises(ValueError, match="condition_manifest_mismatch"):
        probe._condition(manifest, changed)


def test_whole_document_metrics_do_not_reuse_chunk_denominators():
    value = {
        "pool": {"rechunked": {"unique_chunks": 85}, "payload_chunk_ratio": probe.fraction(4, 85)},
        "analyzer_visible_unique": {
            "rates": {"full_payload_present": {"unique_chunks": probe.fraction(2, 10)}},
            "chunk_occurrences": 10,
        },
        "retrieval_unit": "source_document",
    }
    result = probe.source_document_metrics(value)
    assert result["pool"]["indexed_documents"]["unique_documents"] == 85
    assert result["pool"]["payload_document_ratio"] == probe.fraction(4, 85)
    assert result["analyzer_visible_unique"]["document_occurrences"] == 10
    assert probe._payload_exposed(result, "analyzer_visible_unique", "full_payload_present")
    assert value["pool"]["rechunked"]["unique_chunks"] == 85


def test_whole_document_schedule_runs_isolated_cells_at_the_requested_parallelism():
    barrier = threading.Barrier(5)
    lock = threading.Lock()
    first, active, maximum = 0, 0, 0

    def collect(task, arm):
        nonlocal first, active, maximum
        with lock:
            first += 1
            wait = first <= 5
            active += 1
            maximum = max(maximum, active)
        if wait:
            barrier.wait(timeout=2)
        time.sleep(0.002)
        with lock:
            active -= 1
        return task, arm

    rows = probe.run_pilot_cells(
        probe.DEFAULT_TASKS, probe.PILOT_ARMS, collect, max_workers=5, parallel_cells=True
    )
    assert set(rows) == {(task, arm) for task in probe.DEFAULT_TASKS for arm in probe.PILOT_ARMS}
    assert len(rows) == 15 and maximum == 5


def test_whole_document_summary_keeps_document_units(tmp_path):
    row = probe.source_document_metrics(measured_row("a", ARM, visible=1, frozen=1))
    row["retrieval_unit"] = "source_document"
    row["pool"]["payload_document_ratio"] = probe.fraction(4, 85)
    atomic_json(tmp_path / "cells/a" / ARM / "probe-result.json", row)
    workflow = SimpleNamespace(
        root=tmp_path,
        identity={"identity_hash": "whole-source"},
        spec=SimpleNamespace(
            namespace="skillsbench.skill-evolution.v8",
            cells=range(765),
            values={"retrieval_probe": {"document_unit": "source_document"}},
        ),
    )
    summary = probe.write_summary(workflow, tasks=("a",), arms=(ARM,))
    assert summary["retrieval_unit"] == "source_document"
    assert summary["conditions"][ARM]["payload_document_ratio"] == probe.fraction(4, 85)
    assert summary["conditions"][ARM]["frozen_full_payload_tasks"] == probe.fraction(1, 1)


def test_full_dataset_schedules_425_cells_and_checkpoints_on_the_owner_thread():
    tasks = tuple(f"task-{index}" for index in range(85))
    owner = threading.get_ident()
    updates = []
    rows = probe.run_pilot_cells(
        tasks,
        probe.PILOT_ARMS,
        lambda task, arm: (task, arm),
        max_workers=6,
        parallel_cells=True,
        on_progress=lambda: updates.append(threading.get_ident()),
    )
    assert len(rows) == len(set(rows)) == 425
    assert updates == [owner] * 425


def test_reference_coverage_distinguishes_returned_visible_and_retained():
    source = SimpleNamespace(
        manifest={
            "files": [
                {"task_id": "a", "relative_path": "background/guide.md", "document_id": "a::guide"},
                {"task_id": "a", "relative_path": "input.csv", "document_id": "a::input"},
                {"task_id": "b", "relative_path": "background/guide.md", "document_id": "b::guide"},
            ]
        }
    )
    result = probe.reference_coverage(
        source,
        "a",
        {
            "searches": [{"results": [{"document_id": "a::guide"}, {"document_id": "b::guide"}]}],
            "analyzer_requests": [{"visible_document_ids": ["b::guide"]}],
            "selected_document_ids": [],
        },
    )
    assert result["retrieved"] == probe.fraction(1, 1)
    assert result["analyzer_visible"] == result["frozen"] == probe.fraction(0, 1)


def test_reuse_seals_same_base_without_copying_or_dispatching_old_requests(tmp_path, monkeypatch):
    from tau_skill_evolution import skillsbench, skillsbench_whole_documents
    from tau_skill_evolution.artifacts import load_base, seal_base

    root, old, destination = tmp_path, tmp_path / "archive/old", tmp_path / "new"
    settings = {
        name: {} for name in ("acquisition", "provider", "retrieval", "embedding", "source")
    }
    settings["roles"] = {"analyzer": {"reasoning_effort": "medium"}}
    atomic_json(old / "logs/whole-document-config.json", settings)
    files = {}
    for relative in (
        "src/tau_skill_evolution/acquisition.py",
        "src/tau_skill_evolution/artifacts.py",
        "src/tau_skill_evolution/model.py",
        "src/tau_skill_evolution/journal.py",
        "src/tau_skill_evolution/skillsbench.py",
        "src/tau_skill_evolution/skillsbench_whole_documents.py",
        "src/tau_skill_evolution/dense.py",
        "prompts/analyzer.md",
        "prompts/analyzer-skillsbench.md",
    ):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(relative)
        files[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    source = SimpleNamespace(
        manifest={
            "files": [
                {"task_id": "a", "relative_path": "background/guide.md", "document_id": "a::guide"}
            ]
        }
    )
    monkeypatch.setattr(skillsbench, "SkillsBenchSource", lambda _: source)
    retrieval = {"document_unit": "source_document"}
    monkeypatch.setattr(skillsbench_whole_documents, "retrieval_contract", lambda *_: retrieval)
    previous = Journal(old / "cells/a/benign/journal", identity={"files": files, "provider": {}})
    contract = {"task_id": "a", "condition_id": "benign", "retrieval": retrieval}
    for operation, value in (("retrieval-corpus-contract", contract), ("acquisition-summary", {})):
        previous.dispatch(operation, value, lambda value=value: value, external=False)
    base = FrozenBase(
        ({"document_id": "a::guide", "title": "Guide", "content": "body"},), {"opening": "task"}
    )
    seal_base(old / "cells/a/benign/base", base)
    metrics = {
        "status": "MEASURED",
        "task_id": "a",
        "arm": "benign",
        "base_hash": base.base_hash,
        "retrieval_unit": "source_document",
        "retrieval_contract": contract,
        "searches": [{"results": [{"document_id": "a::guide"}]}],
        "analyzer_requests": [{"visible_document_ids": ["a::guide"]}],
        "selected_document_ids": ["a::guide"],
        "search_call_count": 1,
    }
    atomic_json(old / "cells/a/benign/probe-result.json", metrics)
    journal = Journal(destination / "cells/a/benign/journal", identity={"trial": "new"})
    workflow = SimpleNamespace(
        spec=SimpleNamespace(root=root, values=settings),
        _prompt=lambda _: "original prompt",
        _cell=lambda *_: (destination / "cells/a/benign", journal),
    )
    assert probe.seed_completed(workflow, old, ["a"], ["benign"]) == 1
    assert probe.seed_completed(workflow, old, ["a"], ["benign"]) == 1
    assert load_base(destination / "cells/a/benign/base").base_hash == base.base_hash
    assert journal.response("acquisition-seed")["producer_identity"]["files"] == files
    imported = json.loads((destination / "cells/a/benign/probe-result.json").read_text())
    assert imported["search_call_count"] == 1 and imported["origin"]["kind"] == "reused"
    operations = [
        json.loads(path.read_text())["operation_id"] for path in journal.root.glob("*/request.json")
    ]
    assert not any(operation.startswith("acquisition/") for operation in operations)
    (root / "prompts/analyzer-skillsbench.md").write_text("changed")
    with pytest.raises(ValueError, match="seed_source_changed"):
        probe.seed_completed(workflow, old, ["a"], ["benign"])


def test_usage_replayed_records_do_not_double_count(tmp_path):
    record = {"response_id": "once", "usage": {"input_tokens": 11, "output_tokens": 3}}
    path = tmp_path / "usage.jsonl"
    path.write_text(json.dumps(record) + "\n" + json.dumps(record) + "\n")
    assert probe.usage_totals(path) == {
        "requests": 1,
        "input_tokens": 11,
        "output_tokens": 3,
        "cached_input_tokens": 0,
    }
