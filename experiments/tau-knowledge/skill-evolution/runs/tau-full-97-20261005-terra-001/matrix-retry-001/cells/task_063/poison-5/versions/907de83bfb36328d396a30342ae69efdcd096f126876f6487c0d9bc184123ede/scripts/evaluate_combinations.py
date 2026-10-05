#!/usr/bin/env python3
"""Filter and rank documented savings/card combinations from JSON stdin."""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

ZERO = Decimal("0")
HUNDRED = Decimal("100")
CENT = Decimal("0.01")
DELIVERY = {"paper_allowed", "paperless_required", "unknown"}
RANKING = {"gross_interest", "net_known_fees"}


def dec(value, field):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{field} must be numeric")


def as_money(value):
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def as_float(value):
    return float(value)


def require_name(item, kind):
    name = item.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"each {kind} needs a nonempty name")
    return name


def tier_for(product, deposit):
    tiers = product.get("tiers")
    if tiers is None:
        if "base_apy" not in product:
            raise ValueError(f"{product.get('name')!r} needs tiers or base_apy")
        return dec(product["base_apy"], "base_apy"), None
    if not isinstance(tiers, list) or not tiers:
        raise ValueError("tiers must be a nonempty list when supplied")
    usable = []
    for tier in tiers:
        minimum = dec(tier.get("minimum_balance"), "tiers.minimum_balance")
        apy = dec(tier.get("apy"), "tiers.apy")
        if minimum <= deposit:
            usable.append((minimum, apy))
    if not usable:
        raise ValueError(f"deposit does not meet a supplied tier for {product.get('name')!r}")
    return max(usable, key=lambda item: item[0])[1], max(usable, key=lambda item: item[0])[0]


def card_status(card, requirements):
    """Return (usable, reasons). Usable means apparent, not guaranteed, eligibility."""
    reasons = []
    score = requirements.get("approximate_credit_score")
    minimum = card.get("minimum_credit_score")
    if minimum is None:
        reasons.append("Card minimum credit score is undocumented.")
    elif score is None:
        reasons.append("Customer credit-score information is unavailable for this card.")
    elif dec(score, "approximate_credit_score") < dec(minimum, "minimum_credit_score"):
        reasons.append("Customer's stated approximate score is below the card minimum.")
    if requirements.get("credit_check_required") is True:
        if card.get("credit_check_required") is not True:
            reasons.append("Card does not have a documented required credit check matching the customer's requirement.")
    if card.get("other_eligibility_met") is not True:
        reasons.append("Other documented card eligibility has not been confirmed.")
    return not reasons, reasons


def checking_bonus(boosts, savings_name):
    matches = []
    for boost in boosts:
        if boost.get("savings_name") != savings_name:
            continue
        if boost.get("documented_applicable") is not True:
            continue
        matches.append((dec(boost.get("apy_bonus"), "checking apy_bonus"), boost.get("checking_name", "Unnamed checking account")))
    if not matches:
        return ZERO, None
    highest = max(matches, key=lambda item: item[0])
    return highest


