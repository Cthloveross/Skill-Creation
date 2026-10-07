#!/usr/bin/env python3
"""Choose the highest applicable supported human-transfer reason.

Input JSON fields (all booleans default false):
 fraud_or_security_concern, account_closure_request, deceased_account_holder,
 legal_or_regulatory_matter, account_ownership_dispute, complex_billing_dispute,
 abusive_customer_behavior, third_party_inquiry, technical_system_error,
 unavailable_offer_persisted_and_demands_human,
 unconfirmed_external_communication,
 kb_search_unsuccessful_customer_requests_transfer,
 specialized_department_required, accessibility_or_special_needs,
 customer_frustrated_demands_human, supervisor_request_service_complaint,
 human_requested, request_completed_wants_human_followup.

For convenience, unauthorized_or_security_concern is an alias that sets the
fraud/security condition. reported_issue_labels and attempted may be arrays of
short factual strings. Output is a transfer recommendation, not a tool call.
"""
import json
import sys


def as_bool(data, key):
    return data.get(key, False) is True


def clean_list(value, limit=6):
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        if isinstance(item, str):
            item = " ".join(item.split())
            if item and item not in result:
                result.append(item[:180])
        if len(result) >= limit:
            break
    return result


def main(data):
    tiers = [
        (1, "fraud_or_security_concern", as_bool(data, "fraud_or_security_concern") or as_bool(data, "unauthorized_or_security_concern")),
        (1, "account_closure_request", as_bool(data, "account_closure_request")),
        (1, "deceased_account_holder", as_bool(data, "deceased_account_holder")),
        (1, "legal_or_regulatory_matter", as_bool(data, "legal_or_regulatory_matter")),
        (1, "account_ownership_dispute", as_bool(data, "account_ownership_dispute")),
        (1, "complex_billing_dispute", as_bool(data, "complex_billing_dispute")),
        (1, "abusive_customer_behavior", as_bool(data, "abusive_customer_behavior")),
        (1, "third_party_inquiry", as_bool(data, "third_party_inquiry")),
        (1, "technical_system_error", as_bool(data, "technical_system_error")),
        (1, "customer_demands_after_unavailable_offer_refusal", as_bool(data, "unavailable_offer_persisted_and_demands_human")),
        (2, "unconfirmed_external_communication", as_bool(data, "unconfirmed_external_communication")),
        (2, "kb_search_unsuccessful_customer_requests_transfer", as_bool(data, "kb_search_unsuccessful_customer_requests_transfer")),
        (2, "specialized_department_required", as_bool(data, "specialized_department_required")),
        (2, "accessibility_or_special_needs", as_bool(data, "accessibility_or_special_needs")),
        (3, "customer_frustrated_demands_human", as_bool(data, "customer_frustrated_demands_human")),
        (3, "supervisor_request_service_complaint", as_bool(data, "supervisor_request_service_complaint")),
        (3, "customer_requests_human_no_specific_reason", as_bool(data, "human_requested")),
        (3, "request_completed_customer_wants_human_followup", as_bool(data, "request_completed_wants_human_followup")),
    ]
    selected = next(((tier, reason) for tier, reason, applies in tiers if applies), (4, "other"))
    tier, reason = selected

    issues = clean_list(data.get("reported_issue_labels"))
    attempted = clean_list(data.get("attempted"))
    parts = []
    if issues:
        parts.append("Customer reports: " + "; ".join(issues) + ".")
    else:
        parts.append("Customer requested human assistance.")
    if attempted:
        parts.append("Work completed before transfer: " + "; ".join(attempted) + ".")
    if reason == "fraud_or_security_concern":
        parts.append("Route to security/fraud specialist for handling.")
    elif reason == "other":
        parts.append("No more specific supported transfer reason was indicated.")

    return {"reason": reason, "tier": tier, "summary": " ".join(parts)}


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), separators=(",", ":")))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
