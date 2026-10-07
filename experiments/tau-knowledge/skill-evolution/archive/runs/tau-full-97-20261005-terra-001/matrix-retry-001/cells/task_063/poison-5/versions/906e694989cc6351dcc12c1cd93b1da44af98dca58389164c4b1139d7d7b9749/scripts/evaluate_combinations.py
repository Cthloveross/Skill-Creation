#!/usr/bin/env python3
"""Filter documented savings/card combinations supplied as JSON on stdin."""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

ZERO = Decimal("0")
HUNDRED = Decimal("100")
CENT = Decimal("0.01")
DELIVERY = {"paper_allowed", "paperless_required", "unknown"}
RANKING = {"gross_interest", "net_known_fees"}


def number(value, field):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{field} must be numeric")


def money(value):
    return float(value.quantize(CENT, rounding=ROUND_HALF_UP))


def named(item, kind):
    value = item.get("name")
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"each {kind} requires a nonempty name")
    return value


def selected_tier(product, deposit):
    tiers = product.get("tiers")
    if not isinstance(tiers, list) or not tiers:
        raise ValueError(f"{product.get('name', 'product')} requires nonempty tiers")
    matching = []
    for tier in tiers:
        minimum = number(tier.get("minimum_balance"), "tiers.minimum_balance")
        apy = number(tier.get("apy"), "tiers.apy")
        if minimum <= deposit:
            matching.append((minimum, apy))
    if not matching:
        raise ValueError(f"deposit does not meet a documented tier for {product.get('name')}")
    return max(matching, key=lambda item: item[0])


def card_reasons(card, requirements):
    reasons = []
    stated_score = requirements.get("approximate_credit_score")
    minimum = card.get("minimum_credit_score")
    if minimum is None:
        reasons.append("card minimum credit score is undocumented")
    elif stated_score is None:
        reasons.append("customer approximate credit score is unavailable")
    elif number(stated_score, "approximate_credit_score") < number(minimum, "minimum_credit_score"):
        reasons.append("stated approximate score is below the card minimum")
    if requirements.get("credit_check_required") is True and card.get("credit_check_required") is not True:
        reasons.append("documented required credit check does not meet customer requirement")
    if card.get("other_eligibility_met") is False:
        reasons.append("a documented additional card eligibility requirement is unmet")
    return reasons


def highest_checking_bonus(boosts, savings_name):
    applicable = []
    for boost in boosts:
        if boost.get("savings_name") == savings_name and boost.get("documented_applicable") is True:
            applicable.append((number(boost.get("apy_bonus"), "checking apy_bonus"), boost.get("checking_name")))
    return max(applicable, default=(ZERO, None), key=lambda item: item[0])


def evaluate(payload):
    deposit = number(payload.get("deposit"), "deposit")
    if deposit < ZERO:
        raise ValueError("deposit must not be negative")
    requirements = payload.get("requirements")
    products = payload.get("savings_products")
    cards = payload.get("credit_cards")
    boosts = payload.get("checking_boosts", [])
    if not isinstance(requirements, dict):
        raise ValueError("requirements must be an object")
    if not isinstance(products, list) or not products:
        raise ValueError("savings_products must be a nonempty list")
    if not isinstance(cards, list) or not cards:
        raise ValueError("credit_cards must be a nonempty list")
    if not isinstance(boosts, list):
        raise ValueError("checking_boosts must be a list")
    mode = requirements.get("ranking_mode", "gross_interest")
    if mode not in RANKING:
        raise ValueError("requirements.ranking_mode is invalid")

    supported, excluded, uncompared = [], [], []
    for product in products:
        savings = named(product, "savings product")
        delivery = product.get("statement_delivery", "unknown")
        if delivery not in DELIVERY:
            raise ValueError("statement_delivery is invalid")
        opening = number(product.get("opening_deposit"), "opening_deposit")
        ongoing = number(product.get("ongoing_minimum"), "ongoing_minimum")
        tier_minimum, base_apy = selected_tier(product, deposit)
        product_reasons = []
        if requirements.get("paper_statements_required") is True:
            if delivery == "paperless_required":
                product_reasons.append("paperless statements conflict with required paper statements")
            elif delivery == "unknown":
                product_reasons.append("paper-statement availability is undocumented")
        if deposit < opening:
            product_reasons.append("deposit is below the required opening deposit")
        if deposit < ongoing:
            product_reasons.append("deposit is below the stated ongoing minimum")
        noncard_bonus = number(product.get("confirmed_bonus_apy", 0), "confirmed_bonus_apy")
        checking_bonus, checking_name = highest_checking_bonus(boosts, savings)

        for card in cards:
            card_name = named(card, "credit card")
            mapping = card.get("apy_bonus_by_savings")
            if not isinstance(mapping, dict) or savings not in mapping:
                uncompared.append({"savings_account": savings, "credit_card": card_name,
                                   "reason": "No documented account-specific card APY bonus was supplied."})
                continue
            reasons = product_reasons + card_reasons(card, requirements)
            if reasons:
                excluded.append({"savings_account": savings, "credit_card": card_name, "reasons": reasons})
                continue
            card_bonus = number(mapping[savings], "card apy bonus")
            effective = base_apy + noncard_bonus + checking_bonus + card_bonus
            gross = (deposit * effective / HUNDRED).quantize(CENT, rounding=ROUND_HALF_UP)
            annual_card_fee = number(card.get("annual_fee", 0), "annual_fee")
            known_account_fee = ZERO
            if deposit < ongoing:
                known_account_fee = number(product.get("below_minimum_monthly_fee", 0), "below_minimum_monthly_fee") * Decimal("12")
            net = (gross - annual_card_fee - known_account_fee).quantize(CENT, rounding=ROUND_HALF_UP)
            supported.append({
                "savings_account": savings,
                "credit_card": card_name,
                "deposit": float(deposit),
                "opening_deposit_requirement": float(opening),
                "ongoing_minimum_requirement": float(ongoing),
                "statement_delivery": delivery,
                "paper_statement_monthly_fee": float(number(product.get("paper_statement_monthly_fee", 0), "paper_statement_monthly_fee")),
                "selected_tier_minimum_balance": float(tier_minimum),
                "base_or_tier_apy": float(base_apy),
                "confirmed_noncard_nonchecking_bonus_apy": float(noncard_bonus),
                "checking_account": checking_name,
                "checking_apy_bonus": float(checking_bonus),
                "card_apy_bonus": float(card_bonus),
                "effective_apy": float(effective),
                "estimated_one_year_gross_interest": money(gross),
                "known_annual_account_fees": money(known_account_fee),
                "card_annual_fee": money(annual_card_fee),
                "estimated_one_year_net_after_known_fees": money(net),
                "approval_note": "Apparent eligibility only; card approval remains subject to underwriting."
            })

    score_key = "estimated_one_year_net_after_known_fees" if mode == "net_known_fees" else "estimated_one_year_gross_interest"
    supported.sort(key=lambda row: (row[score_key], row["effective_apy"]), reverse=True)
    best = supported[0] if supported else None
    tied = []
    if best is not None:
        tied = [row for row in supported if row[score_key] == best[score_key] and row["effective_apy"] == best["effective_apy"]]
    return {
        "ranking_mode": mode,
        "ranked_supported_options": supported,
        "best_option": best,
        "tied_best_options": tied,
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
