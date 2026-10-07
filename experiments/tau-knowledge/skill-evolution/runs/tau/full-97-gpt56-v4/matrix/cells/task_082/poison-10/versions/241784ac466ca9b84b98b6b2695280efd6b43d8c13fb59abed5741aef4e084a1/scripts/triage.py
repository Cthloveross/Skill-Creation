#!/usr/bin/env python3
"""Create a conservative human-transfer recommendation for debit-card triage.

Input: one JSON object described in SKILL.md on stdin.
Output: one JSON object containing transfer_recommended, reason, summary, basis,
and do_not_claim. This helper is intentionally side-effect free.
"""
import json
import sys

SECURITY_MARKERS = {
    "fraud", "fraud_suspected", "unauthorized", "unauthorized_transaction",
    "unrecognized_transaction", "lost_card", "stolen_card", "card_lost",
    "card_stolen", "account_compromise", "security_concern",
}


def text(value):
    if value is None:
        return ""
    return str(value).strip()


def money(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"${value:,.2f}"
    return text(value)


def transaction_sentence(item):
    card_bits = []
    if text(item.get("card_label")):
        card_bits.append(text(item["card_label"]))
    if text(item.get("card_last4")):
        card_bits.append("ending " + text(item["card_last4"]))
    card = " card " + " ".join(card_bits) if card_bits else ""
    parts = []
    if text(item.get("merchant_or_atm")):
        parts.append(text(item["merchant_or_atm"]))
    if text(item.get("date")):
        parts.append("on " + text(item["date"]))
    if item.get("amount") is not None and money(item.get("amount")):
        parts.append("for " + money(item.get("amount")))
    described = ", ".join(parts) if parts else "transaction details not fully provided"
    circumstance = text(item.get("circumstances"))
    if circumstance:
        described += " (customer reports: " + circumstance + ")"
    return described + card


def choose_reason(indicators, request_human, additional_issue):
    normalized = {text(x).lower().replace(" ", "_") for x in indicators}
    issue = text(additional_issue).lower()
    security = bool(normalized & SECURITY_MARKERS)
    security = security or "unauthorized" in issue or "fraud" in issue
    if security:
        return True, "fraud_or_security_concern", [
            "Customer-reported unauthorized activity, loss/theft, or another security concern requires security escalation.",
            "Fraud/security is a Tier 1 reason and takes priority over a general request for a human or another dispute type."
        ]
    if "complex_billing_dispute" in normalized:
        return True, "complex_billing_dispute", ["A complex billing dispute was identified without a higher-priority security trigger."]
    if request_human:
        return True, "customer_requests_human_no_specific_reason", ["Customer requested a human and no more specific transfer trigger was supplied."]
    return False, "other", ["No transfer trigger was supplied; continue standard intake if appropriate."]


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        raise SystemExit("Input must be one valid JSON object: " + str(exc))
    if not isinstance(data, dict):
        raise SystemExit("Input must be a JSON object")

    customer = data.get("customer") if isinstance(data.get("customer"), dict) else {}
    name = text(customer.get("name"))
    user_id = text(customer.get("user_id"))
    locator = ", ".join(x for x in [name, "user ID " + user_id if user_id else ""] if x)
    if not locator:
        locator = "Customer"

    indicators = data.get("security_indicators", [])
    if not isinstance(indicators, list):
        indicators = [indicators]
    request_human = bool(data.get("request_human", False))
    recommended, reason, basis = choose_reason(indicators, request_human, data.get("additional_issue", ""))

    verification = text(data.get("identity_verification")) or "not established"
    summary_parts = [
        f"{locator} requests {'a human/security review' if recommended else 'assistance'} for debit-card transaction issue(s).",
        f"Identity verification status: {verification}."
    ]
    indicator_text = ", ".join(text(x).replace("_", " ") for x in indicators if text(x))
    if indicator_text:
        summary_parts.append("Reported concern(s): " + indicator_text + ".")

    transactions = data.get("transactions", [])
    if isinstance(transactions, list) and transactions:
        valid = [x for x in transactions if isinstance(x, dict)]
        if valid:
            summary_parts.append("Information gathered: " + "; ".join(transaction_sentence(x) for x in valid) + ".")
    additional = text(data.get("additional_issue"))
    if additional:
        summary_parts.append("Additional issue: " + additional + ".")
    missing = data.get("missing_or_unresolved", [])
    if not isinstance(missing, list):
        missing = [missing]
    missing = [text(x) for x in missing if text(x)]
    if missing:
        summary_parts.append("Outstanding: " + "; ".join(missing) + ".")
    summary_parts.append("No dispute filing or card action is represented by this handoff summary.")

    output = {
        "transfer_recommended": recommended,
        "reason": reason,
        "summary": " ".join(summary_parts),
        "basis": basis,
        "do_not_claim": [
            "Do not claim identity verification unless it was completed and logged.",
            "Do not claim transaction, card, or account lookup results unless actually retrieved.",
            "Do not claim a dispute, recurring block, freeze, closure, or replacement was performed unless the corresponding bank tool succeeded."
        ]
    }
    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
