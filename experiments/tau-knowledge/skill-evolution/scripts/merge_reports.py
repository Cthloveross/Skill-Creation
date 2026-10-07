#!/usr/bin/env python3
"""Collect explicitly identified rerun trials without replacing primary matrix samples."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


def load_report(directory: Path) -> dict:
    return json.loads((directory / "report.json").read_text(encoding="utf-8"))


def case_index(report: dict) -> dict[str, dict]:
    indexed = {}
    for case in report["cases"]:
        key = f"{case['task_id']}|{case['condition']}"
        if key in indexed:
            raise ValueError(f"duplicate report cell: {key}")
        indexed[key] = case
    return indexed


def validate_report(
    report: dict, identity: dict, experiment: str, namespace: str, runtime: str | None = None
) -> None:
    if report.get("identity") != identity:
        raise ValueError(
            "report experiment identity differs or is missing; legacy reports stay separate"
        )
    if report.get("experiment") != experiment or report.get("namespace") != namespace:
        raise ValueError("report does not belong to the selected experiment")
    if not isinstance(report.get("trial_id"), str) or not report["trial_id"]:
        raise ValueError("report must identify its independent trial")
    backend = report.get("execution", {}).get("backend")
    if (report.get("run_mode"), backend) not in {("formal", "docker"), ("workspace", "workspace")}:
        raise ValueError("trial collection requires matching Docker or workspace reports")
    if runtime is not None and backend != runtime:
        raise ValueError("report runtime differs from the selected runtime")
    if backend == "workspace" and report.get("formal_matrix_result", False):
        raise ValueError("workspace results cannot claim Docker isolation acceptance")
    case_index(report)


def execution_identity(report: dict) -> dict:
    return {
        key: value for key, value in report["execution"].items() if key != "formal_matrix_result"
    }


def resampled_cases(primary: dict, retry: dict, cells: set[str]) -> list[dict]:
    originals, reruns = case_index(primary), case_index(retry)
    if cells - originals.keys() or cells - reruns.keys():
        raise ValueError("selected rerun cells are missing from a report")
    trials = []
    for key in sorted(cells):
        original, rerun = originals[key], reruns[key]
        if rerun.get("stop_reason") == "not_started" or rerun.get("status") == "NOT_STARTED":
            raise ValueError(f"rerun cell was not started: {key}")
        trials.append(
            {
                "cell": key,
                "trial_id": retry["trial_id"],
                "primary_trial_id": primary["trial_id"],
                "kind": "whole_chain_resample",
                "primary_base_hash": original.get("acquisition", {}).get("base_hash"),
                "primary_initial_bundle_hash": original.get("initial_bundle_hash"),
                "primary_stop_reason": original.get("stop_reason"),
                "resampled_base_hash": rerun.get("acquisition", {}).get("base_hash"),
                "resampled_initial_bundle_hash": rerun.get("initial_bundle_hash"),
                "case": rerun,
            }
        )
    return trials


def merged_usage(primary: dict, retries: list[dict], names: list[str]) -> dict:
    fields = ("requests", "input_tokens", "output_tokens", "cached_input_tokens")
    roles: dict[str, dict] = {}
    for report in [primary, *retries]:
        for role, row in ((report.get("usage") or {}).get("roles") or {}).items():
            target = roles.setdefault(role, dict.fromkeys(fields, 0))
            for field in fields:
                value = row.get(field)
                target[field] = (
                    None if target[field] is None or value is None else target[field] + value
                )
    return {
        "status": "MEASURED" if roles else "NOT_MEASURED",
        "basis": "provider_response_usage across primary and separately reported rerun trials",
        "roles": roles,
        "total": {
            field: sum(row[field] for row in roles.values())
            if roles and all(row[field] is not None for row in roles.values())
            else None
            for field in fields
        },
        "cost_usd": None,
        "cost_status": "NOT_MEASURED",
        "cost_reason": "provider responses do not include billing charges",
        "runs": {
            "primary": primary.get("usage"),
            **dict(zip(names, [r.get("usage") for r in retries], strict=True)),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--runtime", choices=("workspace", "docker"), default="workspace")
    parser.add_argument("--primary", type=Path, required=True)
    parser.add_argument("--retry", type=Path, action="append", required=True)
    parser.add_argument("--cells", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    from tau_skill_evolution.artifacts import atomic_json
    from tau_skill_evolution.evaluation import report_cases
    from tau_skill_evolution.spec import load_spec
    from tau_skill_evolution.workflow import Workflow

    if len(args.retry) != len(args.cells):
        parser.error("--retry and --cells must be paired")
    directories = [args.primary.resolve(), *(path.resolve() for path in args.retry)]
    if len(set(directories)) != len(directories) or args.output.resolve() in directories:
        parser.error("input trials and output must be separate directories")
    spec = load_spec(args.config.resolve())
    identity = spec.identity
    primary = load_report(args.primary)
    retries = [load_report(path) for path in args.retry]
    trial_ids = set()
    matrix_cells = {f"{task}|{arm}" for task, arm in spec.cells}
    for report in [primary, *retries]:
        validate_report(report, identity, spec.experiment, spec.namespace, args.runtime)
        if execution_identity(report) != execution_identity(primary):
            raise ValueError("report execution runtime or lock differs from the primary trial")
        if report["trial_id"] in trial_ids:
            raise ValueError("trial_id must be unique across independent runs")
        trial_ids.add(report["trial_id"])
        if case_index(report).keys() != matrix_cells:
            raise ValueError("report task population differs from the fixed matrix")
    resamples, trial_summaries = [], []
    for directory, retry, path in zip(args.retry, retries, args.cells, strict=True):
        selected = json.loads(path.read_text(encoding="utf-8"))
        if (
            not isinstance(selected, list)
            or not selected
            or any(not isinstance(cell, str) for cell in selected)
            or len(selected) != len(set(selected))
            or set(selected) - matrix_cells
        ):
            raise ValueError("--cells must contain unique cells from the fixed matrix")
        trials = resampled_cases(primary, retry, set(selected))
        resamples.extend({**trial, "source": str(directory)} for trial in trials)
        trial_summaries.append(
            {
                "trial_id": retry["trial_id"],
                "source": str(directory),
                "selected_cells": selected,
                "metrics": report_cases(
                    [trial["case"] for trial in trials],
                    task_denominator=len(spec.tasks),
                    conditions=spec.arms,
                ),
            }
        )
    report = report_cases(primary["cases"], task_denominator=len(spec.tasks), conditions=spec.arms)
    report.update(
        namespace=spec.namespace,
        experiment=spec.experiment,
        protocol=spec.namespace,
        identity=identity,
        trial_id=primary["trial_id"],
        run_mode="workspace-trials" if args.runtime == "workspace" else "formal-trials",
        formal_matrix_result=args.runtime == "docker"
        and primary.get("formal_matrix_result", False),
        execution={**primary["execution"], "collected_from": [str(p) for p in directories]},
        cases=primary["cases"],
        resampled_trials=resamples,
        trial_summaries=trial_summaries,
        usage=merged_usage(primary, retries, [str(p) for p in args.retry]),
    )
    args.output.mkdir(parents=True, exist_ok=True)
    atomic_json(args.output / "report.json", report)
    shim = SimpleNamespace(
        spec=spec, demo=False, runtime=args.runtime, execution=report["execution"], root=args.output
    )
    shim._write_report_tail = lambda *a, **k: Workflow._write_report_tail(shim, *a, **k)
    Workflow._write_report_md(shim, report)
    with (args.output / "REPORT.md").open("a", encoding="utf-8") as stream:
        stream.write(
            "\n\nPrimary matrix metrics retain the original samples. "
            f"{len(resamples)} separately identified whole-chain reruns appear in "
            "`resampled_trials` and `trial_summaries`; they are not checkpoint resumes.\n"
        )
    print(json.dumps({"output": str(args.output), "resampled_trial_cells": len(resamples)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
