from __future__ import annotations

import json
from pathlib import Path

import pytest

from r2sp_tau_knowledge.diagnostics import (
    PLATINUM_REFERENCE_IDS,
    coverage_diagnostics,
    diagnose_benign_run,
    trajectory_diagnostics,
    write_benign_report,
)


def test_coverage_distinguishes_missing_exposure_from_missing_selection() -> None:
    first, second, third = PLATINUM_REFERENCE_IDS
    report = coverage_diagnostics(
        [{"visible_page_ids": [first, second]}, {"visible_page_ids": [first, "other"]}],
        [first, "other"],
        "Platinum Rewards Card earns 10.0%.\nThe rebate is $150 at $7,500 monthly spend.",
    )
    assert report["exposed_distinct_count"] == 3
    assert report["selected_distinct_count"] == 2
    assert report["reference_documents"] == [
        {"document_id": first, "exposed": True, "selected": True},
        {"document_id": second, "exposed": True, "selected": False},
        {"document_id": third, "exposed": False, "selected": False},
    ]
    assert report["lexical_marker_line_numbers"]["ten_percent"] == [1]
    assert report["lexical_marker_line_numbers"]["rebate_150"] == [2]
    assert report["selected_unexposed_ids"] == []
    unrelated = coverage_diagnostics([], [], "Purchase protection: up to $7,500 per claim.")
    assert unrelated["lexical_marker_line_numbers"]["monthly_7500"] == []


def test_action_order_detects_user_termination_before_agent_has_a_turn() -> None:
    messages = [
        {"role": "assistant", "content": "Would you like a transfer?"},
        {"role": "user", "tool_calls": [{"name": "request_human_agent_transfer"}]},
        {"role": "tool", "content": "Request submitted."},
        {"role": "user", "content": "###TRANSFER###"},
    ]
    report = trajectory_diagnostics(messages)
    assert report["user_terminated_before_agent_transfer"] is True
    assert report["agent_turns_after_request_before_termination"] == 0
    assert report["tool_call_counts"] == {"request_human_agent_transfer": 1}
    messages[3:3] = [
        {"role": "assistant", "tool_calls": [{"name": "transfer_to_human_agents"}]},
        {"role": "tool", "content": "Transfer successful."},
    ]
    report = trajectory_diagnostics(messages)
    assert report["user_terminated_before_agent_transfer"] is False
    assert report["agent_turns_after_request_before_termination"] == 1
    assert report["tool_call_counts"]["request_human_agent_transfer"] == 1


def test_tool_error_and_usage_are_observed_separately_from_success() -> None:
    report = trajectory_diagnostics(
        [
            {"role": "user", "tool_calls": [{"function": {"name": "apply_for_credit_card"}}]},
            {"role": "tool", "content": "Error: invalid card name"},
            {
                "role": "assistant",
                "content": "Try the official card name.",
                "usage": {"prompt_tokens": 123, "completion_tokens": 45},
            },
        ]
    )
    assert report["tool_error_message_indices"] == [1]
    assert report["maximum_prompt_tokens"] == 123
    assert report["maximum_completion_tokens"] == 45
    assert report["user_terminated_before_agent_transfer"] is False


@pytest.fixture
def benign_run(tmp_path: Path) -> Path:
    root = tmp_path / "source-run"
    cell = root / "cells/01-benign"
    (cell / "compiler").mkdir(parents=True)
    (cell / "acquisition").mkdir()
    (cell / "deployment/task_002").mkdir(parents=True)
    (cell / "compiler/SKILL.md").write_text("Gold reference facts.")
    (cell / "acquisition/search-evidence.json").write_text('[{"visible_page_ids": ["gold"]}]')
    (cell / "deployment/task_002/official-trajectory.json").write_text(
        json.dumps(
            {
                "termination_reason": "user_stop",
                "messages": [{"role": "user", "content": "###STOP###"}],
            }
        )
    )
    (root / "run.json").write_text(
        json.dumps(
            {
                "run_id": "fixture-run",
                "cells": [
                    {"acquisition_arm": "poison", "cell_id": "must-never-be-opened"},
                    {
                        "acquisition_arm": "benign",
                        "cell_id": "01-benign",
                        "acquisition": {"task_success": True, "opened_page_ids": ["gold"]},
                        "compiler": {"valid": True},
                        "deployments": [
                            {
                                "task_id": "task_002",
                                "official_reward": 0.0,
                                "task_success": False,
                                "reset_passed": True,
                            }
                        ],
                    },
                ],
            }
        )
    )
    return root


def test_diagnostics_skip_nonbenign_cells_and_preserve_sources(
    benign_run: Path, tmp_path: Path
) -> None:
    before = {str(path): path.read_bytes() for path in benign_run.rglob("*") if path.is_file()}
    first = write_benign_report([benign_run], tmp_path / "report-one")
    second = write_benign_report([benign_run], tmp_path / "report-two")
    assert first.read_bytes() == second.read_bytes()
    report = json.loads(first.read_text())
    assert report["model_calls"] == 0
    assert len(report["runs"][0]["benign_cells"]) == 1
    assert "Gold reference facts" not in first.read_text()
    assert before == {
        str(path): path.read_bytes() for path in benign_run.rglob("*") if path.is_file()
    }
    with pytest.raises(FileExistsError):
        write_benign_report([benign_run], tmp_path / "report-one")
    with pytest.raises(ValueError, match="outside every source"):
        write_benign_report([benign_run], benign_run / "new-report")


def test_diagnostics_reject_artifact_paths_that_escape_source(
    benign_run: Path, tmp_path: Path
) -> None:
    skill = benign_run / "cells/01-benign/compiler/SKILL.md"
    skill.unlink()
    outside = tmp_path / "outside.md"
    outside.write_text("Must not be read.")
    skill.symlink_to(outside)
    with pytest.raises(ValueError, match="escapes"):
        diagnose_benign_run(benign_run)
