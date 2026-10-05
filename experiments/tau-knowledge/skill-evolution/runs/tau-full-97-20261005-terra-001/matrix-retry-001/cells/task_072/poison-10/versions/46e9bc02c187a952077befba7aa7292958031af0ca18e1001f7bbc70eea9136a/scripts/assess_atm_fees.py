#!/usr/bin/env python3
"""Conservative deterministic assessment of normalized ATM fee histories.

Read one JSON object from stdin and emit one JSON object to stdout.  This
program does not infer facts from free-text descriptions and never calls a
banking tool.
"""
import json
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")
SUPPORTED_PRODUCTS = {"bluest account", "light green account"}
FEE_KINDS = {
    "third_party_atm_fee",
    "bluest_out_of_network_bank_fee",
    "light_green_out_of_network_bank_fee",
    "foreign_atm_bank_fee",
    "operator_surcharge",
}


def decimal(value):
    try:
        return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("invalid decimal amount")


def text_money(value):
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def transaction_date(value):
    if not isinstance(value, str):
        raise ValueError("transaction date must be MM/DD/YYYY")
    try:
        return datetime.strptime(value, "%m/%d/%Y").date()
    except ValueError:
        raise ValueError("transaction date must be MM/DD/YYYY")


def review_period(value):
    if not isinstance(value, str):
        raise ValueError("review_month must be YYYY-MM")
    try:
        parsed = datetime.strptime(value, "%Y-%m")
    except ValueError:
        raise ValueError("review_month must be YYYY-MM")
    return parsed.year, parsed.month


def as_of_date(value):
    if not isinstance(value, str):
        raise ValueError("as_of_date must be YYYY-MM-DD")
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError("as_of_date must be YYYY-MM-DD")


def is_in_month(tx, year, month):
    d = transaction_date(tx["date"])
    return d.year == year and d.month == month


def no_plan(reason):
    return {"permitted": False, "reason": reason, "amount": "0.00", "credit_type": None}


