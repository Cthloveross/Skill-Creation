#!/usr/bin/env python3
"""Read reward transactions as JSON from stdin and emit a deterministic audit JSON.

See SKILL.md for the input and output schema.  This module uses Decimal so currency
and truncation are not affected by binary floating-point behavior.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_FLOOR

BSILVER_EXCLUSIONS = (
    "concur", "sap concur", "expensify", "navan", "apple", "microsoft",
    "dell", "xbox game pass", "playstation plus", "nintendo switch online",
    "coursera", "udemy", "linkedin learning", "skillshare", "pluralsight",
)
ECO_STANDARD_EXCLUSIONS = ("target", "walmart", "amazon", "thredup")
ECO_CERTIFIED_EV = ("tesla supercharger", "chargepoint", "evgo")


def text(value):
    return str(value or "").strip()


def normalized(value):
    return " ".join(text(value).casefold().split())


def merchant_matches(merchant, names):
    """Match an exact documented merchant or a natural merchant-name extension."""
    merchant = normalized(merchant)
    for name in names:
        if merchant == name:
            return True
        if merchant.startswith(name) and len(merchant) > len(name):
            next_char = merchant[len(name)]
            if next_char in " -.,:/":
                return True
    return False


def parse_amount(value):
    cleaned = text(value).replace("$", "").replace(",", "")
    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError("transaction_amount is not a valid decimal") from exc


def parse_points(value):
    if isinstance(value, bool):
        raise ValueError("rewards_earned must be an integer")
    try:
        decimal_value = Decimal(text(value))
    except InvalidOperation as exc:
        raise ValueError("rewards_earned is not numeric") from exc
    if decimal_value != decimal_value.to_integral_value():
        raise ValueError("rewards_earned must be a whole number")
    return int(decimal_value)


def floored_points(amount, points_per_dollar):
    return int((amount * Decimal(str(points_per_dollar))).to_integral_value(rounding=ROUND_FLOOR))


def base_result(tx):
    return {
        "transaction_id": tx.get("transaction_id"),
        "credit_card_type": tx.get("credit_card_type"),
        "merchant_name": tx.get("merchant_name"),
    }


def unsupported(tx, reason):
    result = base_result(tx)
    result.update({"disposition": "unsupported", "reason": reason})
    return result


def indeterminate(tx, reason, possible=None):
    result = base_result(tx)
    result.update({"disposition": "indeterminate", "reason": reason})
    if possible is not None:
        result["possible_expected_points"] = possible
    return result


def determinable(tx, amount, recorded, rate, basis):
    expected = floored_points(amount, rate)
    difference = expected - recorded
    finding = "correct" if difference == 0 else ("under_awarded" if difference > 0 else "over_awarded")
    result = base_result(tx)
    result.update({
        "disposition": "confirmed",
        "rate": str(rate),
        "rate_unit": "points_per_dollar",
        "basis": basis,
        "expected_points": expected,
        "recorded_points": recorded,
        "difference_points": difference,
        "finding": finding,
    })
    return result


def audit_one(tx):
    if not isinstance(tx, dict):
        return {"transaction_id": None, "disposition": "unsupported", "reason": "transaction must be an object"}
    required = ("transaction_id", "credit_card_type", "merchant_name", "transaction_amount", "category", "status", "rewards_earned")
    missing = [key for key in required if key not in tx or tx[key] is None or text(tx[key]) == ""]
    if missing:
        return unsupported(tx, "missing required field(s): " + ", ".join(missing))
    if normalized(tx["status"]) != "completed":
        return unsupported(tx, "only completed positive purchase records can be recalculated")
    try:
        amount = parse_amount(tx["transaction_amount"])
        recorded = parse_points(tx["rewards_earned"])
    except ValueError as exc:
        return unsupported(tx, str(exc))
    if amount <= 0:
        return unsupported(tx, "zero, negative, refund, or reversal amounts require net-purchase review")

    card = normalized(tx["credit_card_type"])
    category = normalized(tx["category"])
    merchant = tx["merchant_name"]

    if card == "diamond elite card":
        return determinable(tx, amount, recorded, Decimal("5"), "Diamond Elite 5.0% cash back")
    if card == "business platinum rewards card":
        qualifying = category in {"travel", "software", "media", "media advertising", "advertising"}
        rate = Decimal("4") if qualifying else Decimal("1.5")
        basis = "Business Platinum qualifying category" if qualifying else "Business Platinum standard category"
        return determinable(tx, amount, recorded, rate, basis)
    if card == "business silver rewards card":
        excluded = merchant_matches(merchant, BSILVER_EXCLUSIONS)
        qualifying = category in {"travel", "software"}
        if excluded:
            return determinable(tx, amount, recorded, Decimal("1"), "Business Silver documented merchant exclusion")
        rate = Decimal("10") if qualifying else Decimal("1")
        basis = "Business Silver qualifying category" if qualifying else "Business Silver standard category"
        return determinable(tx, amount, recorded, rate, basis)
    if card == "ecocard":
        if merchant_matches(merchant, ECO_STANDARD_EXCLUSIONS):
            return determinable(tx, amount, recorded, Decimal("1"), "EcoCard documented merchant exclusion")
        if merchant_matches(merchant, ECO_CERTIFIED_EV):
            return determinable(tx, amount, recorded, Decimal("5"), "EcoCard documented certified EV network")
        if category == "green":
            standard = floored_points(amount, Decimal("1"))
            high = floored_points(amount, Decimal("5"))
            return indeterminate(
                tx,
                "green eligibility is not established by merchant name or category; require directory, receipt/statement indicator, or support confirmation",
                {"standard_rate": standard, "qualifying_green_rate": high},
            )
        return determinable(tx, amount, recorded, Decimal("1"), "EcoCard non-Green transaction category")
    return unsupported(tx, "card type is outside the documented rules in this Skill")


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": "invalid JSON input: " + str(exc)}))
        return 2
    if not isinstance(payload, dict) or not isinstance(payload.get("transactions"), list):
        print(json.dumps({"error": "input must be an object containing a transactions array"}))
        return 2

    results = [audit_one(tx) for tx in payload["transactions"]]
    summary = {
        "transactions_received": len(results),
        "confirmed": sum(r.get("disposition") == "confirmed" for r in results),
        "indeterminate": sum(r.get("disposition") == "indeterminate" for r in results),
        "unsupported": sum(r.get("disposition") == "unsupported" for r in results),
        "correct": sum(r.get("finding") == "correct" for r in results),
        "under_awarded": sum(r.get("finding") == "under_awarded" for r in results),
        "over_awarded": sum(r.get("finding") == "over_awarded" for r in results),
    }
    print(json.dumps({"results": results, "summary": summary}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
