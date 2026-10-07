#!/usr/bin/env python3
"""Compare supplied savings/card pairs; read one JSON object from stdin and emit one JSON object."""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

ZERO = Decimal("0")
HUNDRED = Decimal("100")
MONTHS_PER_YEAR = Decimal("12")
CENT = Decimal("0.01")


def dec(value, field):
    try:
        answer = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{field} must be numeric")
    if not answer.is_finite():
        raise ValueError(f"{field} must be finite")
    return answer


def as_money(value):
    return str(value.quantize(CENT, rounding=ROUND_HALF_UP))


def as_percent(value):
    return str(value.normalize())


def choose_tier(balance, tiers, name):
    if not isinstance(tiers, list) or not tiers:
        raise ValueError(f"{name}.tiers must be a nonempty list")
    parsed = []
    for tier in tiers:
        parsed.append((dec(tier["minimum_balance"], f"{name}.tier.minimum_balance"),
                       dec(tier["apy_percent"], f"{name}.tier.apy_percent")))
    eligible = [tier for tier in parsed if balance >= tier[0]]
    return max(eligible, key=lambda tier: tier[0]) if eligible else None


def card_check(card, profile, savings_name):
    """Return card eligibility based only on stated facts, plus its bonus for this savings name."""
    reasons = []
    score = profile.get("credit_score")
    minimum = card.get("minimum_credit_score")
    if minimum is not None:
        minimum_value = dec(minimum, "card.minimum_credit_score")
        # A zero published minimum denotes no score threshold, not missing score data.
        if minimum_value > ZERO and score is None:
            reasons.append("credit score is unknown")
        elif score is not None and dec(score, "profile.credit_score") < minimum_value:
            reasons.append("stated credit score is below the published minimum")
    subscription = card.get("subscription_required")
    if subscription and subscription not in profile.get("subscriptions", []):
        reasons.append("required subscription is not active")
    if profile.get("require_credit_review", False) and card.get("credit_review_required") is not True:
        reasons.append("does not meet the requested credit-review requirement")
    bonuses = card.get("savings_apy_bonus_percent", {})
    if not isinstance(bonuses, dict):
        raise ValueError("card.savings_apy_bonus_percent must be an object")
    return reasons, dec(bonuses.get(savings_name, "0"), "card savings APY bonus")


def effective_ongoing_minimum(savings, card_name):
    """Use a documented card-specific override when supplied; otherwise use the normal minimum."""
    base = dec(savings.get("ongoing_minimum", "0"), f"{savings['name']}.ongoing_minimum")
    overrides = savings.get("ongoing_minimum_overrides", {})
    if overrides is None:
        overrides = {}
    if not isinstance(overrides, dict):
        raise ValueError(f"{savings['name']}.ongoing_minimum_overrides must be an object")
    return dec(overrides.get(card_name, base), f"{savings['name']}.ongoing_minimum_override")


