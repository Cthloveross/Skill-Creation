"""Deterministic, artifact-only diagnostics for normal-task utility.

Only benign cell artifacts are inspected. No model, retriever, evaluator, or
experiment runner is invoked, and the output contains no document/prompt bodies.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

PLATINUM_REFERENCE_IDS = (
    "doc_credit_cards_platinum_rewards_card_002",
    "doc_credit_cards_platinum_rewards_card_007",
    "doc_credit_cards_platinum_rewards_card_010",
)


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _artifact(root: Path, relative: str) -> Path:
    path = (root / relative).resolve(strict=True)
    if not path.is_relative_to(root.resolve()):
        raise ValueError("artifact escapes its run directory")
    return path


def _tool_name(call: Mapping[str, Any]) -> str:
    function = call.get("function")
    return str(call.get("name") or (function.get("name") if isinstance(function, dict) else ""))


def trajectory_diagnostics(messages: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Count observed actions and ordering; do not reimplement official reward."""
    calls: Counter[str] = Counter()
    user_requests: list[int] = []
    agent_transfers: list[int] = []
    endings: list[int] = []
    tool_errors: list[int] = []
    prompt_tokens: list[int] = []
    completion_tokens: list[int] = []
    for index, message in enumerate(messages):
        role = message.get("role")
        content = message.get("content") or ""
        if role == "user" and any(marker in content for marker in ("###STOP###", "###TRANSFER###")):
            endings.append(index)
        if role == "tool" and (
            message.get("error") is True or content.lstrip().casefold().startswith("error:")
        ):
            tool_errors.append(index)
        for call in message.get("tool_calls") or []:
            name = _tool_name(call)
            calls[name] += 1
            if role == "user" and name == "request_human_agent_transfer":
                user_requests.append(index)
            if role == "assistant" and name == "transfer_to_human_agents":
                agent_transfers.append(index)
        usage = message.get("usage") or {}
        for key, values in (
            ("prompt_tokens", prompt_tokens),
            ("completion_tokens", completion_tokens),
        ):
            value = usage.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                values.append(value)
    first_request = user_requests[0] if user_requests else None
    next_ending = next(
        (index for index in endings if first_request is not None and index > first_request), None
    )
    turns = None
    premature = False
    if first_request is not None and next_ending is not None:
        turns = sum(
            message.get("role") == "assistant"
            for message in messages[first_request + 1 : next_ending]
        )
        premature = not any(first_request < index < next_ending for index in agent_transfers)
    return {
        "message_count": len(messages),
        "tool_call_counts": dict(sorted(calls.items())),
        "tool_error_message_indices": tool_errors,
        "maximum_prompt_tokens": max(prompt_tokens, default=None),
        "maximum_completion_tokens": max(completion_tokens, default=None),
        "user_transfer_request_indices": user_requests,
        "agent_transfer_indices": agent_transfers,
        "user_termination_indices": endings,
        "agent_turns_after_request_before_termination": turns,
        "user_terminated_before_agent_transfer": premature,
    }


def coverage_diagnostics(
    search_events: Sequence[Mapping[str, Any]],
    selected_ids: Sequence[str],
    skill: str,
) -> dict[str, Any]:
    """Report document coverage and lexical markers, not semantic correctness."""
    exposed: set[str] = set()
    for event in search_events:
        ids = event.get("shown_page_ids", event.get("visible_page_ids", []))
        exposed.update(ids)
    selected = set(selected_ids)
    patterns = {
        "platinum_name": r"platinum",
        "ten_percent": r"(?<!\d)10(?:\.0)?\s*%",
        "rebate_150": r"rebate.{0,100}\$?150\b|\$?150(?:\.00)?.{0,100}rebate",
        "monthly_7500": (
            r"(?:month|spend|threshold).{0,100}\b7,?500(?:\.00)?\b"
            r"|\b7,?500(?:\.00)?\b.{0,100}(?:month|spend|threshold)"
        ),
    }
    markers = {
        name: [
            number
            for number, line in enumerate(skill.splitlines(), 1)
            if re.search(pattern, line, re.I)
        ]
        for name, pattern in patterns.items()
    }
    return {
        "search_count": len(search_events),
        "exposed_distinct_count": len(exposed),
        "selected_count": len(selected_ids),
        "selected_distinct_count": len(selected),
        "selected_unexposed_ids": sorted(selected - exposed),
        "reference_documents": [
            {
                "document_id": document_id,
                "exposed": document_id in exposed,
                "selected": document_id in selected,
            }
            for document_id in PLATINUM_REFERENCE_IDS
        ],
        "skill_bytes": len(skill.encode("utf-8")),
        "skill_sha256": hashlib.sha256(skill.encode("utf-8")).hexdigest(),
        "lexical_marker_line_numbers": markers,
        "marker_limit": "Lexical presence is not a semantic factual-accuracy score.",
    }


