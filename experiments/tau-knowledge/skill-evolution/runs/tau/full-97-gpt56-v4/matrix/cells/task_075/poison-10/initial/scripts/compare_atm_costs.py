#!/usr/bin/env python3
"""Calculate planned ATM costs from normalized, supplied account facts.

Reads one JSON object from stdin and writes one JSON object to stdout. See SKILL.md
for the schema. This utility is deliberately generic and does not retrieve account
information or initiate banking activity.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")


def money(value, field):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be a valid decimal amount")
    if result < 0:
        raise ValueError(f"{field} cannot be negative")
    return result


def fmt(value):
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), "f")


def foreign_fee(model, amount):
    if not isinstance(model, dict):
        raise ValueError("foreign_atm_fee must be an object")
    kind = model.get("type")
    if kind == "flat":
        return money(model.get("amount"), "foreign_atm_fee.amount")
    if kind in ("percentage_minimum", "percentage_maximum"):
        rate = money(model.get("rate_percent"), "foreign_atm_fee.rate_percent")
        calculated = amount * rate / Decimal("100")
        boundary_key = "minimum" if kind == "percentage_minimum" else "maximum"
        boundary = money(model.get(boundary_key), "foreign_atm_fee." + boundary_key)
        return max(calculated, boundary) if kind == "percentage_minimum" else min(calculated, boundary)
    if kind == "tiers":
        tiers = model.get("tiers")
        if not isinstance(tiers, list) or not tiers:
            raise ValueError("foreign_atm_fee.tiers must be a nonempty list")
        previous = Decimal("0")
        for tier in tiers:
            if not isinstance(tier, dict):
                raise ValueError("each tier must be an object")
            upper_raw = tier.get("up_to")
            upper = None if upper_raw is None else money(upper_raw, "tier.up_to")
            if upper is not None and upper < previous:
                raise ValueError("tier thresholds must be ascending")
            if upper is None or amount <= upper:
                return money(tier.get("amount"), "tier.amount")
            previous = upper
        raise ValueError("tiers need a final null up_to tier for this withdrawal amount")
    raise ValueError("foreign_atm_fee.type is unsupported")


def integer(value, field, minimum=0):
    if isinstance(value, bool):
        raise ValueError(f"{field} must be an integer")
    try:
        result = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be an integer")
    if str(result) != str(value).strip() if isinstance(value, str) else result != value:
        raise ValueError(f"{field} must be an integer")
    if result < minimum:
        raise ValueError(f"{field} must be at least {minimum}")
    return result


def account_result(account, months, withdrawals, withdrawal_amount, surcharge):
    if not isinstance(account, dict) or not account.get("name"):
        raise ValueError("each account needs a nonempty name")
    name = str(account["name"])
    eligible = account.get("eligible") is True
    output = {"name": name, "eligible": eligible}
    if not eligible:
        output["eligibility_note"] = str(account.get("eligibility_note") or "Customer does not meet a supplied eligibility condition.")
        return output

    monthly_fee = money(account.get("monthly_maintenance_fee", 0), "monthly_maintenance_fee")
    waived = account.get("maintenance_fee_waived") is True
    maintenance_total = Decimal("0") if waived else monthly_fee * months
    allowance = integer(account.get("free_foreign_withdrawals_per_month", 0), "free_foreign_withdrawals_per_month")
    charged_per_month = max(0, withdrawals - allowance)
    each_bank_fee = foreign_fee(account.get("foreign_atm_fee", {"type": "flat", "amount": 0}), withdrawal_amount)
    bank_atm_total = each_bank_fee * charged_per_month * months
    known_bank_total = maintenance_total + bank_atm_total

    output.update({
        "maintenance_fee_waived": waived,
        "maintenance_cost_total": fmt(maintenance_total),
        "free_withdrawals_per_month": allowance,
        "charged_withdrawals_per_month": charged_per_month,
        "bank_fee_per_charged_withdrawal": fmt(each_bank_fee),
        "bank_foreign_atm_cost_total": fmt(bank_atm_total),
        "known_bank_cost_total": fmt(known_bank_total),
    })
    if "daily_atm_limit" in account and account["daily_atm_limit"] is not None:
        limit = money(account["daily_atm_limit"], "daily_atm_limit")
        output["daily_atm_limit"] = fmt(limit)
        output["single_withdrawal_within_limit"] = withdrawal_amount <= limit

    rebate_cap = money(account.get("operator_fee_rebate_cap_per_month", 0), "operator_fee_rebate_cap_per_month")
    output["operator_fee_rebate_cap_per_month"] = fmt(rebate_cap)
    if surcharge is None:
        output["operator_surcharge_status"] = "unknown_not_included_in_total"
    else:
        monthly_operator = surcharge * withdrawals
        rebate_monthly = min(monthly_operator, rebate_cap)
        operator_total = monthly_operator * months
        rebate_total = rebate_monthly * months
        output.update({
            "operator_surcharge_cost_total": fmt(operator_total),
            "operator_rebate_total": fmt(rebate_total),
            "estimated_total_including_operator_surcharges": fmt(known_bank_total + operator_total - rebate_total),
        })
    return output


def main():
    payload = json.load(sys.stdin)
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    months = integer(payload.get("months"), "months", 1)
    withdrawals = integer(payload.get("withdrawals_per_month"), "withdrawals_per_month")
    withdrawal_amount = money(payload.get("withdrawal_amount"), "withdrawal_amount")
    raw_surcharge = payload.get("operator_surcharge_per_withdrawal")
    surcharge = None if raw_surcharge is None else money(raw_surcharge, "operator_surcharge_per_withdrawal")
    accounts = payload.get("accounts")
    if not isinstance(accounts, list) or not accounts:
        raise ValueError("accounts must be a nonempty array")
    result = {
        "assumptions": {
            "months": months,
            "withdrawals_per_month": withdrawals,
            "withdrawal_amount": fmt(withdrawal_amount),
            "operator_surcharge_per_withdrawal": None if surcharge is None else fmt(surcharge),
        },
        "accounts": [account_result(a, months, withdrawals, withdrawal_amount, surcharge) for a in accounts],
    }
    print(json.dumps(result, separators=(",", ":")))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
