#!/usr/bin/env python3
"""Calculate supported savings APY components and a daily-compounded correction.

Reads one JSON object from stdin and writes one JSON object to stdout.  This
helper is intentionally limited to product rates supported by its Skill.
"""
import json
import math
import sys
from decimal import Decimal, ROUND_HALF_UP

BASE_APY = {
    "Bronze Account": 2.00,
    "Gold Plus Account": 6.00,
}

CHECKING_RATES = {
    "Bronze Account": {
        "Bluest Account": 0.70,
        "Green Fee-Free Account": 0.40,
    },
    "Gold Plus Account": {
        "Gold Years Account": 0.50,
        "Green Fee-Free Account": 0.35,
    },
}

CARD_RATES = {
    "Bronze Account": {
        "Bronze Rewards Card": 0.10,
        "Silver Rewards Card": 0.00,
        "Gold Rewards Card": 0.25,
        "EcoCard": 0.00,
        "Green Rewards Card": 0.20,
        "Crypto-Cash Back Card": 0.30,
        "Platinum Rewards Card": 0.55,
        "Diamond Elite Card": 0.15,
    },
    "Gold Plus Account": {
        "Bronze Rewards Card": 0.15,
        "Silver Rewards Card": 0.10,
        "Gold Rewards Card": 0.35,
        "Platinum Rewards Card": 0.20,
        "Diamond Elite Card": 0.25,
        "EcoCard": 0.10,
        "Green Rewards Card": 0.05,
        "Crypto-Cash Back Card": 0.30,
    },
}


def number(value, field, allow_zero=True):
    if isinstance(value, bool):
        raise ValueError(f"{field} must be numeric")
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be numeric")
    if not math.isfinite(result) or (result < 0 if allow_zero else result <= 0):
        qualifier = "nonnegative" if allow_zero else "positive"
        raise ValueError(f"{field} must be a finite {qualifier} number")
    return result


def active(items, type_field):
    if not isinstance(items, list):
        raise ValueError(f"{type_field}s must be an array")
    result = []
    for item in items:
        if isinstance(item, str):
            result.append(item)
        elif isinstance(item, dict):
            name = item.get(type_field)
            status = str(item.get("status", "ACTIVE")).upper()
            if isinstance(name, str) and status == "ACTIVE":
                result.append(name)
        else:
            raise ValueError(f"each {type_field} entry must be a string or object")
    return result


def compounded_interest(balances, apy_percent):
    """Accrue uncredited interest daily on principal plus prior accrual."""
    daily_rate = (1.0 + apy_percent / 100.0) ** (1.0 / 365.0) - 1.0
    accrued = 0.0
    for balance in balances:
        accrued += (balance + accrued) * daily_rate
    return accrued


def equivalent_apy(balances, actual_interest):
    """Find the APY that produces actual_interest over the supplied schedule."""
    if actual_interest == 0:
        return 0.0
    low, high = 0.0, 100.0
    while compounded_interest(balances, high) < actual_interest and high < 1_000_000:
        high *= 2.0
    if high >= 1_000_000 and compounded_interest(balances, high) < actual_interest:
        raise ValueError("actual interest is outside the supported APY solve range")
    for _ in range(100):
        midpoint = (low + high) / 2.0
        if compounded_interest(balances, midpoint) < actual_interest:
            low = midpoint
        else:
            high = midpoint
    return (low + high) / 2.0


def cents(value):
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def incomplete(reason, details=None):
    output = {"status": "insufficient_evidence", "reason": reason}
    if details is not None:
        output["details"] = details
    return output


def main(payload):
    savings_type = payload.get("savings_type")
    if savings_type not in BASE_APY:
        return incomplete("unsupported_savings_type")

    unspecified = payload.get("qualifying_checkings_without_documented_rate", [])
    if not isinstance(unspecified, list) or not all(isinstance(x, str) for x in unspecified):
        raise ValueError("qualifying_checkings_without_documented_rate must be an array of strings")
    if unspecified:
        return incomplete("qualifying_checking_rate_not_documented", unspecified)

    checks = active(payload.get("checking_accounts", []), "account_type")
    cards = active(payload.get("credit_cards", []), "card_type")
    raw_balances = payload.get("daily_balances")
    if not isinstance(raw_balances, list) or not raw_balances:
        return incomplete("exact_daily_balances_required")
    balances = [number(value, "daily_balances entry") for value in raw_balances]
    actual_interest = number(payload.get("actual_interest_credit"), "actual_interest_credit")

    check_candidates = [
        (name, CHECKING_RATES[savings_type][name])
        for name in checks if name in CHECKING_RATES[savings_type]
    ]
    card_candidates = [
        (name, CARD_RATES[savings_type][name])
        for name in cards if name in CARD_RATES[savings_type]
    ]
    selected_check = max(check_candidates, key=lambda item: item[1], default=(None, 0.0))
    selected_card = max(card_candidates, key=lambda item: item[1], default=(None, 0.0))
    expected_apy = BASE_APY[savings_type] + selected_check[1] + selected_card[1]
    expected_interest_unrounded = compounded_interest(balances, expected_apy)
    expected_interest = cents(expected_interest_unrounded)
    correction = cents(expected_interest - actual_interest)
    actual_apy = equivalent_apy(balances, actual_interest)

    return {
        "status": "ready_for_review",
        "days": len(balances),
        "base_apy_percent": BASE_APY[savings_type],
        "selected_checking": selected_check[0],
        "checking_boost_percent": selected_check[1],
        "selected_credit_card": selected_card[0],
        "credit_card_bonus_percent": selected_card[1],
        "expected_apy_percent": round(expected_apy, 8),
        "actual_apy_percent": round(actual_apy, 8),
        "expected_interest": expected_interest,
        "actual_interest_credit": cents(actual_interest),
        "correction_amount": correction,
        "action": (
            "apply_interest_correction_then_submit_report" if correction > 0
            else "no_credit_due" if correction == 0
            else "do_not_debit; preserve_evidence_for_review"
        ),
        "assumptions": [
            "Each daily balance is the eligible principal balance for that calendar day.",
            "The target monthly interest credit is excluded from the supplied daily balances.",
            "Interest compounds daily and is rounded only at period end for this calculation."
        ],
    }


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("stdin must contain one JSON object")
        print(json.dumps(main(data), sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "invalid_input", "reason": str(error)}, sort_keys=True))
