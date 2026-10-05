#!/usr/bin/env python3
"""Deterministic posted-ATM-fee analysis.

Reads the JSON schema documented in SKILL.md from stdin and writes one JSON object.
It deliberately requires explicit classification/linkage where transaction fields alone
cannot establish location, network, or whether a fee belongs to the bank or ATM owner.
"""
import json
import sys
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")
ZERO = Decimal("0")


def money(value):
    try:
        return Decimal(str(value)).copy_abs().quantize(CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("invalid monetary amount: %r" % (value,))


def fmt(value):
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def parse_date(value):
    return datetime.strptime(str(value), "%m/%d/%Y").date()


def month_of(tx):
    return parse_date(tx.get("date", "")).strftime("%Y-%m")


def account_product(account):
    text = " ".join(str(account.get(k, "")) for k in ("account_class", "account_name", "name", "product"))).lower()
    if "light blue" in text:
        return "light_blue"
    if "dark green" in text:
        return "dark_green"
    if "evergreen" in text:
        return "evergreen"
    if "purple" in text:
        return "purple"
    return None


def expected_fee(product, location, amount, ordinal=None):
    if product == "purple":
        return Decimal("2.50") if location == "domestic" else ZERO
    if product == "dark_green":
        if location == "domestic":
            return max((amount * Decimal("0.01")).quantize(CENT), Decimal("1.50"))
        return min((amount * Decimal("0.025")).quantize(CENT), Decimal("6.00"))
    if product == "evergreen":
        if location == "domestic":
            return min((amount * Decimal("0.01")).quantize(CENT), Decimal("2.50"))
        return max((amount * Decimal("0.02")).quantize(CENT), Decimal("3.00"))
    if product == "light_blue":
        if ordinal is None:
            raise ValueError("Light Blue allowance ordinal missing")
        if ordinal <= 2:
            return ZERO
        return Decimal("2.50") if location == "domestic" else Decimal("4.00")
    raise ValueError("unsupported product")


def add_manual(items, message):
    if message not in items:
        items.append(message)


