#!/usr/bin/env python3
"""Calculate expected Gold Rewards Card and EcoCard transaction rewards.

Reads JSON from stdin with {"transactions": [...]} and emits one JSON object.
No bank actions are performed.
"""

import json
import re
import sys
from decimal import Decimal, InvalidOperation, ROUND_FLOOR

EXCLUDED_ECO_MERCHANTS = {"target", "walmart", "amazon", "thredup"}
CERTIFIED_EV_MERCHANTS = {"tesla supercharger", "chargepoint", "evgo"}


def normalize_text(value):
    return " ".join(str(value or "").casefold().split())


def as_decimal(value, field):
    if isinstance(value, bool) or value is None:
        raise ValueError(field + " must be a decimal amount")
    text = str(value).strip().replace("$", "").replace(",", "")
    try:
        amount = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(field + " is not a valid decimal") from exc
    if amount < 0:
        raise ValueError(field + " must not be negative")
    return amount


def as_points(value):
    if isinstance(value, bool) or value is None:
        raise ValueError("rewards_earned is required")
    match = re.fullmatch(r"\s*(\d+)\s*(?:points?)?\s*", str(value), re.IGNORECASE)
    if not match:
        raise ValueError("rewards_earned must be a nonnegative whole-point value")
    return int(match.group(1))


def floor_points(amount, rate):
    return int((amount * rate).to_integral_value(rounding=ROUND_FLOOR))


def eco_eligibility(record):
    """Return (eligible, source) or (None, source) when not determinable."""
    merchant = normalize_text(record.get("merchant_name"))
    category = normalize_text(record.get("category"))

    if merchant in EXCLUDED_ECO_MERCHANTS:
        return False, "documented EcoCard merchant exclusion"
    if merchant in CERTIFIED_EV_MERCHANTS:
        return True, "certified EV-charging partner"

    # Do not promote a specifically identified non-partner charging network.
    charging_words = ("charging", "charger", "supercharger")
    if any(word in merchant for word in charging_words):
        return False, "identified charging merchant is not a certified partner"

    explicit = record.get("green_eligible")
    if isinstance(explicit, bool):
        return explicit, "supplied eligibility determination"
    if explicit is not None:
        return None, "green_eligible must be boolean when supplied"
    if category == "green":
        return True, "transaction category marked Green"
    if category:
        return False, "transaction category is not Green"
    return None, "no category or eligibility determination supplied"


def audit_record(record, index):
    if not isinstance(record, dict):
        return {"index": index, "outcome": "invalid_record", "error": "transaction must be an object"}

    transaction_id = record.get("transaction_id")
    card = str(record.get("credit_card_type", "")).strip()
    base = {
        "index": index,
        "transaction_id": transaction_id,
        "credit_card_type": card,
        "merchant_name": record.get("merchant_name"),
    }
    if not transaction_id:
        base.update({"outcome": "invalid_record", "error": "transaction_id is required"})
        return base

    if normalize_text(record.get("status")) != "completed":
        base.update({"outcome": "skipped", "explanation": "only COMPLETED transactions are audited"})
        return base

    if card not in ("Gold Rewards Card", "EcoCard"):
        base.update({"outcome": "unsupported_card", "explanation": "card type is outside this Skill"})
        return base

    try:
        amount = as_decimal(record.get("transaction_amount"), "transaction_amount")
        recorded = as_points(record.get("rewards_earned"))
    except ValueError as exc:
        base.update({"outcome": "invalid_record", "error": str(exc)})
        return base

    if card == "Gold Rewards Card":
        expected = floor_points(amount, Decimal("2.5"))
        rationale = "Gold Rewards Card: floor(amount × 2.5 points per dollar)"
    else:
        eligible, eligibility_source = eco_eligibility(record)
        if eligible is None:
            base.update({
                "outcome": "needs_eligibility_review",
                "recorded_points": recorded,
                "explanation": eligibility_source,
            })
            return base
        rate = Decimal("5") if eligible else Decimal("1")
        expected = floor_points(amount, rate)
        rate_name = "qualifying green" if eligible else "standard"
        rationale = "EcoCard %s rate: floor(amount × %s points per dollar); %s" % (
            rate_name, rate, eligibility_source)

    difference = expected - recorded
    base.update({
        "expected_points": expected,
        "recorded_points": recorded,
        "difference_points": difference,
        "expected_cash_value": format(Decimal(expected) * Decimal("0.01"), ".2f"),
        "recorded_cash_value": format(Decimal(recorded) * Decimal("0.01"), ".2f"),
        "explanation": rationale,
    })
    if difference == 0:
        base["outcome"] = "match"
    else:
        base["outcome"] = "possible_discrepancy"
    return base


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict) or not isinstance(payload.get("transactions"), list):
            raise ValueError("input must be an object containing a transactions array")
        results = [audit_record(record, i) for i, record in enumerate(payload["transactions"])]
        discrepancies = [r for r in results if r.get("outcome") == "possible_discrepancy"]
        summary = {
            "input_count": len(results),
            "match_count": sum(r.get("outcome") == "match" for r in results),
            "possible_discrepancy_count": len(discrepancies),
            "skipped_count": sum(r.get("outcome") == "skipped" for r in results),
            "needs_eligibility_review_count": sum(r.get("outcome") == "needs_eligibility_review" for r in results),
            "invalid_record_count": sum(r.get("outcome") == "invalid_record" for r in results),
            "unsupported_card_count": sum(r.get("outcome") == "unsupported_card" for r in results),
        }
        print(json.dumps({"ok": True, "summary": summary, "results": results, "discrepancies": discrepancies}, indent=2))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
