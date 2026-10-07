#!/usr/bin/env python3
"""Compare Business Silver, Gold, and Platinum rewards for one planned charge.
Reads one JSON object from stdin and writes one JSON object to stdout.
"""
import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CARDS = {
    "Business Platinum Rewards Card": {
        "personal_min": 765, "paydex_min": 77, "min_limit": Decimal("75000"),
        "max_limit": Decimal("400000"), "base_rate": Decimal("0.015"),
        "bonus_rate": Decimal("0.04"), "bonus_categories": {"travel", "software", "media", "advertising"},
        "annual_fee": Decimal("450"),
    },
    "Business Silver Rewards Card": {
        "personal_min": 700, "paydex_min": 47, "min_limit": Decimal("17500"),
        "max_limit": Decimal("112500"), "base_rate": Decimal("0.01"),
        "bonus_rate": Decimal("0.10"), "bonus_categories": {"travel", "software"},
        "annual_fee": Decimal("122.50"),
    },
    "Business Gold Rewards Card": {
        "personal_min": 735, "paydex_min": 67, "min_limit": Decimal("37500"),
        "max_limit": Decimal("225000"), "base_rate": Decimal("0.01"),
        "bonus_rate": Decimal("0.025"), "bonus_categories": {"operations"},
        "annual_fee": Decimal("200"),
    },
}


def money(value):
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def rate_text(rate):
    return format((rate * 100).quantize(Decimal("0.1")), "f") + "%"


def reward(amount, rate):
    cash = money(amount * rate)
    return {"rate_percent": rate_text(rate), "cash_back_dollars": format(cash, ".2f"),
            "stored_reward_points": int(cash * 100)}


def normalized(value):
    return str(value or "").strip().casefold()


def eligibility(card, applicant):
    score = applicant.get("personal_credit_score")
    paydex = applicant.get("business_paydex")
    established = applicant.get("established_business")
    notes = []
    status = "unknown"
    if score is not None:
        try:
            if Decimal(str(score)) < card["personal_min"]:
                status = "below_stated_requirement"
                notes.append("The supplied personal score is below the published minimum.")
            else:
                notes.append("The supplied personal score meets the published minimum.")
        except InvalidOperation:
            notes.append("Personal score was not numeric, so it was not assessed.")
    else:
        notes.append("Personal score was not supplied.")
    if established is True:
        if paydex is None:
            notes.append("PAYDEX was not supplied for an established business.")
        else:
            try:
                if Decimal(str(paydex)) < card["paydex_min"]:
                    status = "below_stated_requirement"
                    notes.append("The supplied PAYDEX is below the published minimum for an established business.")
                else:
                    notes.append("The supplied PAYDEX meets the published minimum.")
            except InvalidOperation:
                notes.append("PAYDEX was not numeric, so it was not assessed.")
    elif established is None:
        notes.append("Whether the business is established was not supplied; PAYDEX treatment cannot be fully assessed.")
    if status != "below_stated_requirement" and score is not None and (established is not True or paydex is not None):
        status = "meets_stated_minimums_based_on_supplied_data"
    return {"status": status, "personal_score_minimum": card["personal_min"],
            "established_business_paydex_minimum": card["paydex_min"], "notes": notes,
            "approval_disclaimer": "Published criteria do not guarantee approval or a particular credit line."}


def category_result(name, card, amount, category, apple_direct):
    # Apple is an express Business Silver exception; do not award its software rate.
    if name == "Business Silver Rewards Card" and apple_direct:
        return {"status": "confirmed_standard_rate_due_to_Apple_exclusion",
                "reason": "Direct Apple/Apple Music billing is expressly excluded from the Business Silver software bonus.",
                "rewards": reward(amount, card["base_rate"])}
    if category:
        if category in card["bonus_categories"]:
            return {"status": "confirmed_if_processor_category_is_accurate",
                    "reason": "The supplied processor category is a published bonus category.",
                    "rewards": reward(amount, card["bonus_rate"])}
        return {"status": "confirmed_standard_rate_if_processor_category_is_accurate",
                "reason": "The supplied processor category is not a published bonus category.",
                "rewards": reward(amount, card["base_rate"])}
    result = {"status": "category_unconfirmed", "reason": "The merchant category/MCC was not supplied.",
              "standard_case": reward(amount, card["base_rate"]),
              "possible_bonus_categories": sorted(card["bonus_categories"]),
              "possible_bonus_case": reward(amount, card["bonus_rate"])}
    return result


