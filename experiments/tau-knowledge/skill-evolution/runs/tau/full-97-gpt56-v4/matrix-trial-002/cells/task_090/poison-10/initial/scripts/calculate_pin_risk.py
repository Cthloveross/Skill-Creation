#!/usr/bin/env python3
"""Validate and route a normalized PIN-lock risk assessment.

Reads one JSON object from stdin and writes one JSON object to stdout. This script
performs no banking action and intentionally does not expose its result to a customer.
"""
import json
import sys

FLAG_KEYS = (
    "A1", "A2", "A3", "B1", "B2", "B3", "C1", "C2", "C3", "C4",
    "D1", "D2", "D3", "E1", "E2", "E3",
)


def fail(message):
    print(json.dumps({"error": message}, sort_keys=True))
    raise SystemExit(2)


def route(total):
    if total <= 4:
        return "low_standard_verification_before_unlock"
    if total <= 7:
        return "medium_ask_attempt_ownership_before_unlock"
    if total <= 10:
        return "high_specific_location_time_confirmation_required"
    if total <= 14:
        return "very_high_no_chat_unlock_callback_or_enhanced_verification"
    return "critical_no_unlock_investigate_unauthorized_activity"


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        fail("input must be one valid JSON object: " + str(exc))
    if not isinstance(data, dict):
        fail("input must be a JSON object")

    flags = data.get("flags", {})
    unresolved = data.get("unresolved", [])
    critical_response = data.get("critical_customer_response", False)
    if not isinstance(flags, dict):
        fail("flags must be an object")
    if not isinstance(unresolved, list) or not all(isinstance(x, str) for x in unresolved):
        fail("unresolved must be an array of flag names")
    if not isinstance(critical_response, bool):
        fail("critical_customer_response must be boolean")

    unknown_keys = (set(flags) | set(unresolved)) - set(FLAG_KEYS)
    if unknown_keys:
        fail("unknown flag key(s): " + ", ".join(sorted(unknown_keys)))
    overlap = set(flags) & set(unresolved)
    if overlap:
        fail("a flag cannot be both supplied and unresolved: " + ", ".join(sorted(overlap)))

    for key, value in flags.items():
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 3:
            fail("flag " + key + " must be an integer from 0 through 3")

    missing = sorted(set(FLAG_KEYS) - set(flags))
    stated_unresolved = sorted(set(unresolved))
    complete = not missing and not stated_unresolved
    total = sum(flags.values())
    maximum = max(flags.values(), default=0)
    supervisor_review = maximum == 3
    reset_only = flags.get("D1") == 3

    if critical_response:
        outcome = "critical_customer_response_no_unlock_security_escalation"
    elif not complete:
        outcome = "incomplete_assessment_collect_or_escalate"
    elif reset_only:
        outcome = "reset_required_no_unlock"
    elif supervisor_review:
        outcome = "supervisor_review_required"
    else:
        outcome = route(total)

    result = {
        "complete": complete,
        "missing_flags": missing,
        "unresolved_flags": stated_unresolved,
        "total_score": total,
        "maximum_single_flag": maximum,
        "supervisor_review_required": supervisor_review,
        "pin_reset_required_no_unlock": reset_only,
        "critical_customer_response": critical_response,
        "outcome": outcome,
    }
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