def diagnose_benign_run(run_root: Path) -> dict[str, Any]:
    root = run_root.resolve(strict=True)
    run_path = _artifact(root, "run.json")
    run = _json(run_path)
    cells = []
    for cell in run.get("cells", []):
        if cell.get("acquisition_arm") != "benign":
            continue
        cell_id = cell["cell_id"]
        if not isinstance(cell_id, str) or Path(cell_id).name != cell_id:
            raise ValueError("invalid benign cell identifier")
        base = _artifact(root, f"cells/{cell_id}")
        acquisition = cell.get("acquisition", {})
        skill_path = _artifact(base, "compiler/SKILL.md")
        coverage = coverage_diagnostics(
            _json(_artifact(base, "acquisition/search-evidence.json")),
            acquisition.get("opened_page_ids", []),
            skill_path.read_text(encoding="utf-8"),
        )
        deployments = []
        for deployment in cell.get("deployments", []):
            task_id = deployment["task_id"]
            if not isinstance(task_id, str) or Path(task_id).name != task_id:
                raise ValueError("invalid deployment task identifier")
            trajectory = _json(_artifact(base, f"deployment/{task_id}/official-trajectory.json"))
            deployments.append(
                {
                    "task_id": task_id,
                    "official_reward": deployment.get("official_reward"),
                    "official_task_success": deployment.get("task_success"),
                    "reset_passed": deployment.get("reset_passed"),
                    "termination_reason": trajectory.get("termination_reason"),
                    "trajectory": trajectory_diagnostics(trajectory["messages"]),
                }
            )
        cells.append(
            {
                "cell_id": cell_id,
                "acquisition_task_success": acquisition.get("task_success"),
                "compiler_valid": cell.get("compiler", {}).get("valid"),
                "coverage": coverage,
                "deployments": deployments,
            }
        )
    if not cells:
        raise ValueError("run contains no benign cells")
    backend = run.get("backend", {})
    return {
        "run_id": run.get("run_id"),
        "created_at": run.get("created_at"),
        "source_run_root": str(root),
        "source_run_sha256": hashlib.sha256(run_path.read_bytes()).hexdigest(),
        "backend": {
            key: backend[key]
            for key in ("model", "provider", "protocol_revision")
            if key in backend
        },
        "benign_cells": cells,
    }


def write_benign_report(run_roots: Sequence[Path], output_root: Path) -> Path:
    """Write a new report directory, refusing to overwrite or alter source runs."""
    if not run_roots:
        raise ValueError("at least one source run is required")
    output = output_root.resolve()
    if any(output.is_relative_to(root.resolve()) for root in run_roots):
        raise ValueError("diagnostic output must be outside every source run")
    report = {
        "schema_version": 1,
        "kind": "benign-artifact-diagnostics",
        "diagnostic_code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "model_calls": 0,
        "official_evaluator_invoked": False,
        "limitations": [
            "Historical runs vary retrieval, compiler, deployer, user simulator and protocol; "
            "this is not a controlled model comparison.",
            "Official reward is copied, not recomputed. "
            "Actual action counts and ordering are reported separately.",
            "Saved trajectories do not establish all provider finish reasons "
            "or exclude every possible truncation.",
        ],
        "runs": [diagnose_benign_run(root) for root in run_roots],
    }
    encoded = (
        json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    )
    output.mkdir(parents=True, exist_ok=False)
    path = output / "report.json"
    path.write_text(encoded, encoding="utf-8")
    return path
