#!/usr/bin/env python3
"""Create a non-executing, fact-preserving debit-card human-handoff summary.

Reads one JSON object from stdin and emits one JSON object to stdout. It never calls
banking tools or takes account actions. Callers must extract supplied conversation facts
into the structured input rather than relying on this script to interpret prose.
"""
import json
import sys

POSSESSION = {
    "lost_not_possessed": "lost; customer no longer has the physical card",
    "still_possessed": "customer still has the physical card",
    "unknown": "physical-card possession not yet established",
}


def text(value):
    return value.strip() if isinstance(value, str) else ""


def flag(value, yes, no, unknown="not established"):
    if value is True:
        return yes
    if value is False:
        return no
    return unknown


def card_line(card, errors):
    if not isinstance(card, dict):
        errors.append("Each cards item must be an object.")
        return None
    label = text(card.get("label"))
    if not label:
        errors.append("Each card requires a nonempty label.")
        return None
    possession = card.get("possession", "unknown")
    if possession not in POSSESSION:
        errors.append("Invalid possession value for card " + label + ".")
        possession = "unknown"
    details = [label + ": " + POSSESSION[possession] + "."]
    if card.get("unauthorized_reported") is True:
        details.append("Unauthorized transaction reported; " + flag(
            card.get("fraud_suspected"), "customer believes it is fraudulent", 
            "fraud not reported as suspected") + ".")
    elif card.get("unauthorized_reported") is False:
        details.append("No unauthorized transaction assigned to this card.")

    atm = text(card.get("atm_issue"))
    if atm:
        details.append("ATM issue: " + atm + ".")

    recurring = card.get("recurring")
    if recurring is not None:
        if not isinstance(recurring, dict):
            errors.append("recurring for card " + label + " must be an object.")
        else:
            merchant = text(recurring.get("merchant")) or "merchant not yet identified"
            cancelled = flag(recurring.get("after_cancellation"),
                             "charge occurred after cancellation",
                             "cancellation status not established")
            contacted = flag(recurring.get("merchant_contacted"),
                             "customer contacted the merchant",
                             "customer did not contact the merchant")
            outcome = text(recurring.get("merchant_outcome"))
            sentence = "Recurring-charge claim: " + merchant + "; " + cancelled + "; " + contacted
            if outcome:
                sentence += "; merchant outcome: " + outcome
            sentence += "."
            details.append(sentence)
            if recurring.get("declines_cardwide_block") is True:
                details.append("Customer wants the past charge addressed only and does not want a card-wide block of all recurring payments.")
            elif recurring.get("declines_cardwide_block") is False:
                details.append("Customer has not declined a card-wide recurring-payment block; confirm any request and scope before action.")
    return " ".join(details)


def build(data):
    errors = []
    if not isinstance(data, dict):
        return {"errors": ["Input must be a JSON object."], "summary": ""}
    cards = data.get("cards", [])
    if not isinstance(cards, list) or not cards:
        errors.append("cards must be a nonempty array so each dispute can be routed.")
        cards = []
    lines = []
    unauthorized_count = 0
    atm_count = 0
    recurring_count = 0
    for card in cards:
        line = card_line(card, errors)
        if line:
            lines.append(line)
        if isinstance(card, dict):
            unauthorized_count += int(card.get("unauthorized_reported") is True)
            atm_count += int(bool(text(card.get("atm_issue"))))
            recurring_count += int(isinstance(card.get("recurring"), dict))

    requested = data.get("human_requested") is True
    security = data.get("fraud_or_security_concern") is True or unauthorized_count > 0
    if security:
        reason = "fraud_or_security_concern"
    elif requested:
        reason = "complex_billing_dispute" if (atm_count or recurring_count) else "customer_requests_human_no_specific_reason"
    else:
        reason = None
        errors.append("human_requested is not true; no transfer is recommended by this helper.")

    scope = "%d card(s)" % len(lines)
    issues = []
    if unauthorized_count:
        issues.append("%d unauthorized" % unauthorized_count)
    if atm_count:
        issues.append("%d ATM" % atm_count)
    if recurring_count:
        issues.append("%d recurring-charge-after-cancellation" % recurring_count)
    issue_text = ", ".join(issues) if issues else "reported debit-card issues"
    opening = ("Customer explicitly requests a human agent for " + issue_text +
               " disputes across " + scope + ".")
    if security:
        opening += " Suspected fraud/security concern is present."

    verification = text(data.get("verification_status")) or "not established"
    actions = data.get("actions_completed", [])
    if not isinstance(actions, list):
        errors.append("actions_completed must be an array.")
        actions = []
    action_text = "; ".join(text(x) for x in actions if text(x)) or "No banking action completed before handoff"
    unresolved = data.get("unresolved_items", [])
    if not isinstance(unresolved, list):
        errors.append("unresolved_items must be an array.")
        unresolved = []
    unresolved_text = "; ".join(text(x) for x in unresolved if text(x)) or "None stated"

    summary = "\n\n".join([
        opening,
        "Card-by-card routing: " + " ".join(lines),
        "Verification status: " + verification + ". Actions completed: " + action_text + ".",
        "Still needed: " + unresolved_text + ".",
    ])
    return {
        "errors": errors,
        "reason": reason,
        "summary": summary,
        "non_execution_notice": "This output is a transfer-summary recommendation only; it does not transfer, file disputes, alter cards, or block payments."
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(build(payload), sort_keys=True))
    except json.JSONDecodeError as exc:
        print(json.dumps({"errors": ["Invalid JSON input: " + str(exc)], "summary": ""}))
        sys.exit(1)
