#!/usr/bin/env python3
"""Read normalized checking ATM activity from JSON and emit a cautious fee review."""
import json
import re
import sys
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")
PRODUCTS = {"blue": "Blue", "green": "Green", "light green": "Light Green"}
CREDIT_TYPES = {"fee_rebate", "rebate_credit", "fee_refund"}


def money(value):
    try:
        return Decimal(str(value)).copy_abs().quantize(CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        return None


def date_value(value):
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(value), fmt).date()
        except ValueError:
            pass
    return None


def month_matches(tx, review_month):
    d = date_value(tx.get("date"))
    return d is not None and d.strftime("%Y-%m") == review_month


def as_amount(value):
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), ".2f") if value is not None else None


def expected_fee(product, category, withdrawal_amount, light_ordinal=None):
    if withdrawal_amount is None:
        return None, "withdrawal amount is invalid or unavailable"
    if product == "Blue":
        if category == "domestic_out_of_network":
            return min(withdrawal_amount * Decimal("0.01"), Decimal("3.00")).quantize(CENT), "1% of withdrawal, capped at $3.00"
        if category == "foreign":
            return max(withdrawal_amount * Decimal("0.03"), Decimal("5.00")).quantize(CENT), "greater of 3% of USD-equivalent withdrawal or $5.00"
    elif product == "Green":
        if category == "domestic_out_of_network":
            return Decimal("3.00"), "$3.00 per non-network withdrawal"
        if category == "foreign":
            return max(withdrawal_amount * Decimal("0.03"), Decimal("5.00")).quantize(CENT), "greater of 3% of settled USD-equivalent withdrawal or $5.00"
    elif product == "Light Green":
        if category == "foreign":
            if withdrawal_amount <= Decimal("100.00"):
                return Decimal("2.00"), "$2.00 for a withdrawal up to and including $100"
            if withdrawal_amount <= Decimal("300.00"):
                return Decimal("3.50"), "$3.50 for a withdrawal over $100 through $300"
            return Decimal("5.00"), "$5.00 for a withdrawal above $300"
        if category == "domestic_out_of_network":
            if light_ordinal is None:
                return None, "Light Green monthly sequence is incomplete"
            if light_ordinal <= 4:
                return Decimal("0.00"), "one of the first four monthly out-of-network withdrawals"
            return Decimal("1.50"), "withdrawal after four free monthly out-of-network withdrawals"
    return None, "unsupported product or location category"


def error(message):
    print(json.dumps({"status": "error", "error": message}, separators=(",", ":")))
    raise SystemExit(0)