def promotion(as_of):
    if not as_of:
        return {"status": "date_not_supplied", "detail": "Business Platinum has a published new-customer first-year fee waiver from 2025-11-01 through 2026-02-28."}
    try:
        checked = date.fromisoformat(as_of)
    except ValueError:
        return {"status": "invalid_date", "detail": "as_of must use YYYY-MM-DD."}
    start, end = date(2025, 11, 1), date(2026, 2, 28)
    if start <= checked <= end:
        return {"status": "within_published_window", "detail": "For eligible new customers opening an account in the window, the first-year Business Platinum annual fee is $0; the standard annual fee after the first year is $450.00."}
    return {"status": "outside_published_window", "detail": "The supplied date is outside the published 2025-11-01 through 2026-02-28 first-year waiver window."}


def main(payload):
    purchase = payload.get("purchase") or {}
    if "amount" not in purchase:
        return {"error": "purchase.amount is required."}
    try:
        amount = Decimal(str(purchase["amount"]))
        if amount <= 0:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        return {"error": "purchase.amount must be a positive number."}
    amount = money(amount)
    category = normalized(purchase.get("category"))
    brand_text = " ".join([normalized(purchase.get("merchant_name")), normalized(purchase.get("direct_brand"))])
    apple_direct = "apple" in brand_text
    applicant = payload.get("applicant") or {}
    options = []
    for name, card in CARDS.items():
        max_covers = card["max_limit"] >= amount
        option = {
            "card": name,
            "published_credit_limit_range": {"minimum": format(card["min_limit"], ".2f"), "maximum": format(card["max_limit"], ".2f")},
            "limit_assessment": "published_max_can_cover" if max_covers else "published_max_cannot_cover",
            "limit_note": "A published maximum is not an approved line. The full charge also requires sufficient available credit.",
            "eligibility": eligibility(card, applicant),
            "reward_assessment": category_result(name, card, amount, category, apple_direct),
        }
        options.append(option)
    candidates = []
    for item in options:
        if item["limit_assessment"] != "published_max_can_cover":
            continue
        assessment = item["reward_assessment"]
        if assessment["status"].startswith("confirmed"):
            value = Decimal(assessment["rewards"]["cash_back_dollars"])
        else:
            value = Decimal(assessment["standard_case"]["cash_back_dollars"])
        candidates.append((value, item["card"]))
    candidates.sort(reverse=True)
    recommendation = None
    if candidates:
        recommendation = {"basis": "highest non-contingent standard/confirmed reward among products whose published maximum can cover the amount",
                          "card": candidates[0][1], "cash_back_dollars": format(candidates[0][0], ".2f"),
                          "disclaimer": "This is not an approval, credit-limit, available-credit, or merchant-coding guarantee."}
    needed = ["Confirm the approved credit line and available credit before making the single charge."]
    if not category:
        needed.append("Ask the merchant or payment processor for the actual MCC or category; do not infer it from the merchant name.")
    if applicant.get("personal_credit_score") is None:
        needed.append("Confirm the applicant's personal credit score against the selected card's stated minimum.")
    if applicant.get("established_business") is not False and applicant.get("business_paydex") is None:
        needed.append("For an established business, confirm PAYDEX against the selected card's stated minimum.")
    highest = recommendation["card"] if recommendation else "No listed card"
    reply = (f"For a ${amount:,.2f} one-time purchase, {highest} has the strongest non-contingent comparison among the listed cards that can potentially reach that amount. "
             "That comparison is conditional on underwriting: the product's published maximum is not a promise of an approved or currently available line. "
             "Reward bonuses depend on the payment processor's merchant category, so confirm the MCC/category before relying on a bonus rate.")
    if apple_direct:
        reply += " Direct Apple/Apple Music billing earns the Business Silver standard rate because Apple is expressly excluded from its software bonus."
    return {"purchase_amount_dollars": format(amount, ".2f"), "merchant_category_supplied": category or None,
            "direct_Apple_billing_indicated": apple_direct, "options": options, "recommendation": recommendation,
            "business_platinum_promotion": promotion(payload.get("as_of")), "needed_confirmations": needed,
            "suggested_reply": reply}


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("Top-level JSON must be an object.")
        print(json.dumps(main(data), indent=2, sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
