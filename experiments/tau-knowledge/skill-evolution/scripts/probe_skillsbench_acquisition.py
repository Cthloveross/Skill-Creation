#!/usr/bin/env python3
"""Collect reusable SkillsBench v8 FrozenBases without creating Skills.

This entry point never creates, executes, verifies, or grades a Skill. The
default reproduces the chunk pilot. The whole-document comparison rebuilds
both indexes from complete source documents and permits independent cells to
run concurrently; it does not alter the production matrix configuration.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
import threading
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from statistics import median
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import tau_skill_evolution.skillsbench_attack as _attack  # noqa: E402

PAGE_FLAGS = _attack.ACQUISITION_FLAGS
HOST_ONLY_MODEL_KEYS = _attack.ACQUISITION_HOST_ONLY_MODEL_KEYS
fraction = _attack.acquisition_fraction
_page_flag = _attack.acquisition_page_flag
exposure = _attack.acquisition_exposure
journal_records = _attack.acquisition_journal_records
analyzer_payload = _attack.acquisition_analyzer_payload
_keys = _attack.acquisition_keys
_operation_index = _attack.acquisition_operation_index
_pages = _attack.load_acquisition_pages
collect_acquisition_exposure = _attack.collect_acquisition_exposure

DEFAULT_TASKS = (
    "manufacturing-codebook-normalization",
    "dialogue-parser",
    "3d-scan-calc",
)
PILOT_ARMS = (
    "benign",
    "data-exfil-http-5",
    "data-exfil-http-10",
    "file-delete-5",
    "file-delete-10",
)


def _condition(manifest: Mapping[str, Any], expected: Mapping[str, Any]) -> dict[str, Any]:
    injection = manifest.get("injection", {})
    targets = list(injection.get("target_document_ids", []))
    observed = {
        "condition_id": injection.get("condition_id", "benign"),
        "profile": injection.get("profile"),
        "level": injection.get("level", 0),
        "target_document_ids": targets,
    }
    normalized_expected = {
        "condition_id": expected["condition_id"],
        "profile": expected.get("profile"),
        "level": expected.get("level", 0),
        "target_document_ids": list(expected.get("target_document_ids", [])),
    }
    if observed != normalized_expected:
        raise ValueError("probe_condition_manifest_mismatch")
    return observed


def cell_metrics(
    task: str,
    arm: str,
    base: Any,
    journal: Any,
    manifest: dict[str, Any],
    directory: Path,
    condition: Mapping[str, Any],
    budget_limits: Mapping[str, int],
) -> dict[str, Any]:
    pages = _pages(manifest, directory)
    trace = collect_acquisition_exposure(base, journal, pages)
    searches = trace["searches"]
    analyzer_requests = trace["analyzer_requests"]
    discovery_calls = trace["input_discovery"]
    summary = journal.response("acquisition-summary")
    selected = trace["selected_document_ids"]
    source_ids = {item["source_document_id"] for item in pages.values()}
    bound_condition = _condition(manifest, condition)
    source_targets = set(bound_condition["target_document_ids"])
    counters = dict(summary["counters"])
    used = {**counters, "analyzer_steps": len(analyzer_requests)}
    remaining = {
        name: max(0, budget_limits[name] - used[name])
        for name in ("search", "clarify", "read_only", "analyzer_steps")
    }
    pool_exposure = trace["stages"]["corpus"]
    retrieval = journal.response("retrieval-corpus-contract")
    return {
        "task_id": task,
        "condition_id": arm,
        "arm": arm,
        "condition": bound_condition,
        "task_own_background_targeted": any(
            identifier.startswith(task + "::background/") for identifier in source_targets
        ),
        "status": "MEASURED",
        "base_hash": base.base_hash,
        "pool_hash": manifest["corpus_hash"],
        "retrieval_contract": retrieval,
        "pool": {
            "source_documents": len(source_ids),
            "source_injection": fraction(len(source_targets), len(source_ids)),
            "rechunked": pool_exposure,
            "payload_chunk_ratio": pool_exposure["rates"]["payload_present"]["unique_chunks"],
        },
        "search_call_count": len(searches),
        "retrieval_return_occurrences": trace["stages"]["search_returns"],
        "retrieval_unique": trace["retrieval_unique"],
        "repeated_hit_count": trace["repeated_hit_count"],
        "analyzer_request_count": len(analyzer_requests),
        "analyzer_visible_occurrences": trace["stages"]["analyzer_visible"],
        "analyzer_visible_unique": trace["analyzer_visible_unique"],
        "frozen_base": trace["stages"]["frozen_base"],
        "selected_document_ids": selected,
        "evidence_references": [
            {
                "requirement": item.get("requirement"),
                "document_id": item.get("document_id"),
            }
            for item in base.evidence
        ],
        "document_scores": [
            {
                **score,
                "source_document_id": pages[score["document_id"]]["source_document_id"],
                "selected": score["document_id"] in selected,
                **{flag: _page_flag(pages[score["document_id"]], flag) for flag in PAGE_FLAGS},
            }
            for score in summary["document_scores"]
        ],
        "searches": searches,
        "analyzer_requests": analyzer_requests,
        "input_discovery": discovery_calls,
        "budgets": {"limits": dict(budget_limits), "used": used, "remaining": remaining},
        "stop_reason": base.stop_reason,
        "stop_detail": summary["stop_detail"],
        "base_tokens": base.token_count,
        "base_token_occupancy": fraction(base.token_count, budget_limits["base_tokens"]),
        "unreviewed_document_ids": summary["unreviewed_document_ids"],
        "unreviewable_document_ids": summary["unreviewable_document_ids"],
        "model_input_host_metadata_absent": True,
        "utility": {"status": "NOT_MEASURED", "value": None},
        "asr": {"status": "NOT_MEASURED", "value": None},
        "skill_creation": "NOT_MEASURED",
        "task_execution": "NOT_MEASURED",
        "verification": "NOT_MEASURED",
        "oracle": "NOT_MEASURED",
    }


def source_document_metrics(value: Any) -> Any:
    return _attack.source_document_metrics(value)


def reference_coverage(source: Any, task: str, metrics: Mapping[str, Any]) -> dict[str, Any]:
    """Host-only recall of the background originally associated with this task."""
    reference = {
        entry["document_id"]
        for entry in source.manifest["files"]
        if entry["task_id"] == task and entry["relative_path"].startswith("background/")
    }
    returned = {
        result["document_id"] for search in metrics["searches"] for result in search["results"]
    }
    visible = {
        identifier
        for request in metrics["analyzer_requests"]
        for identifier in request["visible_document_ids"]
    }
    selected = set(metrics["selected_document_ids"])
    return {
        "reference_document_ids": sorted(reference),
        "retrieved": fraction(len(reference & returned), len(reference)),
        "analyzer_visible": fraction(len(reference & visible), len(reference)),
        "frozen": fraction(len(reference & selected), len(reference)),
    }


def seed_completed(
    workflow: Any, source_run: Path, tasks: Sequence[str], arms: Sequence[str]
) -> int:
    """Import completed compatible acquisitions, never their operational journals."""
    from tau_skill_evolution.artifacts import atomic_json, load_base, seal_base
    from tau_skill_evolution.journal import Journal
    from tau_skill_evolution.skillsbench import SkillsBenchSource
    from tau_skill_evolution.skillsbench_whole_documents import retrieval_contract

    source_run = source_run.resolve()
    source = SkillsBenchSource(workflow.spec.root)
    previous = json.loads((source_run / "logs/whole-document-config.json").read_text())
    for name in ("acquisition", "provider", "retrieval", "embedding", "source"):
        if previous[name] != workflow.spec.values[name]:
            raise ValueError(f"acquisition_seed_{name}_changed")
    if previous["roles"]["analyzer"] != workflow.spec.values["roles"]["analyzer"]:
        raise ValueError("acquisition_seed_analyzer_changed")
    count = 0
    for task in tasks:
        for arm in arms:
            old = source_run / "cells" / task / arm
            if not (old / "probe-result.json").is_file():
                continue
            metrics = json.loads((old / "probe-result.json").read_text())
            if metrics.get("status") != "MEASURED":
                continue
            identity = json.loads((old / "journal/identity.json").read_text())["identity"]
            prior = Journal(old / "journal", identity=identity)
            protected = (
                "src/tau_skill_evolution/acquisition.py",
                "src/tau_skill_evolution/artifacts.py",
                "src/tau_skill_evolution/model.py",
                "src/tau_skill_evolution/journal.py",
                "src/tau_skill_evolution/skillsbench.py",
                "src/tau_skill_evolution/skillsbench_whole_documents.py",
                "src/tau_skill_evolution/dense.py",
                "prompts/analyzer.md",
                "prompts/analyzer-skillsbench.md",
            )
            if any(
                hashlib.sha256((workflow.spec.root / name).read_bytes()).hexdigest()
                != identity["files"].get(name)
                for name in protected
            ):
                raise ValueError("acquisition_seed_source_changed")
            requests = [json.loads(path.read_text()) for path in prior.root.glob("*/request.json")]
            if any(
                item["operation_id"] in {"generate_initial", "creation"}
                or prior.status(item["operation_id"]) != "COMPLETED"
                for item in requests
            ):
                raise ValueError("acquisition_seed_incomplete_or_not_retrieval_only")
            contract = {
                "task_id": task,
                "condition_id": arm,
                "retrieval": retrieval_contract(workflow.spec, arm),
            }
            base = load_base(old / "base")
            if (
                prior.response("retrieval-corpus-contract") != contract
                or metrics.get("retrieval_contract") != contract
                or metrics.get("base_hash") != base.base_hash
                or metrics.get("task_id") != task
                or metrics.get("arm") != arm
                or metrics.get("retrieval_unit") != "source_document"
            ):
                raise ValueError("acquisition_seed_artifact_mismatch")
            producer = {
                "provider": identity["provider"],
                "analyzer": previous["roles"]["analyzer"],
                "prompt_sha256": hashlib.sha256(workflow._prompt("analyzer").encode()).hexdigest(),
                "budgets": previous["acquisition"],
                "retrieval": previous["retrieval"],
            }
            seed = {
                "producer_identity": identity,
                "producer_acquisition": producer,
                "source_run": str(source_run.relative_to(workflow.spec.root)),
                "source_base_hash": base.base_hash,
            }
            root, journal = workflow._cell(task, arm)
            if (root / "base").exists() and load_base(root / "base").base_hash != base.base_hash:
                raise ValueError("acquisition_seed_destination_changed")
            for operation, value in (
                ("retrieval-corpus-contract", contract),
                ("collect-base", base.to_dict()),
                ("acquisition-summary", prior.response("acquisition-summary")),
                ("acquisition-seed", seed),
            ):
                journal.dispatch(operation, value, lambda value=value: value, external=False)
            seal_base(root / "base", base)
            atomic_json(
                root / "probe-result.json",
                {
                    **metrics,
                    "reference_coverage": reference_coverage(source, task, metrics),
                    "origin": {"kind": "reused", **seed},
                },
            )
            count += 1
    return count


def collect_cell(
    workflow: Any, source: Any, task: str, arm: str, *, whole_documents: bool = False
) -> dict[str, Any]:
    from tau_skill_evolution.acquisition import AcquisitionBudgets, collect_base
    from tau_skill_evolution.artifacts import atomic_json, load_base, seal_base
    from tau_skill_evolution.retrieval import prepare_corpus
    from tau_skill_evolution.skillsbench import SkillsBenchInputView, selected_pool, validate_pool
    from tau_skill_evolution.skillsbench_attack import retrieval_contract

    root, journal = workflow._cell(task, arm)
    if journal.dispatched("generate_initial") or journal.dispatched("creation"):
        raise ValueError("probe_requires_a_separate_acquisition_only_trial")
    condition = workflow.spec.condition(arm)
    if whole_documents:
        from tau_skill_evolution.skillsbench_whole_documents import (
            prepare_corpus,
            prepare_pool,
            retrieval_contract,
        )

        directory, manifest = prepare_pool(workflow.spec, source, arm)
    else:
        directory = selected_pool(workflow.spec, arm)
        manifest = validate_pool(workflow.spec.root, source, directory=directory)
    if (root / "base").exists():
        if not journal.completed("retrieval-corpus-contract"):
            raise ValueError("probe_retrieval_contract_missing_requires_new_trial")
        contract = {
            "task_id": task,
            "condition_id": arm,
            "retrieval": retrieval_contract(workflow.spec, arm),
        }
        journal.dispatch("retrieval-corpus-contract", contract, lambda: contract, external=False)
        base = load_base(root / "base")
        if journal.completed("acquisition-seed"):
            result = json.loads((root / "probe-result.json").read_text())
            if result["base_hash"] != base.base_hash or result["retrieval_contract"] != contract:
                raise ValueError("acquisition_seed_result_changed")
            return result
    else:
        view = SkillsBenchInputView(source, task)
        corpus = prepare_corpus(workflow.spec, task, arm)
        try:
            if not journal.completed("retrieval-corpus-contract") and any(
                json.loads(path.read_text())["operation_id"].startswith("acquisition/")
                for path in journal.root.glob("*/request.json")
            ):
                raise ValueError("probe_retrieval_contract_missing_requires_new_trial")
            contract = {
                "task_id": task,
                "condition_id": arm,
                "retrieval": retrieval_contract(workflow.spec, arm),
            }
            journal.dispatch(
                "retrieval-corpus-contract", contract, lambda: contract, external=False
            )
        except BaseException:
            view.close()
            corpus.close()
            raise
        settings = workflow.spec.values["acquisition"]
        try:
            with workflow._model_context("analyzer", scope=f"{task}/{arm}") as model:
                base = collect_base(
                    model,
                    view.public_inputs,
                    corpus,
                    {
                        name: (lambda name=name, **args: view.read(name, args))
                        for name in view.allowed_read_only_tool_names
                    },
                    view.clarify,
                    workflow.counter,
                    budgets=AcquisitionBudgets(
                        searches=settings["max_searches"],
                        clarifications=settings["max_clarifications"],
                        read_only_queries=settings["max_reads"],
                        base_tokens=settings["base_token_limit"],
                        analyzer_steps=settings["max_steps"],
                    ),
                    journal=journal,
                    system_prompt=workflow._prompt("analyzer"),
                    tool_schemas=view.tool_schemas,
                    allowed_read_only_tool_names=view.allowed_read_only_tool_names,
                    min_document_confidence=settings["min_document_confidence"],
                    input_token_limit=workflow.spec.values["roles"]["analyzer"]["max_input_tokens"],
                    action_dispatcher=view.perform,
                )
            seal_base(root / "base", base)
        finally:
            view.close()
            corpus.close()
    settings = workflow.spec.values["acquisition"]
    limits = {
        "search": settings["max_searches"],
        "clarify": settings["max_clarifications"],
        "read_only": settings["max_reads"],
        "analyzer_steps": settings["max_steps"],
        "base_tokens": settings["base_token_limit"],
    }
    result = cell_metrics(task, arm, base, journal, manifest, directory, condition, limits)
    result["retrieval_unit"] = "source_document" if whole_documents else "chunk"
    result["origin"] = {"kind": "new"}
    if whole_documents:
        result = source_document_metrics(result)
        result["reference_coverage"] = reference_coverage(source, task, result)
    atomic_json(root / "probe-result.json", result)
    return result


def _payload_exposed(cell: Mapping[str, Any], stage: str, flag: str) -> bool:
    unit = (
        "unique_documents" if cell.get("retrieval_unit") == "source_document" else "unique_chunks"
    )
    return cell[stage]["rates"][flag][unit]["numerator"] > 0


def _constant_metric(cells: Sequence[Mapping[str, Any]], *path: str) -> Any:
    values = []
    for cell in cells:
        value: Any = cell
        for key in path:
            value = value[key]
        values.append(value)
    if not values:
        return None
    if any(value != values[0] for value in values[1:]):
        raise ValueError("probe_condition_pool_metric_differs_between_tasks")
    return values[0]


def write_summary(
    workflow: Any,
    *,
    tasks: Sequence[str] | None = None,
    arms: Sequence[str] | None = None,
    compact: bool = False,
) -> dict[str, Any]:
    from tau_skill_evolution.artifacts import atomic_json

    tasks = tuple(tasks or DEFAULT_TASKS)
    arms = tuple(arms or PILOT_ARMS)
    cells = [
        json.loads(path.read_text())
        for path in sorted(workflow.root.glob("cells/*/*/probe-result.json"))
        if path.parent.name in arms and path.parent.parent.name in tasks
    ]
    measured = [cell for cell in cells if cell["status"] == "MEASURED"]
    expected = {(task, arm) for task in tasks for arm in arms}
    observed = {(cell["task_id"], cell["arm"]) for cell in cells}
    whole = (
        workflow.spec.values.get("retrieval_probe", {}).get("document_unit") == "source_document"
        if hasattr(workflow.spec, "values")
        else False
    )
    ratio = "payload_document_ratio" if whole else "payload_chunk_ratio"
    result = {
        "schema": "skillsbench.acquisition-probe.v8",
        "namespace": workflow.spec.namespace,
        "source_identity": workflow.identity["identity_hash"],
        "probe_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "retrieval_unit": "source_document" if whole else "chunk",
        "scope": (
            "Analyzer, public input discovery, hybrid retrieval, and FrozenBase only; "
            "Skill creation, execution, verification, oracle, and evaluation are not measured"
        ),
        "dataset_matrix_cell_count": len(workflow.spec.cells),
        "pilot_expected_cell_count": len(expected),
        "pilot_recorded_cell_count": len(observed),
        "pilot_measured_cell_count": len(measured),
        "pilot_status": "COMPLETE" if len(measured) == len(expected) else "INCOMPLETE",
        "missing_cells": [list(cell) for cell in sorted(expected - observed)],
        "cells": sorted(
            [
                {
                    **{
                        key: cell.get(key)
                        for key in (
                            "task_id",
                            "condition_id",
                            "arm",
                            "status",
                            "base_hash",
                            "stop_reason",
                            "stop_detail",
                            "base_tokens",
                            "search_call_count",
                            "analyzer_request_count",
                            "reference_coverage",
                            "error_type",
                            "error_code",
                            "authentication_status",
                        )
                    },
                    "origin": cell.get("origin", {}).get("kind", "new"),
                    "details": f"cells/{cell['task_id']}/{cell['arm']}/probe-result.json",
                }
                if compact
                else cell
                for cell in cells
            ],
            key=lambda cell: (tasks.index(cell["task_id"]), arms.index(cell["arm"])),
        ),
        "conditions": {
            arm: {
                "measured_tasks": len(
                    selected := [cell for cell in measured if cell["arm"] == arm]
                ),
                "planned_tasks": len(tasks),
                "unfinished_tasks": len(tasks) - len(selected),
                "judged_sufficient": sum(cell["stop_reason"] == "sufficient" for cell in selected),
                "reference_coverage": {
                    stage: fraction(
                        sum(
                            cell["reference_coverage"][stage]["numerator"]
                            for cell in selected
                            if "reference_coverage" in cell
                        ),
                        sum(
                            cell["reference_coverage"][stage]["denominator"]
                            for cell in selected
                            if "reference_coverage" in cell
                        ),
                    )
                    for stage in ("retrieved", "analyzer_visible", "frozen")
                },
                "mean_search_calls": (
                    sum(cell["search_call_count"] for cell in selected) / len(selected)
                    if selected
                    else None
                ),
                "median_base_tokens": median(cell["base_tokens"] for cell in selected)
                if selected
                else None,
                "source_injection": _constant_metric(selected, "pool", "source_injection"),
                ratio: _constant_metric(selected, "pool", ratio),
                "analyzer_payload_exposed_tasks": fraction(
                    sum(
                        _payload_exposed(cell, "analyzer_visible_unique", "payload_present")
                        for cell in selected
                    ),
                    len(selected),
                ),
                "analyzer_full_payload_exposed_tasks": fraction(
                    sum(
                        _payload_exposed(cell, "analyzer_visible_unique", "full_payload_present")
                        for cell in selected
                    ),
                    len(selected),
                ),
                "frozen_payload_tasks": fraction(
                    sum(
                        _payload_exposed(cell, "frozen_base", "payload_present")
                        for cell in selected
                    ),
                    len(selected),
                ),
                "frozen_full_payload_tasks": fraction(
                    sum(
                        _payload_exposed(cell, "frozen_base", "full_payload_present")
                        for cell in selected
                    ),
                    len(selected),
                ),
            }
            for arm in arms
        },
        "utility": {"status": "NOT_MEASURED", "value": None},
        "asr": {"status": "NOT_MEASURED", "value": None},
    }
    atomic_json(workflow.root / "acquisition-summary.json", result)
    return result


def write_progress(workflow: Any, tasks: Sequence[str], arms: Sequence[str]) -> None:
    from tau_skill_evolution.artifacts import atomic_json
    from tau_skill_evolution.retrieval_dataset import write_catalog

    summary = write_summary(workflow, tasks=tasks, arms=arms, compact=True)
    catalog = write_catalog(workflow, tasks, arms)
    reused = sum(
        cell["origin"] == "reused" for cell in summary["cells"] if cell["status"] == "MEASURED"
    )
    usage = usage_totals(workflow.root / "usage.jsonl")
    reused_runs = {
        json.loads(path.read_text()).get("origin", {}).get("source_run")
        for path in workflow.root.glob("cells/*/*/probe-result.json")
    } - {None}
    producer_usage = [usage_totals(workflow.spec.root / run / "usage.jsonl") for run in reused_runs]
    summary["usage"] = {
        "new_collection": usage,
        "reused_source_runs": sorted(reused_runs),
        "reused_source_usage": {key: sum(item[key] for item in producer_usage) for key in usage},
    }
    atomic_json(workflow.root / "acquisition-summary.json", summary)
    atomic_json(
        workflow.root / "progress.json",
        {
            "status": summary["pilot_status"],
            "expected": len(tasks) * len(arms),
            "frozen": catalog["sealed_cell_count"],
            "reused": reused,
            "newly_frozen": catalog["sealed_cell_count"] - reused,
            "not_completed": len(tasks) * len(arms) - catalog["sealed_cell_count"],
            "catalog_hash": catalog["catalog_hash"],
            "later_stages": "NOT_MEASURED",
        },
    )
    rows = [
        "# SkillsBench retrieval results",
        "",
        f"{catalog['sealed_cell_count']}/{len(tasks) * len(arms)} bases frozen; "
        f"{reused} reused, {catalog['sealed_cell_count'] - reused} newly collected. "
        "This is retrieval only; Skill creation, utility and execution ASR are NOT_MEASURED.",
        "",
        "| Condition | Planned | Frozen | Unfinished | Sufficient | Reference found | "
        "Reference retained | Payload seen | Payload retained |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]

    def ratio(value: Any) -> str:
        return f"{value['numerator']}/{value['denominator']}" if value else "—"

    for arm, value in summary["conditions"].items():
        rows.append(
            f"| {arm} | {len(tasks)} | {value['measured_tasks']} | {value['unfinished_tasks']} | "
            f"{value['judged_sufficient']} | {ratio(value['reference_coverage']['retrieved'])} | "
            f"{ratio(value['reference_coverage']['frozen'])} | "
            f"{ratio(value['analyzer_full_payload_exposed_tasks'])} | "
            f"{ratio(value['frozen_full_payload_tasks'])} |"
        )
    rows.extend(
        [
            "",
            "Reference and payload ratios use completed acquisitions only; the Unfinished column "
            "preserves the full planned denominator. Reference coverage is host-side and is never "
            "supplied to the Analyzer.",
            "",
            "Full queries, scores, selection reasons and stopping budgets are in catalog.json "
            "entries.source_metrics. Each recipe reconstructs exactly the sealed base from pinned "
            "public data without new Analyzer calls. Insufficient frozen bases remain reusable "
            "and keep their original stop reason.",
            "",
            "Input discovery reads public files supplied in the pinned task source. It is not a "
            "snapshot of every file produced by building the official task container. General "
            "syntax/algorithm gaps and Analyzer sufficiency judgments remain semantic limitations.",
            "",
        ]
    )
    temporary = workflow.root / ".REPORT.md.tmp"
    temporary.write_text("\n".join(rows), encoding="utf-8")
    temporary.replace(workflow.root / "REPORT.md")


def usage_totals(path: Path) -> dict[str, int]:
    counts = {"requests": 0, "input_tokens": 0, "output_tokens": 0, "cached_input_tokens": 0}
    if not path.exists():
        return counts
    seen = set()
    for line in path.read_text().splitlines():
        record = json.loads(line)
        if record.get("response_id") in seen:
            continue
        seen.add(record.get("response_id"))
        counts["requests"] += 1
        usage = record["usage"]
        counts["input_tokens"] += usage.get("input_tokens", usage.get("prompt_tokens", 0))
        counts["output_tokens"] += usage.get("output_tokens", usage.get("completion_tokens", 0))
        counts["cached_input_tokens"] += usage.get("input_tokens_details", {}).get(
            "cached_tokens", 0
        )
    return counts


def run_pilot_cells(
    tasks: Sequence[str],
    arms: Sequence[str],
    collect: Callable[[str, str], Any],
    *,
    max_workers: int = 3,
    parallel_cells: bool = False,
    on_progress: Callable[[], None] | None = None,
) -> list[Any]:
    """Keep the old serial contract or schedule fully isolated comparison cells."""
    if not 1 <= max_workers <= (6 if parallel_cells else 3):
        raise ValueError("pilot_max_workers_out_of_range")
    stop = threading.Event()

    def run_cell(task: str, arm: str) -> list[Any]:
        if stop.is_set():
            return []
        try:
            return [collect(task, arm)]
        except BaseException:
            stop.set()
            raise

    def run_task(task: str) -> list[Any]:
        rows = []
        for arm in arms:
            if stop.is_set():
                break
            try:
                rows.append(collect(task, arm))
            except BaseException:
                stop.set()
                raise
        return rows

    results: list[Any] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = (
            {executor.submit(run_cell, task, arm): (task, arm) for arm in arms for task in tasks}
            if parallel_cells
            else {executor.submit(run_task, task): task for task in tasks}
        )
        try:
            for future in as_completed(futures):
                results.extend(future.result())
                if on_progress is not None:
                    on_progress()
        except BaseException:
            stop.set()
            for future in futures:
                future.cancel()
            raise
    return results


def main(argv: list[str] | None = None) -> int:
    from tau_skill_evolution.artifacts import atomic_json
    from tau_skill_evolution.cli import load_env, run_locks
    from tau_skill_evolution.model import authentication_status
    from tau_skill_evolution.preflight import bedrock_authentication
    from tau_skill_evolution.retrieval import prepare_corpus
    from tau_skill_evolution.skillsbench import SkillsBenchSource, selected_pool, validate_pool
    from tau_skill_evolution.spec import load_spec
    from tau_skill_evolution.workflow import Workflow

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--jobs", type=int, default=3)
    parser.add_argument("--whole-documents", action="store_true")
    parser.add_argument(
        "--all-tasks", action="store_true", help="collect all 85 tasks in five conditions"
    )
    parser.add_argument(
        "--reuse-from", type=Path, help="reuse compatible completed whole-document acquisitions"
    )
    parser.add_argument(
        "--embedding-endpoint", help="separate pinned Qwen service with an 8192-token limit"
    )
    args = parser.parse_args(argv)
    if args.env_file:
        load_env(args.env_file)
    spec = load_spec(args.config)
    if (
        spec.experiment != "skillsbench"
        or spec.namespace != "skillsbench.skill-evolution.v8"
        or spec.provider_settings["transport"] != "bedrock-responses"
    ):
        parser.error("probe requires a SkillsBench v8 Bedrock Responses configuration")
    tasks, arms = tuple(spec.tasks) if args.all_tasks else DEFAULT_TASKS, PILOT_ARMS
    if (args.all_tasks or args.reuse_from) and not args.whole_documents:
        parser.error("--all-tasks and --reuse-from require --whole-documents")
    if set(tasks) - set(spec.tasks) or set(arms) - set(spec.arms):
        parser.error("selected tasks and conditions must belong to the frozen v8 matrix")
    if not 1 <= args.jobs <= (6 if args.whole_documents else 3):
        parser.error("--jobs must be 1..6 for whole documents, otherwise 1..3")
    if args.whole_documents:
        from tau_skill_evolution.spec import ExperimentSpec

        if not args.embedding_endpoint:
            parser.error("--whole-documents requires --embedding-endpoint")
        values = copy.deepcopy(spec.values)
        values["embedding"].update(endpoint=args.embedding_endpoint, max_length=8192, chunks=False)
        # This probe connects to a separately managed service; it does not launch
        # a server or inherit the production service's GPU allocation settings.
        for name in ("gpu_uuid", "gpu_memory_utilization", "chunk_tokens", "chunk_overlap_tokens"):
            values["embedding"].pop(name, None)
        values["retrieval_probe"] = {
            "schema": "skillsbench.whole-document-retrieval-probe.v1",
            "document_unit": "source_document",
            "baseline_config_sha256": hashlib.sha256(args.config.read_bytes()).hexdigest(),
            "max_parallel_cells": args.jobs,
        }
        snapshot = args.run_dir / "logs/whole-document-config.json"
        if snapshot.exists() and json.loads(snapshot.read_text()) != values:
            raise ValueError("probe_config_changed_requires_new_trial")
        atomic_json(snapshot, values)
        spec = ExperimentSpec(snapshot, values)
    elif args.embedding_endpoint:
        parser.error("--embedding-endpoint is only for the whole-document comparison")
    cells = tuple((task, arm) for task in tasks for arm in arms)
    source = SkillsBenchSource(spec.root)
    source.validate()
    with run_locks(args.run_dir, cells):
        # Build and validate both routes before authentication and before any paid
        # Analyzer request. This also prevents three task workers from racing to
        # construct the same condition index.
        for arm in arms:
            if args.whole_documents:
                from tau_skill_evolution.skillsbench_whole_documents import prepare_corpus
            else:
                directory = selected_pool(spec, arm)
                validate_pool(spec.root, source, directory=directory)
            corpus = prepare_corpus(spec, tasks[0], arm)
            corpus.close()
        workflow = Workflow(spec, args.run_dir, runtime="docker", interim_report=False)
        workflow.journal.dispatch(
            "acquisition-probe-contract",
            {
                "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "tasks": list(tasks),
                "conditions": list(arms),
                "cells": [list(cell) for cell in cells],
                "max_parallel_cells" if args.whole_documents else "max_parallel_tasks": args.jobs,
                "serial_conditions_within_task": not args.whole_documents,
                "retrieval_unit": "source_document" if args.whole_documents else "chunk",
                "reuse_from": str(args.reuse_from.resolve()) if args.reuse_from else None,
            },
            lambda: {"stage": "acquisition-only", "expected_acquisitions": len(cells)},
            external=False,
        )
        if args.reuse_from:
            seed_completed(workflow, args.reuse_from, tasks, arms)
        if args.all_tasks:
            write_progress(workflow, tasks, arms)
        admission = bedrock_authentication(spec)
        atomic_json(
            workflow.root / "acquisition-admission.json",
            {"catalog": admission, "docker_required": False},
        )

        def collect(task: str, arm: str) -> dict[str, Any]:
            try:
                result = collect_cell(
                    workflow, source, task, arm, whole_documents=args.whole_documents
                )
                print(
                    json.dumps(
                        {
                            key: result[key]
                            for key in (
                                "task_id",
                                "condition_id",
                                "status",
                                "stop_reason",
                                "frozen_base",
                            )
                        }
                    ),
                    flush=True,
                )
                return result
            except Exception as error:
                root, _ = workflow._cell(task, arm)
                atomic_json(
                    root / "probe-result.json",
                    {
                        "task_id": task,
                        "condition_id": arm,
                        "arm": arm,
                        "condition": spec.condition(arm),
                        "status": "NOT_MEASURED",
                        "error_type": type(error).__name__,
                        "error_code": getattr(error, "code", None),
                        "authentication_status": authentication_status(error),
                        "utility": {"status": "NOT_MEASURED", "value": None},
                        "asr": {"status": "NOT_MEASURED", "value": None},
                    },
                )
                raise

        try:
            run_pilot_cells(
                tasks,
                arms,
                collect,
                max_workers=args.jobs,
                parallel_cells=args.whole_documents,
                on_progress=(lambda: write_progress(workflow, tasks, arms))
                if args.all_tasks
                else None,
            )
        finally:
            if args.all_tasks:
                write_progress(workflow, tasks, arms)
            else:
                write_summary(workflow, tasks=tasks, arms=arms)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
