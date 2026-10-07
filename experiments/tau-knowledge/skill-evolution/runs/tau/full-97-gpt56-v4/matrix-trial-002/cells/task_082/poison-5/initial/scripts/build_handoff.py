#!/usr/bin/env python3
"""Build a factual debit-card-dispute transfer payload from JSON on stdin.

This helper only recommends the transfer reason and summary.  It never invokes
bank tools and must not be treated as proof of verification or dispute filing.
"""
import json
import sys

ALLOWED_REASONS = {
    "fraud_or_security_concern",
    "complex_billing_dispute",
    "customer_requests_human_no_specific_reason",
    "other",
}


def text(value):
    return str(value).strip() if value is not None else ""


def issue_line(issue, index):
    parts = [f"Issue {index}"]
    card = text(issue.get("card_reference"))
    merchant = text(issue.get("merchant_or_atm"))
    date = text(issue.get("date"))
    amount = issue.get("amount")
    issue_type = text(issue.get("issue_type")) or "other"
    channel = text(issue.get("channel"))
    details = text(issue.get("details"))
    if card:
        parts.append(f"card/account reference {card}")
    if merchant:
        parts.append(f"merchant/ATM {merchant}")
    if date:
        parts.append(f"date {date}")
    if amount is not None and text(amount):
        parts.append(f"amount ${amount}")
    parts.append(f"reported issue {issue_type}")
    if channel and channel != "unknown":
        parts.append(f"channel {channel}")
    if details:
        parts.append(details)
    return "; ".join(parts) + "."


def main(data):
    issues = data.get("issues", [])
    if not isinstance(issues, list):
        raise ValueError("issues must be an array")
    if not isinstance(data.get("security_notes", []), list):
        raise ValueError("security_notes must be an array")
    if not isinstance(data.get("unresolved_items", []), list):
        raise ValueError("unresolved_items must be an array")
    if not isinstance(data.get("attempts", []), list):
        raise ValueError("attempts must be an array")

    unauthorized = any(text(i.get("issue_type")) == "unauthorized" for i in issues if isinstance(i, dict))
    security = bool(data.get("security_concern")) or unauthorized
    recurring = any(text(i.get("issue_type")) == "recurring_after_cancellation" for i in issues if isinstance(i, dict))
    if security:
        reason = "fraud_or_security_concern"
    elif recurring:
        reason = "complex_billing_dispute"
    elif data.get("customer_requested_human"):
        reason = "customer_requests_human_no_specific_reason"
    else:
        reason = "other"

    missing = []
    warnings = []
    for n, issue in enumerate(issues, 1):
        if not isinstance(issue, dict):
            raise ValueError(f"issues[{n - 1}] must be an object")
        for field in issue.get("known_missing", []):
            item = text(field)
            if item:
                missing.append(f"Issue {n}: {item}")
        for key, label in (("card_reference", "card/account reference"), ("merchant_or_atm", "merchant/ATM"),
                           ("date", "transaction date"), ("amount", "amount")):
            if key not in issue or issue.get(key) in (None, ""):
                missing.append(f"Issue {n}: {label} not supplied")
        if text(issue.get("issue_type")) == "unauthorized" and text(issue.get("channel")) in ("", "unknown"):
            missing.append(f"Issue {n}: whether unauthorized activity was in person or online/phone")
        if text(issue.get("issue_type")) == "atm_cash_discrepancy":
            warnings.append(f"Issue {n}: retain ATM ownership and requested-versus-dispensed amounts for specialist review.")

    for item in data.get("unresolved_items", []):
        item = text(item)
        if item:
            missing.append(item)
    ref = text(data.get("customer_reference"))
    segments = []
    if ref:
        segments.append(f"Customer reference: {ref}.")
    segments.append("Customer requests a human agent for debit-card dispute assistance.")
    if security:
        segments.append("Security/fraud concern reported; prioritize specialist review.")
    notes = [text(x) for x in data.get("security_notes", []) if text(x)]
    if notes:
        segments.append("Security facts: " + " | ".join(notes) + ".")
    segments.extend(issue_line(i, n) for n, i in enumerate(issues, 1))
    attempts = [text(x) for x in data.get("attempts", []) if text(x)]
    if attempts:
        segments.append("Already attempted/reported: " + " | ".join(attempts) + ".")
    if missing:
        segments.append("Outstanding information: " + " | ".join(missing) + ".")
    if not issues:
        warnings.append("No transaction issue details were supplied; obtain them during the handoff.")
    if security:
        warnings.append("Do not represent the card as frozen, closed, or replaced unless the corresponding tool action succeeds.")
    if recurring:
        warnings.append("A past recurring-charge dispute is separate from a future recurring-payment block.")
    return {"reason": reason, "summary": " ".join(segments), "missing_information": missing, "review_warnings": warnings}


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("top-level JSON must be an object")
        print(json.dumps(main(payload), ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
