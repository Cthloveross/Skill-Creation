#!/usr/bin/env python3
"""Calculation-only comparison of supplied card terms for one planned purchase.

Reads a JSON object from stdin and emits a JSON object on stdout. The caller is
responsible for extracting terms from disclosures and for communicating all
conditions to the customer.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

ZERO = Decimal("0")
CENT = Decimal("0.01")


def dec(value: Any, label: str, errors: list[str], minimum: Decimal = ZERO) -> Decimal | None:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        errors.append(f"{label} must be numeric")
        return None
    if not result.is_finite() or result < minimum:
        errors.append(f"{label} must be a finite number at least {minimum}")
        return None
    return result


def dollars(value: Decimal) -> str:
    return str(value.quantize(CENT, rounding=ROUND_HALF_UP))


def date_value(value: Any, label: str, errors: list[str]) -> date | None:
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
    """Return confirmed, possible, and customer-facing conditions."""
    start = date_value(item.get("start"), label + ".start", errors)
    end = date_value(item.get("end"), label + ".end", errors)
    notes: list[str] = []
    if start and end and start > end:
        errors.append(label + " has start after end")
        return False, False, notes
    if when is not None and start is not None and when < start:
        return False, False, ["promotion has not started for the supplied opening date"]
    if when is not None and end is not None and when > end:
        return False, False, ["promotion has ended for the supplied opening date"]
    date_known = not ((start or end) and when is None)
    if not date_known:
        notes.append("requires application or account-opening date verification")
    needs_new = bool(item.get("requires_new_customer", False))
    if needs_new and new_customer is False:
        return False, False, ["not available because new-customer status is false"]
    if needs_new and new_customer is None:
        notes.append("requires new-customer eligibility verification")
    confirmed = date_known and (not needs_new or new_customer is True)
    possible = new_customer is not False
    return confirmed, possible, notes


def known_category(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip().lower()
    return value if value and value != "unknown" else None


def credit_capacity(card: dict[str, Any], purchase: Decimal, prefix: str,
                    errors: list[str]) -> tuple[str, list[str]]:
    low = dec(card["minimum_credit_limit"], prefix + ".minimum_credit_limit", errors) if "minimum_credit_limit" in card else None
    high = dec(card["maximum_credit_limit"], prefix + ".maximum_credit_limit", errors) if "maximum_credit_limit" in card else None
    notes = ["actual approval and available credit must cover the charge"]
    if low is not None and high is not None and low > high:
        errors.append(prefix + " has a minimum credit limit above its maximum")
    if high is not None and high < purchase:
        return "published maximum below planned purchase", notes
    if low is not None and low >= purchase:
        return "published minimum can cover purchase, subject to approval and available credit", notes
    if high is not None:
        return "requires an approved credit line of at least the planned purchase", notes
    return "credit-line range not supplied", notes


def usable_rate(card: dict[str, Any], category: str | None, default: Decimal,
                prefix: str, errors: list[str]) -> tuple[Decimal, str]:
    if category is None:
        return default, "default rate used because merchant category is unknown"
    rates = card.get("category_cash_back_rates", {})
    if not isinstance(rates, dict):
        errors.append(prefix + ".category_cash_back_rates must be an object")
        return default, "default rate used because category-rate data is invalid"
    if category not in rates:
        return default, "default rate used because no supplied bonus rate matches merchant category"
    rate = dec(rates[category], prefix + ".category_cash_back_rates." + category, errors)
    return (rate, "supplied category rate used for " + category) if rate is not None else (default, "default rate used because matching category rate is invalid")


def promo_categories_match(promo: dict[str, Any], category: str | None) -> bool:
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
    default = dec(card.get("default_cash_back_rate"), prefix + ".default_cash_back_rate", errors)
    fee = dec(card.get("annual_fee", 0), prefix + ".annual_fee", errors)
    if default is None or fee is None:
        return None
    rate, basis = usable_rate(card, category, default, prefix, errors)
    conditions: list[str] = []
    conditional_fee = fee
    conditional_multiplier = Decimal("1")
    conditional_offer = ZERO

    for field in ("fee_promotions", "rate_promotions", "spend_offers"):
        if field in card and not isinstance(card[field], list):
            errors.append(prefix + "." + field + " must be an array")

    for n, promo in enumerate(card.get("fee_promotions", []) if isinstance(card.get("fee_promotions", []), list) else []):
        if not isinstance(promo, dict):
            errors.append(prefix + f".fee_promotions[{n}] must be an object")
            continue
        waived_fee = dec(promo.get("fee"), prefix + f".fee_promotions[{n}].fee", errors)
        if waived_fee is None:
            continue
        confirmed, possible, notes = promotion_state(promo, when, new_customer, prefix + f".fee_promotions[{n}]", errors)
        if confirmed:
            conditional_fee = min(conditional_fee, waived_fee)
        elif possible:
            conditional_fee = min(conditional_fee, waived_fee)
            conditions.extend(notes + ["first-year fee promotion is conditional"])

    for n, promo in enumerate(card.get("rate_promotions", []) if isinstance(card.get("rate_promotions", []), list) else []):
        if not isinstance(promo, dict):
            errors.append(prefix + f".rate_promotions[{n}] must be an object")
            continue
        if not promo_categories_match(promo, category):
            if promo.get("eligible_categories") is not None and category is None:
                conditions.append("category-limited multiplier was not assumed because merchant category is unknown")
            continue
        multiplier = dec(promo.get("multiplier"), prefix + f".rate_promotions[{n}].multiplier", errors)
        if multiplier is None:
            continue
        confirmed, possible, notes = promotion_state(promo, when, new_customer, prefix + f".rate_promotions[{n}]", errors)
        if confirmed or possible:
            conditional_multiplier *= multiplier
            if not confirmed:
                conditions.extend(notes + ["rate multiplier is conditional"])

    for n, offer in enumerate(card.get("spend_offers", []) if isinstance(card.get("spend_offers", []), list) else []):
        if not isinstance(offer, dict):
            errors.append(prefix + f".spend_offers[{n}] must be an object")
            continue
        amount = dec(offer.get("amount"), prefix + f".spend_offers[{n}].amount", errors)
        threshold = dec(offer.get("threshold"), prefix + f".spend_offers[{n}].threshold", errors)
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
            conditions.extend(([] if confirmed else notes + ["spend offer is conditional"]) + [timing])

    status, capacity_notes = credit_capacity(card, purchase, prefix, errors)
    conditions.extend(capacity_notes)
    conditions.extend(["merchant coding and stated exclusions determine the final rate", "returns or credits can reduce rewards and qualifying spend"])
    default_reward = purchase * rate
    return {
        "name": name.strip(),
        "merchant_category_used": category,
        "rate_basis": basis,
        "rate_used": str(rate),
        "default_purchase_reward": dollars(default_reward),
        "standard_first_year_net": dollars(default_reward - fee),
        "conditional_first_year_net": dollars(purchase * rate * conditional_multiplier + conditional_offer - conditional_fee),
        "conditional_fee_used": dollars(conditional_fee),
        "credit_capacity": status,
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
    purchase = dec(payload.get("purchase_amount"), "purchase_amount", errors, Decimal("0.01"))
    cards = payload.get("cards")
    if not isinstance(cards, list):
        errors.append("cards must be an array")
        cards = []
    application = date_value(payload.get("application_date"), "application_date", errors)
    opening = date_value(payload.get("account_open_date"), "account_open_date", errors)
    new_customer = payload.get("is_new_customer")
    if new_customer is not None and not isinstance(new_customer, bool):
        errors.append("is_new_customer must be true, false, or null")
    category = known_category(payload.get("merchant_category"))
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
