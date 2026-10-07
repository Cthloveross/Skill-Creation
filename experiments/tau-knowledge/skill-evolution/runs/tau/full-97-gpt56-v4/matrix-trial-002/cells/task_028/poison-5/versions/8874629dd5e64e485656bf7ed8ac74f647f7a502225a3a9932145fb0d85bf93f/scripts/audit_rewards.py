#!/usr/bin/env python3
"""Audit normalized credit-card reward transactions.

Reads one JSON object from stdin and writes one JSON object to stdout. See SKILL.md
for the input/output schema. Uses Decimal and ROUND_FLOOR so currency calculations
do not depend on binary floating point.
"""

import json
import re
import sys
from decimal import Decimal, InvalidOperation, ROUND_FLOOR


def as_text(value):
    return "" if value is None else str(value).strip()


def normalized(value):
    return as_text(value).casefold()


def money(value):
    text = as_text(value).replace("$", "").replace(",", "")
    return Decimal(text)


def whole_points(amount, points_per_dollar):
    return int((amount * Decimal(str(points_per_dollar))).to_integral_value(rounding=ROUND_FLOOR))


def is_non_purchase(category):
    c = normalized(category)
    blocked = (
        "cash equivalent", "balance transfer", "fee", "gift card",
        "person-to-person", "person to person", "interest", "insurance",
        "return", "refund", "credit",
    )
    return any(term in c for term in blocked)


def parse_raw_transactions(text):
    """Parse the stable line-oriented transaction lookup rendering when supplied."""
    starts = list(re.finditer(r"(?m)^\d+\. Record ID:.*$", text))
    records = []
    for index, start in enumerate(starts):
        end = starts[index + 1].start() if index + 1 < len(starts) else len(text)
        chunk = text[start.start():end]
        fields = {}
        for line in chunk.splitlines():
            match = re.match(r"^\s{3}([a-z_]+):\s*(.*?)\s*$", line)
            if match:
                fields[match.group(1)] = match.group(2)
        if fields.get("transaction_id"):
            records.append(fields)
    return records


def base_finding(tx, verdict, reason, expected=None, conditional=False):
    finding = {
        "transaction_id": as_text(tx.get("transaction_id")),
        "card_type": as_text(tx.get("credit_card_type") or tx.get("card_type")),
        "merchant_name": as_text(tx.get("merchant_name")),
        "category": as_text(tx.get("category")),
        "verdict": verdict,
        "reason": reason,
    }
    try:
        finding["amount"] = format(money(tx.get("transaction_amount")), ".2f")
    except (InvalidOperation, ValueError):
        pass
    try:
        finding["recorded_points"] = int(Decimal(as_text(tx.get("rewards_earned")).split()[0]))
    except (InvalidOperation, ValueError, IndexError):
        pass
    if expected is not None:
        finding["expected_points"] = expected
        if "recorded_points" in finding:
            difference = expected - finding["recorded_points"]
            finding["difference_points"] = difference
            finding["difference_cash_back"] = format(Decimal(difference) / Decimal("100"), ".2f")
            if verdict == "candidate":
                finding["verdict"] = "match" if difference == 0 else "mismatch"
    if conditional:
        finding["conditional"] = True
    return finding


def rate_for_transaction(tx, green_category_is_qualifying):
    card = normalized(tx.get("credit_card_type") or tx.get("card_type"))
    category = normalized(tx.get("category"))
    merchant = normalized(tx.get("merchant_name"))

    if card == "business platinum rewards card":
        if is_non_purchase(category):
            return (0, "Business Platinum excludes this transaction type from rewards.")
        if category in {"travel", "software", "media"}:
            return (4, "Business Platinum earns 4 points per dollar in this bonus category.")
        return (Decimal("1.5"), "Business Platinum earns 1.5 points per dollar outside its bonus categories.")

    if card == "silver rewards card":
        if is_non_purchase(category):
            return (0, "This transaction type is not an eligible Silver Rewards purchase.")
        if category in {"travel", "software"}:
            return (4, "Silver Rewards earns 4 points per dollar for merchant-coded Travel or Software.")
        return (None, "Silver Rewards' default rate is not documented for this category.")

    if card == "ecocard":
        if merchant in {"target", "walmart", "amazon", "thredup"}:
            return (1, "This EcoCard merchant is an explicit green-rate exclusion and earns the standard rate.")
        ev_words = ("charge", "charging", "supercharger")
        is_ev = any(word in merchant for word in ev_words)
        certified_ev = merchant in {"tesla supercharger", "chargepoint", "evgo"}
        if is_ev and not certified_ev:
            return (1, "EV charging receives EcoCard's green rate only at certified partner networks.")
        if category in {"green", "sustainable"}:
            if green_category_is_qualifying:
                return (5, "EcoCard earns 5 points per dollar for a supplied qualifying Green/Sustainable category.")
            return (None, "The record is Green/Sustainable, but merchant qualification was not established.")
        return (1, "EcoCard earns 1 point per dollar outside qualifying green purchases.")

    if card == "crypto-cash back":
        return ("conditional_2pct", "Crypto-Cash Back states 2% only on eligible purchases; available terms do not define eligibility.")

    return (None, "No supported documented reward rule is available for this card type.")


def audit_one(tx, green_category_is_qualifying):
    transaction_id = as_text(tx.get("transaction_id"))
    status = normalized(tx.get("status"))
    if not transaction_id:
        return base_finding(tx, "not_reviewed", "Missing transaction_id.")
    if status and status not in {"completed", "posted"}:
        return base_finding(tx, "not_reviewed", "Only completed/posted purchase records are automatically audited.")
    try:
        amount = money(tx.get("transaction_amount"))
        recorded = int(Decimal(as_text(tx.get("rewards_earned")).split()[0]))
        if amount < 0:
            raise ValueError("negative amount")
    except (InvalidOperation, ValueError, IndexError):
        return base_finding(tx, "not_reviewed", "A nonnegative amount and whole recorded-points value are required.")

    rate, reason = rate_for_transaction(tx, green_category_is_qualifying)
    if rate is None:
        return base_finding(tx, "indeterminate", reason)
    if rate == "conditional_2pct":
        expected = whole_points(amount, 2)
        return base_finding(tx, "conditional", reason, expected=expected, conditional=True)
    expected = whole_points(amount, rate)
    return base_finding(tx, "candidate", reason + " Expected points are truncated down per transaction.", expected=expected)


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("Input must be a JSON object.")
        transactions = payload.get("transactions")
        if transactions is None:
            transactions = parse_raw_transactions(as_text(payload.get("raw_transaction_text")))
        if not isinstance(transactions, list):
            raise ValueError("transactions must be an array, or raw_transaction_text must be supplied.")
        green_signal = payload.get("green_category_is_qualifying", True)
        findings = [audit_one(tx, bool(green_signal)) for tx in transactions if isinstance(tx, dict)]
        counts = {}
        for finding in findings:
            counts[finding["verdict"]] = counts.get(finding["verdict"], 0) + 1
        result = {
            "findings": findings,
            "summary": {
                "transactions_received": len(transactions),
                "transactions_audited": len(findings),
                "verdict_counts": counts,
                "confirmed_discrepancy_count": counts.get("mismatch", 0),
            },
        }
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc), "findings": []}, ensure_ascii=False))
        sys.exit(2)


if __name__ == "__main__":
    main()
