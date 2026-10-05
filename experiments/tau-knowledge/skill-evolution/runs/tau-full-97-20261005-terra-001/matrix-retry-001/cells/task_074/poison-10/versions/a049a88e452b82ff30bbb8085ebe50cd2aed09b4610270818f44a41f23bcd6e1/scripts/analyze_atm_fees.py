#!/usr/bin/env python3
"""Deterministically analyze annotated posted ATM fee records.

Reads the JSON schema documented in SKILL.md from stdin and emits JSON to stdout.
This script never calls banking tools and never authorizes a credit.
"""
import json
import sys
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

ZERO = Decimal("0")
CENT = Decimal("0.01")


def money(value):
    try:
        return Decimal(str(value)).copy_abs().quantize(CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("invalid monetary amount: %r" % (value,))


def text(value):
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def date_of(tx):
    return datetime.strptime(str(tx.get("date")), "%m/%d/%Y").date()


def month_of(tx):
    return date_of(tx).strftime("%Y-%m")


def product_for(account):
    fields = ("account_class", "account_name", "name", "product")
    source = " ".join(str(account.get(field, "")) for field in fields).lower()
    for phrase, product in (
        ("light blue", "light_blue"),
        ("dark green", "dark_green"),
        ("evergreen", "evergreen"),
        ("purple", "purple"),
    ):
        if phrase in source:
            return product
    return None


def expected_rho_fee(product, location, amount, allowance_ordinal=None):
    """Return the fee permitted for one out-of-network withdrawal."""
    if product == "purple":
        return Decimal("2.50") if location == "domestic" else ZERO
    if product == "light_blue":
        if allowance_ordinal is None:
            raise ValueError("Light Blue allowance ordinal is required")
        if allowance_ordinal <= 2:
            return ZERO
        return Decimal("2.50") if location == "domestic" else Decimal("4.00")
    if product == "dark_green":
        if location == "domestic":
            return max((amount * Decimal(".01")).quantize(CENT), Decimal("1.50"))
        return min((amount * Decimal(".025")).quantize(CENT), Decimal("6.00"))
    if product == "evergreen":
        if location == "domestic":
            return min((amount * Decimal(".01")).quantize(CENT), Decimal("2.50"))
        return max((amount * Decimal(".02")).quantize(CENT), Decimal("3.00"))
    raise ValueError("unsupported account product")


def add_once(items, value):
    if value not in items:
        items.append(value)


def failure(errors):
    return {
        "ok": False,
        "errors": errors,
        "findings": [],
        "corrections": [],
        "manual_review": [],
        "credit_candidate": None,
    }


def analyze(payload):
    errors, manual = [], []
    account = payload.get("account")
    transactions = payload.get("transactions")
    annotations = payload.get("annotations", {})
    review_month = payload.get("review_month")

    if not isinstance(account, dict):
        errors.append("account must be an object")
    if not isinstance(transactions, list):
        errors.append("transactions must be an array")
    if not isinstance(annotations, dict):
        errors.append("annotations must be an object")
    try:
        datetime.strptime(str(review_month), "%Y-%m")
    except (TypeError, ValueError):
        errors.append("review_month must use YYYY-MM")
    if errors:
        return failure(errors)

    product = product_for(account)
    if not account.get("account_id"):
        errors.append("account.account_id is required")
    if product is None:
        errors.append("account product must identify Purple, Light Blue, Dark Green, or Evergreen")
    if errors:
        return failure(errors)
    if not payload.get("full_transaction_history"):
        add_once(manual, "Complete transaction history was not supplied; monthly allowances and rebate caps cannot be validated.")

    by_id = {}
    for tx in transactions:
        if not isinstance(tx, dict) or not tx.get("transaction_id"):
            errors.append("every transaction must have transaction_id")
            continue
        tid = str(tx["transaction_id"])
        if tid in by_id:
            errors.append("duplicate transaction_id: " + tid)
            continue
        try:
            date_of(tx)
            money(tx.get("amount"))
        except ValueError as exc:
            errors.append("transaction %s: %s" % (tid, exc))
            continue
        by_id[tid] = tx
    if errors:
        return failure(errors)

    withdrawals = [
        tx for tx in by_id.values()
        if tx.get("status") == "posted" and tx.get("type") == "atm_withdrawal"
        and month_of(tx) == review_month
    ]
    withdrawals.sort(key=lambda tx: (date_of(tx), str(tx["transaction_id"])))
    withdrawal_ids = {str(tx["transaction_id"]) for tx in withdrawals}

    expected = {}
    allowance_count = defaultdict(int)
    for withdrawal in withdrawals:
        wid = str(withdrawal["transaction_id"])
        note = annotations.get(wid, {})
        location, network = note.get("location"), note.get("network")
        if location not in ("domestic", "foreign"):
            add_once(manual, "Withdrawal %s lacks a verified domestic/foreign classification." % wid)
            continue
        if network not in ("in_network", "out_of_network"):
            add_once(manual, "Withdrawal %s lacks a verified network classification." % wid)
            continue
        if network == "in_network":
            expected[wid] = ZERO
        elif product == "light_blue":
            # Only eligible out-of-network withdrawals consume this allowance.
            allowance_count[location] += 1
            expected[wid] = expected_rho_fee(
                product, location, money(withdrawal["amount"]), allowance_count[location]
            )
        else:
            expected[wid] = expected_rho_fee(product, location, money(withdrawal["amount"]))

    rho_fees = defaultdict(list)
    operator_fees = defaultdict(list)
    target_fee_ids = set()
    for tx in by_id.values():
        if tx.get("status") != "posted" or tx.get("type") != "atm_fee" or month_of(tx) != review_month:
            continue
        fid = str(tx["transaction_id"])
        target_fee_ids.add(fid)
        note = annotations.get(fid, {})
        origin = note.get("fee_origin")
        related = str(note.get("related_withdrawal_id", ""))
        if origin not in ("rho_bank", "operator") or not related:
            add_once(manual, "ATM fee %s lacks a verified origin and related withdrawal." % fid)
            continue
        if related not in withdrawal_ids:
            add_once(manual, "ATM fee %s is not linked to a posted target-month withdrawal." % fid)
            continue
        (rho_fees if origin == "rho_bank" else operator_fees)[related].append(tx)

    findings, corrections = [], []
    for withdrawal in withdrawals:
        wid = str(withdrawal["transaction_id"])
        if wid not in expected:
            continue
        linked = rho_fees.get(wid, [])
        charged = sum((money(fee["amount"]) for fee in linked), ZERO)
        permitted = expected[wid]
        difference = charged - permitted
        note = annotations[wid]
        finding = {
            "subject": "withdrawal " + wid,
            "withdrawal_id": wid,
            "location": note["location"],
            "network": note["network"],
            "rho_bank_fee_ids": [str(fee["transaction_id"]) for fee in linked],
            "expected_rho_bank_fee": text(permitted),
            "charged_rho_bank_fee": text(charged),
            "difference_charged_minus_expected": text(difference),
        }
        if difference > ZERO:
            finding["outcome"] = "overcharge"
            corrections.append({"credit_type": "fee_refund", "amount": difference, "basis": finding["subject"]})
        elif difference < ZERO:
            finding["outcome"] = "undercharge_or_unposted_fee"
        else:
            finding["outcome"] = "matches_schedule"
        findings.append(finding)

    if product == "purple":
        rebates_by_fee = defaultdict(list)
        for tx in by_id.values():
            if tx.get("status") != "posted" or month_of(tx) != review_month:
                continue
            if tx.get("type") not in ("fee_rebate", "rebate_credit"):
                continue
            rid = str(tx["transaction_id"])
            note = annotations.get(rid, {})
            related_fee = str(note.get("related_fee_id", ""))
            if note.get("rebate_source") != "atm_operator_rebate" or not related_fee:
                add_once(manual, "Potential Purple rebate %s lacks verified ATM-operator-fee linkage." % rid)
                continue
            if related_fee not in target_fee_ids:
                add_once(manual, "Purple rebate %s references a fee outside the target-month review." % rid)
                continue
            rebates_by_fee[related_fee].append(tx)

        operator_lines = [fee for wid in withdrawal_ids for fee in operator_fees.get(wid, [])]
        eligible_total = sum((money(fee["amount"]) for fee in operator_lines), ZERO)
        expected_rebate = min(eligible_total, Decimal("30.00"))
        posted_rebate = sum(
            (money(rebate["amount"])
             for fee in operator_lines
             for rebate in rebates_by_fee.get(str(fee["transaction_id"]), [])),
            ZERO,
        )
        rebate_difference = expected_rebate - posted_rebate
        rebate_finding = {
            "subject": "Purple eligible ATM operator-fee rebates",
            "operator_fee_ids": [str(fee["transaction_id"]) for fee in operator_lines],
            "eligible_operator_fees": text(eligible_total),
            "monthly_cap": "30.00",
            "expected_rebate_up_to_cap": text(expected_rebate),
            "posted_linked_rebates": text(posted_rebate),
            "difference_expected_minus_posted": text(rebate_difference),
            "outcome": "possible_missing_rebate" if rebate_difference > ZERO else "cap_or_posted_rebates_accounted_for",
        }
        if posted_rebate > expected_rebate:
            add_once(manual, "Linked Purple operator-fee rebates exceed the documented monthly cap; verify postings and classifications.")
        if rebate_difference > ZERO:
            corrections.append({
                "credit_type": "rebate_credit",
                "amount": rebate_difference,
                "basis": rebate_finding["subject"],
            })
        findings.append(rebate_finding)

    candidate = None
    if not manual and corrections:
        refund_items = sum(item["credit_type"] == "fee_refund" for item in corrections)
        rebate_items = sum(item["credit_type"] == "rebate_credit" for item in corrections)
        if refund_items == rebate_items:
            add_once(manual, "Fee-refund and rebate-credit corrections are tied; no majority credit type is defined.")
        else:
            candidate = {
                "account_id": account["account_id"],
                "amount": text(sum((item["amount"] for item in corrections), ZERO)),
                "credit_type": "fee_refund" if refund_items > rebate_items else "rebate_credit",
                "basis": [item["basis"] for item in corrections],
                "requires_external_prerequisites": [
                    "completed identity and ownership verification",
                    "eligible checking-account type, status, and balance confirmation",
                    "no relevant prior correction, interaction duplicate, or applicable 14-day cooldown",
                    "checking-account credit action and resulting balance retrieval",
                ],
            }

    return {
        "ok": True,
        "errors": [],
        "account_id": account["account_id"],
        "product": product,
        "review_month": review_month,
        "findings": findings,
        "corrections": [
            {"credit_type": item["credit_type"], "amount": text(item["amount"]), "basis": item["basis"]}
            for item in corrections
        ],
        "manual_review": manual,
        "credit_candidate": candidate if not manual else None,
    }


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("top-level JSON value must be an object")
        result = analyze(payload)
    except Exception as exc:
        result = failure([str(exc)])
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
