#!/usr/bin/env python3
"""Create a deterministic transfer-tool plan; does not execute banking actions.

Reads one JSON object from stdin and emits one JSON object to stdout.
See SKILL.md for the public input and output schemas.
"""
import json
import sys

TIERED_REASONS = [
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
]
VALID_REASONS = set(TIERED_REASONS + ["other"])


def fail(message):
    print(json.dumps({"error": message}, ensure_ascii=False))
    raise SystemExit(2)


def select_reason(reason_facts):
    """Return the highest-tier established reason, or the documented fallback."""
    for reason in TIERED_REASONS:
        if reason_facts.get(reason) is True:
            return reason
    # A transfer request with no established special disposition is simply a
    # preference for a human. This is above the catch-all tier.
    return "customer_requests_human_no_specific_reason"


def main():
    try:
        raw = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        fail("stdin must contain one valid JSON object: " + str(exc))

    if not isinstance(raw, dict):
        fail("input must be a JSON object")

    qualifying = raw.get("qualifying_card_decline")
    requesting = raw.get("requests_human_now")
    prior = raw.get("prior_transfer_requests", 0)
    summary = raw.get("customer_summary", "")
    facts = raw.get("reason_facts", {})

    if not isinstance(qualifying, bool):
        fail("qualifying_card_decline must be boolean")
    if not isinstance(requesting, bool):
        fail("requests_human_now must be boolean")
    if not isinstance(prior, int) or isinstance(prior, bool) or prior < 0:
        fail("prior_transfer_requests must be a nonnegative integer")
    if not isinstance(summary, str):
        fail("customer_summary must be a string")
    if not isinstance(facts, dict):
        fail("reason_facts must be an object")
    for key, value in facts.items():
        if key not in VALID_REASONS:
            fail("reason_facts includes unsupported reason: " + str(key))
        if not isinstance(value, bool):
            fail("each reason_facts value must be boolean")

    if not requesting:
        print(json.dumps({
            "action": "continue_assistance",
            "request_number": None,
            "tool_calls": [],
            "selected_reason": None,
            "notes": [
                "No current human-transfer request was indicated.",
                "Continue decline troubleshooting and retain the prior transfer count."
            ]
        }, ensure_ascii=False))
        return

    if not summary.strip():
        fail("customer_summary must be nonempty when requests_human_now is true")

    number = prior + 1
    reason = select_reason(facts)

    if qualifying and number <= 3:
        plan = {
            "action": "initial_transfer_protocol",
            "request_number": number,
            "tool_calls": [
                {
                    "tool": "unlock_discoverable_agent_tool",
                    "arguments": {
                        "agent_tool_name": "initial_transfer_to_human_agent_0218"
                    }
                },
                {
                    "tool": "call_discoverable_agent_tool",
                    "arguments": {
                        "agent_tool_name": "initial_transfer_to_human_agent_0218",
                        "arguments": "{}"
                    }
                }
            ],
            "selected_reason": None,
            "notes": [
                "Do not call transfer_to_human_agents for qualifying transfer requests one through three.",
                "If the discoverable tool is already unlocked, the executor may omit only the redundant unlock call."
            ]
        }
    else:
        plan = {
            "action": "regular_transfer",
            "request_number": number,
            "tool_calls": [
                {
                    "tool": "transfer_to_human_agents",
                    "arguments": {
                        "reason": reason,
                        "summary": summary.strip()
                    }
                }
            ],
            "selected_reason": reason,
            "notes": [
                "Use the regular transfer path because this is request four or later, or the supplied facts do not qualify for the special card-decline protocol.",
                "The execution agent must make the listed banking-tool call; this plan itself has no external effect."
            ]
        }

    print(json.dumps(plan, ensure_ascii=False))


if __name__ == "__main__":
    main()
