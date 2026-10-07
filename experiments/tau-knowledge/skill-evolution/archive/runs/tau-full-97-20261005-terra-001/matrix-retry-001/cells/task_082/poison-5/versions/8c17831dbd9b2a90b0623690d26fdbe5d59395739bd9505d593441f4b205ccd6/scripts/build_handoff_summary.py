#!/usr/bin/env python3
"""Build a factual debit-card human-handoff summary.

Reads one JSON object from stdin and writes one JSON object to stdout. This is a
non-executing helper: it never performs a lookup, transfer, verification,
dispute, card action, or payment-setting change.
"""

import json
import re
import sys

SUCCESS_STATUSES = {"ok", "success"}


def clean(value):
    return value.strip() if isinstance(value, str) else ""


def successful_items(payload, key, errors):
    value = payload.get(key, [])
    if value is None:
        return []
    if not isinstance(value, list):
        errors.append(f"{key} must be an array")
        return []
    output = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            errors.append(f"{key}[{index}] must be an object")
            continue
        if clean(item.get("status")).lower() in SUCCESS_STATUSES:
            output.append(item)
    return output


def string_list(payload, key, errors):
    value = payload.get(key, [])
    if value is None:
        return []
    if not isinstance(value, list):
        errors.append(f"{key} must be an array")
        return []
    output = []
    for index, item in enumerate(value):
        if not isinstance(item, str):
            errors.append(f"{key}[{index}] must be a string")
        elif item.strip():
            output.append(item.strip())
    return output


def full_case_text(opening, clarifications):
    pieces = [opening]
    for item in clarifications:
        pieces.extend((clean(item.get("question")), clean(item.get("result"))))
    return " ".join(piece for piece in pieces if piece)


def select_reason(source):
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


def lookup_facts(observations):
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
                cross_product = "Read-only cross-product check returned credit-card account records for specialist review."
    return name, user_id, cross_product


def answers_matching(clarifications, keywords):
    answers = []
    for item in clarifications:
        question = clean(item.get("question"))
        answer = clean(item.get("result"))
        if answer and any(word in (question + " " + answer).lower() for word in keywords):
            if answer not in answers:
                answers.append(answer)
    return answers


def block_declined(source):
    source = source.lower().replace("’", "'").replace("‘", "'")
    patterns = (
        r"(?:do not|don't|dont|does not|doesn't|doesnt) want all recurring",
        r"(?:do not|don't|dont) block",
        r"declin(?:e|ed|es) (?:a )?(?:card-wide|global|all recurring)",
        r"not all recurring",
    )
    return any(re.search(pattern, source) for pattern in patterns)


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

    clarifications = successful_items(payload, "clarifications", errors)
    observations = successful_items(payload, "read_only_observations", errors)
    actions = string_list(payload, "actions_completed", errors)
    unresolved = string_list(payload, "unresolved_items", errors)
    verification = clean(payload.get("verification_status")) or "not completed"

    for index, item in enumerate(clarifications):
        if not clean(item.get("result")):
            errors.append(f"successful clarifications[{index}] is missing result text")

    source = full_case_text(opening, clarifications)
    reason = select_reason(source)
    name, user_id, cross_product = lookup_facts(observations)

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
            "Verification status: " + verification + ". "
            "Read-only lookup is not completed identity verification."
        )
    else:
        lines.append(
            "No customer record was located in the supplied read-only observations. "
            "Verification status: " + verification + "."
        )

    # These focused sections deliberately repeat customer answers so a specialist can
    # immediately see card-to-issue associations. The verbatim record below prevents
    # loss of other details in those answers.
    security = answers_matching(
        clarifications, ("unauthorized", "fraud", "lost", "stolen", "possession")
    )
    atm = answers_matching(clarifications, ("atm",))
    recurring = answers_matching(
        clarifications,
        ("subscription", "recurring", "merchant", "refund", "cancelled", "canceled"),
    )
    if security or atm or recurring:
        lines.append("Card-specific routing:")
        if security:
            lines.append("Unauthorized activity and card-possession facts: " + " | ".join(security))
        if atm:
            lines.append("ATM issue-to-card facts: " + " | ".join(atm))
        if recurring:
            lines.append("Subscription/merchant issue-to-card facts: " + " | ".join(recurring))

    if block_declined(source):
        lines.append(
            "Recurring-payment preference: customer does not want all recurring payments blocked; "
            "address only the reported past charge and do not apply a card-wide recurring-payment block."
        )
    if cross_product:
        lines.append(cross_product)

    lines.append("Completed clarification record (verbatim; these are known case facts):")
    if clarifications:
        for index, item in enumerate(clarifications, start=1):
            lines.append(clarification_line(index, item))
    else:
        lines.append("No successful clarification answers were supplied.")

    lines.append(
        "Actions completed before handoff: " +
        ("; ".join(actions) if actions else "no banking action completed") + "."
    )
    if unresolved:
        lines.append("Still needed for dispute intake: " + "; ".join(unresolved) + ".")
    else:
        lines.append(
            "Still needed for dispute intake, unless separately collected: transaction identifiers; "
            "exact dates and amounts; card IDs; transaction channel; PIN status; ATM operator/network "
            "details; completed identity verification; and filing-eligibility facts."
        )

    return {
        "reason": reason,
        "summary": "\n".join(lines),
        "errors": errors,
        "non_execution_notice": (
            "This is a transfer recommendation only; no transfer, dispute, verification, card action, "
            "or payment-setting change was performed."
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
