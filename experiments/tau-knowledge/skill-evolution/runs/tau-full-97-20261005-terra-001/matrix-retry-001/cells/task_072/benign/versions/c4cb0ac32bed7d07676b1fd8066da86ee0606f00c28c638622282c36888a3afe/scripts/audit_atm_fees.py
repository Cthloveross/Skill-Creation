#!/usr/bin/env python3
"""Audit supported Bluest and Light Green ATM corrections.

Reads one JSON object from stdin and emits one JSON object to stdout.  The script
is deterministic, uses decimal cents, and never calls banking tools.
"""
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")
ANNOTATIONS = {
    "out_of_network_withdrawal", "light_domestic_oon_rho_fee",
    "light_foreign_rho_fee", "bluest_foreign_rho_fee",
    "bluest_out_of_network_rho_fee", "bluest_third_party_atm_fee",
    "bluest_atm_rebate",
}


def decimal(value, signed=False):
    try:
        amount = Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("invalid decimal amount")
    return amount if signed else abs(amount)


def dollars(value):
    return format(value.quantize(CENT), ".2f")


def tx_date(tx):
    return datetime.strptime(str(tx.get("date", "")), "%m/%d/%Y")


def in_month(tx, year, month):
    date = tx_date(tx)
    return date.year == year and date.month == month


def posted(tx):
    return str(tx.get("status", "")).lower() == "posted"


def txid(tx):
    return str(tx.get("transaction_id", ""))


def append_component(result, transaction_id, kind, actual, expected, reason):
    difference = (actual - expected).quantize(CENT)
    if difference > 0:
        result["components"].append({
            "transaction_id": transaction_id,
            "correction_type": kind,
            "actual": dollars(actual),
            "expected": dollars(expected),
            "amount": dollars(difference),
            "reason": reason,
        })


def automatic_bluest_kind(tx):
    description = str(tx.get("description", "")).strip().upper()
    if description.startswith("FOREIGN ATM FEE"):
        return "bluest_foreign_rho_fee"
    if description == "NON-RHO ATM FEE":
        return "bluest_third_party_atm_fee"
    return None


def audit_bluest(result, transactions, labels):
    third_party_fees = Decimal("0.00")
    posted_rebates = Decimal("0.00")

    for tx in transactions:
        tid = txid(tx)
        if not posted(tx):
            if tx.get("type") in ("atm_fee", "fee_rebate"):
                result["pending_relevant"].append(tid)
            continue
        if tx.get("type") == "fee_rebate":
            # A posted fee_rebate is the account-history evidence of an ATM rebate.
            posted_rebates += max(decimal(tx.get("amount"), signed=True), Decimal("0.00"))
            continue
        if tx.get("type") != "atm_fee":
            continue
        kind = labels.get(tid, {}).get("kind") or automatic_bluest_kind(tx)
        actual = decimal(tx.get("amount"))
        if kind == "bluest_foreign_rho_fee":
            append_component(result, tid, "fee_refund", actual, Decimal("0.00"),
                             "Bluest has no Rho foreign ATM withdrawal fee")
        elif kind == "bluest_out_of_network_rho_fee":
            append_component(result, tid, "fee_refund", actual, Decimal("2.00"),
                             "Bluest Rho out-of-network ATM fee")
        elif kind == "bluest_third_party_atm_fee":
            third_party_fees += actual
        else:
            result["unresolved"].append(
                "Bluest ATM fee %s lacks an established Rho/third-party classification." % tid)

    entitled = min(third_party_fees, Decimal("50.00"))
    if entitled > posted_rebates:
        result["components"].append({
            "transaction_id": None,
            "correction_type": "rebate_credit",
            "actual": dollars(posted_rebates),
            "expected": dollars(entitled),
            "amount": dollars(entitled - posted_rebates),
            "reason": "Bluest eligible third-party ATM fee rebate, capped at $50 monthly",
        })


def audit_light_green(result, transactions, labels):
    withdrawals = {}
    domestic_oon = []
    for tx in transactions:
        tid = txid(tx)
        if tx.get("type") != "atm_withdrawal":
            continue
        if not posted(tx):
            result["pending_relevant"].append(tid)
            continue
        withdrawals[tid] = tx
        if labels.get(tid, {}).get("kind") == "out_of_network_withdrawal":
            domestic_oon.append(tx)
    domestic_oon.sort(key=tx_date)
    domestic_expected = {
        txid(tx): Decimal("0.00") if position < 4 else Decimal("1.50")
        for position, tx in enumerate(domestic_oon)
    }

    for tx in transactions:
        tid = txid(tx)
        if tx.get("type") != "atm_fee":
            continue
        if not posted(tx):
            result["pending_relevant"].append(tid)
            continue
        label = labels.get(tid)
        if not label or label.get("kind") not in {
            "light_domestic_oon_rho_fee", "light_foreign_rho_fee"
        }:
            result["unresolved"].append(
                "Light Green ATM fee %s lacks an established fee classification and withdrawal link." % tid)
            continue
        withdrawal_id = str(label.get("withdrawal_id", ""))
        withdrawal = withdrawals.get(withdrawal_id)
        if withdrawal is None:
            result["unresolved"].append(
                "Light Green fee %s is not linked to a posted in-month ATM withdrawal." % tid)
            continue
        actual = decimal(tx.get("amount"))
        if label["kind"] == "light_domestic_oon_rho_fee":
            if withdrawal_id not in domestic_expected:
                result["unresolved"].append(
                    "Domestic out-of-network fee %s lacks a supported linked out-of-network withdrawal." % tid)
                continue
            append_component(result, tid, "fee_refund", actual,
                             domestic_expected[withdrawal_id],
                             "Light Green domestic out-of-network ATM fee")
        else:
            withdrawal_amount = decimal(withdrawal.get("amount"))
            expected = (Decimal("2.00") if withdrawal_amount <= Decimal("100.00")
                        else Decimal("3.50") if withdrawal_amount <= Decimal("300.00")
                        else Decimal("5.00"))
            append_component(result, tid, "fee_refund", actual, expected,
                             "Light Green foreign ATM fee tier")


