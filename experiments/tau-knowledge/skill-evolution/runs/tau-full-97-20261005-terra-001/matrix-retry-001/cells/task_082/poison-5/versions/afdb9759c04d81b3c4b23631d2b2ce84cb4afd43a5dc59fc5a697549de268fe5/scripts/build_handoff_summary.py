#!/usr/bin/env python3
"""Create a fact-preserving recommendation for a debit-card human handoff.

Reads one JSON object from stdin and emits one JSON object on stdout. This program
performs no transfer, banking lookup, verification, card action, dispute filing, or
payment-setting change.
"""

import json
import re
import sys

SUCCESS = {"ok", "success"}


def text(value):
    return value.strip() if isinstance(value, str) else ""


def records(payload, key, errors):
    value = payload.get(key, [])
    if value is None:
        return []
    if not isinstance(value, list):
        errors.append(f"{key} must be an array")
        return []
    result = []
    for item in value:
        if not isinstance(item, dict):
            errors.append(f"each {key} item must be an object")
            continue
        if text(item.get("status")).lower() in SUCCESS:
            result.append(item)
    return result


def string_list(payload, key, errors):
    value = payload.get(key, [])
    if value is None:
        return []
    if not isinstance(value, list):
        errors.append(f"{key} must be an array")
        return []
    return [text(item) for item in value if text(item)]


def case_text(opening, clarifications):
    pieces = [opening]
    for item in clarifications:
        pieces.extend([text(item.get("question")), text(item.get("result"))])
    return " ".join(pieces)


def transfer_reason(value):
    lowered = value.lower()
    fraud_terms = ("unauthorized", "fraud", "fraudulent", "identity theft", "lost", "stolen")
    billing_terms = ("atm", "subscription", "recurring", "cancelled", "canceled", "billing")
    if any(term in lowered for term in fraud_terms):
        return "fraud_or_security_concern"
    if any(term in lowered for term in billing_terms):
        return "complex_billing_dispute"
    return "customer_requests_human_no_specific_reason"


def issue_card(value, issue_terms):
    """Return a customer-stated card label associated with an issue, if explicit."""
    for term in issue_terms:
        pattern = re.compile(
            r"\b" + re.escape(term) + r"\b[^.]{0,220}?\bon\s+(?:my|the)\s+"
            r"([A-Za-z][A-Za-z0-9 &'\-]*?)\s+(?:debit\s+)?card\b",
            re.IGNORECASE,
        )
        match = pattern.search(value)
        if match:
            return re.sub(r"\s+", " ", match.group(1)).strip()
    return ""


def first_related_answer(clarifications, terms):
    for item in clarifications:
        combined = text(item.get("question")) + " " + text(item.get("result"))
        if any(term in combined.lower() for term in terms):
            return text(item.get("result"))
    return ""


def lookup_details(observations):
    name = ""
    user_id = ""
    credit_check = ""
    for item in observations:
        tool = text(item.get("tool"))
        result = text(item.get("result"))
        if tool in {"get_user_information_by_name", "get_user_information_by_id"}:
            if not name:
                match = re.search(r"^\s*name:\s*(.+?)\s*$", result, re.MULTILINE | re.I)
                if match:
                    name = match.group(1).strip()
            if not user_id:
                match = re.search(r"^\s*user_id:\s*(\S+)\s*$", result, re.MULTILINE | re.I)
                if match:
                    user_id = match.group(1).strip()
        if tool == "get_credit_card_accounts_by_user" and result:
            if "no records found" in result.lower():
                credit_check = "Read-only credit-card cross-product check found no credit-card account records."
            else:
                credit_check = "Read-only credit-card cross-product check returned records for specialist review."
    return name, user_id, credit_check


def answer_line(item):
    question = text(item.get("question"))
    answer = text(item.get("result"))
    if question:
        return f"Question: {question} Customer answer: {answer}"
    return f"Customer clarification: {answer}"


