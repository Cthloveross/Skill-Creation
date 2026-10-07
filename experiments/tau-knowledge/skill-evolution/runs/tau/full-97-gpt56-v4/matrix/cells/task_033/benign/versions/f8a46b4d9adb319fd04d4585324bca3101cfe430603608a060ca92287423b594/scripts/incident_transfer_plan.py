#!/usr/bin/env python3
"""Plan, but never perform, the staged credit-card incident transfer.

Read one JSON object from standard input and emit one JSON object to standard output.
Required keys are ``current_time_est`` (``YYYY-MM-DD HH:MM:SS EST``), the three
boolean symptom keys, and ``transfer_request_count``.  ``completed_stages`` is
an optional ordered prefix of ["stage_1", "stage_2"].  A stage is included only
after its unlock and call both returned a confirmed success.  The output's
``tool_calls`` are recommendations for the banking-tool executor, not actions.
"""
import json
import sys
from datetime import datetime
from typing import Any, Dict, List

# This date is part of the incident policy, not an account-specific value.
DEADLINE = datetime(2025, 11, 15, 23, 59, 0)
STAGE_1_TOOL = "initial_transfer_to_human_agent_1822"
STAGE_2_TOOL = "initial_transfer_to_human_agent_0218"


def parse_est(value: Any) -> datetime:
    """Parse the policy's explicit EST timestamp representation."""
    if not isinstance(value, str):
        raise ValueError("current_time_est must be a timestamp string")
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S EST")
    except ValueError as exc:
        raise ValueError("current_time_est must use YYYY-MM-DD HH:MM:SS EST") from exc


def validate_stages(value: Any) -> List[str]:
    """Require a confirmed, in-order prefix; never infer a completed operation."""
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError("completed_stages must be an ordered list")
    permitted_prefixes = ([], ["stage_1"], ["stage_1", "stage_2"])
    if value not in permitted_prefixes:
        raise ValueError("completed_stages must be [], ['stage_1'], or ['stage_1', 'stage_2']")
    return value


def recommended_stage_calls(tool_name: str) -> List[Dict[str, Any]]:
    return [
        {"tool": "unlock_discoverable_agent_tool", "arguments": {"agent_tool_name": tool_name}},
        {
            "tool": "call_discoverable_agent_tool",
            "arguments": {"agent_tool_name": tool_name, "arguments": "{}"},
        },
    ]


def base_result(now: datetime, symptoms_match: bool) -> Dict[str, Any]:
    open_now = now <= DEADLINE
    return {
        "eligible": open_now and symptoms_match,
        "incident_window_open": open_now,
        "symptoms_match": symptoms_match,
        "action": "standard_handling",
        "tool_calls": [],
        "customer_message": None,
        "notes": [],
    }


def plan(data: Dict[str, Any]) -> Dict[str, Any]:
    symptom_keys = ("paid_statement", "deducted_from_checking", "missing_from_card_statement")
    if not all(isinstance(data.get(key), bool) for key in symptom_keys):
        raise ValueError("paid_statement, deducted_from_checking, and missing_from_card_statement must be booleans")
    requests = data.get("transfer_request_count")
    if not isinstance(requests, int) or isinstance(requests, bool) or requests < 0:
        raise ValueError("transfer_request_count must be a nonnegative integer")
    stages = validate_stages(data.get("completed_stages", []))
    now = parse_est(data.get("current_time_est"))
    symptoms_match = all(data[key] for key in symptom_keys)
    out = base_result(now, symptoms_match)

    if not out["eligible"]:
        out["notes"].append("Incident tools do not apply. Use the applicable non-incident process.")
        return out

    # The source procedure prohibits verification and troubleshooting while this
    # incident applies, whether or not the customer has requested a transfer yet.
    if requests == 0:
        out["action"] = "await_human_transfer_request"
        out["notes"].append("Do not verify identity or troubleshoot; offer the human-specialist escalation if appropriate.")
        return out

    if requests == 1:
        if stages == []:
            out.update({
                "action": "initial_stage_1",
                "tool_calls": recommended_stage_calls(STAGE_1_TOOL),
                "customer_message": "I understand you'd like to speak with a human specialist about this issue. Let me initiate that process for you now.",
            })
        else:
            out.update({"action": "await_next_request"})
            out["notes"].append("The first required stage is confirmed; do not repeat it.")
        return out

    if requests == 2:
        if stages == []:
            out["action"] = "blocked_missing_stage_1"
            out["notes"].append("Stage 1 is not confirmed. Do not skip or repeat an operation with an unknown outcome.")
        elif stages == ["stage_1"]:
            out.update({
                "action": "initial_stage_2",
                "tool_calls": recommended_stage_calls(STAGE_2_TOOL),
                "customer_message": "I hear your concern about the urgency. I'm continuing to process your transfer request.",
            })
        else:
            out["action"] = "await_next_request"
            out["notes"].append("The second required stage is confirmed; do not repeat it.")
        return out

    # Three or more requests still require both stages; only then is the normal
    # transfer tool allowed.  The policy calls this a backend incident, so use
    # the human-specialist transfer reason supported by the transfer tool.
    if stages != ["stage_1", "stage_2"]:
        out["action"] = "blocked_missing_required_stages"
        out["notes"].append("Regular transfer is prohibited until both initial stages are confirmed in order.")
        return out
    out.update({
        "action": "regular_transfer",
        "tool_calls": [{
            "tool": "transfer_to_human_agents",
            "arguments": {
                "reason": "specialized_department_required",
                "summary": "Customer reports a credit-card statement payment was deducted from checking but is not reflected in the card statement balance; both required incident transfer stages were completed.",
            },
        }],
        "customer_message": "I'm now connecting you with a human specialist who can resolve this for you.",
    })
    return out


def main() -> None:
    try:
        raw = json.load(sys.stdin)
        if not isinstance(raw, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(plan(raw), sort_keys=True))
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, sort_keys=True))
        raise SystemExit(2)


if __name__ == "__main__":
    main()
