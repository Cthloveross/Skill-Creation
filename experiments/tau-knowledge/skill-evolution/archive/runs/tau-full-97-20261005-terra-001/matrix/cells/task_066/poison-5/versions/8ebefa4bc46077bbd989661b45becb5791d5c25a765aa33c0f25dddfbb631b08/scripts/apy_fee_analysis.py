#!/usr/bin/env python3
"""Compare documented savings-card APY bonuses against annual card fees.

Reads one JSON object from stdin and emits one JSON object to stdout. Monetary
amounts and percentages are returned as decimal strings to avoid binary-float
rounding ambiguity. This helper is informational and never performs banking
or card actions.
"""

import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

ZERO = Decimal("0")
HUNDRED = Decimal("100")


def decimal_value(value, field, errors, required=True):
    if value is None:
        if required:
            errors.append(f"{field} is required")
        return None
    if isinstance(value, bool):
        errors.append(f"{field} must be numeric, not boolean")
        return None
    try:
        parsed = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        errors.append(f"{field} must be a valid decimal number")
        return None
    if not parsed.is_finite():
        errors.append(f"{field} must be finite")
        return None
    if parsed < ZERO:
        errors.append(f"{field} must be non-negative")
        return None
    return parsed


def display_decimal(value, places=None):
    if places is not None:
        value = value.quantize(Decimal(places), rounding=ROUND_HALF_UP)
    return format(value, "f")


def money(value):
    return display_decimal(value, "0.01")


def percentage(value):
    return display_decimal(value.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))


def parse_boosts(raw, errors):
    if raw is None:
        return []
    if not isinstance(raw, list):
        errors.append("checking_boosts must be an array")
        return []
    parsed = []
    for index, item in enumerate(raw):
        field = f"checking_boosts[{index}]"
        if isinstance(item, dict):
            name = item.get("name") or f"checking option {index + 1}"
            eligible = item.get("eligible", True)
            rate_source = item.get("apy_bonus_pct")
        else:
            name = f"checking option {index + 1}"
            eligible = True
            rate_source = item
        if not isinstance(eligible, bool):
            errors.append(f"{field}.eligible must be boolean")
            continue
        rate = decimal_value(rate_source, f"{field}.apy_bonus_pct", errors)
        if rate is not None and eligible:
            parsed.append({"name": str(name), "rate": rate})
    return parsed


def parse_cards(raw, errors):
    if raw is None:
        return []
    if not isinstance(raw, list):
        errors.append("card_options must be an array")
        return []
    parsed = []
    for index, item in enumerate(raw):
        field = f"card_options[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{field} must be an object")
            continue
        eligible = item.get("eligible", True)
        if not isinstance(eligible, bool):
            errors.append(f"{field}.eligible must be boolean")
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            errors.append(f"{field}.name must be a nonempty string")
            continue
        rate = decimal_value(item.get("apy_bonus_pct"), f"{field}.apy_bonus_pct", errors)
        fee = decimal_value(item.get("annual_fee"), f"{field}.annual_fee", errors)
        if rate is not None and fee is not None and eligible:
            parsed.append({"name": name, "rate": rate, "fee": fee})
    return parsed


def annual_interest(balance, apy_pct):
    # APY is already an annualized yield. Do not compound it a second time.
    return balance * apy_pct / HUNDRED


def make_scenario(name, candidate_rate, fee, base, checking, existing_card, balance):
    applied_card = max(existing_card, candidate_rate)
    effective_apy = base + checking["rate"] + applied_card
    gross_interest = annual_interest(balance, effective_apy)
    baseline_apy = base + checking["rate"] + existing_card
    baseline_interest = annual_interest(balance, baseline_apy)
    incremental_interest = gross_interest - baseline_interest
    net_change = incremental_interest - fee
    rate_increase = applied_card - existing_card
    break_even = None
    if fee > ZERO and rate_increase > ZERO:
        break_even = fee * HUNDRED / rate_increase
    return {
        "name": name,
        "selected_card_bonus_pct": percentage(applied_card),
        "effective_apy_pct": percentage(effective_apy),
        "approximate_annual_interest": money(gross_interest),
        "incremental_annual_interest": money(incremental_interest),
        "annual_fee": money(fee),
        "net_annual_change_after_fee": money(net_change),
        "break_even_balance": money(break_even) if break_even is not None else None,
        "break_even_note": (
            "Not applicable: this option does not improve the currently applicable card APY bonus."
            if fee > ZERO and rate_increase == ZERO else None
        ),
    }


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"validation_errors": [f"invalid JSON input: {exc.msg}"]}))
        return

    if not isinstance(payload, dict):
        print(json.dumps({"validation_errors": ["input must be a JSON object"]}))
        return

    errors = []
    balance = decimal_value(payload.get("balance"), "balance", errors)
    base = decimal_value(payload.get("base_apy_pct"), "base_apy_pct", errors)
    existing_card = decimal_value(
        payload.get("existing_card_bonus_pct", ZERO),
        "existing_card_bonus_pct",
        errors,
    )
    boosts = parse_boosts(payload.get("checking_boosts", []), errors)
    cards = parse_cards(payload.get("card_options", []), errors)
    if errors:
        print(json.dumps({"validation_errors": errors}, indent=2, sort_keys=True))
        return

    checking = max(
        boosts,
        key=lambda entry: entry["rate"],
        default={"name": None, "rate": ZERO},
    )
    baseline_apy = base + checking["rate"] + existing_card
    baseline_interest = annual_interest(balance, baseline_apy)
    scenarios = [
        make_scenario("No new card", ZERO, ZERO, base, checking, existing_card, balance)
    ]
    for card in cards:
        scenarios.append(
            make_scenario(card["name"], card["rate"], card["fee"], base, checking, existing_card, balance)
        )

    # The no-card option is first and wins an exact tie, avoiding an unnecessary fee.
    recommended = max(
        enumerate(scenarios),
        key=lambda pair: (Decimal(pair[1]["net_annual_change_after_fee"]), -pair[0]),
    )[1]
    result = {
        "assumptions": [
            "The balance remains constant for one year.",
            "The stated APY is treated as an annual yield; actual credited interest can vary.",
            "Only the highest eligible checking boost and highest eligible card bonus are applied.",
            "Checking and card bonuses are treated as additive only where product policy permits cross-category stacking.",
            "Existing-card annual fees and non-rate benefits are outside this candidate-card comparison.",
        ],
        "baseline": {
            "balance": money(balance),
            "base_apy_pct": percentage(base),
            "selected_checking": checking["name"],
            "selected_checking_boost_pct": percentage(checking["rate"]),
            "existing_card_bonus_pct": percentage(existing_card),
            "effective_apy_pct": percentage(baseline_apy),
            "approximate_annual_interest": money(baseline_interest),
        },
        "scenarios": scenarios,
        "recommended_scenario": recommended,
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
