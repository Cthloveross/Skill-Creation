#!/usr/bin/env python3
"""Plan the required transfer action for the credit-card decline protocol.

Reads a JSON object on stdin and writes a JSON object on stdout. This helper is
pure: it never performs a banking action.
"""
import json
import sys

INITIAL_TOOL = "initial_transfer_to_human_agent_0218"
VALID_REASONS = {
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
PRIORITY = [
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
    "unconfirmed_external_communication",
    "kb_search_unsuccessful_customer_requests_transfer",
    "specialized_department_required",
    "accessibility_or_special_needs",
    "customer_frustrated_demands_human",
    "supervisor_request_service_complaint",
    "customer_requests_human_no_specific_reason",
    "request_completed_customer_wants_human_followup",
    "other",
]


def fail(message):
    print(json.dumps({"error": message}, sort_keys=True))
    raise SystemExit(2)


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, TypeError) as exc:
        fail("stdin must contain one JSON object: " + str(exc))
    if not isinstance(data, dict):
        fail("input must be a JSON object")

    number = data.get("transfer_request_number", 0)
    if isinstance(number, bool) or not isinstance(number, int) or number < 0:
        fail("transfer_request_number must be a nonnegative integer")

    in_scope = data.get("purchase_declines_despite_available_credit", False)
    if not isinstance(in_scope, bool):
        fail("purchase_declines_despite_available_credit must be boolean")

    supplied = data.get("applicable_reason_codes", [])
    if not isinstance(supplied, list) or not all(isinstance(x, str) for x in supplied):
        fail("applicable_reason_codes must be an array of strings")
    unknown = sorted(set(supplied) - VALID_REASONS)
    if unknown:
        fail("unsupported reason code(s): " + ", ".join(unknown))

    if not in_scope or number == 0:
        result = {
            "action": "normal_assistance",
            "protocol_applies": False,
            "reason": None,
        }
    elif number <= 3:
        result = {
            "action": "unlock_and_call_initial_transfer",
            "arguments_json": "{}",
            "discoverable_agent_tool": INITIAL_TOOL,
            "protocol_applies": True,
            "regular_transfer_forbidden": True,
            "request_number": number,
        }
    else:
        supplied_set = set(supplied)
        reason = next((item for item in PRIORITY if item in supplied_set), "other")
        result = {
            "action": "regular_transfer",
            "protocol_applies": True,
            "reason": reason,
            "request_number": number,
            "summary_required": True,
            "detailed_summary_required": reason == "other",
        }
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
