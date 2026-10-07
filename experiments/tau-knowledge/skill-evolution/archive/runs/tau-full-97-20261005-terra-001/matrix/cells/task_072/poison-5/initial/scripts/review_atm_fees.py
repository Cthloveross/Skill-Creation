#!/usr/bin/env python3
"""Safely calculate candidate ATM fee corrections from pre-classified evidence.

Input: one JSON object described in SKILL.md.
Output: JSON with findings, candidate amount, credit-type recommendation, and guards.
This script makes no banking-tool calls and deliberately refuses unsupported or
ambiguous account inputs.
"""

import json
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


def money(value, field):
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a nonnegative decimal")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be a nonnegative decimal")
    if not result.is_finite() or result < 0:
        raise ValueError(f"{field} must be a nonnegative decimal")
    return result.quantize(CENT, rounding=ROUND_HALF_UP)


def render(value):
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def required(obj, key, kind=None):
    if key not in obj:
        raise ValueError(f"missing required field: {key}")
    value = obj[key]
    if kind is not None and not isinstance(value, kind):
        raise ValueError(f"{key} has an invalid type")
    return value


def validate_entries(entries, label):
    if not isinstance(entries, list):
        raise ValueError(f"{label} must be a list")
    total = ZERO
    seen = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(f"{label}[{index}] must be an object")
        txid = required(entry, "transaction_id", str).strip()
        if not txid:
            raise ValueError(f"{label}[{index}].transaction_id must not be empty")
        if txid in seen:
            raise ValueError(f"duplicate transaction_id in {label}: {txid}")
        seen.add(txid)
        total += money(required(entry, "amount"), f"{label}[{index}].amount")
    return total


def base_output():
    return {
        "actionable": False,
        "manual_review_required": False,
        "errors": [],
        "findings": [],
        "candidate_credit_amount": "0.00",
        "recommended_credit_type": None,
        "correction_counts": {"rebate_credit": 0, "fee_refund": 0},
    }


def calculate_bluest(data, output):
    section = required(data, "bluest", dict)
    eligibility = required(section, "benefit_eligibility_confirmed")
    if eligibility is not True:
        output["manual_review_required"] = True
        output["errors"].append(
            "Bluest historical daily-balance benefit eligibility is not confirmed"
        )
        return

    qualifying = validate_entries(
        required(section, "qualifying_third_party_fee_entries", list),
        "bluest.qualifying_third_party_fee_entries",
    )
    posted = validate_entries(
        required(section, "posted_rebate_entries", list),
        "bluest.posted_rebate_entries",
    )
    overcharges = required(section, "confirmed_rho_fee_overcharge_entries", list)
    overcharge_total = validate_entries(overcharges, "bluest.confirmed_rho_fee_overcharge_entries")

    count = required(section, "missing_rebate_correction_count")
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise ValueError("bluest.missing_rebate_correction_count must be a nonnegative integer")

    required_rebate = min(qualifying, Decimal("50.00"))
    missing_rebate = max(required_rebate - posted, ZERO)
    if missing_rebate == ZERO and count != 0:
        raise ValueError("missing_rebate_correction_count must be zero when no rebate is missing")
    if missing_rebate > ZERO and count == 0:
        raise ValueError("missing_rebate_correction_count must be positive when a rebate is missing")

    output["findings"].append({
        "kind": "bluest_rebate",
        "qualifying_third_party_fees": render(qualifying),
        "statement_cycle_cap": "50.00",
        "required_rebate": render(required_rebate),
        "posted_rebates": render(posted),
        "missing_rebate": render(missing_rebate),
    })
    if overcharge_total > ZERO:
        output["findings"].append({
            "kind": "confirmed_rho_fee_overcharges",
            "amount": render(overcharge_total),
        })

    output["correction_counts"]["rebate_credit"] = count
    output["correction_counts"]["fee_refund"] = sum(
        1 for item in overcharges if money(item["amount"], "overcharge amount") > ZERO
    )
    return missing_rebate + overcharge_total


def expected_foreign_fee(withdrawal):
    if withdrawal <= Decimal("100.00"):
        return Decimal("2.00")
    if withdrawal <= Decimal("300.00"):
        return Decimal("3.50")
    return Decimal("5.00")


