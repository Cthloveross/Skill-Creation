#!/usr/bin/env python3
"""Select a prioritized human-transfer reason from JSON facts.

Reads one JSON object from stdin and writes one JSON object to stdout.
No external dependencies or banking-system access are used.
"""

import json
import sys

TIERS = {
    1: [
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
    ],
    2: [
        "unconfirmed_external_communication",
        "kb_search_unsuccessful_customer_requests_transfer",
        "specialized_department_required",
        "accessibility_or_special_needs",
    ],
    3: [
        "customer_frustrated_demands_human",
        "supervisor_request_service_complaint",
        "customer_requests_human_no_specific_reason",
        "request_completed_customer_wants_human_followup",
    ],
    4: ["other"],
}

REASON_TO_TIER = {
    reason: tier for tier, reasons in TIERS.items() for reason in reasons
}

# Aliases encode only direct, documented implications. Compound conditions must
# be evaluated by the caller and supplied through applicable_reasons.
ALIASES = {
    "identity_verification_failure": "account_ownership_dispute",
    "customer_requested_transfer": "customer_requests_human_no_specific_reason",
    "customer_frustrated": "customer_frustrated_demands_human",
    "supervisor_service_complaint": "supervisor_request_service_complaint",
    "request_completed_followup": "request_completed_customer_wants_human_followup",
}


def fail(message):
    print(json.dumps({"ok": False, "error": message}, ensure_ascii=False))
    return 2


def as_clean_text(value):
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())


def make_summary(data):
    explicit = as_clean_text(data.get("summary"))
    if explicit:
        return explicit

    parts = []
    issue = as_clean_text(data.get("issue"))
    if issue:
        parts.append("Customer request: " + issue + ".")

    attempts = data.get("attempts", [])
    if isinstance(attempts, list):
        cleaned_attempts = [as_clean_text(item) for item in attempts]
        cleaned_attempts = [item for item in cleaned_attempts if item]
        if cleaned_attempts:
            parts.append("Attempts: " + "; ".join(cleaned_attempts) + ".")

    blocker = as_clean_text(data.get("blocker"))
    if blocker:
        parts.append("Unresolved issue: " + blocker + ".")

    if not parts:
        parts.append("Customer requires human-agent assistance; review the conversation and prior lookup results.")
    return " ".join(parts)


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, TypeError) as exc:
        return fail("stdin must contain one valid JSON object: " + str(exc))

    if not isinstance(data, dict):
        return fail("input must be a JSON object")

    candidates = set()
    supplied = data.get("applicable_reasons", [])
    if supplied is None:
        supplied = []
    if not isinstance(supplied, list) or not all(isinstance(x, str) for x in supplied):
        return fail("applicable_reasons must be an array of reason-code strings")
    unknown = sorted(set(supplied) - set(REASON_TO_TIER))
    if unknown:
        return fail("unsupported reason code(s): " + ", ".join(unknown))
    candidates.update(supplied)

    facts = data.get("facts", {})
    if facts is None:
        facts = {}
    if not isinstance(facts, dict):
        return fail("facts must be an object")
    for key, value in facts.items():
        if not isinstance(value, bool):
            return fail("every facts value must be boolean (invalid: " + str(key) + ")")
        if not value:
            continue
        if key in REASON_TO_TIER:
            candidates.add(key)
        elif key in ALIASES:
            candidates.add(ALIASES[key])

    # A transfer is expected only after the caller has decided it is necessary.
    # If no supported condition was supplied, use the documented catch-all.
    if not candidates:
        candidates.add("other")

    # Tier is the required priority criterion. Lexical ordering makes ties
    # deterministic while callers should provide only the most accurate same-tier fact.
    selected = sorted(candidates, key=lambda reason: (REASON_TO_TIER[reason], reason))[0]
    summary = make_summary(data)
    if not summary:
        return fail("could not produce a nonempty summary")

    print(json.dumps({
        "ok": True,
        "reason": selected,
        "summary": summary,
        "tier": REASON_TO_TIER[selected],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
