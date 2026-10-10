#!/usr/bin/env python3
"""Run the fixed SkillsBench v8 retrieval-only pilot and freeze B*.

This entry point never creates, executes, verifies, or grades a Skill. It runs
the three pilot tasks in parallel (at most three workers) while processing the
five conditions for each task in a fixed serial order.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import threading
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
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


def collect_cell(workflow: Any, source: Any, task: str, arm: str) -> dict[str, Any]:
    from tau_skill_evolution.acquisition import AcquisitionBudgets, collect_base
    from tau_skill_evolution.artifacts import atomic_json, load_base, seal_base
    from tau_skill_evolution.retrieval import prepare_corpus
    from tau_skill_evolution.skillsbench import SkillsBenchInputView, selected_pool, validate_pool
    from tau_skill_evolution.skillsbench_attack import retrieval_contract

    root, journal = workflow._cell(task, arm)
    if journal.dispatched("generate_initial") or journal.dispatched("creation"):
        raise ValueError("probe_requires_a_separate_acquisition_only_trial")
    condition = workflow.spec.condition(arm)
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
    atomic_json(root / "probe-result.json", result)
    return result


def _payload_exposed(cell: Mapping[str, Any], stage: str, flag: str) -> bool:
    return cell[stage]["rates"][flag]["unique_chunks"]["numerator"] > 0


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
    result = {
        "schema": "skillsbench.acquisition-probe.v8",
        "namespace": workflow.spec.namespace,
        "source_identity": workflow.identity["identity_hash"],
        "probe_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
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
            cells,
            key=lambda cell: (tasks.index(cell["task_id"]), arms.index(cell["arm"])),
        ),
        "conditions": {
            arm: {
                "measured_tasks": len(
                    selected := [cell for cell in measured if cell["arm"] == arm]
                ),
                "source_injection": _constant_metric(selected, "pool", "source_injection"),
                "payload_chunk_ratio": _constant_metric(selected, "pool", "payload_chunk_ratio"),
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


def run_pilot_cells(
    tasks: Sequence[str],
    arms: Sequence[str],
    collect: Callable[[str, str], Any],
    *,
    max_workers: int = 3,
) -> list[Any]:
    """Run conditions serially within each task and at most three tasks concurrently."""
    if not 1 <= max_workers <= 3:
        raise ValueError("pilot_max_workers_must_be_between_one_and_three")
    stop = threading.Event()

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
    with ThreadPoolExecutor(max_workers=min(max_workers, len(tasks))) as executor:
        futures = {executor.submit(run_task, task): task for task in tasks}
        try:
            for future in as_completed(futures):
                results.extend(future.result())
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
    tasks, arms = DEFAULT_TASKS, PILOT_ARMS
    if set(tasks) - set(spec.tasks) or set(arms) - set(spec.arms):
        parser.error("selected tasks and conditions must belong to the frozen v8 matrix")
    if not 1 <= args.jobs <= 3:
        parser.error("--jobs must be between one and three")
    cells = tuple((task, arm) for task in tasks for arm in arms)
    source = SkillsBenchSource(spec.root)
    source.validate()
    with run_locks(args.run_dir, cells):
        # Build and validate both routes before authentication and before any paid
        # Analyzer request. This also prevents three task workers from racing to
        # construct the same condition index.
        for arm in arms:
            directory = selected_pool(spec, arm)
            validate_pool(spec.root, source, directory=directory)
            corpus = prepare_corpus(spec, tasks[0], arm)
            corpus.close()
        admission = bedrock_authentication(spec)
        workflow = Workflow(spec, args.run_dir, runtime="docker", interim_report=False)
        workflow.journal.dispatch(
            "acquisition-probe-contract",
            {
                "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "tasks": list(tasks),
                "conditions": list(arms),
                "cells": [list(cell) for cell in cells],
                "max_parallel_tasks": args.jobs,
                "serial_conditions_within_task": True,
            },
            lambda: {"stage": "acquisition-only", "expected_acquisitions": len(cells)},
            external=False,
        )
        atomic_json(
            workflow.root / "acquisition-admission.json",
            {"catalog": admission, "docker_required": False},
        )

        def collect(task: str, arm: str) -> dict[str, Any]:
            try:
                result = collect_cell(workflow, source, task, arm)
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
            run_pilot_cells(tasks, arms, collect, max_workers=args.jobs)
        finally:
            write_summary(workflow, tasks=tasks, arms=arms)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
