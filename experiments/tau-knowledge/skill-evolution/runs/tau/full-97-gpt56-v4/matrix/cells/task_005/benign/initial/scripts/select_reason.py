#!/usr/bin/env python3
"""Recommend a documented human-transfer reason from explicit boolean facts.

Read JSON from stdin: {"facts": {"customer_requested_human": true, ...}}
Write JSON: {"reason": str|None, "tier": int|None, "matched": [str],
             "needs_manual_review": bool}.

This program never invokes banking tools.
"""
import json
import sys

# Each tuple is (reason enum, priority tier, required facts).  The ordering within
# a tier is a deterministic fallback only; executor review resolves real ambiguity.
RULES = (
    ("fraud_or_security_concern", 1, ("fraud_or_security_concern",)),
    ("account_closure_request", 1, ("account_closure_request",)),
    ("deceased_account_holder", 1, ("deceased_account_holder",)),
    ("legal_or_regulatory_matter", 1, ("legal_or_regulatory_matter",)),
    ("account_ownership_dispute", 1, ("account_ownership_dispute",)),
    ("complex_billing_dispute", 1, ("complex_billing_dispute",)),
    ("abusive_customer_behavior", 1, ("abusive_customer_behavior",)),
    ("third_party_inquiry", 1, ("third_party_inquiry",)),
    ("technical_system_error", 1, ("technical_system_error",)),
    ("customer_demands_after_unavailable_offer_refusal", 1,
     ("unavailable_offer_requested", "unavailable_offer_explained",
      "offer_persisted_multiple_times", "customer_requested_human")),
    ("unconfirmed_external_communication", 2,
     ("external_offer_communication_claimed", "kb_searched_no_verification",
      "customer_requested_human")),
    ("kb_search_unsuccessful_customer_requests_transfer", 2,
     ("customer_requested_information_or_instructions", "kb_searched_unsuccessfully",
      "customer_informed_kb_not_found", "customer_requested_human")),
    ("specialized_department_required", 2,
     ("specialized_department_required",)),
    ("accessibility_or_special_needs", 2,
     ("accessibility_or_special_needs",)),
    ("customer_frustrated_demands_human", 3,
     ("general_frustration", "customer_requested_human")),
    ("supervisor_request_service_complaint", 3,
     ("supervisor_requested_for_service_complaint",)),
    ("request_completed_customer_wants_human_followup", 3,
     ("request_completed", "customer_requested_human")),
    ("customer_requests_human_no_specific_reason", 3,
     ("customer_requested_human",)),
)


def select(facts):
    """Return a selector response for a mapping of explicit boolean facts."""
    if not isinstance(facts, dict):
        raise ValueError("facts must be a JSON object")
    normalized = {str(key): value is True for key, value in facts.items()}
    if not normalized.get("customer_requested_human", False):
        return {"reason": None, "tier": None, "matched": [], "needs_manual_review": False}

    matches = []
    for reason, tier, required in RULES:
        if all(normalized.get(flag, False) for flag in required):
            matches.append((reason, tier, list(required)))
    if not matches:
        return {"reason": "other", "tier": 4, "matched": [], "needs_manual_review": False}

    best_tier = min(item[1] for item in matches)
    finalists = [item for item in matches if item[1] == best_tier]
    reason, tier, required = finalists[0]
    # The generic human-request disposition is expected to co-match more specific
    # Tier 3 dispositions, so it alone is not treated as ambiguity.
    material = [item for item in finalists
                if item[0] != "customer_requests_human_no_specific_reason"]
    needs_review = len(material) > 1
    return {
        "reason": reason,
        "tier": tier,
        "matched": required,
        "needs_manual_review": needs_review,
    }


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("top-level input must be a JSON object")
        output = select(payload.get("facts", {}))
        print(json.dumps(output, sort_keys=True))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        raise SystemExit(2)


if __name__ == "__main__":
    main()