def calculate_light_green(data, output):
    section = required(data, "light_green", dict)
    events = required(section, "events", list)
    if not events:
        raise ValueError("light_green.events must not be empty")

    parsed = []
    seen_ids = set()
    seen_orders = set()
    for index, item in enumerate(events):
        if not isinstance(item, dict):
            raise ValueError(f"light_green.events[{index}] must be an object")
        txid = required(item, "transaction_id", str).strip()
        if not txid or txid in seen_ids:
            raise ValueError("each Light Green event requires a unique nonempty transaction_id")
        seen_ids.add(txid)
        date_text = required(item, "transaction_date", str)
        try:
            date = datetime.strptime(date_text, "%m/%d/%Y").date()
        except ValueError:
            raise ValueError(f"invalid transaction_date for {txid}; use MM/DD/YYYY")
        order = required(item, "order")
        if isinstance(order, bool) or not isinstance(order, int) or order < 1 or order in seen_orders:
            raise ValueError("each Light Green event requires a unique positive integer order")
        seen_orders.add(order)
        network = required(item, "network", str)
        if network not in ("out_of_network", "foreign"):
            raise ValueError("Light Green network must be out_of_network or foreign")
        status = required(item, "status", str).lower()
        if status not in ("posted", "pending"):
            raise ValueError("Light Green status must be posted or pending")
        parsed.append({
            "transaction_id": txid,
            "date": date,
            "order": order,
            "network": network,
            "withdrawal": money(required(item, "withdrawal_amount"), f"withdrawal_amount for {txid}"),
            "charged": money(required(item, "rho_fee_charged"), f"rho_fee_charged for {txid}"),
            "status": status,
        })

    parsed.sort(key=lambda x: (x["date"], x["order"]))
    qualifying_count = 0
    total = ZERO
    refund_count = 0
    for item in parsed:
        if item["status"] != "posted":
            output["findings"].append({
                "transaction_id": item["transaction_id"],
                "status": "pending",
                "decision": "excluded_pending",
            })
            continue
        if item["network"] == "foreign":
            expected = expected_foreign_fee(item["withdrawal"])
            rule = "foreign per-withdrawal Rho-Bank fee tier"
        else:
            qualifying_count += 1
            expected = ZERO if qualifying_count <= 4 else Decimal("1.50")
            rule = f"out-of-network allowance position {qualifying_count}"
        overcharge = max(item["charged"] - expected, ZERO)
        total += overcharge
        if overcharge > ZERO:
            refund_count += 1
        output["findings"].append({
            "transaction_id": item["transaction_id"],
            "network": item["network"],
            "withdrawal_amount": render(item["withdrawal"]),
            "rho_fee_charged": render(item["charged"]),
            "expected_rho_fee": render(expected),
            "overcharge": render(overcharge),
            "rule": rule,
        })
    output["correction_counts"]["fee_refund"] = refund_count
    return total


def main(data):
    output = base_output()
    account = required(data, "account", dict)
    account_id = required(account, "account_id", str).strip()
    if not account_id:
        raise ValueError("account.account_id must not be empty")
    account_class = required(account, "account_class", str)
    if required(account, "account_type", str).lower() != "checking":
        output["manual_review_required"] = True
        output["errors"].append("credits are only allowed for checking accounts")
        return output
    if required(account, "status", str).upper() != "OPEN":
        output["manual_review_required"] = True
        output["errors"].append("account must be OPEN before a credit can be considered")
        return output
    cycle = required(data, "cycle", dict)
    if not required(cycle, "id", str).strip():
        raise ValueError("cycle.id must not be empty")
    controls = required(data, "controls", dict)
    if required(controls, "history_reviewed") is not True:
        output["manual_review_required"] = True
        output["errors"].append("transaction history must be reviewed for duplicate corrections")
    if required(controls, "no_prior_correction_within_14_days") is not True:
        output["manual_review_required"] = True
        output["errors"].append("prior correction or 14-day cooldown has not been cleared")

    if account_class == "Bluest Account":
        total = calculate_bluest(data, output)
    elif account_class == "Light Green Account":
        total = calculate_light_green(data, output)
    else:
        output["manual_review_required"] = True
        output["errors"].append("unsupported account class for this ATM-fee calculator")
        return output

    output["candidate_credit_amount"] = render(total)
    rebates = output["correction_counts"]["rebate_credit"]
    refunds = output["correction_counts"]["fee_refund"]
    if total == ZERO:
        return output
    if rebates > refunds:
        output["recommended_credit_type"] = "rebate_credit"
    elif refunds > rebates:
        output["recommended_credit_type"] = "fee_refund"
    else:
        output["manual_review_required"] = True
        output["errors"].append("no majority correction type; do not guess the credit type")

    output["actionable"] = (
        not output["manual_review_required"]
        and not output["errors"]
        and output["recommended_credit_type"] is not None
        and total > ZERO
    )
    return output


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        result = main(payload)
    except (ValueError, KeyError, TypeError) as exc:
        result = base_output()
        result["manual_review_required"] = True
        result["errors"].append(str(exc))
    print(json.dumps(result, sort_keys=True))
