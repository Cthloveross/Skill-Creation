#!/usr/bin/env python3
"""Plan, but never execute, a staged incident human-transfer action.

Input: one JSON object on stdin, as documented in SKILL.md.
Output: one JSON object on stdout.  Invalid input and unsafe state return a
stop action rather than raising or selecting a later transfer stage.
"""
import json
import re
import sys
from datetime import datetime

DEADLINE = datetime(2025, 11, 15, 23, 59, 0)
FIRST = "initial_transfer_to_human_agent_1822"
SECOND = "initial_transfer_to_human_agent_0218"
BOOLEAN_FIELDS = (
    "paid_statement", "deducted_from_checking", "not_reflected_in_card_balance",
    "explicit_human_request", "first_initial_completed", "second_initial_completed",
)


def stop(status, message):
    return {"applicable": False, "status": status, "action": "stop", "message": message}


def parse_time(value):
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r"\s*(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2})(?::(\d{2}))?\s+EST\s*", value)
    if not match:
        return None
    try:
        return datetime.strptime(
            "%s %s:%s" % (match.group(1), match.group(2), match.group(3) or "00"),
            "%Y-%m-%d %H:%M:%S",
        )
    except ValueError:
        return None


def plan(data):
    if not isinstance(data, dict):
        return stop("insufficient_information", "Input must be a JSON object.")
    for key in BOOLEAN_FIELDS:
        if type(data.get(key)) is not bool:
            return stop("insufficient_information", "Missing or non-boolean field: " + key)
    prior = data.get("prior_transfer_requests")
    if type(prior) is not int or prior < 0:
        return stop("insufficient_information", "prior_transfer_requests must be a nonnegative integer.")
    now = parse_time(data.get("current_time"))
    if now is None:
        return stop("insufficient_information", "current_time must be YYYY-MM-DD HH:MM[:SS] EST.")
    if now > DEADLINE:
        return {"applicable": False, "status": "outside_incident_window", "action": "standard_handling"}
    if not (data["paid_statement"] and data["deducted_from_checking"] and data["not_reflected_in_card_balance"]):
        return {"applicable": False, "status": "symptoms_do_not_match", "action": "standard_handling"}

    first, second = data["first_initial_completed"], data["second_initial_completed"]
    if second and not first:
        return stop("invalid_state", "Second initial stage cannot precede first initial stage.")
    if prior == 0 and (first or second):
        return stop("invalid_state", "Completed stage conflicts with zero earlier requests.")
    if prior == 1 and (not first or second):
        return stop("invalid_state", "Second request requires exactly the first stage complete.")
    if prior == 2 and (not first or not second):
        return stop("invalid_state", "Third request requires both initial stages complete.")

    if not data["explicit_human_request"]:
        return {"applicable": True, "status": "awaiting_explicit_transfer_request", "action": "acknowledge_and_offer_human_transfer"}
    if prior == 0:
        return {"applicable": True, "status": "ok", "action": "first_initial_transfer", "unlock_agent_tool": FIRST, "call_agent_tool": FIRST, "call_arguments": {}}
    if prior == 1:
        return {"applicable": True, "status": "ok", "action": "second_initial_transfer", "unlock_agent_tool": SECOND, "call_agent_tool": SECOND, "call_arguments": {}}
    if prior == 2:
        return {"applicable": True, "status": "ok", "action": "regular_human_transfer", "transfer_reason": "specialized_department_required"}
    return {"applicable": True, "status": "transfer_sequence_already_advanced", "action": "stop"}


def main():
    try:
        data = json.load(sys.stdin)
        result = plan(data)
    except (ValueError, json.JSONDecodeError) as exc:
        result = stop("insufficient_information", str(exc))
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
