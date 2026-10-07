#!/usr/bin/env python3
"""Compute transparent business-card reward scenarios from JSON stdin.

See SKILL.md for the input/output contract. Product policy decisions (MCC,
promotion dates, actual approval, and applicable fees) are supplied explicitly,
not inferred by this program.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")
HUNDRED = Decimal("100")


def decimal_value(value, field):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a finite decimal number") from exc
    if not number.is_finite():
        raise ValueError(f"{field} must be a finite decimal number")
    return number


def money(value):
    return str(value.quantize(CENT, rounding=ROUND_HALF_UP))


def validate_enum(value, allowed, field):
    if value not in allowed:
        choices = ", ".join(repr(x) for x in allowed)
        raise ValueError(f"{field} must be one of {choices}")
    return value


def readiness(documented_capacity, available_credit):
    if documented_capacity == "cannot_cover" or available_credit == "insufficient":
        return "cannot_make_charge"
    if documented_capacity == "can_cover" and available_credit == "confirmed":
        return "confirmed_ready"
    if documented_capacity == "can_cover":
        return "conditional_on_approval_and_available_credit"
    return "capacity_unknown"


def compute_reward(amount, rate):
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

    results = []
    for index, option in enumerate(options):
        if not isinstance(option, dict):
            raise ValueError(f"options[{index}] must be an object")
        prefix = f"options[{index}]"
        name = option.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"{prefix}.name must be a nonempty string")
        documented_capacity = validate_enum(
            option.get("documented_capacity", "unknown"),
            ("can_cover", "cannot_cover", "unknown"), f"{prefix}.documented_capacity")
        available_credit = validate_enum(
            option.get("available_credit", "unconfirmed"),
            ("confirmed", "unconfirmed", "insufficient"), f"{prefix}.available_credit")
        base_rate = decimal_value(option.get("base_rate_percent"), f"{prefix}.base_rate_percent")
        if base_rate < 0:
            raise ValueError("rates cannot be negative")
        multiplier = decimal_value(option.get("promotion_multiplier", 1), f"{prefix}.promotion_multiplier")
        if multiplier <= 0:
            raise ValueError("promotion_multiplier must be greater than zero")
        promotion_eligible = option.get("promotion_eligible", False)
        if not isinstance(promotion_eligible, bool):
            raise ValueError(f"{prefix}.promotion_eligible must be boolean")
        applied_multiplier = multiplier if promotion_eligible else Decimal("1")
        fee = decimal_value(option.get("annual_fee", 0), f"{prefix}.annual_fee")
        if fee < 0:
            raise ValueError("annual_fee cannot be negative")
        fee_used = fee if include_fee else Decimal("0")

        guaranteed_rate = base_rate * applied_multiplier
        guaranteed_gross = compute_reward(amount, guaranteed_rate)
        guaranteed_net = guaranteed_gross - fee_used
        result = {
            "name": name,
            "documented_capacity": documented_capacity,
            "available_credit": available_credit,
            "charge_readiness": readiness(documented_capacity, available_credit),
            "promotion_applied_to_guaranteed_rate": promotion_eligible,
            "guaranteed_rate_percent": str(guaranteed_rate),
            "guaranteed_gross_reward": money(guaranteed_gross),
            "annual_fee_subtracted": money(fee_used),
            "guaranteed_net_value": money(guaranteed_net),
        }
        eligibility = validate_enum(option.get("bonus_eligibility", "not_eligible"),
                                    ("confirmed", "unconfirmed", "not_eligible"),
                                    f"{prefix}.bonus_eligibility")
        if "bonus_rate_percent" in option:
            bonus_rate = decimal_value(option["bonus_rate_percent"], f"{prefix}.bonus_rate_percent")
            if bonus_rate < 0:
                raise ValueError("rates cannot be negative")
            if eligibility != "not_eligible":
                effective_bonus_rate = bonus_rate * applied_multiplier
                bonus_gross = compute_reward(amount, effective_bonus_rate)
                bonus_net = bonus_gross - fee_used
                result["bonus_scenario"] = {
                    "eligibility": eligibility,
                    "guaranteed": eligibility == "confirmed",
                    "rate_percent": str(effective_bonus_rate),
                    "gross_reward": money(bonus_gross),
                    "net_value": money(bonus_net),
                }
                if eligibility == "confirmed":
                    result.update({
                        "guaranteed_rate_percent": str(effective_bonus_rate),
                        "guaranteed_gross_reward": money(bonus_gross),
                        "guaranteed_net_value": money(bonus_net),
                    })
        results.append(result)

    rankable = [x for x in results if x["charge_readiness"] != "cannot_make_charge"]
    ranked = sorted(rankable, key=lambda x: Decimal(x["guaranteed_net_value"]), reverse=True)
    return {
        "amount": money(amount),
        "include_annual_fee": include_fee,
        "options": results,
        "ranked_not_documented_ineligible": [x["name"] for x in ranked],
        "notice": (
            "Ranking uses guaranteed rates and excludes only options documented as unable to cover the charge. "
            "A conditional-capacity option still requires approval and enough available credit."
        ),
    }


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), separators=(",", ":")))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, separators=(",", ":")))
        sys.exit(2)
