#!/usr/bin/env python3
"""Deterministic comparison of supplied business-card terms.

Reads one JSON object from stdin and writes one JSON object to stdout. It performs
no network, account, application, or payment action.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")


def decimal_value(value, field, allow_none=False):
    if value is None and allow_none:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a decimal, not boolean")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be a decimal")
    if not number.is_finite():
        raise ValueError(f"{field} must be finite")
    return number


def money(value):
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def normalized(value):
    return str(value).strip().casefold()


def error(message):
    print(json.dumps({"ok": False, "error": message}, sort_keys=True))
    raise SystemExit(0)


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
    category = normalized(purchase.get("category", ""))
    if not category:
        raise ValueError("purchase.category is required")
    merchant = normalized(purchase.get("merchant", ""))
    point_value = decimal_value(
        purchase.get("cash_back_point_value"),
        "purchase.cash_back_point_value",
        allow_none=True,
    )
    if point_value is not None and point_value <= 0:
        raise ValueError("purchase.cash_back_point_value must be greater than zero")

    results = []
    for index, card in enumerate(cards):
        if not isinstance(card, dict):
            raise ValueError(f"cards[{index}] must be an object")
        name = str(card.get("name", "")).strip()
        if not name:
            raise ValueError(f"cards[{index}].name is required")
        rates = card.get("rates")
        if not isinstance(rates, dict):
            raise ValueError(f"cards[{index}].rates must be an object")
        normalized_rates = {normalized(key): value for key, value in rates.items()}
        overrides = card.get("merchant_overrides", {})
        if not isinstance(overrides, dict):
            raise ValueError(f"cards[{index}].merchant_overrides must be an object")
        normalized_overrides = {normalized(key): value for key, value in overrides.items()}
        exclusions = card.get("excluded_merchants", [])
        if not isinstance(exclusions, list):
            raise ValueError(f"cards[{index}].excluded_merchants must be an array")
        excluded = merchant and merchant in {normalized(item) for item in exclusions}

        if excluded:
            raw_rate = card.get("excluded_merchant_rate", "0")
            rate_source = "documented merchant exclusion"
        elif merchant and merchant in normalized_overrides:
            raw_rate = normalized_overrides[merchant]
            rate_source = "documented merchant override"
        elif category in normalized_rates:
            raw_rate = normalized_rates[category]
            rate_source = f"documented {category} category rate"
        elif "default" in normalized_rates:
            raw_rate = normalized_rates["default"]
            rate_source = "documented default rate"
        else:
            raise ValueError(
                f"cards[{index}] has neither a rate for {category!r} nor a default rate"
            )
        rate = decimal_value(raw_rate, f"cards[{index}] selected rate")
        if rate < 0:
            raise ValueError(f"cards[{index}] selected rate cannot be negative")

        limit = card.get("limit", {})
        if not isinstance(limit, dict):
            raise ValueError(f"cards[{index}].limit must be an object")
        maximum = decimal_value(limit.get("maximum"), f"cards[{index}].limit.maximum", True)
        if maximum is not None and maximum < 0:
            raise ValueError(f"cards[{index}].limit.maximum cannot be negative")
        if maximum is None:
            capacity = "unknown"
            capacity_note = "No documented maximum line was supplied; standalone capacity is unconfirmed."
            capacity_rank = 1
        elif maximum < amount:
            capacity = "no"
            capacity_note = "Documented maximum line is below the single purchase amount."
            capacity_rank = 2
        else:
            capacity = "potentially"
            capacity_note = (
                "Requires approval for at least the purchase amount and sufficient available credit "
                "when the charge is authorized."
            )
            capacity_rank = 0

        rewards = (amount * rate).quantize(CENT, rounding=ROUND_HALF_UP)
        fees = card.get("fees", {})
        if not isinstance(fees, dict):
            raise ValueError(f"cards[{index}].fees must be an object")
        verified_first_year = decimal_value(
            fees.get("verified_first_year"),
            f"cards[{index}].fees.verified_first_year",
            True,
        )
        annual = decimal_value(fees.get("annual"), f"cards[{index}].fees.annual", True)
        result = {
            "name": name,
            "rate": str(rate),
            "rate_source": rate_source,
            "gross_cash_back": money(rewards),
            "capacity_for_single_purchase": capacity,
            "capacity_note": capacity_note,
            "mcc_condition": bool(card.get("requires_eligible_mcc", False)) and not excluded,
        }
        if point_value is not None:
            points = (rewards / point_value).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            result["cash_back_database_points"] = str(points)
        if verified_first_year is not None:
            result["verified_first_year_fee"] = money(verified_first_year)
            result["first_year_net_after_fee"] = money(rewards - verified_first_year)
        else:
            result["verified_first_year_fee"] = None
            result["first_year_net_after_fee"] = None
        result["standard_annual_fee"] = money(annual) if annual is not None else None
        results.append((capacity_rank, -rewards, name.casefold(), result))

    results.sort(key=lambda item: (item[0], item[1], item[2]))
    return {
        "ok": True,
        "purchase_amount": money(amount),
        "purchase_category": category,
        "results": [item[3] for item in results],
    }


if __name__ == "__main__":
    try:
        raw = sys.stdin.read()
        main_payload = json.loads(raw)
        print(json.dumps(main(main_payload), sort_keys=True))
    except json.JSONDecodeError:
        error("stdin must contain valid JSON")
    except ValueError as exc:
        error(str(exc))
