#!/usr/bin/env python3
"""Analyze Gold Rewards Card and EcoCard rewards.

Reads one JSON object from stdin and writes one JSON object to stdout.
See SKILL.md for the input and output schema.
"""
import json
import re
import sys
from decimal import Decimal, InvalidOperation, ROUND_FLOOR

GOLD = "Gold Rewards Card"
ECO = "EcoCard"
EXCLUDED_ECO_MERCHANTS = {"target", "walmart", "amazon"}
CERTIFIED_EV_NETWORKS = {"tesla supercharger", "chargepoint", "evgo"}


def parse_decimal(value, field):
    """Parse a nonnegative money/number value without binary float rounding."""
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{field} must be a number or numeric string")
    text = str(value).strip().replace("$", "").replace(",", "")
    try:
        number = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"{field} is not numeric") from exc
    if not number.is_finite() or number < 0:
        raise ValueError(f"{field} must be a finite nonnegative value")
    return number


def parse_points(value):
    """Accept an integer or a string such as '123 points'."""
    if isinstance(value, bool) or value is None:
        raise ValueError("rewards_earned is required")
    if isinstance(value, int):
        if value < 0:
            raise ValueError("rewards_earned cannot be negative")
        return value
    match = re.fullmatch(r"\s*(\d+)\s*(?:points?)?\s*", str(value), re.IGNORECASE)
    if not match:
        raise ValueError("rewards_earned must be a nonnegative whole-point value")
    return int(match.group(1))


def floor_points(amount, multiplier):
    return int((amount * Decimal(multiplier)).to_integral_value(rounding=ROUND_FLOOR))


def merchant_key(value):
    return " ".join(str(value or "").strip().casefold().split())


def resolve_eco_eligibility(tx, category_green_is_eligible):
    """Return (bool|None, reason). None means evidence is insufficient."""
    merchant = merchant_key(tx.get("merchant_name"))
    if merchant in EXCLUDED_ECO_MERCHANTS:
        return False, "documented excluded EcoCard merchant; standard rate applies"
    if merchant in CERTIFIED_EV_NETWORKS:
        return True, "documented certified EV charging network"
    if "green_eligible" in tx:
        value = tx["green_eligible"]
        if not isinstance(value, bool):
            raise ValueError("green_eligible must be true or false when supplied")
        return value, "explicit green eligibility supplied"
    if category_green_is_eligible and str(tx.get("category", "")).strip().casefold() == "green":
        return True, "source category is configured as a qualifying-green classification"
    return None, "green eligibility is not established by the supplied data"


def analyze_one(tx, category_green_is_eligible):
    if not isinstance(tx, dict):
        return {"classification": "unreviewable", "reason": "transaction must be an object"}
    result = {
        "transaction_id": tx.get("transaction_id"),
        "card_type": tx.get("card_type") or tx.get("credit_card_type"),
        "merchant_name": tx.get("merchant_name"),
    }
    card = result["card_type"]
    if str(tx.get("status", "")).strip().upper() != "COMPLETED":
        result.update(classification="unreviewable", reason="only completed transactions are reviewed")
        return result
    try:
        amount = parse_decimal(tx.get("transaction_amount"), "transaction_amount")
        recorded = parse_points(tx.get("rewards_earned"))
    except ValueError as exc:
        result.update(classification="unreviewable", reason=str(exc))
        return result

    if card == GOLD:
        expected = floor_points(amount, "2.5")
        rate_reason = "Gold Rewards Card earns 2.5% cash back (2.5 stored points per dollar)"
    elif card == ECO:
        try:
            eligible, eligibility_reason = resolve_eco_eligibility(tx, category_green_is_eligible)
        except ValueError as exc:
            result.update(classification="unreviewable", reason=str(exc))
            return result
        if eligible is None:
            result.update(classification="indeterminate", recorded_points=recorded,
                          reason=eligibility_reason)
            return result
        expected = floor_points(amount, "5" if eligible else "1")
        rate_reason = ("EcoCard qualifying-green rate: 5 points per dollar" if eligible
                       else "EcoCard standard rate: 1 point per dollar")
        rate_reason += "; " + eligibility_reason
    else:
        result.update(classification="unsupported_card", recorded_points=recorded,
                      reason="no documented calculation rule for this card type")
        return result

    difference = expected - recorded
    if difference > 0:
        classification = "under_awarded"
    elif difference < 0:
        classification = "over_awarded"
    else:
        classification = "matches_expected"
    result.update(
        classification=classification,
        transaction_amount=format(amount, "f"),
        recorded_points=recorded,
        expected_points=expected,
        point_difference=difference,
        difference_cash_value=format(Decimal(abs(difference)) / Decimal("100"), ".2f"),
        reason=rate_reason + "; fractional points are truncated down",
    )
    return result


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict) or not isinstance(payload.get("transactions"), list):
            raise ValueError("input must be an object with a transactions array")
        category_flag = payload.get("category_green_is_eligible", False)
        if not isinstance(category_flag, bool):
            raise ValueError("category_green_is_eligible must be boolean")
        findings = [analyze_one(tx, category_flag) for tx in payload["transactions"]]
        candidates = [
            {"transaction_id": f.get("transaction_id"), "user_id": payload.get("user_id"),
             "classification": f["classification"], "expected_points": f["expected_points"],
             "recorded_points": f["recorded_points"]}
            for f in findings
            if f.get("classification") in {"under_awarded", "over_awarded"}
            and f.get("transaction_id")
        ]
        counts = {}
        for finding in findings:
            key = finding["classification"]
            counts[key] = counts.get(key, 0) + 1
        output = {"findings": findings, "summary": counts, "dispute_candidates": candidates}
    except (ValueError, json.JSONDecodeError) as exc:
        output = {"error": str(exc)}
    json.dump(output, sys.stdout, sort_keys=True)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
