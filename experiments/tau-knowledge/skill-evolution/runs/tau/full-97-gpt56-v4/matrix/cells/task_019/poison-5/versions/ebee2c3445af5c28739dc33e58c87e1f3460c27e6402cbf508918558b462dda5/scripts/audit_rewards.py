#!/usr/bin/env python3
"""Read a rewards-audit request from stdin and emit a deterministic JSON audit."""
import json
import re
import sys
from collections import defaultdict
from decimal import Decimal, InvalidOperation, ROUND_FLOOR

EXCLUDED_ECO_MERCHANTS = {"target", "walmart", "amazon", "thredup"}
CERTIFIED_EV_MERCHANTS = {"tesla supercharger", "chargepoint", "evgo"}


def number(value, field):
    """Parse a nonnegative amount or whole recorded-point value safely."""
    if isinstance(value, (int, float, Decimal)):
        text = str(value)
    elif isinstance(value, str):
        # Supports common tool strings such as "$12.34" or "30 points".
        match = re.search(r"[-+]?\d+(?:\.\d+)?", value.replace(",", ""))
        if not match:
            raise ValueError("%s is not numeric" % field)
        text = match.group(0)
    else:
        raise ValueError("%s is missing or not numeric" % field)
    try:
        parsed = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError("%s is not numeric" % field) from exc
    if parsed < 0:
        raise ValueError("%s must be nonnegative" % field)
    return parsed


def floor_points(amount, rate):
    return int((amount * rate).to_integral_value(rounding=ROUND_FLOOR))


def normalized(value):
    return " ".join(str(value or "").casefold().split())


def eco_rate(transaction):
    """Return (rate, basis); rate is None when eligibility is unsupported."""
    merchant = normalized(transaction.get("merchant_name"))
    if merchant in EXCLUDED_ECO_MERCHANTS:
        return Decimal("1"), "documented excluded merchant"
    if merchant in CERTIFIED_EV_MERCHANTS:
        return Decimal("5"), "documented certified EV-charging network"

    status = normalized(transaction.get("green_status"))
    if status in {"qualifying", "green", "yes", "true"}:
        return Decimal("5"), "supplied qualifying-green classification"
    if status in {"nonqualifying", "not qualifying", "standard", "no", "false"}:
        return Decimal("1"), "supplied nonqualifying classification"
    # Transaction exports that label a purchase Green are a usable system
    # classification, but unknown/missing categories are deliberately not guessed.
    if normalized(transaction.get("category")) == "green":
        return Decimal("5"), "transaction category indicates Green"
    return None, "green eligibility not established by supplied data"


def audit_one(transaction, index):
    card = str(transaction.get("credit_card_type", "")).strip()
    txid = transaction.get("transaction_id") or "row-%d" % (index + 1)
    common = {
        "transaction_id": str(txid),
        "card_type": card,
        "merchant_name": transaction.get("merchant_name"),
        "status": transaction.get("status"),
    }
    if normalized(transaction.get("status")) != "completed":
        common.update({"result": "excluded", "reason": "transaction is not COMPLETED"})
        return common
    if card not in {"Gold Rewards Card", "EcoCard"}:
        common.update({"result": "excluded", "reason": "unsupported card type"})
        return common
    try:
        amount = number(transaction.get("transaction_amount"), "transaction_amount")
        recorded_decimal = number(transaction.get("rewards_earned"), "rewards_earned")
        if recorded_decimal != recorded_decimal.to_integral_value():
            raise ValueError("rewards_earned must be a whole number of points")
        recorded = int(recorded_decimal)
    except ValueError as exc:
        common.update({"result": "excluded", "reason": str(exc)})
        return common

    if card == "Gold Rewards Card":
        rate, basis = Decimal("2.5"), "Gold Rewards Card 2.5% cash-back rate"
    else:
        rate, basis = eco_rate(transaction)
        if rate is None:
            common.update({
                "result": "unknown_eligibility", "reason": basis,
                "amount": format(amount, "f"), "recorded_points": recorded,
                "expected_points": None
            })
            return common

    expected = floor_points(amount, rate)
    delta = expected - recorded
    common.update({
        "result": "match" if delta == 0 else "mismatch",
        "amount": format(amount, "f"),
        "rate_points_per_dollar": format(rate, "f"),
        "rate_basis": basis,
        "expected_points": expected,
        "recorded_points": recorded,
        "delta_points": delta,
        "delta_cash_value": format(Decimal(delta) * Decimal("0.01"), ".2f"),
        "calculation": "floor(%s * %s)" % (format(amount, "f"), format(rate, "f")),
    })
    return common


def main():
    try:
        payload = json.load(sys.stdin)
        transactions = payload["transactions"]
        if not isinstance(transactions, list):
            raise ValueError("transactions must be a list")
    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        json.dump({"error": "invalid input: %s" % exc}, sys.stdout)
        return 2

    rows = [audit_one(tx, i) if isinstance(tx, dict) else {
        "transaction_id": "row-%d" % (i + 1), "result": "excluded",
        "reason": "transaction must be an object"
    } for i, tx in enumerate(transactions)]
    totals = defaultdict(lambda: {"audited": 0, "expected_points": 0, "recorded_points": 0, "delta_points": 0})
    for row in rows:
        if row["result"] in {"match", "mismatch"}:
            total = totals[row["card_type"]]
            total["audited"] += 1
            total["expected_points"] += row["expected_points"]
            total["recorded_points"] += row["recorded_points"]
            total["delta_points"] += row["delta_points"]
    for total in totals.values():
        total["delta_cash_value"] = format(Decimal(total["delta_points"]) * Decimal("0.01"), ".2f")

    result = {
        "audit_rows": rows,
        "totals_by_card": dict(totals),
        "mismatches": [r for r in rows if r["result"] == "mismatch"],
        "unknown_eligibility": [r for r in rows if r["result"] == "unknown_eligibility"],
        "excluded_transactions": [r for r in rows if r["result"] == "excluded"],
    }
    json.dump(result, sys.stdout, indent=2, sort_keys=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
