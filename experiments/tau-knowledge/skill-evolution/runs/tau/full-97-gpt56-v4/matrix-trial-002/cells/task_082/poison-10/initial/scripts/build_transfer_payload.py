#!/usr/bin/env python3
"""Build a human-transfer recommendation without performing banking actions.

Reads one JSON object from stdin and emits one JSON object to stdout. See SKILL.md
for the public input schema.
"""
import json
import sys

VALID_REASONS = {
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

# The ordering is only used when structured input provides several alternatives and
# no security concern. Security concerns deliberately take precedence.
TIER_ORDER = [
    "account_closure_request", "deceased_account_holder", "legal_or_regulatory_matter",
    "account_ownership_dispute", "complex_billing_dispute", "abusive_customer_behavior",
    "third_party_inquiry", "technical_system_error",
    "customer_demands_after_unavailable_offer_refusal",
    "unconfirmed_external_communication", "kb_search_unsuccessful_customer_requests_transfer",
    "specialized_department_required", "accessibility_or_special_needs",
    "customer_frustrated_demands_human", "supervisor_request_service_complaint",
    "customer_requests_human_no_specific_reason",
    "request_completed_customer_wants_human_followup", "other",
]


def text(value):
    return str(value).strip() if value is not None else ""


def choose_reason(data, errors):
    if data.get("security_concern") is True:
        return "fraud_or_security_concern"
    supplied = data.get("other_applicable_reasons", [])
    if not isinstance(supplied, list):
        errors.append("other_applicable_reasons must be an array when provided")
        supplied = []
    usable = [x for x in supplied if isinstance(x, str) and x in VALID_REASONS]
    invalid = [x for x in supplied if not isinstance(x, str) or x not in VALID_REASONS]
    if invalid:
        errors.append("other_applicable_reasons contains unsupported reason code(s)")
    for reason in TIER_ORDER:
        if reason in usable:
            return reason
    return "other"


def build_summary(data, errors):
    parts = []
    customer = text(data.get("customer"))
    if customer:
        parts.append("Customer: " + customer + ".")

    if data.get("security_concern") is True:
        parts.append("Customer reports possible unauthorized activity or another security concern.")
    elif data.get("security_concern") not in (False, None):
        errors.append("security_concern must be true or false when provided")

    lost = text(data.get("lost_card_details"))
    if lost:
        parts.append("Card status: " + lost + ".")

    issues = data.get("issues", [])
    if not isinstance(issues, list):
        errors.append("issues must be an array")
        issues = []
    if not issues:
        errors.append("at least one reported issue is required for a useful handoff")
    else:
        rendered = []
        for index, issue in enumerate(issues, start=1):
            if not isinstance(issue, dict):
                errors.append("issue %d must be an object" % index)
                continue
            fields = []
            for label, key in (("card", "card"), ("date", "date"), ("amount", "amount"),
                               ("merchant/ATM", "merchant_or_atm"), ("reported issue", "description")):
                value = text(issue.get(key))
                if value:
                    fields.append(label + ": " + value)
            if not fields:
                errors.append("issue %d has no factual details" % index)
            else:
                rendered.append("Item %d: %s." % (index, "; ".join(fields)))
        parts.extend(rendered)

    verification = text(data.get("identity_verification_status"))
    if verification:
        parts.append("Identity verification status: " + verification + ".")
    else:
        parts.append("Identity verification status: not provided.")

    attempted = text(data.get("attempted"))
    if attempted:
        parts.append("Before transfer: " + attempted + ".")
    else:
        parts.append("Before transfer: no account action represented by this handoff payload.")
    return " ".join(parts)


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"validation_errors": ["invalid JSON: " + str(exc)]}))
        return
    if not isinstance(data, dict):
        print(json.dumps({"validation_errors": ["input must be a JSON object"]}))
        return

    errors = []
    reason = choose_reason(data, errors)
    summary = build_summary(data, errors)
    print(json.dumps({
        "reason": reason,
        "summary": summary,
        "needs_human_transfer": True,
        "validation_errors": errors,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
