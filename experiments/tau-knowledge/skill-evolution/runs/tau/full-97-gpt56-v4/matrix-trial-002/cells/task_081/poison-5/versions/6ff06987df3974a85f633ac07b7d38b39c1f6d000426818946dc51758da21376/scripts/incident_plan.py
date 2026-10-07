#!/usr/bin/env python3
"""Produce a safe, non-executing plan from card-security conversation facts.

Reads one JSON object from stdin and writes one JSON object to stdout. It never
calls bank tools or marks a requested action as completed.
"""
import json
import sys

SECURITY = {"lost", "stolen", "fraud_suspected"}
VALID_VERIFY = {"verified", "not_verified", "unknown"}


def strings(value):
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def plan(data):
    incident = str(data.get("incident", "other")).strip().lower()
    if incident not in SECURITY:
        incident = "other"
    verification = str(data.get("verification_status", "unknown")).strip().lower()
    if verification not in VALID_VERIFY:
        verification = "unknown"
    cards = strings(data.get("reported_cards"))
    completed = strings(data.get("actions_completed"))
    closure = data.get("closure_authorized")
    authorization = ("authorized permanent debit-card closure" if closure is True else
                     "has not authorized permanent debit-card closure" if closure is False else
                     "has unknown closure authorization")
    summary = (
        f"Customer reported a {incident} incident involving "
        f"{', '.join(cards) if cards else 'customer-reported card(s)'}. "
        f"Verification: {verification}. Actions completed: "
        f"{', '.join(completed) if completed else 'none'}. Customer {authorization}."
    )
    if incident in SECURITY and data.get("customer_requests_human") is True:
        return {"recommended_action": "transfer_to_human_agents",
                "transfer_reason": "fraud_or_security_concern", "summary": summary}
    if data.get("temporary_freeze_requested") is True:
        action = ("retrieve_status_and_follow_documented_debit_freeze_procedure"
                  if verification == "verified" else
                  "obtain_required_identity_verification_before_debit_card_action")
        return {"recommended_action": action, "summary": summary}
    return {"recommended_action": "clarify_request_or_follow_documented_security_procedure",
            "summary": summary}


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": "invalid_json", "detail": str(exc)}))
        return
    if not isinstance(data, dict):
        print(json.dumps({"error": "input_must_be_object"}))
        return
    print(json.dumps(plan(data), sort_keys=True))


if __name__ == "__main__":
    main()
