#!/usr/bin/env python3
"""Calculate supported ATM fee/rebate corrections from supplied account activity.
Reads one JSON object from stdin and emits one JSON object to stdout.
No network access, tool calls, or file writes are performed.
"""
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENTS = Decimal("0.01")
VALID_KINDS = {
    "out_of_network_withdrawal", "foreign_withdrawal",
    "light_domestic_oon_rho_fee", "light_foreign_rho_fee",
    "bluest_foreign_rho_fee", "bluest_out_of_network_rho_fee",
    "bluest_third_party_atm_fee", "bluest_atm_rebate",
}


def money(value):
    try:
        return Decimal(str(value)).copy_abs().quantize(CENTS, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("amount is not a valid decimal")


def signed_money(value):
    try:
        return Decimal(str(value)).quantize(CENTS, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("amount is not a valid decimal")


def fmt(value):
    return format(value.quantize(CENTS), ".2f")


def date_key(tx):
    return datetime.strptime(str(tx.get("date", "")), "%m/%d/%Y")


def in_period(tx, year, month):
    d = date_key(tx)
    return d.year == year and d.month == month


def find_account_class(account):
    return str(account.get("account_class", "")).strip().lower()


def main(data):
    errors = []
    try:
        year, month = int(data["review_year"]), int(data["review_month"])
        if not 1 <= month <= 12:
            raise ValueError("review_month must be 1 through 12")
    except Exception as exc:
        return {"errors": ["invalid review period: %s" % exc], "accounts": []}

    accounts = data.get("accounts")
    tx_by_account = data.get("transactions_by_account")
    annotations = data.get("annotations", [])
    if not isinstance(accounts, list) or not isinstance(tx_by_account, dict) or not isinstance(annotations, list):
        return {"errors": ["accounts, transactions_by_account, and annotations must be list/object/list"], "accounts": []}

    annotation_map = defaultdict(dict)
    for index, ann in enumerate(annotations):
        if not isinstance(ann, dict):
            errors.append("annotation %d is not an object" % index)
            continue
        aid, tid, kind = ann.get("account_id"), ann.get("transaction_id"), ann.get("kind")
        if not aid or not tid or kind not in VALID_KINDS:
            errors.append("annotation %d has invalid account_id, transaction_id, or kind" % index)
            continue
        if tid in annotation_map[aid]:
            errors.append("duplicate annotation for transaction %s in account %s" % (tid, aid))
            continue
        annotation_map[aid][tid] = ann

    results = []
    for account in accounts:
        if not isinstance(account, dict) or not account.get("account_id"):
            errors.append("account entry lacks account_id")
            continue
        aid = str(account["account_id"])
        result = audit_account(account, tx_by_account.get(aid, []), annotation_map.get(aid, {}), year, month)
        results.append(result)

    return {"review_period": "%04d-%02d" % (year, month), "errors": errors, "accounts": results}


def audit_account(account, raw_txs, annotations, year, month):
    aid = str(account["account_id"])
    result = {
        "account_id": aid,
        "account_class": account.get("account_class"),
        "eligible_checking_account": str(account.get("account_type", "")).lower() == "checking",
        "components": [], "unresolved": [], "pending_relevant": [],
        "status": "no_correction", "ready_for_credit": False,
        "credit_amount": "0.00", "credit_type": None,
    }
    if not result["eligible_checking_account"]:
        result["status"] = "ineligible_nonchecking"
        return result
    if not isinstance(raw_txs, list):
        result["status"] = "manual_review"
        result["unresolved"].append("Transaction history was not a list.")
        return result

    txs = []
    ids = set()
    for tx in raw_txs:
        if not isinstance(tx, dict) or not tx.get("transaction_id"):
            result["unresolved"].append("A transaction lacks a transaction_id.")
            continue
        tid = str(tx["transaction_id"])
        if tid in ids:
            result["unresolved"].append("Duplicate transaction_id %s." % tid)
            continue
        ids.add(tid)
        try:
            if in_period(tx, year, month):
                money(tx.get("amount"))
                txs.append(tx)
        except ValueError as exc:
            result["unresolved"].append("Transaction %s has invalid date or amount: %s." % (tid, exc))
    txs.sort(key=date_key)
    by_id = {str(t["transaction_id"]): t for t in txs}

    # Annotation references must be valid, in period, and applicable to the transaction status/type.
    valid_annotations = {}
    for tid, ann in annotations.items():
        tx = by_id.get(str(tid))
        if not tx:
            result["unresolved"].append("Annotation %s does not reference an in-period transaction." % tid)
            continue
        kind = ann["kind"]
        if kind in ("out_of_network_withdrawal", "foreign_withdrawal") and tx.get("type") != "atm_withdrawal":
            result["unresolved"].append("Annotation %s must be on an ATM withdrawal." % tid)
            continue
        if kind not in ("out_of_network_withdrawal", "foreign_withdrawal") and tx.get("status") != "posted":
            result["pending_relevant"].append(tid)
            continue
        valid_annotations[str(tid)] = ann

    # Pending ATM items are disclosed but never made into correction components.
    for tx in txs:
        if tx.get("status") == "pending" and tx.get("type") in ("atm_withdrawal", "atm_fee"):
            result["pending_relevant"].append(str(tx["transaction_id"]))

    klass = find_account_class(account)
    if "bluest" in klass:
        audit_bluest(result, txs, valid_annotations)
    elif "light green" in klass:
        audit_light_green(result, txs, valid_annotations, by_id)
    else:
        result["unresolved"].append("Unsupported checking account class; no documented ATM schedule was selected.")

    finalize(result)
    return result


def add_component(result, transaction_id, correction_type, actual, expected, reason):
    diff = (actual - expected).quantize(CENTS)
    if diff <= 0:
        return
    result["components"].append({
        "transaction_id": transaction_id,
        "correction_type": correction_type,
        "actual": fmt(actual), "expected": fmt(expected), "amount": fmt(diff), "reason": reason,
    })


def audit_light_green(result, txs, anns, by_id):
    # Monthly free-withdrawal order must use all supported posted domestic OON withdrawals.
    domestic = []
    for tx in txs:
        ann = anns.get(str(tx["transaction_id"]))
        if tx.get("status") == "posted" and ann and ann["kind"] == "out_of_network_withdrawal":
            domestic.append(tx)
    domestic.sort(key=date_key)
    domestic_expected = {str(tx["transaction_id"]): (Decimal("0.00") if i < 4 else Decimal("1.50"))
                         for i, tx in enumerate(domestic)}

    for tx in txs:
        tid = str(tx["transaction_id"])
        ann = anns.get(tid)
        if tx.get("type") != "atm_fee" or tx.get("status") != "posted":
            continue
        if not ann:
            # An ATM fee cannot be assigned a schedule from its type alone.
            result["unresolved"].append("ATM fee %s lacks supported Rho/foreign/out-of-network classification and withdrawal linkage." % tid)
            continue
        kind = ann["kind"]
        actual = money(tx["amount"])
        wid = ann.get("withdrawal_id")
        if kind == "light_domestic_oon_rho_fee":
            if wid not in domestic_expected:
                result["unresolved"].append("Domestic fee %s lacks a linked supported out-of-network withdrawal." % tid)
                continue
            add_component(result, tid, "fee_refund", actual, domestic_expected[wid],
                          "Light Green out-of-network ATM fee after four free withdrawals")
        elif kind == "light_foreign_rho_fee":
            wd = by_id.get(str(wid))
            if not wd or wd.get("type") != "atm_withdrawal" or wd.get("status") != "posted":
                result["unresolved"].append("Foreign fee %s lacks a linked posted ATM withdrawal." % tid)
                continue
            amount = money(wd["amount"])
            expected = Decimal("2.00") if amount <= Decimal("100.00") else (Decimal("3.50") if amount <= Decimal("300.00") else Decimal("5.00"))
            add_component(result, tid, "fee_refund", actual, expected,
                          "Light Green foreign ATM fee tier")
        elif kind not in ("out_of_network_withdrawal", "foreign_withdrawal"):
            result["unresolved"].append("Fee %s has an incompatible Light Green annotation." % tid)


def audit_bluest(result, txs, anns):
    eligible_third_party = Decimal("0.00")
    posted_rebates = Decimal("0.00")
    for tx in txs:
        tid = str(tx["transaction_id"])
        ann = anns.get(tid)
        if tx.get("status") != "posted" or not ann:
            continue
        kind = ann["kind"]
        if kind == "bluest_foreign_rho_fee":
            add_component(result, tid, "fee_refund", money(tx["amount"]), Decimal("0.00"),
                          "Bluest has no Rho foreign ATM withdrawal fee")
        elif kind == "bluest_out_of_network_rho_fee":
            add_component(result, tid, "fee_refund", money(tx["amount"]), Decimal("2.00"),
                          "Bluest Rho out-of-network ATM fee")
        elif kind == "bluest_third_party_atm_fee":
            eligible_third_party += money(tx["amount"])
        elif kind == "bluest_atm_rebate":
            # A rebate is a credit; require a positive signed amount rather than abs() here.
            try:
                posted_rebates += max(signed_money(tx["amount"]), Decimal("0.00"))
            except ValueError:
                result["unresolved"].append("ATM rebate %s has an invalid amount." % tid)

    # Unannotated posted ATM fees could change fee ownership or the $50 eligible-fee total.
    for tx in txs:
        tid = str(tx["transaction_id"])
        if tx.get("status") == "posted" and tx.get("type") == "atm_fee" and tid not in anns:
            result["unresolved"].append("ATM fee %s lacks supported Bluest fee classification." % tid)
    expected_rebate = min(eligible_third_party, Decimal("50.00"))
    if expected_rebate > posted_rebates:
        result["components"].append({
            "transaction_id": None, "correction_type": "rebate_credit",
            "actual": fmt(posted_rebates), "expected": fmt(expected_rebate),
            "amount": fmt(expected_rebate - posted_rebates),
            "reason": "Bluest eligible third-party ATM fee rebate, capped at $50 monthly",
        })


def finalize(result):
    total = sum((Decimal(c["amount"]) for c in result["components"]), Decimal("0.00"))
    result["credit_amount"] = fmt(total)
    if result["unresolved"]:
        result["status"] = "manual_review"
        return
    if total == 0:
        result["status"] = "no_correction"
        return
    counts = Counter(c["correction_type"] for c in result["components"])
    if len(counts) > 1 and len(set(counts.values())) == 1:
        result["status"] = "manual_review"
        result["unresolved"].append("Correction types are tied; policy provides no credit-type tie breaker.")
        return
    result["credit_type"] = counts.most_common(1)[0][0]
    result["status"] = "credit_recommended"
    result["ready_for_credit"] = True


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("top-level JSON must be an object")
        print(json.dumps(main(payload), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"errors": ["input processing failed: %s" % exc], "accounts": []}, sort_keys=True))
