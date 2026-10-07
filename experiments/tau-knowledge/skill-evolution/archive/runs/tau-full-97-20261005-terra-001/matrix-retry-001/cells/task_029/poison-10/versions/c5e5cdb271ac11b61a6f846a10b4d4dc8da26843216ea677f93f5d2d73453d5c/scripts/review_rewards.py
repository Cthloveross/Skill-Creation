#!/usr/bin/env python3
"""Analyze documented credit-card reward calculations from JSON stdin."""
import json
import re
import sys
from decimal import Decimal, InvalidOperation, ROUND_FLOOR

FINAL = {"completed", "posted", "settled"}
BP_BONUS = {"travel", "software", "media"}
SILVER_BONUS = {"travel", "software"}
ECO_EXCLUSIONS = {"target", "walmart", "amazon", "thredup"}
EV_PARTNERS = {"tesla supercharger", "chargepoint", "evgo"}


def norm(value):
    return str(value or "").strip().casefold()


def decimal_value(value, field):
    if value is None or isinstance(value, bool):
        raise ValueError(field + " is required and must be numeric")
    text = str(value).strip().replace("$", "").replace(",", "")
    if not re.fullmatch(r"[-+]?\d+(?:\.\d+)?", text):
        raise ValueError(field + " is not numeric")
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(field + " is not numeric") from exc


def point_value(value):
    if value is None or value == "":
        raise ValueError("rewards_earned is required")
    if isinstance(value, bool):
        raise ValueError("rewards_earned is not numeric")
    match = re.search(r"[-+]?\d+(?:\.\d+)?", str(value).replace(",", ""))
    if not match:
        raise ValueError("rewards_earned is not numeric")
    return Decimal(match.group(0))


def number(value):
    if value is None:
        return None
    return int(value) if value == value.to_integral_value() else format(value, "f")


def base(tx):
    return {
        "transaction_id": tx.get("transaction_id"),
        "card_type": tx.get("credit_card_type", tx.get("card_type")),
        "merchant_name": tx.get("merchant_name"),
        "transaction_date": tx.get("transaction_date"),
        "category": tx.get("category"),
    }


def unavailable(result, disposition, reason):
    result.update({
        "disposition": disposition, "reason": reason,
        "rate_points_per_dollar": None, "expected_points": None,
        "actual_points": None, "difference_points": None,
        "difference_cash_value_usd": None,
    })
    return result


def merchant_contains(merchant, names):
    return any(name in merchant for name in names)


def rate_for(tx):
    card = norm(tx.get("credit_card_type", tx.get("card_type")))
    category = norm(tx.get("category"))
    merchant = norm(tx.get("merchant_name"))
    kind = " ".join(norm(tx.get(k)) for k in ("transaction_kind", "type", "category"))

    if card == "crypto-cash back":
        if tx.get("is_eligible") is False:
            return None, "not_reviewable", "purchase is explicitly ineligible"
        return Decimal("2"), None, "documented Crypto-Cash Back eligible-purchase rate"

    if card == "business platinum rewards card":
        excluded = (tx.get("is_cash_equivalent") is True or
                    tx.get("is_balance_transfer") is True or tx.get("is_fee") is True or
                    any(word in kind for word in ("cash equivalent", "balance transfer", " fee", "fees")))
        if excluded:
            return Decimal("0"), None, "Business Platinum excluded transaction type"
        if category in BP_BONUS:
            return Decimal("4"), None, "documented Business Platinum Travel/Software/Media rate"
        return Decimal("1.5"), None, "documented Business Platinum standard rate"

    if card == "silver rewards card":
        excluded = (tx.get("is_gift_card") is True or tx.get("is_person_to_person") is True or
                    tx.get("is_fee") is True or
                    any(word in kind for word in ("gift card", "person-to-person", "p2p", "interest", "insurance", " fee", "fees")))
        if excluded:
            return Decimal("0"), None, "Silver excluded transaction type"
        if category in SILVER_BONUS:
            return Decimal("4"), None, "documented Silver Travel/Software rate"
        return None, "not_reviewable", "no Silver rate is documented for this category"

    if card == "ecocard":
        if merchant_contains(merchant, ECO_EXCLUSIONS):
            return Decimal("1"), None, "EcoCard excluded merchant receives standard rate"
        ev_charging = tx.get("is_ev_charging") is True or "ev charging" in category
        if ev_charging:
            if merchant_contains(merchant, EV_PARTNERS):
                return Decimal("5"), None, "EcoCard certified EV-charging partner"
            return Decimal("1"), None, "EcoCard nonpartner EV charging receives standard rate"
        if tx.get("merchant_of_record_confirmed") is False:
            return None, "unresolved", "qualifying merchant of record is not confirmed"
        if tx.get("green_eligible") is True or category in {"green", "sustainable"}:
            return Decimal("5"), None, "EcoCard qualifying green purchase"
        return Decimal("1"), None, "EcoCard standard non-green rate"

    return None, "not_reviewable", "card type is outside documented policies"


