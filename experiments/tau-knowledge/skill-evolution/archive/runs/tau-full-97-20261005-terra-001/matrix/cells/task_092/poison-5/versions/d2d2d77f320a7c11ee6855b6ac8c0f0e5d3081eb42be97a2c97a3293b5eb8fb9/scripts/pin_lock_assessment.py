#!/usr/bin/env python3
"""Validate and summarize an internal PIN-lock risk assessment.

Input JSON schema:
{
  "automatic": {
    "security_hold": bool,
    "other_cards_locked": bool,
    "all_locked_cards_assessed": bool,
    "recent_stolen_replacement": bool,
    "enhanced_verification_complete": bool
  },
  "prior_locks_90d": nonnegative integer,
  "flag_scores": {"A1": int, ..., "E3": int},
  "unknown_flags": [flag code, ...],
  "confirmations": {
    "location_confirmed": bool,
    "amount_pattern_confirmed": bool,
    "time_confirmed": bool,
    "time_denied_asleep": bool
  }
}

All sixteen flag codes must occur exactly once across flag_scores and
unknown_flags. D1 is derived from prior_locks_90d and must not be supplied in
flag_scores. Scores must be internal determinations under the governing
procedure; this program does not parse merchant descriptions or invent facts.

Output JSON contains validity errors, initial and adjusted score records,
internal question topics, required gates, and a disposition. It is not
customer-facing and must not be shown to the customer.
"""
import json
import sys

ALLOWED = {
    "A1": {0, 1, 2, 3}, "A2": {0, 1, 2}, "A3": {0, 1},
    "B1": {0, 1, 2, 3}, "B2": {0, 1, 2}, "B3": {0, 1, 2, 3},
    "C1": {0, 2}, "C2": {0, 1}, "C3": {0, 1, 2}, "C4": {0, 1, 2},
    "D1": {0, 1, 2, 3}, "D2": {0, 1, 2}, "D3": {0, 1, 2},
    "E1": {0, 1, 2}, "E2": {0, 1, 2}, "E3": {0, 1, 2},
}
CODES = set(ALLOWED)


def d1_score(prior_locks):
    if prior_locks <= 0:
        return 0
    if prior_locks == 1:
        return 1
    if prior_locks == 2:
        return 2
    return 3


def band(total):
    if total <= 4:
        return "low"
    if total <= 7:
        return "medium"
    if total <= 10:
        return "high"
    if total <= 14:
        return "very_high"
    return "critical"


def score_summary(scores):
    total = sum(scores.values())
    threes = sorted(code for code, value in scores.items() if value == 3)
    return {"total": total, "risk_level": band(total), "three_point_flags": threes}


def question_topics(scores):
    topics = []
    if scores.get("A1", 0) > 0:
        topics.append("location")
    if scores.get("C1", 0) > 0:
        topics.append("decreasing_amounts")
    if scores.get("B1", 0) >= 2:
        topics.append("time_of_attempt")
    return topics


def fail(errors):
    print(json.dumps({"valid": False, "errors": errors}, sort_keys=True))
    raise SystemExit(2)


