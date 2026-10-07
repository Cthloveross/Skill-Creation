#!/usr/bin/env python3
"""Create a fact-preserving, non-executing debit-card human-handoff summary.

The script reads one JSON object from stdin and emits one JSON object on stdout.
It neither invokes bank tools nor changes customer data. Successful clarification
responses are copied into issue-specific sections to prevent loss of supplied facts.
"""

import json
import re
import sys

SUCCESS_STATUSES = {"ok", "success"}


def text(value):
    return value.strip() if isinstance(value, str) else ""


def successful_records(value, field, errors):
    if value is None:
        return []
    if not isinstance(value, list):
        errors.append(f"{field} must be an array.")
        return []
    records = []
    for item in value:
        if not isinstance(item, dict):
            errors.append(f"Each {field} item must be an object.")
            continue
        if text(item.get("status")).lower() in SUCCESS_STATUSES:
            records.append(item)
    return records


def string_list(payload, field, errors):
    value = payload.get(field, [])
    if value is None:
        return []
    if not isinstance(value, list):
        errors.append(f"{field} must be an array.")
        return []
    values = []
    for item in value:
        item_text = text(item)
        if item_text:
            values.append(item_text)
    return values


def combined(record):
    """Return a complete Q&A representation without omitting response context."""
    question = text(record.get("question"))
    answer = text(record.get("result"))
    if question:
        return f"Question: {question} Customer answer: {answer}"
    return f"Customer clarification: {answer}"


def category(record):
    value = (text(record.get("question")) + " " + text(record.get("result"))).lower()
    if any(word in value for word in ("fitlife", "subscription", "recurring", "cancelled", "canceled")):
        return "subscription"
    if "atm" in value:
        return "atm"
    if any(word in value for word in ("unauthorized", "fraud", "lost", "stolen", "possession")):
        return "security"
    return "other"


def merchant_name(record):
    """Extract a stated merchant label conservatively; absence is never invented."""
    value = text(record.get("result"))
    patterns = (
        r"\b([A-Z][A-Za-z0-9&'\-]*(?:\s+[A-Z][A-Za-z0-9&'\-]*){0,3})\s+recurring\s+charge\b",
        r"\b([A-Z][A-Za-z0-9&'\-]*(?:\s+[A-Z][A-Za-z0-9&'\-]*){0,3})\s+subscription\b",
    )
    for pattern in patterns:
        match = re.search(pattern, value)
        if match:
            return match.group(1).strip()
    return ""


def lookup_facts(observations):
    name = ""
    user_id = ""
    credit_check = ""
    for observation in observations:
        tool = text(observation.get("tool"))
        result = text(observation.get("result"))
        result_lower = result.lower()
        if tool in {"get_user_information_by_name", "get_user_information_by_id"}:
            if not name:
                match = re.search(r"^\s*name:\s*(.+?)\s*$", result, re.MULTILINE | re.IGNORECASE)
                if match:
                    name = match.group(1).strip()
            if not user_id:
                match = re.search(r"^\s*user_id:\s*([^\s]+)\s*$", result, re.MULTILINE | re.IGNORECASE)
                if match:
                    user_id = match.group(1).strip()
        elif tool == "get_credit_card_accounts_by_user":
            if "no records found" in result_lower:
                credit_check = "Read-only credit-card cross-product check found no credit-card account records."
            elif result:
                credit_check = "Read-only credit-card cross-product check returned records; receiving specialist should review them."
    return name, user_id, credit_check


def transfer_reason(case_text):
    case_text = case_text.lower()
    if any(word in case_text for word in ("unauthorized", "fraud", "fraudulent", "identity theft", "lost", "stolen")):
        return "fraud_or_security_concern"
    if any(word in case_text for word in ("atm", "subscription", "recurring", "cancelled", "canceled", "billing")):
        return "complex_billing_dispute"
    return "customer_requests_human_no_specific_reason"


def declined_recurring_block(case_text):
    case_text = case_text.lower()
    if "recurring" not in case_text:
        return False
    negatives = (
        "do not want", "don't want", "does not want", "declined", "decline",
        "no recurring block", "not all recurring", "do not block",
    )
    return any(value in case_text for value in negatives)


def result(reason, summary, errors):
    return {
        "reason": reason,
        "summary": summary,
        "errors": errors,
        "non_execution_notice": (
            "This output is a transfer recommendation only; no transfer, dispute, card action, "
            "verification, or payment-setting change was performed."
        ),
    }


def build(payload):
    if not isinstance(payload, dict):
        return result(None, "", ["Input must be a JSON object."])

    errors = []
    opening = text(payload.get("opening"))
    if not opening:
        errors.append("opening is required and must be nonempty.")

    clarifications = successful_records(payload.get("clarifications", []), "clarifications", errors)
    observations = successful_records(payload.get("read_only_observations", []), "read_only_observations", errors)
    actions = string_list(payload, "actions_completed", errors)
    unresolved = string_list(payload, "unresolved_items", errors)
    verification_status = text(payload.get("verification_status")) or "not completed"

    for record in clarifications:
        if not text(record.get("result")):
            errors.append("A successful clarification is missing its result.")

    all_case_text = " ".join(
        [opening] + [text(record.get("question")) + " " + text(record.get("result")) for record in clarifications]
    )
    reason = transfer_reason(all_case_text)
    name, user_id, credit_check = lookup_facts(observations)

    lines = [
        f"Customer explicitly requests a human agent. Opening request: {opening}",
        f"Transfer routing: {reason}.",
    ]
    identity = []
    if name:
        identity.append(f"name: {name}")
    if user_id:
        identity.append(f"user ID: {user_id}")
    if identity:
        lines.append("Located customer record: " + "; ".join(identity) + f". Verification status: {verification_status}.")
    else:
        lines.append(f"No customer record was located from supplied read-only observations. Verification status: {verification_status}.")

    # Put subscription and ATM Q&A first. This keeps card-to-issue assignments adjacent
    # while still preserving every successful customer statement verbatim.
    grouped = {key: [] for key in ("subscription", "atm", "security", "other")}
    for record in clarifications:
        if text(record.get("result")):
            grouped[category(record)].append(record)

    headings = {
        "subscription": "Subscription/recurring issue facts",
        "atm": "ATM issue facts",
        "security": "Unauthorized/fraud and card-possession facts",
        "other": "Other known clarification facts",
    }
    for key in ("subscription", "atm", "security", "other"):
        for record in grouped[key]:
            entry = combined(record)
            if key == "subscription":
                merchant = merchant_name(record)
                if merchant:
                    # Repeating the identified merchant before the answer makes the merchant,
                    # subscription card, and stated preference readable as one case unit.
                    entry = entry.replace(" Customer answer:", f" Merchant identified: {merchant}. Customer answer:", 1)
            lines.append(f"{headings[key]}: {entry}")

    if declined_recurring_block(all_case_text):
        lines.append("Customer does not want all recurring payments blocked; do not block recurring payments card-wide.")
    if credit_check:
        lines.append(credit_check)
    lines.append("Actions completed before handoff: " + ("; ".join(actions) if actions else "no banking action completed") + ".")
    lines.append(
        "Still needed for dispute intake: " + (
            "; ".join(unresolved)
            if unresolved else
            "only facts not supplied in the current record, including transaction identifiers, dates, amounts, transaction channel, PIN status, and filing-eligibility facts as applicable"
        ) + "."
    )
    return result(reason, "\n".join(lines), errors)


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps(result(None, "", [f"Invalid JSON input: {exc}" ]), sort_keys=True))
        return 1
    print(json.dumps(build(payload), sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