def build(payload):
    if not isinstance(payload, dict):
        return {
            "reason": None, "summary": "", "errors": ["input must be a JSON object"],
            "non_execution_notice": "No action was performed."
        }

    errors = []
    opening = text(payload.get("opening"))
    if not opening:
        errors.append("opening is required and must be nonempty")
    clarifications = records(payload, "clarifications", errors)
    observations = records(payload, "read_only_observations", errors)
    actions = string_list(payload, "actions_completed", errors)
    unresolved = string_list(payload, "unresolved_items", errors)
    verification = text(payload.get("verification_status")) or "not completed"

    for item in clarifications:
        if not text(item.get("result")):
            errors.append("a successful clarification is missing result text")

    source = case_text(opening, clarifications)
    reason = transfer_reason(source)
    name, user_id, credit_check = lookup_details(observations)
    lines = []

    # Place explicit issue/card mappings before generic narration. The entire successful
    # answer is also retained below, avoiding loss when a wording pattern is unfamiliar.
    atm_card = issue_card(source, ("atm error", "atm"))
    if atm_card:
        lines.append(f"ATM issue routing: {atm_card} card; customer reported an ATM error on this card.")

    subscription_card = issue_card(source, (
        "cancelled subscription charge", "canceled subscription charge", "subscription charge",
        "recurring charge", "subscription",
    ))
    if subscription_card:
        lines.append(
            f"Subscription/recurring issue routing: {subscription_card} card; customer reported a charge after cancellation."
        )

    security_answer = first_related_answer(
        clarifications, ("unauthorized", "fraud", "lost", "stolen", "possession")
    )
    if security_answer:
        lines.append("Unauthorized/fraud and card-possession facts: " + security_answer)

    merchant_answer = first_related_answer(clarifications, ("merchant", "refund", "subscription"))
    if merchant_answer:
        lines.append("Merchant/contact facts: " + merchant_answer)

    preference_answer = first_related_answer(
        clarifications, ("recurring payments", "recurring-payment", "block every")
    )
    if preference_answer:
        lines.append("Future recurring-payment preference: " + preference_answer)

    lowered = source.lower()
    declined = ("recurring" in lowered and any(term in lowered for term in (
        "don't want", "do not want", "doesn't want", "does not want", "decline", "do not block", "don't block"
    )))
    if declined:
        lines.append("Customer does not want all recurring payments blocked; do not apply a card-wide recurring-payment block.")

    lines.append("Customer explicitly requests a human agent. Opening request: " + opening)
    lines.append("Transfer routing: " + reason + ".")
    if name or user_id:
        fields = []
        if name:
            fields.append("name: " + name)
        if user_id:
            fields.append("user ID: " + user_id)
        lines.append("Located customer record: " + "; ".join(fields) +
                     ". Verification status: " + verification + "; lookup alone is not identity verification.")
    else:
        lines.append("No customer record was located in supplied read-only observations. Verification status: " + verification + ".")
    if credit_check:
        lines.append(credit_check)

    # Verbatim preservation is deliberate: answers often contain details beyond the
    # fixed intake fields and must reach the receiving specialist unchanged.
    for item in clarifications:
        lines.append("Successful clarification retained verbatim: " + answer_line(item))

    lines.append("Actions completed before handoff: " + ("; ".join(actions) if actions else "no banking action completed") + ".")
    if unresolved:
        lines.append("Still needed for dispute intake: " + "; ".join(unresolved) + ".")
    else:
        lines.append(
            "Still needed for dispute intake: transaction identifiers, exact dates and amounts, card IDs, transaction channel, "
            "PIN status, ATM operator/network details, completed identity verification, and filing-eligibility facts as applicable. "
            "Customer-supplied facts retained above are known."
        )

    return {
        "reason": reason,
        "summary": "\n".join(lines),
        "errors": errors,
        "non_execution_notice": (
            "This is a transfer recommendation only; no transfer, dispute, verification, card action, or payment-setting change was performed."
        ),
    }


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({
            "reason": None, "summary": "", "errors": [f"invalid JSON input: {exc}"],
            "non_execution_notice": "No action was performed."
        }, sort_keys=True))
        return 1
    print(json.dumps(build(payload), sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
