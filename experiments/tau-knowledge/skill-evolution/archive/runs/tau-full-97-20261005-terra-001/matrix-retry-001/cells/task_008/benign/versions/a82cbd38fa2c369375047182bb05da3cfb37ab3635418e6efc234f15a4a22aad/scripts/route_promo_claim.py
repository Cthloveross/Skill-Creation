#!/usr/bin/env python3
"""Produce a validated routing recommendation for an external promotion claim.

Reads one JSON object from stdin and writes one JSON object to stdout. This helper is
advisory: the executor must confirm inputs against the conversation and then call
the banking transfer tool itself.
"""

import json
import sys

TIER_1_REASONS = {
    "fraud_or_security_concern",
    "account_closure_request",
    "deceased_account_holder",
    "legal_or_regulatory_matter",
    "account_ownership_dispute",
    "complex_billing_dispute",
    "abusive_customer_behavior",
    "third_party_inquiry",
    "technical_system_error",
    "customer_demands_after_unavailable_offer_refusal",
}
TRANSFER_REASONS = TIER_1_REASONS | {
    "unconfirmed_external_communication",
    "kb_search_unsuccessful_customer_requests_transfer",
    "specialized_department_required",
    "accessibility_or_special_needs",
    "customer_frustrated_demands_human",
    "supervisor_request_service_complaint",
    "customer_requests_human_no_specific_reason",
    "request_completed_customer_wants_human_followup",
    "other",
}
REQUIRED = {
    "external_promotion_claimed": bool,
    "promotion_verified_in_kb": bool,
    "customer_has_account": bool,
    "customer_requested_or_demands_review": bool,
    "claim_description": str,
}


def fail(message):
    print(json.dumps({"action": "input_error", "error": message}))
    raise SystemExit(2)


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        fail("stdin must contain one valid JSON object: " + str(exc))
    if not isinstance(data, dict):
        fail("input must be a JSON object")

    for key, expected_type in REQUIRED.items():
        if key not in data:
            fail("missing required field: " + key)
        if type(data[key]) is not expected_type:
            fail("field %s must be %s" % (key, expected_type.__name__))
    if not data["claim_description"].strip():
        fail("claim_description must not be empty")

    identifiers = data.get("missing_identifiers", [])
    if not isinstance(identifiers, list) or not all(isinstance(x, str) for x in identifiers):
        fail("missing_identifiers must be an array of strings")

    tier_1 = data.get("specific_operational_reason")
    if tier_1 is not None and tier_1 not in TIER_1_REASONS:
        fail("specific_operational_reason must be a recognized Tier 1 reason")

    claim = " ".join(data["claim_description"].split())
    identifier_text = ", ".join(x.strip() for x in identifiers if x.strip())

    if tier_1:
        reason = tier_1
        basis = "A specific Tier 1 operational reason was supplied."
    elif data["external_promotion_claimed"] and not data["promotion_verified_in_kb"]:
        reason = "unconfirmed_external_communication"
        basis = "An externally communicated promotion could not be verified in documented terms."
    elif data["customer_requested_or_demands_review"]:
        reason = "customer_requests_human_no_specific_reason"
        basis = "The customer requested human review without an unverified external-promotion route."
    else:
        print(json.dumps({
            "action": "do_not_transfer_from_this_helper",
            "reason": None,
            "summary": claim,
            "validation": {"valid": True, "basis": "No transfer trigger supplied."},
        }))
        return

    account_text = (
        "Customer reports no existing account."
        if not data["customer_has_account"]
        else "Customer account status requires normal servicing checks."
    )
    pieces = [
        "Promotion claim: " + claim + ".",
        basis,
        account_text,
    ]
    if identifier_text:
        pieces.append("Unavailable identifying details: " + identifier_text + ".")
    if data["customer_requested_or_demands_review"]:
        pieces.append("Customer requests or demands review.")

    print(json.dumps({
        "action": "transfer",
        "reason": reason,
        "summary": " ".join(pieces),
        "validation": {
            "valid": reason in TRANSFER_REASONS,
            "reason_is_transfer_enum": reason in TRANSFER_REASONS,
            "do_not_apply_credit_without_verified_entitlement": not data["promotion_verified_in_kb"],
        },
    }))


if __name__ == "__main__":
    main()