def main(payload):
    errors = []
    manual = []
    findings = []
    corrections = []

    account = payload.get("account")
    txs = payload.get("transactions")
    annotations = payload.get("annotations", {})
    review_month = payload.get("review_month")
    if not isinstance(account, dict):
        errors.append("account must be an object")
    if not isinstance(txs, list):
        errors.append("transactions must be an array")
    if not isinstance(annotations, dict):
        errors.append("annotations must be an object")
    try:
        datetime.strptime(str(review_month), "%Y-%m")
    except (ValueError, TypeError):
        errors.append("review_month must use YYYY-MM")
    if errors:
        return {"ok": False, "errors": errors, "findings": [], "corrections": [], "manual_review": [], "credit_candidate": None}

    product = account_product(account)
    if not product:
        errors.append("account product is not one of Purple, Light Blue, Dark Green, or Evergreen")
    if not account.get("account_id"):
        errors.append("account.account_id is required")
    if not payload.get("full_transaction_history"):
        add_manual(manual, "Complete transaction history was not asserted; monthly Light Blue and Purple calculations cannot be validated.")

    indexed = {}
    valid_txs = []
    for tx in txs:
        if not isinstance(tx, dict) or not tx.get("transaction_id"):
            errors.append("every transaction must be an object with transaction_id")
            continue
        tid = str(tx["transaction_id"])
        if tid in indexed:
            errors.append("duplicate transaction_id: " + tid)
            continue
        try:
            parse_date(tx.get("date"))
            money(tx.get("amount"))
        except ValueError as exc:
            errors.append("transaction %s: %s" % (tid, exc))
            continue
        indexed[tid] = tx
        valid_txs.append(tx)
    if errors:
        return {"ok": False, "errors": errors, "findings": [], "corrections": [], "manual_review": manual, "credit_candidate": None}

    posted_withdrawals = [
        tx for tx in valid_txs
        if tx.get("status") == "posted" and tx.get("type") == "atm_withdrawal" and month_of(tx) == review_month
    ]
    posted_withdrawals.sort(key=lambda t: (parse_date(t["date"]), str(t["transaction_id"])))

    # Require geography/network for every target-month withdrawal. This prevents an
    # incorrect Light Blue allowance count and prevents treating an in-network fee as valid.
    for tx in posted_withdrawals:
        ann = annotations.get(str(tx["transaction_id"]), {})
        if ann.get("location") not in ("domestic", "foreign") or ann.get("network") not in ("in_network", "out_of_network"):
            add_manual(manual, "Withdrawal %s lacks explicit domestic/foreign and in-network/out-of-network classification." % tx["transaction_id"])

    # Fee links are explicit because dates/descriptions alone may not safely associate a fee.
    bank_fees = defaultdict(list)
    operator_fees = defaultdict(list)
    for tx in valid_txs:
        if tx.get("status") != "posted" or tx.get("type") != "atm_fee":
            continue
        tid = str(tx["transaction_id"])
        ann = annotations.get(tid, {})
        origin = ann.get("fee_origin")
        related = str(ann.get("related_withdrawal_id", ""))
        if origin not in ("rho_bank", "operator") or not related:
            if month_of(tx) == review_month:
                add_manual(manual, "ATM fee %s lacks a verified origin and related withdrawal." % tid)
            continue
        if related not in indexed:
            add_manual(manual, "ATM fee %s references an unknown withdrawal %s." % (tid, related))
            continue
        if origin == "rho_bank":
            bank_fees[related].append(tx)
        else:
            operator_fees[related].append(tx)

    # Existing Purple rebates must be linked and classified so their use of the cap is known.
    rebates_by_fee = defaultdict(list)
    if product == "purple":
        for tx in valid_txs:
            if tx.get("status") != "posted" or tx.get("type") not in ("fee_rebate", "rebate_credit"):
                continue
            tid = str(tx["transaction_id"])
            ann = annotations.get(tid, {})
            related_fee = str(ann.get("related_fee_id", ""))
            if ann.get("rebate_source") != "atm_operator_rebate" or not related_fee:
                if month_of(tx) == review_month:
                    add_manual(manual, "Potential rebate %s is not verified as a linked ATM operator-fee rebate." % tid)
                continue
            rebates_by_fee[related_fee].append(tx)

    applicable = []
    for withdrawal in posted_withdrawals:
        wid = str(withdrawal["transaction_id"])
        ann = annotations.get(wid, {})
        if ann.get("network") != "out_of_network":
            # A linked Rho fee on an in-network withdrawal is still a possible mischarge.
            if bank_fees.get(wid):
                applicable.append((withdrawal, ZERO, "in_network"))
            continue
        if ann.get("location") not in ("domestic", "foreign"):
            continue
        applicable.append((withdrawal, None, ann["location"]))

    # For Light Blue, the schedule is applied in chronological order separately by location.
    if product == "light_blue":
        location_ordinals = defaultdict(int)
        calculated = []
        for withdrawal, _, location in applicable:
            location_ordinals[location] += 1
            calculated.append((withdrawal, expected_fee(product, location, money(withdrawal["amount"]), location_ordinals[location]), location))
    else:
        calculated = []
        for withdrawal, expected, location in applicable:
            if expected is None:
                expected = expected_fee(product, location, money(withdrawal["amount"]))
            calculated.append((withdrawal, expected, location))

    # Light Blue result is summarized by location so the free allowance is not falsely
    # assigned to a particular same-day fee line; other products can be evaluated per withdrawal.
    groups = defaultdict(list)
    for withdrawal, expected, location in calculated:
        key = location if product == "light_blue" else str(withdrawal["transaction_id"])
        groups[key].append((withdrawal, expected, location))

    for key, group in groups.items():
        expected_total = sum((entry[1] for entry in group), ZERO)
        charged_total = ZERO
        fee_ids = []
        for withdrawal, _, _ in group:
            wid = str(withdrawal["transaction_id"])
            for fee in bank_fees.get(wid, []):
                charged_total += money(fee["amount"])
                fee_ids.append(str(fee["transaction_id"]))
        label = ("Light Blue %s out-of-network withdrawals" % key) if product == "light_blue" else ("withdrawal " + key)
        delta = charged_total - expected_total
        finding = {
            "subject": label,
            "withdrawal_ids": [str(x[0]["transaction_id"]) for x in group],
            "rho_bank_fee_ids": fee_ids,
            "expected_rho_bank_fee": fmt(expected_total),
            "charged_rho_bank_fee": fmt(charged_total),
            "difference_charged_minus_expected": fmt(delta),
        }
        if delta > ZERO:
            finding["outcome"] = "overcharge"
            corrections.append({"credit_type": "fee_refund", "amount": delta, "basis": label})
        elif delta < ZERO:
            finding["outcome"] = "undercharge_or_unposted_fee"
        else:
            finding["outcome"] = "matches_schedule"
        findings.append(finding)

    # Purple operator rebates: the documented cap is evaluated on linked posted operator fees
    # for withdrawals in the review month, and linked posted ATM rebate credits.
    if product == "purple":
        eligible_operator_fees = []
        for withdrawal in posted_withdrawals:
            wid = str(withdrawal["transaction_id"])
            for fee in operator_fees.get(wid, []):
                eligible_operator_fees.append(fee)
        eligible_total = sum((money(f["amount"]) for f in eligible_operator_fees), ZERO)
        expected_rebate = min(eligible_total, Decimal("30.00"))
        credited_total = ZERO
        for fee in eligible_operator_fees:
            fid = str(fee["transaction_id"])
            credited_total += sum((money(r["amount"]) for r in rebates_by_fee.get(fid, [])), ZERO)
        if credited_total > expected_rebate:
            add_manual(manual, "Linked Purple ATM operator rebates exceed the documented monthly cap; verify classifications and postings.")
        rebate_finding = {
            "subject": "Purple eligible ATM operator-fee rebates",
            "operator_fee_ids": [str(f["transaction_id"]) for f in eligible_operator_fees],
            "eligible_operator_fees": fmt(eligible_total),
            "monthly_cap": "30.00",
            "expected_rebate_up_to_cap": fmt(expected_rebate),
            "posted_linked_rebates": fmt(credited_total),
            "difference_expected_minus_posted": fmt(expected_rebate - credited_total),
        }
        if expected_rebate > credited_total:
            rebate_finding["outcome"] = "possible_missing_rebate"
            corrections.append({"credit_type": "rebate_credit", "amount": expected_rebate - credited_total, "basis": "Purple linked eligible ATM operator-fee rebates"})
        else:
            rebate_finding["outcome"] = "cap_or_posted_rebates_accounted_for"
        findings.append(rebate_finding)

    # A candidate is analytical only. Suppress it whenever evidence is incomplete.
    candidate = None
    if not manual and corrections:
        fee_count = sum(1 for c in corrections if c["credit_type"] == "fee_refund")
        rebate_count = sum(1 for c in corrections if c["credit_type"] == "rebate_credit")
        chosen = None
        if fee_count > rebate_count:
            chosen = "fee_refund"
        elif rebate_count > fee_count:
            chosen = "rebate_credit"
        else:
            add_manual(manual, "Fee-refund and rebate-credit corrections are tied; policy does not define a majority credit type.")
        if chosen:
            candidate = {
                "account_id": account["account_id"],
                "amount": fmt(sum((c["amount"] for c in corrections), ZERO)),
                "credit_type": chosen,
                "basis": [c["basis"] for c in corrections],
                "requires_external_prerequisites": [
                    "verified identity and account ownership",
                    "eligible checking account and account status confirmation",
                    "14-day cooldown and no prior credit in this interaction",
                    "customer confirmation of the exact combined credit",
                ],
            }

    # Decimal values are converted only at the boundary above.
    return {
        "ok": not errors,
        "errors": errors,
        "account_id": account.get("account_id"),
        "product": product,
        "review_month": review_month,
        "findings": findings,
        "corrections": [{"credit_type": c["credit_type"], "amount": fmt(c["amount"]), "basis": c["basis"]} for c in corrections],
        "manual_review": manual,
        "credit_candidate": candidate if not manual else None,
    }


if __name__ == "__main__":
    try:
        source = json.load(sys.stdin)
        if not isinstance(source, dict):
            raise ValueError("top-level JSON value must be an object")
        result = main(source)
    except Exception as exc:  # Emit machine-readable failure rather than a partial result.
        result = {"ok": False, "errors": [str(exc)], "findings": [], "corrections": [], "manual_review": [], "credit_candidate": None}
    print(json.dumps(result, sort_keys=True))
