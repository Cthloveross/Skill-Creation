#!/usr/bin/env python3
"""Calculate daily-compounded interest from a complete verified balance series.

Input JSON: annual_apy_percent, daily_balances, optional posted_interest, optional
365-day day_count, and optional rate_basis (apy_effective or nominal_annual_rate).
Output JSON contains unrounded and cent-rounded expected interest and, if supplied,
the expected-minus-posted difference. No banking action is performed.
"""
import json
import sys
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext

CENTS = Decimal("0.01")


def text(value):
    return format(value, "f")


def as_decimal(value, field):
    if isinstance(value, bool):
        raise ValueError(field + " must be a number or numeric string")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(field + " must be a number or numeric string")


def fail(message):
    print(json.dumps({"ok": False, "error": message}, sort_keys=True))
    return 2


def main():
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise ValueError("input must be a JSON object")
        annual_percent = as_decimal(request.get("annual_apy_percent"), "annual_apy_percent")
        if annual_percent < 0:
            raise ValueError("annual_apy_percent cannot be negative")
        raw_days = request.get("daily_balances")
        if not isinstance(raw_days, list) or not raw_days:
            raise ValueError("daily_balances must be a nonempty array")
        balances, dates = [], []
        object_mode = all(isinstance(item, dict) for item in raw_days)
        if object_mode:
            for index, item in enumerate(raw_days):
                if "balance" not in item:
                    raise ValueError("daily_balances[%d] is missing balance" % index)
                balance = as_decimal(item["balance"], "daily_balances[%d].balance" % index)
                if balance < 0:
                    raise ValueError("daily balances cannot be negative")
                balances.append(balance)
                if "date" in item:
                    try:
                        dates.append(date.fromisoformat(str(item["date"])))
                    except ValueError:
                        raise ValueError("daily_balances[%d].date must be ISO YYYY-MM-DD" % index)
            if dates and len(dates) != len(balances):
                raise ValueError("when dates are supplied, every daily balance must include a date")
            if dates:
                for before, after in zip(dates, dates[1:]):
                    if after != before + timedelta(days=1):
                        raise ValueError("dated daily_balances must be consecutive calendar days")
        elif any(isinstance(item, dict) for item in raw_days):
            raise ValueError("daily_balances must contain either all numbers or all balance objects")
        else:
            for index, item in enumerate(raw_days):
                balance = as_decimal(item, "daily_balances[%d]" % index)
                if balance < 0:
                    raise ValueError("daily balances cannot be negative")
                balances.append(balance)

        day_count_value = request.get("day_count", 365)
        if isinstance(day_count_value, bool):
            raise ValueError("day_count must be a positive integer")
        try:
            day_count = int(day_count_value)
        except (ValueError, TypeError):
            raise ValueError("day_count must be a positive integer")
        if day_count <= 0 or str(day_count_value).strip() not in {str(day_count), str(float(day_count))}:
            # Numeric JSON inputs such as 365 and strings such as '365' are accepted;
            # reject fractional and nonnumeric forms rather than silently truncating.
            if not (isinstance(day_count_value, int) and not isinstance(day_count_value, bool)):
                raise ValueError("day_count must be a positive integer")

        basis = request.get("rate_basis", "apy_effective")
        if basis not in ("apy_effective", "nominal_annual_rate"):
            raise ValueError("rate_basis must be apy_effective or nominal_annual_rate")
        annual_rate = annual_percent / Decimal("100")
        with localcontext() as ctx:
            ctx.prec = 50
            if basis == "apy_effective":
                daily_rate = (Decimal("1") + annual_rate) ** (Decimal("1") / Decimal(day_count)) - Decimal("1")
            else:
                daily_rate = annual_rate / Decimal(day_count)
            accrued = Decimal("0")
            for balance in balances:
                accrued += (balance + accrued) * daily_rate
            rounded_expected = accrued.quantize(CENTS, rounding=ROUND_HALF_UP)

        result = {
            "ok": True,
            "days_processed": len(balances),
            "date_range": ([dates[0].isoformat(), dates[-1].isoformat()] if dates else None),
            "rate_basis": basis,
            "annual_apy_percent": text(annual_percent),
            "daily_rate": text(daily_rate),
            "unrounded_expected_interest": text(accrued),
            "expected_interest_rounded": text(rounded_expected),
            "rounding_method": "ROUND_HALF_UP at end of period"
        }
        if "posted_interest" in request and request["posted_interest"] is not None:
            posted = as_decimal(request["posted_interest"], "posted_interest")
            result["posted_interest"] = text(posted.quantize(CENTS, rounding=ROUND_HALF_UP))
            difference = rounded_expected - posted.quantize(CENTS, rounding=ROUND_HALF_UP)
            result["difference_expected_minus_posted"] = text(difference)
            result["comparison"] = "potential_undercredit" if difference > 0 else ("potential_overcredit" if difference < 0 else "matches_after_rounding")
        print(json.dumps(result, sort_keys=True))
        return 0
    except (ValueError, TypeError, KeyError, InvalidOperation, json.JSONDecodeError) as exc:
        return fail(str(exc))


if __name__ == "__main__":
    sys.exit(main())
