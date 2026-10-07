#!/usr/bin/env python3
"""Audit posted transaction rewards.

Reads one JSON object from stdin and emits a JSON report to stdout.  See
SKILL.md for the public schema.  Uses only the Python standard library.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_FLOOR

ECO_EXCLUDED_MERCHANTS = {"target", "walmart", "amazon", "thredup"}
ECO_EV_PARTNERS = {"tesla supercharger", "chargepoint", "evgo"}


def decimal_amount(value):
    if isinstance(value, bool):
        raise ValueError("amount must not be boolean")
    text = str(value).strip().replace("$", "").replace(",", "")
    try:
        amount = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError("invalid transaction_amount") from exc
    if amount < 0:
        raise ValueError("transaction_amount must be nonnegative")
    return amount


def integer_points(value):
    if isinstance(value, bool):
        raise ValueError("rewards_earned must be an integer")
    try:
        points = Decimal(str(value).strip().replace("points", "").strip())
    except InvalidOperation as exc:
        raise ValueError("invalid rewards_earned") from exc
    if points != points.to_integral_value() or points < 0:
        raise ValueError("rewards_earned must be a nonnegative whole number")
    return int(points)


def normalized(value):
    return str(value or "").strip().casefold()


def completed(status):
    return normalized(status) in {"completed", "posted"}


def eco_rate(transaction, strict):
    """Return (rate, basis, provisional, reason), or rate None for manual review."""
    merchant = normalized(transaction.get("merchant_name"))
    category = normalized(transaction.get("category"))
    explicit = transaction.get("green_eligible")
    if merchant in ECO_EXCLUDED_MERCHANTS:
        return Decimal("1"), "EcoCard named merchant exclusion", False, None
    if "charging" in merchant and merchant not in ECO_EV_PARTNERS:
        return Decimal("1"), "EcoCard nonpartner EV charging", False, None
    if merchant in ECO_EV_PARTNERS:
        return Decimal("5"), "EcoCard certified EV charging partner", False, None
    if explicit is True:
        return Decimal("5"), "explicit qualifying-green eligibility", False, None
    if explicit is False:
        return Decimal("1"), "explicit non-green eligibility", False, None
    if category == "green":
        if strict:
            return None, None, False, "green category lacks explicit merchant eligibility"
        return Decimal("5"), "Green category (provisional merchant qualification)", True, None
    return Decimal("1"), "EcoCard non-green category", False, None


def determine_rate(transaction, strict_eco):
    card = normalized(transaction.get("credit_card_type"))
    category = normalized(transaction.get("category"))
    if card == "silver rewards card":
        rate = Decimal("4") if category in {"travel", "software"} else Decimal("1")
        return rate, "Silver enhanced category" if rate == 4 else "Silver standard category", False, None
    if card == "business platinum rewards card":
        enhanced = {"travel", "software", "media", "media advertising"}
        rate = Decimal("4") if category in enhanced else Decimal("1.5")
        return rate, "Business Platinum enhanced category" if rate == 4 else "Business Platinum standard category", False, None
    if card == "crypto-cash back":
        return Decimal("2"), "Crypto-Cash Back eligible-purchase rate", False, None
    if card == "ecocard":
        return eco_rate(transaction, strict_eco)
    return None, None, False, "unsupported card type"


def public_transaction(transaction):
    return {
        "transaction_id": transaction.get("transaction_id"),
        "merchant_name": transaction.get("merchant_name"),
        "credit_card_type": transaction.get("credit_card_type"),
        "category": transaction.get("category"),
        "status": transaction.get("status"),
    }


def audit_transaction(transaction, strict_eco):
    required = {"transaction_id", "credit_card_type", "transaction_amount", "category", "status", "rewards_earned"}
    missing = sorted(key for key in required if key not in transaction or transaction[key] in (None, ""))
    base = public_transaction(transaction)
    if missing:
        base["reason"] = "missing required fields: " + ", ".join(missing)
        return "skipped", base
    if not completed(transaction["status"]):
        base["reason"] = "transaction is not a completed/posted purchase"
        return "skipped", base
    try:
        amount = decimal_amount(transaction["transaction_amount"])
        recorded = integer_points(transaction["rewards_earned"])
    except ValueError as exc:
        base["reason"] = str(exc)
        return "skipped", base
    rate, basis, provisional, reason = determine_rate(transaction, strict_eco)
    if rate is None:
        base["reason"] = reason
        return "manual_review", base
    expected = int((amount * rate).to_integral_value(rounding=ROUND_FLOOR))
    base.update({
        "expected_points": expected,
        "recorded_points": recorded,
        "difference_points": expected - recorded,
        "rate_points_per_dollar": str(rate),
        "basis": basis,
        "provisional_eligibility": provisional,
    })
    return ("matched" if expected == recorded else "discrepancies"), base


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict) or not isinstance(payload.get("transactions"), list):
            raise ValueError("input must be an object with a transactions array")
        strict = bool(payload.get("strict_eco_eligibility", False))
        report = {"matched": [], "discrepancies": [], "manual_review": [], "skipped": []}
        for transaction in payload["transactions"]:
            if not isinstance(transaction, dict):
                report["skipped"].append({"reason": "transaction must be an object"})
                continue
            bucket, result = audit_transaction(transaction, strict)
            report[bucket].append(result)
        bonus = payload.get("eco_account_bonus_eligible")
        if bonus is True:
            report["eco_account_bonus"] = "Linked-account eligibility was supplied as true; the conditional 2% EcoCard bonus remains outside this standard-rate calculation."
        elif bonus is False:
            report["eco_account_bonus"] = "Linked-account eligibility was supplied as false; no conditional EcoCard bonus is expected."
        else:
            report["eco_account_bonus"] = "Linked Green Account/good-standing status is unknown; the conditional 2% EcoCard bonus cannot be audited."
        report["summary"] = {key: len(report[key]) for key in ("matched", "discrepancies", "manual_review", "skipped")}
        json.dump(report, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    except (ValueError, json.JSONDecodeError) as exc:
        json.dump({"error": str(exc)}, sys.stdout)
        sys.stdout.write("\n")
        sys.exit(2)


if __name__ == "__main__":
    main()
