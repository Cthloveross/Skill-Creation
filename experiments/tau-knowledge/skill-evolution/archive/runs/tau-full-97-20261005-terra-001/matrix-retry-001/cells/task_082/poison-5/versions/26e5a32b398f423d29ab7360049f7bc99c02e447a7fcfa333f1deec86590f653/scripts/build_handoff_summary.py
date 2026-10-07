#!/usr/bin/env python3
"""Build a fact-preserving debit-card human-handoff recommendation.

The program reads one JSON object from stdin and emits one JSON object on stdout.
It performs no lookup, transfer, verification, dispute filing, card action, or
payment-setting change.
"""

import json
import re
import sys

SUCCESS_STATUSES = {"ok", "success"}


def as_text(value):
    return value.strip() if isinstance(value, str) else ""


def successful_records(payload, key, errors):
    value = payload.get(key, [])
    if value is None:
        return []
    if not isinstance(value, list):
        errors.append(f"{key} must be an array")
        return []
    accepted = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            errors.append(f"{key}[{index}] must be an object")
            continue
        if as_text(item.get("status")).lower() in SUCCESS_STATUSES:
            accepted.append(item)
    return accepted


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


def all_case_text(opening, clarifications):
    parts = [opening]
    for item in clarifications:
        parts.append(as_text(item.get("question")))
        parts.append(as_text(item.get("result")))
    return " ".join(part for part in parts if part)


def choose_reason(case_text):
    lowered = case_text.lower()
    security_terms = (
        "unauthorized", "fraud", "fraudulent", "identity theft", "lost", "stolen",
        "security concern",
    )
    billing_terms = ("atm", "subscription", "recurring", "cancelled", "canceled", "billing")
    if any(term in lowered for term in security_terms):
        return "fraud_or_security_concern"
    if any(term in lowered for term in billing_terms):
        return "complex_billing_dispute"
    return "customer_requests_human_no_specific_reason"


def clarification_line(item):
    question = as_text(item.get("question"))
    result = as_text(item.get("result"))
    if question:
        return f"Question: {question}\nCustomer answer: {result}"
    return f"Customer clarification: {result}"


def relevant_answer(clarifications, terms):
    """Return successful answers whose question or answer mentions a case topic."""
    found = []
    for item in clarifications:
        combined = (as_text(item.get("question")) + " " + as_text(item.get("result"))).lower()
        if any(term in combined for term in terms):
            answer = as_text(item.get("result"))
            if answer and answer not in found:
                found.append(answer)
    return found


def lookup_details(observations):
    name = ""
    user_id = ""
    credit_card_note = ""
    for item in observations:
        tool = as_text(item.get("tool"))
        result = as_text(item.get("result"))
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
                credit_card_note = "Read-only cross-product check: no credit-card account records found."
            else:
                credit_card_note = "Read-only cross-product check returned credit-card account records for specialist review."
    return name, user_id, credit_card_note


def build(payload):
    if not isinstance(payload, dict):
        return {
            "reason": None,
            "summary": "",
            "errors": ["input must be a JSON object"],
            "non_execution_notice": "No action was performed.",
        }

    errors = []
    opening = as_text(payload.get("opening"))
    if not opening:
        errors.append("opening is required and must be a nonempty string")

    clarifications = successful_records(payload, "clarifications", errors)
    observations = successful_records(payload, "read_only_observations", errors)
    actions = string_list(payload, "actions_completed", errors)
    unresolved = string_list(payload, "unresolved_items", errors)
    verification = as_text(payload.get("verification_status")) or "not completed"

    for index, item in enumerate(clarifications):
        if not as_text(item.get("result")):
            errors.append(f"successful clarifications[{index}] is missing result text")

    source = all_case_text(opening, clarifications)
    reason = choose_reason(source)
    name, user_id, credit_card_note = lookup_details(observations)

    lines = [
        "Human-agent handoff requested for debit-card dispute/security concerns.",
        "Reported scope and opening request: " + opening,
        "Transfer routing reason: " + reason + ".",
    ]

    if name or user_id:
        identity_fields = []
        if name:
            identity_fields.append("name: " + name)
        if user_id:
            identity_fields.append("user ID: " + user_id)
        lines.append(
            "Located customer record: " + "; ".join(identity_fields)
            + ". Verification status: " + verification
            + ". A read-only lookup is not identity verification."
        )
    else:
        lines.append("No customer record was located in supplied read-only observations. Verification status: " + verification + ".")

    # These concise sections aid routing. The complete answers are retained below as
    # authoritative source text, so no fact is lost if natural-language extraction is imperfect.
    security = relevant_answer(clarifications, ("unauthorized", "fraud", "lost", "stolen", "possession"))
    if security:
        lines.append("Security/card-possession routing facts: " + " | ".join(security))
    atm = relevant_answer(clarifications, ("atm",))
    if atm:
        lines.append("ATM routing facts: " + " | ".join(atm))
    recurring = relevant_answer(clarifications, ("subscription", "recurring", "merchant", "refund", "cancelled", "canceled"))
    if recurring:
        lines.append("Subscription/merchant routing facts: " + " | ".join(recurring))

    lowered = source.lower()
    block_declined = any(phrase in lowered for phrase in (
        "do not want all recurring", "don't want all recurring", "does not want all recurring",
        "doesn't want all recurring", "do not block", "don't block", "decline a card-wide",
    ))
    if block_declined:
        lines.append(
            "Customer does not want all recurring payments blocked: address the reported past charge only; do not apply a card-wide recurring-payment block."
        )

    if credit_card_note:
        lines.append(credit_card_note)

    lines.append("Completed clarification record (verbatim; these are known case facts):")
    if clarifications:
        for number, item in enumerate(clarifications, start=1):
            lines.append(f"[{number}] " + clarification_line(item))
    else:
        lines.append("No successful clarification answers were supplied.")

    lines.append("Actions completed before handoff: " + ("; ".join(actions) if actions else "no banking action completed") + ".")
    if unresolved:
        lines.append("Still needed for dispute intake: " + "; ".join(unresolved) + ".")
    else:
        lines.append(
            "Still needed for dispute intake, unless already separately collected: transaction identifiers; exact dates and amounts; card IDs; transaction channel; PIN status; ATM operator/network details; completed identity verification; and filing-eligibility facts."
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
