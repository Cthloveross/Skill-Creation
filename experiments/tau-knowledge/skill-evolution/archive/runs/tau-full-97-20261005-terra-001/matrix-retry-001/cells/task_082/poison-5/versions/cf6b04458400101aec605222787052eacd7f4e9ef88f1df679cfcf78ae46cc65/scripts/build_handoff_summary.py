#!/usr/bin/env python3
"""Build a fact-preserving, non-executing debit-card human-handoff summary.

Reads one JSON object from stdin and emits one JSON object to stdout. The script
never calls tools, transfers a customer, or changes banking data. It retains every
successful clarification verbatim and additionally places card-specific routing
facts in concise sections for the receiving specialist.
"""

import json
import re
import sys

SUCCESS = {"ok", "success"}
CARD_LABEL = r"([A-Z][A-Za-z0-9&'\-]*(?:\s+[A-Z][A-Za-z0-9&'\-]*){0,5})"
CARD_RE = re.compile(
    r"\b(?:my|the)\s+" + CARD_LABEL + r"\s+(?:debit\s+)?card\b"
)


def as_text(value):
    return value.strip() if isinstance(value, str) else ""


def successful_records(payload, key, errors):
    value = payload.get(key, [])
    if value is None:
        return []
    if not isinstance(value, list):
        errors.append(f"{key} must be an array.")
        return []
    output = []
    for item in value:
        if not isinstance(item, dict):
            errors.append(f"Each {key} item must be an object.")
            continue
        if as_text(item.get("status")).lower() in SUCCESS:
            output.append(item)
    return output


def string_list(payload, key, errors):
    value = payload.get(key, [])
    if value is None:
        return []
    if not isinstance(value, list):
        errors.append(f"{key} must be an array.")
        return []
    return [as_text(item) for item in value if as_text(item)]


def qa(record):
    question = as_text(record.get("question"))
    answer = as_text(record.get("result"))
    if question:
        return f"Question: {question} Customer answer: {answer}"
    return f"Customer clarification: {answer}"


def all_text(records):
    return " ".join(
        as_text(item.get("question")) + " " + as_text(item.get("result"))
        for item in records
    )


def cards_in(value):
    """Return distinct customer-visible card labels in source order."""
    found = []
    for match in CARD_RE.finditer(value):
        label = re.sub(r"\s+", " ", match.group(1)).strip()
        if label.lower() not in {item.lower() for item in found}:
            found.append(label)
    return found


def card_after_issue(value, terms):
    """Find a stated card following an issue phrase without inventing a mapping."""
    for term in terms:
        pattern = re.compile(
            re.escape(term) + r"[^.]{0,180}?\bon\s+(?:my|the)\s+" +
            CARD_LABEL + r"\s+(?:debit\s+)?card\b",
            re.IGNORECASE,
        )
        match = pattern.search(value)
        if match:
            return re.sub(r"\s+", " ", match.group(1)).strip()
    return ""


def first_matching(records, words):
    for record in records:
        value = (as_text(record.get("question")) + " " + as_text(record.get("result"))).lower()
        if any(word in value for word in words):
            return record
    return None


