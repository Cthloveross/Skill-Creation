#!/usr/bin/env python3
"""Merge a primary matrix report with a retry run that re-sampled selected cells.

Usage:
    .venv/bin/python scripts/merge_reports.py --config CFG --primary RUN/matrix \
        --retry RUN/matrix-retry-001 --cells /tmp/affected.json --output RUN/matrix-merged

For every cell named in ``--cells`` (JSON list of "task|arm"), the retry run's case
replaces the primary case; all other cells keep the primary case. Aggregates are
recomputed with the package's own ``report_cases`` so denominators and NOT_MEASURED
handling are identical to a single-run report. The merged report records, per cell,
which run it came from and why the cell was re-sampled (infrastructure-caused unknown
results in the primary run). Neither input directory is modified.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


def load_report(directory: Path) -> dict:
    path = directory / "report.json"
    if not path.is_file():
        raise SystemExit(f"missing report: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def merge_cases(primary: dict, retry: dict, cells: set[str]) -> tuple[list[dict], dict]:
    retry_cases = {f"{c['task_id']}|{c['condition']}": c for c in retry["cases"]}
    merged: list[dict] = []
    provenance: dict[str, dict] = {}
    for case in primary["cases"]:
        key = f"{case['task_id']}|{case['condition']}"
        if key in cells and key in retry_cases:
            merged.append(retry_cases[key])
            provenance[key] = {
                "source": "retry",
                "primary_status": case.get("status"),
                "primary_stop_reason": case.get("stop_reason"),
                "retry_status": retry_cases[key].get("status"),
                "retry_stop_reason": retry_cases[key].get("stop_reason"),
            }
        else:
            merged.append(case)
            provenance[key] = {"source": "primary"}
    missing = sorted(key for key in cells if key not in retry_cases)
    return merged, {"cells": provenance, "retry_cells_missing_from_retry_run": missing}


def merged_usage(primary: dict, retries: list[dict], names: list[str]) -> dict:
    """Sum per-role provider usage across runs; keep each run's own usage for provenance."""
    fields = ("requests", "input_tokens", "output_tokens", "cached_input_tokens")
    roles: dict[str, dict] = {}
    for report in [primary, *retries]:
        for role, row in ((report.get("usage") or {}).get("roles") or {}).items():
            target = roles.setdefault(role, dict.fromkeys(fields, 0))
            for field in fields:
                value = row.get(field)
                if target[field] is None or value is None:
                    target[field] = None
                else:
                    target[field] += value
    total = {
        field: (
            sum(row[field] for row in roles.values())
            if roles and all(row[field] is not None for row in roles.values())
            else None
        )
        for field in fields
    }
    return {
        "status": "MEASURED" if roles else "NOT_MEASURED",
        "basis": "provider_response_usage summed over primary and retry runs; "
        "primary includes abandoned (re-sampled) cells",
        "roles": roles,
        "total": total,
        "cost_usd": None,
        "cost_status": "NOT_MEASURED",
        "cost_reason": "provider responses do not include billing charges",
        "runs": {
            "primary": primary.get("usage"),
            **dict(zip(names, [r.get("usage") for r in retries], strict=True)),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--primary", type=Path, required=True)
    parser.add_argument(
        "--retry",
        type=Path,
        action="append",
        required=True,
        help="retry run dir; repeatable, paired in order with --cells; later dirs win",
    )
    parser.add_argument("--cells", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    from tau_skill_evolution.artifacts import atomic_json
    from tau_skill_evolution.evaluation import report_cases
    from tau_skill_evolution.spec import load_spec
    from tau_skill_evolution.workflow import Workflow

    spec = load_spec(args.config.resolve())
    if len(args.retry) != len(args.cells):
        raise SystemExit("--retry and --cells must be given the same number of times")
    primary = load_report(args.primary)
    for report, name in ((primary, "primary"),):
        if report.get("namespace") != spec.namespace or report.get("experiment") != spec.experiment:
            raise SystemExit(f"{name} report does not belong to this experiment/config")
    merged_cases = primary["cases"]
    provenance: dict = {"cells": {}, "retry_cells_missing_from_retry_run": []}
    for retry_dir, cells_path in zip(args.retry, args.cells, strict=True):
        retry = load_report(retry_dir)
        if retry.get("namespace") != spec.namespace or retry.get("experiment") != spec.experiment:
            raise SystemExit(f"{retry_dir} report does not belong to this experiment/config")
        cells = set(json.loads(cells_path.read_text(encoding="utf-8")))
        merged_cases, step = merge_cases({"cases": merged_cases}, retry, cells)
        for key, value in step["cells"].items():
            if value["source"] == "retry":
                provenance["cells"][key] = {**value, "source": str(retry_dir)}
            else:
                provenance["cells"].setdefault(key, {"source": "primary"})
        provenance["retry_cells_missing_from_retry_run"] += [
            f"{retry_dir}:{key}" for key in step["retry_cells_missing_from_retry_run"]
        ]
    report = report_cases(
        merged_cases,
        task_denominator=len(spec.tasks),
        conditions=tuple(spec.values["matrix"]["arms"]),
    )
    report.update(
        namespace=spec.namespace,
        experiment=spec.experiment,
        protocol=spec.namespace,
        run_mode="formal-merged",
        formal_matrix_result=any(
            m.get("status") == "MEASURED" for c in merged_cases for m in c["evaluations"].values()
        ),
        execution={
            **primary.get("execution", {}),
            "merged_from": [str(args.primary), str(args.retry)],
        },
        cases=merged_cases,
        usage=merged_usage(
            primary, [load_report(r) for r in args.retry], [str(r) for r in args.retry]
        ),
        merge_provenance={
            "reason": (
                "cells whose primary run had an infrastructure-caused unknown result "
                "(900 s request timeouts) were re-sampled in the retry run"
            ),
            "retry_cell_count": sum(
                1 for v in provenance["cells"].values() if v["source"] != "primary"
            ),
            **provenance,
        },
    )
    args.output.mkdir(parents=True, exist_ok=True)
    atomic_json(args.output / "report.json", report)
    shim = SimpleNamespace(spec=spec, demo=False, root=args.output)
    shim._write_report_tail = lambda *a, **k: Workflow._write_report_tail(shim, *a, **k)
    Workflow._write_report_md(shim, report)
    with (args.output / "REPORT.md").open("a", encoding="utf-8") as stream:
        stream.write(
            "\n\n## Merge provenance\n\n"
            f"{report['merge_provenance']['retry_cell_count']} cells were re-sampled in "
            f"{', '.join(f'`{r}`' for r in args.retry)} because their earlier run ended in an "
            "infrastructure-caused unknown result; see `merge_provenance` in report.json.\n"
        )
    print(
        json.dumps(
            {
                "output": str(args.output),
                **{k: report["merge_provenance"][k] for k in ("retry_cell_count",)},
                "missing": report["merge_provenance"]["retry_cells_missing_from_retry_run"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
