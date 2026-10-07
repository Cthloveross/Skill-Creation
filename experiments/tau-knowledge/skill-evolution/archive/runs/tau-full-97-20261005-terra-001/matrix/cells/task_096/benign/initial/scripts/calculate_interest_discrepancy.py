#!/usr/bin/env python3
"""Calculate documented APY components and a daily-compounded interest comparison.

Input JSON schema:
{
  "savings_type": "Bronze Account" | "Gold Plus Account",
  "checking_accounts": [{"type": str, "active": bool}, ...],
  "credit_cards": [{"type": str, "active": bool}, ...],
  "daily_balances": [number|string, ...],
  // Or use both constant_balance and days instead of daily_balances:
  "constant_balance": number|string,
  "days": integer,
  "actual_interest": number|string,              // optional
  "daily_rate_method": "effective_apy" | "nominal_apy_div_365" // optional
}

All money values must be nonnegative. Daily balances must cover exactly the
interest-crediting period and be eligible end-of-day savings balances. Output is
one JSON object. This script performs no tool calls and makes no account changes.
"""

import json
import math
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

CENT = Decimal("0.01")
DAYS_PER_YEAR = Decimal("365")


def emit(obj):
    print(json.dumps(obj, sort_keys=True, separators=(",", ":")))


def dec(value, field):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"{field} must be a valid number")
    if not result.is_finite():
        raise ValueError(f"{field} must be finite")
    return result


def money(value):
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def load_policy():
    path = Path(__file__).resolve().parent.parent / "references" / "apy_policy.json"
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def active_types(items, label):
    if not isinstance(items, list):
        raise ValueError(f"{label} must be a list")
    result = []
    for index, item in enumerate(items):
        if not isinstance(item, dict) or not isinstance(item.get("type"), str):
            raise ValueError(f"{label}[{index}] must contain a string type")
        if item.get("active") is True:
            result.append(item["type"])
    return result


def get_balances(data):
    has_daily = "daily_balances" in data
    has_constant = "constant_balance" in data or "days" in data
    if has_daily and has_constant:
        raise ValueError("provide daily_balances or constant_balance with days, not both")
    if has_daily:
        raw = data["daily_balances"]
        if not isinstance(raw, list) or not raw:
            raise ValueError("daily_balances must be a nonempty list")
        balances = [dec(x, "daily_balances") for x in raw]
    else:
        if "constant_balance" not in data or "days" not in data:
            raise ValueError("provide daily_balances or both constant_balance and days")
        days = data["days"]
        if not isinstance(days, int) or isinstance(days, bool) or days <= 0:
            raise ValueError("days must be a positive integer")
        balance = dec(data["constant_balance"], "constant_balance")
        balances = [balance] * days
    if any(balance < 0 for balance in balances):
        raise ValueError("all balances must be nonnegative")
    return balances


def daily_rate(apy_percent, method):
    annual = float(apy_percent) / 100.0
    if method == "effective_apy":
        return Decimal(str(math.pow(1.0 + annual, 1.0 / 365.0) - 1.0))
    if method == "nominal_apy_div_365":
        return apy_percent / Decimal("100") / DAYS_PER_YEAR
    raise ValueError("daily_rate_method must be effective_apy or nominal_apy_div_365")


def accrued_interest(balances, apy_percent, method):
    rate = daily_rate(apy_percent, method)
    accrued = Decimal("0")
    for balance in balances:
        accrued += (balance + accrued) * rate
    return accrued


def infer_apy(balances, actual_interest, method):
    """Numerically invert the same daily compounding model, in percentage points."""
    target = float(actual_interest)
    if target < 0:
        return None
    low, high = 0.0, 1000.0
    for _ in range(100):
        middle = (low + high) / 2.0
        calculated = float(accrued_interest(balances, Decimal(str(middle)), method))
        if calculated < target:
            low = middle
        else:
            high = middle
    return Decimal(str((low + high) / 2.0))


