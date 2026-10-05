#!/usr/bin/env python3
"""Create a safe, deterministic plan for the payment-reflection incident protocol.

Reads one JSON object from stdin and writes one JSON object to stdout. This program only
plans external actions; it does not call tools or modify any account.
"""

import json
import sys
from datetime import datetime
from typing import Any, Dict, List, Tuple

CUTOFF = datetime(2025, 11, 15, 23, 59, 59)
FIRST_TOOL = "initial_transfer_to_human_agent_1822"
SECOND_TOOL = "initial_transfer_to_human_agent_0218"


def emit(value: Dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(value, separators=(",", ":")) + "\n")


def fail(message: str) -> None:
    emit({"valid": False, "error": message, "actions": []})


def require_bool(container: Dict[str, Any], key: str) -> bool:
    value = container.get(key)
    if type(value) is not bool:
        raise ValueError("%s must be a boolean" % key)
    return value


def parse_est(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("current_time must be a string in YYYY-MM-DD HH:MM:SS EST format")
    suffix = " EST"
    if not value.endswith(suffix):
        raise ValueError("current_time must use the EST timezone label")
    try:
        return datetime.strptime(value[: -len(suffix)], "%Y-%m-%d %H:%M:%S")
    except ValueError as exc:
        raise ValueError("current_time must be in YYYY-MM-DD HH:MM:SS EST format") from exc


def discoverable_pair(tool_name: str) -> List[Dict[str, Any]]:
    return [
        {
            "tool": "unlock_discoverable_agent_tool",
            "arguments": {"agent_tool_name": tool_name},
        },
        {
            "tool": "call_discoverable_agent_tool",
            "arguments": {"agent_tool_name": tool_name, "arguments": "{}"},
        },
    ]


def validate_state(prior: int, completed: Dict[str, Any]) -> Tuple[bool, bool, bool]:
    if type(prior) is not int or prior < 0:
        raise ValueError("prior_incident_transfer_requests must be a nonnegative integer")
    first = require_bool(completed, "first_initial_tool_completed")
    second = require_bool(completed, "second_initial_tool_completed")
    regular = require_bool(completed, "regular_transfer_completed")

    # A completed stage must exactly correspond to an already processed request.
    if first != (prior >= 1):
        raise ValueError("first_initial_tool_completed is inconsistent with prior request count")
    if second != (prior >= 2):
        raise ValueError("second_initial_tool_completed is inconsistent with prior request count")
    if regular and prior < 3:
        raise ValueError("regular_transfer_completed requires at least three prior requests")
    return first, second, regular


def main() -> None:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("input must be a JSON object")

        symptoms = data.get("symptoms")
        if not isinstance(symptoms, dict):
            raise ValueError("symptoms must be an object")
        paid = require_bool(symptoms, "statement_payment_made")
        deducted = require_bool(symptoms, "deducted_from_checking")
        missing = require_bool(symptoms, "missing_from_statement_balance")
        transfer_requested = require_bool(data, "human_transfer_requested")
        now = parse_est(data.get("current_time"))

        completed = data.get("completed")
        if not isinstance(completed, dict):
            raise ValueError("completed must be an object")
        prior = data.get("prior_incident_transfer_requests", 0)
        first_done, second_done, regular_done = validate_state(prior, completed)
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        fail(str(exc))
        return

    incident_applicable = paid and deducted and missing
    within_window = now <= CUTOFF
    base: Dict[str, Any] = {
        "valid": True,
        "incident_applicable": incident_applicable,
        "within_incident_window": within_window,
        "actions": [],
    }

    if not incident_applicable or not within_window:
        base.update(
            {
                "status": "standard_handling_required",
                "customer_message": None,
                "instructions": "Do not use this incident protocol; follow applicable standard handling.",
            }
        )
        emit(base)
        return

    if not transfer_requested:
        base.update(
            {
                "status": "awaiting_explicit_human_transfer_request",
                "customer_message": "I understand this is urgent. If you'd like, I can connect you with a human specialist.",
                "instructions": "Do not troubleshoot, verify identity, inspect accounts, or call transfer tools until the customer explicitly requests a human.",
            }
        )
        emit(base)
        return

    request_number = prior + 1
    if request_number == 1:
        # validate_state guarantees first_done is false here.
        base.update(
            {
                "status": "process_first_transfer_request",
                "request_number": request_number,
                "actions": discoverable_pair(FIRST_TOOL),
                "customer_message": "I understand you'd like to speak with a human specialist about this issue. Let me initiate that process for you now.",
                "state_update_after_success": {
                    "prior_incident_transfer_requests": 1,
                    "first_initial_tool_completed": True,
                },
            }
        )
    elif request_number == 2:
        if not first_done or second_done:
            fail("second transfer stage prerequisites are inconsistent")
            return
        base.update(
            {
                "status": "process_second_transfer_request",
                "request_number": request_number,
                "actions": discoverable_pair(SECOND_TOOL),
                "customer_message": "I hear your concern about the urgency. I'm continuing to process your transfer request.",
                "state_update_after_success": {
                    "prior_incident_transfer_requests": 2,
                    "second_initial_tool_completed": True,
                },
            }
        )
    elif regular_done:
        base.update(
            {
                "status": "regular_transfer_already_completed",
                "request_number": request_number,
                "customer_message": None,
                "instructions": "Do not issue a duplicate transfer; the normal transfer is already recorded as complete.",
            }
        )
    else:
        if not first_done or not second_done:
            fail("regular transfer is prohibited until both initial incident tools are completed")
            return
        base.update(
            {
                "status": "process_regular_human_transfer",
                "request_number": request_number,
                "actions": [
                    {
                        "tool": "transfer_to_human_agents",
                        "arguments": {
                            "reason": "technical_system_error",
                            "summary": "Customer reports a credit-card statement payment was deducted from checking but is not reflected in the statement balance; both incident transfer stages were completed.",
                        },
                    }
                ],
                "customer_message": "I'm now connecting you with a human specialist who can resolve this for you.",
                "state_update_after_success": {
                    "prior_incident_transfer_requests": request_number,
                    "regular_transfer_completed": True,
                },
            }
        )

    emit(base)


if __name__ == "__main__":
    main()
