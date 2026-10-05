#!/usr/bin/env python3
"""Calculate confirmed checking-account ATM-fee corrections from mapped records.

Input: JSON object on stdin as documented in SKILL.md.
Output: JSON object containing event calculations, account totals, unresolved items,
and non-actioning fee_refund recommendations. This program never calls bank tools.
"""
import json
import sys
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")
PRODUCTS = {"Blue", "Green", "Light Green"}
SCOPES = {"foreign", "domestic_out_of_network", "domestic_in_network"}
SOURCES = {"bank", "operator", "unknown"}
OFFSET_TYPES = {"fee_rebate", "rebate_credit", "fee_refund"}
REQUIRED_PREREQUISITES = (
    "identity_verified",
    "authority_verified",
    "account_ownership_verified",
    "checking_eligibility_verified",
    "balance_reviewed",
    "confirmation_requirements_checked",
    "one_credit_rule_and_cooldown_verified",
)


def as_money(value, nullable=False):
    if value is None and nullable:
        return None
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("invalid monetary value")
    if not amount.is_finite() or amount < 0:
        raise ValueError("monetary values must be finite and non-negative")
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


def fmt(amount):
    return format(amount.quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def parse_date(value):
    try:
        return datetime.strptime(value, "%m/%d/%Y")
    except (TypeError, ValueError):
        raise ValueError("date must use MM/DD/YYYY")


def expected_fee(product, scope, withdrawal, light_green_domestic_number=None):
    if scope == "domestic_in_network":
        return Decimal("0.00")
    if scope == "foreign":
        if product in {"Blue", "Green"}:
            return max(withdrawal * Decimal("0.03"), Decimal("5.00")).quantize(
                CENT, rounding=ROUND_HALF_UP
            )
        if withdrawal <= Decimal("100.00"):
            return Decimal("2.00")
        if withdrawal <= Decimal("300.00"):
            return Decimal("3.50")
        return Decimal("5.00")
    if product == "Blue":
        return min(withdrawal * Decimal("0.01"), Decimal("3.00")).quantize(
            CENT, rounding=ROUND_HALF_UP
        )
    if product == "Green":
        return Decimal("3.00")
    if light_green_domestic_number is None:
        raise ValueError("Light Green domestic withdrawal number is required")
    return Decimal("0.00") if light_green_domestic_number <= 4 else Decimal("1.50")


def normalize_record(raw, index):
    if not isinstance(raw, dict):
        raise ValueError("record must be an object")
    account_id = raw.get("account_id")
    if not isinstance(account_id, str) or not account_id:
        raise ValueError("account_id is required")
    product = raw.get("product")
    if product not in PRODUCTS:
        raise ValueError("product must be Blue, Green, or Light Green")
    scope = raw.get("scope")
    if scope not in SCOPES:
        raise ValueError("invalid scope")
    source = raw.get("fee_source")
    if source not in SOURCES:
        raise ValueError("fee_source must be bank, operator, or unknown")
    status = raw.get("fee_status")
    if status not in {"posted", "pending"}:
        raise ValueError("fee_status must be posted or pending")
    withdrawal = as_money(raw.get("withdrawal_amount"))
    if withdrawal == 0:
        raise ValueError("withdrawal_amount must be greater than zero")
    order = raw.get("order")
    if product == "Light Green" and scope == "domestic_out_of_network":
        if not isinstance(order, int) or isinstance(order, bool):
            raise ValueError("order must be an integer for Light Green domestic withdrawals")

    offsets = raw.get("offsetting_credits", [])
    if not isinstance(offsets, list):
        raise ValueError("offsetting_credits must be an array")
    posted_offsets = Decimal("0.00")
    for offset in offsets:
        if not isinstance(offset, dict):
            raise ValueError("each offsetting credit must be an object")
        if offset.get("type") not in OFFSET_TYPES:
            raise ValueError("invalid offsetting credit type")
        amount = as_money(offset.get("amount"))
        if offset.get("status") not in {"posted", "pending"}:
            raise ValueError("invalid offsetting credit status")
        if offset["status"] == "posted":
            posted_offsets += amount

    return {
        "index": index,
        "account_id": account_id,
        "product": product,
        "account_type": raw.get("account_type"),
        "account_status": raw.get("account_status"),
        "date": raw.get("date"),
        "date_value": parse_date(raw.get("date")),
        "order": order,
        "withdrawal": withdrawal,
        "scope": scope,
        "source": source,
        "fee": as_money(raw.get("bank_fee"), nullable=True),
        "fee_status": status,
        "posted_offsets": posted_offsets.quantize(CENT),
        "withdrawal_transaction_id": raw.get("withdrawal_transaction_id"),
        "fee_transaction_id": raw.get("fee_transaction_id"),
    }


def main(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
        raise ValueError("input must be an object with a records array")
    prerequisites = payload.get("prerequisites", {})
    if not isinstance(prerequisites, dict):
        raise ValueError("prerequisites must be an object")

    records, input_errors = [], []
    for index, raw in enumerate(payload["records"]):
        try:
            records.append(normalize_record(raw, index))
        except ValueError as exc:
            input_errors.append({"record_index": index, "error": str(exc)})

    # Only qualifying Light Green domestic out-of-network withdrawals count.
    light_groups = defaultdict(list)
    for record in records:
        if record["product"] == "Light Green" and record["scope"] == "domestic_out_of_network":
            light_groups[record["account_id"]].append(record)
    for group in light_groups.values():
        group.sort(key=lambda r: (r["date_value"], r["order"], r["index"]))
        for number, record in enumerate(group, 1):
            record["light_green_domestic_number"] = number

    account_info = {}
    totals = defaultdict(lambda: Decimal("0.00"))
    counts = defaultdict(int)
    events = []

    for record in records:
        account_id = record["account_id"]
        account_info.setdefault(account_id, record)
        event = {
            "record_index": record["index"],
            "account_id": account_id,
            "product": record["product"],
            "date": record["date"],
            "scope": record["scope"],
            "withdrawal_amount": fmt(record["withdrawal"]),
            "withdrawal_transaction_id": record["withdrawal_transaction_id"],
            "fee_transaction_id": record["fee_transaction_id"],
        }
        if "light_green_domestic_number" in record:
            event["monthly_domestic_out_of_network_withdrawal_number"] = record[
                "light_green_domestic_number"
            ]

        if record["source"] == "operator":
            event.update({
                "status": "excluded_operator_charge",
                "reason": "ATM operator charges are separate from the documented bank fee.",
            })
            events.append(event)
            continue
        if record["source"] == "unknown":
            event.update({
                "status": "unresolved",
                "reason": "Fee source is unknown; no bank-fee correction is calculated.",
            })
            events.append(event)
            continue
        if record["fee_status"] != "posted":
            event.update({
                "status": "pending_not_final",
                "reason": "A pending bank fee is not refunded as a final charge.",
            })
            events.append(event)
            continue
        if record["fee"] is None:
            event.update({
                "status": "no_posted_bank_fee",
                "reason": "No linked bank-fee amount was posted for this withdrawal.",
            })
            events.append(event)
            continue

        expected = expected_fee(
            record["product"], record["scope"], record["withdrawal"],
            record.get("light_green_domestic_number"),
        )
        net = max(record["fee"] - record["posted_offsets"], Decimal("0.00")).quantize(CENT)
        overcharge = max(net - expected, Decimal("0.00")).quantize(CENT)
        event.update({
            "expected_bank_fee": fmt(expected),
            "gross_posted_bank_fee": fmt(record["fee"]),
            "posted_offsetting_credits": fmt(record["posted_offsets"]),
            "net_posted_bank_charge": fmt(net),
            "confirmed_overcharge": fmt(overcharge),
            "status": "confirmed_overcharge" if overcharge else "no_customer_refund_due",
        })
        if overcharge:
            totals[account_id] += overcharge
            counts[account_id] += 1
        events.append(event)

    accounts = []
    for account_id, info in account_info.items():
        blockers = []
        if info["account_type"] != "checking":
            blockers.append("Returned account_type is not checking.")
        for key in REQUIRED_PREREQUISITES:
            if prerequisites.get(key) is not True:
                blockers.append("Prerequisite not affirmatively verified: " + key + ".")
        total = totals[account_id].quantize(CENT)
        recommendation = None
        if total > 0 and not blockers:
            recommendation = {
                "account_id": account_id,
                "amount": fmt(total),
                "credit_type": "fee_refund",
                "basis": "Exact sum of independently confirmed posted bank ATM-fee overcharges after posted offsets.",
                "execution": "Make one live checking-account credit call only after final prerequisite recheck.",
            }
        accounts.append({
            "account_id": account_id,
            "product": info["product"],
            "account_type": info["account_type"],
            "account_status": info["account_status"],
            "confirmed_overcharge_total": fmt(total),
            "confirmed_overcharge_event_count": counts[account_id],
            "blocking_reasons": blockers,
            "credit_recommendation": recommendation,
        })

    return {"events": events, "accounts": accounts, "input_errors": input_errors}


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), separators=(",", ":")))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, separators=(",", ":")))
        sys.exit(1)
