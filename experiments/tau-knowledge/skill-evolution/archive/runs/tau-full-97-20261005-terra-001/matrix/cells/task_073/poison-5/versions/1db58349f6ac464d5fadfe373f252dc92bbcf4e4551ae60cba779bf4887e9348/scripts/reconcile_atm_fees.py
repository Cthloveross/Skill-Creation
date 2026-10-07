#!/usr/bin/env python3
"""Calculate documented bank ATM fees from explicitly matched transaction records.

Reads one JSON object from stdin and writes one JSON object to stdout.  It never
calls banking tools and does not change account data.
"""
import json
import sys
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")
VALID_PRODUCTS = {"Blue", "Green", "Light Green"}
VALID_SCOPES = {"foreign", "domestic_out_of_network"}
VALID_SOURCES = {"bank", "operator", "unknown"}


def money(value):
    if value is None:
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("invalid monetary value")
    if not result.is_finite() or result < 0:
        raise ValueError("monetary values must be finite and non-negative")
    return result.quantize(CENT, rounding=ROUND_HALF_UP)


def fmt(value):
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def parsed_date(value):
    try:
        return datetime.strptime(value, "%m/%d/%Y")
    except (TypeError, ValueError):
        raise ValueError("date must use MM/DD/YYYY")


def expected_fee(product, scope, withdrawal, domestic_number=None):
    if scope == "foreign":
        if product in {"Blue", "Green"}:
            return max(withdrawal * Decimal("0.03"), Decimal("5.00")).quantize(CENT, rounding=ROUND_HALF_UP)
        if withdrawal <= Decimal("100.00"):
            return Decimal("2.00")
        if withdrawal <= Decimal("300.00"):
            return Decimal("3.50")
        return Decimal("5.00")
    if product == "Blue":
        return min(withdrawal * Decimal("0.01"), Decimal("3.00")).quantize(CENT, rounding=ROUND_HALF_UP)
    if product == "Green":
        return Decimal("3.00")
    if domestic_number is None:
        raise ValueError("Light Green domestic withdrawal number is required")
    return Decimal("0.00") if domestic_number <= 4 else Decimal("1.50")


def record_error(index, message):
    return {"record_index": index, "error": message}


