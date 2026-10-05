#!/usr/bin/env python3
"""Compare supplied business-card terms for one planned purchase.

Reads one JSON object from stdin and writes one JSON object to stdout. This is
calculation-only code: it never accesses customer accounts or banking systems.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple

CENT = Decimal("0.01")
ZERO = Decimal("0")


def money(value: Decimal) -> str:
    return str(value.quantize(CENT, rounding=ROUND_HALF_UP))


def decimal_value(value: Any, field: str, errors: List[str], minimum: Optional[Decimal] = None) -> Optional[Decimal]:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        errors.append(f"{field} must be numeric")
        return None
    if not result.is_finite():
        errors.append(f"{field} must be finite")
        return None
    if minimum is not None and result < minimum:
        errors.append(f"{field} must be at least {minimum}")
        return None
    return result


def parse_date(value: Any, field: str, errors: List[str]) -> Optional[date]:
    if value is None:
        return None
    if not isinstance(value, str):
        errors.append(f"{field} must be YYYY-MM-DD when provided")
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        errors.append(f"{field} must be YYYY-MM-DD when provided")
        return None


def window_state(item: Dict[str, Any], when: Optional[date], prefix: str, errors: List[str]) -> str:
    """Return active, expired, future, or date_unknown for an inclusive window."""
    start = parse_date(item.get("start"), f"{prefix}.start", errors)
    end = parse_date(item.get("end"), f"{prefix}.end", errors)
    if start and end and start > end:
        errors.append(f"{prefix} has start after end")
        return "expired"
    if when is None and (start or end):
        return "date_unknown"
    if when is None:
        return "active"
    if start and when < start:
        return "future"
    if end and when > end:
        return "expired"
    return "active"


def customer_condition(item: Dict[str, Any], is_new_customer: Any) -> Tuple[bool, bool, List[str]]:
    """Return (confirmed, possible, notes) for the new-customer condition."""
    if not item.get("requires_new_customer", False):
        return True, True, []
    if is_new_customer is True:
        return True, True, []
    if is_new_customer is False:
        return False, False, ["not available because new-customer status is false"]
    return False, True, ["requires verification of new-customer eligibility"]


def promotion_availability(
    item: Dict[str, Any], when: Optional[date], is_new_customer: Any,
    prefix: str, errors: List[str],
) -> Tuple[bool, bool, List[str]]:
    state = window_state(item, when, prefix, errors)
    confirmed_customer, possible_customer, notes = customer_condition(item, is_new_customer)
    if state == "expired":
        return False, False, notes + ["promotion window has ended for the supplied date"]
    if state == "future":
        return False, False, notes + ["promotion window has not started for the supplied date"]
    if state == "date_unknown":
        return False, possible_customer, notes + ["requires account-opening/application date verification"]
    return confirmed_customer, possible_customer, notes


def known_category(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    return normalized if normalized and normalized != "unknown" else None


def credit_status(card: Dict[str, Any], purchase: Decimal, errors: List[str], path: str) -> Tuple[str, List[str]]:
    minimum = card.get("minimum_credit_limit")
    maximum = card.get("maximum_credit_limit")
    min_value = decimal_value(minimum, f"{path}.minimum_credit_limit", errors, ZERO) if minimum is not None else None
    max_value = decimal_value(maximum, f"{path}.maximum_credit_limit", errors, ZERO) if maximum is not None else None
    notes: List[str] = ["actual approval and available credit must cover the charge"]
    if min_value is not None and max_value is not None and min_value > max_value:
        errors.append(f"{path} has minimum_credit_limit greater than maximum_credit_limit")
    if max_value is not None and max_value < purchase:
        return "published maximum below planned purchase", notes
    if min_value is not None and min_value >= purchase:
        return "published minimum can cover purchase, subject to approval and available credit", notes
    if max_value is not None:
        return "requires approved credit line of at least planned purchase", notes
    return "credit-line range not supplied", notes


def category_rate(card: Dict[str, Any], category: Optional[str], default_rate: Decimal, errors: List[str], path: str) -> Tuple[Decimal, str]:
    if category is None:
        return default_rate, "default rate used because merchant category is unknown"
    rates = card.get("category_cash_back_rates", {})
    if not isinstance(rates, dict):
        errors.append(f"{path}.category_cash_back_rates must be an object")
        return default_rate, "default rate used because category rates are invalid"
    if category not in rates:
        return default_rate, "default rate used because no supplied enhanced rate matches merchant category"
    rate = decimal_value(rates[category], f"{path}.category_cash_back_rates.{category}", errors, ZERO)
    if rate is None:
        return default_rate, "default rate used because matching category rate is invalid"
    return rate, f"supplied enhanced rate used for category '{category}'"


def applies_to_category(item: Dict[str, Any], category: Optional[str]) -> bool:
    eligible = item.get("eligible_categories")
    if eligible is None:
        return True
    if not isinstance(eligible, list):
        return False
    if category is None:
        return False
    return category in [str(x).strip().lower() for x in eligible]


def compare_card(
    card: Dict[str, Any], purchase: Decimal, category: Optional[str], when: Optional[date],
    is_new_customer: Any, index: int, errors: List[str],
) -> Optional[Dict[str, Any]]:
    path = f"cards[{index}]"
    name = card.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append(f"{path}.name must be a nonempty string")
        return None
    default_rate = decimal_value(card.get("default_cash_back_rate"), f"{path}.default_cash_back_rate", errors, ZERO)
    if default_rate is None:
        return None
    base_rate, rate_basis = category_rate(card, category, default_rate, errors, path)
    annual_fee = decimal_value(card.get("annual_fee", 0), f"{path}.annual_fee", errors, ZERO)
    if annual_fee is None:
        return None

    conditions: List[str] = []
    confirmed_fee = annual_fee
    potential_fee = annual_fee
    fee_promos = card.get("first_year_fee_promotions", [])
    if not isinstance(fee_promos, list):
        errors.append(f"{path}.first_year_fee_promotions must be an array")
        fee_promos = []
    for promo_index, promo in enumerate(fee_promos):
        if not isinstance(promo, dict):
            errors.append(f"{path}.first_year_fee_promotions[{promo_index}] must be an object")
            continue
        fee = decimal_value(promo.get("fee"), f"{path}.first_year_fee_promotions[{promo_index}].fee", errors, ZERO)
        if fee is None:
            continue
        confirmed, possible, notes = promotion_availability(promo, when, is_new_customer, f"{path}.first_year_fee_promotions[{promo_index}]", errors)
        if confirmed:
            confirmed_fee = min(confirmed_fee, fee)
            potential_fee = min(potential_fee, fee)
        elif possible:
            potential_fee = min(potential_fee, fee)
            conditions.extend(notes + ["first-year fee promotion is conditional"])

    confirmed_multiplier = Decimal("1")
    potential_multiplier = Decimal("1")
    multiplier_promos = card.get("rate_multiplier_promotions", [])
    if not isinstance(multiplier_promos, list):
        errors.append(f"{path}.rate_multiplier_promotions must be an array")
        multiplier_promos = []
    for promo_index, promo in enumerate(multiplier_promos):
        if not isinstance(promo, dict):
            errors.append(f"{path}.rate_multiplier_promotions[{promo_index}] must be an object")
            continue
        multiplier = decimal_value(promo.get("multiplier"), f"{path}.rate_multiplier_promotions[{promo_index}].multiplier", errors, ZERO)
        if multiplier is None:
            continue
        if not applies_to_category(promo, category):
            if promo.get("eligible_categories") is not None and category is None:
                conditions.append("category-limited rate multiplier was not assumed because merchant category is unknown")
            continue
        confirmed, possible, notes = promotion_availability(promo, when, is_new_customer, f"{path}.rate_multiplier_promotions[{promo_index}]", errors)
        if confirmed:
            confirmed_multiplier *= multiplier
            potential_multiplier *= multiplier
        elif possible:
            potential_multiplier *= multiplier
            conditions.extend(notes + ["rate multiplier is conditional"])

    confirmed_bonus = ZERO
    potential_bonus = ZERO
    bonuses = card.get("spend_bonuses", [])
    if not isinstance(bonuses, list):
        errors.append(f"{path}.spend_bonuses must be an array")
        bonuses = []
    for bonus_index, bonus in enumerate(bonuses):
        if not isinstance(bonus, dict):
            errors.append(f"{path}.spend_bonuses[{bonus_index}] must be an object")
            continue
        amount = decimal_value(bonus.get("amount"), f"{path}.spend_bonuses[{bonus_index}].amount", errors, ZERO)
        threshold = decimal_value(bonus.get("spend_threshold"), f"{path}.spend_bonuses[{bonus_index}].spend_threshold", errors, ZERO)
        if amount is None or threshold is None:
            continue
        if purchase < threshold:
            continue
        confirmed, possible, notes = promotion_availability(bonus, when, is_new_customer, f"{path}.spend_bonuses[{bonus_index}]", errors)
        posting_required = bonus.get("requires_posting", False)
        period = bonus.get("period_months")
        timing_note = ""
        if posting_required:
            timing_note = "qualifying transactions must post"
        if period is not None:
            timing_note = (timing_note + "; " if timing_note else "") + f"qualifying net spend must occur within {period} month(s)"
        if confirmed:
            # A purchase amount alone cannot prove that it will remain net and post on time.
            potential_bonus += amount
            conditions.append("sign-up bonus requires net qualifying spend" + (f"; {timing_note}" if timing_note else ""))
        elif possible:
            potential_bonus += amount
            conditions.extend(notes + ["sign-up bonus is conditional on net qualifying spend" + (f"; {timing_note}" if timing_note else "")])

    standard_reward = purchase * base_rate
    confirmed_net = purchase * base_rate * confirmed_multiplier + confirmed_bonus - confirmed_fee
    potential_net = purchase * base_rate * potential_multiplier + potential_bonus - potential_fee
    status, credit_notes = credit_status(card, purchase, errors, path)
    conditions.extend(credit_notes)
    conditions.append("merchant category and stated exclusions determine the final applicable rate")
    conditions.append("returns or credits can reduce net qualifying purchases and rewards")

    result: Dict[str, Any] = {
        "name": name.strip(),
        "merchant_category_used": category,
        "rate_basis": rate_basis,
        "base_cash_back_rate": str(base_rate),
        "standard_purchase_reward": money(standard_reward),
        "standard_first_year_net": money(standard_reward - annual_fee),
        "potential_first_year_net": money(potential_net),
        "first_year_fee_used_in_potential": money(potential_fee),
        "credit_capacity": status,
        "conditions": list(dict.fromkeys(conditions)),
    }
    if card.get("eligibility_notes") is not None:
        result["eligibility_notes"] = card["eligibility_notes"]
    if card.get("terms") is not None:
        result["terms"] = card["terms"]
    return result


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "errors": [f"invalid JSON: {exc.msg}"], "results": []}))
        return
    if not isinstance(payload, dict):
        print(json.dumps({"ok": False, "errors": ["top-level JSON must be an object"], "results": []}))
        return

    errors: List[str] = []
    purchase = decimal_value(payload.get("purchase_amount"), "purchase_amount", errors, Decimal("0.01"))
    cards = payload.get("cards")
    if not isinstance(cards, list):
        errors.append("cards must be an array")
        cards = []
    application_date = parse_date(payload.get("application_date"), "application_date", errors)
    opening_date = parse_date(payload.get("account_open_date"), "account_open_date", errors)
    when = opening_date or application_date
    is_new_customer = payload.get("is_new_customer")
    if is_new_customer is not None and not isinstance(is_new_customer, bool):
        errors.append("is_new_customer must be true, false, or null")
    category = known_category(payload.get("merchant_category"))

    results: List[Dict[str, Any]] = []
    if purchase is not None:
        for index, card in enumerate(cards):
            if not isinstance(card, dict):
                errors.append(f"cards[{index}] must be an object")
                continue
            result = compare_card(card, purchase, category, when, is_new_customer, index, errors)
            if result is not None:
                results.append(result)

    def net_for(item: Dict[str, Any], field: str) -> Decimal:
        return Decimal(item[field])

    standard_ranking = [item["name"] for item in sorted(results, key=lambda x: net_for(x, "standard_first_year_net"), reverse=True)]
    potential_ranking = [item["name"] for item in sorted(results, key=lambda x: net_for(x, "potential_first_year_net"), reverse=True)]
    output = {
        "ok": not errors,
        "errors": errors,
        "assumptions": {
            "merchant_category": category,
            "promotion_date_used": when.isoformat() if when else None,
            "new_customer_status": is_new_customer,
            "calculation_scope": "one planned net purchase and one first-year annual fee; no approval or merchant coding is assumed",
        },
        "results": results,
        "standard_ranking": standard_ranking,
        "potential_ranking": potential_ranking,
    }
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
