#!/usr/bin/env python3
"""Create a deterministic, policy-tiered recommendation for a human transfer.

Input: JSON object documented in SKILL.md. Output: {transfer, reason, summary}.
The program does not invoke bank tools.
"""
import json
import sys

# Ordered by tier; only the tier determines precedence. Ordering within a tier is
# deterministic for the unusual case where several supplied facts are true.
RULES = [
    ("fraud_or_security_concern", "fraud_or_security_concern"),
    ("account_closure_request", "account_closure_request"),
    ("deceased_account_holder", "deceased_account_holder"),
    ("legal_or_regulatory_matter", "legal_or_regulatory_matter"),
    ("account_ownership_dispute", "account_ownership_dispute"),
    ("complex_billing_dispute", "complex_billing_dispute"),
    ("abusive_customer_behavior", "abusive_customer_behavior"),
    ("third_party_inquiry", "third_party_inquiry"),
    ("technical_system_error", "technical_system_error"),
    ("persistent_unavailable_offer_demand", "customer_demands_after_unavailable_offer_refusal"),
    ("unconfirmed_external_communication", "unconfirmed_external_communication"),
    ("kb_search_unsuccessful_then_transfer", "kb_search_unsuccessful_customer_requests_transfer"),
    ("specialized_department_required", "specialized_department_required"),
    ("accessibility_or_special_needs", "accessibility_or_special_needs"),
    ("frustrated_human_request", "customer_frustrated_demands_human"),
    ("supervisor_service_complaint", "supervisor_request_service_complaint"),
    ("human_request_no_specific_reason", "customer_requests_human_no_specific_reason"),
    ("completed_request_human_followup", "request_completed_customer_wants_human_followup"),
]
ALLOWED_FACTS = {fact for fact, _ in RULES}


def fail(message):
    print(json.dumps({"error": message}), file=sys.stdout)
    raise SystemExit(2)


def compact_summary(issue, steps):
    parts = [issue.strip()]
    usable = [s.strip() for s in steps if isinstance(s, str) and s.strip()]
    if usable:
        parts.append("Attempted/offered: " + "; ".join(usable))
    return " ".join(parts)


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        fail("input must be valid JSON: " + str(exc))
    if not isinstance(payload, dict):
        fail("input must be a JSON object")

    issue = payload.get("issue_summary")
    if not isinstance(issue, str) or not issue.strip():
        fail("issue_summary must be a nonempty string")
    steps = payload.get("attempted_steps", [])
    if not isinstance(steps, list):
        fail("attempted_steps must be an array of strings")
    facts = payload.get("facts", {})
    if not isinstance(facts, dict):
        fail("facts must be an object")
    unknown = sorted(set(facts) - ALLOWED_FACTS)
    if unknown:
        fail("unknown fact keys: " + ", ".join(unknown))
    if any(not isinstance(value, bool) for value in facts.values()):
        fail("each supplied fact value must be boolean")

    reason = next((reason for fact, reason in RULES if facts.get(fact, False)), None)
    summary = compact_summary(issue, steps)
    if reason is None:
        result = {
            "transfer": False,
            "reason": None,
            "summary": summary,
        }
    else:
        result = {
            "transfer": True,
            "reason": reason,
            "summary": summary,
        }
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
