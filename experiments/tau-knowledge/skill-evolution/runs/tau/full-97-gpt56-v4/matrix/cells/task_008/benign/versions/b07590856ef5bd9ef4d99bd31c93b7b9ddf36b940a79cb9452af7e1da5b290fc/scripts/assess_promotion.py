#!/usr/bin/env python3
"""Assess escalation for a claimed external promotion.

Reads one JSON object from stdin and writes one JSON object to stdout.
Input fields:
  external_promotion_claimed (bool), knowledge_checked (bool),
  promotion_verified (bool), tier1_reason (string|null), claimed_terms (string),
  missing_identifiers (list of strings), comparison (string), customer_request (string).
Output fields:
  action, reason, summary, ready, and missing_prerequisites.
"""
import json
import sys

TIER1 = {
    "fraud_or_security_concern", "account_closure_request", "deceased_account_holder",
    "legal_or_regulatory_matter", "account_ownership_dispute", "complex_billing_dispute",
    "abusive_customer_behavior", "third_party_inquiry", "technical_system_error",
    "customer_demands_after_unavailable_offer_refusal",
}


def text(value):
    return str(value).strip() if value is not None else ""


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"action": "review", "reason": None, "ready": False,
                          "missing_prerequisites": ["valid JSON input"],
                          "summary": "Cannot assess promotion: invalid JSON input."}))
        return

    tier1 = text(data.get("tier1_reason"))
    if tier1:
        if tier1 not in TIER1:
            print(json.dumps({"action": "review", "reason": None, "ready": False,
                              "missing_prerequisites": ["recognized Tier 1 reason"],
                              "summary": "A supplied Tier 1 reason is not recognized by this helper."}))
            return
        print(json.dumps({"action": "transfer_to_human_agents", "reason": tier1,
                          "ready": True, "missing_prerequisites": [],
                          "summary": "A higher-priority operational escalation reason applies: " + tier1 + "."}))
        return

    claimed = bool(data.get("external_promotion_claimed"))
    checked = bool(data.get("knowledge_checked"))
    verified = bool(data.get("promotion_verified"))
    if not claimed:
        result = {"action": "review", "reason": None, "ready": False,
                  "missing_prerequisites": ["confirmation of a specific external promotion"],
                  "summary": "This helper applies only to a claimed external promotion."}
    elif not checked:
        result = {"action": "gather_or_check", "reason": None, "ready": False,
                  "missing_prerequisites": ["available-promotion knowledge check"],
                  "summary": "Obtain identifying details and check available promotion information before escalation."}
    elif verified:
        result = {"action": "handle_verified_offer", "reason": None, "ready": False,
                  "missing_prerequisites": [],
                  "summary": "The claimed offer is verified; follow its documented redemption process."}
    else:
        missing = [text(x) for x in data.get("missing_identifiers", []) if text(x)]
        pieces = ["Customer seeks to redeem an external promotion"]
        terms = text(data.get("claimed_terms"))
        if terms:
            pieces.append("claiming " + terms)
        if missing:
            pieces.append("The item did not provide: " + ", ".join(missing))
        comparison = text(data.get("comparison"))
        if comparison:
            pieces.append("Available promotion information was checked: " + comparison)
        pieces.append("The claimed external offer could not be verified")
        request = text(data.get("customer_request"))
        if request:
            pieces.append("Customer requests: " + request)
        result = {"action": "transfer_to_human_agents",
                  "reason": "unconfirmed_external_communication", "ready": True,
                  "missing_prerequisites": [], "summary": ". ".join(pieces) + "."}
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
