#!/usr/bin/env python3
"""Create a transfer-ready debit-card fraud/dispute handoff summary.

Input is one JSON object on stdin:
{
  "opening": str,
  "clarifications": [ {"status": str, "question": str, "result": str}, ... ],
  "read_only_observations": [ {"status": str, "tool": str, "result": str}, ... ],
  "verification_status": str,
  "actions_completed": [str, ...],
  "unresolved_items": [str, ...]
}

Output is one JSON object with reason, summary, errors, and non_execution_notice.
The program is purely textual and performs no banking or customer action.
"""

import json
import re
import sys

SUCCESS = {"ok", "success"}


def clean(value):
    return value.strip() if isinstance(value, str) else ""


def arrays_of_objects(payload, field, errors):
    value = payload.get(field, [])
    if value is None:
        return []
    if not isinstance(value, list):
        errors.append(f"{field} must be an array")
        return []
    output = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            errors.append(f"{field}[{index}] must be an object")
        elif clean(item.get("status")).lower() in SUCCESS:
            output.append(item)
    return output


def strings(payload, field, errors):
    value = payload.get(field, [])
    if value is None:
        return []
    if not isinstance(value, list):
        errors.append(f"{field} must be an array")
        return []
    output = []
    for index, item in enumerate(value):
        if not isinstance(item, str):
            errors.append(f"{field}[{index}] must be a string")
        elif item.strip():
            output.append(item.strip())
    return output


def joined_case_text(opening, clarifications):
    fragments = [opening]
    for item in clarifications:
        fragments.extend((clean(item.get("question")), clean(item.get("result"))))
    return " ".join(part for part in fragments if part)


def reason_for(source):
    lowered = source.lower()
    security = (
        "unauthorized", "fraud", "fraudulent", "identity theft", "lost",
        "stolen", "security concern",
    )
    billing = ("atm", "subscription", "recurring", "cancelled", "canceled", "billing")
    if any(term in lowered for term in security):
        return "fraud_or_security_concern"
    if any(term in lowered for term in billing):
        return "complex_billing_dispute"
    return "customer_requests_human_no_specific_reason"


def lookup_details(observations):
    name = ""
    user_id = ""
    cross_product = ""
    for item in observations:
        tool = clean(item.get("tool"))
        result = clean(item.get("result"))
        if tool in {"get_user_information_by_name", "get_user_information_by_id"}:
            if not name:
                match = re.search(r"^\s*name:\s*(.+?)\s*$", result, re.I | re.M)
                if match:
                    name = match.group(1).strip()
            if not user_id:
                match = re.search(r"^\s*user_id:\s*(\S+)\s*$", result, re.I | re.M)
                if match:
                    user_id = match.group(1).strip()
        if tool == "get_credit_card_accounts_by_user" and result:
            if "no records found" in result.lower():
                cross_product = "Read-only cross-product check: no credit-card account records found."
            else:
                cross_product = "Read-only cross-product check: credit-card account records were returned for specialist review."
    return name, user_id, cross_product


def account_names(source):
    """Extract named account/card labels without relying on fixed customer values."""
    pattern = re.compile(
        r"\b([A-Z][A-Za-z0-9-]*(?:\s+[A-Z][A-Za-z0-9-]*){0,4}\s+Account)\s+(?:debit\s+)?card\b",
        re.I,
    )
    found = []
    for match in pattern.finditer(source):
        label = re.sub(r"\s+", " ", match.group(1)).strip()
        if label.lower() not in {item.lower() for item in found}:
            found.append(label)
    return found


def answers_matching(clarifications, terms):
    answers = []
    for item in clarifications:
        answer = clean(item.get("result"))
        question = clean(item.get("question"))
        corpus = (question + " " + answer).lower()
        if answer and any(term in corpus for term in terms) and answer not in answers:
            answers.append(answer)
    return answers


def snippets_for_card(card, clarifications):
    """Return each successful answer that explicitly names the card."""
    short = card.lower().replace(" account", "").strip()
    snippets = []
    for item in clarifications:
        answer = clean(item.get("result"))
        if answer and (card.lower() in answer.lower() or short in answer.lower()):
            snippets.append(answer)
    return snippets


def merchant_name(source):
    patterns = (
        r"only want (?:the )?([A-Z][A-Za-z0-9&.'-]*(?:\s+[A-Z][A-Za-z0-9&.'-]*){0,4})\s+(?:recurring )?charge",
        r"([A-Z][A-Za-z0-9&.'-]*(?:\s+[A-Z][A-Za-z0-9&.'-]*){0,4})\s+(?:subscription|recurring)\s+(?:charge|merchant)",
    )
    for pattern in patterns:
        match = re.search(pattern, source)
        if match:
            return match.group(1).strip()
    return ""


