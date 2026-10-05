#!/usr/bin/env python3
"""Deterministic planner for the direct-deposit human-transfer gate.

Reads one JSON object from stdin and writes one JSON object to stdout.
It never performs customer communication, account lookup, or transfer actions.
"""

import json
import sys
from typing import Any, Dict

TIER_1_OR_2 = {
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

REQUIRED_OPENING = (
    "I understand your frustration, but I need to try to help you resolve this "
    "first before I can initiate a transfer. Let me see what else I can do for you...."
)


def fail(message: str) -> None:
    print(json.dumps({"error": message}, separators=(",", ":")))
    raise SystemExit(2)


def require_bool(data: Dict[str, Any], key: str, required: bool = True) -> Any:
    if key not in data:
        if required:
            fail(f"Missing required field: {key}")
        return False
    value = data[key]
    if not isinstance(value, bool):
        fail(f"Field {key} must be a JSON boolean")
    return value


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        fail(f"Invalid JSON input: {exc.msg}")

    if not isinstance(data, dict):
        fail("Input must be a JSON object")

    count = data.get("transfer_request_count")
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        fail("transfer_request_count must be a non-negative integer")

    frustrated = require_bool(data, "customer_frustrated")
    reviewed = require_bool(data, "account_review_completed", required=False)

    higher = data.get("higher_priority_reason")
    if higher is not None:
        if not isinstance(higher, str) or higher not in TIER_1_OR_2:
            fail("higher_priority_reason must be null or a supported Tier 1/Tier 2 reason")

    for key in ("payer_confirmed_sent", "trace_information_available"):
        value = data.get(key)
        if value is not None and not isinstance(value, bool):
            fail(f"Field {key} must be a JSON boolean or null")

    if count < 8:
        points = [
            "Acknowledge the urgency without promising that funds will arrive by a particular time.",
            "Explain that deposits typically post from 6 AM to 9 AM on the scheduled pay date and may take up to three days depending on payer processing and transmission.",
            "Ask the payer to confirm it initiated this pay-cycle payment and request deposit trace information.",
        ]
        if not reviewed:
            points.append("Offer authorized account review only after required identity verification and account identification.")
        result = {
            "action": "continue_support",
            "must_not_transfer": True,
            "transfer_reason": None,
            "required_opening": REQUIRED_OPENING,
            "response_points": points,
            "summary_checklist": [],
        }
    elif count == 8:
        reason = higher or (
            "customer_frustrated_demands_human"
            if frustrated
            else "customer_requests_human_no_specific_reason"
        )
        result = {
            "action": "transfer_now",
            "must_not_transfer": False,
            "transfer_reason": reason,
            "required_opening": None,
            "response_points": [
                "Tell the customer that the transfer is being initiated; do not promise a resolution or a specific wait time.",
            ],
            "summary_checklist": [
                "expected pay date and amount, if provided",
                "payer/employer and whether the payer confirmed it sent the payment",
                "whether trace information was provided",
                "account review performed and only its supported findings",
                "timing guidance and troubleshooting already provided",
                "that this was the eighth explicit request for a human",
            ],
        }
    else:
        result = {
            "action": "manual_process_review",
            "must_not_transfer": True,
            "transfer_reason": None,
            "required_opening": None,
            "response_points": [
                "The eighth-request transfer action was not recorded at the required point.",
                "Preserve the conversation count and use the active operational escalation process; do not reset or silently recount requests.",
            ],
            "summary_checklist": [],
        }

    result["context"] = {
        "transfer_request_count": count,
        "payer_confirmed_sent": data.get("payer_confirmed_sent"),
        "trace_information_available": data.get("trace_information_available"),
        "account_review_completed": reviewed,
        "current_time": data.get("current_time"),
    }
    print(json.dumps(result, separators=(",", ":")))


if __name__ == "__main__":
    main()