def finalize(result):
    total = sum((Decimal(x["amount"]) for x in result["components"]), Decimal("0.00"))
    result["credit_amount"] = dollars(total)
    if result["unresolved"]:
        result["status"] = "manual_review"
        return
    if total == 0:
        result["status"] = "no_correction"
        return
    kinds = Counter(component["correction_type"] for component in result["components"])
    highest = max(kinds.values())
    winners = [kind for kind, count in kinds.items() if count == highest]
    if len(winners) != 1:
        result["status"] = "manual_review"
        result["unresolved"].append("Correction-type counts tie; no authorized credit type is available.")
        return
    result["credit_type"] = winners[0]
    result["status"] = "credit_recommended"
    result["ready_for_credit"] = True


def audit_account(account, raw_transactions, labels, year, month):
    result = {
        "account_id": str(account.get("account_id", "")),
        "account_class": account.get("account_class"),
        "eligible_checking_account": str(account.get("account_type", "")).lower() == "checking",
        "components": [], "unresolved": [], "pending_relevant": [],
        "credit_amount": "0.00", "credit_type": None,
        "ready_for_credit": False, "status": "no_correction",
    }
    if not result["account_id"]:
        result["status"] = "manual_review"
        result["unresolved"].append("Account has no account_id.")
        return result
    if not result["eligible_checking_account"]:
        result["status"] = "ineligible_nonchecking"
        return result
    if not isinstance(raw_transactions, list):
        result["status"] = "manual_review"
        result["unresolved"].append("Transaction history is not a list.")
        return result

    selected = []
    ids = set()
    for tx in raw_transactions:
        if not isinstance(tx, dict) or not txid(tx):
            result["unresolved"].append("A transaction lacks a transaction_id.")
            continue
        if txid(tx) in ids:
            result["unresolved"].append("Duplicate transaction_id %s." % txid(tx))
            continue
        ids.add(txid(tx))
        try:
            decimal(tx.get("amount"))
            if in_month(tx, year, month):
                selected.append(tx)
        except ValueError as exc:
            result["unresolved"].append("Invalid transaction %s: %s." % (txid(tx), exc))
    selected.sort(key=tx_date)

    valid_labels = {}
    selected_ids = {txid(tx) for tx in selected}
    for tid, label in labels.items():
        if tid not in selected_ids:
            result["unresolved"].append("Annotation %s does not reference an in-month transaction." % tid)
        else:
            valid_labels[tid] = label

    account_class = str(account.get("account_class", "")).lower()
    if "bluest" in account_class:
        audit_bluest(result, selected, valid_labels)
    elif "light green" in account_class:
        audit_light_green(result, selected, valid_labels)
    else:
        result["unresolved"].append("No documented ATM schedule for this account class.")
    finalize(result)
    return result


def main(payload):
    try:
        year, month = int(payload["review_year"]), int(payload["review_month"])
        if not 1 <= month <= 12:
            raise ValueError("review_month must be 1 through 12")
    except (KeyError, TypeError, ValueError) as exc:
        return {"errors": ["invalid review period: %s" % exc], "accounts": []}
    accounts = payload.get("accounts")
    histories = payload.get("transactions_by_account")
    annotations = payload.get("annotations", [])
    if not isinstance(accounts, list) or not isinstance(histories, dict) or not isinstance(annotations, list):
        return {"errors": ["accounts, transactions_by_account, and annotations must be list, object, and list"], "accounts": []}

    errors = []
    labels = defaultdict(dict)
    for position, annotation in enumerate(annotations):
        if not isinstance(annotation, dict):
            errors.append("annotation %d is not an object" % position)
            continue
        aid = str(annotation.get("account_id", ""))
        tid = str(annotation.get("transaction_id", ""))
        kind = annotation.get("kind")
        if not aid or not tid or kind not in ANNOTATIONS:
            errors.append("annotation %d has invalid account_id, transaction_id, or kind" % position)
            continue
        if tid in labels[aid]:
            errors.append("duplicate annotation for transaction %s in account %s" % (tid, aid))
            continue
        labels[aid][tid] = annotation

    results = []
    for account in accounts:
        if not isinstance(account, dict):
            errors.append("account entry is not an object")
            continue
        aid = str(account.get("account_id", ""))
        results.append(audit_account(account, histories.get(aid, []), labels.get(aid, {}), year, month))
    return {"review_period": "%04d-%02d" % (year, month), "errors": errors, "accounts": results}


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("top-level JSON must be an object")
        print(json.dumps(main(data), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"errors": ["input processing failed: %s" % exc], "accounts": []}, sort_keys=True))
