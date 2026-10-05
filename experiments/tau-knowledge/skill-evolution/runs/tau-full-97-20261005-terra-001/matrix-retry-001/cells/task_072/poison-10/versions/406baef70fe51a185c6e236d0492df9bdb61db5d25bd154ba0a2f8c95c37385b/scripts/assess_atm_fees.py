#!/usr/bin/env python3
"""Assess normalized ATM fee records without making banking-tool calls.

Input and output are JSON objects on stdin/stdout. Fee classifications and
fee/withdrawal links are supplied by the executor from retrieved evidence; this
program deliberately does not infer them from arbitrary free text.
"""
import json
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")
KINDS = {
    "third_party_atm_fee", "bluest_out_of_network_bank_fee",
    "light_green_out_of_network_bank_fee", "foreign_atm_bank_fee",
    "operator_surcharge",
}


def money(value):
    try:
        return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("invalid decimal amount")


def fmt(value):
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def parse_date(value, field="date"):
    if not isinstance(value, str):
        raise ValueError(field + " must be a string")
    try:
        return datetime.strptime(value, "%m/%d/%Y").date()
    except ValueError:
        raise ValueError(field + " must be MM/DD/YYYY")


def parse_period(value):
    if not isinstance(value, str):
        raise ValueError("review_month must be YYYY-MM")
    try:
        return datetime.strptime(value, "%Y-%m")
    except ValueError:
        raise ValueError("review_month must be YYYY-MM")


def no_plan(reason):
    return {"permitted": False, "reason": reason, "amount": "0.00", "credit_type": None}


def foreign_light_green_fee(withdrawal_amount):
    amount = abs(withdrawal_amount)
    if amount <= Decimal("100.00"):
        return Decimal("2.00")
    if amount <= Decimal("300.00"):
        return Decimal("3.50")
    return Decimal("5.00")


