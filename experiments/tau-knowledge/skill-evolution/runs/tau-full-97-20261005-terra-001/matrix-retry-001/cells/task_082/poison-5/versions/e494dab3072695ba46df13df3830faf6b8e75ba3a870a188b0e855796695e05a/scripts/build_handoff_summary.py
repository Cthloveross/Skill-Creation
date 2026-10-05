#!/usr/bin/env python3
"""Build a factual debit-card human-handoff summary.

Input: one JSON object on stdin with opening, clarifications,
read_only_observations, verification_status, actions_completed, and optional
unresolved_items. Output: one JSON object with reason, summary, errors, and a
non_execution_notice. This helper performs no customer or banking action.
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
        elif text(item.get("status")).lower() in SUCCESS_STATUSES:
            result.append(item)
    return result


def string_array(payload, key, errors):
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
    values = [opening]
    for item in clarifications:
        values.append(text(item.get("question")))
        values.append(text(item.get("result")))
    return " ".join(value for value in values if value)


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
    cross_product = ""
    for item in observations:
        tool = text(item.get("tool"))
        result = text(item.get("result"))
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


def matching_answers(clarifications, keywords):
    found = []
    for item in clarifications:
        question = text(item.get("question"))
        answer = text(item.get("result"))
        corpus = (question + " " + answer).lower()
        if answer and any(keyword in corpus for keyword in keywords) and answer not in found:
            found.append(answer)
    return found


def block_is_declined(source):
    lowered = source.lower().replace("’", "'").replace("‘", "'")
    patterns = (
        r"(?:do not|don't|dont|does not|doesn't|doesnt) want all recurring",
        r"(?:do not|don't|dont) (?:want )?(?:a )?(?:card-wide )?(?:recurring )?block",
        r"declin(?:e|ed|es) (?:a )?(?:card-wide|global|all recurring)",
        r"not all recurring",
    )
    return any(re.search(pattern, lowered) for pattern in patterns)


def clarification_record(index, item):
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
    actions = string_array(payload, "actions_completed", errors)
    unresolved = string_array(payload, "unresolved_items", errors)
    verification = text(payload.get("verification_status")) or "not completed"

    for index, item in enumerate(clarifications):
        if not text(item.get("result")):
            errors.append(f"successful clarifications[{index}] is missing result text")

    source = case_text(opening, clarifications)
    reason = transfer_reason(source)
    name, user_id, cross_product = customer_lookup(observations)

    lines = [
        "Human-agent handoff requested for debit-card dispute/security concerns.",
        "Opening request and reported scope: " + opening,
        "Transfer routing reason: " + reason + ".",
    ]

    if name or user_id:
        record = []
        if name:
            record.append("name: " + name)
        if user_id:
            record.append("user ID: " + user_id)
        lines.append(
            "Located customer record: " + "; ".join(record) + ". "
            "Verification status: " + verification + ". "
            "Read-only lookup is not completed identity verification."
        )
    else:
        lines.append("No customer record was located in supplied read-only observations. Verification status: " + verification + ".")

    security = matching_answers(clarifications, ("unauthorized", "fraud", "lost", "stolen", "possession"))
    atm = matching_answers(clarifications, ("atm",))
    recurring = matching_answers(
        clarifications,
        ("subscription", "recurring", "merchant", "refund", "cancelled", "canceled", "fitlife"),
    )
    if security or atm or recurring:
        lines.append("Card-specific routing:")
        if security:
            lines.append("Unauthorized/fraud and physical-card status: " + " | ".join(security))
        if atm:
            lines.append("ATM issue-to-card assignment: " + " | ".join(atm))
        if recurring:
            lines.append("Subscription/merchant issue-to-card assignment: " + " | ".join(recurring))

    if block_is_declined(source):
        lines.append(
            "Recurring-payment preference: customer does not want all recurring payments blocked; "
            "address only the reported past charge and do not apply a card-wide recurring-payment block."
        )
    if cross_product:
        lines.append(cross_product)

    lines.append("Completed clarification record (verbatim; these are known case facts):")
    if clarifications:
        for index, item in enumerate(clarifications, start=1):
            lines.append(clarification_record(index, item))
    else:
        lines.append("No successful clarification answers were supplied.")

    lines.append("Actions completed before handoff: " + ("; ".join(actions) if actions else "no banking action completed") + ".")
    if unresolved:
        lines.append("Still needed for dispute intake: " + "; ".join(unresolved) + ".")
    else:
        lines.append(
            "Still needed for dispute intake, unless separately collected: transaction identifiers; exact dates and amounts; "
            "card IDs; transaction channel; PIN status; ATM operator/network details; completed identity verification; and filing-eligibility facts."
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
