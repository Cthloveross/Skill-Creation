#!/usr/bin/env python3
"""Compare supplied business-card terms for one large purchase.

Reads one JSON object from stdin and writes one JSON object to stdout. This script
performs arithmetic only; it does not access accounts, apply for credit, transfer a
customer, make a payment, or retrieve card terms.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")


def fail(message):
    print(json.dumps({"ok": False, "error": message}, sort_keys=True))
    raise SystemExit(0)


def decimal_value(value, field, allow_none=False):
    if value is None and allow_none:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a decimal, not boolean")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be a decimal")
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result


def money(value):
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def normalize(value):
    return " ".join(str(value).strip().casefold().split())


def merchant_matches(merchant, documented_name):
    """Match an exact billed name or a documented brand followed by a word boundary.

    The latter permits a documented brand-level exclusion to cover a branded service
    name. Callers must only provide brand names where supplied terms support that
    scope; this function does not infer exclusions.
    """
    merchant = normalize(merchant)
    documented_name = normalize(documented_name)
    if not merchant or not documented_name:
        return False
    return merchant == documented_name or merchant.startswith(documented_name + " ")


def select_rate(card, category, merchant, index):
    rates = card.get("rates")
    if not isinstance(rates, dict):
        raise ValueError(f"cards[{index}].rates must be an object")
    normalized_rates = {normalize(key): value for key, value in rates.items()}
    exclusions = card.get("excluded_merchants", [])
    if not isinstance(exclusions, list):
        raise ValueError(f"cards[{index}].excluded_merchants must be an array")

    matched_exclusion = next(
        (str(item) for item in exclusions if merchant_matches(merchant, item)), None
    )
    if matched_exclusion is not None:
        return card.get("excluded_merchant_rate", "0"), "documented merchant exclusion", matched_exclusion

    overrides = card.get("merchant_overrides", {})
    if not isinstance(overrides, dict):
        raise ValueError(f"cards[{index}].merchant_overrides must be an object")
    for merchant_name, value in overrides.items():
        if merchant_matches(merchant, merchant_name):
            return value, "documented merchant override", None

    if category in normalized_rates:
        return normalized_rates[category], f"documented {category} category rate", None
    if "default" in normalized_rates:
        return normalized_rates["default"], "documented default rate", None
    raise ValueError(
        f"cards[{index}] has neither a rate for {category!r} nor a default rate"
    )


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("top-level input must be an object")
    purchase = payload.get("purchase")
    cards = payload.get("cards")
    if not isinstance(purchase, dict):
        raise ValueError("purchase must be an object")
    if not isinstance(cards, list) or not cards:
        raise ValueError("cards must be a nonempty array")

    amount = decimal_value(purchase.get("amount"), "purchase.amount")
    if amount <= 0:
        raise ValueError("purchase.amount must be greater than zero")
    category = normalize(purchase.get("category", ""))
    merchant = normalize(purchase.get("merchant", ""))
    if not category or not merchant:
        raise ValueError("purchase.category and purchase.merchant are required")
    point_value = decimal_value(
        purchase.get("cash_back_point_value"), "purchase.cash_back_point_value", True
    )
    if point_value is not None and point_value <= 0:
        raise ValueError("purchase.cash_back_point_value must be greater than zero")

    sortable_results = []
    for index, card in enumerate(cards):
        if not isinstance(card, dict):
            raise ValueError(f"cards[{index}] must be an object")
        name = str(card.get("name", "")).strip()
        if not name:
            raise ValueError(f"cards[{index}].name is required")
        raw_rate, source, excluded_name = select_rate(card, category, merchant, index)
        rate = decimal_value(raw_rate, f"cards[{index}] selected rate")
        if rate < 0 or rate > 1:
            raise ValueError(f"cards[{index}] selected rate must be between 0 and 1")

        limit = card.get("limit", {})
        if not isinstance(limit, dict):
            raise ValueError(f"cards[{index}].limit must be an object")
        minimum = decimal_value(limit.get("minimum"), f"cards[{index}].limit.minimum", True)
        maximum = decimal_value(limit.get("maximum"), f"cards[{index}].limit.maximum", True)
        if minimum is not None and minimum < 0:
            raise ValueError(f"cards[{index}].limit.minimum cannot be negative")
        if maximum is not None and maximum < 0:
            raise ValueError(f"cards[{index}].limit.maximum cannot be negative")
        if minimum is not None and maximum is not None and minimum > maximum:
            raise ValueError(f"cards[{index}].limit.minimum cannot exceed maximum")

        if maximum is None:
            capacity, capacity_rank = "unknown", 1
            capacity_note = "No documented maximum line was supplied; standalone capacity is unconfirmed."
        elif maximum < amount:
            capacity, capacity_rank = "no", 2
            capacity_note = "Documented maximum line is below the full single purchase amount."
        else:
            capacity, capacity_rank = "potentially", 0
            capacity_note = (
                "Requires approval for at least the purchase amount and sufficient available "
                "credit when the charge is authorized."
            )

        fees = card.get("fees", {})
        if not isinstance(fees, dict):
            raise ValueError(f"cards[{index}].fees must be an object")
        annual = decimal_value(fees.get("annual"), f"cards[{index}].fees.annual", True)
        verified_first_year = decimal_value(
            fees.get("verified_first_year"),
            f"cards[{index}].fees.verified_first_year",
            True,
        )
        if annual is not None and annual < 0:
            raise ValueError(f"cards[{index}].fees.annual cannot be negative")
        if verified_first_year is not None and verified_first_year < 0:
            raise ValueError(f"cards[{index}].fees.verified_first_year cannot be negative")

        cash_back = (amount * rate).quantize(CENT, rounding=ROUND_HALF_UP)
        result = {
            "name": name,
            "rate": str(rate),
            "rate_percent": str((rate * 100).normalize()),
            "rate_source": source,
            "gross_cash_back": money(cash_back),
            "capacity_for_single_purchase": capacity,
            "capacity_note": capacity_note,
            "documented_limit_minimum": money(minimum) if minimum is not None else None,
            "documented_limit_maximum": money(maximum) if maximum is not None else None,
            "mcc_condition": bool(card.get("requires_eligible_mcc", False)) and excluded_name is None,
            "matched_merchant_exclusion": excluded_name,
            "standard_annual_fee": money(annual) if annual is not None else None,
            "verified_first_year_fee": (
                money(verified_first_year) if verified_first_year is not None else None
            ),
            "first_year_net_after_fee": (
                money(cash_back - verified_first_year)
                if verified_first_year is not None
                else None
            ),
        }
        if point_value is not None:
            result["cash_back_database_points"] = str(
                (cash_back / point_value).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            )
        sortable_results.append((capacity_rank, -cash_back, name.casefold(), result))

    sortable_results.sort(key=lambda item: (item[0], item[1], item[2]))
    return {
        "ok": True,
        "purchase_amount": money(amount),
        "purchase_category": category,
        "purchase_merchant": merchant,
        "results": [item[3] for item in sortable_results],
    }


if __name__ == "__main__":
    try:
        main_payload = json.loads(sys.stdin.read())
        print(json.dumps(main(main_payload), sort_keys=True))
    except json.JSONDecodeError:
        fail("stdin must contain valid JSON")
    except ValueError as exc:
        fail(str(exc))
