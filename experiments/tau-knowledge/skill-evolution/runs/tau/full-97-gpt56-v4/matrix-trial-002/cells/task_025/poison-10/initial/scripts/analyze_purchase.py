#!/usr/bin/env python3
"""Analyze a high-value business-card purchase.

Reads a JSON object from stdin and emits JSON only to stdout. See SKILL.md for
input and output schema. Uses only the Python standard library.
"""
import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

MONEY = Decimal("0.01")


def parse_date(value, field, errors):
    if value is None:
        return None
    if not isinstance(value, str):
        errors.append(f"{field} must be an ISO YYYY-MM-DD string or null")
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        errors.append(f"{field} must be an ISO YYYY-MM-DD date")
        return None


def money(value):
    return Decimal(value).quantize(MONEY, rounding=ROUND_HALF_UP)


def reward(amount, rate):
    dollars = (amount * rate).quantize(MONEY, rounding=ROUND_HALF_UP)
    return {
        "rate_percent": str((rate * Decimal("100")).quantize(Decimal("0.1"))),
        "cash_back_dollars": format(dollars, ".2f"),
        "stored_reward_points": int(dollars * Decimal("100")),
    }


def normalize_category(value, errors):
    if value is None:
        return None
    if not isinstance(value, str):
        errors.append("merchant_category must be a string or null")
        return None
    norm = value.strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "media": "media_advertising",
        "advertising": "media_advertising",
        "media_and_advertising": "media_advertising",
    }
    norm = aliases.get(norm, norm)
    allowed = {"travel", "software", "media_advertising", "operations", "other"}
    if norm not in allowed:
        errors.append("merchant_category must be travel, software, media_advertising, operations, other, or null")
        return None
    return norm


def max_line_supports(maximum, amount, single):
    if not single:
        return {"published_maximum_can_support": None,
                "reason": "Single-transaction requirement was not specified; split charges require separate authorization and limit analysis."}
    possible = maximum >= amount
    return {
        "published_maximum_can_support": possible,
        "reason": ("Published maximum is at least the requested single-purchase amount. "
                   "Actual approved limit and available credit remain unverified.") if possible else
                  "Published maximum is below the requested single-purchase amount.",
    }


def fee_status(card, account_date, new_customer):
    standard = card["annual_fee"]
    waiver = card.get("waiver")
    if waiver is None:
        return {"standard_annual_fee_dollars": standard, "first_year_fee_status": "No supplied first-year waiver."}
    output = {"standard_annual_fee_dollars": standard}
    if new_customer is not True:
        output["first_year_fee_status"] = "Waiver requires new-customer status, which is not confirmed."
        return output
    if account_date is None:
        output["first_year_fee_status"] = "New-customer waiver may apply only if account opening falls within the stated window."
        output["waiver_window"] = waiver
        return output
    start = date.fromisoformat(waiver["start"])
    end = date.fromisoformat(waiver["end"])
    if start <= account_date <= end:
        output["first_year_fee_status"] = "Waived (based on supplied new-customer status and account-opening date)."
        output["first_year_annual_fee_dollars"] = "0.00"
    else:
        output["first_year_fee_status"] = "Not within the supplied waiver window."
    output["waiver_window"] = waiver
    return output


def scenarios_for(card_key, merchant, category, amount):
    if card_key == "business_silver":
        apple_excluded = merchant is not None and "apple" in merchant.lower()
        if apple_excluded:
            return [{"condition": "Named Apple exclusion applies; standard rate.", "category": category, "result": reward(amount, Decimal("0.01"))}]
        if category is None:
            return [
                {"condition": "If processor MCC is qualifying travel or software.", "result": reward(amount, Decimal("0.10"))},
                {"condition": "If MCC is not qualifying travel/software or an exclusion applies.", "result": reward(amount, Decimal("0.01"))},
            ]
        rate = Decimal("0.10") if category in {"travel", "software"} else Decimal("0.01")
        return [{"condition": "Confirmed category evaluated under Business Silver rules.", "category": category, "result": reward(amount, rate)}]
    if card_key == "business_gold":
        if category is None:
            return [
                {"condition": "If processor MCC qualifies as operations spend.", "result": reward(amount, Decimal("0.025"))},
                {"condition": "If processor MCC does not qualify as operations spend.", "result": reward(amount, Decimal("0.01"))},
            ]
        rate = Decimal("0.025") if category == "operations" else Decimal("0.01")
        return [{"condition": "Confirmed category evaluated under Business Gold rules.", "category": category, "result": reward(amount, rate)}]
    if card_key == "business_platinum":
        eligible = {"travel", "software", "media_advertising"}
        if category is None:
            return [
                {"condition": "If processor MCC is qualifying travel, software, or media/advertising.", "result": reward(amount, Decimal("0.04"))},
                {"condition": "If processor MCC is outside those qualifying categories.", "result": reward(amount, Decimal("0.015"))},
            ]
        rate = Decimal("0.04") if category in eligible else Decimal("0.015")
        return [{"condition": "Confirmed category evaluated under Business Platinum rules.", "category": category, "result": reward(amount, rate)}]
    return []


