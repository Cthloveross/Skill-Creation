#!/usr/bin/env python3
"""Analyze a fully evidenced Silver Account interest cycle.

Input JSON schema is documented in SKILL.md. Output is a JSON object and never
performs banking actions. Monetary inputs are accepted as JSON numbers/strings.
"""
import json
import math
import sys
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")
DAYS_PER_YEAR = Decimal("365")


def decimal_value(value, field, errors, allow_zero=True):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        errors.append(f"{field} must be numeric")
        return None
    if not result.is_finite():
        errors.append(f"{field} must be finite")
        return None
    if result < 0 or (not allow_zero and result <= 0):
        errors.append(f"{field} must be {'positive' if not allow_zero else 'nonnegative'}")
        return None
    return result


def daily_rate(apy):
    # Decimal has no portable fractional exponent, so calculate at sufficient
    # float precision and convert immediately for decimal money arithmetic.
    return Decimal(str(math.expm1(math.log1p(float(apy) / 100.0) / 365.0)))


def accrued_interest(rows, checking_boost, card_bonus, relationship_bonus):
    """Return unrounded daily-compounded interest and each day's nominal APY."""
    accrued = Decimal("0")
    apys = []
    for row in rows:
        base = row["high_apy"] if row["balance"] >= row["threshold"] else row["low_apy"]
        apy = base + checking_boost + card_bonus + relationship_bonus
        # Daily ledger balances generally exclude accrued-but-unposted interest.
        # Carry accrued interest so the documented daily compounding is reflected.
        accrued += (row["balance"] + accrued) * daily_rate(apy)
        apys.append(apy)
    return accrued, apys


def infer_apy(rows, target_interest, checking_boost, card_bonus, relationship_bonus):
    """Solve for a uniform adjustment to the tier APY that matches paid interest.

    The returned annual percent is an effective, balance-weighted applied APY,
    suitable only when an actual APY is not recorded separately.
    """
    if target_interest <= 0:
        return Decimal("0")
    low, high = Decimal("0"), Decimal("1000")
    for _ in range(100):
        mid = (low + high) / 2
        accrued = Decimal("0")
        for row in rows:
            # Uniform inferred APY is used solely to express the actual payment.
            accrued += (row["balance"] + accrued) * daily_rate(mid)
        if accrued < target_interest:
            low = mid
        else:
            high = mid
    return (low + high) / 2


def output_number(value, places=6):
    return float(value.quantize(Decimal("1").scaleb(-places), rounding=ROUND_HALF_UP))