def account_assessment(account, account_links, period, cutoff, interaction_credit):
    result = {
        "account_id": account.get("account_id"),
        "account_class": account.get("account_class"),
        "unlinked_posted_atm_fee_ids": [],
        "pending_atm_fee_ids": [],
        "cooldown_credit_transaction_ids": [],
        "warnings": [],
        "bluest_qualifying_fee_total": "0.00",
        "posted_bluest_rebate_total": "0.00",
        "missing_bluest_rebate": "0.00",
        "fee_refund_total": "0.00",
        "fee_refund_correction_count": 0,
        "credit_plan": None,
    }
    product = str(account.get("account_class", "")).strip().lower()
    is_bluest = product == "bluest account"
    is_light_green = product == "light green account"
    if not (is_bluest or is_light_green):
        result["credit_plan"] = no_plan("Unsupported account class.")
        return result
    if str(account.get("account_type", "")).lower() != "checking" or str(account.get("status", "")).lower() != "open":
        result["credit_plan"] = no_plan("Credits require an OPEN checking account.")
        return result
    records = account.get("transactions")
    if not isinstance(records, list):
        result["credit_plan"] = no_plan("Transactions are missing or invalid.")
        return result

    transactions = {}
    invalid = False
    for raw in records:
        if not isinstance(raw, dict) or not raw.get("transaction_id"):
            invalid = True
            result["warnings"].append("A transaction lacks a transaction_id.")
            continue
        txid = raw["transaction_id"]
        if txid in transactions:
            invalid = True
            result["warnings"].append("Duplicate transaction_id: " + str(txid))
            continue
        try:
            tx = dict(raw)
            tx["_date"] = parse_date(tx.get("date"))
            tx["_amount"] = money(tx.get("amount"))
        except ValueError:
            invalid = True
            result["warnings"].append("Invalid date or amount: " + str(txid))
            continue
        transactions[txid] = tx

    scoped = [t for t in transactions.values() if (t["_date"].year, t["_date"].month) == (period.year, period.month) and t["_date"] <= cutoff]
    posted_fees = {t["transaction_id"] for t in scoped if t.get("type") == "atm_fee" and t.get("status") == "posted"}
    result["pending_atm_fee_ids"] = sorted(t["transaction_id"] for t in scoped if t.get("type") == "atm_fee" and t.get("status") == "pending")

    linked = set()
    valid = []
    orders = set()
    for link in account_links:
        if not isinstance(link, dict):
            result["warnings"].append("Non-object fee link.")
            continue
        feeid = link.get("fee_transaction_id")
        withdrawalid = link.get("withdrawal_transaction_id")
        if feeid in linked:
            result["warnings"].append("Multiple links for fee " + str(feeid))
            continue
        fee, withdrawal = transactions.get(feeid), transactions.get(withdrawalid)
        kind = link.get("fee_kind")
        if not fee or not withdrawal or kind not in KINDS:
            result["warnings"].append("Invalid or unknown fee link.")
            continue
        if fee.get("type") != "atm_fee" or withdrawal.get("type") != "atm_withdrawal":
            result["warnings"].append("A fee link must pair atm_fee and atm_withdrawal.")
            continue
        if fee not in scoped:
            result["warnings"].append("Linked fee is outside the reviewed cutoff.")
            continue
        linked.add(feeid)
        if fee.get("status") != "posted":
            continue
        if withdrawal.get("status") != "posted" or fee["_amount"] >= 0:
            result["warnings"].append("Posted fee has invalid withdrawal/status/amount evidence: " + str(feeid))
            continue
        order = link.get("withdrawal_order")
        if is_light_green and kind == "light_green_out_of_network_bank_fee":
            if not isinstance(order, int) or isinstance(order, bool) or order < 1 or order in orders:
                result["warnings"].append("Light Green domestic fee requires a unique positive withdrawal_order.")
                continue
            orders.add(order)
        valid.append((fee, withdrawal, kind, order))

    result["unlinked_posted_atm_fee_ids"] = sorted(posted_fees - linked)
    qualifying = Decimal("0.00")
    refunds = Decimal("0.00")
    refund_count = 0
    for fee, withdrawal, kind, order in valid:
        charged = -fee["_amount"]
        expected = None
        if is_bluest and kind == "third_party_atm_fee":
            qualifying += charged
        elif is_bluest and kind == "foreign_atm_bank_fee":
            expected = Decimal("0.00")
        elif is_light_green and kind == "light_green_out_of_network_bank_fee":
            expected = Decimal("0.00") if order <= 4 else Decimal("1.50")
        elif is_light_green and kind == "foreign_atm_bank_fee":
            expected = foreign_light_green_fee(withdrawal["_amount"])
        if expected is not None and charged > expected:
            refunds += charged - expected
            refund_count += 1

    rebates = sum((t["_amount"] for t in scoped if t.get("status") == "posted" and t.get("type") in {"fee_rebate", "rebate_credit"} and t["_amount"] > 0), Decimal("0.00"))
    missing_rebate = max(Decimal("0.00"), min(qualifying, Decimal("50.00")) - rebates) if is_bluest else Decimal("0.00")
    result["bluest_qualifying_fee_total"] = fmt(qualifying)
    result["posted_bluest_rebate_total"] = fmt(rebates if is_bluest else Decimal("0.00"))
    result["missing_bluest_rebate"] = fmt(missing_rebate)
    result["fee_refund_total"] = fmt(refunds)
    result["fee_refund_correction_count"] = refund_count

    cooldown = []
    for tx in transactions.values():
        if tx.get("status") == "posted" and tx.get("type") in {"rebate_credit", "fee_refund"} and tx["_amount"] > 0:
            age = (cutoff - tx["_date"]).days
            if 0 <= age < 14:
                cooldown.append(tx["transaction_id"])
    result["cooldown_credit_transaction_ids"] = sorted(cooldown)

    total = refunds + missing_rebate
    if invalid or result["warnings"] or result["unlinked_posted_atm_fee_ids"]:
        result["credit_plan"] = no_plan("Review is incomplete: resolve warnings and every posted ATM-fee line.")
    elif interaction_credit:
        result["credit_plan"] = no_plan("A credit was already applied to this account in this interaction.")
    elif cooldown:
        result["credit_plan"] = no_plan("Visible history shows a credit within the 14-day cooldown.")
    elif total <= 0:
        result["credit_plan"] = no_plan("No supported positive correction is due from supplied posted activity.")
    else:
        rebate_count = 1 if missing_rebate > 0 else 0
        if refund_count == rebate_count:
            result["credit_plan"] = no_plan("Correction categories are tied; resolve credit type before crediting.")
        else:
            result["credit_plan"] = {
                "permitted": True,
                "reason": "Complete supplied review supports one consolidated checking-account credit.",
                "amount": fmt(total),
                "credit_type": "fee_refund" if refund_count > rebate_count else "rebate_credit",
            }
    return result


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    period = parse_period(payload.get("review_month"))
    cutoff = parse_date(payload.get("as_of_date"), "as_of_date") if isinstance(payload.get("as_of_date"), str) else None
    if cutoff is None:
        raise ValueError("as_of_date must be YYYY-MM-DD")
    # as_of_date has ISO rather than transaction date format.


def iso_date(value):
    if not isinstance(value, str):
        raise ValueError("as_of_date must be YYYY-MM-DD")
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError("as_of_date must be YYYY-MM-DD")


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        period = parse_period(payload.get("review_month"))
        cutoff = iso_date(payload.get("as_of_date"))
        accounts = payload.get("accounts")
        links = payload.get("fee_links", [])
        interaction_credit = payload.get("credit_already_applied_this_interaction", False)
        if not isinstance(accounts, list) or not isinstance(links, list):
            raise ValueError("accounts and fee_links must be arrays")
        if not isinstance(interaction_credit, bool):
            raise ValueError("credit_already_applied_this_interaction must be boolean")
        by_account = {}
        for link in links:
            if isinstance(link, dict):
                by_account.setdefault(link.get("account_id"), []).append(link)
        output = {"ok": True, "review_month": period.strftime("%Y-%m"), "as_of_date": cutoff.isoformat(), "accounts": []}
        for account in accounts:
            if not isinstance(account, dict):
                output["accounts"].append({"account_id": None, "warnings": ["Invalid account entry."], "credit_plan": no_plan("Account entry is not an object.")})
            else:
                output["accounts"].append(account_assessment(account, by_account.get(account.get("account_id"), []), period, cutoff, interaction_credit))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        output = {"ok": False, "error": str(exc)}
    json.dump(output, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")
