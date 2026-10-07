#!/usr/bin/env python3
"""Calculate review evidence for Gold Rewards Card and EcoCard transactions.

Read one JSON object from stdin; write one JSON object to stdout.  The helper
never calls banking tools and never authorizes a rewards update.
"""
import json
import re
import sys
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_DOWN, ROUND_HALF_UP

POINT_RE = re.compile(r"^\s*(-?\d+)\s*(?:points?)?\s*$", re.I)
ROUNDING = {"floor": ROUND_DOWN, "nearest": ROUND_HALF_UP, "ceiling": ROUND_CEILING}
ECO_EXCLUSIONS = {"target", "walmart", "amazon", "thredup"}
CERTIFIED_EV = {"tesla supercharger", "chargepoint", "evgo"}


def amount_of(value):
    if isinstance(value, bool):
        raise ValueError("amount must be a decimal number, not boolean")
    result = Decimal(str(value).strip().replace("$", "").replace(",", ""))
    if result < 0:
        raise ValueError("amount must be non-negative; identify reversals by status")
    return result


def points_of(value):
    if value is None:
        return None
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    found = POINT_RE.match(str(value))
    if not found:
        raise ValueError("rewards_earned must be an integer or '<integer> points'")
    return int(found.group(1))


def normalized(value):
    return " ".join(str(value or "").casefold().split())


def eco_rate(tx):
    merchant = normalized(tx.get("merchant_name"))
    explicit = tx.get("eco_green_eligible")
    # Processor/merchant variants such as Amazon Marketplace remain Amazon purchases.
    if any(merchant == excluded or merchant.startswith(excluded + " ") or merchant.startswith(excluded + ".")
           for excluded in ECO_EXCLUSIONS):
        return Decimal("1"), "standard_excluded_merchant", "Merchant is explicitly excluded from EcoCard high-rate rewards."
    category = normalized(tx.get("category"))
    is_ev = "charging" in merchant or "supercharger" in merchant
    if is_ev and merchant not in CERTIFIED_EV:
        return Decimal("1"), "standard_nonpartner_ev", "EV charging is high-rate only at the three certified networks."
    if merchant in CERTIFIED_EV:
        return Decimal("5"), "green_confirmed_partner_ev", "Merchant is a named certified EV-charging network."
    if explicit is True:
        return Decimal("5"), "green_confirmed", "Green eligibility was explicitly supplied."
    if explicit is False:
        return Decimal("1"), "standard_confirmed", "Standard-rate eligibility was explicitly supplied."
    if category == "green":
        return Decimal("5"), "green_indicated", "Transaction category indicates green; confirm merchant context if disputed."
    return Decimal("1"), "standard_indicated", "No green category or explicit eligibility was supplied."


def audit_one(tx, rounding):
    required = [key for key in ("transaction_id", "card_type", "amount") if tx.get(key) in (None, "")]
    if required:
        return {"transaction_id": tx.get("transaction_id"), "status": "invalid_input", "error": "missing: " + ", ".join(required)}
    try:
        amount, observed = amount_of(tx["amount"]), points_of(tx.get("rewards_earned"))
    except (InvalidOperation, ValueError) as exc:
        return {"transaction_id": tx.get("transaction_id"), "status": "invalid_input", "error": str(exc)}
    card = str(tx["card_type"]).strip()
    out = {"transaction_id": tx["transaction_id"], "card_type": card,
           "amount": format(amount, "f"), "transaction_status": tx.get("status"),
           "recorded_points": observed}
    if card == "Gold Rewards Card":
        rate, basis = Decimal("2.5"), "Gold Rewards Card earns 2.5 points per dollar."
    elif card == "EcoCard":
        rate, assessment, basis = eco_rate(tx)
        out["eligibility_assessment"] = assessment
    else:
        out.update(status="insufficient_rate_information",
                   reason="No earning-rate terms for this card type were supplied; submit a dispute if appropriate, but do not estimate a correction.")
        return out
    exact = amount * rate
    out.update(rate_points_per_dollar=format(rate, "f"), calculation_basis=basis,
               expected_exact_points=format(exact, "f"))
    if rounding == "unresolved":
        out.update(status="needs_rounding_confirmation",
                   reason="No whole-point rounding treatment was supplied; do not make an automated correction.")
        return out
    expected = int(exact.quantize(Decimal("1"), rounding=ROUNDING[rounding]))
    out.update(rounding=rounding, expected_whole_points=expected)
    if observed is None:
        out["status"] = "calculated_no_recorded_value"
    elif observed == expected:
        out["status"] = "matches_calculation"
    else:
        out.update(status="discrepancy_for_review", difference_points=expected - observed)
    return out


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        rounding = payload.get("rounding", "unresolved")
        if rounding not in {"unresolved", *ROUNDING}:
            raise ValueError("rounding must be unresolved, floor, nearest, or ceiling")
        txs = payload.get("transactions")
        if not isinstance(txs, list):
            raise ValueError("transactions must be a list")
        results = [audit_one(tx, rounding) if isinstance(tx, dict) else
                   {"status": "invalid_input", "error": "each transaction must be an object"} for tx in txs]
        print(json.dumps({"rounding": rounding, "results": results}, ensure_ascii=False))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)

if __name__ == "__main__":
    main()
