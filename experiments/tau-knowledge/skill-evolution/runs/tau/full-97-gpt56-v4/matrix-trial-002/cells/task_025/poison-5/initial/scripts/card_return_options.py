#!/usr/bin/env python3
"""Calculate documented conditional cash-back scenarios for business cards.

Input JSON schema:
{
  "purchase_amount": "100000.00",            # required, positive USD amount
  "merchant_category": "unknown",             # optional: travel, software,
                                                  # media_advertising, operations, unknown
  "directly_billed": true,                      # optional boolean
  "current_date": "2025-11-14",                # optional ISO date
  "open_date": "2025-11-14",                   # optional ISO date
  "personal_credit_score": 740,                 # optional numeric
  "business_paydex": 70                         # optional numeric
}

Output JSON contains only documented calculations and conditional flags. It never
claims approval, merchant classification, or promotional eligibility.
"""

import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENTS = Decimal("0.01")
SUPPORTED_CATEGORIES = {"travel", "software", "media_advertising", "operations", "unknown"}

CARDS = (
    {
        "name": "Business Silver Rewards",
        "line_min": Decimal("17500"), "line_max": Decimal("112500"),
        "base_rate": Decimal("0.01"), "bonus_rate": Decimal("0.10"),
        "bonus_categories": {"travel", "software"},
        "personal_min": 700, "paydex_min": 47,
        "annual_fee": None,
        "promotion": {
            "name": "new-customer double cash back",
            "start": date(2024, 11, 14), "end": date(2025, 11, 14),
            "multiplier": Decimal("2"),
            "duration": "first 6 months after account opening",
        },
    },
    {
        "name": "Business Gold Rewards",
        "line_min": Decimal("37500"), "line_max": Decimal("225000"),
        "base_rate": Decimal("0.01"), "bonus_rate": Decimal("0.025"),
        "bonus_categories": {"operations"},
        "personal_min": 735, "paydex_min": 67,
        "annual_fee": Decimal("200"), "promotion": None,
    },
    {
        "name": "Business Platinum Rewards",
        "line_min": Decimal("75000"), "line_max": Decimal("400000"),
        "base_rate": Decimal("0.015"), "bonus_rate": Decimal("0.04"),
        "bonus_categories": {"travel", "software", "media_advertising"},
        "personal_min": 765, "paydex_min": 77,
        "annual_fee": Decimal("450"),
        "fee_waiver": {
            "start": date(2025, 11, 1), "end": date(2026, 2, 28),
            "description": "first-year annual fee waived for new accounts opened in this window",
        },
        "promotion": None,
    },
)


def money(value: Decimal) -> str:
    return format(value.quantize(CENTS, rounding=ROUND_HALF_UP), ".2f")


def parse_date(value, field):
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO date string")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be YYYY-MM-DD") from exc


def rate_result(amount, rate):
    return {"rate_percent": str(rate * 100), "cash_back_usd": money(amount * rate)}


def threshold_status(value, required):
    if value is None:
        return "not_provided"
    try:
        numeric = Decimal(str(value))
    except InvalidOperation:
        return "invalid"
    return "meets_published_threshold" if numeric >= required else "below_published_threshold"


def window_status(open_date, window):
    if open_date is None:
        return "unknown_open_date"
    return "within_window" if window["start"] <= open_date <= window["end"] else "outside_window"


def card_output(card, amount, category, open_date, personal_score, paydex):
    possibly_fundable = amount <= card["line_max"]
    known_qualifies = category in card["bonus_categories"]
    known_nonqualifies = category != "unknown" and not known_qualifies
    base = rate_result(amount, card["base_rate"])
    enhanced = rate_result(amount, card["bonus_rate"])

    if known_qualifies:
        category_scenarios = {"documented_category_result": enhanced}
    elif known_nonqualifies:
        category_scenarios = {"documented_category_result": base}
    else:
        category_scenarios = {
            "if_merchant_is_submitted_in_a_bonus_category": enhanced,
            "if_merchant_is_not_submitted_in_a_bonus_category": base,
        }

    result = {
        "card": card["name"],
        "published_credit_line_usd": {"minimum": money(card["line_min"]), "maximum": money(card["line_max"])},
        "line_capacity_possible": possibly_fundable,
        "line_capacity_note": (
            "Published maximum can cover the requested amount, but underwriting must approve a sufficient line."
            if possibly_fundable else
            "Requested amount exceeds the published maximum credit line for this card."
        ),
        "category_scenarios": category_scenarios,
        "preliminary_published_thresholds": {
            "minimum_personal_credit_score": card["personal_min"],
            "minimum_established_business_paydex": card["paydex_min"],
            "personal_score_status": threshold_status(personal_score, card["personal_min"]),
            "paydex_status": threshold_status(paydex, card["paydex_min"]),
            "note": "Threshold comparison is not an approval decision; PAYDEX criteria apply to established businesses.",
        },
    }
    if card["annual_fee"] is not None:
        result["documented_annual_fee_usd"] = money(card["annual_fee"])
    if "fee_waiver" in card:
        waiver = card["fee_waiver"]
        result["first_year_fee_waiver"] = {
            "status": window_status(open_date, waiver),
            "window": {"start": waiver["start"].isoformat(), "end": waiver["end"].isoformat()},
            "description": waiver["description"],
        }
    if card["promotion"]:
        promo = card["promotion"]
        status = window_status(open_date, promo)
        promo_result = {
            "status": status,
            "window": {"start": promo["start"].isoformat(), "end": promo["end"].isoformat()},
            "description": f"Rates are doubled for the {promo['duration']} when the account is opened in the stated window.",
        }
        if status == "within_window":
            promo_result["if_bonus_category_cash_back_usd"] = money(amount * card["bonus_rate"] * promo["multiplier"])
            promo_result["if_nonbonus_category_cash_back_usd"] = money(amount * card["base_rate"] * promo["multiplier"])
        result["promotion"] = promo_result
    return result


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        try:
            amount = Decimal(str(payload["purchase_amount"]))
        except (KeyError, InvalidOperation, ValueError) as exc:
            raise ValueError("purchase_amount is required and must be a decimal number") from exc
        if not amount.is_finite() or amount <= 0:
            raise ValueError("purchase_amount must be positive")
        category = payload.get("merchant_category", "unknown")
        if category not in SUPPORTED_CATEGORIES:
            raise ValueError("merchant_category must be travel, software, media_advertising, operations, or unknown")
        open_date = parse_date(payload.get("open_date"), "open_date")
        current_date = parse_date(payload.get("current_date"), "current_date")
        output = {
            "purchase_amount_usd": money(amount),
            "merchant_category_input": category,
            "directly_billed": payload.get("directly_billed"),
            "classification_note": "Direct billing may support a qualification review but does not determine the merchant category or reward rate.",
            "calculation_date": current_date.isoformat() if current_date else None,
            "results": [card_output(card, amount, category, open_date, payload.get("personal_credit_score"), payload.get("business_paydex")) for card in CARDS],
            "limitations": [
                "Rewards depend on the merchant category submitted by the merchant/payment processor.",
                "All returns are conditional; no result guarantees approval, available credit, promotion eligibility, or reward posting.",
                "Cash-back values are stated in dollars; system-stored points for these cash-back cards convert at 1 point = $0.01.",
            ],
        }
        print(json.dumps(output, sort_keys=True))
    except ValueError as error:
        print(json.dumps({"error": str(error)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
