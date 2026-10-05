#!/usr/bin/env python3
"""Analyze documented credit-card rewards. Reads JSON stdin and writes JSON stdout."""

import json
import re
import sys
from decimal import Decimal, InvalidOperation, ROUND_FLOOR, ROUND_HALF_UP

BONUS_CATEGORIES = {"travel", "software", "media"}
SILVER_CATEGORIES = {"travel", "software"}
ECO_EXCLUDED_MERCHANTS = {"target", "walmart", "amazon", "thredup"}
EV_PARTNERS = {"tesla supercharger", "chargepoint", "evgo"}
FINAL_STATUSES = {"completed", "posted", "settled"}


def normalized(value):
    return str(value or "").strip().casefold()


def parse_decimal(value, field):
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{field} is required and must be numeric")
    if isinstance(value, (int, float, Decimal)):
        text = str(value)
    else:
        text = str(value).strip().replace(",", "").replace("$", "")
    if not re.fullmatch(r"[-+]?\d+(?:\.\d+)?", text):
        raise ValueError(f"{field} is not a valid numeric value")
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"{field} is not a valid numeric value") from exc


def parse_points(value):
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError("rewards_earned is not numeric")
    if isinstance(value, (int, float, Decimal)):
        return parse_decimal(value, "rewards_earned")
    match = re.search(r"[-+]?\d+(?:\.\d+)?", str(value).replace(",", ""))
    if not match:
        raise ValueError("rewards_earned is not numeric")
    return Decimal(match.group(0))


def json_number(value):
    if value is None:
        return None
    if value == value.to_integral_value():
        return int(value)
    return format(value, "f")


def money_text(points):
    return format(Decimal(points) / Decimal("100"), ".2f")


def round_points(raw, mode):
    rounding = ROUND_FLOOR if mode == "floor" else ROUND_HALF_UP
    return int(raw.to_integral_value(rounding=rounding))


def merchant_matches(merchant, candidates):
    return any(candidate in merchant for candidate in candidates)


def contains_any(text, phrases):
    return any(phrase in text for phrase in phrases)


def result_base(tx):
    return {
        "transaction_id": tx.get("transaction_id"),
        "card_type": tx.get("credit_card_type", tx.get("card_type")),
        "merchant_name": tx.get("merchant_name"),
        "transaction_date": tx.get("transaction_date"),
        "category": tx.get("category"),
    }


def not_reviewable(base, reason, disposition="not_reviewable"):
    base.update({
        "disposition": disposition,
        "reason": reason,
        "rate_points_per_dollar": None,
        "expected_points": None,
        "actual_points": None,
        "difference_points": None,
        "expected_cash_value_usd": None,
    })
    return base


def eligibility_and_rate(tx):
    """Return (rate, reason) or (None, reason) for a supported calculation."""
    card = normalized(tx.get("credit_card_type", tx.get("card_type")))
    category = normalized(tx.get("category"))
    merchant = normalized(tx.get("merchant_name"))
    kind = " ".join(normalized(tx.get(k)) for k in ("transaction_kind", "type", "category"))

    if card == "crypto-cash back":
        if tx.get("is_eligible") is False:
            return None, "purchase is explicitly marked ineligible"
        return Decimal("2"), "documented Crypto-Cash Back eligible-purchase rate"

    if card == "business platinum rewards card":
        if tx.get("is_cash_equivalent") is True or tx.get("is_balance_transfer") is True or tx.get("is_fee") is True:
            return Decimal("0"), "explicit Business Platinum no-reward transaction type"
        if contains_any(kind, ("cash equivalent", "balance transfer", " fee", "fees")):
            return Decimal("0"), "Business Platinum excluded transaction type"
        if category in BONUS_CATEGORIES:
            return Decimal("4"), "documented Business Platinum bonus category"
        return Decimal("1.5"), "documented Business Platinum standard rate"

    if card == "silver rewards card":
        if tx.get("is_gift_card") is True or tx.get("is_person_to_person") is True or tx.get("is_fee") is True:
            return Decimal("0"), "explicit Silver no-bonus transaction type"
        if contains_any(kind, ("gift card", "person-to-person", "p2p", "interest", "insurance", " fee", "fees")):
            return Decimal("0"), "Silver excluded transaction type"
        if category in SILVER_CATEGORIES:
            return Decimal("4"), "documented Silver travel/software rate"
        return None, "no Silver Rewards Card rate is documented for this category"

    if card == "ecocard":
        if merchant_matches(merchant, ECO_EXCLUDED_MERCHANTS):
            return Decimal("1"), "EcoCard excluded retailer receives standard rate"
        is_ev = tx.get("is_ev_charging") is True or "ev charging" in category
        if is_ev:
            if merchant_matches(merchant, EV_PARTNERS):
                return Decimal("5"), "EcoCard certified EV-charging partner"
            return Decimal("1"), "EcoCard nonpartner EV charging receives standard rate"
        if tx.get("merchant_of_record_confirmed") is False:
            return None, "merchant of record is known not to be confirmed as qualifying green"
        if tx.get("green_eligible") is True or category in {"green", "sustainable"}:
            return Decimal("5"), "EcoCard qualifying green purchase"
        if tx.get("green_eligible") is False:
            return Decimal("1"), "EcoCard purchase explicitly not green-eligible"
        return Decimal("1"), "EcoCard standard non-green rate"

    return None, "card type is outside this Skill's documented reward policies"


