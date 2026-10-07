#!/usr/bin/env python3
"""Filter business-checking candidates and apply an optional dated priority order.
Reads one JSON object from stdin and writes one JSON object to stdout.
"""
import json
import sys
from datetime import date


def parse_day(value, field):
    if not isinstance(value, str):
        raise ValueError(f"{field} must be YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be YYYY-MM-DD") from exc


def select(payload):
    as_of = parse_day(payload.get("as_of"), "as_of")
    requirements = payload.get("requirements")
    accounts = payload.get("accounts")
    if not isinstance(requirements, dict) or not isinstance(accounts, list):
        raise ValueError("requirements must be an object and accounts must be a list")

    need_zero_overdraft = requirements.get("no_overdraft_fee", False) is True
    minimum_rebate = requirements.get("minimum_atm_rebate_monthly")
    if minimum_rebate is not None and (not isinstance(minimum_rebate, (int, float)) or isinstance(minimum_rebate, bool)):
        raise ValueError("minimum_atm_rebate_monthly must be numeric when provided")

    qualified = []
    rejected = {}
    for account in accounts:
        if not isinstance(account, dict) or not isinstance(account.get("name"), str):
            raise ValueError("each account requires a string name")
        name = account["name"]
        reasons = []
        if account.get("eligible") is not True:
            reasons.append("eligibility is unconfirmed or not met")
        if need_zero_overdraft:
            fee = account.get("overdraft_fee")
            if not isinstance(fee, (int, float)) or isinstance(fee, bool) or fee != 0:
                reasons.append("does not have a confirmed $0 overdraft fee")
        if minimum_rebate is not None:
            rebate = account.get("atm_rebate_monthly")
            if (not isinstance(rebate, (int, float)) or isinstance(rebate, bool)
                    or rebate < minimum_rebate):
                reasons.append("does not meet the required monthly ATM-rebate cap")
        if reasons:
            rejected[name] = reasons
        else:
            qualified.append(name)

    priority = []
    promotion = payload.get("promotion")
    if isinstance(promotion, dict):
        start = parse_day(promotion.get("start"), "promotion.start")
        end = parse_day(promotion.get("end"), "promotion.end")
        if start > end:
            raise ValueError("promotion.start must not be after promotion.end")
        supplied_priority = promotion.get("priority", [])
        if not isinstance(supplied_priority, list) or not all(isinstance(x, str) for x in supplied_priority):
            raise ValueError("promotion.priority must be a list of names")
        if start <= as_of <= end:
            priority = supplied_priority

    rank = {name: index for index, name in enumerate(priority)}
    ordered = sorted(qualified, key=lambda name: (rank.get(name, len(rank)), name.casefold()))
    return {
        "recommendation": ordered[0] if ordered else None,
        "qualifying_accounts": ordered,
        "rejection_reasons": rejected,
        "promotion_active": bool(priority),
    }


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(select(payload), sort_keys=True))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)


if __name__ == "__main__":
    main()