def merchant_from_text(value):
    """Conservatively extract a capitalized merchant supplied with recurring wording."""
    patterns = [
        r"\b([A-Z][A-Za-z0-9&'\-]*(?:\s+[A-Z][A-Za-z0-9&'\-]*){0,4})\s+recurring\s+charge\b",
        r"\b([A-Z][A-Za-z0-9&'\-]*(?:\s+[A-Z][A-Za-z0-9&'\-]*){0,4})\s+subscription\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, value)
        if match:
            return match.group(1).strip()
    return ""


def lookup_facts(observations):
    name = ""
    user_id = ""
    credit = ""
    for observation in observations:
        tool = as_text(observation.get("tool"))
        result = as_text(observation.get("result"))
        if tool in {"get_user_information_by_name", "get_user_information_by_id"}:
            if not name:
                match = re.search(r"^\s*name:\s*(.+?)\s*$", result, re.MULTILINE | re.IGNORECASE)
                if match:
                    name = match.group(1).strip()
            if not user_id:
                match = re.search(r"^\s*user_id:\s*(\S+)\s*$", result, re.MULTILINE | re.IGNORECASE)
                if match:
                    user_id = match.group(1).strip()
        if tool == "get_credit_card_accounts_by_user":
            if "no records found" in result.lower():
                credit = "Read-only credit-card cross-product check found no credit-card account records."
            elif result:
                credit = "Read-only credit-card cross-product check returned records for specialist review."
    return name, user_id, credit


def reason_for(case_text):
    lowered = case_text.lower()
    if any(word in lowered for word in ("unauthorized", "fraud", "fraudulent", "identity theft", "lost", "stolen")):
        return "fraud_or_security_concern"
    if any(word in lowered for word in ("atm", "subscription", "recurring", "cancelled", "canceled", "billing")):
        return "complex_billing_dispute"
    return "customer_requests_human_no_specific_reason"


def declined_broad_block(case_text):
    lowered = case_text.lower()
    if "recurring" not in lowered:
        return False
    negatives = (
        "do not want", "don't want", "does not want", "declined", "decline",
        "do not block", "don't block", "not all recurring", "no recurring block",
    )
    return any(term in lowered for term in negatives)


def response(reason, summary, errors):
    return {
        "reason": reason,
        "summary": summary,
        "errors": errors,
        "non_execution_notice": (
            "This is a transfer recommendation only; no transfer, dispute, verification, "
            "card action, or payment-setting change was performed."
        ),
    }


def build(payload):
    if not isinstance(payload, dict):
        return response(None, "", ["Input must be a JSON object."])

    errors = []
    opening = as_text(payload.get("opening"))
    if not opening:
        errors.append("opening is required and must be nonempty.")

    clarifications = successful_records(payload, "clarifications", errors)
    observations = successful_records(payload, "read_only_observations", errors)
    actions = string_list(payload, "actions_completed", errors)
    unresolved = string_list(payload, "unresolved_items", errors)
    verification = as_text(payload.get("verification_status")) or "not completed"

    for record in clarifications:
        if not as_text(record.get("result")):
            errors.append("A successful clarification is missing its result.")

    case_text = opening + " " + all_text(clarifications)
    reason = reason_for(case_text)
    name, user_id, credit_check = lookup_facts(observations)

    security = first_matching(clarifications, ("unauthorized", "fraud", "lost", "stolen", "possession"))
    atm = first_matching(clarifications, ("atm",))
    subscription = first_matching(clarifications, ("subscription", "recurring", "cancelled", "canceled"))
    preference = first_matching(clarifications, ("all future recurring", "block every", "recurring payments"))

    lines = []

    # Put routing facts first. This makes each issue and associated card readily visible,
    # then the source Q&A below supplies the complete supporting detail.
    if atm:
        source = as_text(atm.get("result"))
        card = card_after_issue(source, ("atm",))
        if not card:
            card = card_after_issue(as_text(atm.get("question")) + " " + source, ("atm",))
        prefix = f"ATM issue routing: {card} card." if card else "ATM issue routing: card assignment not supplied."
        lines.append(prefix + " Customer-reported detail: " + source)

    if subscription:
        source = as_text(subscription.get("result"))
        surrounding = as_text(subscription.get("question")) + " " + source
        card = card_after_issue(source, ("subscription", "recurring", "cancelled", "canceled"))
        if not card:
            card = card_after_issue(surrounding, ("subscription", "recurring", "cancelled", "canceled"))
        merchant = merchant_from_text(case_text)
        parts = ["Subscription/recurring issue routing:"]
        if card:
            parts.append(f"{card} card;")
        if merchant:
            parts.append(f"merchant: {merchant};")
        parts.append("customer-reported detail: " + source)
        lines.append(" ".join(parts))

    if security:
        lines.append("Unauthorized/fraud and card-possession facts: " + as_text(security.get("result")))

    if preference:
        lines.append("Future recurring-payment preference: " + as_text(preference.get("result")))
    if declined_broad_block(case_text):
        lines.append("Customer does not want all recurring payments blocked; do not block recurring payments card-wide.")

    lines.append(f"Customer explicitly requests a human agent. Opening request: {opening}")
    lines.append(f"Transfer routing: {reason}.")
    identity = []
    if name:
        identity.append(f"name: {name}")
    if user_id:
        identity.append(f"user ID: {user_id}")
    if identity:
        lines.append("Located customer record: " + "; ".join(identity) + f". Verification status: {verification}; lookup alone is not verification.")
    else:
        lines.append(f"No customer record was located in supplied read-only observations. Verification status: {verification}.")
    if credit_check:
        lines.append(credit_check)

    # Preserve all source answers, including ones already condensed above. This prevents
    # future intake fields or customer wording from being lost during routing extraction.
    for record in clarifications:
        lines.append("Successful clarification retained verbatim: " + qa(record))

    lines.append("Actions completed before handoff: " + ("; ".join(actions) if actions else "no banking action completed") + ".")
    if unresolved:
        lines.append("Still needed for dispute intake: " + "; ".join(unresolved) + ".")
    else:
        lines.append(
            "Still needed for dispute intake: transaction identifiers, exact dates and amounts, card IDs, "
            "transaction channel, PIN status, ATM operator/network details, verification, and filing-eligibility "
            "facts as applicable. Customer-supplied card, merchant, contact, and preference facts above are known."
        )

    return response(reason, "\n".join(lines), errors)


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps(response(None, "", [f"Invalid JSON input: {exc}"]), sort_keys=True))
        return 1
    print(json.dumps(build(payload), sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
