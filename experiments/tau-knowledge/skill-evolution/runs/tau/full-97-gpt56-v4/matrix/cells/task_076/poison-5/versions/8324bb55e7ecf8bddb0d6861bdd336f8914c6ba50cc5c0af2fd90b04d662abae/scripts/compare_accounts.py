#!/usr/bin/env python3
"""Compare disclosed travel ATM costs.

Reads the JSON schema documented in SKILL.md from stdin and writes JSON. The
program makes no product-specific assumptions; callers supply account facts.
"""
import json
import sys
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

CENTS = Decimal("0.01")
SUPPORTED_KINDS = {"none", "flat", "percent", "percent_with_min", "unknown"}


def money(value):
    return Decimal(str(value)).quantize(CENTS, rounding=ROUND_HALF_UP)


def fee_per_withdrawal(spec, withdrawal):
    if not spec:
        return None
    kind = spec.get("kind", "unknown")
    if kind not in SUPPORTED_KINDS:
        raise ValueError("unsupported fee kind: %s" % kind)
    if kind == "unknown":
        return None
    if kind == "none":
        return Decimal("0")
    if kind == "flat":
        return money(spec["amount"])
    if kind == "percent":
        return money(withdrawal * Decimal(str(spec["percent"])))
    # percent_with_min
    calculated = withdrawal * Decimal(str(spec["percent"]))
    return money(max(calculated, Decimal(str(spec["minimum"]))))


def dollars(value):
    if value is None:
        return None
    return format(money(value), ".2f")


def main(data):
    for field in ("trip_months", "withdrawals_per_month", "withdrawal_amount", "accounts"):
        if field not in data:
            raise ValueError("missing required field: " + field)
    months = int(data["trip_months"])
    monthly_withdrawals = int(data["withdrawals_per_month"])
    withdrawal = Decimal(str(data["withdrawal_amount"]))
    required_days = Decimal(str(data.get("early_direct_deposit_min_days", 0)))
    include_oon = bool(data.get("treat_withdrawals_as_out_of_network", False))
    if months < 0 or monthly_withdrawals < 0 or withdrawal < 0 or required_days < 0:
        raise ValueError("trip quantities and required days must be non-negative")
    total_withdrawals = months * monthly_withdrawals
    results = []
    for account in data["accounts"]:
        name = account.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("each account needs a nonempty name")
        eligible = bool(account.get("eligible", True))
        early_days = Decimal(str(account.get("early_direct_deposit_days", 0)))
        meets_early = early_days >= required_days
        row = {
            "name": name,
            "eligible": eligible,
            "ineligibility_reason": account.get("ineligibility_reason"),
            "early_direct_deposit_days": str(early_days),
            "meets_early_direct_deposit_requirement": meets_early,
            "qualifies": eligible and meets_early,
            "notes": account.get("notes", []),
        }
        foreign_each = fee_per_withdrawal(account.get("foreign_atm_fee", {"kind": "unknown"}), withdrawal)
        oon_each = fee_per_withdrawal(account.get("out_of_network_atm_fee"), withdrawal)
        row["foreign_bank_fee_per_withdrawal"] = dollars(foreign_each)
        row["foreign_bank_fee_trip_total"] = dollars(None if foreign_each is None else foreign_each * total_withdrawals)
        row["out_of_network_scenario_included"] = include_oon
        row["out_of_network_fee_per_withdrawal"] = dollars(oon_each)
        if include_oon and foreign_each is not None and oon_each is not None:
            row["known_bank_atm_fee_trip_total"] = dollars((foreign_each + oon_each) * total_withdrawals)
        elif foreign_each is not None:
            row["known_bank_atm_fee_trip_total"] = dollars(foreign_each * total_withdrawals)
        else:
            row["known_bank_atm_fee_trip_total"] = None
        cap = account.get("operator_rebate_monthly_cap")
        row["operator_rebate_monthly_cap"] = dollars(cap) if cap is not None else None
        operator_fee = account.get("operator_fee_per_withdrawal")
        if operator_fee is not None and cap is not None:
            monthly_operator = money(Decimal(str(operator_fee)) * monthly_withdrawals)
            row["estimated_operator_rebate_trip_total"] = dollars(min(monthly_operator, money(cap)) * months)
        else:
            row["estimated_operator_rebate_trip_total"] = None
        maintenance = Decimal(str(account.get("monthly_maintenance_fee", 0)))
        waived = bool(account.get("maintenance_fee_waived", False))
        row["non_atm_maintenance_fee_trip_total"] = dollars(Decimal("0") if waived else maintenance * months)
        results.append(row)

    def rank_key(row):
        total = row["known_bank_atm_fee_trip_total"]
        return (total is None, Decimal(total) if total is not None else Decimal("0"), row["name"])

    qualifying = sorted((r for r in results if r["qualifies"]), key=rank_key)
    return {
        "assumptions": {
            "trip_months": months,
            "withdrawals_per_month": monthly_withdrawals,
            "total_withdrawals": total_withdrawals,
            "withdrawal_amount": dollars(withdrawal),
            "treat_withdrawals_as_out_of_network": include_oon,
            "operator_surcharges_are_unknown_unless_input_supplies_them": True,
        },
        "accounts": results,
        "qualifying_accounts_ranked_by_known_bank_atm_cost": [r["name"] for r in qualifying],
        "recommendation_status": "available" if qualifying else "no_eligible_account_meets_requirement",
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), indent=2, sort_keys=True))
    except (json.JSONDecodeError, ValueError, KeyError, InvalidOperation) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
