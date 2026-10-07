#!/usr/bin/env python3
"""Audit documented credit-card rewards. Reads one JSON object from stdin, writes one JSON object."""
import json
import re
import sys
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_HALF_UP

BONUS_BUSINESS = {"travel", "software", "media"}
SILVER_BONUS = {"travel", "software"}
ECO_HIGH = {"green", "sustainable"}
ECO_EXCLUDED = {"target", "walmart", "amazon", "thredup"}
ECO_EV_PARTNERS = {"tesla supercharger", "chargepoint", "evgo"}


def norm(value):
    return " ".join(str(value or "").strip().lower().split())


def money(value):
    text = str(value).replace("$", "").replace(",", "").strip()
    result = Decimal(text)
    if result < 0:
        raise ValueError("transaction_amount must be nonnegative")
    return result


def points(value):
    if isinstance(value, int):
        return value
    match = re.search(r"-?\d+", str(value or ""))
    if not match:
        raise ValueError("rewards_earned must contain a whole point value")
    return int(match.group())


def whole(value, rounding):
    mode = ROUND_HALF_UP if rounding == "nearest" else ROUND_DOWN
    return int(value.quantize(Decimal("1"), rounding=mode))


def expected_rate(row):
    """Return (points_per_dollar, rule, assessment) or (None, rule, status)."""
    if row.get("is_cash_equivalent") or row.get("is_balance_transfer") or row.get("is_fee"):
        return Decimal("0"), "Excluded transaction type earns zero rewards", "assessed"
    category = norm(row.get("category"))
    merchant = norm(row.get("merchant_name"))
    card = norm(row.get("credit_card_type"))

    if card == "crypto-cash back":
        return Decimal("2"), "Crypto-Cash Back: 2 points per eligible dollar", "assessed"
    if card == "business platinum rewards card":
        rate = Decimal("4") if category in BONUS_BUSINESS else Decimal("1.5")
        label = "4" if rate == 4 else "1.5"
        return rate, "Business Platinum Rewards Card: %s points per dollar" % label, "assessed"
    if card == "silver rewards card":
        if category in SILVER_BONUS:
            return Decimal("4"), "Silver Rewards Card: 4 points per posted Travel/Software dollar", "assessed"
        return None, "Silver Rewards Card non-bonus base rate is not established by supplied terms", "not_assessed"
    if card == "ecocard":
        if merchant in ECO_EXCLUDED:
            return Decimal("1"), "EcoCard named merchant exclusion: 1 point per dollar", "assessed"
        if category in ECO_HIGH:
            return Decimal("5"), "EcoCard qualifying Green/Sustainable purchase: 5 points per dollar", "assessed"
        if "charging" in category and merchant not in ECO_EV_PARTNERS:
            return None, "EcoCard EV charging eligibility needs certified-network evidence", "needs_review"
        return Decimal("1"), "EcoCard other purchase: 1 point per dollar", "assessed"
    return None, "Unsupported card type or no supplied rate rule", "not_assessed"


def audit(row, rounding):
    out = {"transaction_id": row.get("transaction_id"), "card_type": row.get("credit_card_type")}
    if not row.get("transaction_id"):
        out.update(status="not_assessed", reason="Missing transaction_id")
        return out
    if norm(row.get("status")) != "completed":
        out.update(status="not_assessed", reason="Only completed transactions are audited")
        return out
    try:
        amount = money(row.get("transaction_amount"))
        actual = points(row.get("rewards_earned"))
    except (InvalidOperation, ValueError) as exc:
        out.update(status="not_assessed", reason=str(exc))
        return out
    rate, rule, state = expected_rate(row)
    out.update(amount=str(amount), actual_points=actual, rule=rule)
    if rate is None:
        out["status"] = state
        return out
    expected = whole(amount * rate, rounding)
    out.update(expected_points=expected, points_difference=expected - actual)
    out["status"] = "match" if expected == actual else "discrepancy"
    return out


def main():
    try:
        payload = json.load(sys.stdin)
        rows = payload.get("transactions")
        if not isinstance(rows, list):
            raise ValueError("transactions must be an array")
        rounding = payload.get("rounding", "truncate")
        if rounding not in {"truncate", "nearest"}:
            raise ValueError("rounding must be 'truncate' or 'nearest'")
        results = [audit(row, rounding) if isinstance(row, dict) else
                   {"status": "not_assessed", "reason": "Transaction row must be an object"}
                   for row in rows]
        print(json.dumps({
            "rounding": rounding,
            "transactions": results,
            "discrepancies": [r for r in results if r.get("status") == "discrepancy"],
            "needs_review": [r for r in results if r.get("status") == "needs_review"],
            "not_assessed": [r for r in results if r.get("status") == "not_assessed"],
        }, separators=(",", ":")))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
