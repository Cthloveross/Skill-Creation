#!/usr/bin/env python3
"""Rank checking products for international-ATM and early-deposit priorities.

Input JSON schema:
{
  "products": [{
    "account_class": str,
    "foreign_atm_fee": number | {"type": "flat"|"percent_min"|"allowance", ...},
    "atm_rebate_monthly": number (optional, default 0),
    "early_direct_deposit_days": number (optional, default 0),
    "opening_deposit": number (optional),
    "minimum_daily_balance": number (optional),
    "monthly_fee": number (optional),
    "conditions_confirmed": bool (optional, default false)
  }],
  "priorities": {"foreign_atm_cost": bool, "early_direct_deposit": bool},
  "confirmed": {"maximum_opening_deposit": number, "maximum_daily_balance": number}
}

The output has `ranked`, `best_fit`, and `excluded`. Fees with a percentage,
minimum, allowance, or another non-flat structure are retained as descriptions
rather than falsely converted to a comparable dollar amount. This program is
advisory only and performs no banking action.
"""
import json
import sys


def fee_rank(value):
    """Return (rank, printable description); lower rank is a lower known fee."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value), f"${float(value):.2f} per foreign ATM withdrawal"
    if isinstance(value, dict):
        kind = value.get("type", "variable")
        if kind == "flat" and isinstance(value.get("amount"), (int, float)):
            amount = float(value["amount"])
            return amount, f"${amount:.2f} per foreign ATM withdrawal"
        if kind == "percent_min":
            pct = value.get("percent")
            minimum = value.get("minimum")
            return 1000000.0, f"{pct}% of withdrawal, ${minimum:.2f} minimum" if isinstance(minimum, (int, float)) else f"{pct}% of withdrawal"
        if kind == "allowance":
            free = value.get("free_withdrawals")
            after = value.get("fee_after")
            return 500000.0, f"{free} free withdrawals, then ${after:.2f} each" if isinstance(after, (int, float)) else f"{free} free withdrawals"
    return 2000000.0, "foreign ATM fee not available"


def affordability_issues(product, confirmed):
    issues = []
    opening = product.get("opening_deposit")
    daily = product.get("minimum_daily_balance")
    max_opening = confirmed.get("maximum_opening_deposit")
    max_daily = confirmed.get("maximum_daily_balance")
    if isinstance(opening, (int, float)):
        if not isinstance(max_opening, (int, float)):
            issues.append(f"opening deposit of ${opening:,.2f} is unconfirmed")
        elif max_opening < opening:
            issues.append(f"requires ${opening:,.2f} opening deposit, above confirmed amount")
    if isinstance(daily, (int, float)):
        if not isinstance(max_daily, (int, float)):
            issues.append(f"daily-balance condition of ${daily:,.2f} is unconfirmed")
        elif max_daily < daily:
            issues.append(f"requires ${daily:,.2f} daily balance, above confirmed amount")
    return issues


def main():
    payload = json.load(sys.stdin)
    products = payload.get("products")
    if not isinstance(products, list):
        raise ValueError("products must be an array")
    confirmed = payload.get("confirmed") or {}
    prepared, excluded = [], []
    for product in products:
        if not isinstance(product, dict) or not isinstance(product.get("account_class"), str) or not product["account_class"].strip():
            excluded.append({"reason": "missing a nonempty account_class"})
            continue
        issues = affordability_issues(product, confirmed)
        foreign_rank, fee_description = fee_rank(product.get("foreign_atm_fee"))
        rebate = product.get("atm_rebate_monthly", 0)
        early = product.get("early_direct_deposit_days", 0)
        rebate = float(rebate) if isinstance(rebate, (int, float)) else 0.0
        early = float(early) if isinstance(early, (int, float)) else 0.0
        entry = {
            "account_class": product["account_class"],
            "foreign_atm_fee": fee_description,
            "atm_rebate_monthly": rebate,
            "early_direct_deposit_days": early,
            "unknown_conditions": issues,
            "monthly_fee": product.get("monthly_fee"),
        }
        # Conditions affect disclosure, not the cost ranking: a caller must not
        # silently treat an unconfirmed condition as an exclusion or approval.
        entry["_sort"] = (foreign_rank, -rebate, -early, product["account_class"].casefold())
        prepared.append(entry)
    prepared.sort(key=lambda x: x["_sort"])
    for entry in prepared:
        entry.pop("_sort", None)
    result = {"ranked": prepared, "excluded": excluded, "best_fit": prepared[0] if prepared else None}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
