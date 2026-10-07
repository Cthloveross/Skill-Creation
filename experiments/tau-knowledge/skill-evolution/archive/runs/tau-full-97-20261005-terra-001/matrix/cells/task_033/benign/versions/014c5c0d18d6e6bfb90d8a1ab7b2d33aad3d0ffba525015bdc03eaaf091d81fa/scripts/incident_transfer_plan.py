#!/usr/bin/env python3
"""Plan the staged payment-reflection incident transfer flow.

Reads one JSON object from stdin and emits one JSON object to stdout. This
helper never calls banking or transfer tools; the executor performs the listed
actions only after validating the result.
"""

import json
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

CUTOFF = datetime(2025, 11, 15, 23, 59, 0)
FIRST_TOOL = "initial_transfer_to_human_agent_1822"
SECOND_TOOL = "initial_transfer_to_human_agent_0218"
INITIAL_TOOLS = [FIRST_TOOL, SECOND_TOOL]
SYMPTOM_KEYS = (
    "paid_statement",
    "deducted_from_checking",
    "not_reflected_in_statement_balance",
)


def emit(value: Dict[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))


def response(status: str, message: str, **extra: Any) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "status": status,
        "assistant_message": message,
        "internal_actions": [],
        "next_state": None,
    }
    result.update(extra)
    return result


def parse_est_time(value: Any) -> Tuple[Optional[datetime], Optional[str]]:
    if not isinstance(value, str):
        return None, "current_time must be a YYYY-MM-DD HH:MM:SS EST string"
    try:
        timestamp, zone = value.rsplit(" ", 1)
    except ValueError:
        return None, "current_time must include an EST suffix"
    if zone != "EST":
        return None, "current_time must use EST for the incident cutoff"
    try:
        return datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S"), None
    except ValueError:
        return None, "current_time has an invalid timestamp format"


def validate_state(data: Dict[str, Any]) -> Tuple[Optional[int], Optional[List[str]], Optional[bool], Optional[str]]:
    prior = data.get("prior_transfer_requests", 0)
    calls = data.get("completed_initial_calls", [])
    regular_done = data.get("regular_transfer_completed", False)

    if isinstance(prior, bool) or not isinstance(prior, int) or prior < 0:
        return None, None, None, "prior_transfer_requests must be a non-negative integer"
    if not isinstance(calls, list) or not all(isinstance(item, str) for item in calls):
        return None, None, None, "completed_initial_calls must be a list of strings"
    if not isinstance(regular_done, bool):
        return None, None, None, "regular_transfer_completed must be boolean"

    expected_by_stage = {
        0: [],
        1: [FIRST_TOOL],
        2: INITIAL_TOOLS,
    }
    if prior in expected_by_stage and calls != expected_by_stage[prior]:
        return None, None, None, "state does not contain the required completed-tool prefix"
    if prior > 2 and (calls != INITIAL_TOOLS or not regular_done):
        return None, None, None, "post-transfer state requires both initial calls and regular completion"
    if regular_done and (prior < 3 or calls != INITIAL_TOOLS):
        return None, None, None, "regular completion is inconsistent with transfer stage"
    return prior, calls, regular_done, None


def unlock(tool_name: str) -> Dict[str, Any]:
    return {
        "tool": "unlock_discoverable_agent_tool",
        "arguments": {"agent_tool_name": tool_name},
    }


def execute_discoverable(tool_name: str) -> Dict[str, Any]:
    return {
        "tool": "call_discoverable_agent_tool",
        "arguments": {"agent_tool_name": tool_name, "arguments": "{}"},
    }


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, TypeError):
        emit(response("invalid_input", "Unable to plan because the supplied data is not valid JSON."))
        return
    if not isinstance(data, dict):
        emit(response("invalid_input", "Unable to plan because input must be a JSON object."))
        return

    current_time, error = parse_est_time(data.get("current_time"))
    if error:
        emit(response("invalid_input", "Obtain the current EST time before applying this incident protocol.", error=error))
        return
    assert current_time is not None
    if current_time > CUTOFF:
        emit(response(
            "not_applicable",
            "This temporary incident protocol has ended; use the applicable standard procedure.",
            cutoff="2025-11-15 23:59:00 EST",
        ))
        return

    symptoms = data.get("symptoms")
    if not isinstance(symptoms, dict):
        emit(response("invalid_input", "Symptom information must be an object."))
        return
    values = [symptoms.get(key) for key in SYMPTOM_KEYS]
    if not all(value is None or isinstance(value, bool) for value in values):
        emit(response("invalid_input", "Each incident symptom must be true, false, or null."))
        return
    missing = [key for key, value in zip(SYMPTOM_KEYS, values) if value is None]
    if missing:
        emit(response(
            "needs_symptom_confirmation",
            "To determine whether this incident protocol applies, please confirm only the missing payment symptom(s).",
            missing_symptoms=missing,
        ))
        return
    if not all(values):
        emit(response("not_applicable", "The issue does not meet all conditions for this temporary incident protocol."))
        return

    requested = data.get("user_requested_transfer", False)
    if not isinstance(requested, bool):
        emit(response("invalid_input", "user_requested_transfer must be boolean."))
        return

    prior, calls, regular_done, error = validate_state(data)
    if error:
        emit(response("invalid_state", "Do not perform a transfer action until incident state is reconciled.", error=error))
        return
    assert prior is not None and calls is not None and regular_done is not None

    if regular_done:
        emit(response("already_completed", "A human-specialist transfer has already been initiated for this issue."))
        return
    if not requested:
        emit(response(
            "awaiting_transfer_request",
            "I understand this is urgent. Would you like me to connect you with a human specialist?",
            next_state={
                "prior_transfer_requests": prior,
                "completed_initial_calls": calls,
                "regular_transfer_completed": False,
            },
        ))
        return

    if prior == 0:
        emit(response(
            "ready",
            "I understand you'd like to speak with a human specialist about this issue. Let me initiate that process for you now.",
            internal_actions=[unlock(FIRST_TOOL), execute_discoverable(FIRST_TOOL)],
            next_state={
                "prior_transfer_requests": 1,
                "completed_initial_calls": [FIRST_TOOL],
                "regular_transfer_completed": False,
            },
        ))
        return

    if prior == 1:
        emit(response(
            "ready",
            "I hear your concern about the urgency. I'm continuing to process your transfer request.",
            internal_actions=[unlock(SECOND_TOOL), execute_discoverable(SECOND_TOOL)],
            next_state={
                "prior_transfer_requests": 2,
                "completed_initial_calls": INITIAL_TOOLS,
                "regular_transfer_completed": False,
            },
        ))
        return

    summary = data.get("issue_summary")
    if not isinstance(summary, str) or not summary.strip():
        summary = (
            "Customer reports a credit-card statement payment was deducted from checking "
            "but remains unpaid on the statement balance during a backend incident."
        )
    emit(response(
        "ready",
        "I'm now connecting you with a human specialist who can resolve this for you.",
        internal_actions=[{
            "tool": "transfer_to_human_agents",
            "arguments": {"reason": "technical_system_error", "summary": summary.strip()},
        }],
        next_state={
            "prior_transfer_requests": 3,
            "completed_initial_calls": INITIAL_TOOLS,
            "regular_transfer_completed": True,
        },
    ))


if __name__ == "__main__":
    main()
