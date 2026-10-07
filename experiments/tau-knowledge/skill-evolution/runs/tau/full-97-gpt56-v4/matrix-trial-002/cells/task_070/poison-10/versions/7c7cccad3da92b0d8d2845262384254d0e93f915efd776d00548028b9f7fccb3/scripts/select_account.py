#!/usr/bin/env python3
"""Filter business-checking candidates using runtime-supplied facts.

Reads a JSON request on stdin and emits the documented JSON decision object on stdout.
"""
import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation


def decimal_value(value, field):
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{field} must be a decimal-compatible value") from exc


def parse_date(value, field):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be YYYY-MM-DD") from exc


def promotion_is_active(payload):
    promotion = payload.get("promotion")
    if not promotion:
        return False, []
    as_of = parse_date(payload.get("as_of_date"), "as_of_date")
    start = parse_date(promotion.get("start_date"), "promotion.start_date")
    end = parse_date(promotion.get("end_date"), "promotion.end_date")
    if end < start:
        raise ValueError("promotion.end_date must not precede promotion.start_date")
    return start <= as_of <= end, promotion.get("priority_order", [])


def evaluate(candidate, requirements):
    name = candidate.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("every candidate needs a nonempty name")
    reasons = []
    if requirements.get("no_overdraft_fee") is True:
        if "overdraft_fee" not in candidate:
            reasons.append("overdraft fee is not evidenced")
        elif decimal_value(candidate["overdraft_fee"], f"{name}.overdraft_fee") != 0:
            reasons.append("overdraft fee is not zero")
    if "minimum_monthly_atm_rebate" in requirements:
        required = decimal_value(requirements["minimum_monthly_atm_rebate"], "minimum_monthly_atm_rebate")
        if "monthly_atm_rebate" not in candidate:
            reasons.append("monthly ATM rebate is not evidenced")
        elif decimal_value(candidate["monthly_atm_rebate"], f"{name}.monthly_atm_rebate") < required:
            reasons.append("monthly ATM rebate is below the required amount")
    if "company_age_years" in requirements and "maximum_company_age_years" in candidate:
        age = decimal_value(requirements["company_age_years"], "company_age_years")
        maximum = decimal_value(candidate["maximum_company_age_years"], f"{name}.maximum_company_age_years")
        if age > maximum:
            reasons.append("company age exceeds the evidenced eligibility limit")
    return reasons


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    requirements = payload.get("requirements", {})
    candidates = payload.get("candidates", [])
    if not isinstance(requirements, dict) or not isinstance(candidates, list):
        raise ValueError("requirements must be an object and candidates must be an array")

    active, priority = promotion_is_active(payload)
    qualified, rejected = [], []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise ValueError("each candidate must be an object")
        reasons = evaluate(candidate, requirements)
        if reasons:
            rejected.append({"name": candidate["name"], "reasons": reasons})
        else:
            qualified.append(candidate)

    rank = {name: index for index, name in enumerate(priority)} if active else {}
    qualified.sort(key=lambda item: (rank.get(item["name"], len(rank)), item["name"].casefold()))
    recommendation = None
    basis = []
    if qualified:
        chosen = qualified[0]
        recommendation = {"name": chosen["name"], "features": chosen.get("features", [])}
        basis.append("meets all supplied objective requirements")
        if active and chosen["name"] in rank:
            basis.append("selected by the active supplied promotion priority")
    else:
        basis.append("no supplied candidate meets all supplied objective requirements")

    return {
        "recommended": recommendation,
        "qualifying_accounts": [item["name"] for item in qualified],
        "rejected": rejected,
        "promotion_active": active,
        "basis": basis,
    }


if __name__ == "__main__":
    try:
        request = json.load(sys.stdin)
        print(json.dumps(main(request), separators=(",", ":")))
    except (ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"error": str(error)}, separators=(",", ":")))
        sys.exit(2)
