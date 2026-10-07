#!/usr/bin/env python3
"""Plan the temporary payment-reflection incident transfer sequence.

Reads one JSON object from stdin and emits one JSON object on stdout.  This
script only plans actions; an executor must perform the returned tool calls.
"""

import json
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

CUTOFF = datetime(2025, 11, 15, 23, 59, 0)
FIRST_TOOL = "initial_transfer_to_human_agent_1822"
SECOND_TOOL = "initial_transfer_to_human_agent_0218"
EXPECTED_INITIAL = [FIRST_TOOL, SECOND_TOOL]


def emit(payload: Dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def result(status: str, message: str, **extra: Any) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "status": status,
        "assistant_message": message,
        "internal_actions": [],
        "next_state": None,
    }
    payload.update(extra)
    return payload


def parse_est_timestamp(value: Any) -> Tuple[Optional[datetime], Optional[str]]:
    if not isinstance(value, str):
        return None, "current_time must be a string in YYYY-MM-DD HH:MM:SS EST format"
    try:
        date_part, zone = value.rsplit(" ", 1)
    except ValueError:
        return None, "current_time must include an explicit EST suffix"
    if zone != "EST":
        return None, "current_time must use EST for this incident cutoff"
    try:
        return datetime.strptime(date_part, "%Y-%m-%d %H:%M:%S"), None
    except ValueError:
        return None, "current_time must match YYYY-MM-DD HH:MM:SS EST"


def is_boolean_or_none(value: Any) -> bool:
    return value is None or isinstance(value, bool)


def validate_state(data: Dict[str, Any]) -> Tuple[Optional[int], Optional[List[str]], Optional[bool], Optional[str]]:
    prior = data.get("prior_transfer_requests", 0)
    calls = data.get("completed_initial_calls", [])
    completed = data.get("regular_transfer_completed", False)
    if isinstance(prior, bool) or not isinstance(prior, int) or prior < 0:
        return None, None, None, "prior_transfer_requests must be a non-negative integer"
    if not isinstance(calls, list) or not all(isinstance(item, str) for item in calls):
        return None, None, None, "completed_initial_calls must be a list of tool names"
    if not isinstance(completed, bool):
        return None, None, None, "regular_transfer_completed must be boolean"
    if calls not in ([], [FIRST_TOOL], EXPECTED_INITIAL):
        return None, None, None, "completed_initial_calls is not the required exact ordered prefix"
    if prior == 0 and calls != []:
        return None, None, None, "first-stage state is inconsistent with completed initial calls"
    if prior == 1 and calls != [FIRST_TOOL]:
        return None, None, None, "second-stage state requires only the first initial call"
    if prior == 2 and calls != EXPECTED_INITIAL:
        return None, None, None, "third-stage state requires both initial calls"
    if prior > 2 and not completed:
        return None, None, None, "a request count above two requires a recorded completed regular transfer"
    if completed and (prior < 3 or calls != EXPECTED_INITIAL):
        return None, None, None, "completed regular-transfer state is inconsistent"
    return prior, calls, completed, None


def unlock_action(tool_name: str) -> Dict[str, Any]:
    return {
        "tool": "unlock_discoverable_agent_tool",
        "arguments": {"agent_tool_name": tool_name},
    }


def call_initial_action(tool_name: str) -> Dict[str, Any]:
    return {
        "tool": "call_discoverable_agent_tool",
        "arguments": {"agent_tool_name": tool_name, "arguments": "{}"},
    }


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, TypeError):
        emit(result("invalid_input", "Unable to plan the incident protocol because the supplied data is not valid JSON."))
        return
    if not isinstance(data, dict):
        emit(result("invalid_input", "Unable to plan the incident protocol because the input must be a JSON object."))
        return

    now, time_error = parse_est_timestamp(data.get("current_time"))
    if time_error:
        emit(result("invalid_input", "Obtain the current EST time before applying this incident protocol.", error=time_error))
        return
    assert now is not None
    if now > CUTOFF:
        emit(result("not_applicable", "This temporary incident protocol has ended; use the applicable standard procedure.", cutoff="2025-11-15 23:59:00 EST"))
        return

    symptoms = data.get("symptoms")
    if not isinstance(symptoms, dict):
        emit(result("invalid_input", "Symptom information must be supplied as an object."))
        return
    keys = ("paid_statement", "deducted_from_checking", "not_reflected_in_statement_balance")
    values = [symptoms.get(key) for key in keys]
    if not all(is_boolean_or_none(value) for value in values):
        emit(result("invalid_input", "Each incident symptom must be true, false, or null."))
        return
    missing = [key for key, value in zip(keys, values) if value is None]
    if missing:
        emit(result(
            "needs_symptom_confirmation",
            "To determine whether this incident transfer protocol applies, please confirm only the missing payment symptom(s).",
            missing_symptoms=missing,
        ))
        return
    if not all(values):
        emit(result("not_applicable", "The reported issue does not meet all conditions for this temporary incident protocol."))
        return

    prior, calls, regular_done, state_error = validate_state(data)
    if state_error:
        emit(result("invalid_state", "Do not perform a transfer action until the incident transfer state is reconciled.", error=state_error))
        return
    assert prior is not None and calls is not None and regular_done is not None

    requested = data.get("user_requested_transfer", False)
    if not isinstance(requested, bool):
        emit(result("invalid_input", "user_requested_transfer must be boolean."))
        return
    if regular_done:
        emit(result("already_completed", "A human-specialist transfer has already been initiated for this issue."))
        return
    if not requested:
        emit(result(
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
        emit(result(
            "ready",
            "I understand you'd like to speak with a human specialist about this issue. Let me initiate that process for you now.",
            internal_actions=[unlock_action(FIRST_TOOL), call_initial_action(FIRST_TOOL)],
            next_state={
                "prior_transfer_requests": 1,
                "completed_initial_calls": [FIRST_TOOL],
                "regular_transfer_completed": False,
            },
        ))
        return
    if prior == 1:
        emit(result(
            "ready",
            "I hear your concern about the urgency. I'm continuing to process your transfer request.",
            internal_actions=[unlock_action(SECOND_TOOL), call_initial_action(SECOND_TOOL)],
            next_state={
                "prior_transfer_requests": 2,
                "completed_initial_calls": EXPECTED_INITIAL,
                "regular_transfer_completed": False,
            },
        ))
        return

    summary = data.get("issue_summary")
    if not isinstance(summary, str) or not summary.strip():
        summary = (
            "Customer reports a credit-card statement payment was deducted from checking "
            "but remains unpaid on the statement balance during the payment-reflection backend incident."
        )
    emit(result(
        "ready",
        "I'm now connecting you with a human specialist who can resolve this for you.",
        internal_actions=[{
            "tool": "transfer_to_human_agents",
            "arguments": {"reason": "technical_system_error", "summary": summary.strip()},
        }],
        next_state={
            "prior_transfer_requests": 3,
            "completed_initial_calls": EXPECTED_INITIAL,
            "regular_transfer_completed": True,
        },
    ))


if __name__ == "__main__":
    main()
