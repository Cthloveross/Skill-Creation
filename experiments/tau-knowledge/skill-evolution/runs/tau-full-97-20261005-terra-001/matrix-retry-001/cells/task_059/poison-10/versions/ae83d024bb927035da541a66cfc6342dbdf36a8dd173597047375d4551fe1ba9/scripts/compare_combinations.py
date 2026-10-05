#!/usr/bin/env python3
"""Compare first-year savings/card combinations from runtime-supplied facts.

Reads one JSON object from stdin and writes one JSON object to stdout.
No external dependencies or filesystem access are used.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

MONEY = Decimal("0.01")
VALID_ELIGIBILITY = {"eligible", "unknown", "ineligible"}


def decimal(value, field, minimum=None):
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{field} must be a decimal number")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be a decimal number")
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    if minimum is not None and result < minimum:
        raise ValueError(f"{field} must be at least {minimum}")
    return result


def money(value):
    return str(value.quantize(MONEY, rounding=ROUND_HALF_UP))


def rate_list(value, field):
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    return [decimal(item, field, Decimal("0")) for item in value]


def optional_number(mapping, key, default, field, minimum=Decimal("0")):
    if key not in mapping or mapping[key] is None:
        return default
    return decimal(mapping[key], field, minimum)


def evaluate(candidate, balance, monthly_spend):
    if not isinstance(candidate, dict):
        raise ValueError("each candidate must be an object")
    name = candidate.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("candidate.name must be a nonempty string")

    eligibility = candidate.get("eligibility", "unknown")
    if eligibility not in VALID_ELIGIBILITY:
        raise ValueError("candidate.eligibility must be eligible, unknown, or ineligible")

    savings = candidate.get("savings")
    if not isinstance(savings, dict):
        raise ValueError(f"{name}.savings must be an object")
    base_apy = decimal(
        savings.get("base_apy_percent"),
        f"{name}.savings.base_apy_percent",
        Decimal("0"),
    )
    checking_boosts = rate_list(
        savings.get("checking_apy_boosts_percent", []),
        f"{name}.savings.checking_apy_boosts_percent",
    )
    card_bonuses = rate_list(
        savings.get("credit_card_apy_bonuses_percent", []),
        f"{name}.savings.credit_card_apy_bonuses_percent",
    )
    additive = rate_list(
        savings.get("additive_apy_bonuses_percent", []),
        f"{name}.savings.additive_apy_bonuses_percent",
    )
    savings_fee = optional_number(
        savings, "annual_fee", Decimal("0"), f"{name}.savings.annual_fee"
    )
    opening_min = optional_number(
        savings,
        "opening_deposit_min",
        Decimal("0"),
        f"{name}.savings.opening_deposit_min",
    )
    ongoing_min = optional_number(
        savings,
        "ongoing_balance_min",
        Decimal("0"),
        f"{name}.savings.ongoing_balance_min",
    )

    card = candidate.get("card") or {}
    if not isinstance(card, dict):
        raise ValueError(f"{name}.card must be an object when supplied")
    card_fee = optional_number(card, "annual_fee", Decimal("0"), f"{name}.card.annual_fee")
    reward_rate = optional_number(
        card,
        "blended_rewards_rate_percent",
        Decimal("0"),
        f"{name}.card.blended_rewards_rate_percent",
    )
    first_year_bonus = optional_number(
        card,
        "first_year_bonus_value",
        Decimal("0"),
        f"{name}.card.first_year_bonus_value",
    )
    additional_fees = optional_number(
        candidate,
        "additional_annual_fees",
        Decimal("0"),
        f"{name}.additional_annual_fees",
    )

    best_checking = max(checking_boosts, default=Decimal("0"))
    best_card = max(card_bonuses, default=Decimal("0"))
    additive_total = sum(additive, Decimal("0"))
    effective_apy = base_apy + best_checking + best_card + additive_total
    interest = balance * effective_apy / Decimal("100")
    rewards = monthly_spend * Decimal("12") * reward_rate / Decimal("100")
    fees = savings_fee + card_fee + additional_fees
    net = interest + rewards + first_year_bonus - fees

    notes = candidate.get("eligibility_notes", [])
    if not isinstance(notes, list) or not all(isinstance(note, str) for note in notes):
        raise ValueError(f"{name}.eligibility_notes must be a list of strings")
    warnings = list(notes)
    if balance < opening_min:
        warnings.append("planned balance is below the supplied opening-deposit minimum")
    if balance < ongoing_min:
        warnings.append("planned balance is below the supplied ongoing-balance minimum")
    if eligibility != "eligible":
        warnings.append("do not present this candidate as available until eligibility is confirmed")

    return {
        "name": name,
        "eligibility": eligibility,
        "base_apy_percent": str(base_apy),
        "highest_checking_boost_percent": str(best_checking),
        "highest_card_bonus_percent": str(best_card),
        "additive_bonus_percent": str(additive_total),
        "effective_apy_percent": str(effective_apy),
        "estimated_interest": money(interest),
        "estimated_card_rewards": money(rewards),
        "verified_first_year_bonus_value": money(first_year_bonus),
        "known_annual_fees": money(fees),
        "estimated_first_year_net": money(net),
        "warnings": warnings,
        "_net_sort": net,
    }


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    balance = decimal(payload.get("balance"), "balance", Decimal("0"))
    monthly_spend = decimal(
        payload.get("monthly_card_spend", "0"),
        "monthly_card_spend",
        Decimal("0"),
    )
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("candidates must be a nonempty list")

    rows = [evaluate(candidate, balance, monthly_spend) for candidate in candidates]
    priority = {"eligible": 0, "unknown": 1, "ineligible": 2}
    rows.sort(key=lambda row: (priority[row["eligibility"]], -row["_net_sort"], row["name"].lower()))
    for row in rows:
        del row["_net_sort"]

    eligible = [row["name"] for row in rows if row["eligibility"] == "eligible"]
    return {
        "ok": True,
        "assumptions": {
            "balance": money(balance),
            "monthly_card_spend": money(monthly_spend),
            "annual_card_spend": money(monthly_spend * Decimal("12")),
            "method": "APY is treated as an effective annual rate; only the highest supplied checking and card bonuses are used.",
        },
        "recommended_eligible_candidate": eligible[0] if eligible else None,
        "candidates_ranked": rows,
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), separators=(",", ":")))
    except (ValueError, TypeError, json.JSONDecodeError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, separators=(",", ":")))