def analyze_transaction(tx, included_cards, rounding):
    base = result_base(tx)
    if not isinstance(tx, dict):
        return not_reviewable({"transaction_id": None}, "transaction must be an object", "invalid")
    if not tx.get("transaction_id"):
        return not_reviewable(base, "transaction_id is required", "invalid")
    card_norm = normalized(tx.get("credit_card_type", tx.get("card_type")))
    if not card_norm:
        return not_reviewable(base, "credit_card_type is required", "invalid")
    if included_cards is not None and card_norm not in included_cards:
        return not_reviewable(base, "transaction is outside requested review scope")
    status = normalized(tx.get("status"))
    if status not in FINAL_STATUSES:
        return not_reviewable(base, "transaction is not posted/completed; rewards may still adjust")
    if tx.get("is_return_or_credit") is True or status in {"returned", "refunded", "reversed", "credited"}:
        return not_reviewable(base, "return or credit must be reconciled against the original net purchase")
    try:
        amount = parse_decimal(tx.get("transaction_amount", tx.get("amount")), "transaction_amount")
    except ValueError as exc:
        return not_reviewable(base, str(exc), "invalid")
    if amount <= 0:
        return not_reviewable(base, "transaction_amount must be positive for an individual purchase review")
    try:
        actual = parse_points(tx.get("rewards_earned"))
    except ValueError as exc:
        return not_reviewable(base, str(exc), "invalid")
    if actual is None:
        return not_reviewable(base, "rewards_earned is required for comparison", "invalid")

    rate, reason = eligibility_and_rate(tx)
    if rate is None:
        disposition = "unresolved" if "merchant of record" in reason else "not_reviewable"
        return not_reviewable(base, reason, disposition)

    expected = round_points(amount * rate, rounding)
    difference = Decimal(expected) - actual
    if difference > 0:
        disposition = "under_earned"
    elif difference < 0:
        disposition = "over_earned"
    else:
        disposition = "matches"
    base.update({
        "disposition": disposition,
        "reason": reason,
        "rate_points_per_dollar": json_number(rate),
        "expected_points": expected,
        "actual_points": json_number(actual),
        "difference_points": json_number(difference),
        "expected_cash_value_usd": money_text(expected),
    })
    return base


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        transactions = payload.get("transactions")
        if not isinstance(transactions, list):
            raise ValueError("transactions must be an array")
        scope = payload.get("scope") or {}
        if not isinstance(scope, dict):
            raise ValueError("scope must be an object when supplied")
        rounding = scope.get("whole_point_rounding", "floor")
        if rounding not in {"floor", "half_up"}:
            raise ValueError("scope.whole_point_rounding must be floor or half_up")
        supplied_scope = scope.get("include_card_types")
        if supplied_scope is not None and not isinstance(supplied_scope, list):
            raise ValueError("scope.include_card_types must be an array when supplied")
        included_cards = None if supplied_scope is None else {normalized(x) for x in supplied_scope}
        findings = [analyze_transaction(tx, included_cards, rounding) for tx in transactions]
        counts = {}
        for finding in findings:
            key = finding["disposition"]
            counts[key] = counts.get(key, 0) + 1
        output = {
            "findings": findings,
            "summary": {
                "transactions_received": len(transactions),
                "disposition_counts": counts,
                "possible_under_earnings": counts.get("under_earned", 0),
            },
            "assumptions": {
                "point_cash_value_usd": "0.01 per point",
                "whole_point_rounding": rounding,
                "amount_basis": "each supplied positive posted/completed transaction amount is treated as its net purchase amount",
                "silver_scope": "only Travel and Software rows have a documented rate in this Skill",
            },
        }
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        output = {"error": "invalid_input", "message": str(exc)}
    json.dump(output, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
