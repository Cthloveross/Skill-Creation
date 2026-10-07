#!/usr/bin/env python3
"""Select non-stacking APY bonuses and calculate a documented interest estimate.

Reads one JSON object from stdin and writes one JSON object to stdout. No network,
file, or banking operations are performed.
"""

import json
import math
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")
EPSILON = Decimal("0.000001")


def decimal_value(value, field, nonnegative=True):
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{field} must be a number")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be a number")
    if not number.is_finite():
        raise ValueError(f"{field} must be finite")
    if nonnegative and number < 0:
        raise ValueError(f"{field} must not be negative")
    return number


def as_number(value):
    """JSON-friendly number without unnecessary Decimal serialization issues."""
    return float(value)


def select_highest(entries, amount_key, required_flag):
    eligible = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(f"entry {index} must be an object")
        # Conservative selection: unknown status never qualifies.
        if entry.get("active") is True and entry.get(required_flag) is True:
            amount = decimal_value(entry.get(amount_key), f"entry {index}.{amount_key}")
            name = entry.get("name", f"entry_{index}")
            if not isinstance(name, str):
                raise ValueError(f"entry {index}.name must be a string")
            eligible.append({"name": name, "amount": amount})
    if not eligible:
        return Decimal("0"), [], 0
    maximum = max(item["amount"] for item in eligible)
    winners = [item["name"] for item in eligible if item["amount"] == maximum]
    return maximum, winners, len(eligible)


def compound_interest(principals, annual_apy):
    """Accrue daily at the effective annual APY.

    Each supplied principal is the verified daily principal balance before accrued
    interest. This model carries prior accrued interest forward. It is reliable
    only when the caller supplies the complete day-by-day balance basis.
    """
    annual_fraction = float(annual_apy / Decimal("100"))
    daily_factor = Decimal(str(math.pow(1.0 + annual_fraction, 1.0 / 365.0)))
    accrued = Decimal("0")
    for principal in principals:
        accrued = (principal + accrued) * daily_factor - principal
    return accrued


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")

    base_apy = decimal_value(payload.get("base_apy"), "base_apy")
    cards = payload.get("credit_card_bonuses", [])
    checking = payload.get("checking_boosts", [])
    if not isinstance(cards, list) or not isinstance(checking, list):
        raise ValueError("credit_card_bonuses and checking_boosts must be arrays")

    card_bonus, card_winners, eligible_cards = select_highest(
        cards, "apy_bonus", "same_profile"
    )
    checking_boost, checking_winners, eligible_checking = select_highest(
        checking, "apy_boost", "qualifying"
    )
    expected_apy = base_apy + card_bonus + checking_boost

    missing = []
    if not cards:
        missing.append("No credit-card eligibility data was supplied.")
    elif eligible_cards == 0:
        missing.append("No active, same-profile eligible credit card was confirmed.")
    if not checking:
        missing.append("No linked-checking eligibility data was supplied.")
    elif eligible_checking == 0:
        missing.append("No active qualifying linked checking account was confirmed.")

    result = {
        "expected_apy": as_number(expected_apy),
        "components": {
            "base_apy": as_number(base_apy),
            "highest_credit_card_bonus": as_number(card_bonus),
            "highest_checking_boost": as_number(checking_boost),
        },
        "selected_credit_card_bonus": {
            "selected_names": card_winners,
            "tied_highest": len(card_winners) > 1,
            "eligible_count": eligible_cards,
        },
        "selected_checking_boost": {
            "selected_names": checking_winners,
            "tied_highest": len(checking_winners) > 1,
            "eligible_count": eligible_checking,
        },
        "missing_evidence": missing,
        "interest_calculation": None,
        "apy_comparison": None,
        "discrepancy_status": "not_assessable",
        "warnings": [],
    }

    displayed = payload.get("displayed_apy")
    if displayed is not None:
        displayed_apy = decimal_value(displayed, "displayed_apy")
        rate_difference = expected_apy - displayed_apy
        result["apy_comparison"] = {
            "displayed_apy": as_number(displayed_apy),
            "expected_minus_displayed_apy": as_number(rate_difference),
            "matches_within_precision": abs(rate_difference) <= EPSILON,
        }
        if abs(rate_difference) > EPSILON:
            result["discrepancy_status"] = "possible_rate_discrepancy"

    principals = None
    basis = None
    daily_balances = payload.get("daily_balances")
    if daily_balances is not None:
        if not isinstance(daily_balances, list) or not daily_balances:
            raise ValueError("daily_balances must be a nonempty array when supplied")
        principals = [decimal_value(v, f"daily_balances[{i}]") for i, v in enumerate(daily_balances)]
        basis = "daily_balance_calculation"
    elif payload.get("days") is not None or payload.get("balance") is not None:
        if payload.get("days") is None or payload.get("balance") is None:
            raise ValueError("days and balance must be supplied together for an estimate")
        days = payload["days"]
        if isinstance(days, bool) or not isinstance(days, int) or days <= 0:
            raise ValueError("days must be a positive integer")
        balance = decimal_value(payload["balance"], "balance")
        principals = [balance] * days
        basis = "stable_balance_estimate"
        result["warnings"].append(
            "This is an estimate because a single balance does not establish all daily balances."
        )
    else:
        result["missing_evidence"].append(
            "A statement period and daily balances, or a clearly labeled stable-balance estimate, are needed to calculate interest."
        )

    expected_interest = None
    if principals is not None:
        expected_interest = compound_interest(principals, expected_apy)
        result["interest_calculation"] = {
            "basis": basis,
            "day_count": len(principals),
            "expected_interest_unrounded": as_number(expected_interest),
            "expected_interest_rounded": as_number(
                expected_interest.quantize(CENT, rounding=ROUND_HALF_UP)
            ),
        }

    actual_interest = payload.get("actual_interest")
    if actual_interest is not None:
        actual = decimal_value(actual_interest, "actual_interest")
        if expected_interest is None:
            result["missing_evidence"].append(
                "Actual interest was supplied, but there is no reliable period/balance calculation to compare it with."
            )
        else:
            difference = expected_interest - actual
            rounded_difference = difference.quantize(CENT, rounding=ROUND_HALF_UP)
            result["interest_calculation"]["actual_interest"] = as_number(actual)
            result["interest_calculation"]["expected_minus_actual"] = as_number(rounded_difference)
            if abs(rounded_difference) <= CENT:
                result["discrepancy_status"] = "interest_matches_within_one_cent"
            elif basis == "daily_balance_calculation":
                result["discrepancy_status"] = "possible_confirmed_interest_discrepancy"
            else:
                result["discrepancy_status"] = "possible_interest_discrepancy_estimate_only"
                result["warnings"].append(
                    "Do not use an estimate alone as a credit amount; verify complete daily balances and statement dates."
                )

    return result


if __name__ == "__main__":
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            raise ValueError("stdin must contain one JSON object")
        output = main(json.loads(raw))
        print(json.dumps(output, sort_keys=True))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
