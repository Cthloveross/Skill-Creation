#!/usr/bin/env python3
"""Rank supplied savings APY scenarios without taking banking actions.

Read one JSON object from stdin and write one JSON object to stdout. APYs are
percentage points. Invalid input writes {"error": message} and exits with 2.
"""
import json
import sys
from decimal import Decimal, InvalidOperation


def decimal(value, field):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{field} must be numeric")
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result


def optional_amount(row, key, account_class):
    if key not in row:
        raise ValueError(f"{key} is required for {account_class}; use null when unknown")
    value = row[key]
    if value is None:
        return None
    amount = decimal(value, f"{key} for {account_class}")
    if amount < 0:
        raise ValueError(f"{key} must be nonnegative")
    return amount


def text(value):
    if value is None:
        return None
    rendered = format(value.normalize(), "f")
    return "0" if rendered in ("", "-0") else rendered


def array(data, name):
    value = data.get(name, [])
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a list")
    return value


def active_classes(records, class_key):
    return {
        row.get(class_key) for row in records
        if isinstance(row, dict) and row.get("active") is True
        and isinstance(row.get(class_key), str)
    }


def qualifying_checking(records):
    """Return boost-eligible classes and proposed classes whose boost is conditional."""
    qualifying, proposed = set(), set()
    for row in records:
        if not isinstance(row, dict) or not isinstance(row.get("account_class"), str):
            continue
        if row.get("active") is True:
            qualifying.add(row["account_class"])
        elif row.get("proposed_and_eligible") is True:
            qualifying.add(row["account_class"])
            proposed.add(row["account_class"])
    return qualifying, proposed


def highest_boost(boosts, left_key, left_classes, savings_class, label):
    candidates = []
    for row in boosts:
        if not isinstance(row, dict):
            continue
        if row.get("savings_class") == savings_class and row.get(left_key) in left_classes:
            amount = decimal(row.get("apy_boost"), f"{label} apy_boost")
            candidates.append((amount, row[left_key]))
    return max(candidates, default=(Decimal("0"), None), key=lambda item: (item[0], item[1] or ""))


def main(data):
    deposit = decimal(data.get("deposit_amount"), "deposit_amount")
    if deposit < 0:
        raise ValueError("deposit_amount must be nonnegative")
    cards_confirmed = data.get("cards_confirmed")
    if not isinstance(cards_confirmed, bool):
        raise ValueError("cards_confirmed must be boolean")

    options = array(data, "savings_options")
    checking_records = array(data, "checking_accounts")
    checking, proposed_checking = qualifying_checking(checking_records)
    active_checking = active_classes(checking_records, "account_class")
    cards = active_classes(array(data, "credit_card_accounts"), "card_class")
    checking_boosts = array(data, "checking_boosts")
    card_boosts = array(data, "card_boosts")

    eligible, excluded = [], []
    for option in options:
        if not isinstance(option, dict) or not isinstance(option.get("account_class"), str):
            raise ValueError("each savings option needs a string account_class")
        savings_class = option["account_class"]
        base = decimal(option.get("base_apy"), f"base_apy for {savings_class}")
        opening_min = optional_amount(option, "minimum_opening_deposit", savings_class)
        ongoing_min = optional_amount(option, "minimum_ongoing_balance", savings_class)
        confirmed = option.get("requirements_confirmed")
        if not isinstance(confirmed, bool):
            raise ValueError(f"requirements_confirmed must be boolean for {savings_class}")

        check_boost, check_class = highest_boost(checking_boosts, "checking_class", checking, savings_class, "checking")
        card_boost, card_class = highest_boost(card_boosts, "card_class", cards, savings_class, "card")
        warnings = []
        opening_ok = opening_min is not None and deposit >= opening_min
        ongoing_ok = ongoing_min is not None and deposit >= ongoing_min
        if opening_min is None:
            warnings.append("documented opening minimum is unavailable")
        elif not opening_ok:
            warnings.append("planned deposit is below the documented opening minimum")
        if ongoing_min is None:
            warnings.append("documented ongoing minimum is unavailable")
        elif not ongoing_ok:
            warnings.append("planned deposit is below the documented ongoing minimum")
        if not confirmed:
            warnings.append("product requirements have not been confirmed")
        if not cards_confirmed:
            warnings.append("card records have not been confirmed; card bonus is incomplete")
        if not active_checking:
            warnings.append("no active checking relationship was supplied")
        if check_class in proposed_checking:
            warnings.append("selected checking boost is conditional on successful opening of the proposed checking account")

        comparison_complete = cards_confirmed and bool(active_checking)
        result = {
            "account_class": savings_class,
            "base_apy": text(base),
            "selected_checking_class": check_class,
            "selected_checking_boost": text(check_boost),
            "selected_card_class": card_class,
            "selected_card_boost": text(card_boost),
            "estimated_total_apy": text(base + check_boost + card_boost),
            "minimum_opening_deposit": text(opening_min),
            "minimum_ongoing_balance": text(ongoing_min),
            "opening_deposit_feasible": opening_ok,
            "ongoing_balance_feasible": ongoing_ok,
            "requirements_confirmed": confirmed,
            "comparison_complete": comparison_complete,
            "warnings": warnings,
        }
        is_eligible = opening_ok and ongoing_ok and confirmed and comparison_complete
        (eligible if is_eligible else excluded).append(result)

    key = lambda row: (Decimal(row["estimated_total_apy"]), row["account_class"])
    eligible.sort(key=key, reverse=True)
    excluded.sort(key=key, reverse=True)
    return {
        "deposit_amount": text(deposit),
        "cards_confirmed": cards_confirmed,
        "eligible_ranked_options": eligible,
        "ineligible_or_unconfirmed_options": excluded,
        "action_required": "Obtain exact customer confirmation and complete all account eligibility checks before opening any account.",
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), separators=(",", ":")))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, separators=(",", ":")))
        sys.exit(2)
