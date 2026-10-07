#!/usr/bin/env python3
"""Deterministically recommend a human-transfer reason from explicit evidence.

Read JSON from stdin and write JSON to stdout. This helper never performs a bank action.
"""
import json
import sys


def flag(signals, name):
    return bool(signals.get(name, False))


def choose(payload):
    signals = payload.get("signals") or {}
    transfer_requested = bool(payload.get("customer_requested_transfer", False))

    tier1 = [
        ("fraud_or_security_concern", flag(signals, "fraud_or_security_concern")),
        ("account_closure_request", flag(signals, "account_closure_request")),
        ("deceased_account_holder", flag(signals, "deceased_account_holder")),
        ("legal_or_regulatory_matter", flag(signals, "legal_or_regulatory_matter")),
        ("account_ownership_dispute", flag(signals, "account_ownership_dispute")),
        ("complex_billing_dispute", flag(signals, "complex_billing_dispute")),
        ("abusive_customer_behavior", flag(signals, "abusive_customer_behavior")),
        ("third_party_inquiry", flag(signals, "third_party_inquiry")),
        ("technical_system_error", flag(signals, "technical_system_error")),
        ("customer_demands_after_unavailable_offer_refusal",
         flag(signals, "unavailable_offer_refused")
         and int(signals.get("offer_persistence_count", 0) or 0) >= 2
         and transfer_requested),
    ]
    for reason, applies in tier1:
        if applies:
            return reason, 1, True

    kb_gap = (
        flag(signals, "information_or_instruction_requested")
        and flag(signals, "kb_search_performed")
        and flag(signals, "kb_search_failed")
        and flag(signals, "customer_informed_kb_unavailable")
        and transfer_requested
    )
    tier2 = [
        ("unconfirmed_external_communication", flag(signals, "unconfirmed_external_communication")),
        ("kb_search_unsuccessful_customer_requests_transfer", kb_gap),
        ("specialized_department_required", flag(signals, "specialized_department_required")),
        ("accessibility_or_special_needs", flag(signals, "accessibility_or_special_needs")),
    ]
    for reason, applies in tier2:
        if applies:
            return reason, 2, True

    tier3 = [
        ("customer_frustrated_demands_human", flag(signals, "customer_frustrated") and transfer_requested),
        ("supervisor_request_service_complaint", flag(signals, "supervisor_service_complaint")),
        ("customer_requests_human_no_specific_reason",
         flag(signals, "no_specific_reason_for_human") and transfer_requested),
        ("request_completed_customer_wants_human_followup",
         flag(signals, "request_completed") and flag(signals, "human_followup_requested")),
    ]
    for reason, applies in tier3:
        if applies:
            return reason, 3, True

    return "other", 4, transfer_requested


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("top-level JSON value must be an object")
        reason, tier, eligible = choose(payload)
        facts = payload.get("facts") or []
        if not isinstance(facts, list):
            raise ValueError("facts must be a list of strings")
        clean_facts = [str(item).strip() for item in facts if str(item).strip()]
        if clean_facts:
            hint = "; ".join(clean_facts)
        else:
            hint = "State the customer's request, actions already attempted, results, and remaining issue."
        output = {
            "reason": reason,
            "tier": tier,
            "eligible": eligible,
            "summary_hint": hint,
        }
        print(json.dumps(output, ensure_ascii=False))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
