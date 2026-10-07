#!/usr/bin/env python3
"""Deterministic ATM fee/rebate assessment for normalized account histories.

Reads one JSON object from stdin and writes one JSON object to stdout.
It deliberately requires explicit fee links and classifications; it does not
infer financial facts from transaction descriptions.
"""
import json
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")
VALID_KINDS = {
    "third_party_atm_fee",
    "bluest_out_of_network_bank_fee",
    "light_green_out_of_network_bank_fee",
    "foreign_atm_bank_fee",
    "operator_surcharge",
}


def money(value):
    try:
        result = Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("invalid decimal amount")
    return result


def money_text(value):
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def parse_tx_date(value):
    if not isinstance(value, str):
        raise ValueError("transaction date must be MM/DD/YYYY")
    try:
        return datetime.strptime(value, "%m/%d/%Y").date()
    except ValueError:
        raise ValueError("transaction date must be MM/DD/YYYY")


def parse_month(value):
    if not isinstance(value, str):
        raise ValueError("review_month must be YYYY-MM")
    try:
        parsed = datetime.strptime(value, "%Y-%m")
    except ValueError:
        raise ValueError("review_month must be YYYY-MM")
    return parsed.year, parsed.month


def parse_as_of(value):
    if not isinstance(value, str):
        raise ValueError("as_of_date must be YYYY-MM-DD")
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError("as_of_date must be YYYY-MM-DD")


def in_month(tx, year, month):
    tx_date = parse_tx_date(tx.get("date"))
    return tx_date.year == year and tx_date.month == month


def empty_plan(reason):
    return {
        "permitted": False,
        "reason": reason,
        "amount": "0.00",
        "credit_type": None,
    }


