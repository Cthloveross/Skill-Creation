#!/usr/bin/env python3
"""Build a fact-preserving debit-card human-handoff recommendation.

Reads one JSON object from stdin and writes one JSON object to stdout. This program does
not call tools, transfer a customer, file disputes, or make account/card changes.
"""
import json
import sys

POSSESSION_TEXT = {
    "lost_not_possessed": "lost; customer no longer has the physical card",
    "still_possessed": "customer still has the physical card",
    "unknown": "physical-card possession is not yet established",
}


def clean(value):
    return value.strip() if isinstance(value, str) else ""


def bool_text(value, true_text, false_text, unknown_text):
    if value is True:
        return true_text
    if value is False:
        return false_text
    return unknown_text


def card_summary(card, errors):
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
        fraud = bool_text(
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
    recurring = card.get("recurring")
    if recurring is not None:
        if not isinstance(recurring, dict):
            errors.append("recurring must be an object for card: " + label)
        else:
            recurring_present = True
            merchant = clean(recurring.get("merchant"))
            if not merchant:
                merchant = "merchant not yet identified"
            cancellation = bool_text(
                recurring.get("after_cancellation"),
                "charge occurred after cancellation",
                "cancellation status is not established",
                "cancellation status is not established",
            )
            contact = bool_text(
                recurring.get("merchant_contacted"),
                "customer contacted the merchant",
                "customer did not contact the merchant",
                "merchant-contact status is not established",
            )
            outcome = clean(recurring.get("merchant_outcome"))
            sentence = "Recurring subscription claim: " + merchant + "; " + cancellation + "; " + contact
            if outcome:
                sentence += "; merchant outcome: " + outcome
            sentence += "."
            parts.append(sentence)
            if recurring.get("declines_cardwide_block") is True:
                parts.append(
                    "Customer wants the past charge addressed only and does not want a card-wide block of all recurring payments."
                )
            elif recurring.get("declines_cardwide_block") is False:
                parts.append(
                    "Customer has not declined a card-wide recurring-payment block; confirm any future-payment request before action."
                )

    return " ".join(parts), unauthorized, bool(atm_issue), recurring_present


def string_list(data, field, errors):
    value = data.get(field, [])
    if not isinstance(value, list):
        errors.append(field + " must be an array.")
        return []
    return [clean(item) for item in value if clean(item)]


def build(data):
    if not isinstance(data, dict):
        return {
            "reason": None,
            "summary": "",
            "errors": ["Input must be a JSON object."],
            "non_execution_notice": "No action was taken.",
        }

    errors = []
    raw_cards = data.get("cards", [])
    if not isinstance(raw_cards, list) or not raw_cards:
        errors.append("cards must be a nonempty array so claims can be routed card by card.")
        raw_cards = []

    card_lines = []
    unauthorized_count = 0
    atm_count = 0
    recurring_count = 0
    fraud_reported = False
    for card in raw_cards:
        line, unauthorized, has_atm, has_recurring = card_summary(card, errors)
        if line:
            card_lines.append(line)
        unauthorized_count += int(unauthorized)
        atm_count += int(has_atm)
        recurring_count += int(has_recurring)
        if isinstance(card, dict) and card.get("fraud_suspected") is True:
            fraud_reported = True
        if isinstance(card, dict) and card.get("possession") == "lost_not_possessed":
            fraud_reported = True

    requested = data.get("human_requested") is True
    security = unauthorized_count > 0 or fraud_reported
    if security:
        reason = "fraud_or_security_concern"
    elif requested and (atm_count or recurring_count):
        reason = "complex_billing_dispute"
    elif requested:
        reason = "customer_requests_human_no_specific_reason"
    else:
        reason = None
        errors.append("human_requested is not true; this helper does not recommend a transfer.")

    supplied_count = data.get("reported_transaction_count")
    if isinstance(supplied_count, int) and supplied_count > 0:
        scope = str(supplied_count) + " reported debit-card transaction(s) across " + str(len(card_lines)) + " card(s)"
    else:
        scope = str(len(card_lines)) + " card(s) with reported debit-card issues"

    opening = "Customer explicitly requests a human agent for " + scope + "."
    if security:
        opening += " Fraud/security concern is present."
    identity = clean(data.get("customer_identity"))
    verification = clean(data.get("verification_status")) or "not established"
    identity_line = "Customer: " + (identity if identity else "identity not supplied") + ". Verification status: " + verification + "."

    actions = string_list(data, "actions_completed", errors)
    unresolved = string_list(data, "unresolved_items", errors)
    actions_line = "Actions completed: " + ("; ".join(actions) if actions else "No banking action completed before handoff") + "."
    unresolved_line = "Still needed: " + ("; ".join(unresolved) if unresolved else "None stated") + "."

    summary = "\n\n".join([
        opening,
        identity_line,
        "Card-by-card routing: " + (" ".join(card_lines) if card_lines else "No card facts supplied."),
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