def analyze(tx, included):
    if not isinstance(tx, dict):
        return unavailable({"transaction_id": None}, "invalid", "transaction must be an object")
    result = base(tx)
    if not tx.get("transaction_id"):
        return unavailable(result, "invalid", "transaction_id is required")
    card = norm(tx.get("credit_card_type", tx.get("card_type")))
    if not card:
        return unavailable(result, "invalid", "credit_card_type is required")
    if included is not None and card not in included:
        return unavailable(result, "not_reviewable", "transaction is outside requested scope")
    status = norm(tx.get("status"))
    if status not in FINAL:
        return unavailable(result, "not_reviewable", "transaction is not posted/completed")
    if tx.get("is_return_or_credit") is True:
        return unavailable(result, "not_reviewable", "return or credit requires net-purchase reconciliation")
    try:
        amount = decimal_value(tx.get("transaction_amount", tx.get("amount")), "transaction_amount")
        actual = point_value(tx.get("rewards_earned"))
    except ValueError as exc:
        return unavailable(result, "invalid", str(exc))
    if amount <= 0:
        return unavailable(result, "not_reviewable", "transaction_amount must be positive")

    rate, unavailable_disposition, reason = rate_for(tx)
    if rate is None:
        return unavailable(result, unavailable_disposition, reason)
    expected = int((amount * rate).to_integral_value(rounding=ROUND_FLOOR))
    difference = Decimal(expected) - actual
    disposition = "under_earned" if difference > 0 else "over_earned" if difference < 0 else "matches"
    result.update({
        "disposition": disposition,
        "reason": reason,
        "rate_points_per_dollar": number(rate),
        "expected_points": expected,
        "actual_points": number(actual),
        "difference_points": number(difference),
        "difference_cash_value_usd": format(abs(difference) / Decimal("100"), ".2f"),
    })
    return result


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict) or not isinstance(payload.get("transactions"), list):
            raise ValueError("input must be an object with a transactions array")
        scope = payload.get("scope") or {}
        if not isinstance(scope, dict):
            raise ValueError("scope must be an object")
        rounding = scope.get("whole_point_rounding", "floor")
        if rounding != "floor":
            raise ValueError("only floor whole-point rounding is supported")
        selected = scope.get("include_card_types")
        if selected is not None and not isinstance(selected, list):
            raise ValueError("scope.include_card_types must be an array")
        included = None if selected is None else {norm(x) for x in selected}
        findings = [analyze(tx, included) for tx in payload["transactions"]]
        counts = {}
        for finding in findings:
            counts[finding["disposition"]] = counts.get(finding["disposition"], 0) + 1
        mismatches = [f for f in findings if f["disposition"] in {"under_earned", "over_earned"}]
        output = {
            "findings": findings,
            "summary": {
                "transactions_received": len(findings),
                "disposition_counts": counts,
                "reward_mismatches": len(mismatches),
                "under_earnings": counts.get("under_earned", 0),
                "over_earnings": counts.get("over_earned", 0),
            },
            "assumptions": {
                "point_cash_value_usd": "0.01 per point",
                "whole_point_rounding": "floor",
                "amount_basis": "each supplied positive final transaction amount is treated as its net purchase amount",
                "silver_scope": "only Travel and Software have documented rates",
            },
        }
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        output = {"error": "invalid_input", "message": str(exc)}
    json.dump(output, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