def block_declined(source):
    text = source.lower().replace("’", "'").replace("‘", "'")
    patterns = (
        r"(?:do not|don't|dont|does not|doesn't|doesnt) want all recurring",
        r"(?:do not|don't|dont) (?:want )?(?:a )?(?:card-wide )?(?:recurring )?block",
        r"not all recurring",
        r"declin(?:e|ed|es) (?:a )?(?:card-wide|global|all recurring)",
    )
    return any(re.search(pattern, text) for pattern in patterns)


def clarification_line(index, item):
    question = clean(item.get("question"))
    answer = clean(item.get("result"))
    if question:
        return f"[{index}] Question: {question}\n[{index}] Customer answer: {answer}"
    return f"[{index}] Customer clarification: {answer}"


def build(payload):
    if not isinstance(payload, dict):
        return {
            "reason": None,
            "summary": "",
            "errors": ["input must be a JSON object"],
            "non_execution_notice": "No action was performed.",
        }

    errors = []
    opening = clean(payload.get("opening"))
    if not opening:
        errors.append("opening is required and must be a nonempty string")

    clarifications = arrays_of_objects(payload, "clarifications", errors)
    observations = arrays_of_objects(payload, "read_only_observations", errors)
    actions = strings(payload, "actions_completed", errors)
    unresolved = strings(payload, "unresolved_items", errors)
    verification = clean(payload.get("verification_status")) or "not completed"

    for index, item in enumerate(clarifications):
        if not clean(item.get("result")):
            errors.append(f"successful clarifications[{index}] is missing result text")

    source = joined_case_text(opening, clarifications)
    reason = reason_for(source)
    name, user_id, cross_product = lookup_details(observations)
    cards = account_names(source)
    merchant = merchant_name(source)
    atm_answers = answers_matching(clarifications, ("atm",))
    subscription_answers = answers_matching(
        clarifications, ("subscription", "recurring", "merchant", "refund", "cancelled", "canceled")
    )

    lines = [
        "Human-agent handoff requested for debit-card dispute/security concerns.",
        "Opening request and reported scope: " + opening,
        "Transfer routing reason: " + reason + ".",
    ]

    if name or user_id:
        identity = []
        if name:
            identity.append("name: " + name)
        if user_id:
            identity.append("user ID: " + user_id)
        lines.append(
            "Located customer record: " + "; ".join(identity) + ". "
            "Formal identity verification status: " + verification + "; read-only lookup is not formal verification."
        )
    else:
        lines.append("No customer record was located in supplied read-only observations. Formal identity verification status: " + verification + ".")

    lines.append("Card-specific routing:")
    if cards:
        for card in cards:
            facts = snippets_for_card(card, clarifications)
            line = card + " debit card: "
            if facts:
                line += "Known clarification(s): " + " | ".join(facts)
            else:
                line += "card-specific dispute details were not supplied."

            # Put the merchant and recurring-charge context directly on the card line when
            # that answer assigns a cancelled subscription to this card.
            card_lower = card.lower()
            subscription_on_card = any(
                card_lower in answer.lower() and any(term in answer.lower() for term in ("subscription", "recurring", "cancelled", "canceled"))
                for answer in subscription_answers
            )
            if subscription_on_card and merchant:
                line += "; subscription merchant: " + merchant + "."
            lines.append("- " + line)
    else:
        lines.append("- Named card/account labels were not supplied in the successful clarifications.")

    if atm_answers:
        lines.append("ATM routing detail: " + " | ".join(atm_answers))
    if subscription_answers:
        merchant_text = ("; identified merchant: " + merchant) if merchant else ""
        lines.append("Subscription merchant/contact detail: " + " | ".join(subscription_answers) + merchant_text + ".")

    if block_declined(source):
        lines.append(
            "Recurring-payment preference: customer does not want all recurring payments blocked; "
            "address only the reported past charge and do not apply a card-wide recurring-payment block."
        )

    if cross_product:
        lines.append(cross_product)

    lines.append("Completed clarification record (known facts):")
    if clarifications:
        for index, item in enumerate(clarifications, start=1):
            lines.append(clarification_line(index, item))
    else:
        lines.append("No successful clarification answers were supplied.")

    lines.append("Actions completed before handoff: " + ("; ".join(actions) if actions else "no banking action completed") + ".")
    if unresolved:
        lines.append("Still needed for dispute intake: " + "; ".join(unresolved) + ".")
    else:
        lines.append(
            "Still needed for dispute intake: transaction identifiers; card IDs; exact transaction dates and amounts; "
            "transaction channels; PIN status; ATM operator/network; formal identity verification; and filing eligibility."
        )

    return {
        "reason": reason,
        "summary": "\n".join(lines),
        "errors": errors,
        "non_execution_notice": (
            "This is a transfer recommendation only; no transfer, dispute, verification, card action, "
            "or recurring-payment setting was performed."
        ),
    }


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({
            "reason": None,
            "summary": "",
            "errors": [f"invalid JSON input: {exc}"],
            "non_execution_notice": "No action was performed.",
        }, sort_keys=True))
        return 1
    print(json.dumps(build(payload), sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
