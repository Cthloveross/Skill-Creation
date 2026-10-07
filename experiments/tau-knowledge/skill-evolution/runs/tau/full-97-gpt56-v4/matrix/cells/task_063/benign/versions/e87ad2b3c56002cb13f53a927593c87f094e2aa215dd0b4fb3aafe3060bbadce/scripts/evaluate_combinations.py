#!/usr/bin/env python3
"""Filter documented savings/card combinations from JSON stdin.

This is a decision aid only.  It does not apply for, open, or fund an account.
"""
import json
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

RULES = Path(__file__).resolve().parents[1] / "references" / "product_rules.json"


def decimal(value, field):
    try:
        value = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{field} must be numeric")
    if not value.is_finite() or value < 0:
        raise ValueError(f"{field} must be a finite nonnegative number")
    return value


def flag(payload, key, default=False):
    value = payload.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be true or false")
    return value


def savings_rate(product, balance):
    if "tier_1_apy_percent" in product:
        threshold = decimal(product["tier_2_threshold"], "tier_2_threshold")
        if balance >= threshold:
            return Decimal(str(product["tier_2_apy_percent"])), "tier_2"
        return Decimal(str(product["tier_1_apy_percent"])), "tier_1"
    return Decimal(str(product["base_apy_percent"])), "base"


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    balance = decimal(payload.get("balance"), "balance")
    score = payload.get("credit_score")
    score = None if score is None else decimal(score, "credit_score")
    needs_paper = flag(payload, "paper_statements_required")
    needs_check = flag(payload, "credit_check_required")
    premium = flag(payload, "premium_subscription_active")
    invited = flag(payload, "invitation_received")
    linked = flag(payload, "same_customer_profile_confirmed")

    rules = json.loads(RULES.read_text(encoding="utf-8"))
    savings = rules["savings_products"]
    cards = rules["credit_cards"]
    eligible_savings, savings_exclusions = [], {}
    for name, product in savings.items():
        if needs_paper and not product.get("paper_statements_available", False):
            savings_exclusions[name] = "mailed paper statements are unavailable or paperless is required"
            continue
        opening = decimal(product.get("opening_deposit_minimum", 0), "opening_deposit_minimum")
        ongoing = decimal(product.get("ongoing_balance_minimum", 0), "ongoing_balance_minimum")
        if balance < opening or balance < ongoing:
            savings_exclusions[name] = "intended balance does not meet documented opening or ongoing minimum"
            continue
        base, tier = savings_rate(product, balance)
        eligible_savings.append((name, product, base, tier))

    eligible_cards, card_exclusions = [], {}
    for name, card in cards.items():
        minimum = card.get("minimum_credit_score")
        # A published zero explicitly means no score is required; do not turn
        # absence of a score into an exclusion in that case.
        minimum_value = None if minimum is None else decimal(minimum, "minimum_credit_score")
        if minimum_value is not None and minimum_value > 0 and (score is None or score < minimum_value):
            card_exclusions[name] = "published credit-score minimum is not confirmed met"
            continue
        if card.get("premium_subscription_required") and not premium:
            card_exclusions[name] = "required premium subscription is not active"
            continue
        if card.get("invitation_only") and not invited:
            card_exclusions[name] = "invitation-only eligibility is not confirmed"
            continue
        # null means the supplied evidence does not establish a credit check.
        if needs_check and card.get("credit_check_consent_required") is not True:
            card_exclusions[name] = "supplied documentation does not confirm the required credit check"
            continue
        eligible_cards.append((name, card))

    combinations = []
    for savings_name, product, base, tier in eligible_savings:
        bonuses = product.get("card_apy_bonuses_percent", {})
        for card_name, card in eligible_cards:
            bonus = Decimal(str(bonuses.get(card_name, 0))) if linked else Decimal("0")
            apy = base + bonus
            combinations.append({
                "savings_account": savings_name,
                "credit_card": card_name,
                "balance_tier": tier,
                "base_apy_percent": float(base),
                "card_bonus_apy_percent": float(bonus),
                "effective_apy_percent": float(apy),
                "estimated_one_year_interest": float((balance * apy / Decimal("100")).quantize(Decimal("0.01"))),
                "unbonused_one_year_interest": float((balance * base / Decimal("100")).quantize(Decimal("0.01"))),
                "card_bonus_incremental_one_year_interest": float((balance * bonus / Decimal("100")).quantize(Decimal("0.01"))),
                "card_annual_fee": card.get("annual_fee"),
                "bonus_assumption": "same customer profile confirmed" if linked else "no card bonus included until same-profile linkage is confirmed",
                "approval_note": "Meets documented filters only; approval is not guaranteed."
            })
    combinations.sort(key=lambda x: (-x["effective_apy_percent"], x["card_annual_fee"] or 0, x["savings_account"], x["credit_card"]))
    return {
        "compatible_combinations": combinations,
        "savings_exclusions": savings_exclusions,
        "card_exclusions": card_exclusions,
        "note": "Only documented products and confirmed inputs were evaluated. Card bonuses are not stacked."
    }


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), sort_keys=True))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
