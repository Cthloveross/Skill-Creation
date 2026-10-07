#!/usr/bin/env python3
"""Compare documented card economics for a planned purchase.

Reads one JSON object from stdin and writes one JSON object to stdout.  The
schema is documented in SKILL.md.  This program is intentionally generic: it
performs arithmetic only and does not determine product facts or eligibility.
"""

from __future__ import annotations

import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, List, Optional

CENT = Decimal("0.01")


def money(value: Decimal) -> str:
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def decimal_field(obj: Dict[str, Any], key: str, *, required: bool = False) -> Optional[Decimal]:
    value = obj.get(key)
    if value is None:
        if required:
            raise ValueError("missing required field: " + key)
        return None
    if isinstance(value, bool):
        raise ValueError("field must be a decimal, not boolean: " + key)
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("invalid decimal field: " + key)


def tri_state(value: Any, key: str) -> Optional[bool]:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    raise ValueError("field must be true, false, or null: " + key)


def signup_status(card: Dict[str, Any], amount: Decimal) -> str:
    credit = decimal_field(card, "signup_credit")
    threshold = decimal_field(card, "signup_threshold")
    if credit is None and threshold is None:
        return "not_offered_or_not_supplied"
    if credit is None or threshold is None:
        return "incomplete_terms"
    if amount < threshold:
        return "not_met"
    conditions = card.get("signup_conditions")
    if not isinstance(conditions, dict):
        return "conditional"
    required = (
        "new_customer",
        "opened_in_offer_window",
        "net_spend_within_period",
        "purchases_post_within_period",
    )
    values: List[Optional[bool]] = []
    for key in required:
        values.append(tri_state(conditions.get(key), "signup_conditions." + key))
    if any(item is False for item in values):
        return "not_met"
    if any(item is None for item in values):
        return "conditional"
    return "confirmed"


def capacity_assessment(card: Dict[str, Any], amount: Decimal) -> str:
    minimum = decimal_field(card, "minimum_approved_credit")
    maximum = decimal_field(card, "maximum_available_credit")
    if maximum is not None and maximum < amount:
        return "documented_maximum_below_purchase"
    if minimum is not None and minimum >= amount:
        return "documented_minimum_covers_purchase"
    if minimum is not None or maximum is not None:
        return "approval_dependent"
    return "no_documented_limit_supplied"


def compare_card(card: Dict[str, Any], amount: Decimal, eligible: Optional[bool]) -> Dict[str, Any]:
    if not isinstance(card, dict):
        raise ValueError("each cards item must be an object")
    name = card.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("each card requires a non-empty name")

    standard_rate = decimal_field(card, "standard_rate_pct", required=True)
    if standard_rate is None or standard_rate < 0:
        raise ValueError("standard_rate_pct must be non-negative")
    qualifying_rate = decimal_field(card, "qualifying_rate_pct")
    if qualifying_rate is not None and qualifying_rate < 0:
        raise ValueError("qualifying_rate_pct must be non-negative")
    category = tri_state(card.get("category_qualifies"), "category_qualifies")

    conditional: List[str] = []
    applied_rate = standard_rate
    rate_basis = "standard_rate"
    if category is True:
        if qualifying_rate is None:
            conditional.append("category marked qualifying but no qualifying_rate_pct was supplied")
        else:
            applied_rate = qualifying_rate
            rate_basis = "confirmed_qualifying_category_rate"
    elif category is None and qualifying_rate is not None:
        conditional.append("enhanced category rate excluded because merchant classification is unconfirmed")

    multiplier = decimal_field(card, "promo_multiplier")
    if multiplier is None:
        multiplier = Decimal("1")
    if multiplier < 0:
        raise ValueError("promo_multiplier must be non-negative")
    promo_active = tri_state(card.get("promo_active"), "promo_active")
    applied_multiplier = Decimal("1")
    if multiplier != 1:
        if promo_active is True:
            applied_multiplier = multiplier
        elif promo_active is None:
            conditional.append("promotional multiplier excluded because promotion timing or eligibility is unconfirmed")
        else:
            conditional.append("promotional multiplier not applied because promotion is not active")

    if eligible is False:
        rewards = Decimal("0")
        rate_basis = "purchase_marked_ineligible"
    else:
        rewards = amount * applied_rate / Decimal("100") * applied_multiplier
        if eligible is None:
            conditional.append("calculation assumes the purchase is eligible for rewards")

    first_year_fee = decimal_field(card, "first_year_annual_fee")
    if first_year_fee is None:
        first_year_fee = decimal_field(card, "annual_fee")
    if first_year_fee is None:
        first_year_fee = Decimal("0")
        conditional.append("no first-year annual fee supplied; treated as zero only for arithmetic")
    if first_year_fee < 0:
        raise ValueError("annual fee must be non-negative")

    sign_status = signup_status(card, amount)
    sign_credit = decimal_field(card, "signup_credit") or Decimal("0")
    confirmed_signup = sign_credit if sign_status == "confirmed" else Decimal("0")
    if sign_status == "conditional":
        conditional.append("sign-up credit excluded until every offer condition is confirmed")
    elif sign_status == "incomplete_terms":
        conditional.append("sign-up credit excluded because its threshold or credit amount is incomplete")
    elif sign_status == "not_met":
        conditional.append("sign-up credit not included because threshold or stated conditions are not met")

    return {
        "name": name,
        "applied_rate_pct": str(applied_rate),
        "rate_basis": rate_basis,
        "applied_promo_multiplier": str(applied_multiplier),
        "gross_purchase_rewards": money(rewards),
        "signup_credit_status": sign_status,
        "confirmed_signup_credit": money(confirmed_signup),
        "first_year_fee_used": money(first_year_fee),
        "confirmed_net_value": money(rewards + confirmed_signup - first_year_fee),
        "conditional_items": conditional,
        "capacity_assessment": capacity_assessment(card, amount),
    }


def main() -> None:
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be a JSON object")
        amount = decimal_field(data, "purchase_amount", required=True)
        if amount is None or amount <= 0:
            raise ValueError("purchase_amount must be greater than zero")
        eligible = tri_state(data.get("purchase_eligible"), "purchase_eligible")
        cards = data.get("cards")
        if not isinstance(cards, list) or not cards:
            raise ValueError("cards must be a non-empty array")
        rows = [compare_card(card, amount, eligible) for card in cards]
        rows.sort(key=lambda row: Decimal(row["confirmed_net_value"]), reverse=True)
        print(json.dumps({"ok": True, "purchase_amount": money(amount), "comparisons": rows}, separators=(",", ":")))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, separators=(",", ":")))


if __name__ == "__main__":
    main()
