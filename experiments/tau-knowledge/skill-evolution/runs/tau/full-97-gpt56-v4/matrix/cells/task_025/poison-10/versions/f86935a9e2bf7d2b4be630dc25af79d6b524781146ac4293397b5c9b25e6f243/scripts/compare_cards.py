#!/usr/bin/env python3
"""Compare published business-card reward treatment for one proposed charge.

Reads one JSON object from stdin and writes one JSON object to stdout.  It makes no
banking changes and uses no network or system time; all time-sensitive decisions use
the supplied as_of date.
"""
import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")


def money(value):
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def parse_date(value, field):
    if not isinstance(value, str):
        raise ValueError(field + " must be YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError(field + " must be YYYY-MM-DD")


def add_months(day, months):
    """Calendar-month addition without nonstandard dependencies."""
    month_index = day.month - 1 + months
    year = day.year + month_index // 12
    month = month_index % 12 + 1
    # first day of following month minus a day gives target month's length
    if month == 12:
        next_month = date(year + 1, 1, 1)
    else:
        next_month = date(year, month + 1, 1)
    last_day = (next_month - date.resolution).day
    return date(year, month, min(day.day, last_day))


def in_inclusive_window(day, start, end):
    return start <= day <= end


def normalized_text(*parts):
    return " ".join(str(x or "").casefold() for x in parts)


def is_apple_merchant(merchant, description):
    """Known exclusion applies to Apple-billed Apple/Apple Music charges.

    This does not attempt to guess a merchant category; it recognizes the named
    merchant for the sole purpose of the published Silver exclusion.
    """
    text = normalized_text(merchant, description)
    return "apple music" in text or text.strip().startswith("apple")


def reward(amount, rate):
    return amount * rate / Decimal("100")


def card_result(name, maximum, rate, amount, rationale, fee, qualification,
                conditional_bonus=None):
    can_cover = maximum >= amount
    return {
        "card": name,
        "published_maximum_credit_line": money(maximum),
        "max_line_can_cover_single_charge": can_cover,
        "known_rate_percent": format(rate, "f"),
        "known_cash_back": money(reward(amount, rate)),
        "rationale": rationale,
        "annual_fee_note": fee,
        "qualification_note": qualification,
        "conditional_bonus": conditional_bonus,
    }


def main(payload):
    try:
        amount = Decimal(str(payload.get("purchase_amount")))
    except (InvalidOperation, ValueError):
        raise ValueError("purchase_amount must be a decimal number")
    if not amount.is_finite() or amount <= 0:
        raise ValueError("purchase_amount must be greater than zero")

    as_of = parse_date(payload.get("as_of"), "as_of")
    merchant = payload.get("merchant_name", "")
    description = payload.get("purchase_description", "")
    category = str(payload.get("merchant_category", "other")).casefold().strip()
    valid_categories = {"travel", "software", "media_advertising", "operations", "other"}
    if category not in valid_categories:
        raise ValueError("merchant_category must be travel, software, media_advertising, operations, or other")
    new_customer = payload.get("is_new_customer") is True
    opening_raw = payload.get("account_open_date")
    opening = parse_date(opening_raw, "account_open_date") if opening_raw else None
    if opening and opening > as_of:
        raise ValueError("account_open_date cannot be after as_of")

    apple = is_apple_merchant(merchant, description)
    limitations = []
    if category == "other":
        limitations.append("No qualifying merchant category was confirmed; category-based bonus rates are not guaranteed.")
    if not merchant:
        limitations.append("No billing merchant was supplied; named merchant exclusions cannot be fully checked.")

    # Silver: named Apple exclusion overrides even a supplied software category.
    silver_promo = False
    if new_customer and opening:
        silver_promo = (in_inclusive_window(opening, date(2024, 11, 14), date(2025, 11, 14))
                        and as_of < add_months(opening, 6))
    elif new_customer:
        limitations.append("Silver promotion cannot be determined without account_open_date.")
    silver_base = Decimal("1") if apple or category not in {"travel", "software"} else Decimal("10")
    silver_rate = silver_base * (Decimal("2") if silver_promo else Decimal("1"))
    if apple:
        silver_reason = "Apple is a named Silver hardware/electronics exclusion, so the standard rate applies; exclusions continue during the double-cash-back offer."
    elif category in {"travel", "software"}:
        silver_reason = "Confirmed qualifying Silver category."
    else:
        silver_reason = "Standard Silver rate because a qualifying travel/software category was not confirmed."
    if silver_promo:
        silver_reason += " The qualifying new-account double-cash-back period is active."
    silver_fee = "$122.50 standard annual fee; a separate new-customer waiver offer is stated for accounts opened 2025-11-15 through 2026-01-15."

    platinum_enhanced = category in {"travel", "software", "media_advertising"}
    platinum_rate = Decimal("4") if platinum_enhanced else Decimal("1.5")
    platinum_conditional = None
    if not platinum_enhanced:
        platinum_conditional = {
            "if": "The actual merchant category is confirmed as travel, software, or media advertising",
            "rate_percent": "4",
            "cash_back": money(reward(amount, Decimal("4"))),
            "note": "A streaming subscription is not automatically media advertising."
        }
    platinum_fee = "$450 standard annual fee; first-year fee is $0 for a qualifying new account opened 2025-11-01 through 2026-02-28."

    gold_operations = category == "operations"
    gold_rate = Decimal("2.5") if gold_operations else Decimal("1")
    gold_conditional = None
    if not gold_operations:
        gold_conditional = {
            "if": "The actual merchant category is confirmed as operations",
            "rate_percent": "2.5",
            "cash_back": money(reward(amount, Decimal("2.5"))),
        }

    cards = [
        card_result("Business Silver Rewards Card", Decimal("112500"), silver_rate, amount,
                    silver_reason, silver_fee,
                    "Published minimum FICO 700; established-business PAYDEX 47.", None),
        card_result("Business Platinum Rewards Card", Decimal("400000"), platinum_rate, amount,
                    "4% only for confirmed travel, software, or media-advertising coding; otherwise 1.5%.",
                    platinum_fee, "Published minimum personal credit 765 and PAYDEX 77.", platinum_conditional),
        card_result("Business Gold Rewards Card", Decimal("225000"), gold_rate, amount,
                    "2.5% only for confirmed operations coding; otherwise 1%.", "$200 annual fee.",
                    "Published minimum FICO 735 and PAYDEX 67.", gold_conditional),
        card_result("Business Bronze Rewards Card", Decimal("50000"), Decimal("1"), amount,
                    "1% on eligible purchases.", "$0 annual fee.",
                    "Published minimum FICO 660; PAYDEX 20 may be considered.", None),
    ]
    capacity = [c for c in cards if c["max_line_can_cover_single_charge"]]
    capacity.sort(key=lambda c: Decimal(c["known_cash_back"]), reverse=True)
    non_capacity = [c["card"] for c in cards if not c["max_line_can_cover_single_charge"]]
    if non_capacity:
        limitations.append("Published maximum line is below this one-charge amount for: " + ", ".join(non_capacity) + ".")

    return {
        "purchase_amount": money(amount),
        "as_of": as_of.isoformat(),
        "assumptions": {
            "merchant_name": merchant or None,
            "purchase_description": description or None,
            "confirmed_merchant_category": category,
            "new_customer": new_customer,
            "account_open_date": opening.isoformat() if opening else None,
            "apple_named_silver_exclusion_applied": apple,
        },
        "cards": cards,
        "ranked_capacity_options": capacity,
        "limitations": limitations,
        "disclaimer": "Published maximum credit line and reward treatment do not guarantee approval, assigned line, merchant coding, or transaction acceptance."
    }


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        if not isinstance(raw, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(raw), separators=(",", ":")))
    except (ValueError, TypeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