def main(payload):
    review_month = payload.get("review_month")
    if not isinstance(review_month, str) or not re.fullmatch(r"\d{4}-\d{2}", review_month):
        error("review_month must be YYYY-MM")
    try:
        datetime.strptime(review_month + "-01", "%Y-%m-%d")
    except ValueError:
        error("review_month is not a valid calendar month")
    accounts = payload.get("accounts")
    tx_by_account = payload.get("transactions_by_account")
    contexts = payload.get("withdrawal_context", [])
    if not isinstance(accounts, list) or not isinstance(tx_by_account, dict) or not isinstance(contexts, list):
        error("accounts, transactions_by_account, and withdrawal_context must be arrays/object as documented")

    warnings = []
    all_transactions = {}
    for account_id, transactions in tx_by_account.items():
        if not isinstance(transactions, list):
            error("each transactions_by_account value must be an array")
        for tx in transactions:
            if not isinstance(tx, dict) or not tx.get("transaction_id"):
                error("every transaction requires a transaction_id")
            tid = str(tx["transaction_id"])
            if tid in all_transactions:
                error("transaction_id values must be unique across supplied accounts")
            all_transactions[tid] = (str(account_id), tx)

    context_by_fee = {}
    contexts_by_withdrawal = defaultdict(list)
    for item in contexts:
        if not isinstance(item, dict):
            error("each withdrawal_context item must be an object")
        fee_id = str(item.get("fee_transaction_id", ""))
        withdrawal_id = str(item.get("withdrawal_transaction_id", ""))
        category = item.get("location_category")
        if not fee_id or not withdrawal_id or category not in {"domestic_out_of_network", "foreign"}:
            error("withdrawal_context needs fee_transaction_id, withdrawal_transaction_id, and a supported location_category")
        if fee_id in context_by_fee:
            error("only one withdrawal_context may be supplied for each fee_transaction_id")
        context_by_fee[fee_id] = item
        contexts_by_withdrawal[withdrawal_id].append(item)

    account_reports = []
    for account in accounts:
        if not isinstance(account, dict) or not account.get("account_id"):
            error("each account requires account_id and product")
        account_id = str(account["account_id"])
        raw_product = str(account.get("product", "")).strip().lower()
        product = PRODUCTS.get(raw_product)
        report = {
            "account_id": account_id,
            "product": account.get("product"),
            "account_class": account.get("account_class"),
            "status": account.get("status"),
            "fees": [],
            "rebate_candidates": [],
            "warnings": []
        }
        transactions = tx_by_account.get(account_id, [])
        monthly = [tx for tx in transactions if month_matches(tx, review_month)]
        invalid_dates = [str(tx.get("transaction_id")) for tx in transactions if tx.get("date") and date_value(tx.get("date")) is None]
        if invalid_dates:
            report["warnings"].append("Transactions with invalid dates were excluded: " + ", ".join(invalid_dates))
        if product is None:
            report["warnings"].append("Unsupported or missing product; no fee schedule calculation was performed.")

        # A Light Green free-withdrawal ordinal is reliable only if every November ATM
        # withdrawal has a supplied location context. Sort chronologically, never in API order.
        light_ordinals = {}
        if product == "Light Green":
            monthly_withdrawals = [tx for tx in monthly if tx.get("type") == "atm_withdrawal"]
            unclassified = [str(tx.get("transaction_id")) for tx in monthly_withdrawals if str(tx.get("transaction_id")) not in contexts_by_withdrawal]
            if unclassified:
                report["warnings"].append("Cannot establish Light Green free-withdrawal sequence; location context is missing for ATM withdrawal(s): " + ", ".join(unclassified))
            else:
                domestic = []
                for tx in monthly_withdrawals:
                    tid = str(tx.get("transaction_id"))
                    categories = {x["location_category"] for x in contexts_by_withdrawal[tid]}
                    if "domestic_out_of_network" in categories:
                        d = date_value(tx.get("date"))
                        domestic.append((d, tid))
                for ordinal, (_, tid) in enumerate(sorted(domestic), start=1):
                    light_ordinals[tid] = ordinal

        for tx in monthly:
            tx_type = tx.get("type")
            desc = str(tx.get("description", ""))
            if tx_type in CREDIT_TYPES and ("atm" in desc.lower() or tx_type == "fee_rebate"):
                report["rebate_candidates"].append({
                    "transaction_id": tx.get("transaction_id"), "date": tx.get("date"), "description": desc,
                    "amount": as_amount(money(tx.get("amount"))), "type": tx_type, "status": tx.get("status"),
                    "note": "Candidate ATM-related credit; it is not automatically linked to a fee."
                })
            if tx_type != "atm_fee":
                continue
            tid = str(tx.get("transaction_id"))
            assessment = {
                "fee_transaction_id": tid, "fee_date": tx.get("date"), "fee_description": desc,
                "actual_fee": as_amount(money(tx.get("amount"))), "fee_status": tx.get("status"),
                "assessment": "insufficient_evidence", "expected_fee": None, "calculation": None
            }
            context = context_by_fee.get(tid)
            if context is None:
                assessment["reason"] = "No explicit supported link to a cash withdrawal and location category."
                report["fees"].append(assessment)
                continue
            withdrawal_id = str(context["withdrawal_transaction_id"])
            linked = all_transactions.get(withdrawal_id)
            if linked is None:
                assessment["reason"] = "Linked withdrawal_transaction_id was not supplied."
                report["fees"].append(assessment)
                continue
            linked_account, withdrawal = linked
            if linked_account != account_id or withdrawal.get("type") != "atm_withdrawal":
                assessment["reason"] = "Linked transaction is not an ATM withdrawal on this account."
                report["fees"].append(assessment)
                continue
            category = context["location_category"]
            amount = money(withdrawal.get("amount"))
            ordinal = light_ordinals.get(withdrawal_id)
            expected, calculation = expected_fee(product, category, amount, ordinal)
            assessment.update({
                "withdrawal_transaction_id": withdrawal_id, "withdrawal_date": withdrawal.get("date"),
                "withdrawal_amount": as_amount(amount), "withdrawal_status": withdrawal.get("status"),
                "location_category": category, "light_green_domestic_ordinal": ordinal,
                "expected_fee": as_amount(expected), "calculation": calculation
            })
            actual = money(tx.get("amount"))
            if expected is None or actual is None:
                assessment["reason"] = calculation or "Fee amount is invalid or unavailable."
            else:
                assessment["assessment"] = "matches_schedule" if actual == expected else "does_not_match_schedule"
                assessment["reason"] = "Compared absolute fee amount with the applicable schedule; third-party operator fees are excluded."
                if tx.get("status") != "posted" or withdrawal.get("status") != "posted":
                    assessment["reason"] += " At least one item is pending, so settlement may change."
            report["fees"].append(assessment)
        account_reports.append(report)

    return {"status": "ok", "review_month": review_month, "account_reports": account_reports, "warnings": warnings}


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        error("stdin must contain one valid JSON object: " + str(exc))
    if not isinstance(payload, dict):
        error("stdin JSON must be an object")
    print(json.dumps(main(payload), separators=(",", ":")))
