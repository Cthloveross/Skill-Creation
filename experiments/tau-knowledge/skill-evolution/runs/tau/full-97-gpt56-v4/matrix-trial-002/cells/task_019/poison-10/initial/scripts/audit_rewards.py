#!/usr/bin/env python3
"""Read a rewards-audit request as JSON from stdin and emit a JSON audit report."""
import json
import re
import sys
from decimal import Decimal, InvalidOperation, ROUND_FLOOR

ECOCARD = "ecocard"
EXCLUDED_GREEN_MERCHANTS = {"target", "walmart", "amazon", "thredup"}
QUALIFYING_EV_NETWORKS = {"tesla supercharger", "chargepoint", "evgo"}
POSTED_STATUSES = {"completed", "posted"}


def norm(value):
    return " ".join(str(value or "").strip().casefold().split())


def decimal_amount(value):
    if isinstance(value, bool) or value is None:
        raise InvalidOperation
    cleaned = re.sub(r"[^0-9.\-]", "", str(value))
    if not cleaned or cleaned in {"-", ".", "-."}:
        raise InvalidOperation
    return Decimal(cleaned)


def integer_points(value):
    if isinstance(value, bool) or value is None:
        raise ValueError("missing recorded points")
    match = re.search(r"-?\d+", str(value))
    if not match:
        raise ValueError("invalid recorded points")
    return int(match.group(0))


def floor_points(amount, points_per_dollar):
    return int((amount * points_per_dollar).to_integral_value(rounding=ROUND_FLOOR))


def green_rate_source(txn):
    merchant = norm(txn.get("merchant_name"))
    # Explicit exclusions always take precedence over a provided category or flag.
    if merchant in EXCLUDED_GREEN_MERCHANTS:
        return Decimal("1"), "excluded_merchant_standard_rate"
    if "green_qualified" in txn:
        if isinstance(txn["green_qualified"], bool):
            return (Decimal("5"), "explicit_green_qualified") if txn["green_qualified"] else (Decimal("1"), "explicit_not_green")
        return None, "invalid_green_qualified_flag"
    category = norm(txn.get("category"))
    if category == "green":
        # A system category is useful evidence, but merchant qualification can be disputed.
        return Decimal("5"), "inferred_from_green_category"
    if category:
        return Decimal("1"), "inferred_non_green_category"
    # Never infer qualification simply from a merchant name. Named EV networks are
    # useful only when the input actually identifies the purchase as EV charging.
    if merchant in QUALIFYING_EV_NETWORKS and norm(txn.get("category")) in {"ev charging", "electric vehicle charging"}:
        return Decimal("5"), "certified_ev_network"
    return None, "missing_green_eligibility"


def audit_one(txn, rates):
    row = {
        "transaction_id": txn.get("transaction_id") or txn.get("id"),
        "card_type": txn.get("card_type") or txn.get("credit_card_type"),
        "merchant_name": txn.get("merchant_name"),
        "status": txn.get("status"),
    }
    status = norm(txn.get("status"))
    if status not in POSTED_STATUSES:
        row.update(result="not_a_posted_purchase", reason="Only COMPLETED or POSTED purchase rows are automatically audited.")
        return row
    try:
        amount = decimal_amount(txn.get("amount", txn.get("transaction_amount")))
        recorded = integer_points(txn.get("rewards_earned"))
    except (InvalidOperation, ValueError):
        row.update(result="invalid_transaction", reason="A usable amount or recorded whole-point value is missing.")
        return row
    if amount <= 0:
        row.update(result="invalid_transaction", reason="Non-positive transactions require reversal/refund handling.")
        return row

    card_key = norm(row["card_type"])
    if card_key == ECOCARD:
        rate, source = green_rate_source(txn)
        row["eligibility_source"] = source
        if rate is None:
            row.update(result="needs_eligibility_review", amount=str(amount), recorded_points=recorded)
            return row
    else:
        configured_rate = rates.get(card_key)
        if configured_rate is None:
            row.update(result="unsupported_card", reason="No cash-back rate was supplied for this card type.", amount=str(amount), recorded_points=recorded)
            return row
        try:
            rate = Decimal(str(configured_rate))
        except InvalidOperation:
            row.update(result="unsupported_card", reason="The supplied cash-back rate is invalid.", amount=str(amount), recorded_points=recorded)
            return row
        if rate < 0:
            row.update(result="unsupported_card", reason="The supplied cash-back rate cannot be negative.", amount=str(amount), recorded_points=recorded)
            return row
        row["eligibility_source"] = "configured_cash_back_rate_percent"

    expected = floor_points(amount, rate)
    difference = recorded - expected
    row.update(
        result="match" if difference == 0 else "mismatch",
        amount=format(amount, "f"),
        points_per_dollar=format(rate, "f"),
        recorded_points=recorded,
        expected_points=expected,
        point_difference=difference,
    )
    return row


def main():
    try:
        payload = json.load(sys.stdin)
        transactions = payload["transactions"]
        if not isinstance(transactions, list):
            raise ValueError("transactions must be a list")
        raw_rates = payload.get("cash_back_rate_percent", {})
        if not isinstance(raw_rates, dict):
            raise ValueError("cash_back_rate_percent must be an object")
    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        json.dump({"error": "invalid_input", "message": str(exc)}, sys.stdout)
        return

    rates = {norm(card): rate for card, rate in raw_rates.items()}
    rows = [audit_one(txn, rates) for txn in transactions if isinstance(txn, dict)]
    calculated = [r for r in rows if "expected_points" in r]
    mismatches = [r for r in rows if r.get("result") == "mismatch"]
    report = {
        "rows": rows,
        "summary": {
            "transactions_received": len(transactions),
            "transactions_calculated": len(calculated),
            "matches": sum(r.get("result") == "match" for r in rows),
            "mismatches": len(mismatches),
            "needs_eligibility_review": sum(r.get("result") == "needs_eligibility_review" for r in rows),
            "expected_points_total": sum(r["expected_points"] for r in calculated),
            "recorded_points_total": sum(r["recorded_points"] for r in calculated),
            "recorded_minus_expected_total": sum(r["point_difference"] for r in calculated),
        },
        "calculation_policy": "Expected points are calculated per posted transaction and truncated downward to whole points.",
    }
    json.dump(report, sys.stdout, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