def main(payload):
    errors = []
    if payload.get("daily_balances_complete") is not True:
        return {
            "status": "insufficient_data",
            "missing": ["daily_balances_complete must be true after the full statement-cycle history is verified"],
            "actions": ["Do not credit or report until the statement-cycle daily balances and posted interest credit are established."]
        }

    raw_rows = payload.get("daily_balances")
    if not isinstance(raw_rows, list) or not raw_rows:
        return {"status": "insufficient_data", "missing": ["daily_balances"]}

    actual = decimal_value(payload.get("actual_interest_credit"), "actual_interest_credit", errors, allow_zero=True)
    threshold = decimal_value(payload.get("tier_threshold"), "tier_threshold", errors, allow_zero=True)
    low_apy = decimal_value(payload.get("low_tier_apy"), "low_tier_apy", errors)
    high_apy = decimal_value(payload.get("high_tier_apy"), "high_tier_apy", errors)
    rows = []
    seen_dates = set()
    for index, item in enumerate(raw_rows):
        if not isinstance(item, dict):
            errors.append(f"daily_balances[{index}] must be an object")
            continue
        raw_date = item.get("date")
        try:
            parsed = date.fromisoformat(str(raw_date))
            if parsed in seen_dates:
                errors.append(f"duplicate daily balance date: {raw_date}")
            seen_dates.add(parsed)
        except (TypeError, ValueError):
            errors.append(f"daily_balances[{index}].date must be YYYY-MM-DD")
            parsed = None
        balance = decimal_value(item.get("balance"), f"daily_balances[{index}].balance", errors)
        if parsed is not None and balance is not None:
            rows.append({"date": parsed, "balance": balance})

    if errors:
        return {"status": "invalid_input", "errors": errors}
    rows.sort(key=lambda row: row["date"])
    for previous, current in zip(rows, rows[1:]):
        if (current["date"] - previous["date"]).days != 1:
            return {"status": "insufficient_data", "missing": ["daily_balances must include every consecutive statement-cycle day"]}

    checking_boosts = []
    for index, candidate in enumerate(payload.get("checking_candidates", [])):
        if not isinstance(candidate, dict):
            return {"status": "invalid_input", "errors": [f"checking_candidates[{index}] must be an object"]}
        if candidate.get("active") is True and candidate.get("linked") is True and candidate.get("qualifying") is True:
            boost = decimal_value(candidate.get("boost_apy"), f"checking_candidates[{index}].boost_apy", errors)
            if boost is not None:
                checking_boosts.append((boost, str(candidate.get("name", "unnamed checking account"))))

    card_bonuses = []
    for index, candidate in enumerate(payload.get("card_candidates", [])):
        if not isinstance(candidate, dict):
            return {"status": "invalid_input", "errors": [f"card_candidates[{index}] must be an object"]}
        if candidate.get("active") is True and candidate.get("applicable") is True:
            bonus = decimal_value(candidate.get("bonus_apy"), f"card_candidates[{index}].bonus_apy", errors)
            if bonus is not None:
                card_bonuses.append((bonus, str(candidate.get("name", "unnamed card"))))

    relationship = payload.get("relationship", {})
    if not isinstance(relationship, dict):
        errors.append("relationship must be an object")
        relationship = {}
    relationship_bonus = Decimal("0")
    if relationship.get("eligible") is True:
        relationship_bonus = decimal_value(relationship.get("bonus_apy"), "relationship.bonus_apy", errors)
        if relationship_bonus is None:
            relationship_bonus = Decimal("0")
    if errors:
        return {"status": "invalid_input", "errors": errors}

    checking_boost, checking_name = max(checking_boosts, default=(Decimal("0"), None), key=lambda pair: pair[0])
    card_bonus, card_name = max(card_bonuses, default=(Decimal("0"), None), key=lambda pair: pair[0])
    expected_unrounded, daily_apys = accrued_interest(rows, checking_boost, card_bonus, relationship_bonus)
    expected_paid = expected_unrounded.quantize(CENT, rounding=ROUND_HALF_UP)
    difference = (expected_paid - actual).quantize(CENT, rounding=ROUND_HALF_UP)

    # A balance-weighted nominal APY expresses variable tier results in the
    # single numeric field required by the discrepancy-report tool.
    balance_total = sum((row["balance"] for row in rows), Decimal("0"))
    if balance_total > 0:
        report_expected_apy = sum((row["balance"] * apy for row, apy in zip(rows, daily_apys)), Decimal("0")) / balance_total
    else:
        report_expected_apy = daily_apys[0]
    actual_inferred = infer_apy(rows, actual, checking_boost, card_bonus, relationship_bonus)
    variable = len(set(daily_apys)) > 1

    result = {
        "status": "ready_for_correction" if difference > 0 else "no_underpayment",
        "cycle_start": rows[0]["date"].isoformat(),
        "cycle_end": rows[-1]["date"].isoformat(),
        "days": len(rows),
        "components": {
            "highest_checking_boost_apy": output_number(checking_boost),
            "selected_checking_account": checking_name,
            "highest_card_bonus_apy": output_number(card_bonus),
            "selected_card": card_name,
            "relationship_bonus_apy": output_number(relationship_bonus)
        },
        "expected_interest": output_number(expected_paid, 2),
        "actual_interest_credit": output_number(actual, 2),
        "amount_difference": output_number(max(difference, Decimal("0")), 2),
        "report_expected_apy": output_number(report_expected_apy),
        "actual_apy_inferred": output_number(actual_inferred),
        "rate_varies_by_day": variable,
        "notes": []
    }
    if variable:
        result["notes"].append("The balance crossed a tier or otherwise produced multiple daily expected APYs; report_expected_apy is balance-weighted. Retain the daily calculation for backend review.")
    if difference <= 0:
        result["notes"].append("No positive underpayment was calculated. Do not apply an interest-correction credit or submit an interest-discrepancy report.")
    else:
        result["notes"].append("Apply exactly amount_difference as an interest_correction credit, confirm success, then submit the discrepancy report.")
    return result


if __name__ == "__main__":
    try:
        incoming = json.load(sys.stdin)
        if not isinstance(incoming, dict):
            raise ValueError("stdin JSON must be an object")
        print(json.dumps(main(incoming), separators=(",", ":")))
    except Exception as exc:
        print(json.dumps({"status": "invalid_input", "errors": [str(exc)]}, separators=(",", ":")))
