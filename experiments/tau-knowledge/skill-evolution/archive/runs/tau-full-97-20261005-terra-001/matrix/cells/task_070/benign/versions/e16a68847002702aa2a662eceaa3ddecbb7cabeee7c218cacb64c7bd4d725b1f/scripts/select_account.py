#!/usr/bin/env python3
"""Select a qualifying business account from caller-supplied normalized facts.

Reads one JSON object from stdin and writes one JSON object to stdout. No external
services, files, or product-specific constants are used.
"""

import json
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation


def decimal_value(value, field):
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{field} must be a number or numeric string")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be a number or numeric string")


def date_value(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonempty ISO date or timestamp")
    text = value.strip()
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        raise ValueError(f"{field} must begin with YYYY-MM-DD")


def active_promotion(promotion, as_of):
    if not isinstance(promotion, dict):
        return None
    try:
        start = date_value(promotion.get("start"), "promotion.start")
        end = date_value(promotion.get("end"), "promotion.end")
    except ValueError:
        return None
    if end < start or not (start <= as_of <= end):
        return None
    priority = promotion.get("priority")
    if isinstance(priority, bool) or not isinstance(priority, int) or priority < 1:
        return None
    return priority


def evaluate(account, requirements, as_of):
    if not isinstance(account, dict) or not isinstance(account.get("name"), str) or not account["name"].strip():
        return None, ["account requires a nonempty name"]

    failures = []
    review = []

    if requirements.get("zero_overdraft_fee") is True:
        if "overdraft_fee" not in account:
            review.append("overdraft fee is not documented")
        else:
            try:
                if decimal_value(account["overdraft_fee"], "overdraft_fee") != Decimal("0"):
                    failures.append("overdraft fee is not zero")
            except ValueError as exc:
                review.append(str(exc))

    if "minimum_atm_rebate_monthly" in requirements:
        try:
            required_rebate = decimal_value(requirements["minimum_atm_rebate_monthly"], "minimum_atm_rebate_monthly")
            if required_rebate < 0:
                review.append("minimum_atm_rebate_monthly cannot be negative")
            elif "atm_rebate_monthly" not in account:
                review.append("monthly ATM rebate cap is not documented")
            elif decimal_value(account["atm_rebate_monthly"], "atm_rebate_monthly") < required_rebate:
                failures.append("monthly ATM rebate cap is below the required amount")
        except ValueError as exc:
            review.append(str(exc))

    if "company_age_years" in requirements:
        age = requirements["company_age_years"]
        if isinstance(age, bool) or not isinstance(age, (int, float)) or age < 0:
            review.append("company_age_years must be a nonnegative number")
        elif "max_company_age_years" in account:
            maximum = account["max_company_age_years"]
            if isinstance(maximum, bool) or not isinstance(maximum, (int, float)) or maximum < 0:
                review.append("max_company_age_years must be a nonnegative number")
            elif age > maximum:
                failures.append("company age exceeds the documented maximum")

    result = {
        "name": account["name"].strip(),
        "promotion_priority": active_promotion(account.get("promotion"), as_of),
        "failures": failures,
        "review": review,
    }
    return result, []


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    as_of = date_value(payload.get("as_of"), "as_of")
    requirements = payload.get("requirements", {})
    accounts = payload.get("accounts")
    if not isinstance(requirements, dict):
        raise ValueError("requirements must be an object")
    if not isinstance(accounts, list) or not accounts:
        raise ValueError("accounts must be a nonempty array")

    qualifying = []
    review_required = []
    rejected = []
    for account in accounts:
        result, structural_errors = evaluate(account, requirements, as_of)
        if result is None:
            review_required.extend(structural_errors)
            continue
        if result["review"]:
            review_required.append({"name": result["name"], "issues": result["review"]})
        elif result["failures"]:
            rejected.append({"name": result["name"], "reasons": result["failures"]})
        else:
            qualifying.append(result)

    # An unresolved hard fact means no automated recommendation is safe.
    selected = None
    if not review_required and qualifying:
        qualifying.sort(key=lambda item: (
            item["promotion_priority"] is None,
            item["promotion_priority"] if item["promotion_priority"] is not None else 10**9,
            item["name"].casefold(),
        ))
        selected = qualifying[0]

    return {
        "ok": True,
        "selected": selected,
        "qualifying": qualifying,
        "rejected": rejected,
        "review_required": review_required,
    }


if __name__ == "__main__":
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw)
        print(json.dumps(main(payload), sort_keys=True))
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
