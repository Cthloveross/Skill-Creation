#!/usr/bin/env python3
"""Calculate documented bank ATM fees from explicitly classified monthly events.
Reads one JSON object from stdin and writes one JSON object to stdout.
"""
import json
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")
VALID_CLASSES = {"purple", "light_blue", "dark_green", "evergreen"}
VALID_KINDS = {"out_of_network", "foreign"}


def money(value, field, nonnegative=True):
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValueError(f"{field} must be a decimal string or number")
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"{field} is not a valid decimal") from exc
    if not result.is_finite() or (nonnegative and result < 0) or (not nonnegative and result <= 0):
        comparator = "nonnegative" if nonnegative else "greater than zero"
        raise ValueError(f"{field} must be {comparator}")
    return result.quantize(CENT, rounding=ROUND_HALF_UP)


def expected_fee(account_class, kind, amount, ordinal):
    if account_class == "purple":
        return Decimal("2.50") if kind == "out_of_network" else Decimal("0.00")
    if account_class == "light_blue":
        if ordinal <= 2:
            return Decimal("0.00")
        return Decimal("2.50") if kind == "out_of_network" else Decimal("4.00")
    if account_class == "dark_green":
        if kind == "out_of_network":
            return max(amount * Decimal("0.01"), Decimal("1.50"))
        return min(amount * Decimal("0.025"), Decimal("6.00"))
    # evergreen
    if kind == "out_of_network":
        return min(amount * Decimal("0.01"), Decimal("2.50"))
    return max(amount * Decimal("0.02"), Decimal("3.00"))


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    account_class = payload.get("account_class")
    if account_class not in VALID_CLASSES:
        raise ValueError("account_class must be one of purple, light_blue, dark_green, evergreen")
    events = payload.get("events")
    if not isinstance(events, list) or not events:
        raise ValueError("events must be a nonempty array")

    parsed = []
    month_marker = None
    for index, event in enumerate(events):
        if not isinstance(event, dict):
            raise ValueError(f"events[{index}] must be an object")
        if event.get("classification") not in VALID_KINDS:
            raise ValueError(f"events[{index}].classification is invalid")
        if not isinstance(event.get("date"), str):
            raise ValueError(f"events[{index}].date must be MM/DD/YYYY")
        try:
            date = datetime.strptime(event["date"], "%m/%d/%Y").date()
        except ValueError as exc:
            raise ValueError(f"events[{index}].date must be MM/DD/YYYY") from exc
        marker = (date.year, date.month)
        if month_marker is None:
            month_marker = marker
        elif marker != month_marker:
            raise ValueError("all events must be from one calendar month")
        amount = money(event.get("withdrawal_amount"), f"events[{index}].withdrawal_amount", nonnegative=False)
        actual = None
        if "actual_bank_fee" in event and event["actual_bank_fee"] is not None:
            actual = money(event["actual_bank_fee"], f"events[{index}].actual_bank_fee")
        parsed.append((date, index, event["classification"], amount, actual))

    parsed.sort(key=lambda row: (row[0], row[1]))
    ordinals = {"out_of_network": 0, "foreign": 0}
    results = []
    for date, original_index, kind, amount, actual in parsed:
        ordinals[kind] += 1
        fee = expected_fee(account_class, kind, amount, ordinals[kind]).quantize(CENT, rounding=ROUND_HALF_UP)
        row = {
            "source_index": original_index,
            "date": date.strftime("%m/%d/%Y"),
            "classification": kind,
            "withdrawal_amount": f"{amount:.2f}",
            "monthly_classification_ordinal": ordinals[kind],
            "expected_bank_fee": f"{fee:.2f}",
        }
        if actual is not None:
            row["actual_bank_fee"] = f"{actual:.2f}"
            row["difference_actual_minus_expected"] = f"{(actual - fee):.2f}"
        results.append(row)
    return {
        "account_class": account_class,
        "month": f"{month_marker[0]:04d}-{month_marker[1]:02d}",
        "events_processed": len(results),
        "results_chronological": results,
        "warning": "Results cover bank fees only. They do not identify ATM operator surcharges, determine Purple rebate eligibility, or authorize credits.",
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), separators=(",", ":")))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, separators=(",", ":")))
        sys.exit(1)
