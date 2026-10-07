#!/usr/bin/env python3
"""Validate and total normalized PIN-lock fraud flags.

Read one JSON object from stdin:
{
  "automatic_triggers": {
    "security_hold": true|false,
    "other_cards_locked": true|false,
    "recent_stolen_replacement": true|false
  },
  "flags": {"A1": 0, ..., "E3": 0}
}
Every flag must be supplied as an integer in its policy range.  A missing or
null flag makes the assessment incomplete.  The JSON result is an internal
decision aid; it does not contact a bank service or authorize an action.
"""
import json
import sys

CAPS = {
    "A1": 3, "A2": 2, "A3": 1,
    "B1": 3, "B2": 2, "B3": 3,
    "C1": 2, "C2": 1, "C3": 2, "C4": 2,
    "D1": 3, "D2": 2, "D3": 2,
    "E1": 2, "E2": 2, "E3": 2,
}
TRIGGERS = ("security_hold", "other_cards_locked", "recent_stolen_replacement")


def fail(message):
    print(json.dumps({"error": message}, sort_keys=True))
    raise SystemExit(2)


def risk_band(total):
    if total <= 4:
        return "low"
    if total <= 7:
        return "medium"
    if total <= 10:
        return "high"
    if total <= 14:
        return "very_high"
    return "critical"


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, TypeError) as exc:
        fail("input must be a JSON object: " + str(exc))
    if not isinstance(data, dict):
        fail("input must be a JSON object")
    flags = data.get("flags")
    triggers = data.get("automatic_triggers", {})
    if not isinstance(flags, dict) or not isinstance(triggers, dict):
        fail("flags and automatic_triggers must be JSON objects")
    unknown_flags = sorted(set(flags) - set(CAPS))
    unknown_triggers = sorted(set(triggers) - set(TRIGGERS))
    if unknown_flags:
        fail("unknown flag codes: " + ", ".join(unknown_flags))
    if unknown_triggers:
        fail("unknown automatic trigger codes: " + ", ".join(unknown_triggers))

    normalized_triggers = {}
    for key in TRIGGERS:
        if key not in triggers:
            fail("missing automatic trigger: " + key)
        value = triggers[key]
        if not isinstance(value, bool):
            fail(key + " must be true or false")
        normalized_triggers[key] = value

    values, missing = {}, []
    for code, cap in CAPS.items():
        value = flags.get(code)
        if value is None:
            missing.append(code)
        elif isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= cap:
            fail(f"{code} must be an integer from 0 to {cap}, or null")
        else:
            values[code] = value

    complete = not missing
    total = sum(values.values()) if complete else None
    band = risk_band(total) if complete else "undetermined"
    three_point = sorted(code for code, value in values.items() if value == 3)

    # These are concurrent gates, deliberately not a single lossy recommendation.
    gates = []
    if normalized_triggers["security_hold"]:
        gates.append("security_team_transfer_no_chat_unlock")
    if not complete:
        gates.append("complete_evidence_before_decision")
    if normalized_triggers["other_cards_locked"]:
        gates.append("finish_all_locked_card_investigations_before_any_unlock")
    if normalized_triggers["recent_stolen_replacement"]:
        gates.append("enhanced_verification_required_before_unlock")
    # A known hard flag remains a gate even when another flag is unavailable.
    if values.get("D1") == 3:
        gates.append("pin_reset_required_no_unlock")
    if three_point:
        gates.append("supervisor_review_required")
    if complete:
        if band == "critical":
            gates.append("no_unlock_review_unauthorized_activity_and_replacement")
        elif band == "very_high":
            gates.append("no_unlock_on_call_callback_or_enhanced_verification")
        elif band == "high":
            gates.append("specific_location_time_confirmation_and_satisfactory_explanation_required")
        elif band == "medium":
            gates.append("failed_attempt_ownership_confirmation_required")
        else:
            gates.append("standard_verification_required")

    result = {
        "assessment_complete": complete,
        "missing_flags": missing,
        "total_score": total,
        "risk_level": band,
        "single_three_point_flags": three_point,
        "automatic_triggers": normalized_triggers,
        "required_internal_gates": gates,
        "unlock_eligible_after_gates": complete and not any(
            gate in gates for gate in (
                "security_team_transfer_no_chat_unlock",
                "finish_all_locked_card_investigations_before_any_unlock",
                "pin_reset_required_no_unlock",
                "supervisor_review_required",
                "no_unlock_review_unauthorized_activity_and_replacement",
                "no_unlock_on_call_callback_or_enhanced_verification",
            )
        ),
    }
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
