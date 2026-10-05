#!/usr/bin/env python3
"""Select non-stacking Gold APY components and assess available interest evidence.

Read one JSON object from stdin and write one JSON object to stdout. This helper
performs no retrieval, file access, or banking action.
"""

import json
import math
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")
EPSILON = Decimal("0.000001")


def number(value, field, nonnegative=True):
    if value is None or isinstance(value, bool):
        raise ValueError(f"{field} must be a number")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be a number")
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    if nonnegative and result < 0:
        raise ValueError(f"{field} must not be negative")
    return result


def json_number(value):
    return float(value)


def select(entries, value_key, eligibility_key, category):
    if not isinstance(entries, list):
        raise ValueError(f"{category} must be an array")
    eligible = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(f"{category}[{index}] must be an object")
        if entry.get("active") is True and entry.get(eligibility_key) is True:
            label = entry.get("name")
            if not isinstance(label, str) or not label.strip():
                raise ValueError(f"{category}[{index}].name must be a nonempty string")
            eligible.append((label, number(entry.get(value_key), f"{category}[{index}].{value_key}")))
    if not eligible:
        return Decimal("0"), [], 0
    highest = max(value for _, value in eligible)
    return highest, [label for label, value in eligible if value == highest], len(eligible)


def daily_interest(principals, apy):
    """Return daily-compounded interest for supplied daily principal balances.

    The APY is treated as an effective annual yield. A complete daily-balance list
    is the reliable basis; a replicated single balance remains an estimate.
    """
    annual_fraction = float(apy / Decimal("100"))
    daily_rate = Decimal(str(math.pow(1.0 + annual_fraction, 1.0 / 365.0) - 1.0))
    return sum((principal * daily_rate for principal in principals), Decimal("0"))


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")

    base = number(payload.get("base_apy"), "base_apy")
    cards_raw = payload.get("credit_card_bonuses", [])
    checking_raw = payload.get("checking_boosts", [])
    card_bonus, card_names, card_count = select(
        cards_raw, "apy_bonus", "same_profile", "credit_card_bonuses"
    )
    checking_bonus, checking_names, checking_count = select(
        checking_raw, "apy_boost", "qualifying", "checking_boosts"
    )
    expected_apy = base + card_bonus + checking_bonus

    missing = []
    if not cards_raw:
        missing.append("No credit-card eligibility data was supplied.")
    elif card_count == 0:
        missing.append("No active same-profile eligible credit card was confirmed.")
    if not checking_raw:
        missing.append("No linked-checking eligibility data was supplied.")
    elif checking_count == 0:
        missing.append("No active qualifying linked checking account was confirmed.")

    output = {
        "expected_apy": json_number(expected_apy),
        "components": {
            "base_apy": json_number(base),
            "highest_credit_card_bonus": json_number(card_bonus),
            "highest_checking_boost": json_number(checking_bonus),
        },
        "selected_credit_card_bonus": {
            "selected_names": card_names,
            "tied_highest": len(card_names) > 1,
            "eligible_count": card_count,
        },
        "selected_checking_boost": {
            "selected_names": checking_names,
            "tied_highest": len(checking_names) > 1,
            "eligible_count": checking_count,
        },
        "apy_comparison": None,
        "interest_calculation": None,
        "discrepancy_status": "not_assessable",
        "missing_evidence": missing,
        "warnings": [],
    }

    if payload.get("displayed_apy") is not None:
        displayed = number(payload["displayed_apy"], "displayed_apy")
        difference = expected_apy - displayed
        output["apy_comparison"] = {
            "displayed_apy": json_number(displayed),
            "expected_minus_displayed_apy": json_number(difference),
            "matches_within_precision": abs(difference) <= EPSILON,
        }
        if abs(difference) > EPSILON:
            output["discrepancy_status"] = "possible_rate_discrepancy"

    principals = None
    basis = None
    if payload.get("daily_balances") is not None:
        values = payload["daily_balances"]
        if not isinstance(values, list) or not values:
            raise ValueError("daily_balances must be a nonempty array when supplied")
        principals = [number(value, f"daily_balances[{index}]") for index, value in enumerate(values)]
        basis = "daily_balance_calculation"
    elif payload.get("days") is not None or payload.get("balance") is not None:
        if payload.get("days") is None or payload.get("balance") is None:
            raise ValueError("days and balance must be supplied together")
        days = payload["days"]
        if isinstance(days, bool) or not isinstance(days, int) or days <= 0:
            raise ValueError("days must be a positive integer")
        balance = number(payload["balance"], "balance")
        principals = [balance] * days
        basis = "stable_balance_estimate"
        output["warnings"].append(
            "A single balance produces an estimate, not a verified daily-balance calculation."
        )
    else:
        output["missing_evidence"].append(
            "Statement day count and daily balances, or a clearly labeled stable-balance estimate, are needed to calculate interest."
        )

    expected_interest = None
    if principals is not None:
        expected_interest = daily_interest(principals, expected_apy)
        output["interest_calculation"] = {
            "basis": basis,
            "day_count": len(principals),
            "expected_interest_unrounded": json_number(expected_interest),
            "expected_interest_rounded": json_number(expected_interest.quantize(CENT, rounding=ROUND_HALF_UP)),
        }

    if payload.get("actual_interest") is not None:
        actual = number(payload["actual_interest"], "actual_interest")
        if expected_interest is None:
            output["missing_evidence"].append(
                "Actual interest was supplied, but no period/balance calculation is available for comparison."
            )
        else:
            difference = (expected_interest - actual).quantize(CENT, rounding=ROUND_HALF_UP)
            output["interest_calculation"]["actual_interest"] = json_number(actual)
            output["interest_calculation"]["expected_minus_actual"] = json_number(difference)
            if abs(difference) <= CENT:
                output["discrepancy_status"] = "interest_matches_within_one_cent"
            elif basis == "daily_balance_calculation":
                output["discrepancy_status"] = "possible_confirmed_interest_discrepancy"
            else:
                output["discrepancy_status"] = "possible_interest_discrepancy_estimate_only"
                output["warnings"].append(
                    "Do not use an estimate alone as an interest-correction amount."
                )

    return output


if __name__ == "__main__":
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            raise ValueError("stdin must contain one JSON object")
        print(json.dumps(main(json.loads(raw)), sort_keys=True))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
