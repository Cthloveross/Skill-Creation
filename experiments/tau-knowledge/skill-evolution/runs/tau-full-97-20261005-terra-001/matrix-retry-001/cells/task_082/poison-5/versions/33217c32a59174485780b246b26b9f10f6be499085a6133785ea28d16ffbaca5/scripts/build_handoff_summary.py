#!/usr/bin/env python3
"""Build a fact-preserving recommendation for a debit-card human handoff.

Reads one JSON object from stdin and writes one JSON object to stdout. It performs
no banking action and does not call external tools.
"""

import json
import sys

NUMBER_WORDS = {
    1: "one", 2: "two", 3: "three", 4: "four", 5: "five",
    6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten",
}
POSSESSION = {
    "lost_not_possessed": "lost; customer no longer has the physical card",
    "still_possessed": "customer still has the physical card",
    "unknown": "physical-card possession was not supplied",
}


def text(value):
    return value.strip() if isinstance(value, str) else ""


def string_list(payload, key, errors):
    value = payload.get(key, [])
    if not isinstance(value, list):
        errors.append("%s must be an array." % key)
        return []
    return [text(item) for item in value if text(item)]


def count_phrase(value):
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        word = NUMBER_WORDS.get(value)
        return "%s (%d)" % (word, value) if word else str(value)
    return ""


def describe_recurring(value, label, errors):
    if not isinstance(value, dict):
        errors.append("recurring for %s must be an object." % label)
        return "", False

    merchant = text(value.get("merchant"))
    if not merchant:
        errors.append("recurring.merchant is required when a recurring claim is supplied for %s." % label)
        merchant = "merchant not identified"

    if value.get("after_cancellation") is True:
        cancellation = "charge occurred after cancellation"
    elif value.get("after_cancellation") is False:
        cancellation = "customer did not report cancellation before the charge"
    else:
        cancellation = "whether the charge followed cancellation is unresolved"

    if value.get("merchant_contacted") is True:
        contact = "customer contacted the merchant"
    elif value.get("merchant_contacted") is False:
        contact = "customer did not contact the merchant"
    else:
        contact = "merchant-contact status is unresolved"

    outcome = text(value.get("merchant_outcome"))
    result = "Subscription/recurring claim: %s; %s; %s" % (merchant, cancellation, contact)
    if outcome:
        result += "; merchant outcome: %s" % outcome
    result += "."

    declined = value.get("declines_cardwide_block")
    if declined is True:
        result += " Customer wants the past charge addressed only. Customer does not want all recurring payments blocked; do not block recurring payments card-wide."
    elif declined is False:
        result += " Customer did not decline a card-wide recurring-payment block; confirm any future-payment request before action."
    return result, True


def describe_card(card, errors):
    if not isinstance(card, dict):
        errors.append("Each cards item must be an object.")
        return "", False, False, False, False

    label = text(card.get("label"))
    if not label:
        errors.append("Each card requires a nonempty label.")
        return "", False, False, False, False

    possession = card.get("possession", "unknown")
    if possession not in POSSESSION:
        errors.append("Invalid possession value for %s." % label)
        possession = "unknown"

    parts = ["%s: %s." % (label, POSSESSION[possession])]
    unauthorized = card.get("unauthorized_reported") is True
    fraud = card.get("fraud_suspected") is True
    if unauthorized:
        if fraud:
            status = "customer believes the unauthorized transaction is fraudulent"
        elif card.get("fraud_suspected") is False:
            status = "customer did not report fraud as suspected"
        else:
            status = "whether fraud is suspected is unresolved"
        parts.append("Unauthorized transaction reported; %s." % status)

    atm_issue = text(card.get("atm_issue"))
    if atm_issue:
        parts.append("ATM issue: %s." % atm_issue)

    has_recurring = card.get("recurring") is not None
    if has_recurring:
        recurring_text, _ = describe_recurring(card["recurring"], label, errors)
        if recurring_text:
            parts.append(recurring_text)

    return " ".join(parts), unauthorized, fraud, possession == "lost_not_possessed", bool(atm_issue) or has_recurring


def build(payload):
    if not isinstance(payload, dict):
        return output(None, "", ["Input must be a JSON object."])

    errors = []
    human_requested = payload.get("human_requested") is True
    if not human_requested:
        errors.append("human_requested must be true for a handoff recommendation.")

    verification = text(payload.get("verification_status"))
    if not verification:
        errors.append("verification_status is required.")
        verification = "not established"

    cards = payload.get("cards")
    if not isinstance(cards, list) or not cards:
        errors.append("cards must be a nonempty array.")
        cards = []

    card_sections = []
    has_unauthorized = False
    has_suspected_fraud = False
    has_lost = False
    has_other_issue = False
    for card in cards:
        section, unauthorized, fraud, lost, other_issue = describe_card(card, errors)
        if section:
            card_sections.append(section)
        has_unauthorized = has_unauthorized or unauthorized
        has_suspected_fraud = has_suspected_fraud or fraud
        has_lost = has_lost or lost
        has_other_issue = has_other_issue or other_issue

    security = has_unauthorized or has_suspected_fraud or has_lost
    if security:
        reason = "fraud_or_security_concern"
    elif human_requested and has_other_issue:
        reason = "complex_billing_dispute"
    elif human_requested:
        reason = "customer_requests_human_no_specific_reason"
    else:
        reason = None

    transaction_count = count_phrase(payload.get("reported_transaction_count"))
    card_count = count_phrase(len(card_sections))
    if transaction_count:
        scope = "%s reported debit-card transactions across %s cards" % (transaction_count, card_count)
    else:
        scope = "%s cards with reported debit-card issues" % card_count
    opening = "Customer explicitly requests a human agent for %s." % scope
    if security:
        opening += " Fraud/security concern is present."

    name = text(payload.get("customer_name"))
    user_id = text(payload.get("user_id"))
    identity = []
    if name:
        identity.append("name: %s" % name)
    if user_id:
        identity.append("user ID: %s" % user_id)
    record = "; ".join(identity) if identity else "no customer record supplied"
    identity_line = "Customer record: %s. Verification status: %s." % (record, verification)

    actions = string_list(payload, "actions_completed", errors)
    unresolved = string_list(payload, "unresolved_items", errors)
    actions_line = "Actions completed: %s." % (
        "; ".join(actions) if actions else "no banking action completed before handoff"
    )
    unresolved_line = "Still needed for dispute intake: %s." % (
        "; ".join(unresolved) if unresolved else "none stated"
    )
    routing = "Card-by-card routing: %s" % (
        " ".join(card_sections) if card_sections else "no card facts supplied."
    )

    summary = "\n\n".join([opening, identity_line, routing, actions_line, unresolved_line])
    return output(reason, summary, errors)


def output(reason, summary, errors):
    return {
        "reason": reason,
        "summary": summary,
        "errors": errors,
        "non_execution_notice": "This output is a handoff recommendation only; no transfer, dispute, card action, or payment-setting change was performed.",
    }


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps(output(None, "", ["Invalid JSON input: %s" % exc]), sort_keys=True))
        return 1
    print(json.dumps(build(payload), sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
