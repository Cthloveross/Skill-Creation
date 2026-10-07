#!/usr/bin/env python3
"""Read transaction rewards JSON from stdin and emit a documented-rules audit."""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_FLOOR

STANDARD_ECO_MERCHANTS = {"target", "walmart", "amazon", "thredup"}
GREEN_EV_MERCHANTS = {"tesla supercharger", "chargepoint", "evgo"}


def floor_points(amount: Decimal, multiplier: Decimal) -> int:
    return int((amount * multiplier).to_integral_value(rounding=ROUND_FLOOR))


def money(points):
    return format((Decimal(points) / Decimal("100")).quantize(Decimal("0.01")), ".2f")


def normalized(value):
    return " ".join(str(value or "").strip().casefold().split())


def value_error(index, message):
    return {"index": index, "finding": "input_error", "message": message}


def base_item(tx, amount, actual):
    return {
        "transaction_id": tx["transaction_id"],
        "card_type": tx["card_type"],
        "merchant_name": tx.get("merchant_name", ""),
        "amount": format(amount, ".2f"),
        "recorded_points": actual,
        "recorded_value_dollars": money(actual),
    }


def expected_item(item, expected, rule):
    item.update({
        "expected_points": expected,
        "expected_value_dollars": money(expected),
        "difference_points": expected - item["recorded_points"],
        "difference_value_dollars": money(expected - item["recorded_points"]),
        "rule": rule,
    })
    item["finding"] = (
        "match" if expected == item["recorded_points"] else "deterministic_discrepancy"
    )
    return item


def audit_transaction(tx, index):
    required = ("transaction_id", "card_type", "transaction_amount", "rewards_earned", "status")
    missing = [key for key in required if key not in tx or tx[key] in (None, "")]
    if missing:
        return value_error(index, "missing required field(s): " + ", ".join(missing))
    try:
        amount = Decimal(str(tx["transaction_amount"]).replace(",", "").replace("$", ""))
    except (InvalidOperation, ValueError):
        return value_error(index, "transaction_amount must be a decimal")
    if not amount.is_finite() or amount < 0:
        return value_error(index, "transaction_amount must be a nonnegative finite decimal")
    actual = tx["rewards_earned"]
    if isinstance(actual, bool) or not isinstance(actual, int) or actual < 0:
        return value_error(index, "rewards_earned must be a nonnegative integer")

    item = base_item(tx, amount, actual)
    if str(tx["status"]).upper() != "COMPLETED":
        item.update({
            "finding": "unsupported_terms",
            "rule": "Only completed purchases can be compared by this audit. Refunds and other nonstandard statuses require the original transaction and applicable terms.",
        })
        return item

    card = normalized(tx["card_type"])
    merchant = normalized(tx.get("merchant_name"))
    category = normalized(tx.get("category"))

    if card == "crypto-cash back":
        expected = floor_points(amount, Decimal("2"))
        if tx.get("eligible") is True:
            return expected_item(item, expected, "Eligible Crypto-Cash Back purchases earn 2.0%; points are truncated down.")
        item.update({
            "finding": "conditional",
            "conditional_expected_points": expected,
            "conditional_expected_value_dollars": money(expected),
            "rule": "If this was an eligible Crypto-Cash Back purchase, it earns 2.0% with truncation. Eligibility is not established by this record.",
        })
        return item

    if card == "ecocard":
        if merchant in STANDARD_ECO_MERCHANTS:
            return expected_item(item, floor_points(amount, Decimal("1")), "This EcoCard merchant is excluded from the higher rate and earns the 1-point-per-dollar standard rate, truncated down.")
        if merchant in GREEN_EV_MERCHANTS:
            return expected_item(item, floor_points(amount, Decimal("5")), "This is a documented certified EV charging network and earns 5 EcoCard points per dollar, truncated down.")
        if tx.get("green_qualified") is True:
            return expected_item(item, floor_points(amount, Decimal("5")), "Authoritatively confirmed qualifying green EcoCard purchase: 5 points per dollar, truncated down.")
        if tx.get("green_qualified") is False or (category and category != "green"):
            return expected_item(item, floor_points(amount, Decimal("1")), "Other/non-qualifying EcoCard purchase: 1 point per dollar, truncated down.")
        item.update({
            "finding": "conditional",
            "green_rate_expected_points": floor_points(amount, Decimal("5")),
            "standard_rate_expected_points": floor_points(amount, Decimal("1")),
            "rule": "EcoCard earns 5 points per dollar only when green qualification is established; otherwise other purchases earn 1 point per dollar. This record does not establish qualification.",
        })
        return item

    item.update({
        "finding": "unsupported_terms",
        "rule": "The stored points are worth $0.01 each, but this audit has no documented earning schedule for this card type.",
    })
    return item


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": "invalid_json", "message": str(exc)}))
        return
    transactions = payload.get("transactions") if isinstance(payload, dict) else None
    if not isinstance(transactions, list):
        print(json.dumps({"error": "invalid_input", "message": "transactions must be a JSON array"}))
        return

    items = []
    seen_ids = set()
    for index, tx in enumerate(transactions):
        if not isinstance(tx, dict):
            items.append(value_error(index, "transaction must be an object"))
            continue
        item = audit_transaction(tx, index)
        txid = item.get("transaction_id")
        if txid and txid in seen_ids and item["finding"] != "input_error":
            item = value_error(index, "duplicate transaction_id: " + str(txid))
        elif txid:
            seen_ids.add(txid)
        items.append(item)
    counts = {}
    for item in items:
        finding = item["finding"]
        counts[finding] = counts.get(finding, 0) + 1
    print(json.dumps({"items": items, "summary": counts}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
