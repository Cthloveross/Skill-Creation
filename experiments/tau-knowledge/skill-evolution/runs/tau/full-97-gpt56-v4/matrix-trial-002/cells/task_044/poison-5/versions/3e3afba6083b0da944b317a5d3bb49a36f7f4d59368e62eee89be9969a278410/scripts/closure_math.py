#!/usr/bin/env python3
"""Closure date and rewards-value calculations; JSON stdin to JSON stdout."""
import json
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation


def parse_date(value: object, field: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a date string")
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"{field} must use MM/DD/YYYY or YYYY-MM-DD")


def plus_one_year(value: date) -> date:
    try:
        return value.replace(year=value.year + 1)
    except ValueError:  # Feb. 29 to a non-leap year
        return value.replace(year=value.year + 1, month=2, day=28)


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        opened = parse_date(payload.get("opened_on"), "opened_on")
        today = parse_date(payload.get("today"), "today")
        if opened > today:
            raise ValueError("opened_on cannot be after today")
        elapsed_days = (today - opened).days
        result = {
            "elapsed_days": elapsed_days,
            "meets_60_day_minimum": elapsed_days >= 60,
            "fee_waiver_expiration_date": plus_one_year(today).strftime("%m/%d/%Y"),
        }
        if "optional_rewards_points" in payload and payload["optional_rewards_points"] is not None:
            try:
                points = Decimal(str(payload["optional_rewards_points"]))
            except (InvalidOperation, ValueError):
                raise ValueError("optional_rewards_points must be numeric")
            if not points.is_finite() or points < 0:
                raise ValueError("optional_rewards_points must be a nonnegative finite number")
            if points != points.to_integral_value():
                raise ValueError("optional_rewards_points must be a whole number")
            value = (points * Decimal("0.01")).quantize(Decimal("0.01"))
            result["rewards_points"] = int(points)
            result["cash_back_statement_credit_value_usd"] = format(value, ".2f")
        print(json.dumps(result, separators=(",", ":")))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, separators=(",", ":")))
        sys.exit(2)


if __name__ == "__main__":
    main()
