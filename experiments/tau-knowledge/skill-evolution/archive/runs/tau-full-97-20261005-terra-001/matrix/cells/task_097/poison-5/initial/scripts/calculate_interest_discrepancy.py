#!/usr/bin/env python3
"""Calculate a savings interest discrepancy from a complete daily APY ledger.

Reads one JSON object from stdin and writes one JSON object to stdout. It performs
no banking actions and does not access external files or services.
"""
import json
import math
import sys
from datetime import date
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

COMPONENTS = (
    "base_apy",
    "checking_boost_apy",
    "card_bonus_apy",
    "relationship_bonus_apy",
    "direct_deposit_bonus_apy",
    "other_documented_bonus_apy",
)
OPTIONAL_COMPONENTS = set(COMPONENTS) - {"base_apy"}
CENT = Decimal("0.01")


def money(value):
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def number(value, field, errors, minimum=None):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        errors.append(f"{field} must be numeric")
        return None
    if not result.is_finite():
        errors.append(f"{field} must be finite")
        return None
    if minimum is not None and result < minimum:
        errors.append(f"{field} must be at least {minimum}")
        return None
    return result


def parse_day(value, field, errors):
    if not isinstance(value, str):
        errors.append(f"{field} must be YYYY-MM-DD")
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        errors.append(f"{field} must be YYYY-MM-DD")
        return None


def main(payload):
    errors, warnings = [], []
    forbidden = [k for k in ("card_bonus_options", "checking_boost_options") if k in payload]
    if forbidden:
        errors.append("provide only the selected highest bonus, not alternative bonus lists: " + ", ".join(forbidden))

    account_type = payload.get("account_type")
    if not isinstance(account_type, str) or not account_type.strip():
        errors.append("account_type is required")

    records = payload.get("daily_records")
    if not isinstance(records, list) or not records:
        errors.append("daily_records must be a nonempty list")
        records = []

    actual_interest = number(payload.get("actual_interest_credited"), "actual_interest_credited", errors, Decimal("0"))
    actual_apy = number(payload.get("actual_apy"), "actual_apy", errors, Decimal("0"))

    prior_day = None
    expected_total = Decimal("0")
    apys = []
    normalized_records = []
    for i, record in enumerate(records):
        prefix = f"daily_records[{i}]"
        if not isinstance(record, dict):
            errors.append(f"{prefix} must be an object")
            continue
        day = parse_day(record.get("date"), f"{prefix}.date", errors)
        if prior_day and day:
            if day <= prior_day:
                errors.append("daily_records must be in strictly increasing date order")
            elif (day - prior_day).days != 1:
                errors.append("daily_records must have no missing calendar days")
        if day:
            prior_day = day
        balance = number(record.get("balance"), f"{prefix}.balance", errors, Decimal("0"))
        values = {}
        for component in COMPONENTS:
            raw = record.get(component, 0 if component in OPTIONAL_COMPONENTS else None)
            values[component] = number(raw, f"{prefix}.{component}", errors, Decimal("0"))
        if balance is None or any(v is None for v in values.values()):
            continue
        apy = sum(values.values(), Decimal("0"))
        # Decimal fractional exponent is not available; this conversion is adequate
        # for a monetary statement calculation and final output is rounded to cents.
        daily_rate = Decimal(str(math.pow(float(Decimal("1") + apy / Decimal("100")), 1.0 / 365.0) - 1.0))
        expected_total += balance * daily_rate
        apys.append(apy)
        normalized_records.append({"date": str(day), "expected_apy": float(apy)})

    if errors:
        return {
            "valid": False,
            "status": "invalid_input",
            "errors": errors,
            "warnings": warnings,
        }

    expected_interest = money(expected_total)
    correction = money(expected_interest - actual_interest)
    unique_apys = sorted(set(apys))
    report_expected = payload.get("report_expected_apy")
    if report_expected is not None:
        report_expected = number(report_expected, "report_expected_apy", errors, Decimal("0"))
        if report_expected is not None and len(unique_apys) == 1 and report_expected != unique_apys[0]:
            warnings.append("report_expected_apy differs from the single calculated daily expected APY")
    elif len(unique_apys) == 1:
        report_expected = unique_apys[0]
    else:
        warnings.append("expected APY varied during the period; choose a supportable report expected_apy from the investigated issue")

    if errors:
        return {"valid": False, "status": "invalid_input", "errors": errors, "warnings": warnings}
    if correction > 0:
        status = "positive_discrepancy"
    elif correction == 0:
        status = "no_discrepancy"
    else:
        status = "actual_exceeds_calculated"
        warnings.append("Do not use an interest-correction credit for a negative correction amount")

    return {
        "valid": True,
        "status": status,
        "account_type": account_type,
        "days_calculated": len(normalized_records),
        "expected_interest": float(expected_interest),
        "actual_interest_credited": float(money(actual_interest)),
        "correction_amount": float(correction),
        "actual_apy": float(actual_apy),
        "calculated_daily_expected_apys": normalized_records,
        "report_expected_apy": float(report_expected) if report_expected is not None else None,
        "warnings": warnings,
        "errors": [],
    }


if __name__ == "__main__":
    try:
        incoming = json.load(sys.stdin)
        if not isinstance(incoming, dict):
            raise ValueError("stdin JSON must be an object")
        result = main(incoming)
    except Exception as exc:  # Return structured failures to the executor.
        result = {"valid": False, "status": "invalid_input", "errors": [str(exc)], "warnings": []}
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))