def evaluate(data):
    deposit = dec(data.get("deposit"), "deposit")
    if deposit < ZERO:
        raise ValueError("deposit must not be negative")
    requirements = data.get("requirements")
    if not isinstance(requirements, dict):
        raise ValueError("requirements must be an object")
    ranking_mode = requirements.get("ranking_mode", "gross_interest")
    if ranking_mode not in RANKING:
        raise ValueError("requirements.ranking_mode is invalid")
    products = data.get("savings_products")
    cards = data.get("credit_cards")
    boosts = data.get("checking_boosts", [])
    if not isinstance(products, list) or not products:
        raise ValueError("savings_products must be a nonempty list")
    if not isinstance(cards, list) or not cards:
        raise ValueError("credit_cards must be a nonempty list")
    if not isinstance(boosts, list):
        raise ValueError("checking_boosts must be a list")

    supported = []
    excluded = []
    uncompared = []
    for product in products:
        savings_name = require_name(product, "savings product")
        delivery = product.get("statement_delivery", "unknown")
        if delivery not in DELIVERY:
            raise ValueError("statement_delivery is invalid")
        opening = dec(product.get("opening_deposit"), "opening_deposit")
        ongoing = dec(product.get("ongoing_minimum", 0), "ongoing_minimum")
        product_reasons = []
        if requirements.get("paper_statements_required") is True:
            if delivery == "paperless_required":
                product_reasons.append("Paperless statements are required, conflicting with the paper-statement requirement.")
            elif delivery == "unknown":
                product_reasons.append("Paper-statement availability is undocumented.")
        if deposit < opening:
            product_reasons.append("Available deposit is below the required opening deposit.")
        if deposit < ongoing:
            product_reasons.append("Available deposit is below the stated ongoing minimum balance.")
        base_apy, tier_minimum = tier_for(product, deposit)
        confirmed_bonus = dec(product.get("confirmed_bonus_apy", 0), "confirmed_bonus_apy")
        check_bonus, checking_name = checking_bonus(boosts, savings_name)

        for card in cards:
            card_name = require_name(card, "credit card")
            mappings = card.get("apy_bonus_by_savings")
            if not isinstance(mappings, dict) or savings_name not in mappings:
                uncompared.append({"savings_account": savings_name, "credit_card": card_name,
                                   "reason": "No documented account-specific card APY bonus was supplied."})
                continue
            reasons = list(product_reasons)
            usable_card, card_reasons = card_status(card, requirements)
            if not usable_card:
                reasons.extend(card_reasons)
            card_bonus = dec(mappings[savings_name], "card apy bonus")
            if reasons:
                excluded.append({"savings_account": savings_name, "credit_card": card_name,
                                 "reasons": reasons})
                continue
            effective = base_apy + confirmed_bonus + check_bonus + card_bonus
            gross = as_money(deposit * effective / HUNDRED)
            account_fee = ZERO
            if deposit < ongoing and "below_minimum_monthly_fee" in product:
                account_fee = dec(product["below_minimum_monthly_fee"], "below_minimum_monthly_fee") * Decimal("12")
            annual_fee = dec(card.get("annual_fee", 0), "annual_fee")
            net = as_money(gross - account_fee - annual_fee)
            supported.append({
                "savings_account": savings_name,
                "credit_card": card_name,
                "deposit": as_float(deposit),
                "opening_deposit_requirement": as_float(opening),
                "ongoing_minimum_requirement": as_float(ongoing),
                "statement_delivery": delivery,
                "paper_statement_monthly_fee": as_float(dec(product.get("paper_statement_monthly_fee", 0), "paper_statement_monthly_fee")),
                "selected_tier_minimum_balance": as_float(tier_minimum) if tier_minimum is not None else None,
                "base_or_tier_apy": as_float(base_apy),
                "confirmed_noncard_nonchecking_bonus_apy": as_float(confirmed_bonus),
                "checking_account": checking_name,
                "checking_apy_bonus": as_float(check_bonus),
                "card_apy_bonus": as_float(card_bonus),
                "effective_apy": as_float(effective),
                "estimated_one_year_gross_interest": as_float(gross),
                "known_annual_account_fees": as_float(account_fee),
                "card_annual_fee": as_float(annual_fee),
                "estimated_one_year_net_after_known_fees": as_float(net),
                "approval_note": "Apparent eligibility only; card approval remains subject to underwriting."
            })

    key = "estimated_one_year_net_after_known_fees" if ranking_mode == "net_known_fees" else "estimated_one_year_gross_interest"
    supported.sort(key=lambda row: (row[key], row["effective_apy"]), reverse=True)
    return {
        "ranking_mode": ranking_mode,
        "ranked_supported_options": supported,
        "best_option": supported[0] if supported else None,
        "excluded_options": excluded,
        "uncompared_card_pairings": uncompared
    }


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(evaluate(payload), indent=2, sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
