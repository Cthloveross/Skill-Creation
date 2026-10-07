#!/usr/bin/env python3
"""Rank documented account options without accessing banking systems.

Reads one JSON object from stdin and writes one JSON object to stdout.
All rates are percentage-point values (for example, 6.0 means 6.0% APY).
"""

import json
import sys
from decimal import Decimal, InvalidOperation


def number(value, field, errors, default=None):
    if value is None:
        if default is not None:
            return Decimal(str(default))
        errors.append(f"missing numeric field: {field}")
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        errors.append(f"invalid numeric field: {field}")
        return None
    if not result.is_finite():
        errors.append(f"non-finite numeric field: {field}")
        return None
    return result


def decimal_list(values, field, errors):
    if values is None:
        return []
    if not isinstance(values, list):
        errors.append(f"{field} must be a list")
        return []
    output = []
    for index, value in enumerate(values):
        parsed = number(value, f"{field}[{index}]", errors)
        if parsed is not None:
            output.append(parsed)
    return output


def render(value):
    return float(value.quantize(Decimal("0.0001")))


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "errors": [f"invalid JSON: {exc.msg}"]}))
        return

    if not isinstance(payload, dict):
        print(json.dumps({"ok": False, "errors": ["input must be a JSON object"]}))
        return

    errors = []
    available = number(payload.get("available_deposit"), "available_deposit", errors)
    early_requirement = number(
        payload.get("minimum_early_deposit_days", 0),
        "minimum_early_deposit_days",
        errors,
        default=0,
    )
    if available is not None and available < 0:
        errors.append("available_deposit must not be negative")
    if early_requirement is not None and early_requirement < 0:
        errors.append("minimum_early_deposit_days must not be negative")

    checking_results = []
    checking_options = payload.get("checking_options", [])
    if not isinstance(checking_options, list):
        errors.append("checking_options must be a list")
        checking_options = []
    for index, option in enumerate(checking_options):
        if not isinstance(option, dict):
            errors.append(f"checking_options[{index}] must be an object")
            continue
        name = option.get("account_class")
        days = number(option.get("early_direct_deposit_days"),
                      f"checking_options[{index}].early_direct_deposit_days", errors)
        if not isinstance(name, str) or not name.strip():
            errors.append(f"checking_options[{index}].account_class must be a nonempty string")
            continue
        if days is None:
            continue
        eligible = early_requirement is not None and days >= early_requirement
        record = {
            "account_class": name,
            "early_direct_deposit_days": render(days),
            "meets_early_deposit_requirement": eligible,
        }
        if "perk_score" in option:
            score = number(option.get("perk_score"), f"checking_options[{index}].perk_score", errors)
            if score is not None:
                record["documented_rubric_perk_score"] = render(score)
        checking_results.append(record)

    checking_results.sort(
        key=lambda item: (
            not item["meets_early_deposit_requirement"],
            -item["early_direct_deposit_days"],
            -item.get("documented_rubric_perk_score", 0),
            item["account_class"].lower(),
        )
    )

    savings_results = []
    savings_options = payload.get("savings_options", [])
    if not isinstance(savings_options, list):
        errors.append("savings_options must be a list")
        savings_options = []
    for index, option in enumerate(savings_options):
        if not isinstance(option, dict):
            errors.append(f"savings_options[{index}] must be an object")
            continue
        prefix = f"savings_options[{index}]"
        name = option.get("account_class")
        base = number(option.get("base_apy_percent"), prefix + ".base_apy_percent", errors)
        opening = number(option.get("opening_deposit_min"), prefix + ".opening_deposit_min", errors)
        ongoing = number(option.get("ongoing_balance_min"), prefix + ".ongoing_balance_min", errors)
        if not isinstance(name, str) or not name.strip():
            errors.append(prefix + ".account_class must be a nonempty string")
            continue
        if base is None or opening is None or ongoing is None:
            continue
        if min(base, opening, ongoing) < 0:
            errors.append(prefix + " rates and balances must not be negative")
            continue
        checking_bonus = max(decimal_list(option.get("checking_boosts_percent"),
                                           prefix + ".checking_boosts_percent", errors), default=Decimal("0"))
        card_bonus = max(decimal_list(option.get("card_bonuses_percent"),
                                      prefix + ".card_bonuses_percent", errors), default=Decimal("0"))
        eligible = available is not None and available >= opening and available >= ongoing
        savings_results.append({
            "account_class": name,
            "meets_stated_opening_and_ongoing_balance": eligible,
            "base_apy_percent": render(base),
            "highest_applicable_checking_boost_percent": render(checking_bonus),
            "highest_applicable_card_bonus_percent": render(card_bonus),
            "calculated_apy_percent": render(base + checking_bonus + card_bonus),
            "required_opening_deposit": render(opening),
            "required_ongoing_balance": render(ongoing),
        })

    savings_results.sort(
        key=lambda item: (
            not item["meets_stated_opening_and_ongoing_balance"],
            -item["calculated_apy_percent"],
            item["account_class"].lower(),
        )
    )
    print(json.dumps({
        "ok": not errors,
        "errors": errors,
        "checking_ranked": checking_results,
        "savings_ranked": savings_results,
        "assumptions": [
            "Savings eligibility here checks only supplied deposit and ongoing-balance thresholds.",
            "Each bonus list is reduced to its highest value; bonuses within a category are not summed.",
            "Calculated APY is advisory and requires live confirmation of every supplied bonus and eligibility condition.",
            "No result authorizes account opening, transfer, or closure."
        ],
    }, separators=(",", ":")))


if __name__ == "__main__":
    main()
