#!/usr/bin/env python3
"""Deterministic rewards audit. Reads one JSON object from stdin and writes JSON."""

import json
import re
import sys
from decimal import Decimal, InvalidOperation, ROUND_DOWN

GOLD = "gold rewards card"
ECO = "ecocard"
EXCLUDED_ECO_MERCHANTS = {"target", "walmart", "amazon", "thredup"}
QUALIFYING_CHARGING_NETWORKS = {"tesla supercharger", "chargepoint", "evgo"}


def normalize(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def decimal_value(value, field):
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{field} is missing or is not numeric")
    text = str(value).strip().replace("$", "").replace(",", "")
    text = re.sub(r"\s*(points?|pts?)$", "", text, flags=re.I).strip()
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"{field} is not a valid decimal") from exc


def bool_value(value):
    """Return bool for actual booleans or conventional JSON-like boolean strings."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lower = value.strip().lower()
        if lower == "true":
            return True
        if lower == "false":
            return False
    return None


def floor_points(amount, rate):
    return int((amount * Decimal(rate)).to_integral_value(rounding=ROUND_DOWN))


def eco_rate(transaction):
    """Return (rate, basis, needs_review). Explicit EV rule outranks category labels."""
    merchant = normalize(transaction.get("merchant_name"))
    category = normalize(transaction.get("category"))
    charging = bool_value(transaction.get("is_ev_charging"))
    explicit_eligible = bool_value(transaction.get("green_eligible"))

    if charging is True:
        if merchant in QUALIFYING_CHARGING_NETWORKS:
            return Decimal("5"), "confirmed qualifying EV-charging network", False
        return Decimal("1"), "confirmed EV charging at non-qualifying network", False
    if merchant in EXCLUDED_ECO_MERCHANTS:
        return Decimal("1"), "named EcoCard merchant exclusion", False
    if explicit_eligible is True:
        return Decimal("5"), "confirmed green eligibility", False
    if explicit_eligible is False:
        return Decimal("1"), "confirmed non-green eligibility", False
    if category in {"green", "sustainable"}:
        return Decimal("5"), "Green/Sustainable transaction category", False
    return Decimal("1"), "green eligibility not established; standard rate used provisionally", True


def make_skip(transaction, index, reason):
    return {
        "index": index,
        "transaction_id": transaction.get("transaction_id"),
        "merchant_name": transaction.get("merchant_name"),
        "reason": reason,
    }


def audit_one(transaction, index):
    if not isinstance(transaction, dict):
        return None, make_skip({}, index, "transaction is not an object")

    card = normalize(transaction.get("credit_card_type"))
    status = normalize(transaction.get("status"))
    if card not in {GOLD, ECO}:
        return None, make_skip(transaction, index, "unsupported card type")
    if status != "completed":
        return None, make_skip(transaction, index, "not a completed purchase")

    try:
        amount = decimal_value(transaction.get("transaction_amount"), "transaction_amount")
        actual_decimal = decimal_value(transaction.get("rewards_earned"), "rewards_earned")
    except ValueError as exc:
        return None, make_skip(transaction, index, str(exc))

    if amount <= 0:
        return None, make_skip(transaction, index, "non-positive amount; refund/reversal requires original-purchase review")
    if actual_decimal != actual_decimal.to_integral_value():
        return None, make_skip(transaction, index, "displayed rewards are not whole points")

    needs_review = False
    if card == GOLD:
        rate = Decimal("2.5")
        basis = "Gold Rewards Card 2.5% cash back (2.5 stored points per dollar)"
    else:
        rate, basis, needs_review = eco_rate(transaction)

    expected = floor_points(amount, rate)
    actual = int(actual_decimal)
    difference = expected - actual
    if difference > 0:
        outcome = "under_awarded"
    elif difference < 0:
        outcome = "over_awarded"
    else:
        outcome = "matches_expected"

    audit = {
        "index": index,
        "transaction_id": transaction.get("transaction_id"),
        "transaction_date": transaction.get("transaction_date"),
        "card_type": transaction.get("credit_card_type"),
        "merchant_name": transaction.get("merchant_name"),
        "amount": format(amount, "f"),
        "actual_points": actual,
        "expected_points": expected,
        "rate_points_per_dollar": format(rate, "f"),
        "classification_basis": basis,
        "needs_eligibility_review": needs_review,
        "point_difference_expected_minus_actual": difference,
        "redemption_value_difference_dollars": format(Decimal(difference) / Decimal("100"), ".2f"),
        "outcome": outcome,
    }
    return audit, None


def main():
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict) or not isinstance(data.get("transactions"), list):
            raise ValueError("input must be an object containing a transactions array")

        audits, skipped = [], []
        for index, transaction in enumerate(data["transactions"]):
            audit, skip = audit_one(transaction, index)
            if audit is not None:
                audits.append(audit)
            if skip is not None:
                skipped.append(skip)

        discrepancies = [a for a in audits if a["outcome"] != "matches_expected"]
        needs_review = [a for a in audits if a["needs_eligibility_review"]]
        total_difference = sum(a["point_difference_expected_minus_actual"] for a in discrepancies)
        output = {
            "audits": audits,
            "discrepancies": discrepancies,
            "needs_review": needs_review,
            "skipped": skipped,
            "summary": {
                "transactions_received": len(data["transactions"]),
                "transactions_audited": len(audits),
                "confirmed_discrepancy_count": len(discrepancies),
                "needs_eligibility_review_count": len(needs_review),
                "skipped_count": len(skipped),
                "total_point_difference_expected_minus_actual": total_difference,
                "total_redemption_value_difference_dollars": format(Decimal(total_difference) / Decimal("100"), ".2f"),
            },
        }
        print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
