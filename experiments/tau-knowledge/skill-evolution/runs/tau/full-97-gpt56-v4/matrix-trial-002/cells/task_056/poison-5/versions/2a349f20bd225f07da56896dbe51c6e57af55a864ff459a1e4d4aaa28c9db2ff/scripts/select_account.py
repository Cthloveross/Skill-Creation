#!/usr/bin/env python3
"""Filter and rank business-checking accounts from JSON on stdin.

This utility performs no bank action. See SKILL.md for the input and output schema.
"""
import json
import sys
from datetime import date


def fail(message):
    print(json.dumps({"error": message}, sort_keys=True))
    raise SystemExit(2)


def parse_date(value, field):
    if not isinstance(value, str):
        fail(f"{field} must be an ISO date string")
    try:
        return date.fromisoformat(value)
    except ValueError:
        fail(f"{field} must be an ISO date string")


def number_or_none(value, field):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        fail(f"{field} must be a number or null")
    return value


def active_priority(promotions, account_name, as_of):
    ranks = []
    for index, promo in enumerate(promotions):
        if not isinstance(promo, dict):
            fail(f"promotions[{index}] must be an object")
        if promo.get("account") != account_name:
            continue
        start = parse_date(promo.get("start"), f"promotions[{index}].start")
        end = parse_date(promo.get("end"), f"promotions[{index}].end")
        rank = promo.get("rank")
        if isinstance(rank, bool) or not isinstance(rank, int):
            fail(f"promotions[{index}].rank must be an integer")
        if start <= as_of <= end:
            ranks.append(rank)
    return min(ranks) if ranks else None


def main(payload):
    if not isinstance(payload, dict):
        fail("top-level JSON must be an object")
    as_of = parse_date(payload.get("as_of"), "as_of")
    requirements = payload.get("requirements", {})
    accounts = payload.get("accounts")
    promotions = payload.get("promotions", [])
    if not isinstance(requirements, dict):
        fail("requirements must be an object")
    if not isinstance(accounts, list) or not accounts:
        fail("accounts must be a nonempty list")
    if not isinstance(promotions, list):
        fail("promotions must be a list")

    company_age = number_or_none(requirements.get("company_age_years"), "requirements.company_age_years")
    max_fee = number_or_none(requirements.get("max_monthly_fee"), "requirements.max_monthly_fee")
    zero_od = requirements.get("zero_overdraft_required", False)
    required_features = requirements.get("required_features", [])
    if not isinstance(zero_od, bool):
        fail("requirements.zero_overdraft_required must be boolean")
    if not isinstance(required_features, list) or not all(isinstance(x, str) for x in required_features):
        fail("requirements.required_features must be a list of strings")

    qualified = []
    rejections = {}
    for index, account in enumerate(accounts):
        if not isinstance(account, dict) or not isinstance(account.get("name"), str) or not account["name"]:
            fail(f"accounts[{index}].name must be a nonempty string")
        name = account["name"]
        monthly_fee = number_or_none(account.get("monthly_maintenance_fee"), f"accounts[{index}].monthly_maintenance_fee")
        overdraft_fee = number_or_none(account.get("overdraft_fee"), f"accounts[{index}].overdraft_fee")
        age_limit = number_or_none(account.get("max_company_age_years"), f"accounts[{index}].max_company_age_years")
        features = account.get("features", [])
        if not isinstance(features, list) or not all(isinstance(x, str) for x in features):
            fail(f"accounts[{index}].features must be a list of strings")

        reasons = []
        if company_age is not None and age_limit is not None and company_age > age_limit:
            reasons.append("company age exceeds account eligibility limit")
        if max_fee is not None:
            if monthly_fee is None:
                reasons.append("monthly maintenance fee is unknown")
            elif monthly_fee > max_fee:
                reasons.append("monthly maintenance fee exceeds customer maximum")
        if zero_od:
            if overdraft_fee is None:
                reasons.append("overdraft fee is unknown")
            elif overdraft_fee != 0:
                reasons.append("overdraft fee is not zero")
        missing = sorted(set(required_features) - set(features))
        if missing:
            reasons.append("missing required features: " + ", ".join(missing))
        if reasons:
            rejections[name] = reasons
        else:
            qualified.append(name)

    by_name = {account["name"]: account for account in accounts}
    def ordering(name):
        priority = active_priority(promotions, name, as_of)
        # Accounts without an active promotional rank follow ranked accounts;
        # preserve supplied order for non-promotional or tied candidates.
        return (0, priority) if priority is not None else (1, 0)

    selected = min(qualified, key=ordering) if qualified else None
    basis = None
    if selected is not None:
        priority = active_priority(promotions, selected, as_of)
        basis = "active promotional priority among qualifying accounts" if priority is not None else "qualifying account; no active promotional priority"

    result = {
        "qualified": qualified,
        "selected": selected,
        "rejections": rejections,
        "selection_basis": basis,
    }
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    try:
        main(json.load(sys.stdin))
    except json.JSONDecodeError as exc:
        fail(f"invalid JSON input: {exc.msg}")