def main(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
        raise ValueError("input must be an object containing a records array")
    prerequisites = payload.get("prerequisites", {})
    if not isinstance(prerequisites, dict):
        raise ValueError("prerequisites must be an object")

    normalized = []
    errors = []
    for index, raw in enumerate(payload["records"]):
        try:
            if not isinstance(raw, dict):
                raise ValueError("record must be an object")
            account_id = raw.get("account_id")
            product = raw.get("product")
            scope = raw.get("scope")
            source = raw.get("fee_source")
            if not isinstance(account_id, str) or not account_id:
                raise ValueError("account_id is required")
            if product not in VALID_PRODUCTS:
                raise ValueError("product must be Blue, Green, or Light Green")
            if scope not in VALID_SCOPES:
                raise ValueError("scope must be foreign or domestic_out_of_network")
            if source not in VALID_SOURCES:
                raise ValueError("fee_source must be bank, operator, or unknown")
            status = raw.get("fee_status")
            if status not in {"posted", "pending"}:
                raise ValueError("fee_status must be posted or pending")
            withdrawal = money(raw.get("withdrawal_amount"))
            if withdrawal is None or withdrawal == 0:
                raise ValueError("withdrawal_amount must be greater than zero")
            fee = money(raw.get("bank_fee"))
            credits = raw.get("offsetting_credits", [])
            if not isinstance(credits, list):
                raise ValueError("offsetting_credits must be an array")
            posted_credits = Decimal("0.00")
            for credit in credits:
                if not isinstance(credit, dict):
                    raise ValueError("each offsetting credit must be an object")
                amount = money(credit.get("amount"))
                if amount is None:
                    raise ValueError("offsetting credit amount is required")
                if credit.get("status") == "posted":
                    posted_credits += amount
            item = {
                "index": index,
                "account_id": account_id,
                "product": product,
                "account_type": raw.get("account_type"),
                "account_class": raw.get("account_class"),
                "account_status": raw.get("account_status"),
                "date": raw.get("date"),
                "date_value": parsed_date(raw.get("date")),
                "order": raw.get("order"),
                "scope": scope,
                "source": source,
                "fee_status": status,
                "withdrawal": withdrawal,
                "fee": fee,
                "posted_credits": posted_credits.quantize(CENT),
                "withdrawal_transaction_id": raw.get("withdrawal_transaction_id"),
                "fee_transaction_id": raw.get("fee_transaction_id"),
            }
            if product == "Light Green" and scope == "domestic_out_of_network":
                if not isinstance(item["order"], int) or isinstance(item["order"], bool):
                    raise ValueError("order must be an integer for Light Green domestic withdrawals")
            normalized.append(item)
        except ValueError as exc:
            errors.append(record_error(index, str(exc)))

    # Number Light Green domestic out-of-network withdrawals per account, using
    # supplied chronological order. Operator fees still represent a withdrawal
    # and therefore count toward the four monthly free withdrawals.
    light_groups = defaultdict(list)
    for item in normalized:
        if item["product"] == "Light Green" and item["scope"] == "domestic_out_of_network":
            light_groups[item["account_id"]].append(item)
    for items in light_groups.values():
        items.sort(key=lambda x: (x["date_value"], x["order"], x["index"]))
        for number, item in enumerate(items, 1):
            item["domestic_number"] = number

    results = []
    account_info = {}
    account_blockers = defaultdict(list)
    totals = defaultdict(lambda: Decimal("0.00"))
    confirmed_counts = defaultdict(int)

    for item in normalized:
        account_id = item["account_id"]
        account_info.setdefault(account_id, item)
        result = {
            "record_index": item["index"],
            "account_id": account_id,
            "product": item["product"],
            "date": item["date"],
            "scope": item["scope"],
            "withdrawal_amount": fmt(item["withdrawal"]),
            "withdrawal_transaction_id": item["withdrawal_transaction_id"],
            "fee_transaction_id": item["fee_transaction_id"],
        }
        if item["product"] == "Light Green" and item["scope"] == "domestic_out_of_network":
            result["monthly_domestic_out_of_network_withdrawal_number"] = item["domestic_number"]

        if item["source"] == "operator":
            result.update({"status": "excluded_operator_charge", "reason": "Operator/network surcharges are separate from the documented bank ATM fee."})
            results.append(result)
            continue
        if item["source"] == "unknown":
            result.update({"status": "unresolved", "reason": "Fee source is unknown; do not treat it as a refundable bank fee."})
            account_blockers[account_id].append("At least one in-scope fee has an unknown source.")
            results.append(result)
            continue
        if item["fee_status"] != "posted":
            result.update({"status": "pending_not_final", "reason": "Pending bank fees must not be refunded as final charges."})
            account_blockers[account_id].append("At least one in-scope bank fee is pending.")
            results.append(result)
            continue
        if item["fee"] is None:
            result.update({"status": "unresolved", "reason": "No linked bank_fee amount was supplied for a bank-fee record."})
            account_blockers[account_id].append("At least one bank fee lacks a supportable linked amount.")
            results.append(result)
            continue

        expected = expected_fee(item["product"], item["scope"], item["withdrawal"], item.get("domestic_number"))
        net = (item["fee"] - item["posted_credits"]).quantize(CENT)
        overcharge = max(net - expected, Decimal("0.00")).quantize(CENT)
        result.update({
            "expected_bank_fee": fmt(expected),
            "gross_posted_bank_fee": fmt(item["fee"]),
            "posted_offsetting_credits": fmt(item["posted_credits"]),
            "net_posted_bank_charge": fmt(net),
            "confirmed_overcharge": fmt(overcharge),
            "status": "confirmed_overcharge" if overcharge > 0 else "no_customer_refund_due",
        })
        if overcharge > 0:
            totals[account_id] += overcharge
            confirmed_counts[account_id] += 1
        results.append(result)

    required_prereqs = [
        "identity_verified", "authority_verified", "account_ownership_verified",
        "available_balance_verified", "confirmation_requirements_checked", "credit_call_available",
    ]
    accounts = []
    for account_id, info in account_info.items():
        blockers = list(account_blockers[account_id])
        if info["account_type"] != "checking":
            blockers.append("Returned account_type is not checking.")
        for key in required_prereqs:
            if prerequisites.get(key) is not True:
                blockers.append("Prerequisite not affirmatively verified: " + key + ".")
        total = totals[account_id].quantize(CENT)
        recommendation = None
        if total > 0 and not blockers:
            recommendation = {
                "account_id": account_id,
                "amount": fmt(total),
                "credit_type": "fee_refund",
                "basis": "Sum of confirmed posted bank ATM-fee overcharges after posted offsets.",
                "warning": "Recommendation only; perform live checks and make at most one permitted credit-tool call for this account.",
            }
        accounts.append({
            "account_id": account_id,
            "product": info["product"],
            "account_type": info["account_type"],
            "confirmed_overcharge_total": fmt(total),
            "confirmed_overcharge_event_count": confirmed_counts[account_id],
            "blocking_reasons": blockers,
            "credit_recommendation": recommendation,
        })

    return {"results": results, "accounts": accounts, "input_errors": errors}


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        print(json.dumps(main(data), separators=(",", ":")))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, separators=(",", ":")))
        sys.exit(1)
