#!/usr/bin/env python3
"""Analyze posted ATM fee records using explicit transaction annotations.

The program reads the JSON schema in SKILL.md from stdin and emits a single JSON
object. It makes no banking-tool calls and never authorizes a credit.
"""
import json
import sys
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

ZERO = Decimal("0")
CENT = Decimal("0.01")


def parse_date(value):
    return datetime.strptime(str(value), "%m/%d/%Y").date()


def parse_money(value):
    try:
        return Decimal(str(value)).copy_abs().quantize(CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("invalid monetary amount: %r" % (value,))


def fmt(value):
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def tx_month(tx):
    return parse_date(tx.get("date")).strftime("%Y-%m")


def product_for(account):
    keys = ("account_class", "account_name", "name", "product")
    text = " ".join(str(account.get(key, "")) for key in keys).lower()
    for label, product in (
        ("light blue", "light_blue"),
        ("dark green", "dark_green"),
        ("evergreen", "evergreen"),
        ("purple", "purple"),
    ):
        if label in text:
            return product
    return None


def expected_fee(product, location, withdrawal_amount, ordinal=None):
    if product == "purple":
        return Decimal("2.50") if location == "domestic" else ZERO
    if product == "light_blue":
        if ordinal is None:
            raise ValueError("Light Blue allowance ordinal is required")
        if ordinal <= 2:
            return ZERO
        return Decimal("2.50") if location == "domestic" else Decimal("4.00")
    if product == "dark_green":
        if location == "domestic":
            return max((withdrawal_amount * Decimal("0.01")).quantize(CENT, rounding=ROUND_HALF_UP), Decimal("1.50"))
        return min((withdrawal_amount * Decimal("0.025")).quantize(CENT, rounding=ROUND_HALF_UP), Decimal("6.00"))
    if product == "evergreen":
        if location == "domestic":
            return min((withdrawal_amount * Decimal("0.01")).quantize(CENT, rounding=ROUND_HALF_UP), Decimal("2.50"))
        return max((withdrawal_amount * Decimal("0.02")).quantize(CENT, rounding=ROUND_HALF_UP), Decimal("3.00"))
    raise ValueError("unsupported account product")


def add_unique(messages, message):
    if message not in messages:
        messages.append(message)


def empty_result(errors):
    return {
        "ok": False,
        "errors": errors,
        "findings": [],
        "corrections": [],
        "manual_review": [],
        "credit_candidate": None,
    }


def analyze(payload):
    errors = []
    manual = []
    account = payload.get("account")
    transactions = payload.get("transactions")
    annotations = payload.get("annotations", {})
    month = payload.get("review_month")

    if not isinstance(account, dict):
        errors.append("account must be an object")
    if not isinstance(transactions, list):
        errors.append("transactions must be an array")
    if not isinstance(annotations, dict):
        errors.append("annotations must be an object")
    try:
        datetime.strptime(str(month), "%Y-%m")
    except (TypeError, ValueError):
        errors.append("review_month must use YYYY-MM")
    if errors:
        return empty_result(errors)

    product = product_for(account)
    if not account.get("account_id"):
        errors.append("account.account_id is required")
    if product is None:
        errors.append("account product must identify Purple, Light Blue, Dark Green, or Evergreen")
    if errors:
        return empty_result(errors)
    if not payload.get("full_transaction_history"):
        add_unique(manual, "Complete transaction history was not supplied; monthly allowances and rebate caps cannot be validated.")

    indexed = {}
    for tx in transactions:
        if not isinstance(tx, dict) or not tx.get("transaction_id"):
            errors.append("every transaction must be an object with transaction_id")
            continue
        tid = str(tx["transaction_id"])
        if tid in indexed:
            errors.append("duplicate transaction_id: " + tid)
            continue
        try:
            parse_date(tx.get("date"))
            parse_money(tx.get("amount"))
        except ValueError as exc:
            errors.append("transaction %s: %s" % (tid, exc))
            continue
        indexed[tid] = tx
    if errors:
        return empty_result(errors)

    target_withdrawals = [
        tx for tx in indexed.values()
        if tx.get("status") == "posted" and tx.get("type") == "atm_withdrawal" and tx_month(tx) == month
    ]
    target_withdrawals.sort(key=lambda tx: (parse_date(tx["date"]), str(tx["transaction_id"])))
    target_ids = {str(tx["transaction_id"]) for tx in target_withdrawals}

    for withdrawal in target_withdrawals:
        wid = str(withdrawal["transaction_id"])
        annotation = annotations.get(wid, {})
        if annotation.get("location") not in ("domestic", "foreign"):
            add_unique(manual, "Withdrawal %s lacks a verified domestic/foreign classification." % wid)
        if annotation.get("network") not in ("in_network", "out_of_network"):
            add_unique(manual, "Withdrawal %s lacks a verified network classification." % wid)

    rho_fees = defaultdict(list)
    operator_fees = defaultdict(list)
    target_fee_ids = set()
    for tx in indexed.values():
        if tx.get("status") != "posted" or tx.get("type") != "atm_fee" or tx_month(tx) != month:
            continue
        fid = str(tx["transaction_id"])
        target_fee_ids.add(fid)
        annotation = annotations.get(fid, {})
        origin = annotation.get("fee_origin")
        related = str(annotation.get("related_withdrawal_id", ""))
        if origin not in ("rho_bank", "operator") or not related:
            add_unique(manual, "ATM fee %s lacks a verified origin and related withdrawal." % fid)
            continue
        if related not in target_ids:
            add_unique(manual, "ATM fee %s is not linked to a posted target-month withdrawal." % fid)
            continue
        if origin == "rho_bank":
            rho_fees[related].append(tx)
        else:
            operator_fees[related].append(tx)

    # Build fee expectations per relevant withdrawal. In-network withdrawals have
    # an expected Rho-Bank fee of zero and thus expose any linked Rho fee directly.
    expected_by_withdrawal = {}
    if product == "light_blue":
        ordinal = defaultdict(int)
        for withdrawal in target_withdrawals:
            wid = str(withdrawal["transaction_id"])
            annotation = annotations.get(wid, {})
            location = annotation.get("location")
            network = annotation.get("network")
            if location not in ("domestic", "foreign") or network not in ("in_network", "out_of_network"):
                continue
            if network == "in_network":
                expected_by_withdrawal[wid] = ZERO
                continue
            # Only eligible out-of-network withdrawals consume the applicable
            # allowance; Rho-Bank/in-network withdrawals are excluded.
            ordinal[location] += 1
            expected_by_withdrawal[wid] = expected_fee(
                product, location, parse_money(withdrawal["amount"]), ordinal[location]
            )
    else:
        for withdrawal in target_withdrawals:
            wid = str(withdrawal["transaction_id"])
            annotation = annotations.get(wid, {})
            location = annotation.get("location")
            network = annotation.get("network")
            if location not in ("domestic", "foreign") or network not in ("in_network", "out_of_network"):
                continue
            expected_by_withdrawal[wid] = (
                ZERO if network == "in_network"
                else expected_fee(product, location, parse_money(withdrawal["amount"]))
            )

    findings = []
    corrections = []
    # For Light Blue the finding is grouped by location, which makes the two free
    # uses auditable without incorrectly charging an in-network withdrawal to it.
    fee_groups = defaultdict(list)
    for withdrawal in target_withdrawals:
        wid = str(withdrawal["transaction_id"])
        if wid not in expected_by_withdrawal:
            continue
        annotation = annotations[wid]
        group = annotation["location"] if product == "light_blue" and annotation["network"] == "out_of_network" else wid
        fee_groups[group].append(withdrawal)

    for group, withdrawals in fee_groups.items():
        expected_total = sum((expected_by_withdrawal[str(tx["transaction_id"])] for tx in withdrawals), ZERO)
        charged_total = ZERO
        fee_ids = []
        for withdrawal in withdrawals:
            for fee in rho_fees.get(str(withdrawal["transaction_id"]), []):
                charged_total += parse_money(fee["amount"])
                fee_ids.append(str(fee["transaction_id"]))
        difference = charged_total - expected_total
        subject = (
            "Light Blue %s out-of-network withdrawals" % group
            if product == "light_blue" and group in ("domestic", "foreign")
            else "withdrawal " + str(group)
        )
        finding = {
            "subject": subject,
            "withdrawal_ids": [str(tx["transaction_id"]) for tx in withdrawals],
            "rho_bank_fee_ids": fee_ids,
            "expected_rho_bank_fee": fmt(expected_total),
            "charged_rho_bank_fee": fmt(charged_total),
            "difference_charged_minus_expected": fmt(difference),
        }
        if difference > ZERO:
            finding["outcome"] = "overcharge"
            corrections.append({"credit_type": "fee_refund", "amount": difference, "basis": subject})
        elif difference < ZERO:
            finding["outcome"] = "undercharge_or_unposted_fee"
        else:
            finding["outcome"] = "matches_schedule"
        findings.append(finding)

    if product == "purple":
        rebates_by_fee = defaultdict(list)
        for tx in indexed.values():
            if tx.get("status") != "posted" or tx_month(tx) != month or tx.get("type") not in ("fee_rebate", "rebate_credit"):
                continue
            rid = str(tx["transaction_id"])
            annotation = annotations.get(rid, {})
            fee_id = str(annotation.get("related_fee_id", ""))
            if annotation.get("rebate_source") != "atm_operator_rebate" or not fee_id:
                add_unique(manual, "Potential Purple rebate %s lacks verified ATM-operator-fee linkage." % rid)
                continue
            if fee_id not in target_fee_ids:
                add_unique(manual, "Purple rebate %s references a fee outside the target-month review." % rid)
                continue
            rebates_by_fee[fee_id].append(tx)

        eligible_operator_fees = []
        for wid in target_ids:
            eligible_operator_fees.extend(operator_fees.get(wid, []))
        operator_total = sum((parse_money(tx["amount"]) for tx in eligible_operator_fees), ZERO)
        expected_rebate = min(operator_total, Decimal("30.00"))
        posted_rebate = sum(
            (parse_money(rebate["amount"])
             for fee in eligible_operator_fees
             for rebate in rebates_by_fee.get(str(fee["transaction_id"]), [])),
            ZERO,
        )
        if posted_rebate > expected_rebate:
            add_unique(manual, "Linked Purple operator-fee rebates exceed the documented monthly cap; verify postings and classifications.")
        rebate_finding = {
            "subject": "Purple eligible ATM operator-fee rebates",
            "operator_fee_ids": [str(tx["transaction_id"]) for tx in eligible_operator_fees],
            "eligible_operator_fees": fmt(operator_total),
            "monthly_cap": "30.00",
            "expected_rebate_up_to_cap": fmt(expected_rebate),
            "posted_linked_rebates": fmt(posted_rebate),
            "difference_expected_minus_posted": fmt(expected_rebate - posted_rebate),
        }
        if expected_rebate > posted_rebate:
            rebate_finding["outcome"] = "possible_missing_rebate"
            corrections.append({
                "credit_type": "rebate_credit",
                "amount": expected_rebate - posted_rebate,
                "basis": "Purple linked eligible ATM operator-fee rebates",
            })
        else:
            rebate_finding["outcome"] = "cap_or_posted_rebates_accounted_for"
        findings.append(rebate_finding)

    candidate = None
    if not manual and corrections:
        refund_count = sum(item["credit_type"] == "fee_refund" for item in corrections)
        rebate_count = sum(item["credit_type"] == "rebate_credit" for item in corrections)
        if refund_count == rebate_count:
            add_unique(manual, "Fee-refund and rebate-credit corrections are tied; no majority credit type is defined.")
        else:
            candidate = {
                "account_id": account["account_id"],
                "amount": fmt(sum((item["amount"] for item in corrections), ZERO)),
                "credit_type": "fee_refund" if refund_count > rebate_count else "rebate_credit",
                "basis": [item["basis"] for item in corrections],
                "requires_external_prerequisites": [
                    "completed identity and ownership verification",
                    "eligible checking account, status, and balance confirmation",
                    "no prior interaction credit and no applicable 14-day cooldown",
                    "checking-account credit action and resulting balance retrieval",
                ],
            }

    return {
        "ok": True,
        "errors": [],
        "account_id": account["account_id"],
        "product": product,
        "review_month": month,
        "findings": findings,
        "corrections": [
            {"credit_type": item["credit_type"], "amount": fmt(item["amount"]), "basis": item["basis"]}
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
        result = empty_result([str(exc)])
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
