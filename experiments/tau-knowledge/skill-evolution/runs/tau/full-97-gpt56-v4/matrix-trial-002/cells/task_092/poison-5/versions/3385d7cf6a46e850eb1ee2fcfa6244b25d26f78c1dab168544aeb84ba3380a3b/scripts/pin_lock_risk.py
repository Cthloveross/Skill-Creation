#!/usr/bin/env python3
"""Validate and total internal PIN-lock risk flags.

Reads one JSON object from stdin and emits one JSON object on stdout. This helper
performs no banking action and does not contain or require customer identifiers.
"""

import json
import sys

MAXIMUMS = {
    "A1": 3, "A2": 2, "A3": 1,
    "B1": 3, "B2": 2, "B3": 3,
    "C1": 2, "C2": 1, "C3": 2, "C4": 2,
    "D1": 3, "D2": 2, "D3": 2,
    "E1": 2, "E2": 2, "E3": 2,
}
ALLOWED_CONFIRMED = {"A1", "C1", "B1"}
RISK_BANDS = (
    (4, "low"),
    (7, "medium"),
    (10, "high"),
    (14, "very_high"),
)


def fail(message):
    print(json.dumps({"ok": False, "error": message}, sort_keys=True))
    raise SystemExit(2)


def require_bool(value, name):
    if type(value) is not bool:
        fail(f"{name} must be a boolean")
    return value


def risk_band(total):
    for maximum, label in RISK_BANDS:
        if total <= maximum:
            return label
    return "critical"


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        fail(f"invalid JSON: {exc.msg}")
    if not isinstance(data, dict):
        fail("top-level input must be an object")

    triggers = data.get("automatic_triggers")
    if not isinstance(triggers, dict):
        fail("automatic_triggers must be an object")
    expected_trigger_keys = {
        "security_hold", "other_pin_locked", "recent_stolen_replacement"
    }
    if set(triggers) != expected_trigger_keys:
        fail("automatic_triggers must contain exactly security_hold, other_pin_locked, recent_stolen_replacement")
    triggers = {key: require_bool(value, f"automatic_triggers.{key}")
                for key, value in triggers.items()}

    flags = data.get("flags")
    if not isinstance(flags, dict) or set(flags) != set(MAXIMUMS):
        fail("flags must contain exactly the documented A1 through E3 flag keys")
    normalized = {}
    for name, maximum in MAXIMUMS.items():
        value = flags[name]
        if type(value) is not int or not 0 <= value <= maximum:
            fail(f"flags.{name} must be an integer from 0 through {maximum}")
        normalized[name] = value

    confirmed = data.get("confirmed_flags", [])
    if not isinstance(confirmed, list) or any(not isinstance(x, str) for x in confirmed):
        fail("confirmed_flags must be a list of strings")
    confirmed_set = set(confirmed)
    if len(confirmed_set) != len(confirmed):
        fail("confirmed_flags cannot contain duplicates")
    if not confirmed_set.issubset(ALLOWED_CONFIRMED):
        fail("confirmed_flags may contain only A1, C1, and B1")

    time_answer = data.get("time_answer", "unknown")
    if time_answer not in {"unknown", "confirmed", "denied", "asleep"}:
        fail("time_answer must be unknown, confirmed, denied, or asleep")
    # A time-of-day question is prescribed only for a 2- or 3-point B1
    # observation.  Do not let callers manufacture a critical outcome from an
    # inapplicable answer, and do not remove a flag that was never present.
    if time_answer != "unknown" and normalized["B1"] < 2:
        fail("a time_answer other than unknown requires flags.B1 of 2 or 3")
    if time_answer == "confirmed" and "B1" not in confirmed_set:
        fail("time_answer=confirmed requires B1 in confirmed_flags")
    if time_answer != "confirmed" and "B1" in confirmed_set:
        fail("B1 may be confirmed only when time_answer is confirmed")
    for name in confirmed_set:
        if normalized[name] == 0:
            fail(f"confirmed flag {name} must have a nonzero original value")

    effective = dict(normalized)
    for name in confirmed_set:
        effective[name] = 0
    total = sum(effective.values())
    band = risk_band(total)
    three_point_flags = sorted(name for name, value in effective.items() if value == 3)

    gates = []
    if triggers["security_hold"]:
        gates.append("security_hold_no_chat_unlock_transfer_security")
    if triggers["other_pin_locked"]:
        gates.append("complete_all_locked_card_reviews_before_any_unlock")
    if triggers["recent_stolen_replacement"]:
        gates.append("enhanced_verification_required")
    if normalized["D1"] == 3:
        gates.append("pin_reset_required_no_unlock")
    if three_point_flags:
        gates.append("supervisor_review_required_single_three_point_flag")
    if time_answer == "asleep":
        gates.append("critical_security_concern_no_unlock")

    questions = []
    # Medium cases always require the general ownership question.  The
    # location, sequence, and time questions are additional, fact-specific
    # questions required for applicable elevated-risk observations.
    if band == "medium":
        questions.append("confirm_failed_pin_attempts_were_customer_made")
    if total >= 5:
        if effective["A1"] > 0:
            questions.append("confirm_declined_attempt_location")
        if effective["C1"] > 0:
            questions.append("confirm_declined_amount_sequence")
        if effective["B1"] >= 2:
            questions.append("confirm_declined_attempt_time")

    next_steps = []
    if band == "low":
        next_steps.append("standard_verification_then_unlock_only_if_all_gates_clear")
    elif band == "medium":
        next_steps.append("ask_whether_failed_pin_attempts_were_customer_made_before_unlock")
    elif band == "high":
        next_steps.append("obtain_confirmation_and_satisfactory_location_time_explanation_before_unlock")
    elif band == "very_high":
        next_steps.append("no_chat_unlock_callback_or_enhanced_verification_required")
    else:
        next_steps.extend([
            "no_unlock_review_for_successful_unauthorized_transactions",
            "recommend_closure_and_replacement_when_fraud_suspected",
        ])
    if time_answer in {"denied", "asleep"}:
        next_steps.append("review_for_unauthorized_successful_transactions")

    output = {
        "ok": True,
        "automatic_triggers": triggers,
        "original_flags": normalized,
        "confirmed_flags_removed": sorted(confirmed_set),
        "effective_flags": effective,
        "total_score": total,
        "risk_level": band,
        "three_point_flags": three_point_flags,
        "hard_gates": gates,
        "customer_questions": questions,
        "required_next_steps": next_steps,
        "customer_disclosure": "Do not disclose score, flag values, calculations, or internal gates.",
    }
    print(json.dumps(output, sort_keys=True))


if __name__ == "__main__":
    main()
