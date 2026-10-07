#!/usr/bin/env python3
"""Create a safe, non-executing plan for a card-security conversation.

Reads one JSON object from stdin and emits one JSON object to stdout. This helper
never calls bank tools and never asserts that any card action has occurred.
"""

import json
import sys
from typing import Any, Dict, List

SECURITY_INCIDENTS = {"lost", "stolen", "fraud_suspected"}
VALID_VERIFICATION = {"verified", "not_verified", "unknown"}


def as_string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def build_summary(data: Dict[str, Any]) -> str:
    incident = str(data.get("incident", "other")).strip().lower() or "other"
    cards = as_string_list(data.get("reported_cards"))
    completed = as_string_list(data.get("actions_completed"))
    verification = str(data.get("verification_status", "unknown")).strip().lower()
    if verification not in VALID_VERIFICATION:
        verification = "unknown"

    card_text = ", ".join(cards) if cards else "card(s) reported by customer"
    completed_text = ", ".join(completed) if completed else "none"
    closure = data.get("closure_authorized")
    if closure is True:
        closure_text = "authorized permanent debit-card closure"
    elif closure is False:
        closure_text = "has not authorized permanent debit-card closure"
    else:
        closure_text = "closure authorization is unknown"

    return (
        f"Customer reported a {incident} security incident involving {card_text}. "
        f"Verification status: {verification}. Actions completed: {completed_text}. "
        f"Customer {closure_text}. Human follow-up is needed for card-security review."
    )


def plan(data: Dict[str, Any]) -> Dict[str, Any]:
    incident = str(data.get("incident", "other")).strip().lower()
    wants_human = data.get("customer_requests_human") is True
    wants_freeze = data.get("temporary_freeze_requested") is True
    closure_authorized = data.get("closure_authorized") is True
    security = incident in SECURITY_INCIDENTS
    summary = build_summary(data)

    if security and (wants_human or not closure_authorized):
        return {
            "recommended_action": "transfer_to_human_agents",
            "transfer_reason": "fraud_or_security_concern",
            "summary": summary,
            "do_not_perform_card_actions_before_transfer": True,
        }
    if security and closure_authorized:
        return {
            "recommended_action": "continue_documented_debit_closure_procedure",
            "summary": summary,
            "do_not_perform_card_actions_before_transfer": False,
        }
    if wants_human:
        return {
            "recommended_action": "transfer_to_human_agents",
            "transfer_reason": "customer_requests_human_no_specific_reason",
            "summary": summary,
            "do_not_perform_card_actions_before_transfer": True,
        }
    if wants_freeze:
        return {
            "recommended_action": "verify_then_check_debit_card_eligibility_for_temporary_freeze",
            "summary": summary,
            "do_not_perform_card_actions_before_transfer": False,
        }
    return {
        "recommended_action": "clarify_customer_request",
        "summary": summary,
        "do_not_perform_card_actions_before_transfer": False,
    }


def main() -> None:
    try:
        raw = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": "invalid_json", "detail": str(exc)}))
        return
    if not isinstance(raw, dict):
        print(json.dumps({"error": "input_must_be_object"}))
        return
    print(json.dumps(plan(raw), sort_keys=True))


if __name__ == "__main__":
    main()
