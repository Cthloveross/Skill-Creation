#!/usr/bin/env python3
"""Calculate documented Silver Account daily interest inputs.

Reads one JSON object on stdin and writes one JSON object on stdout.

Input schema:
{
  "daily_balances": [{"date": "YYYY-MM-DD", "balance": "decimal"}, ...],
  "checking_bonuses": [0.25],
  "active_card_types": ["Green Rewards Card"],
  "relationship_eligible": true,
  "daily_rate_method": "effective_apy" | "apy_divided_by_day_count",
  "day_count": 365,
  "actual_interest": "decimal, optional",
  "actual_apy": "decimal, optional"
}

`checking_bonuses` must contain only boosts whose account pairing, active status,
linkage, and numeric value have already been verified. `active_card_types` must
contain only active, eligible cards under the same customer profile. The program
uses the highest member of each category; it does not decide eligibility.

The script does not infer statement cycles, daily balances, actual APY, linkage,
or a bank's rounding policy. It sums unrounded daily accruals and rounds the
cycle total to cents using ROUND_HALF_UP solely to produce a review candidate.
"""

import json
import sys
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, getcontext

getcontext().prec = 40

CARD_BONUSES = {
    "Bronze Rewards Card": Decimal("0"),
    "Silver Rewards Card": Decimal("0.1"),
    "Gold Rewards Card": Decimal("0.5"),
    "EcoCard": Decimal("2.2"),
    "Green Rewards Card": Decimal("0"),
    "Crypto-Cash Back Card": Decimal("0.5"),
    "Platinum Rewards Card": Decimal("0.2"),
    "Diamond Elite Card": Decimal("0.25"),
}
CENT = Decimal("0.01")


def decimal_value(value, field, errors):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        errors.append(f"{field} must be a decimal number")
        return None
    if not result.is_finite():
        errors.append(f"{field} must be finite")
        return None
    return result


def as_text(value):
    return format(value, "f")


def daily_periodic_rate(apy_percent, method, day_count):
    annual = apy_percent / Decimal("100")
    if method == "apy_divided_by_day_count":
        return annual / Decimal(day_count)
    # This is appropriate only when the supplied APY is an effective annual yield.
    return ((Decimal("1") + annual).ln() / Decimal(day_count)).exp() - Decimal("1")


