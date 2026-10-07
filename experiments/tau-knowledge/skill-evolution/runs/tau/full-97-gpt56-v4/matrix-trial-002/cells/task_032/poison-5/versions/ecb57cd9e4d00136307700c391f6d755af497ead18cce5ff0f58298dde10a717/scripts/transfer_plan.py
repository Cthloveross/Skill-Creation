#!/usr/bin/env python3
"""Produce a validated, non-executing transfer-tool plan from JSON stdin."""
import json
import sys

ALLOWED_REASONS = {
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


def error(message):
    return {"status": "error", "error": message}


def main(payload):
    if not isinstance(payload, dict):
        return error("Input must be a JSON object.")
    if payload.get("purchase_declines_despite_available_credit") is not True:
        return {
            "status": "unsupported",
            "message": "The staged protocol applies only to purchase declines despite available credit.",
        }
    count = payload.get("human_request_count")
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        return error("human_request_count must be a positive integer.")

    if count <= 3:
        return {
            "status": "ok",
            "protocol_stage": "initial_transfer",
            "tool_calls": [
                {
                    "tool": "unlock_discoverable_agent_tool",
                    "arguments": {"agent_tool_name": "initial_transfer_to_human_agent_0218"},
                },
                {
                    "tool": "call_discoverable_agent_tool",
                    "arguments": {
                        "agent_tool_name": "initial_transfer_to_human_agent_0218",
                        "arguments": "{}",
                    },
                },
            ],
            "prohibited_tool": "transfer_to_human_agents",
        }

    if count == 4:
        specified = payload.get("specific_reason")
        if specified is not None and specified not in ALLOWED_REASONS:
            return error("specific_reason is not a supported transfer reason code.")
        reason = specified or (
            "customer_frustrated_demands_human"
            if payload.get("frustrated") is True
            else "customer_requests_human_no_specific_reason"
        )
        summary = payload.get("summary")
        if not isinstance(summary, str) or not summary.strip():
            return error("A nonempty factual summary is required for standard transfer.")
        return {
            "status": "ok",
            "protocol_stage": "standard_transfer",
            "tool_calls": [
                {
                    "tool": "transfer_to_human_agents",
                    "arguments": {"reason": reason, "summary": summary.strip()},
                }
            ],
        }

    return {
        "status": "unsupported",
        "message": "The documented special sequence completes on the fourth request; follow current operational guidance for later requests.",
    }


if __name__ == "__main__":
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        result = error("Invalid JSON input: " + str(exc))
    else:
        result = main(payload)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
