#!/usr/bin/env python3
"""Plan the required transfer route; reads one JSON object from stdin and writes JSON."""

import json
import sys

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


def fail(message):
    print(json.dumps({"error": message}, sort_keys=True))
    raise SystemExit(2)


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        fail("stdin must contain one valid JSON object: " + str(exc))

    if not isinstance(data, dict):
        fail("input must be a JSON object")

    qualifying = data.get("purchase_declines_despite_available_credit")
    requested = data.get("explicit_human_transfer_request")
    prior = data.get("prior_explicit_transfer_requests")
    frustrated = data.get("customer_frustrated", False)
    supplied_reason = data.get("highest_applicable_reason")

    if not isinstance(qualifying, bool) or not isinstance(requested, bool):
        fail("purchase_declines_despite_available_credit and explicit_human_transfer_request must be booleans")
    if not isinstance(prior, int) or isinstance(prior, bool) or prior < 0:
        fail("prior_explicit_transfer_requests must be a non-negative integer")
    if not isinstance(frustrated, bool):
        fail("customer_frustrated must be a boolean")
    if supplied_reason is not None and supplied_reason not in VALID_REASONS:
        fail("highest_applicable_reason is not a valid standard-transfer reason code")

    if not (qualifying and requested):
        print(json.dumps({
            "applicable": False,
            "route": "not_applicable",
            "tool_calls": [],
            "message": "This protocol requires both the qualifying decline report and an explicit human-transfer request."
        }, sort_keys=True))
        return

    request_number = prior + 1
    if request_number <= 3:
        result = {
            "applicable": True,
            "request_number": request_number,
            "route": "initial_discoverable_transfer",
            "tool_calls": [
                {
                    "tool": "unlock_discoverable_agent_tool",
                    "arguments": {"agent_tool_name": "initial_transfer_to_human_agent_0218"}
                },
                {
                    "tool": "call_discoverable_agent_tool",
                    "arguments": {
                        "agent_tool_name": "initial_transfer_to_human_agent_0218",
                        "arguments": "{}"
                    }
                }
            ]
        }
    else:
        reason = supplied_reason
        if reason is None:
            reason = ("customer_frustrated_demands_human" if frustrated
                      else "customer_requests_human_no_specific_reason")
        result = {
            "applicable": True,
            "request_number": request_number,
            "route": "standard_transfer",
            "recommended_reason": reason,
            "tool_calls": [
                {
                    "tool": "transfer_to_human_agents",
                    "arguments": {"reason": reason, "summary": "<executor supplies factual summary>"}
                }
            ]
        }
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
