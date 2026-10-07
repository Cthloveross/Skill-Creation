#!/usr/bin/env python3
"""Plan the next response/action for the staged card-decline transfer protocol.

Reads one JSON object on stdin and writes one JSON object on stdout.  This script
never executes banking tools.
"""
import json
import sys

INITIAL_TOOL = "initial_transfer_to_human_agent_0218"
ALLOWED_REASONS = {
    "fraud_or_security_concern", "account_closure_request",
    "deceased_account_holder", "legal_or_regulatory_matter",
    "account_ownership_dispute", "complex_billing_dispute",
    "abusive_customer_behavior", "third_party_inquiry", "technical_system_error",
    "customer_demands_after_unavailable_offer_refusal",
    "unconfirmed_external_communication",
    "kb_search_unsuccessful_customer_requests_transfer",
    "specialized_department_required", "accessibility_or_special_needs",
    "customer_frustrated_demands_human", "supervisor_request_service_complaint",
    "customer_requests_human_no_specific_reason",
    "request_completed_customer_wants_human_followup", "other",
}


def fail(message):
    return {"status": "error", "error": message}


def main(data):
    if not isinstance(data, dict):
        return fail("Input must be a JSON object.")
    if data.get("purchase_declines_despite_available_credit") is not True:
        return {"status": "unsupported", "message": "This plan is only for purchase declines despite available credit."}
    requested = data.get("clear_human_request")
    if not isinstance(requested, bool):
        return fail("clear_human_request must be a boolean.")
    before = data.get("human_request_count_before", 0)
    if isinstance(before, bool) or not isinstance(before, int) or before < 0:
        return fail("human_request_count_before must be a non-negative integer.")

    if not requested:
        return {
            "status": "ok", "action": "request_email_for_review",
            "human_request_count": before,
            "message_intent": "ask_for_account_email_before_review",
        }

    count = before + 1
    if count <= 3:
        return {
            "status": "ok", "action": "initial_transfer", "human_request_count": count,
            "tool_calls": [
                {"tool": "unlock_discoverable_agent_tool", "arguments": {"agent_tool_name": INITIAL_TOOL}},
                {"tool": "call_discoverable_agent_tool", "arguments": {"agent_tool_name": INITIAL_TOOL, "arguments": "{}"}},
            ],
            "prohibited_tool": "transfer_to_human_agents",
        }
    if count == 4:
        specific = data.get("specific_reason")
        if specific is not None and specific not in ALLOWED_REASONS:
            return fail("specific_reason is not a supported transfer reason code.")
        reason = specific or ("customer_frustrated_demands_human" if data.get("frustrated") is True else "customer_requests_human_no_specific_reason")
        summary = data.get("summary")
        if not isinstance(summary, str) or not summary.strip():
            return fail("A nonempty factual summary is required for the fourth request.")
        return {
            "status": "ok", "action": "standard_transfer", "human_request_count": count,
            "tool_calls": [{"tool": "transfer_to_human_agents", "arguments": {"reason": reason, "summary": summary.strip()}}],
        }
    return {"status": "unsupported", "human_request_count": count, "message": "The documented special sequence ends with the fourth request; use current operational guidance for later requests."}


if __name__ == "__main__":
    try:
        result = main(json.loads(sys.stdin.read()))
    except json.JSONDecodeError as exc:
        result = fail("Invalid JSON input: " + str(exc))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