def main(payload):
    errors = []
    warnings = [
        "Cycle interest is rounded only at the total. Confirm any institution-specific daily rounding before using this result for a credit."
    ]

    balances = payload.get("daily_balances")
    if not isinstance(balances, list) or not balances:
        errors.append("daily_balances must be a nonempty array")
        balances = []

    relationship = payload.get("relationship_eligible")
    if not isinstance(relationship, bool):
        errors.append("relationship_eligible must be a boolean")
        relationship = False

    method = payload.get("daily_rate_method")
    if method not in {"effective_apy", "apy_divided_by_day_count"}:
        errors.append("daily_rate_method must be effective_apy or apy_divided_by_day_count")

    day_count = payload.get("day_count", 365)
    if not isinstance(day_count, int) or isinstance(day_count, bool) or day_count <= 0:
        errors.append("day_count must be a positive integer")
        day_count = 365

    raw_checking = payload.get("checking_bonuses", [])
    checking_bonuses = []
    if not isinstance(raw_checking, list):
        errors.append("checking_bonuses must be an array")
    else:
        for index, value in enumerate(raw_checking):
            parsed = decimal_value(value, f"checking_bonuses[{index}]", errors)
            if parsed is not None:
                if parsed < 0:
                    errors.append(f"checking_bonuses[{index}] cannot be negative")
                else:
                    checking_bonuses.append(parsed)

    raw_cards = payload.get("active_card_types", [])
    card_bonuses = []
    unknown_cards = []
    if not isinstance(raw_cards, list) or not all(isinstance(x, str) for x in raw_cards):
        errors.append("active_card_types must be an array of strings")
    else:
        for card in raw_cards:
            if card in CARD_BONUSES:
                card_bonuses.append(CARD_BONUSES[card])
            else:
                unknown_cards.append(card)
    if unknown_cards:
        errors.append(
            "No documented Silver APY bonus is packaged for active_card_types: "
            + ", ".join(unknown_cards)
        )

    checking_bonus = max(checking_bonuses, default=Decimal("0"))
    card_bonus = max(card_bonuses, default=Decimal("0"))
    relationship_bonus = Decimal("0.025") if relationship else Decimal("0")

    parsed_days = []
    prior_date = None
    for index, item in enumerate(balances):
        if not isinstance(item, dict):
            errors.append(f"daily_balances[{index}] must be an object")
            continue
        try:
            current_date = date.fromisoformat(str(item.get("date")))
        except (TypeError, ValueError):
            errors.append(f"daily_balances[{index}].date must be YYYY-MM-DD")
            continue
        balance = decimal_value(item.get("balance"), f"daily_balances[{index}].balance", errors)
        if balance is None:
            continue
        if balance < 0:
            errors.append(f"daily_balances[{index}].balance cannot be negative")
            continue
        if prior_date is not None and current_date != prior_date + timedelta(days=1):
            errors.append("daily_balances must be chronological and contain every consecutive cycle day")
        prior_date = current_date
        parsed_days.append((current_date, balance))

    actual_interest = None
    if "actual_interest" in payload and payload["actual_interest"] is not None:
        actual_interest = decimal_value(payload["actual_interest"], "actual_interest", errors)

    actual_apy = None
    if "actual_apy" in payload and payload["actual_apy"] is not None:
        actual_apy = decimal_value(payload["actual_apy"], "actual_apy", errors)

    daily_rows = []
    expected_total = Decimal("0")
    expected_apys = []
    if not errors:
        for current_date, balance in parsed_days:
            base_apy = Decimal("4.0") if balance >= Decimal("10000") else Decimal("2.5")
            expected_apy = base_apy + checking_bonus + card_bonus + relationship_bonus
            try:
                rate = daily_periodic_rate(expected_apy, method, day_count)
            except (InvalidOperation, ValueError, OverflowError):
                errors.append("Unable to calculate daily rate with supplied APY convention")
                break
            interest = balance * rate
            expected_total += interest
            expected_apys.append(expected_apy)
            daily_rows.append({
                "date": current_date.isoformat(),
                "ending_balance": as_text(balance),
                "base_apy": as_text(base_apy),
                "expected_apy": as_text(expected_apy),
                "daily_periodic_rate": as_text(rate),
                "accrual_unrounded": as_text(interest),
            })

    expected_rounded = expected_total.quantize(CENT, rounding=ROUND_HALF_UP) if not errors else None
    difference = None
    credit_amount = None
    if expected_rounded is not None and actual_interest is not None:
        actual_rounded = actual_interest.quantize(CENT, rounding=ROUND_HALF_UP)
        difference = expected_rounded - actual_rounded
        if difference > 0:
            credit_amount = difference.quantize(CENT, rounding=ROUND_HALF_UP)

    report_expected_apy = None
    if expected_apys and len(set(expected_apys)) == 1:
        report_expected_apy = expected_apys[0]
    elif expected_apys:
        warnings.append(
            "Expected APY varied by day. The discrepancy-report tool accepts one expected_apy number; obtain an approved reporting convention."
        )

    if actual_apy is None:
        warnings.append("actual_apy was not supplied from an authoritative source; do not submit a discrepancy report yet.")
    if actual_interest is None:
        warnings.append("actual_interest was not supplied; an underpayment and credit amount cannot be determined.")
    if method == "apy_divided_by_day_count":
        warnings.append("apy_divided_by_day_count is not implied by this helper; use it only when the applicable account convention confirms it.")

    output = {
        "errors": errors,
        "warnings": warnings,
        "days": len(parsed_days),
        "checking_bonus_selected": as_text(checking_bonus),
        "card_bonus_selected": as_text(card_bonus),
        "relationship_bonus": as_text(relationship_bonus),
        "daily_rate_method": method,
        "day_count": day_count,
        "daily_accruals": daily_rows,
        "expected_interest_unrounded": as_text(expected_total) if not errors else None,
        "expected_interest_rounded": as_text(expected_rounded) if expected_rounded is not None else None,
        "actual_interest": as_text(actual_interest.quantize(CENT, rounding=ROUND_HALF_UP)) if actual_interest is not None else None,
        "difference_rounded": as_text(difference) if difference is not None else None,
        "credit_amount": as_text(credit_amount) if credit_amount is not None else None,
        "report_expected_apy": as_text(report_expected_apy) if report_expected_apy is not None else None,
        "report_actual_apy": as_text(actual_apy) if actual_apy is not None else None,
    }
    return output


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be a JSON object")
        result = main(data)
    except Exception as exc:  # Keep the declared JSON-only output contract on malformed input.
        result = {"errors": [f"Invalid input: {exc}"], "warnings": [], "credit_amount": None}
    json.dump(result, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")
