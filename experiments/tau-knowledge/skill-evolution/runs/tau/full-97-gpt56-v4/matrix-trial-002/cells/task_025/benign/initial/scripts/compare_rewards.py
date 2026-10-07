#!/usr/bin/env python3
"""Calculate transparent card-reward scenarios from JSON stdin.

Input and output schemas are documented in SKILL.md. This program deliberately
accepts product facts as input: it does not infer merchant category eligibility,
promotion timing, or credit approval.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")
HUNDRED = Decimal("100")


def decimal_value(value, field):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{field} must be a finite decimal number") from exc
    if not result.is_finite():
        raise ValueError(f"{field} must be a finite decimal number")
    return result


def money(value):
    return str(value.quantize(CENT, rounding=ROUND_HALF_UP))


def reward(amount, rate):
    return amount * rate / HUNDRED


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be an object")
    amount = decimal_value(payload.get("amount"), "amount")
    if amount <= 0:
        raise ValueError("amount must be greater than zero")
    include_fee = payload.get("include_annual_fee", True)
    if not isinstance(include_fee, bool):
        raise ValueError("include_annual_fee must be boolean")
    options = payload.get("options")
    if not isinstance(options, list) or not options:
        raise ValueError("options must be a nonempty array")

    calculated = []
    for index, option in enumerate(options):
        if not isinstance(option, dict):
            raise ValueError(f"options[{index}] must be an object")
        name = option.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"options[{index}].name must be a nonempty string")
        capacity = option.get("can_cover_charge", "unknown")
        if capacity not in (True, False, "unknown"):
            raise ValueError(f"options[{index}].can_cover_charge must be true, false, or 'unknown'")
        base_rate = decimal_value(option.get("base_rate_percent"), f"options[{index}].base_rate_percent")
        if base_rate < 0:
            raise ValueError("rates cannot be negative")
        multiplier = decimal_value(option.get("promotion_multiplier", 1), f"options[{index}].promotion_multiplier")
        if multiplier <= 0:
            raise ValueError("promotion_multiplier must be greater than zero")
        promotion_eligible = option.get("promotion_eligible", True)
        if not isinstance(promotion_eligible, bool):
            raise ValueError("promotion_eligible must be boolean")
        applied_multiplier = multiplier if promotion_eligible else Decimal("1")
        fee = decimal_value(option.get("annual_fee", 0), f"options[{index}].annual_fee")
        if fee < 0:
            raise ValueError("annual_fee cannot be negative")

        conservative_rate = base_rate * applied_multiplier
        gross = reward(amount, conservative_rate)
        net = gross - fee if include_fee else gross
        result = {
            "name": name,
            "can_cover_charge": capacity,
            "conservative_rate_percent": str(conservative_rate),
            "conservative_gross_reward": money(gross),
            "annual_fee_subtracted": money(fee if include_fee else Decimal("0")),
            "conservative_net_value": money(net),
        }
        eligibility = option.get("bonus_eligibility", "not_eligible")
        if eligibility not in ("confirmed", "unconfirmed", "not_eligible"):
            raise ValueError("bonus_eligibility must be confirmed, unconfirmed, or not_eligible")
        if "bonus_rate_percent" in option:
            bonus_rate = decimal_value(option["bonus_rate_percent"], f"options[{index}].bonus_rate_percent")
            if bonus_rate < 0:
                raise ValueError("rates cannot be negative")
            if eligibility != "not_eligible":
                bonus_effective_rate = bonus_rate * applied_multiplier
                bonus_gross = reward(amount, bonus_effective_rate)
                bonus_net = bonus_gross - fee if include_fee else bonus_gross
                result["bonus_scenario"] = {
                    "eligibility": eligibility,
                    "guaranteed": eligibility == "confirmed",
                    "rate_percent": str(bonus_effective_rate),
                    "gross_reward": money(bonus_gross),
                    "net_value": money(bonus_net),
                }
                if eligibility == "confirmed":
                    result["conservative_rate_percent"] = str(bonus_effective_rate)
                    result["conservative_gross_reward"] = money(bonus_gross)
                    result["conservative_net_value"] = money(bonus_net)
        calculated.append(result)

    rankable = [item for item in calculated if item["can_cover_charge"] is True]
    ranked = sorted(rankable, key=lambda item: Decimal(item["conservative_net_value"]), reverse=True)
    return {
        "amount": money(amount),
        "include_annual_fee": include_fee,
        "options": calculated,
        "ranked_confirmed_capacity": [item["name"] for item in ranked],
        "notice": "Ranking uses only confirmed capacity and guaranteed (base or confirmed-bonus) rates. Unconfirmed bonus scenarios are not ranked as guaranteed outcomes.",
    }


if __name__ == "__main__":
    try:
        incoming = json.load(sys.stdin)
        print(json.dumps(main(incoming), separators=(",", ":")))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, separators=(",", ":")))
        sys.exit(2)