def main():
    try:
        raw = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"errors": [f"Invalid JSON input: {exc.msg}"]}))
        return
    if not isinstance(raw, dict):
        print(json.dumps({"errors": ["Input must be a JSON object"]}))
        return

    errors = []
    try:
        amount = Decimal(str(raw.get("purchase_amount")))
        if not amount.is_finite() or amount <= 0:
            errors.append("purchase_amount must be a positive numeric amount")
    except (InvalidOperation, ValueError):
        amount = Decimal("0")
        errors.append("purchase_amount must be a positive numeric amount")
    category = normalize_category(raw.get("merchant_category"), errors)
    current_date = parse_date(raw.get("current_date"), "current_date", errors)
    account_date = parse_date(raw.get("account_open_date"), "account_open_date", errors)
    single = raw.get("requires_single_transaction", True)
    if not isinstance(single, bool):
        errors.append("requires_single_transaction must be boolean")
    new_customer = raw.get("new_customer")
    if new_customer is not None and not isinstance(new_customer, bool):
        errors.append("new_customer must be boolean or null")
    merchant = raw.get("merchant_name")
    if merchant is not None and not isinstance(merchant, str):
        errors.append("merchant_name must be a string or null")
    if errors:
        print(json.dumps({"errors": errors}, indent=2, sort_keys=True))
        return

    amount = money(amount)
    effective_open_date = account_date or current_date
    cards = {
        "business_silver": {
            "display_name": "Business Silver Rewards Card",
            "max_line": Decimal("112500"), "annual_fee": "122.50",
            "eligibility": "Stated minimum personal credit score 700; established-business PAYDEX 47.",
            "waiver": {"start": "2025-11-15", "end": "2026-01-15"},
        },
        "business_gold": {
            "display_name": "Business Gold Rewards Card",
            "max_line": Decimal("225000"), "annual_fee": "200.00",
            "eligibility": "Stated minimum personal credit score 735 and PAYDEX 67.",
        },
        "business_platinum": {
            "display_name": "Business Platinum Rewards Card",
            "max_line": Decimal("400000"), "annual_fee": "450.00",
            "eligibility": "Stated minimum personal credit score 765 and PAYDEX 77.",
            "waiver": {"start": "2025-11-01", "end": "2026-02-28"},
        },
        "business_bronze": {
            "display_name": "Business Bronze Rewards Card",
            "max_line": Decimal("75000"), "annual_fee": "0.00",
            "eligibility": "Stated minimum personal credit score 660; PAYDEX 20 is considered when available.",
        },
    }

    result_cards = {}
    for key, card in cards.items():
        entry = {
            "name": card["display_name"],
            "published_maximum_credit_line_dollars": format(card["max_line"], ".2f"),
            "single_purchase_feasibility": max_line_supports(card["max_line"], amount, single),
            "stated_eligibility": card["eligibility"],
            "annual_fee": fee_status(card, effective_open_date, new_customer),
        }
        if key == "business_bronze":
            entry["earnings_scenarios"] = []
            entry["note"] = "Included for feasibility only; do not use it for a single purchase above its published maximum."
        else:
            entry["earnings_scenarios"] = scenarios_for(key, merchant, category, amount)
        result_cards[key] = entry

    guidance = []
    if category is None:
        guidance = [
            "If Business Platinum receives a qualifying travel, software, or media/advertising MCC, its 4.0% rate exceeds the supplied Gold and Silver alternatives.",
            "If the charge is operations-coded but not qualifying for Platinum, Business Gold's 2.5% operations rate exceeds Platinum's 1.5% other-purchase rate and Silver's 1.0% standard rate.",
            "If no bonus category applies, Business Platinum's 1.5% rate exceeds Business Gold and Business Silver at 1.0%.",
            "These rankings are conditional on an approved and available sufficient credit line and on actual processor coding.",
        ]
    else:
        guidance = ["Use the per-card confirmed-category scenarios; merchant category coding, not the service description alone, controls the applicable rate."]
    unresolved = []
    if category is None:
        unresolved.append("Merchant processor category/MCC is unknown; no unconditional best-rewards conclusion is supported.")
    if merchant is None:
        unresolved.append("Merchant name is missing; named merchant exclusions cannot be evaluated.")
    if effective_open_date is None:
        unresolved.append("Account-opening date/current date is missing; fee-waiver timing cannot be determined.")
    unresolved.append("Actual approval, approved line, available credit, and authorization requirements are not established by published maximum lines.")

    output = {
        "purchase_amount_dollars": format(amount, ".2f"),
        "merchant_name": merchant,
        "merchant_category": category,
        "requires_single_transaction": single,
        "fee_assumption_account_open_date": effective_open_date.isoformat() if effective_open_date else None,
        "cards": result_cards,
        "decision_guidance": guidance,
        "unresolved_items": unresolved,
        "cash_back_representation": "stored_reward_points equal 100 points per cash-back dollar.",
    }
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