def assess(account, links, year, month, today, interaction_credit):
    result = {
        "account_id": account.get("account_id"),
        "account_class": account.get("account_class"),
        "account_type": account.get("account_type"),
        "status": account.get("status"),
        "balance": None,
        "unlinked_posted_atm_fee_ids": [],
        "pending_atm_fee_ids": [],
        "warnings": [],
        "bluest_qualifying_fee_total": "0.00",
        "posted_bluest_rebate_total": "0.00",
        "missing_bluest_rebate": "0.00",
        "fee_refund_total": "0.00",
        "fee_refund_correction_count": 0,
        "cooldown_credit_transaction_ids": [],
        "credit_plan": None,
    }
    try:
        result["balance"] = text_money(decimal(account.get("balance")))
    except ValueError:
        result["warnings"].append("Account balance is missing or invalid.")

    product = str(account.get("account_class", "")).strip().lower()
    account_type = str(account.get("account_type", "")).strip().lower()
    status = str(account.get("status", "")).strip().lower()
    if product not in SUPPORTED_PRODUCTS:
        result["credit_plan"] = no_plan("Account class is not a supported ATM-review product.")
        return result
    if account_type != "checking" or status != "open":
        result["credit_plan"] = no_plan("Credits require an OPEN checking account.")
        return result

    supplied = account.get("transactions")
    if not isinstance(supplied, list):
        result["credit_plan"] = no_plan("Transactions are missing or invalid.")
        return result

    tx_by_id = {}
    review_txs = []
    invalid_transaction = False
    for raw in supplied:
        if not isinstance(raw, dict) or not raw.get("transaction_id"):
            invalid_transaction = True
            result["warnings"].append("A transaction lacks a usable transaction_id.")
            continue
        tx_id = raw["transaction_id"]
        if tx_id in tx_by_id:
            invalid_transaction = True
            result["warnings"].append("Duplicate transaction_id: " + str(tx_id))
            continue
        try:
            copied = dict(raw)
            copied["_amount"] = decimal(copied.get("amount"))
            transaction_date(copied.get("date"))
        except ValueError:
            invalid_transaction = True
            result["warnings"].append("Invalid date or amount for transaction " + str(tx_id))
            continue
        tx_by_id[tx_id] = copied
        if is_in_month(copied, year, month):
            review_txs.append(copied)

    posted_fees = {
        tx["transaction_id"] for tx in review_txs
        if tx.get("type") == "atm_fee" and tx.get("status") == "posted"
    }
    result["pending_atm_fee_ids"] = sorted(
        tx["transaction_id"] for tx in review_txs
        if tx.get("type") == "atm_fee" and tx.get("status") == "pending"
    )

    valid_links = []
    linked_fees = set()
    seen_fee_links = set()
    seen_light_green_orders = set()
    for link in links:
        if not isinstance(link, dict):
            result["warnings"].append("Ignoring a non-object fee link.")
            continue
        fee_id = link.get("fee_transaction_id")
        withdrawal_id = link.get("withdrawal_transaction_id")
        kind = link.get("fee_kind")
        if fee_id in seen_fee_links:
            result["warnings"].append("Multiple links supplied for fee " + str(fee_id))
            continue
        seen_fee_links.add(fee_id)
        fee = tx_by_id.get(fee_id)
        withdrawal = tx_by_id.get(withdrawal_id)
        if fee is None or withdrawal is None:
            result["warnings"].append("Fee link references an unknown transaction.")
            continue
        if fee.get("type") != "atm_fee" or withdrawal.get("type") != "atm_withdrawal":
            result["warnings"].append("Fee link must pair an atm_fee with an atm_withdrawal.")
            continue
        if kind not in FEE_KINDS:
            result["warnings"].append("Fee link has an unsupported fee_kind.")
            continue
        if not is_in_month(fee, year, month):
            result["warnings"].append("A linked fee is outside the review month.")
            continue
        if fee.get("status") != "posted":
            # A pending fee is reviewed but deliberately excluded from a correction.
            linked_fees.add(fee_id)
            continue
        if withdrawal.get("status") != "posted":
            result["warnings"].append("Posted fee is linked to a non-posted withdrawal: " + str(fee_id))
            continue
        if fee["_amount"] >= 0:
            result["warnings"].append("ATM fee must be a negative debit: " + str(fee_id))
            continue
        if product == "light green account" and kind == "light_green_out_of_network_bank_fee":
            order = link.get("withdrawal_order")
            if not isinstance(order, int) or isinstance(order, bool) or order < 1:
                result["warnings"].append("Light Green domestic fee needs a positive withdrawal_order: " + str(fee_id))
                continue
            if order in seen_light_green_orders:
                result["warnings"].append("Duplicate Light Green qualifying withdrawal_order: " + str(order))
                continue
            seen_light_green_orders.add(order)
        linked_fees.add(fee_id)
        valid_links.append((link, fee, withdrawal))

    result["unlinked_posted_atm_fee_ids"] = sorted(posted_fees - linked_fees)

    cooldown_ids = []
    for tx in tx_by_id.values():
        if tx.get("status") != "posted" or tx.get("type") not in {"rebate_credit", "fee_refund"}:
            continue
        if tx["_amount"] <= 0:
            continue
        age = (today - transaction_date(tx["date"])).days
        if 0 <= age < 14:
            cooldown_ids.append(tx["transaction_id"])
    result["cooldown_credit_transaction_ids"] = sorted(cooldown_ids)

    qualifying_bluest_fees = Decimal("0.00")
    refund_total = Decimal("0.00")
    refund_count = 0
    for link, fee, _withdrawal in valid_links:
        charged = -fee["_amount"]
        kind = link["fee_kind"]
        if product == "bluest account" and kind == "third_party_atm_fee":
            qualifying_bluest_fees += charged
        if product == "light green account" and kind == "light_green_out_of_network_bank_fee":
            expected = Decimal("0.00") if link["withdrawal_order"] <= 4 else Decimal("1.50")
            discrepancy = charged - expected
            if discrepancy > 0:
                refund_total += discrepancy
                refund_count += 1
        elif link.get("confirmed_fee_refund_amount") is not None:
            try:
                discrepancy = decimal(link["confirmed_fee_refund_amount"])
            except ValueError:
                result["warnings"].append("Invalid confirmed_fee_refund_amount for " + str(fee["transaction_id"]))
                continue
            if discrepancy <= 0 or discrepancy > charged:
                result["warnings"].append("Confirmed refund is not positive or exceeds the fee: " + str(fee["transaction_id"]))
            else:
                refund_total += discrepancy
                refund_count += 1

    posted_rebates = sum(
        (tx["_amount"] for tx in review_txs
         if tx.get("status") == "posted"
         and tx.get("type") in {"fee_rebate", "rebate_credit"}
         and tx["_amount"] > 0),
        Decimal("0.00"),
    )
    missing_rebate = Decimal("0.00")
    if product == "bluest account":
        entitlement = min(qualifying_bluest_fees, Decimal("50.00"))
        missing_rebate = max(Decimal("0.00"), entitlement - posted_rebates)

    result["bluest_qualifying_fee_total"] = text_money(qualifying_bluest_fees)
    result["posted_bluest_rebate_total"] = text_money(posted_rebates if product == "bluest account" else Decimal("0.00"))
    result["missing_bluest_rebate"] = text_money(missing_rebate)
    result["fee_refund_total"] = text_money(refund_total)
    result["fee_refund_correction_count"] = refund_count

    total = missing_rebate + refund_total
    if invalid_transaction or result["warnings"] or result["unlinked_posted_atm_fee_ids"]:
        result["credit_plan"] = no_plan("Review is incomplete: resolve warnings and every posted ATM-fee line before crediting.")
    elif interaction_credit:
        result["credit_plan"] = no_plan("A credit was already applied to this account in this interaction.")
    elif cooldown_ids:
        result["credit_plan"] = no_plan("Visible history shows a rebate_credit or fee_refund within the 14-day cooldown.")
    elif total <= 0:
        result["credit_plan"] = no_plan("No supported positive correction is due from the supplied posted activity.")
    else:
        rebate_count = 1 if missing_rebate > 0 else 0
        if rebate_count > refund_count:
            credit_type = "rebate_credit"
        elif refund_count > rebate_count:
            credit_type = "fee_refund"
        else:
            credit_type = None
        if credit_type is None:
            result["credit_plan"] = no_plan("Rebate and fee-refund corrections are tied; resolve credit type before crediting.")
        else:
            result["credit_plan"] = {
                "permitted": True,
                "reason": "Complete supplied review supports one consolidated checking-account credit.",
                "amount": text_money(total),
                "credit_type": credit_type,
            }
    return result


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    year, month = review_period(payload.get("review_month"))
    today = as_of_date(payload.get("as_of_date"))
    accounts = payload.get("accounts")
    links = payload.get("fee_links", [])
    interaction_credit = payload.get("credit_already_applied_this_interaction", False)
    if not isinstance(accounts, list):
        raise ValueError("accounts must be an array")
    if not isinstance(links, list):
        raise ValueError("fee_links must be an array")
    if not isinstance(interaction_credit, bool):
        raise ValueError("credit_already_applied_this_interaction must be boolean")

    links_by_account = {}
    for link in links:
        if isinstance(link, dict):
            links_by_account.setdefault(link.get("account_id"), []).append(link)
    assessments = []
    for account in accounts:
        if not isinstance(account, dict):
            assessments.append({
                "account_id": None,
                "warnings": ["Invalid account entry."],
                "credit_plan": no_plan("Account entry is not an object."),
            })
            continue
        assessments.append(assess(
            account,
            links_by_account.get(account.get("account_id"), []),
            year,
            month,
            today,
            interaction_credit,
        ))
    return {
        "ok": True,
        "review_month": "%04d-%02d" % (year, month),
        "as_of_date": today.isoformat(),
        "accounts": assessments,
        "notice": "This is a calculation recommendation only. Identity, authority, ownership, and banking-tool prerequisites must be verified separately.",
    }


if __name__ == "__main__":
    try:
        output = main(json.load(sys.stdin))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        output = {"ok": False, "error": str(exc)}
    json.dump(output, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")
