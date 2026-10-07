#!/usr/bin/env python3
"""Create a non-executing, fact-preserving debit-card human-handoff summary.

Reads one JSON object from stdin and emits one JSON object on stdout. The program
never calls tools or changes customer data. Successful clarification Q&A records are
kept verbatim in the resulting summary so material facts survive handoff compression.
"""

import json
import re
import sys

SUCCESS = {"ok", "success"}


def clean(value):
    return value.strip() if isinstance(value, str) else ""


def as_string_list(payload, key, errors):
    value = payload.get(key, [])
    if value is None:
        return []
    if not isinstance(value, list):
        errors.append("%s must be an array." % key)
        return []
    output = []
    for item in value:
        item = clean(item)
        if item:
            output.append(item)
    return output


def successful_records(value, key, errors):
    if value is None:
        return []
    if not isinstance(value, list):
        errors.append("%s must be an array." % key)
        return []
    records = []
    for item in value:
        if not isinstance(item, dict):
            errors.append("Each %s item must be an object." % key)
            continue
        if clean(item.get("status")).lower() in SUCCESS:
            records.append(item)
    return records


def lookup_facts(observations):
    """Extract handoff-safe identity and cross-product facts from public tool text."""
    name = ""
    user_id = ""
    credit_check = ""
    for observation in observations:
        tool = clean(observation.get("tool"))
        result = clean(observation.get("result"))
        lower = result.lower()
        if tool in {"get_user_information_by_name", "get_user_information_by_id"}:
            if not name:
                match = re.search(r"^\s*name:\s*(.+?)\s*$", result, re.MULTILINE | re.IGNORECASE)
                if match:
                    name = match.group(1).strip()
            if not user_id:
                match = re.search(r"^\s*user_id:\s*([^\s]+)\s*$", result, re.MULTILINE | re.IGNORECASE)
                if match:
                    user_id = match.group(1).strip()
        if tool == "get_credit_card_accounts_by_user":
            if "no records found" in lower:
                credit_check = "Read-only credit-card cross-product check found no credit-card account records."
            elif result:
                credit_check = "Read-only credit-card cross-product check returned records; receiving specialist should review them."
    return name, user_id, credit_check


def choose_reason(all_case_text):
    text = all_case_text.lower()
    security_terms = ("unauthorized", "fraud", "fraudulent", "identity theft", "lost", "stolen")
    billing_terms = ("atm", "subscription", "recurring", "cancelled", "canceled", "billing")
    if any(term in text for term in security_terms):
        return "fraud_or_security_concern"
    if any(term in text for term in billing_terms):
        return "complex_billing_dispute"
    return "customer_requests_human_no_specific_reason"


def recurring_block_declined(all_case_text):
    text = all_case_text.lower()
    if "recurring" not in text:
        return False
    negative_terms = (
        "do not want", "don't want", "does not want", "decline", "declined",
        "no,", "not want", "no recurring block",
    )
    return any(term in text for term in negative_terms)


def build(payload):
    if not isinstance(payload, dict):
        return result(None, "", ["Input must be a JSON object."])

    errors = []
    opening = clean(payload.get("opening"))
    if not opening:
        errors.append("opening is required and must be nonempty.")

    clarifications = successful_records(payload.get("clarifications", []), "clarifications", errors)
    observations = successful_records(payload.get("read_only_observations", []), "read_only_observations", errors)
    actions = as_string_list(payload, "actions_completed", errors)
    unresolved = as_string_list(payload, "unresolved_items", errors)
    verification = clean(payload.get("verification_status")) or "not completed"

    qa_lines = []
    case_text = opening
    for record in clarifications:
        question = clean(record.get("question"))
        answer = clean(record.get("result"))
        if not answer:
            errors.append("A successful clarification is missing its result.")
            continue
        # Include question as well as answer: its wording carries the requested issue
        # category and preserves the relation of a response to its card/merchant topic.
        if question:
            qa_lines.append("Question: %s Answer: %s" % (question, answer))
            case_text += " " + question
        else:
            qa_lines.append("Customer clarification: %s" % answer)
        case_text += " " + answer

    if not qa_lines:
        errors.append("At least one successful clarification is required for a fact-preserving handoff.")

    name, user_id, credit_check = lookup_facts(observations)
    identity_bits = []
    if name:
        identity_bits.append("name: %s" % name)
    if user_id:
        identity_bits.append("user ID: %s" % user_id)
    if identity_bits:
        identity_line = "Located customer record: %s. Verification status: %s." % (
            "; ".join(identity_bits), verification
        )
    else:
        identity_line = "No customer record was located from supplied read-only observations. Verification status: %s." % verification

    reason = choose_reason(case_text)
    lines = [
        "Customer explicitly requests a human agent. Opening request: %s" % opening,
        "Transfer routing: %s." % reason,
        identity_line,
        "Known clarification facts (preserved verbatim for the receiving specialist):",
    ]
    lines.extend("- " + line for line in qa_lines)

    if recurring_block_declined(case_text):
        lines.append("Customer does not want all recurring payments blocked; do not block recurring payments card-wide.")
    if credit_check:
        lines.append(credit_check)
    lines.append("Actions completed before handoff: %s." % (
        "; ".join(actions) if actions else "no banking action completed"
    ))
    lines.append("Still needed for dispute intake: %s." % (
        "; ".join(unresolved) if unresolved else "only facts not supplied in the current record, including transaction identifiers, dates, amounts, transaction channel, PIN status, and filing-eligibility facts as applicable"
    ))

    return result(reason, "\n".join(lines), errors)


def result(reason, summary, errors):
    return {
        "reason": reason,
        "summary": summary,
        "errors": errors,
        "non_execution_notice": "This output is a transfer recommendation only; no transfer, dispute, card action, verification, or payment-setting change was performed.",
    }


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps(result(None, "", ["Invalid JSON input: %s" % exc]), sort_keys=True))
        return 1
    print(json.dumps(build(payload), sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
