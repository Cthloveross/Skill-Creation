#!/usr/bin/env python3
"""Deterministic transaction-level rewards audit. Reads JSON stdin and writes JSON stdout."""

import json
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_FLOOR

BONUS_CATEGORIES = {"travel", "software", "media"}
SILVER_BONUS_CATEGORIES = {"travel", "software"}
ECO_STANDARD_MERCHANTS = {"target", "walmart", "amazon", "thredup"}
ECO_CERTIFIED_EV = {"tesla supercharger", "chargepoint", "evgo"}


def text(value):
    return str(value or "").strip()


def norm(value):
    return text(value).casefold()


def parse_money(value):
    raw = text(value).replace("$", "").replace(",", "")
    amount = Decimal(raw)
    if not amount.is_finite():
        raise ValueError("transaction_amount must be finite")
    return amount


def parse_points(value):
    raw = text(value).casefold().replace("points", "").strip()
    points = Decimal(raw)
    if points != points.to_integral_value() or points < 0:
        raise ValueError("rewards_earned must be a nonnegative whole-point value")
    return int(points)


def parse_date(value):
    raw = text(value)
    for pattern in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(raw, pattern).date()
        except ValueError:
            pass
    raise ValueError("transaction_date must be YYYY-MM-DD or MM/DD/YYYY")


def decimal_rate(value):
    try:
        rate = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("applicable_points_per_dollar must be numeric")
    if not rate.is_finite() or rate < 0:
        raise ValueError("applicable_points_per_dollar must be nonnegative and finite")
    return rate


def rate_string(rate):
    return format(rate.normalize(), "f") if rate != 0 else "0"


def inferred_rate(tx):
    """Return (rate, reason), with None rate for intentionally unsupported cases."""
    override = tx.get("applicable_points_per_dollar")
    if override is not None:
        return decimal_rate(override), "verified applicable rate override"

    card = norm(tx.get("credit_card_type"))
    category = norm(tx.get("category"))
    merchant = norm(tx.get("merchant_name"))

    if card == "business platinum rewards card":
        return (Decimal("4") if category in BONUS_CATEGORIES else Decimal("1.5"),
                "Business Platinum documented category rate")
    if card == "silver rewards card":
        if category in SILVER_BONUS_CATEGORIES:
            return Decimal("4"), "Silver documented travel/software rate"
        return None, "Silver standard rate outside travel/software is not supplied"
    if card == "crypto-cash back":
        return Decimal("2"), "Crypto-Cash Back eligible-purchase rate"
    if card == "ecocard":
        if merchant in ECO_STANDARD_MERCHANTS:
            return Decimal("1"), "EcoCard named standard-rate merchant exception"
        if merchant in ECO_CERTIFIED_EV:
            return Decimal("5"), "EcoCard certified EV charging network"
        eligibility = norm(tx.get("green_eligibility") or "unknown")
        if eligibility == "eligible":
            return Decimal("5"), "verified qualifying EcoCard green purchase"
        if eligibility == "ineligible":
            return Decimal("1"), "verified non-qualifying EcoCard purchase"
        if category in {"green", "sustainable"}:
            return None, "EcoCard green qualification requires eligibility evidence"
        return Decimal("1"), "EcoCard standard purchase rate"
    return None, "card type is not supported by supplied policy"


def in_period(date_value, period):
    if not period:
        return True
    start = parse_date(period["start"])
    end = parse_date(period["end"])
    if start > end:
        raise ValueError("period start must not be after period end")
    return start <= date_value <= end


def audit_one(tx, statuses, period):
    required = ["transaction_id", "credit_card_type", "transaction_amount", "transaction_date"]
    missing = [key for key in required if not text(tx.get(key))]
    if missing:
        raise ValueError("transaction missing required fields: " + ", ".join(missing))

    date_value = parse_date(tx["transaction_date"])
    base = {
        "transaction_id": text(tx["transaction_id"]),
        "card_type": text(tx["credit_card_type"]),
        "merchant_name": text(tx.get("merchant_name")),
        "transaction_date": date_value.isoformat(),
        "category": text(tx.get("category")),
        "recorded_points": None,
        "expected_points": None,
        "difference_points": None,
        "rate_points_per_dollar": None,
    }

    status = norm(tx.get("status"))
    if statuses and status not in statuses:
        base.update(audit_status="out_of_scope", reason="transaction status is outside include_statuses")
        return base
    if not in_period(date_value, period):
        base.update(audit_status="out_of_scope", reason="transaction date is outside requested period")
        return base

    amount = parse_money(tx["transaction_amount"])
    if amount <= 0:
        base.update(audit_status="insufficient_information", reason="return, credit, or nonpositive amount needs original-purchase linkage")
        return base
    if tx.get("is_cash_equivalent") or tx.get("is_balance_transfer") or tx.get("is_fee") or tx.get("is_eligible_purchase") is False:
        base.update(audit_status="excluded", reason="record is marked as non-earning or ineligible")
        return base

    if tx.get("rewards_earned") is None:
        base.update(audit_status="insufficient_information", reason="recorded rewards are unavailable")
        return base
    recorded = parse_points(tx["rewards_earned"])
    base["recorded_points"] = recorded
    rate, reason = inferred_rate(tx)
    if rate is None:
        base.update(audit_status="insufficient_information", reason=reason)
        return base

    expected = int((amount * rate).to_integral_value(rounding=ROUND_FLOOR))
    base.update(
        expected_points=expected,
        difference_points=expected - recorded,
        rate_points_per_dollar=rate_string(rate),
        audit_status="match" if expected == recorded else "mismatch",
        reason=reason,
    )
    return base


def main(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("transactions"), list):
        raise ValueError("input must be an object containing a transactions array")
    statuses = payload.get("include_statuses", ["COMPLETED"])
    if not isinstance(statuses, list):
        raise ValueError("include_statuses must be an array")
    statuses = {norm(item) for item in statuses}
    period = payload.get("period")
    if period is not None and (not isinstance(period, dict) or "start" not in period or "end" not in period):
        raise ValueError("period must contain start and end")
    if period:
        # Validate even when no transaction is in the range.
        in_period(parse_date(period["start"]), period)

    results = [audit_one(tx, statuses, period) for tx in payload["transactions"]]
    summary = {}
    for result in results:
        key = result["audit_status"]
        summary[key] = summary.get(key, 0) + 1
    underpaid = [r["transaction_id"] for r in results if r["audit_status"] == "mismatch" and r["difference_points"] > 0]
    overpaid = [r["transaction_id"] for r in results if r["audit_status"] == "mismatch" and r["difference_points"] < 0]
    return {
        "results": results,
        "summary": summary,
        "potential_underpayment_transaction_ids": underpaid,
        "potential_overpayment_transaction_ids": overpaid,
        "calculation_policy": "Expected points are floored independently for each transaction.",
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), separators=(",", ":"), sort_keys=True))
    except (ValueError, KeyError, TypeError, InvalidOperation) as exc:
        print(json.dumps({"error": str(exc)}, separators=(",", ":")))
