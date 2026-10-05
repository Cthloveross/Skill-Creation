#!/usr/bin/env python3
"""Build a fact-preserving debit-card human-handoff recommendation.

Reads one JSON object on stdin and writes one JSON object on stdout. This helper
is non-executing: it never performs a lookup, transfer, verification, dispute,
card action, or payment-setting change.
"""

import json
import re
import sys

SUCCESS_STATUSES = {"ok", "success"}


def text(value):
    return value.strip() if isinstance(value, str) else ""


def successful_objects(payload, key, errors):
    value = payload.get(key, [])
    if value is None:
        return []
    if not isinstance(value, list):
        errors.append(f"{key} must be an array")
        return []
    result = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            errors.append(f"{key}[{index}] must be an object")
            continue
        if text(item.get("status")).lower() in SUCCESS_STATUSES:
            result.append(item)
    return result


def strings(payload, key, errors):
    value = payload.get(key, [])
    if value is None:
        return []
    if not isinstance(value, list):
        errors.append(f"{key} must be an array")
        return []
    result = []
    for index, item in enumerate(value):
        if not isinstance(item, str):
            errors.append(f"{key}[{index}] must be a string")
        elif item.strip():
            result.append(item.strip())
    return result


def case_text(opening, clarifications):
    parts = [opening]
    for item in clarifications:
        parts.extend((text(item.get("question")), text(item.get("result"))))
    return " ".join(part for part in parts if part)


def transfer_reason(source):
    lowered = source.lower()
    security_terms = (
        "unauthorized", "fraud", "fraudulent", "identity theft", "lost",
        "stolen", "security concern",
    )
    billing_terms = ("atm", "subscription", "recurring", "cancelled", "canceled", "billing")
    if any(term in lowered for term in security_terms):
        return "fraud_or_security_concern"
    if any(term in lowered for term in billing_terms):
        return "complex_billing_dispute"
    return "customer_requests_human_no_specific_reason"


def customer_lookup(observations):
    name = ""
    user_id = ""
    cross_product_note = ""
    for item in observations:
        tool = text(item.get("tool"))
        result = text(item.get("result"))
        if tool in {"get_user_information_by_name", "get_user_information_by_id"}:
            if not name:
                found = re.search(r"^\s*name:\s*(.+?)\s*$", result, re.I | re.M)
                if found:
                    name = found.group(1).strip()
            if not user_id:
                found = re.search(r"^\s*user_id:\s*(\S+)\s*$", result, re.I | re.M)
                if found:
                    user_id = found.group(1).strip()
        if tool == "get_credit_card_accounts_by_user" and result:
            if "no records found" in result.lower():
                cross_product_note = "Read-only cross-product check: no credit-card account records found."
            else:
                cross_product_note = "Read-only cross-product check returned credit-card account records for specialist review."
    return name, user_id, cross_product_note


def answer_for_topics(clarifications, topics):
    answers = []
    for item in clarifications:
        question = text(item.get("question"))
        answer = text(item.get("result"))
        combined = (question + " " + answer).lower()
        if answer and any(topic in combined for topic in topics) and answer not in answers:
            answers.append(answer)
    return answers


def block_is_declined(source):
    normalized = source.lower().replace("’", "'").replace("‘", "'")
    patterns = (
        r"(?:do not|don't|dont|does not|doesn't|doesnt) want all recurring",
        r"(?:do not|don't|dont) block",
        r"declin(?:e|ed|es) (?:a )?(?:card-wide|global|all recurring)",
        r"not all recurring",
    )
    return any(re.search(pattern, normalized) for pattern in patterns)


def clarification_entry(index, item):
    question = text(item.get("question"))
    answer = text(item.get("result"))
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
    opening = text(payload.get("opening"))
    if not opening:
        errors.append("opening is required and must be a nonempty string")

    clarifications = successful_objects(payload, "clarifications", errors)
    observations = successful_objects(payload, "read_only_observations", errors)
    actions = strings(payload, "actions_completed", errors)
    unresolved = strings(payload, "unresolved_items", errors)
    verification = text(payload.get("verification_status")) or "not completed"

    for index, item in enumerate(clarifications):
        if not text(item.get("result")):
            errors.append(f"successful clarifications[{index}] is missing result text")

    source = case_text(opening, clarifications)
    reason = transfer_reason(source)
    name, user_id, cross_product_note = customer_lookup(observations)

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
        lines.append("No customer record was located in supplied read-only observations. Verification status: " + verification + ".")

    # Repeat source answers in routing groupings for easy specialist scanning. The
    # complete verbatim record below remains authoritative and prevents information loss.
    security = answer_for_topics(clarifications, ("unauthorized", "fraud", "lost", "stolen", "possession"))
    if security:
        lines.append("Card possession and unauthorized-activity routing: " + " | ".join(security))
    atm = answer_for_topics(clarifications, ("atm",))
    if atm:
        lines.append("ATM issue-to-card routing: " + " | ".join(atm))
    recurring = answer_for_topics(
        clarifications,
        ("subscription", "recurring", "merchant", "refund", "cancelled", "canceled"),
    )
    if recurring:
        lines.append("Subscription/merchant issue-to-card routing: " + " | ".join(recurring))

    if block_is_declined(source):
        lines.append(
            "Customer does not want all recurring payments blocked. Address only the reported past charge; do not block recurring payments card-wide."
        )

    if cross_product_note:
        lines.append(cross_product_note)

    lines.append("Completed clarification record (verbatim; these are known case facts):")
    if clarifications:
        for index, item in enumerate(clarifications, start=1):
            lines.append(clarification_entry(index, item))
    else:
        lines.append("No successful clarification answers were supplied.")

    lines.append("Actions completed before handoff: " + ("; ".join(actions) if actions else "no banking action completed") + ".")
    if unresolved:
        lines.append("Still needed for dispute intake: " + "; ".join(unresolved) + ".")
    else:
        lines.append(
            "Still needed for dispute intake, unless separately collected: transaction identifiers; exact dates and amounts; card IDs; transaction channel; PIN status; ATM operator/network details; completed identity verification; and filing-eligibility facts."
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
