#!/usr/bin/env python3
"""Calculate a constant-balance daily-compounding savings interest estimate.

Reads one JSON object from stdin and writes one JSON object to stdout.  All
monetary and percent inputs may be JSON numbers or decimal strings.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, getcontext

getcontext().prec = 50
CENT = Decimal("0.01")
ZERO = Decimal("0")


def decimal_value(value, field):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be a decimal number")
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result


def decimal_list(value, field):
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{field} must be an array")
    values = [decimal_value(item, field) for item in value]
    if any(item < ZERO for item in values):
        raise ValueError(f"{field} cannot contain negative bonuses")
    return values


def money(value):
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), "f")


def main(payload):
    base = decimal_value(payload["base_apy_percent"], "base_apy_percent")
    if base < ZERO:
        raise ValueError("base_apy_percent cannot be negative")
    checking = decimal_list(payload.get("checking_boosts_percent", []), "checking_boosts_percent")
    cards = decimal_list(payload.get("card_bonuses_percent", []), "card_bonuses_percent")
    relationship = decimal_list(payload.get("relationship_bonuses_percent", []), "relationship_bonuses_percent")
    tier = decimal_list(payload.get("tier_bonuses_percent", []), "tier_bonuses_percent")
    balance = decimal_value(payload["balance"], "balance")
    if balance < ZERO:
        raise ValueError("balance cannot be negative")

    days = payload["days"]
    if isinstance(days, bool) or not isinstance(days, int) or days < 1 or days > 366:
        raise ValueError("days must be an integer from 1 through 366")
    basis = payload.get("day_count_basis", 365)
    if isinstance(basis, bool) or not isinstance(basis, int) or basis < 1 or basis > 366:
        raise ValueError("day_count_basis must be an integer from 1 through 366")

    selected_checking = max(checking, default=ZERO)
    selected_card = max(cards, default=ZERO)
    relationship_total = sum(relationship, ZERO)
    tier_total = sum(tier, ZERO)
    apy = base + selected_checking + selected_card + relationship_total + tier_total

    # APY is modeled as an effective annual yield. This converts it to an
    # equivalent daily rate before compounding for the requested number of days.
    annual_factor = Decimal("1") + apy / Decimal("100")
    daily_factor = annual_factor ** (Decimal("1") / Decimal(basis))
    estimated = balance * (daily_factor ** Decimal(days) - Decimal("1"))

    output = {
        "selected_checking_boost_percent": str(selected_checking),
        "selected_card_bonus_percent": str(selected_card),
        "relationship_bonus_total_percent": str(relationship_total),
        "tier_bonus_total_percent": str(tier_total),
        "expected_apy_percent": str(apy),
        "day_count_basis": basis,
        "days": days,
        "constant_balance_assumption": format(balance, "f"),
        "unrounded_estimated_interest": format(estimated, "f"),
        "estimated_interest": money(estimated),
    }
    if "actual_interest" in payload and payload["actual_interest"] is not None:
        actual = decimal_value(payload["actual_interest"], "actual_interest")
        output["actual_interest"] = money(actual)
        output["difference_from_actual"] = money(estimated - actual)
        output["positive_shortfall"] = estimated > actual
    return output


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        if not isinstance(raw, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(raw), sort_keys=True))
    except (KeyError, ValueError, TypeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
