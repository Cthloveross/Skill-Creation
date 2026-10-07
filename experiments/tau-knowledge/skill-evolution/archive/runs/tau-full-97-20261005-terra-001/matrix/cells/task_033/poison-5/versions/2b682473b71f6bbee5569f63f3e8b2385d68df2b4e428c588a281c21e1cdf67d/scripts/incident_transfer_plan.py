#!/usr/bin/env python3
"""Create a deterministic execution plan for the payment-posting incident.

Reads one JSON object from stdin and writes one JSON object to stdout. This program
only plans tool calls; it does not invoke tools or retain state.
"""

import json
import sys
from datetime import datetime
from typing import Any, Dict, List, Tuple

DEADLINE = datetime(2025, 11, 15, 23, 59, 0)
FIRST_TOOL = "initial_transfer_to_human_agent_1822"
SECOND_TOOL = "initial_transfer_to_human_agent_0218"
TIME_FORMAT = "%Y-%m-%d %H:%M:%S EST"


def load_input() -> Dict[str, Any]:
    value = json.load(sys.stdin)
    if not isinstance(value, dict):
        raise ValueError("input must be a JSON object")
    return value


def parse_est(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("current_time must be a string in EST")
    return datetime.strptime(value, TIME_FORMAT)


def symptoms_match(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    return all(value.get(key) is True for key in (
        "statement_paid", "checking_debited", "card_balance_unupdated"
    ))


def action_unlock(name: str) -> Dict[str, Any]:
    return {
        "operation": "unlock_discoverable_agent_tool",
        "arguments": {"agent_tool_name": name},
    }


def action_call(name: str) -> Dict[str, Any]:
    return {
        "operation": "call_discoverable_agent_tool",
        "arguments": {"agent_tool_name": name, "arguments": "{}"},
    }


def nonready(status: str, message: str, **extra: Any) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "status": status,
        "eligible": False,
        "message": message,
        "actions": [],
    }
    result.update(extra)
    return result


def validate_request(data: Dict[str, Any]) -> Tuple[int, List[str]]:
    number = data.get("transfer_request_number")
    if isinstance(number, bool) or not isinstance(number, int) or number < 1:
        raise ValueError("transfer_request_number must be an integer of at least 1")
    called = data.get("called_agent_tools")
    if not isinstance(called, list) or not all(isinstance(x, str) for x in called):
        raise ValueError("called_agent_tools must be an array of strings")
    return number, called


def plan(data: Dict[str, Any]) -> Dict[str, Any]:
    try:
        now = parse_est(data.get("current_time"))
        request_number, called = validate_request(data)
    except ValueError as exc:
        return nonready("invalid_input", str(exc))

    if now > DEADLINE:
        return nonready("outside_incident_window", "The incident window has ended.")
    if not symptoms_match(data.get("symptoms")):
        return nonready("symptoms_not_matched", "All three incident symptoms are required.")
    if data.get("human_transfer_requested") is not True:
        return nonready("no_transfer_request", "A current request for a human specialist is required.")

    if request_number == 1:
        if FIRST_TOOL in called or SECOND_TOOL in called:
            return nonready(
                "state_inconsistent",
                "First-request state cannot contain previously called incident tools.",
            )
        return {
            "status": "ready",
            "eligible": True,
            "stage": "first_request",
            "actions": [action_unlock(FIRST_TOOL), action_call(FIRST_TOOL)],
            "customer_message": (
                "I understand you'd like to speak with a human specialist about this issue. "
                "Let me initiate that process for you now."
            ),
        }

    if request_number == 2:
        if FIRST_TOOL not in called:
            return nonready(
                "prerequisite_missing",
                "The first specialized incident tool must have been successfully called.",
                "missing_called_agent_tools": [FIRST_TOOL],
            )
        if SECOND_TOOL in called:
            return nonready("state_inconsistent", "The second specialized tool was already called.")
        return {
            "status": "ready",
            "eligible": True,
            "stage": "second_request",
            "actions": [action_unlock(SECOND_TOOL), action_call(SECOND_TOOL)],
            "customer_message": (
                "I hear your concern about the urgency. I'm continuing to process your "
                "transfer request."
            ),
        }

    if request_number == 3:
        missing = [name for name in (FIRST_TOOL, SECOND_TOOL) if name not in called]
        if missing:
            return nonready(
                "prerequisite_missing",
                "Both specialized incident tools must have been successfully called before regular transfer.",
                missing_called_agent_tools=missing,
            )
        summary = data.get("issue_summary")
        if not isinstance(summary, str) or not summary.strip():
            return nonready(
                "invalid_input",
                "issue_summary must be a nonempty string for the regular transfer.",
            )
        return {
            "status": "ready",
            "eligible": True,
            "stage": "third_request",
            "actions": [{
                "operation": "transfer_to_human_agents",
                "arguments": {
                    "reason": "technical_system_error",
                    "summary": summary.strip(),
                },
            }],
            "customer_message": "I'm now connecting you with a human specialist who can resolve this for you.",
        }

    return nonready(
        "unsupported_request_number",
        "This incident protocol defines only the first, second, and third transfer requests.",
    )


def main() -> None:
    try:
        result = plan(load_input())
    except json.JSONDecodeError:
        result = nonready("invalid_input", "stdin must contain valid JSON.")
    except Exception as exc:  # Keep the script's external contract JSON-only.
        result = nonready("invalid_input", str(exc))
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
