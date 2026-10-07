#!/usr/bin/env python3
"""Determine the direct-deposit human-transfer gate from explicit conversation state.

Input and output are JSON objects as documented in SKILL.md. This program does not
perform a transfer; the calling agent remains responsible for customer messaging and
for calling the normal transfer tool when instructed.
"""

import json
import sys
from typing import Any, Dict, List

REQUIRED_PREFIX = (
    "I understand your frustration, but I need to try to help you resolve this first "
    "before I can initiate a transfer. Let me see what else I can do for you...."
)

REASON_PRIORITY = [
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
REASON_SET = set(REASON_PRIORITY)


def invalid(errors: List[str]) -> Dict[str, Any]:
    return {
        "status": "invalid_input",
        "total_transfer_requests": None,
        "action": "manual_state_review",
        "required_prefix": "",
        "transfer_reason": None,
        "transfer_summary": "",
        "validation_errors": errors,
    }


def choose_reason(applicable: List[str], frustrated: bool) -> str:
    """Return the highest-priority stated reason or a disposition fallback."""
    candidates = set(applicable)
    if not candidates:
        candidates.add(
            "customer_frustrated_demands_human"
            if frustrated
            else "customer_requests_human_no_specific_reason"
        )
    return next(reason for reason in REASON_PRIORITY if reason in candidates)


def main(payload: Dict[str, Any]) -> Dict[str, Any]:
    errors: List[str] = []
    prior = payload.get("prior_transfer_requests")
    current = payload.get("current_message_requests_transfer")
    frustrated = payload.get("customer_frustrated", False)
    applicable = payload.get("applicable_reason_codes", [])
    summary = payload.get("issue_summary", "")

    # bool is an int subclass, so exclude it explicitly.
    if isinstance(prior, bool) or not isinstance(prior, int) or prior < 0:
        errors.append("prior_transfer_requests must be a nonnegative integer")
    if not isinstance(current, bool):
        errors.append("current_message_requests_transfer must be a boolean")
    if not isinstance(frustrated, bool):
        errors.append("customer_frustrated must be a boolean")
    if not isinstance(applicable, list) or not all(isinstance(x, str) for x in applicable):
        errors.append("applicable_reason_codes must be an array of strings")
    elif any(x not in REASON_SET for x in applicable):
        unknown = sorted({x for x in applicable if x not in REASON_SET})
        errors.append("unrecognized reason code(s): " + ", ".join(unknown))
    if not isinstance(summary, str):
        errors.append("issue_summary must be a string")

    if errors:
        return invalid(errors)

    total = prior + (1 if current else 0)
    base = {
        "status": "ok",
        "total_transfer_requests": total,
        "required_prefix": "",
        "transfer_reason": None,
        "transfer_summary": "",
        "validation_errors": [],
    }

    if total > 8 or (prior == 8 and not current):
        base.update(
            {
                "status": "state_exception",
                "action": "manual_state_review",
                "validation_errors": [
                    "The eighth request should already have triggered a transfer; "
                    "do not reset or silently continue the request count."
                ],
            }
        )
        return base

    if current and total == 8:
        reason = choose_reason(applicable, frustrated)
        tool_summary = summary.strip()
        suffix = "Customer has made the eighth explicit request for a human agent."
        tool_summary = (tool_summary + " " + suffix).strip()
        base.update(
            {
                "action": "transfer_now",
                "transfer_reason": reason,
                "transfer_summary": tool_summary,
            }
        )
        return base

    if current and total < 8:
        base.update(
            {
                "action": "respond_with_required_gate",
                "required_prefix": REQUIRED_PREFIX,
            }
        )
        return base

    base["action"] = "continue_support"
    return base


if __name__ == "__main__":
    try:
        parsed = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps(invalid(["stdin must contain one valid JSON object: " + str(exc)])))
        sys.exit(0)
    if not isinstance(parsed, dict):
        print(json.dumps(invalid(["stdin JSON value must be an object"])))
        sys.exit(0)
    print(json.dumps(main(parsed), ensure_ascii=False))
