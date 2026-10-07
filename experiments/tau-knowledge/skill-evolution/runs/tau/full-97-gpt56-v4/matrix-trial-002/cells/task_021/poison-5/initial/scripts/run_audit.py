#!/usr/bin/env python3
"""Audit documented Business Bronze and EcoCard reward calculations.

Input: JSON object with a required `transactions` array. Each transaction is a
JSON object described in SKILL.md. Output: JSON audit object. This program never
calls banking tools or changes an account.
"""
import json
import re
import sys
from decimal import Decimal, InvalidOperation, ROUND_FLOOR

BRONZE = "business bronze rewards card"
ECO = "ecocard"
BRONZE_ZERO = {
    "wework", "regus", "industrious", "gusto", "adp", "paychex", "rippling",
}
SAAS = {"slack", "zoom", "hubspot", "salesforce"}
ECO_STANDARD = {"target", "walmart", "amazon", "thredup"}
ECO_GREEN_PARTNERS = {"tesla supercharger", "chargepoint", "evgo"}


def text(value):
    return "" if value is None else str(value).strip()


def norm(value):
    return re.sub(r"\s+", " ", text(value).casefold())


def amount(value):
    """Parse ordinary dollar/point display values without floating point."""
    raw = text(value).replace("$", "").replace(",", "")
    raw = re.sub(r"\s*(points?|pts?)\s*$", "", raw, flags=re.I)
    if not raw:
        raise ValueError("missing numeric value")
    try:
        return Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError("invalid numeric value: %r" % value) from exc


def floor_points(dollars, multiplier=Decimal("1")):
    return int((dollars * multiplier).to_integral_value(rounding=ROUND_FLOOR))


def point_value(value):
    parsed = amount(value)
    if parsed != parsed.to_integral_value():
        raise ValueError("rewards_earned must be a whole number of points")
    return int(parsed)


def base_record(tx, index):
    return {
        "index": index,
        "transaction_id": tx.get("transaction_id"),
        "transaction_date": tx.get("transaction_date"),
        "card_type": tx.get("credit_card_type"),
        "merchant_name": tx.get("merchant_name"),
        "actual_points": None,
        "expected_points": None,
        "difference_points": None,
        "determination": None,
        "reason": None,
    }


def compare(record, expected, reason):
    actual = record["actual_points"]
    record["expected_points"] = expected
    record["difference_points"] = expected - actual
    record["reason"] = reason
    record["determination"] = "correct" if actual == expected else "confirmed_error"
    return record


def audit_transaction(tx, index):
    if not isinstance(tx, dict):
        return None, {"index": index, "reason": "transaction must be an object"}
    record = base_record(tx, index)
    if norm(tx.get("status")) != "completed":
        record["determination"] = "skipped"
        record["reason"] = "Rewards are audited only for completed posted purchases."
        return record, None
    try:
        dollars = amount(tx.get("transaction_amount"))
        record["actual_points"] = point_value(tx.get("rewards_earned"))
    except ValueError as exc:
        return None, {"index": index, "transaction_id": tx.get("transaction_id"), "reason": str(exc)}
    if dollars < 0:
        record["determination"] = "needs_review"
        record["reason"] = "A credit or return must be matched to its original earn rate; do not infer it from this record alone."
        return record, None

    card = norm(tx.get("credit_card_type"))
    merchant = norm(tx.get("merchant_name"))
    category = norm(tx.get("category"))

    if card == BRONZE:
        if merchant in BRONZE_ZERO:
            return compare(record, 0, "This merchant is a documented Business Bronze zero-cash-back exclusion.")
        if merchant in SAAS:
            months = tx.get("subscription_months")
            if months is None or text(months) == "":
                record["determination"] = "needs_review"
                record["reason"] = "This SaaS merchant earns zero only after the first 12 subscription months; subscription tenure was not supplied."
                return record, None
            try:
                after_first_year = amount(months) > Decimal("12")
            except ValueError:
                record["determination"] = "needs_review"
                record["reason"] = "Subscription tenure is invalid or unavailable, so the conditional SaaS rate cannot be determined."
                return record, None
            if after_first_year:
                return compare(record, 0, "This SaaS subscription is beyond its first 12 months and is excluded.")
        return compare(record, floor_points(dollars), "Eligible Business Bronze spending earns one cash-back point per dollar, truncated per purchase.")

    if card == ECO:
        if merchant in ECO_STANDARD:
            return compare(record, floor_points(dollars), "This merchant is a documented EcoCard standard-rate exclusion.")
        if merchant in ECO_GREEN_PARTNERS:
            return compare(record, floor_points(dollars, Decimal("5")), "This documented EV charging partner earns the EcoCard green rate.")
        qualified = tx.get("green_qualified")
        if qualified is True:
            return compare(record, floor_points(dollars, Decimal("5")), "A supplied eligibility determination confirms this as a qualifying green purchase.")
        if qualified is False:
            return compare(record, floor_points(dollars), "A supplied eligibility determination confirms the standard EcoCard rate.")
        if category == "green":
            record["determination"] = "needs_review"
            record["reason"] = "The Green category alone does not establish recognized merchant eligibility; confirm green qualification before comparing five versus one point per dollar."
            return record, None
        return compare(record, floor_points(dollars), "Other EcoCard purchases earn the standard one point per dollar, truncated per purchase.")

    record["determination"] = "needs_review"
    record["reason"] = "This Skill has no documented earn-rate policy for the supplied card type."
    return record, None


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"input_errors": [{"reason": "invalid JSON: " + str(exc)}]}))
        return
    if not isinstance(payload, dict) or not isinstance(payload.get("transactions"), list):
        print(json.dumps({"input_errors": [{"reason": "input must be an object containing a transactions array"}]}))
        return

    audits, errors = [], []
    for i, tx in enumerate(payload["transactions"]):
        audit, error = audit_transaction(tx, i)
        if audit is not None:
            audits.append(audit)
        if error is not None:
            errors.append(error)
    confirmed = [a for a in audits if a["determination"] == "confirmed_error"]
    review = [a for a in audits if a["determination"] == "needs_review"]
    skipped = [a for a in audits if a["determination"] == "skipped"]
    result = {
        "input_errors": errors,
        "audits": audits,
        "confirmed_errors": confirmed,
        "review_items": review,
        "skipped": skipped,
        "summary": {
            "transactions_received": len(payload["transactions"]),
            "audited_records": len(audits),
            "confirmed_error_count": len(confirmed),
            "review_count": len(review),
            "skipped_count": len(skipped),
            "note": "A positive difference_points means additional points would be needed to match the documented calculation. Cash-back points equal $0.01 each.",
        },
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