def main(data):
    if not isinstance(data, dict):
        raise ValueError("input must be a JSON object")
    policy = load_policy()
    savings_type = data.get("savings_type")
    if savings_type not in policy["base_apy_percent"]:
        return {
            "status": "insufficient_data",
            "reason": "unsupported_savings_type",
            "supported_savings_types": sorted(policy["base_apy_percent"].keys())
        }

    checking = active_types(data.get("checking_accounts", []), "checking_accounts")
    cards = active_types(data.get("credit_cards", []), "credit_cards")

    unknown_pairings = []
    known_boosts = []
    for pair in policy["qualifying_checking_savings_pairs"]:
        if pair["savings"] == savings_type and pair["checking"] in checking:
            if pair["boost_percent"] is None:
                unknown_pairings.append(pair["checking"])
            else:
                known_boosts.append((pair["checking"], Decimal(str(pair["boost_percent"]))))
    if unknown_pairings:
        return {
            "status": "insufficient_data",
            "reason": "qualifying_checking_boost_not_documented",
            "savings_type": savings_type,
            "checking_accounts_requiring_rate_confirmation": sorted(unknown_pairings),
            "message": "A qualifying checking pairing is present but its boost percentage is not documented in this package. The highest checking boost cannot be selected safely."
        }

    base = Decimal(str(policy["base_apy_percent"][savings_type]))
    if known_boosts:
        selected_checking, checking_boost = max(known_boosts, key=lambda item: item[1])
    else:
        selected_checking, checking_boost = None, Decimal("0")

    card_table = policy["credit_card_bonus_percent"][savings_type]
    card_candidates = [(card, Decimal(str(card_table[card]))) for card in cards if card in card_table]
    if card_candidates:
        selected_card, card_bonus = max(card_candidates, key=lambda item: item[1])
    else:
        selected_card, card_bonus = None, Decimal("0")

    expected_apy = base + checking_boost + card_bonus
    balances = get_balances(data)
    method = data.get("daily_rate_method", "effective_apy")
    expected_interest = accrued_interest(balances, expected_apy, method)
    result = {
        "status": "ok",
        "savings_type": savings_type,
        "days": len(balances),
        "daily_rate_method": method,
        "components_percent": {
            "base": float(base),
            "selected_checking_boost": float(checking_boost),
            "selected_credit_card_bonus": float(card_bonus)
        },
        "selected_checking_account": selected_checking,
        "selected_credit_card": selected_card,
        "expected_apy_percent": float(expected_apy),
        "expected_interest_unrounded": str(expected_interest.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)),
        "expected_interest_rounded": str(money(expected_interest)),
        "validation_notes": [
            "Only active input accounts were considered.",
            "Checking and card bonuses were each selected as a maximum, not summed within their category.",
            "Confirm that the supplied balance sequence and daily-rate convention match the credited statement period before authorizing a correction."
        ]
    }
    if "actual_interest" in data:
        actual = dec(data["actual_interest"], "actual_interest")
        if actual < 0:
            raise ValueError("actual_interest must be nonnegative")
        difference = money(expected_interest) - money(actual)
        implied = infer_apy(balances, actual, method)
        result.update({
            "actual_interest_rounded": str(money(actual)),
            "amount_difference_rounded": str(difference),
            "implied_actual_apy_percent": float(implied.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)),
            "credit_recommended": difference > Decimal("0")
        })
    else:
        result["credit_recommended"] = False
        result["validation_notes"].append("No actual interest was supplied, so no discrepancy or correction recommendation was calculated.")
    return result


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        emit(main(payload))
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        emit({"status": "insufficient_data", "reason": "invalid_input", "message": str(exc)})
    except Exception as exc:  # Keep script output machine-readable for runtime callers.
        emit({"status": "insufficient_data", "reason": "calculation_error", "message": str(exc)})