def assess_account(account, links, year, month, as_of, interaction_credit):
    account_id = account.get("account_id")
    result = {
        "account_id": account_id,
        "account_class": account.get("account_class"),
        "account_type": account.get("account_type"),
        "status": account.get("status"),
        "balance": None,
        "unlinked_posted_atm_fee_ids": [],
        "pending_atm_fee_ids": [],
        "warnings": [],
        "blueste_rebate_fee_total": "0.00",
        "already_posted_rebate_total": "0.00",
        "missing_bluest_rebate": "0.00",
        "fee_refund_total": "0.00",
        "fee_refund_correction_count": 0,
        "cooldown_credit_transaction_ids": [],
        "credit_plan": None,
    }
    try:
        result["balance"] = money_text(money(account.get("balance")))
    except ValueError:
        result["warnings"].append("Account balance is missing or invalid.")

    product = str(account.get("account_class", "")).strip().lower()
    account_type = str(account.get("account_type", "")).strip().lower()
    status = str(account.get("status", "")).strip().lower()
    if product not in ("bluest account", "light green account"):
        result["credit_plan"] = empty_plan("Account class is not a supported ATM-review product.")
        return result
    if account_type != "checking" or status != "open":
        result["credit_plan"] = empty_plan("Credits require an OPEN checking account.")
        return result

    transactions = account.get("transactions")
    if not isinstance(transactions, list):
        result["credit_plan"] = empty_plan("Transactions are missing or invalid.")
        return result

    tx_by_id = {}
    review_transactions = []
    invalid_dates = False
    for tx in transactions:
        if not isinstance(tx, dict) or not tx.get("transaction_id"):
            result["warnings"].append("A transaction lacks a usable transaction_id.")
            continue
        tx_id = tx["transaction_id"]
        if tx_id in tx_by_id:
            result["warnings"].append("Duplicate transaction_id: " + str(tx_id))
            continue
        try:
            parse_tx_date(tx.get("date"))
            amount = money(tx.get("amount"))
        except ValueError:
            invalid_dates = True
            result["warnings"].append("Invalid date or amount for transaction " + str(tx_id))
            continue
        copied = dict(tx)
        copied["_amount"] = amount
        tx_by_id[tx_id] = copied
        if in_month(copied, year, month):
            review_transactions.append(copied)

    review_fee_ids = {
        tx["transaction_id"] for tx in review_transactions
        if tx.get("type") == "atm_fee"
    }
    posted_fee_ids = {
        tx["transaction_id"] for tx in review_transactions
        if tx.get("type") == "atm_fee" and tx.get("status") == "posted"
    }
    result["pending_atm_fee_ids"] = sorted(
        tx["transaction_id"] for tx in review_transactions
        if tx.get("type") == "atm_fee" and tx.get("status") == "pending"
    )

    valid_links = []
    linked_fee_ids = set()
    seen_linked_fees = set()
    for link in links:
        if not isinstance(link, dict):
            result["warnings"].append("Ignoring a non-object fee link.")
            continue
        fee_id = link.get("fee_transaction_id")
        withdrawal_id = link.get("withdrawal_transaction_id")
        kind = link.get("fee_kind")
        if fee_id in seen_linked_fees:
            result["warnings"].append("Multiple links supplied for fee " + str(fee_id))
            continue
        seen_linked_fees.add(fee_id)
        fee_tx = tx_by_id.get(fee_id)
        withdrawal_tx = tx_by_id.get(withdrawal_id)
        if fee_tx is None or withdrawal_tx is None:
            result["warnings"].append("Fee link references an unknown transaction.")
            continue
        if fee_tx.get("type") != "atm_fee" or withdrawal_tx.get("type") != "atm_withdrawal":
            result["warnings"].append("Fee link does not pair an atm_fee with an atm_withdrawal.")
            continue
        if kind not in VALID_KINDS:
            result["warnings"].append("Fee link has an unsupported fee_kind.")
            continue
        if not in_month(fee_tx, year, month):
            result["warnings"].append("A fee link is outside the review month.")
            continue
        if fee_tx.get("status") != "posted":
            # Pending fees are intentionally not considered for a credit.
            linked_fee_ids.add(fee_id)
            continue
        if withdrawal_tx.get("status") != "posted":
            result["warnings"].append("Posted fee is linked to a non-posted withdrawal: " + str(fee_id))
            continue
        if fee_tx["_amount"] >= 0:
            result["warnings"].append("ATM fee must be a negative debit: " + str(fee_id))
            continue
        linked_fee_ids.add(fee_id)
        valid_links.append((link, fee_tx, withdrawal_tx))

    result["unlinked_posted_atm_fee_ids"] = sorted(posted_fee_ids - linked_fee_ids)

    # Visible cooldown evidence comes from the full returned history, not only the review month.
    cooldown_ids = []
    for tx in tx_by_id.values():
        if tx.get("status") != "posted" or tx.get("type") not in ("rebate_credit", "fee_refund"):
            continue
        if tx["_amount"] <= 0:
            continue
        try:
            age_days = (as_of - parse_tx_date(tx.get("date"))).days
        except ValueError:
            continue
        if 0 <= age_days < 14:
            cooldown_ids.append(tx["transaction_id"])
    result["cooldown_credit_transaction_ids"] = sorted(cooldown_ids)

    # Existing monthly rebate credits reduce the Bluest shortfall. Fee refunds do not.
    existing_rebates = sum(
        (tx["_amount"] for tx in review_transactions
         if tx.get("status") == "posted"
         and tx.get("type") in ("fee_rebate", "rebate_credit")
         and tx["_amount"] > 0),
        Decimal("0.00"),
    )

    rebate_fee_total = Decimal("0.00")
    refund_total = Decimal("0.00")
    refund_count = 0
    for link, fee_tx, _withdrawal_tx in valid_links:
        kind = link["fee_kind"]
        charged = -fee_tx["_amount"]
        if product == "bluest account" and kind == "third_party_atm_fee":
            rebate_fee_total += charged

        if product == "light green account" and kind == "light_green_out_of_network_bank_fee":
            order = link.get("withdrawal_order")
            if not isinstance(order, int) or isinstance(order, bool) or order < 1:
                result["warnings"].append(
                    "Light Green domestic fee needs a positive integer withdrawal_order: " + str(fee_tx["transaction_id"])
                )
            else:
                expected = Decimal("0.00") if order <= 4 else Decimal("1.50")
                discrepancy = charged - expected
                if discrepancy > 0:
                    refund_total += discrepancy
                    refund_count += 1

        # This optional field represents an independently documented exact error.
        # It is not used on Light Green domestic fees, which are calculated above.
        if not (product == "light green account" and kind == "light_green_out_of_network_bank_fee"):
            supplied = link.get("confirmed_fee_refund_amount")
            if supplied is not None:
                try:
                    discrepancy = money(supplied)
                except ValueError:
                    result["warnings"].append("Invalid confirmed_fee_refund_amount for " + str(fee_tx["transaction_id"]))
                    continue
                if discrepancy <= 0 or discrepancy > charged:
                    result["warnings"].append("Confirmed fee refund is not a positive amount no greater than the charge: " + str(fee_tx["transaction_id"]))
                else:
                    refund_total += discrepancy
                    refund_count += 1

    missing_rebate = Decimal("0.00")
    if product == "bluest account":
        entitled = min(rebate_fee_total, Decimal("50.00"))
        missing_rebate = max(Decimal("0.00"), entitled - existing_rebates)

    result["blueste_rebate_fee_total"] = money_text(rebate_fee_total)
    result["already_posted_rebate_total"] = money_text(existing_rebates if product == "bluest account" else Decimal("0.00"))
    result["missing_bluest_rebate"] = money_text(missing_rebate)
    result["fee_refund_total"] = money_text(refund_total)
    result["fee_refund_correction_count"] = refund_count

    total = missing_rebate + refund_total
    if invalid_dates or result["warnings"] or result["unlinked_posted_atm_fee_ids"]:
        result["credit_plan"] = empty_plan("Review is incomplete: resolve warnings and every posted ATM-fee line before crediting.")
    elif interaction_credit:
        result["credit_plan"] = empty_plan("A credit was already applied to this account during this interaction.")
    elif cooldown_ids:
        result["credit_plan"] = empty_plan("Visible account history shows a rebate_credit or fee_refund within the 14-day cooldown.")
    elif total <= 0:
        result["credit_plan"] = empty_plan("No supported positive correction is due from the supplied posted activity.")
    else:
        rebate_count = 1 if missing_rebate > 0 else 0
        if rebate_count > refund_count:
            credit_type = "rebate_credit"
        elif refund_count > rebate_count:
            credit_type = "fee_refund"
        else:
            credit_type = None
        if credit_type is None:
            result["credit_plan"] = empty_plan("Rebate and fee-refund corrections are tied; credit type requires approved resolution.")
        else:
            result["credit_plan"] = {
                "permitted": True,
                "reason": "Complete supplied review supports one consolidated checking-account credit.",
                "amount": money_text(total),
                "credit_type": credit_type,
            }
    return result


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    year, month = parse_month(payload.get("review_month"))
    as_of = parse_as_of(payload.get("as_of_date"))
    accounts = payload.get("accounts")
    links = payload.get("fee_links", [])
    interaction_credit = payload.get("credit_already_applied_this_interaction", False)
    if not isinstance(accounts, list):
        raise ValueError("accounts must be an array")
    if not isinstance(links, list):
        raise ValueError("fee_links must be an array")
    if not isinstance(interaction_credit, bool):
        raise ValueError("credit_already_applied_this_interaction must be boolean")

    by_account = {}
    for link in links:
        if isinstance(link, dict):
            by_account.setdefault(link.get("account_id"), []).append(link)
    assessments = [
        assess_account(account, by_account.get(account.get("account_id"), []), year, month, as_of, interaction_credit)
        if isinstance(account, dict)
        else {"account_id": None, "credit_plan": empty_plan("Account entry is not an object."), "warnings": ["Invalid account entry."]}
        for account in accounts
    ]
    return {
        "ok": True,
        "review_month": "%04d-%02d" % (year, month),
        "as_of_date": as_of.isoformat(),
        "accounts": assessments,
        "notice": "Analyzer output is a recommendation only; identity, authority, ownership, and tool prerequisites must be verified separately.",
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        output = main(payload)
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        output = {"ok": False, "error": str(exc)}
    json.dump(output, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")
