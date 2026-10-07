#!/usr/bin/env python3
"""Calculate conservative one-year savings/card product comparison estimates.

Input: JSON object described in SKILL.md on stdin.
Output: JSON object with combinations, exclusions, viable ranking, and recommendation.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

ZERO = Decimal("0")
HUNDRED = Decimal("100")
CENT = Decimal("0.01")


def dec(value, field):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{field} must be a number") from exc
    if not result.is_finite() or result < ZERO:
        raise ValueError(f"{field} must be a finite non-negative number")
    return result


def money(value):
    return str(value.quantize(CENT, rounding=ROUND_HALF_UP))


def percent(value, field):
    return dec(value, field) / HUNDRED


def status(value, field):
    value = str(value or "unknown").lower()
    if value not in {"eligible", "unknown", "ineligible"}:
        raise ValueError(f"{field} must be eligible, unknown, or ineligible")
    return value


def main(payload):
    start = dec(payload.get("starting_savings"), "starting_savings")
    monthly_spend = dec(payload.get("monthly_card_spend"), "monthly_card_spend")
    months_raw = payload.get("months", 12)
    if isinstance(months_raw, bool) or not isinstance(months_raw, int) or months_raw <= 0:
        raise ValueError("months must be a positive integer")
    months = months_raw
    prefs = payload.get("preferences") or {}
    avoid_undocumented = bool(prefs.get("avoid_undocumented_fees", False))
    avoid_subscription = bool(prefs.get("avoid_subscription", False))
    cards = payload.get("cards") or []
    savings_accounts = payload.get("savings") or []
    if not isinstance(cards, list) or not isinstance(savings_accounts, list):
        raise ValueError("cards and savings must be arrays")

    combinations = []
    exclusions = []
    for card in cards:
        if not isinstance(card, dict):
            raise ValueError("each card must be an object")
        cname = str(card.get("name", "")).strip()
        if not cname:
            raise ValueError("every card requires name")
        c_status = status(card.get("eligibility", "unknown"), f"card {cname} eligibility")
        annual_fee = dec(card.get("annual_fee", 0), f"card {cname} annual_fee")
        subscription = dec(card.get("monthly_subscription_fee", 0), f"card {cname} monthly_subscription_fee")
        reward_rate = percent(card.get("ordinary_reward_rate_percent", 0), f"card {cname} ordinary_reward_rate_percent")
        card_bonus = percent(card.get("savings_apy_bonus_percent", 0), f"card {cname} savings_apy_bonus_percent")
        card_reasons = []
        if bool(card.get("excluded", False)):
            card_reasons.append("explicitly excluded")
        if c_status == "ineligible":
            card_reasons.append("card eligibility is not met")
        if avoid_undocumented and not bool(card.get("fee_documented", False)):
            card_reasons.append("fees are not documented")
        if avoid_subscription and subscription > ZERO:
            card_reasons.append("requires a paid subscription")

        for saving in savings_accounts:
            if not isinstance(saving, dict):
                raise ValueError("each savings item must be an object")
            sname = str(saving.get("name", "")).strip()
            if not sname:
                raise ValueError("every savings item requires name")
            s_status = status(saving.get("eligibility", "unknown"), f"savings {sname} eligibility")
            base_apy = percent(saving.get("base_apy_percent"), f"savings {sname} base_apy_percent")
            maint = dec(saving.get("monthly_maintenance_fee", 0), f"savings {sname} monthly_maintenance_fee")
            linked_bonus = ZERO
            if bool(saving.get("linked_boost_established", False)):
                linked_bonus = percent(saving.get("linked_checking_apy_bonus_percent", 0), f"savings {sname} linked_checking_apy_bonus_percent")

            reasons = list(card_reasons)
            if s_status == "ineligible":
                reasons.append("savings eligibility is not met")
            if reasons:
                exclusions.append({"card": cname, "savings": sname, "reasons": reasons})
                continue

            applicable_apy = base_apy + linked_bonus + card_bonus
            # APY is already an annual yield. Scale proportionally for non-12-month horizons.
            interest = start * applicable_apy * Decimal(months) / Decimal(12)
            rewards = monthly_spend * Decimal(months) * reward_rate
            fees = annual_fee * Decimal(months) / Decimal(12) + subscription * Decimal(months) + maint * Decimal(months)
            net = interest + rewards - fees
            combo_status = "eligible" if c_status == "eligible" and s_status == "eligible" else "unknown"
            combinations.append({
                "card": cname,
                "savings": sname,
                "eligibility": combo_status,
                "applicable_apy_percent": str((applicable_apy * HUNDRED).quantize(Decimal("0.0001"))),
                "estimated_interest": money(interest),
                "estimated_rewards": money(rewards),
                "estimated_fees": money(fees),
                "estimated_net_return": money(net),
                "conditions": (["card eligibility is unknown"] if c_status == "unknown" else []) +
                              (["savings eligibility is unknown"] if s_status == "unknown" else []) +
                              ([] if bool(saving.get("linked_boost_established", False)) else ["no unestablished linked-checking bonus included"])
            })

    combinations.sort(key=lambda x: (Decimal(x["estimated_net_return"]), x["eligibility"] == "eligible"), reverse=True)
    return {
        "months": months,
        "assumptions": [
            "APY is applied to the supplied starting balance without modeled balance changes.",
            "Only supplied, normalized ordinary-purchase rewards are included.",
            "APR, taxes, category bonuses, promotions, and undocumented charges are excluded."
        ],
        "viable_combinations": combinations,
        "excluded_combinations": exclusions,
        "recommended": combinations[0] if combinations else None
    }


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(data), indent=2, sort_keys=True))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
