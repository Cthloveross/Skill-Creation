#!/usr/bin/env python3
"""Calculate a transparent constant-balance savings-interest estimate.

Input JSON schema:
{
  "accounts": [{
    "label": "optional string",
    "balance": "positive decimal",
    "days": positive integer,
    "base_apy_percent": "nonnegative decimal",
    "credit_card_bonuses": [{"name": "string", "percent": "decimal", "eligible": true}],
    "checking_boosts": [{"name": "string", "percent": "decimal", "eligible": true}],
    "reported_interest": "optional decimal"
  }]
}

Output JSON contains per-account selected highest eligible bonuses, effective APY,
constant-balance daily-compounding estimate, comparison (if reported), and warnings.
It does not determine product eligibility or authorize a banking adjustment.
"""

import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, getcontext

getcontext().prec = 40
CENT = Decimal("0.01")
DAYS_IN_YEAR = Decimal("365")


def money(value):
    return str(value.quantize(CENT, rounding=ROUND_HALF_UP))


def decimal_value(value, field, errors, nonnegative=False):
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        errors.append(f"{field} must be a numeric decimal.")
        return None
    if not parsed.is_finite():
        errors.append(f"{field} must be finite.")
        return None
    if nonnegative and parsed < 0:
        errors.append(f"{field} must not be negative.")
        return None
    return parsed


def parse_days(value, errors):
    if isinstance(value, bool):
        errors.append("days must be a positive integer.")
        return None
    try:
        days = int(value)
    except (ValueError, TypeError):
        errors.append("days must be a positive integer.")
        return None
    if str(value).strip() != str(days) if isinstance(value, str) else False:
        errors.append("days must be a positive integer.")
        return None
    if days <= 0:
        errors.append("days must be a positive integer.")
        return None
    return days


def select_highest(items, category, errors, warnings):
    if items is None:
        warnings.append(f"No {category} candidates were supplied.")
        return None
    if not isinstance(items, list):
        errors.append(f"{category} must be a list.")
        return None

    eligible = []
    unknown_count = 0
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"{category}[{index}] must be an object.")
            continue
        status = item.get("eligible", False)
        if status is not True and status is not False:
            errors.append(f"{category}[{index}].eligible must be true or false.")
            continue
        if status is False:
            if "eligible" not in item:
                unknown_count += 1
            continue
        amount = decimal_value(item.get("percent"), f"{category}[{index}].percent", errors, True)
        if amount is not None:
            eligible.append({"name": str(item.get("name", f"{category} candidate {index + 1}")), "percent": amount})

    if unknown_count:
        warnings.append(
            f"{unknown_count} {category} candidate(s) lacked confirmed eligibility and were excluded."
        )
    if not eligible:
        warnings.append(f"No confirmed eligible {category} was used.")
        return None
    # max retains a deterministic first candidate on an exact tie.
    return max(eligible, key=lambda entry: entry["percent"])


def reconcile(account, index):
    errors = []
    warnings = []
    if not isinstance(account, dict):
        return {"label": f"Account {index + 1}", "valid": False,
                "errors": ["Account entry must be an object."], "warnings": []}

    label = str(account.get("label", f"Account {index + 1}"))
    balance = decimal_value(account.get("balance"), "balance", errors, True)
    if balance is not None and balance == 0:
        errors.append("balance must be greater than zero for this estimate.")
    days = parse_days(account.get("days"), errors)
    base = decimal_value(account.get("base_apy_percent"), "base_apy_percent", errors, True)
    card = select_highest(account.get("credit_card_bonuses", []), "credit-card bonus", errors, warnings)
    checking = select_highest(account.get("checking_boosts", []), "checking boost", errors, warnings)

    result = {
        "label": label,
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "selected_credit_card_bonus": None if card is None else {
            "name": card["name"], "percent": str(card["percent"])
        },
        "selected_checking_boost": None if checking is None else {
            "name": checking["name"], "percent": str(checking["percent"])
        }
    }
    if errors:
        return result

    card_percent = card["percent"] if card else Decimal("0")
    checking_percent = checking["percent"] if checking else Decimal("0")
    effective_apy = base + card_percent + checking_percent
    daily_rate = (effective_apy / Decimal("100")) / DAYS_IN_YEAR
    estimate = balance * ((Decimal("1") + daily_rate) ** days - Decimal("1"))

    result.update({
        "base_apy_percent": str(base),
        "effective_apy_percent": str(effective_apy),
        "balance": str(balance),
        "days": days,
        "estimated_interest": money(estimate),
        "calculation_assumption": "Materially constant balance; daily rate estimated as effective APY divided by 365."
    })

    if "reported_interest" in account and account["reported_interest"] is not None:
        reported = decimal_value(account["reported_interest"], "reported_interest", errors)
        if reported is not None:
            result["reported_interest"] = money(reported)
            result["estimated_minus_reported"] = money(estimate - reported)
    result["valid"] = not errors
    return result


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"valid": False, "error": f"Invalid JSON: {exc.msg}"}))
        return
    if not isinstance(payload, dict) or not isinstance(payload.get("accounts"), list):
        print(json.dumps({"valid": False, "error": "Input must be an object with an accounts array."}))
        return

    accounts = [reconcile(account, i) for i, account in enumerate(payload["accounts"])]
    print(json.dumps({
        "valid": bool(accounts) and all(account["valid"] for account in accounts),
        "accounts": accounts,
        "notice": "This is an estimate, not an official posting calculation or authorization to adjust interest."
    }, indent=2))


if __name__ == "__main__":
    main()
