#!/usr/bin/env python3
"""Audit known credit-card rewards rules.

Reads one JSON object from stdin containing {"transactions": [...]} and writes one
JSON result object to stdout. This program is read-only: it never calls banking tools
and never changes account data.
"""

import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_FLOOR

SUPPORTED = {
    "Crypto-Cash Back",
    "EcoCard",
    "Business Platinum Rewards Card",
    "Silver Rewards Card",
}
ECO_STANDARD_MERCHANTS = {"target", "walmart", "amazon", "thredup"}
ECO_EV_PARTNERS = {"tesla supercharger", "chargepoint", "evgo"}


def norm(value):
    return " ".join(str(value or "").strip().lower().split())


def parse_decimal(value, field):
    if value is None or isinstance(value, bool):
        raise ValueError("missing or invalid " + field)
    text = str(value).strip().replace("$", "").replace(",", "")
    try:
        result = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError("invalid " + field) from exc
    if not result.is_finite():
        raise ValueError("invalid " + field)
    return result


def parse_points(value):
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip().lower().replace("points", "").strip()
    try:
        number = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError("invalid rewards_earned") from exc
    if not number.is_finite() or number != number.to_integral_value():
        raise ValueError("rewards_earned must be a whole number")
    return int(number)


def floor_points(amount, rate):
    return int((amount * rate).to_integral_value(rounding=ROUND_FLOOR))


def result_base(tx):
    return {
        "transaction_id": tx.get("transaction_id"),
        "outcome": None,
        "expected_points": None,
        "recorded_points": None,
        "rate_points_per_dollar": None,
        "reason": "",
        "assumptions": [],
    }


def audit_one(tx):
    out = result_base(tx)
    if not isinstance(tx, dict):
        out.update(outcome="skipped", reason="transaction must be an object")
        return out
    if not tx.get("transaction_id"):
        out.update(outcome="skipped", reason="missing transaction_id")
        return out
    card = tx.get("credit_card_type")
    if card not in SUPPORTED:
        out.update(outcome="insufficient_information", reason="unsupported or missing card type")
        return out
    if norm(tx.get("status")) not in {"completed", "posted", ""}:
        out.update(outcome="skipped", reason="transaction is not a completed posted entry")
        return out
    if tx.get("is_return_or_credit") is True:
        out.update(
            outcome="insufficient_information",
            reason="return or credit requires original-transaction rate and net-purchase review",
        )
        return out
    try:
        amount = parse_decimal(tx.get("transaction_amount"), "transaction_amount")
        recorded = parse_points(tx.get("rewards_earned"))
    except ValueError as exc:
        out.update(outcome="insufficient_information", reason=str(exc))
        return out
    out["recorded_points"] = recorded
    if amount < 0:
        out.update(outcome="insufficient_information", reason="negative amount requires return/credit review")
        return out
    if tx.get("reward_eligible") is False:
        expected = 0
        rate = Decimal("0")
        reason = "explicitly marked ineligible for rewards"
    else:
        if tx.get("reward_eligible") is None:
            out["assumptions"].append("completed purchase treated as eligible unless explicitly marked otherwise")
        category = norm(tx.get("category"))
        merchant = norm(tx.get("merchant_name"))
        if card == "Crypto-Cash Back":
            rate = Decimal("2")
            expected = floor_points(amount, rate)
            reason = "2.0% eligible-purchase rate"
        elif card == "EcoCard":
            green = category in {"green", "sustainable"}
            if merchant in ECO_STANDARD_MERCHANTS:
                rate = Decimal("1")
                reason = "EcoCard excluded merchant receives the standard rate"
            elif tx.get("is_ev_charging") is True and merchant not in ECO_EV_PARTNERS:
                rate = Decimal("1")
                reason = "non-partner EV charging receives the standard rate"
            elif green:
                rate = Decimal("5")
                reason = "posted Green/Sustainable purchase at qualifying rate"
            else:
                rate = Decimal("1")
                reason = "EcoCard standard rate"
            expected = floor_points(amount, rate)
        elif card == "Business Platinum Rewards Card":
            if category in {"travel", "software"}:
                rate = Decimal("4")
                expected = floor_points(amount, rate)
                reason = "posted enhanced Travel/Software category"
            elif category == "media" and tx.get("qualifies_media_advertising") is None:
                out.update(
                    outcome="insufficient_information",
                    reason="Media entry needs evidence that it is advertising before applying the enhanced rate",
                )
                return out
            elif category == "media" and tx.get("qualifies_media_advertising") is True:
                rate = Decimal("4")
                expected = floor_points(amount, rate)
                reason = "verified Media advertising purchase"
            else:
                rate = Decimal("1.5")
                expected = floor_points(amount, rate)
                reason = "Business Platinum eligible standard rate"
        else:  # Silver Rewards Card
            if category in {"travel", "software"}:
                rate = Decimal("4")
                expected = floor_points(amount, rate)
                reason = "posted enhanced Travel/Software category"
            else:
                out.update(
                    outcome="insufficient_information",
                    reason="ordinary Silver Rewards Card rate is not established by the supplied terms",
                )
                return out
    out["expected_points"] = expected
    out["rate_points_per_dollar"] = format(rate, "f")
    out["reason"] = reason + "; fractional points truncated down"
    if recorded is None:
        out["outcome"] = "insufficient_information"
        out["reason"] = "missing recorded rewards_earned; " + out["reason"]
    elif recorded == expected:
        out["outcome"] = "match"
    else:
        out["outcome"] = "mismatch"
    return out


def main():
    try:
        payload = json.load(sys.stdin)
        transactions = payload.get("transactions") if isinstance(payload, dict) else None
        if not isinstance(transactions, list):
            raise ValueError("input must be an object with a transactions array")
        results = [audit_one(tx) for tx in transactions]
        summary = {"match": 0, "mismatch": 0, "insufficient_information": 0, "skipped": 0}
        for item in results:
            summary[item["outcome"]] += 1
        json.dump({"summary": summary, "results": results}, sys.stdout, separators=(",", ":"))
        sys.stdout.write("\n")
    except (ValueError, json.JSONDecodeError) as exc:
        json.dump({"error": str(exc)}, sys.stdout, separators=(",", ":"))
        sys.stdout.write("\n")
        sys.exit(2)


if __name__ == "__main__":
    main()
