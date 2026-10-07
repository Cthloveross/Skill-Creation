#!/usr/bin/env python3
"""Rank savings/card combinations supplied as JSON on stdin; emit JSON on stdout."""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

D0 = Decimal("0")
MONEY_Q = Decimal("0.01")


def dec(value, field):
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("%s must be numeric" % field)


def money(value):
    return str(value.quantize(MONEY_Q, rounding=ROUND_HALF_UP))


def percent(value):
    return str(value.normalize())


def tier_for(balance, tiers, label):
    if not isinstance(tiers, list) or not tiers:
        raise ValueError("%s.tiers must be a nonempty list" % label)
    parsed = []
    for t in tiers:
        parsed.append((dec(t["minimum_balance"], label + ".tier.minimum_balance"),
                       dec(t["apy_percent"], label + ".tier.apy_percent")))
    qualifying = [t for t in parsed if balance >= t[0]]
    if not qualifying:
        return None
    return max(qualifying, key=lambda x: x[0])


def card_assessment(card, profile, savings_name):
    reasons = []
    score = profile.get("credit_score")
    minimum = card.get("minimum_credit_score")
    if minimum is not None:
        if score is None:
            reasons.append("credit score is unknown")
        elif Decimal(str(score)) < dec(minimum, "card.minimum_credit_score"):
            reasons.append("stated credit score is below the published minimum")
    required_subscription = card.get("subscription_required")
    if required_subscription:
        if required_subscription not in profile.get("subscriptions", []):
            reasons.append("required subscription is not active")
    if profile.get("require_credit_review") and not card.get("credit_review_required", False):
        reasons.append("does not meet the requested credit-review requirement")
    bonuses = card.get("savings_apy_bonus_percent", {})
    bonus = dec(bonuses.get(savings_name, "0"), "card savings APY bonus")
    return {"eligible": not reasons, "reasons": reasons, "bonus": bonus}


def main(payload):
    balance = dec(payload["balance"], "balance")
    if balance < D0:
        raise ValueError("balance must not be negative")
    profile = payload.get("profile", {})
    savings_options = payload.get("savings_options", [])
    card_options = payload.get("card_options", [])
    if not isinstance(savings_options, list) or not savings_options:
        raise ValueError("savings_options must be a nonempty list")
    if not isinstance(card_options, list):
        raise ValueError("card_options must be a list")

    warnings = []
    ranked = []
    excluded = []
    if profile.get("credit_score") is not None and not profile.get("credit_score_confirmed", False):
        warnings.append("Credit-score eligibility is estimated from an unconfirmed customer statement; underwriting and a required credit review determine approval.")
    if not profile.get("direct_deposit_active", False):
        warnings.append("Direct-deposit bonuses were excluded because direct deposit is not marked active.")

    for savings in savings_options:
        name = savings.get("name")
        if not name:
            raise ValueError("each savings option needs a name")
        opening_min = dec(savings.get("opening_minimum", "0"), name + ".opening_minimum")
        ongoing_min = dec(savings.get("ongoing_minimum", "0"), name + ".ongoing_minimum")
        if profile.get("paper_statements_required") and not savings.get("paper_statements_available", False):
            excluded.append({"savings": name, "reason": "paper statements are required but unavailable"})
            continue
        tier = tier_for(balance, savings.get("tiers"), name)
        if tier is None:
            excluded.append({"savings": name, "reason": "balance does not qualify for a published APY tier"})
            continue
        base_apy = tier[1]
        dd_bonus = dec(savings.get("direct_deposit_bonus_percent", "0"), name + ".direct_deposit_bonus_percent") if profile.get("direct_deposit_active", False) else D0
        other_bonus = dec(savings.get("other_active_bonus_percent", "0"), name + ".other_active_bonus_percent")
        eligible_cards = []
        ineligible_cards = []
        for card in card_options:
            if not card.get("name"):
                raise ValueError("each card option needs a name")
            assessment = card_assessment(card, profile, name)
            if assessment["eligible"]:
                eligible_cards.append((card, assessment))
            else:
                ineligible_cards.append({"card": card["name"], "reasons": assessment["reasons"]})
        # A card APY bonus category is non-stacking: choose exactly one highest bonus.
        if eligible_cards:
            chosen_card, chosen = max(eligible_cards, key=lambda item: item[1]["bonus"])
            card_name = chosen_card["name"]
            card_bonus = chosen["bonus"]
            annual_fee = dec(chosen_card.get("annual_fee", "0"), card_name + ".annual_fee")
        else:
            card_name, card_bonus, annual_fee = None, D0, D0
        total_apy = base_apy + dd_bonus + other_bonus + card_bonus
        gross_interest = balance * total_apy / Decimal("100")
        net_after_fee = gross_interest - annual_fee
        ranked.append({
            "savings": name,
            "card": card_name,
            "balance": money(balance),
            "tier_minimum_balance": money(tier[0]),
            "base_apy_percent": percent(base_apy),
            "direct_deposit_bonus_percent": percent(dd_bonus),
            "other_active_bonus_percent": percent(other_bonus),
            "card_bonus_percent": percent(card_bonus),
            "total_apy_percent": percent(total_apy),
            "estimated_one_year_interest": money(gross_interest),
            "card_annual_fee": money(annual_fee),
            "estimated_interest_less_card_annual_fee": money(net_after_fee),
            "opening_minimum": money(opening_min),
            "ongoing_minimum": money(ongoing_min),
            "opening_minimum_met_by_balance": balance >= opening_min,
            "ongoing_minimum_met_by_balance": balance >= ongoing_min,
            "paper_requirement_met": (not profile.get("paper_statements_required")) or bool(savings.get("paper_statements_available")),
            "paper_statement_monthly_fee": money(dec(savings.get("paper_statement_monthly_fee", "0"), name + ".paper_statement_monthly_fee")),
            "ineligible_cards": ineligible_cards
        })
    ranked.sort(key=lambda row: (Decimal(row["estimated_interest_less_card_annual_fee"]), Decimal(row["estimated_one_year_interest"])), reverse=True)
    return {"status": "ok", "assumptions": ["Balance remains constant for one full year.", "APY is used as the annual yield and is not compounded again.", "Only the highest eligible card APY bonus is used; card bonuses are not summed."], "ranked_combinations": ranked, "excluded_savings_options": excluded, "warnings": warnings}


if __name__ == "__main__":
    try:
        obj = json.load(sys.stdin)
        print(json.dumps(main(obj), separators=(",", ":")))
    except (ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, separators=(",", ":")))
        sys.exit(2)
