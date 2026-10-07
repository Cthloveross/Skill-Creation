#!/usr/bin/env python3
"""Plan the staged human-transfer action for eligible credit-card decline cases.

Reads JSON from stdin and writes JSON to stdout. This helper only recommends a
banking-tool action; it never invokes a banking tool.
"""
import json
import sys

TIERED_REASONS = (
    (
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
    ),
    (
        "unconfirmed_external_communication",
        "kb_search_unsuccessful_customer_requests_transfer",
        "specialized_department_required",
        "accessibility_or_special_needs",
    ),
    (
        "customer_frustrated_demands_human",
        "supervisor_request_service_complaint",
        "customer_requests_human_no_specific_reason",
        "request_completed_customer_wants_human_followup",
    ),
    ("other",),
)
ALL_REASONS = {reason for tier in TIERED_REASONS for reason in tier}


def fail(message):
    print(json.dumps({"status": "error", "error": message}, sort_keys=True))
    raise SystemExit(0)


def select_reason(flags):
    if not isinstance(flags, dict):
        raise ValueError("reason_flags must be an object")
    unknown = sorted(set(flags) - ALL_REASONS)
    if unknown:
        raise ValueError("unknown reason flag(s): " + ", ".join(unknown))
    for tier in TIERED_REASONS:
        for reason in tier:
            if flags.get(reason) is True:
                return reason
    return "other"


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, TypeError) as exc:
        fail("input must be one JSON object: " + str(exc))
    if not isinstance(data, dict):
        fail("input must be a JSON object")

    if data.get("purchase_declines_with_available_credit") is not True:
        print(json.dumps({
            "status": "unsupported",
            "message": "The staged protocol applies only to purchase declines with available credit."
        }, sort_keys=True))
        return

    count = data.get("transfer_request_count")
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        fail("transfer_request_count must be an integer of at least 1")

    if count <= 3:
        print(json.dumps({
            "status": "ok",
            "stage": "specialized_transfer",
            "actions": [
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
        }, sort_keys=True))
        return

    summary = data.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        fail("summary must be a nonempty string for a regular transfer")
    try:
        reason = select_reason(data.get("reason_flags", {}))
    except ValueError as exc:
        fail(str(exc))
    print(json.dumps({
        "status": "ok",
        "stage": "regular_transfer",
        "actions": [{
            "tool": "transfer_to_human_agents",
            "arguments": {"reason": reason, "summary": summary.strip()}
        }]
    }, sort_keys=True))


if __name__ == "__main__":
    main()
