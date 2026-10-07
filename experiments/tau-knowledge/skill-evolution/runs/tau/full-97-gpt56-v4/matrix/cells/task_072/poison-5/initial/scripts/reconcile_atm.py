#!/usr/bin/env python3
"""Validate and calculate documented ATM-fee corrections; never performs bank actions."""
import json
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

ZERO = Decimal("0.00")
CAP = Decimal("50.00")
CENT = Decimal("0.01")


def money(value, label, errors):
    try:
        amount = Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)
        if amount < ZERO:
            raise ValueError
        return amount
    except (InvalidOperation, ValueError):
        errors.append(f"{label} must be a nonnegative decimal amount")
        return ZERO


def fmt(value):
    return format(value.quantize(CENT), ".2f")


def date_in_period(value, period):
    try:
        return datetime.strptime(value, "%m/%d/%Y").strftime("%Y-%m") == period
    except (TypeError, ValueError):
        return False


def ids(event):
    value = event.get("transaction_ids", [])
    return value if isinstance(value, list) else []


def base_result(account_id, product):
    return {
        "account_id": account_id,
        "product": product,
        "status": "ok",
        "errors": [],
        "warnings": [],
        "discrepancies": [],
        "recommendation": None,
    }


def reconcile_bluest(account, period, result):
    if not account.get("statement_cycle_confirmed"):
        result["errors"].append("Bluest requires confirmed monthly statement-cycle boundaries")
    eligible_fees = ZERO
    recorded_rebates = ZERO
    pending_seen = False
    cited = []
    for index, event in enumerate(account.get("events", [])):
        if not date_in_period(event.get("date"), period):
            result["errors"].append(f"event {index} has an invalid or out-of-period date")
            continue
        status = event.get("status")
        if status == "pending":
            pending_seen = True
            continue
        if status != "posted":
            result["errors"].append(f"event {index} must have status posted or pending")
            continue
        fee = money(event.get("third_party_atm_fee_amount", "0"),
                    f"event {index} third_party_atm_fee_amount", result["errors"])
        rebate = money(event.get("rebate_amount", "0"), f"event {index} rebate_amount", result["errors"])
        eligible_fees += fee
        recorded_rebates += rebate
        if fee or rebate:
            cited.extend(ids(event))
    if pending_seen:
        result["warnings"].append("Pending Bluest entries were excluded; do not credit them")
    expected = min(eligible_fees, CAP)
    missing = expected - recorded_rebates
    result["calculation"] = {
        "eligible_third_party_fees": fmt(eligible_fees),
        "monthly_rebate_cap": fmt(CAP),
        "expected_rebate": fmt(expected),
        "recorded_rebates": fmt(recorded_rebates),
    }
    if missing > ZERO:
        result["discrepancies"].append({
            "reason": "missing_bluest_atm_rebate",
            "amount": fmt(missing),
            "transaction_ids": cited,
        })
        result["recommendation"] = {
            "amount": fmt(missing),
            "credit_type": "rebate_credit",
            "reason": "Documented Bluest third-party ATM rebate shortfall",
        }
    elif missing < ZERO:
        result["warnings"].append("Recorded rebates exceed calculated eligible cap; investigate, do not debit")


def foreign_fee(withdrawal):
    if withdrawal <= Decimal("100.00"):
        return Decimal("2.00")
    if withdrawal <= Decimal("300.00"):
        return Decimal("3.50")
    return Decimal("5.00")


def reconcile_light_green(account, period, result):
    domestic_count = 0
    overcharge = ZERO
    cited = []
    pending_seen = False
    events = account.get("events", [])
    # Stable chronological ordering makes the four free withdrawals deterministic.
    valid = []
    for index, event in enumerate(events):
        if not date_in_period(event.get("date"), period):
            result["errors"].append(f"event {index} has an invalid or out-of-period date")
            continue
        valid.append((event.get("date"), index, event))
    valid.sort(key=lambda item: (datetime.strptime(item[0], "%m/%d/%Y"), item[1]))
    expected_total = ZERO
    actual_total = ZERO
    for _, index, event in valid:
        status = event.get("status")
        if status == "pending":
            pending_seen = True
            continue
        if status != "posted":
            result["errors"].append(f"event {index} must have status posted or pending")
            continue
        kind = event.get("location_kind")
        withdrawal = money(event.get("withdrawal_amount", "0"), f"event {index} withdrawal_amount", result["errors"])
        actual = money(event.get("bank_atm_fee_amount", "0"), f"event {index} bank_atm_fee_amount", result["errors"])
        if kind == "domestic_out_of_network":
            domestic_count += 1
            expected = ZERO if domestic_count <= 4 else Decimal("1.50")
        elif kind == "foreign":
            if withdrawal <= ZERO:
                result["errors"].append(f"foreign event {index} requires a positive withdrawal amount")
                expected = ZERO
            else:
                expected = foreign_fee(withdrawal)
        elif kind == "other":
            # It is outside the stated Light Green ATM fee rules and cannot be reconciled automatically.
            result["warnings"].append(f"event {index} is not classified as foreign or domestic out-of-network")
            continue
        else:
            result["errors"].append(f"event {index} has unknown location_kind")
            continue
        expected_total += expected
        actual_total += actual
        difference = actual - expected
        if difference > ZERO:
            overcharge += difference
            cited.extend(ids(event))
            result["discrepancies"].append({
                "reason": "light_green_bank_atm_fee_overcharge",
                "event_index": index,
                "expected_bank_fee": fmt(expected),
                "recorded_bank_fee": fmt(actual),
                "amount": fmt(difference),
                "transaction_ids": ids(event),
            })
        elif difference < ZERO:
            result["warnings"].append(f"event {index} recorded bank fee is below documented fee; do not debit")
    if pending_seen:
        result["warnings"].append("Pending Light Green entries were excluded; do not credit them")
    result["calculation"] = {
        "domestic_out_of_network_withdrawals": domestic_count,
        "expected_bank_fees": fmt(expected_total),
        "recorded_bank_fees": fmt(actual_total),
    }
    if overcharge > ZERO:
        result["recommendation"] = {
            "amount": fmt(overcharge),
            "credit_type": "fee_refund",
            "reason": "Documented Light Green bank ATM fee overcharge",
        }


def reconcile(account, period):
    account_id = account.get("account_id")
    product = account.get("product")
    result = base_result(account_id, product)
    if not isinstance(account_id, str) or not account_id:
        result["errors"].append("account_id is required")
    if not account.get("complete_period"):
        result["errors"].append("complete_period must be true; incomplete history cannot support a credit")
    if not isinstance(account.get("events"), list):
        result["errors"].append("events must be a list")
        account["events"] = []
    if product == "Bluest":
        reconcile_bluest(account, period, result)
    elif product == "Light Green":
        reconcile_light_green(account, period, result)
    else:
        result["errors"].append("product must be Bluest or Light Green")
    if result["errors"]:
        result["status"] = "blocked"
        result["recommendation"] = None
    return result


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"status": "blocked", "errors": [f"invalid JSON: {exc.msg}"]}))
        return
    period = payload.get("period")
    try:
        datetime.strptime(period + "-01", "%Y-%m-%d")
    except (TypeError, ValueError):
        print(json.dumps({"status": "blocked", "errors": ["period must be YYYY-MM"]}))
        return
    accounts = payload.get("accounts")
    if not isinstance(accounts, list):
        print(json.dumps({"status": "blocked", "errors": ["accounts must be a list"]}))
        return
    results = [reconcile(dict(account) if isinstance(account, dict) else {}, period) for account in accounts]
    print(json.dumps({"period": period, "results": results}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
