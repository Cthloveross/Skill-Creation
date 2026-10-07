#!/usr/bin/env python3
"""Calculation-only comparison of supplied card terms for one planned purchase.

Read one JSON object from stdin and emit one JSON object on stdout. The caller
extracts terms from disclosures and communicates all conditions to the customer.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

ZERO = Decimal("0")
CENT = Decimal("0.01")


def as_decimal(value: Any, label: str, errors: list[str], minimum: Decimal = ZERO) -> Decimal | None:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        errors.append(f"{label} must be numeric")
        return None
    if not result.is_finite() or result < minimum:
        errors.append(f"{label} must be a finite number at least {minimum}")
        return None
    return result


def money(value: Decimal) -> str:
    return str(value.quantize(CENT, rounding=ROUND_HALF_UP))


def as_date(value: Any, label: str, errors: list[str]) -> date | None:
    if value is None:
        return None
    if not isinstance(value, str):
        errors.append(f"{label} must be YYYY-MM-DD")
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        errors.append(f"{label} must be YYYY-MM-DD")
        return None


def promotion_state(item: dict[str, Any], when: date | None, new_customer: Any,
                    label: str, errors: list[str]) -> tuple[bool, bool, list[str]]:
    """Return (confirmed, still_possible, conditions)."""
    start = as_date(item.get("start"), label + ".start", errors)
    end = as_date(item.get("end"), label + ".end", errors)
    if start and end and start > end:
        errors.append(label + " has start after end")
        return False, False, []
    if when and start and when < start:
        return False, False, ["promotion has not started for the supplied opening date"]
    if when and end and when > end:
        return False, False, ["promotion has ended for the supplied opening date"]

    conditions: list[str] = []
    date_known = not ((start or end) and when is None)
    if not date_known:
        conditions.append("requires application or account-opening date verification")
    needs_new = bool(item.get("requires_new_customer", False))
    if needs_new and new_customer is False:
        return False, False, ["not available because new-customer status is false"]
    if needs_new and new_customer is None:
        conditions.append("requires new-customer eligibility verification")
    return date_known and (not needs_new or new_customer is True), True, conditions


def normalized_category(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip().lower()
    return value if value and value != "unknown" else None


def capacity(card: dict[str, Any], purchase: Decimal, prefix: str,
             errors: list[str]) -> tuple[str, list[str]]:
    low = as_decimal(card["minimum_credit_limit"], prefix + ".minimum_credit_limit", errors) if "minimum_credit_limit" in card else None
    high = as_decimal(card["maximum_credit_limit"], prefix + ".maximum_credit_limit", errors) if "maximum_credit_limit" in card else None
    caveat = ["actual approval and available credit must cover the charge"]
    if low is not None and high is not None and low > high:
        errors.append(prefix + " has a minimum credit limit above its maximum")
    if high is not None and high < purchase:
        return "published maximum below planned purchase", caveat
    if low is not None and low >= purchase:
        return "published minimum can cover purchase, subject to approval and available credit", caveat
    if high is not None:
        return "requires an approved credit line of at least the planned purchase", caveat
    return "credit-line range not supplied", caveat


def applicable_rate(card: dict[str, Any], category: str | None, default: Decimal,
                    prefix: str, errors: list[str]) -> tuple[Decimal, str]:
    if category is None:
        return default, "default rate used because merchant category is unknown"
    rates = card.get("category_cash_back_rates", {})
    if not isinstance(rates, dict):
        errors.append(prefix + ".category_cash_back_rates must be an object")
        return default, "default rate used because category-rate data is invalid"
    if category not in rates:
        return default, "default rate used because no supplied bonus rate matches merchant category"
    rate = as_decimal(rates[category], prefix + ".category_cash_back_rates." + category, errors)
    if rate is None:
        return default, "default rate used because matching category rate is invalid"
    return rate, "supplied category rate used for " + category


def category_matches(promo: dict[str, Any], category: str | None) -> bool:
    categories = promo.get("eligible_categories")
    if categories is None:
        return True
    if not isinstance(categories, list) or category is None:
        return False
    return category in {str(item).strip().lower() for item in categories}


def card_result(card: dict[str, Any], index: int, purchase: Decimal, category: str | None,
                when: date | None, new_customer: Any, errors: list[str]) -> dict[str, Any] | None:
    prefix = f"cards[{index}]"
    name = card.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append(prefix + ".name must be a nonempty string")
        return None
    default = as_decimal(card.get("default_cash_back_rate"), prefix + ".default_cash_back_rate", errors)
    fee = as_decimal(card.get("annual_fee", 0), prefix + ".annual_fee", errors)
    if default is None or fee is None:
        return None

    for field in ("fee_promotions", "rate_promotions", "spend_offers"):
        if field in card and not isinstance(card[field], list):
            errors.append(prefix + "." + field + " must be an array")

    rate, basis = applicable_rate(card, category, default, prefix, errors)
    conditional_fee = fee
    conditional_multiplier = Decimal("1")
    conditional_offer = ZERO
    conditions: list[str] = []

    promotions = card.get("fee_promotions", [])
    for n, promo in enumerate(promotions if isinstance(promotions, list) else []):
        if not isinstance(promo, dict):
            errors.append(prefix + f".fee_promotions[{n}] must be an object")
            continue
        promotional_fee = as_decimal(promo.get("fee"), prefix + f".fee_promotions[{n}].fee", errors)
        if promotional_fee is None:
            continue
        confirmed, possible, notes = promotion_state(promo, when, new_customer, prefix + f".fee_promotions[{n}]", errors)
        if confirmed or possible:
            conditional_fee = min(conditional_fee, promotional_fee)
            if not confirmed:
                conditions.extend(notes + ["first-year fee promotion is conditional"])

    promotions = card.get("rate_promotions", [])
    for n, promo in enumerate(promotions if isinstance(promotions, list) else []):
        if not isinstance(promo, dict):
            errors.append(prefix + f".rate_promotions[{n}] must be an object")
            continue
        if not category_matches(promo, category):
            if promo.get("eligible_categories") is not None and category is None:
                conditions.append("category-limited multiplier was not assumed because merchant category is unknown")
            continue
        multiplier = as_decimal(promo.get("multiplier"), prefix + f".rate_promotions[{n}].multiplier", errors)
        if multiplier is None:
            continue
        confirmed, possible, notes = promotion_state(promo, when, new_customer, prefix + f".rate_promotions[{n}]", errors)
        if confirmed or possible:
            conditional_multiplier *= multiplier
            if not confirmed:
                conditions.extend(notes + ["rate multiplier is conditional"])

    offers = card.get("spend_offers", [])
    for n, offer in enumerate(offers if isinstance(offers, list) else []):
        if not isinstance(offer, dict):
            errors.append(prefix + f".spend_offers[{n}] must be an object")
            continue
        amount = as_decimal(offer.get("amount"), prefix + f".spend_offers[{n}].amount", errors)
        threshold = as_decimal(offer.get("threshold"), prefix + f".spend_offers[{n}].threshold", errors)
        if amount is None or threshold is None or purchase < threshold:
            continue
        confirmed, possible, notes = promotion_state(offer, when, new_customer, prefix + f".spend_offers[{n}]", errors)
        if confirmed or possible:
            conditional_offer += amount
            timing = "requires net qualifying spend"
            if offer.get("requires_posting"):
                timing += " and timely transaction posting"
            if offer.get("period_months") is not None:
                timing += f" within {offer['period_months']} month(s)"
            conditions.append(timing)
            if not confirmed:
                conditions.extend(notes + ["spend offer is conditional"])

    credit_status, credit_conditions = capacity(card, purchase, prefix, errors)
    conditions.extend(credit_conditions)
    conditions.extend([
        "merchant coding and stated exclusions determine the final rate",
        "returns or credits can reduce rewards and qualifying spend",
    ])
    reward = purchase * rate
    return {
        "name": name.strip(),
        "merchant_category_used": category,
        "rate_basis": basis,
        "rate_used": str(rate),
        "purchase_reward_at_rate_used": money(reward),
        "standard_first_year_net": money(reward - fee),
        "conditional_first_year_net": money(reward * conditional_multiplier + conditional_offer - conditional_fee),
        "conditional_fee_used": money(conditional_fee),
        "credit_capacity": credit_status,
        "conditions": list(dict.fromkeys(conditions)),
        "notes": card.get("notes"),
    }


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "errors": ["invalid JSON: " + exc.msg], "results": []}))
        return
    if not isinstance(payload, dict):
        print(json.dumps({"ok": False, "errors": ["top-level JSON must be an object"], "results": []}))
        return

    errors: list[str] = []
    purchase = as_decimal(payload.get("purchase_amount"), "purchase_amount", errors, Decimal("0.01"))
    cards = payload.get("cards")
    if not isinstance(cards, list):
        errors.append("cards must be an array")
        cards = []
    application = as_date(payload.get("application_date"), "application_date", errors)
    opening = as_date(payload.get("account_open_date"), "account_open_date", errors)
    new_customer = payload.get("is_new_customer")
    if new_customer is not None and not isinstance(new_customer, bool):
        errors.append("is_new_customer must be true, false, or null")
    category = normalized_category(payload.get("merchant_category"))

    results: list[dict[str, Any]] = []
    if purchase is not None:
        for index, card in enumerate(cards):
            if not isinstance(card, dict):
                errors.append(f"cards[{index}] must be an object")
                continue
            result = card_result(card, index, purchase, category, opening or application, new_customer, errors)
            if result is not None:
                results.append(result)

    standard = sorted(results, key=lambda item: Decimal(item["standard_first_year_net"]), reverse=True)
    conditional = sorted(results, key=lambda item: Decimal(item["conditional_first_year_net"]), reverse=True)
    print(json.dumps({
        "ok": not errors,
        "errors": errors,
        "assumptions": {
            "merchant_category": category,
            "promotion_date_used": (opening or application).isoformat() if (opening or application) else None,
            "new_customer_status": new_customer,
            "scope": "one planned net purchase; neither approval nor merchant coding is assumed",
        },
        "results": results,
        "standard_ranking": [item["name"] for item in standard],
        "conditional_ranking": [item["name"] for item in conditional],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
