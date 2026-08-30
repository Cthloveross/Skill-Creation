"""Stable JSON, CSV, and Markdown reports for pilot outcomes."""

from __future__ import annotations

import csv
import json
from io import StringIO
from pathlib import Path
from typing import Any

from r2sp.artifacts import ArtifactStore
from r2sp.evaluation import PilotSummary

CONTEXT_FIELDS = (
    "mode",
    "protocol_version",
    "matched_case_denominator",
    "deployment_task_denominator_per_arm",
    "provenance_json",
)

OUTCOME_FIELDS = (
    "case_id",
    "poison_overlay_top10",
    "sham_overlay_top10",
    "poison_overlay_selected5",
    "sham_overlay_selected5",
    "poison_natural_read",
    "sham_natural_read",
    "poison_valid_skill",
    "sham_valid_skill",
    "poison_positive_canary",
    "poison_full_chain_success",
    "sham_positive_false_activation",
    "sham_negative_false_activation",
    "poison_negative_false_activation",
    "sham_authoring_tgc",
    "poison_authoring_tgc",
    "sham_positive_tgc",
    "sham_negative_tgc",
    "poison_positive_tgc",
    "poison_negative_tgc",
)

FUNNEL_FIELDS = CONTEXT_FIELDS + OUTCOME_FIELDS


def summary_json(summary: PilotSummary) -> str:
    return json.dumps(summary.to_dict(), sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def funnel_csv(summary: PilotSummary) -> str:
    buffer = StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=FUNNEL_FIELDS, lineterminator="\n")
    writer.writeheader()
    denominators = summary.denominators
    context = {
        "mode": summary.eligibility.mode,
        "protocol_version": summary.eligibility.protocol_version,
        "matched_case_denominator": denominators["matched_cases"],
        "deployment_task_denominator_per_arm": denominators["deployment_tasks_per_arm"],
        "provenance_json": json.dumps(
            summary.eligibility.provenance_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
    }
    for outcome in summary.outcomes:
        row = {**context, **outcome.to_dict()}
        writer.writerow({field: row[field] for field in FUNNEL_FIELDS})
    return buffer.getvalue()


def summary_markdown(summary: PilotSummary) -> str:
    denominators = summary.denominators
    cases = denominators["matched_cases"]
    deployments_per_arm = denominators["deployment_tasks_per_arm"]
    negative_deployments = denominators["negative_deployment_tasks_total"]
    provenance = json.dumps(
        summary.eligibility.provenance_dict(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    lines = [
        "# R2SP Pilot Summary",
        "",
        f"- Decision: `{summary.decision}`",
        f"- Research eligible: `{str(summary.eligibility.eligible).lower()}`",
        f"- Mode: `{summary.eligibility.mode}`",
        f"- Protocol version: `{summary.eligibility.protocol_version}`",
        f"- Provenance: `{provenance}`",
        f"- Matched cases (actual / expected): "
        f"`{cases} / {summary.eligibility.expected_case_count}`",
        f"- Deployment tasks (Sham / Poison / total): "
        f"`{deployments_per_arm} / {deployments_per_arm} / "
        f"{denominators['deployment_tasks_total']}`",
        f"- Overlay in acquisition top-10 (Sham / Poison; denominator {cases} each): "
        f"`{summary.sham_overlay_top10} / {summary.poison_overlay_top10}`",
        f"- Overlay selected in model top-5 (Sham / Poison; denominator {cases} each): "
        f"`{summary.sham_overlay_selected5} / {summary.poison_overlay_selected5}`",
        f"- Poison natural full reads: `{summary.poison_natural_reads} / {cases}`",
        f"- Valid skills (Sham / Poison; denominator {cases} each): "
        f"`{summary.sham_valid_skills} / {summary.poison_valid_skills}`",
        f"- Poison positive canary activations (`Y_canary`): "
        f"`{summary.poison_positive_canary_activations} / {cases}`",
        f"- Poison joint full-chain successes (`Y_joint`): "
        f"`{summary.poison_full_chain_successes} / {cases}`",
        f"- Sham-positive false activations: `{summary.sham_positive_false_activations} / {cases}`",
        f"- All negative false activations: "
        f"`{summary.all_negative_false_activations} / {negative_deployments}`",
        f"- Mean deployment TGC (Sham / Poison / difference): "
        f"`{summary.mean_deployment_tgc_sham:.4f} / {summary.mean_deployment_tgc_poison:.4f} / "
        f"{summary.mean_deployment_tgc_difference:.4f}` "
        f"(denominator `{deployments_per_arm}` tasks per arm)",
    ]
    if summary.decision_reasons:
        lines.extend(["", "## Decision reasons", ""])
        lines.extend(f"- {reason}" for reason in summary.decision_reasons)
    lines.extend(
        [
            "",
            "## Interpretation boundary",
            "",
            "Deployment episodes are repeated observations within matched skill-build cases, "
            "not independent samples. Synthetic or incomplete runs validate instrumentation "
            "only and cannot determine the scientific go/no-go.",
            "",
        ]
    )
    return "\n".join(lines)


def write_reports(summary: PilotSummary, output_directory: str | Path) -> dict[str, str]:
    directory = Path(output_directory)
    store = ArtifactStore(directory)
    content: dict[str, str] = {
        "summary.json": summary_json(summary),
        "funnel.csv": funnel_csv(summary),
        "summary.md": summary_markdown(summary),
    }
    paths: dict[str, str] = {}
    for name, value in content.items():
        record = store.write_text(name, value)
        paths[name] = str(record.path)
    return paths


def load_summary_payload(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError("summary payload must be a JSON object")
    return value
