#!/usr/bin/env python3
"""Produce a safe next-action plan for the incident transfer protocol.

Read one JSON object from stdin and emit one JSON object on stdout.  This helper
only plans actions; it never calls banking tools or changes conversational state.
"""

import json
import re
import sys
from datetime import datetime
from typing import Any, Dict, Optional

DEADLINE = datetime(2025, 11, 15, 23, 59, 0)
FIRST_TOOL = "initial_transfer_to_human_agent_1822"
SECOND_TOOL = "initial_transfer_to_human_agent_0218"


def fail(status: str, message: str) -> Dict[str, Any]:
    return {
        "applicable": False,
        "status": status,
        "action": "stop",
        "message": message,
    }


def parse_est_time(value: Any) -> Optional[datetime]:
    """Parse the documented EST timestamp form without relying on host timezone data."""
    if not isinstance(value, str):
        return None
    match = re.fullmatch(
        r"\s*(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2})(?::(\d{2}))?\s+EST\s*",
        value,
    )
    if not match:
        return None
    seconds = match.group(3) or "00"
    try:
        return datetime.strptime(
            match.group(1) + " " + match.group(2) + ":" + seconds,
            "%Y-%m-%d %H:%M:%S",
        )
    except ValueError:
        return None


def main(payload: Dict[str, Any]) -> Dict[str, Any]:
    required_booleans = (
        "paid_statement",
        "deducted_from_checking",
        "not_reflected_in_card_balance",
        "explicit_human_request",
        "first_initial_completed",
        "second_initial_completed",
    )
    for field in required_booleans:
        if not isinstance(payload.get(field), bool):
            return fail("insufficient_information", "Missing or non-boolean field: " + field)

    prior = payload.get("prior_transfer_requests")
    if isinstance(prior, bool) or not isinstance(prior, int) or prior < 0:
        return fail(
            "insufficient_information",
            "prior_transfer_requests must be a nonnegative integer measured before this message.",
        )

    now = parse_est_time(payload.get("current_time"))
    if now is None:
        return fail(
            "insufficient_information",
            "current_time must be a valid YYYY-MM-DD HH:MM[:SS] EST timestamp.",
        )
    if now > DEADLINE:
        return {
            "applicable": False,
            "status": "outside_incident_window",
            "action": "standard_handling",
            "message": "The incident deadline has passed; do not use incident transfer tools.",
        }

    symptoms = (
        payload["paid_statement"]
        and payload["deducted_from_checking"]
        and payload["not_reflected_in_card_balance"]
    )
    if not symptoms:
        return {
            "applicable": False,
            "status": "symptoms_do_not_match",
            "action": "standard_handling",
            "message": "Do not use this incident protocol or its discoverable tools.",
        }

    first_done = payload["first_initial_completed"]
    second_done = payload["second_initial_completed"]
    if second_done and not first_done:
        return fail("invalid_state", "The second initial sequence cannot precede the first.")
    if prior == 0 and (first_done or second_done):
        return fail("invalid_state", "Completed initial steps conflict with zero prior requests.")
    if prior == 1 and (not first_done or second_done):
        return fail("invalid_state", "Stage two requires only the first initial sequence completed.")
    if prior == 2 and (not first_done or not second_done):
        return fail("invalid_state", "Stage three requires both initial sequences completed.")

    if not payload["explicit_human_request"]:
        return {
            "applicable": True,
            "status": "awaiting_explicit_transfer_request",
            "action": "acknowledge_and_offer_human_transfer",
            "message": "Do not call an incident transfer tool until the customer explicitly requests a human.",
        }

    if prior == 0:
        return {
            "applicable": True,
            "status": "ok",
            "action": "first_initial_transfer",
            "unlock_agent_tool": FIRST_TOOL,
            "call_agent_tool": FIRST_TOOL,
            "call_arguments": {},
        }
    if prior == 1:
        return {
            "applicable": True,
            "status": "ok",
            "action": "second_initial_transfer",
            "unlock_agent_tool": SECOND_TOOL,
            "call_agent_tool": SECOND_TOOL,
            "call_arguments": {},
        }
    if prior == 2:
        return {
            "applicable": True,
            "status": "ok",
            "action": "regular_human_transfer",
            "transfer_reason": "specialized_department_required",
            "message": "Call the normal transfer tool once and provide a non-identifying incident summary.",
        }

    return {
        "applicable": True,
        "status": "transfer_sequence_already_advanced",
        "action": "stop",
        "message": "Do not replay incident stages; use the destination or normal platform flow.",
    }


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        if not isinstance(raw, dict):
            raise ValueError("Input must be a JSON object.")
        result = main(raw)
    except (ValueError, json.JSONDecodeError) as exc:
        result = fail("insufficient_information", str(exc))
    print(json.dumps(result, sort_keys=True))
