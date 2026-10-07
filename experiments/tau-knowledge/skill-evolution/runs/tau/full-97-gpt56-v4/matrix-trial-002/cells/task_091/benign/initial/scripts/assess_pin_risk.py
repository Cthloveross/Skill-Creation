#!/usr/bin/env python3
"""Total normalized PIN-lock flags without exposing a customer-facing explanation.

Input JSON:
{
  "automatic_triggers": {"security_hold": bool, "other_cards_locked": bool,
                         "recent_stolen_replacement": bool},
  "flags": {"A1": 0..3, ..., "E3": 0..2}
}
A null or omitted flag is reported as missing; callers must not use a resulting
incomplete assessment to unlock a card. Output is a JSON decision aid only.
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


def fail(message):
    print(json.dumps({"error": message}))
    raise SystemExit(2)


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
    unknown = sorted(set(flags) - set(CAPS))
    if unknown:
        fail("unknown flag codes: " + ", ".join(unknown))

    values, missing = {}, []
    for code, cap in CAPS.items():
        value = flags.get(code)
        if value is None:
            missing.append(code)
            continue
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= cap:
            fail(f"{code} must be an integer from 0 to {cap}, or null")
        values[code] = value

    total = sum(values.values())
    if total <= 4:
        band = "low"
    elif total <= 7:
        band = "medium"
    elif total <= 10:
        band = "high"
    elif total <= 14:
        band = "very_high"
    else:
        band = "critical"

    security_hold = triggers.get("security_hold") is True
    other_locked = triggers.get("other_cards_locked") is True
    recent_stolen = triggers.get("recent_stolen_replacement") is True
    three_point = sorted(code for code, value in values.items() if value == 3)
    d1_reset = values.get("D1") == 3
    complete = not missing

    if security_hold:
        action = "security_team_transfer_no_chat_unlock"
    elif not complete:
        action = "complete_evidence_before_decision"
    elif d1_reset:
        action = "pin_reset_required_no_unlock"
    elif band == "critical":
        action = "no_unlock_review_unauthorized_activity_and_replacement"
    elif band == "very_high":
        action = "no_unlock_on_call_callback_or_enhanced_verification"
    elif three_point:
        action = "supervisor_review_before_any_unlock"
    elif other_locked:
        action = "finish_all_locked_card_investigations_before_unlock"
    elif band == "high":
        action = "specific_location_time_confirmation_and_satisfactory_explanation_required"
    elif band == "medium":
        action = "ask_failed_attempt_ownership_question_before_unlock"
    else:
        action = "standard_verification_then_eligible_for_unlock"

    result = {
        "assessment_complete": complete,
        "missing_flags": missing,
        "total_score": total if complete else None,
        "risk_level": band if complete else "undetermined",
        "single_three_point_flags": three_point,
        "automatic_triggers": {
            "security_hold": security_hold,
            "other_cards_locked": other_locked,
            "recent_stolen_replacement": recent_stolen,
        },
        "enhanced_verification_required": recent_stolen or (complete and band == "very_high"),
        "recommended_internal_action": action,
    }
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
