#!/usr/bin/env python3
"""Return a non-executing safe next-step plan for a card-security case.

Input: one JSON object on stdin. Output: one JSON object on stdout. No bank tools
are called and no stated action is treated as completed unless supplied in input.
"""
import json
import sys

SECURITY = {"lost", "stolen", "fraud_suspected"}
VERIFY = {"verified", "not_verified", "unknown"}


def text_list(value):
    return [str(x).strip() for x in value] if isinstance(value, list) else []


def build(data):
    incident = str(data.get("incident", "other")).strip().lower()
    if incident not in SECURITY | {"other"}:
        incident = "other"
    verified = str(data.get("verification_status", "unknown")).strip().lower()
    if verified not in VERIFY:
        verified = "unknown"
    cards = [x for x in text_list(data.get("reported_cards")) if x]
    completed = [x for x in text_list(data.get("actions_completed")) if x]
    closure = data.get("closure_authorized")
    closure_text = ("authorized permanent debit-card closure" if closure is True else
                    "declined or has not authorized permanent debit-card closure" if closure is False else
                    "has unknown closure authorization")
    summary = (
        f"Customer reported a {incident} security incident involving "
        f"{', '.join(cards) if cards else 'customer-reported card(s)'}. "
        f"Verification: {verified}. Actions completed: "
        f"{', '.join(completed) if completed else 'none'}. Customer {closure_text}."
    )
    if incident in SECURITY and data.get("customer_requests_human") is True:
        return {"recommended_action": "transfer_to_human_agents",
                "transfer_reason": "fraud_or_security_concern", "summary": summary}
    if data.get("temporary_freeze_requested") is True:
        if verified != "verified":
            action = "obtain_required_identity_verification_before_debit_card_action"
        else:
            action = "retrieve_card_status_and_follow_documented_temporary_freeze_process"
        return {"recommended_action": action, "summary": summary}
    if incident in SECURITY and closure is True:
        return {"recommended_action": "continue_documented_debit_card_closure_eligibility_checks",
                "summary": summary}
    return {"recommended_action": "clarify_request_or_offer_documented_security_options",
            "summary": summary}


def main():
    try:
        value = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": "invalid_json", "detail": str(exc)}))
        return
    if not isinstance(value, dict):
        print(json.dumps({"error": "input_must_be_object"}))
        return
    print(json.dumps(build(value), sort_keys=True))

if __name__ == "__main__":
    main()