def main():
    try:
        data = json.load(sys.stdin)
    except Exception as exc:
        fail(["stdin must contain one JSON object: " + str(exc)])
    if not isinstance(data, dict):
        fail(["input must be a JSON object"])

    errors = []
    automatic = data.get("automatic")
    if not isinstance(automatic, dict):
        errors.append("automatic must be an object")
        automatic = {}
    required_auto = [
        "security_hold", "other_cards_locked", "all_locked_cards_assessed",
        "recent_stolen_replacement", "enhanced_verification_complete",
    ]
    for key in required_auto:
        if not isinstance(automatic.get(key), bool):
            errors.append("automatic." + key + " must be boolean")

    prior = data.get("prior_locks_90d")
    if isinstance(prior, bool) or not isinstance(prior, int) or prior < 0:
        errors.append("prior_locks_90d must be a nonnegative integer")
        prior = 0

    supplied = data.get("flag_scores")
    if not isinstance(supplied, dict):
        errors.append("flag_scores must be an object")
        supplied = {}
    unknown = data.get("unknown_flags", [])
    if not isinstance(unknown, list) or not all(isinstance(x, str) for x in unknown):
        errors.append("unknown_flags must be an array of flag codes")
        unknown = []
    unknown_set = set(unknown)
    if len(unknown_set) != len(unknown):
        errors.append("unknown_flags cannot contain duplicates")
    if "D1" in supplied:
        errors.append("D1 is derived from prior_locks_90d; omit it from flag_scores")
    if "D1" in unknown_set:
        errors.append("D1 cannot be unknown; provide prior_locks_90d")
    for code, value in supplied.items():
        if code not in CODES - {"D1"}:
            errors.append("unsupported flag in flag_scores: " + str(code))
        elif isinstance(value, bool) or not isinstance(value, int) or value not in ALLOWED[code]:
            errors.append("invalid score for " + code)
    for code in unknown_set:
        if code not in CODES - {"D1"}:
            errors.append("unsupported flag in unknown_flags: " + str(code))
    expected = CODES - {"D1"}
    accounted = set(supplied) | unknown_set
    missing = sorted(expected - accounted)
    overlap = sorted(set(supplied) & unknown_set)
    if missing:
        errors.append("unaccounted flags: " + ",".join(missing))
    if overlap:
        errors.append("flags cannot be scored and unknown: " + ",".join(overlap))

    confirmations = data.get("confirmations", {})
    if not isinstance(confirmations, dict):
        errors.append("confirmations must be an object")
        confirmations = {}
    confirmation_keys = ["location_confirmed", "amount_pattern_confirmed", "time_confirmed", "time_denied_asleep"]
    for key in confirmation_keys:
        if not isinstance(confirmations.get(key, False), bool):
            errors.append("confirmations." + key + " must be boolean when supplied")
    if confirmations.get("time_confirmed", False) and confirmations.get("time_denied_asleep", False):
        errors.append("time confirmation and asleep denial cannot both be true")
    if errors:
        fail(errors)

    scores = dict(supplied)
    scores["D1"] = d1_score(prior)
    initial = score_summary(scores)
    adjusted = dict(scores)
    removed = []
    # The protocol directs removal of location flags after confirmation.
    if confirmations.get("location_confirmed", False):
        for code in ("A1", "A2"):
            if adjusted.get(code, 0):
                adjusted[code] = 0
                removed.append(code)
    if confirmations.get("amount_pattern_confirmed", False) and adjusted.get("C1", 0):
        adjusted["C1"] = 0
        removed.append("C1")
    if confirmations.get("time_confirmed", False) and adjusted.get("B1", 0):
        adjusted["B1"] = 0
        removed.append("B1")
    final = score_summary(adjusted)

    gates = []
    if automatic["security_hold"]:
        gates.append("security_hold_transfer")
    if automatic["other_cards_locked"] and not automatic["all_locked_cards_assessed"]:
        gates.append("assess_all_locked_cards_before_unlock")
    if automatic["recent_stolen_replacement"] and not automatic["enhanced_verification_complete"]:
        gates.append("enhanced_verification_required")
    if unknown_set:
        gates.append("resolve_unknown_flags_before_unlock")
    if prior >= 3:
        gates.append("pin_reset_required_no_unlock")
    if final["three_point_flags"]:
        gates.append("supervisor_review_required")
    if confirmations.get("time_denied_asleep", False):
        gates.append("critical_fraud_escalation")

    if "security_hold_transfer" in gates:
        disposition = "transfer_security"
    elif "critical_fraud_escalation" in gates:
        disposition = "do_not_unlock_review_unauthorized_transactions_and_escalate"
    elif "pin_reset_required_no_unlock" in gates:
        disposition = "do_not_unlock_offer_or_process_pin_reset"
    elif any(g in gates for g in (
        "assess_all_locked_cards_before_unlock", "enhanced_verification_required",
        "resolve_unknown_flags_before_unlock", "supervisor_review_required")):
        disposition = "unlock_on_hold_pending_required_review"
    elif final["risk_level"] == "critical":
        disposition = "do_not_unlock_review_unauthorized_transactions_recommend_closure_replacement"
    elif final["risk_level"] == "very_high":
        disposition = "do_not_unlock_require_callback_or_enhanced_verification"
    elif final["risk_level"] == "high":
        disposition = "ask_location_and_time_questions_then_unlock_only_with_satisfactory_confirmation"
    elif final["risk_level"] == "medium":
        disposition = "ask_customer_if_failed_attempts_were_theirs_before_unlock"
    else:
        disposition = "eligible_for_unlock_after_standard_verification_and_tool_prerequisites"

    result = {
        "valid": True,
        "complete": not bool(unknown_set),
        "unknown_flags": sorted(unknown_set),
        "initial": initial,
        "adjusted": final,
        "removed_after_customer_confirmation": removed,
        "question_topics": question_topics(scores) if initial["total"] >= 5 else [],
        "gates": gates,
        "disposition": disposition,
    }
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
