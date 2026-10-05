#!/usr/bin/env python3
"""Plan the required transfer action for qualifying credit-card decline requests.

Input and output are JSON objects on stdin/stdout. This helper performs no banking
or transfer action itself.
"""
import json
import sys

INITIAL_TOOL = "initial_transfer_to_human_agent_0218"
STANDARD_REASONS = {
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
# These codes represent facts that take precedence over disposition when explicit.
HIGHER_TIER_REASONS = {
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
}


def emit(value):
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))


def error(message):
    emit({"ok": False, "error": message})
    return 1


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, TypeError) as exc:
        return error("Input must be one valid JSON object: %s" % exc)
    if not isinstance(data, dict):
        return error("Input must be a JSON object")

    count = data.get("transfer_request_count_before")
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        return error("transfer_request_count_before must be a non-negative integer")

    current_request = data.get("current_turn_is_transfer_request")
    qualifies = data.get("qualifying_credit_card_decline")
    if not isinstance(current_request, bool) or not isinstance(qualifies, bool):
        return error("current_turn_is_transfer_request and qualifying_credit_card_decline must be booleans")

    if not current_request or not qualifies:
        emit({
            "ok": True,
            "applicable": False,
            "request_number": None,
            "next_count": count,
            "action": "none",
            "actions": [],
            "note": "No qualifying current transfer request; do not invoke a transfer tool.",
        })
        return 0

    request_number = count + 1
    unlocked = data.get("discoverable_tool_already_unlocked", False)
    if not isinstance(unlocked, bool):
        return error("discoverable_tool_already_unlocked must be a boolean")

    if request_number <= 3:
        actions = []
        if not unlocked:
            actions.append({
                "tool": "unlock_discoverable_agent_tool",
                "arguments": {"agent_tool_name": INITIAL_TOOL},
            })
        actions.append({
            "tool": "call_discoverable_agent_tool",
            "arguments": {"agent_tool_name": INITIAL_TOOL, "arguments": "{}"},
        })
        emit({
            "ok": True,
            "applicable": True,
            "request_number": request_number,
            "next_count": request_number,
            "action": "discoverable_initial_transfer",
            "actions": actions,
            "prohibited_action": "transfer_to_human_agents",
        })
        return 0

    supplied_reason = data.get("highest_applicable_reason")
    if supplied_reason is not None:
        if not isinstance(supplied_reason, str) or supplied_reason not in STANDARD_REASONS:
            return error("highest_applicable_reason must be a supported standard transfer reason")
        reason = supplied_reason
    elif data.get("frustrated_demands_human", False) is True:
        reason = "customer_frustrated_demands_human"
    else:
        reason = "customer_requests_human_no_specific_reason"

    summary = data.get("issue_summary")
    if summary is None:
        summary = (
            "Customer reports credit-card purchase declines despite available credit "
            "and has repeatedly requested a human agent."
        )
    if not isinstance(summary, str) or not summary.strip():
        return error("issue_summary must be a non-empty string when supplied")

    emit({
        "ok": True,
        "applicable": True,
        "request_number": request_number,
        "next_count": request_number,
        "action": "standard_transfer",
        "reason": reason,
        "summary": summary.strip(),
        "actions": [{
            "tool": "transfer_to_human_agents",
            "arguments": {"reason": reason, "summary": summary.strip()},
        }],
        "note": "Use the standard transfer tool on request four or later.",
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())
