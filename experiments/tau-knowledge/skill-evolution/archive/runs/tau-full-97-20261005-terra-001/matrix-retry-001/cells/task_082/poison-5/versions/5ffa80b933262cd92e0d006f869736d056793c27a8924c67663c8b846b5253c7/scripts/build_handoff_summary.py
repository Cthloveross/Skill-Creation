#!/usr/bin/env python3
"""Build a fact-preserving debit-card human-handoff recommendation.

Reads a single JSON object from stdin and writes a single JSON object to stdout.
This helper does not call tools, transfer customers, file disputes, or change cards.
"""
import json
import sys

POSSESSION_TEXT = {
    "lost_not_possessed": "lost; customer no longer has the physical card",
    "still_possessed": "customer still has the physical card",
    "unknown": "physical-card possession is not established",
}


def clean(value):
    return value.strip() if isinstance(value, str) else ""


def clean_list(data, field, errors):
    value = data.get(field, [])
    if not isinstance(value, list):
        errors.append(field + " must be an array.")
        return []
    return [clean(item) for item in value if clean(item)]


def known_boolean(value, yes, no, unknown):
    if value is True:
        return yes
    if value is False:
        return no
    return unknown


def describe_recurring(recurring, label, errors):
    if not isinstance(recurring, dict):
        errors.append("recurring must be an object for card: " + label)
        return "", False

    merchant = clean(recurring.get("merchant"))
    if not merchant:
        merchant = "merchant not yet identified"
    after_cancellation = known_boolean(
        recurring.get("after_cancellation"),
        "charge occurred after cancellation",
        "customer did not report cancellation before the charge",
        "whether the charge followed cancellation is not established",
    )
    contacted = known_boolean(
        recurring.get("merchant_contacted"),
        "customer contacted the merchant",
        "customer did not contact the merchant",
        "merchant-contact status is not established",
    )
    outcome = clean(recurring.get("merchant_outcome"))
    text = "Recurring subscription claim: " + merchant + "; " + after_cancellation + "; " + contacted
    if outcome:
        text += "; merchant outcome: " + outcome
    text += "."

    declined = recurring.get("declines_cardwide_block")
    if declined is True:
        text += " Customer wants the past charge addressed only. Customer does not want all recurring payments blocked; do not block recurring payments card-wide."
    elif declined is False:
        text += " Customer has not declined a card-wide recurring-payment block; confirm any future-payment request before action."
    return text, True


def describe_card(card, errors):
    if not isinstance(card, dict):
        errors.append("Each cards item must be an object.")
        return "", False, False, False

    label = clean(card.get("label"))
    if not label:
        errors.append("Each card requires a nonempty label.")
        return "", False, False, False

    possession = card.get("possession", "unknown")
    if possession not in POSSESSION_TEXT:
        errors.append("Invalid possession for card: " + label)
        possession = "unknown"

    parts = [label + ": " + POSSESSION_TEXT[possession] + "."]
    unauthorized = card.get("unauthorized_reported") is True
    if unauthorized:
        fraud = known_boolean(
            card.get("fraud_suspected"),
            "customer believes the unauthorized transaction is fraudulent",
            "fraud was not reported as suspected",
            "whether fraud is suspected is not established",
        )
        parts.append("Unauthorized transaction reported; " + fraud + ".")

    atm_issue = clean(card.get("atm_issue"))
    if atm_issue:
        parts.append("ATM issue: " + atm_issue + ".")

    recurring_present = False
    if card.get("recurring") is not None:
        recurring_text, recurring_present = describe_recurring(card["recurring"], label, errors)
        if recurring_text:
            parts.append(recurring_text)

    return " ".join(parts), unauthorized, bool(atm_issue), recurring_present


def build(payload):
    if not isinstance(payload, dict):
        return {
            "reason": None,
            "summary": "",
            "errors": ["Input must be a JSON object."],
            "non_execution_notice": "No action was taken.",
        }

    errors = []
    cards = payload.get("cards")
    if not isinstance(cards, list) or not cards:
        errors.append("cards must be a nonempty array so claims can be routed card by card.")
        cards = []

    card_texts = []
    unauthorized_count = 0
    atm_count = 0
    recurring_count = 0
    security_concern = False
    for card in cards:
        text, unauthorized, has_atm, has_recurring = describe_card(card, errors)
        if text:
            card_texts.append(text)
        unauthorized_count += int(unauthorized)
        atm_count += int(has_atm)
        recurring_count += int(has_recurring)
        if isinstance(card, dict):
            if card.get("fraud_suspected") is True or card.get("possession") == "lost_not_possessed":
                security_concern = True

    if unauthorized_count:
        security_concern = True

    requested = payload.get("human_requested") is True
    if security_concern:
        reason = "fraud_or_security_concern"
    elif requested and (atm_count or recurring_count):
        reason = "complex_billing_dispute"
    elif requested:
        reason = "customer_requests_human_no_specific_reason"
    else:
        reason = None
        errors.append("human_requested is not true; this helper does not recommend a transfer.")

    count = payload.get("reported_transaction_count")
    if isinstance(count, int) and count > 0:
        scope = str(count) + " reported debit-card transaction(s) across " + str(len(card_texts)) + " card(s)"
    else:
        scope = str(len(card_texts)) + " card(s) with reported debit-card issues"

    opening = "Customer explicitly requests a human agent for " + scope + "."
    if security_concern:
        opening += " Fraud/security concern is present."

    identity = clean(payload.get("customer_identity"))
    user_id = clean(payload.get("customer_user_id"))
    identity_parts = []
    if identity:
        identity_parts.append("name: " + identity)
    if user_id:
        identity_parts.append("user ID: " + user_id)
    identity_text = "; ".join(identity_parts) if identity_parts else "identity not supplied"
    verification = clean(payload.get("verification_status")) or "not established"
    identity_line = "Customer record: " + identity_text + ". Verification status: " + verification + "."

    actions = clean_list(payload, "actions_completed", errors)
    unresolved = clean_list(payload, "unresolved_items", errors)
    actions_line = "Actions completed: " + ("; ".join(actions) if actions else "No banking action completed before handoff") + "."
    unresolved_line = "Still needed: " + ("; ".join(unresolved) if unresolved else "None stated") + "."

    summary = "\n\n".join([
        opening,
        identity_line,
        "Card-by-card routing: " + (" ".join(card_texts) if card_texts else "No card facts supplied."),
        actions_line,
        unresolved_line,
    ])
    return {
        "reason": reason,
        "summary": summary,
        "errors": errors,
        "non_execution_notice": "This is a transfer-summary recommendation only. It does not transfer, file disputes, alter cards, or block payments.",
    }


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({
            "reason": None,
            "summary": "",
            "errors": ["Invalid JSON input: " + str(exc)],
            "non_execution_notice": "No action was taken.",
        }, sort_keys=True))
        return 1
    print(json.dumps(build(payload), sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