def main(payload):
    balance = dec(payload["balance"], "balance")
    if balance < ZERO:
        raise ValueError("balance must not be negative")
    profile = payload.get("profile", {})
    if not isinstance(profile, dict):
        raise ValueError("profile must be an object")
    savings_options = payload.get("savings_options")
    card_options = payload.get("card_options")
    if not isinstance(savings_options, list) or not savings_options:
        raise ValueError("savings_options must be a nonempty list")
    if not isinstance(card_options, list) or not card_options:
        raise ValueError("card_options must be a nonempty list when a card is requested")

    warnings = []
    if profile.get("credit_score") is not None and not profile.get("credit_score_confirmed", False):
        warnings.append("Credit-score eligibility is estimated from an unconfirmed customer statement; underwriting and any required credit review determine approval.")
    if not profile.get("direct_deposit_active", False):
        warnings.append("Direct-deposit bonuses were excluded because direct deposit is not marked active.")

    ranked, excluded = [], []
    for savings in savings_options:
        name = savings.get("name")
        if not name:
            raise ValueError("each savings option needs a name")
        if profile.get("paper_statements_required", False) and savings.get("paper_statements_available") is not True:
            excluded.append({"savings": name, "card": None, "reason": "paper statements are required but unavailable"})
            continue
        opening = dec(savings.get("opening_minimum", "0"), f"{name}.opening_minimum")
        tier = choose_tier(balance, savings.get("tiers"), name)
        if tier is None:
            excluded.append({"savings": name, "card": None, "reason": "balance does not qualify for a published APY tier"})
            continue
        base_apy = tier[1]
        direct_deposit_bonus = (dec(savings.get("direct_deposit_bonus_percent", "0"), f"{name}.direct_deposit_bonus_percent")
                                if profile.get("direct_deposit_active", False) else ZERO)
        # This is for non-card bonuses only. A card bonus must be supplied on the card option.
        other_bonus = dec(savings.get("other_active_bonus_percent", "0"), f"{name}.other_active_bonus_percent")
        paper_fee = dec(savings.get("paper_statement_monthly_fee", "0"), f"{name}.paper_statement_monthly_fee")

        for card in card_options:
            card_name = card.get("name")
            if not card_name:
                raise ValueError("each card option needs a name")
            reasons, card_bonus = card_check(card, profile, name)
            if reasons:
                excluded.append({"savings": name, "card": card_name, "reason": "; ".join(reasons)})
                continue
            ongoing = effective_ongoing_minimum(savings, card_name)
            if balance < opening:
                excluded.append({"savings": name, "card": card_name, "reason": "balance is below the opening minimum"})
                continue
            if balance < ongoing:
                excluded.append({"savings": name, "card": card_name, "reason": "balance is below the ongoing minimum"})
                continue
            annual_fee = dec(card.get("annual_fee", "0"), f"{card_name}.annual_fee")
            total_apy = base_apy + direct_deposit_bonus + other_bonus + card_bonus
            gross = balance * total_apy / HUNDRED
            paper_cost = paper_fee * MONTHS_PER_YEAR if profile.get("paper_statements_required", False) else ZERO
            less_card_fee = gross - annual_fee
            net = less_card_fee - paper_cost
            ranked.append({
                "savings": name,
                "card": card_name,
                "balance": as_money(balance),
                "tier_minimum_balance": as_money(tier[0]),
                "base_apy_percent": as_percent(base_apy),
                "direct_deposit_bonus_percent": as_percent(direct_deposit_bonus),
                "other_active_bonus_percent": as_percent(other_bonus),
                "card_bonus_percent": as_percent(card_bonus),
                "total_apy_percent": as_percent(total_apy),
                "estimated_one_year_interest": as_money(gross),
                "card_annual_fee": as_money(annual_fee),
                "estimated_interest_less_card_annual_fee": as_money(less_card_fee),
                "paper_statement_monthly_fee": as_money(paper_fee),
                "estimated_annual_paper_statement_fee": as_money(paper_cost),
                "estimated_net_after_required_fees": as_money(net),
                "opening_minimum": as_money(opening),
                "ongoing_minimum": as_money(ongoing),
                "paper_requirement_met": True,
                "eligibility_is_estimated": not profile.get("credit_score_confirmed", False)
            })
    ranked.sort(key=lambda row: (Decimal(row["estimated_net_after_required_fees"]),
                                  Decimal(row["estimated_one_year_interest"])), reverse=True)
    return {
        "status": "ok",
        "assumptions": [
            "Balance remains constant for one full year.",
            "APY is used as the annual yield and is not compounded again.",
            "Each row is one savings account plus one card; card APY bonuses are never summed.",
            "Required monthly paper-statement fees, if supplied, are annualized in the net estimate."
        ],
        "ranked_combinations": ranked,
        "excluded_combinations": excluded,
        "warnings": warnings
    }


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), separators=(",", ":")))
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, separators=(",", ":")))
        sys.exit(2)
