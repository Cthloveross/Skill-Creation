#!/usr/bin/env python3
"""Reconcile classified monthly ATM activity without making banking actions.

Input and output are JSON objects on stdin/stdout. See SKILL.md for the schema.
"""
import json
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")
VALID_CLASSES = {
    "bluest_eligible_third_party_atm_fee",
    "bluest_existing_atm_rebate",
    "lg_domestic_oon_withdrawal",
    "lg_domestic_oon_rho_fee",
    "lg_foreign_withdrawal",
    "lg_foreign_rho_fee",
    "lg_existing_atm_fee_refund",
    "operator_surcharge",
    "unrelated",
    "unknown",
}
ATM_TYPES = {"atm_withdrawal", "atm_fee"}
POSSIBLE_CREDIT_TYPES = {"fee_rebate", "rebate_credit", "fee_refund"}


def money(value):
    try:
        if isinstance(value, bool) or value is None:
            raise InvalidOperation
        return Decimal(str(value).replace("$", "").replace(",", "")).quantize(
            CENT, rounding=ROUND_HALF_UP
        )
    except (InvalidOperation, ValueError):
        raise ValueError("invalid monetary value: %r" % (value,))


def fmt(value):
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def month_date(value):
    return datetime.strptime(str(value), "%m/%d/%Y").date()


def is_open(value):
    return str(value).strip().lower() == "open"


def output_error(errors):
    print(json.dumps({
        "safe_to_credit": False,
        "recommendation": None,
        "validation_errors": errors,
        "unresolved_transaction_ids": [],
    }, sort_keys=True))


def foreign_expected(cash_amount):
    if cash_amount <= Decimal("100.00"):
        return Decimal("2.00")
    if cash_amount <= Decimal("300.00"):
        return Decimal("3.50")
    return Decimal("5.00")


def main(payload):
    errors = []
    account = payload.get("account")
    period = payload.get("period")
    transactions = payload.get("transactions")
    annotations = payload.get("annotations", {})
    if not isinstance(account, dict):
        errors.append("account must be an object")
        account = {}
    if not isinstance(period, dict):
        errors.append("period must be an object")
        period = {}
    if not isinstance(transactions, list):
        errors.append("transactions must be an array containing the complete account feed")
        transactions = []
    if not isinstance(annotations, dict):
        errors.append("annotations must be an object keyed by transaction_id")
        annotations = {}

    account_id = account.get("account_id")
    account_class = account.get("account_class")
    if not account_id:
        errors.append("account.account_id is required")
    if str(account.get("account_type", "")).strip().lower() != "checking":
        errors.append("credits are permitted only for a checking account")
    if not is_open(account.get("status", "")):
        errors.append("account must be OPEN before a correction can be applied")
    if account_class not in {"Bluest Account", "Light Green Account"}:
        errors.append("account_class must be Bluest Account or Light Green Account")
    if payload.get("product_eligibility_confirmed") is not True:
        errors.append("product eligibility has not been confirmed")
    if account_class == "Bluest Account" and payload.get("benefit_active") is not True:
        errors.append("Bluest historical benefit eligibility has not been confirmed")

    try:
        year = int(period.get("year"))
        month = int(period.get("month"))
        if not 1 <= month <= 12:
            raise ValueError
    except (TypeError, ValueError):
        errors.append("period.year and period.month must identify a valid month")
        year, month = 0, 0

    normalized = []
    seen_ids = set()
    for index, raw in enumerate(transactions):
        if not isinstance(raw, dict):
            errors.append("transactions[%d] is not an object" % index)
            continue
        tid = raw.get("transaction_id")
        if not tid:
            errors.append("transactions[%d] has no transaction_id" % index)
            continue
        if tid in seen_ids:
            errors.append("duplicate transaction_id: %s" % tid)
            continue
        seen_ids.add(tid)
        try:
            date = month_date(raw.get("date"))
            amount = money(raw.get("amount"))
        except (ValueError, TypeError) as exc:
            errors.append("transaction %s: %s" % (tid, exc))
            continue
        if raw.get("account_id") != account_id:
            errors.append("transaction %s does not belong to selected account" % tid)
        normalized.append({
            "id": tid,
            "date": date,
            "amount": amount,
            "type": str(raw.get("type", "")).strip(),
            "status": str(raw.get("status", "")).strip().lower(),
        })

    target = [t for t in normalized if t["date"].year == year and t["date"].month == month]
    posted = [t for t in target if t["status"] == "posted"]
    pending = [t["id"] for t in target if t["status"] == "pending" and t["type"] in ATM_TYPES]
    unresolved = []

    # Every ATM item and every possible rebate/refund credit needs an explicit review
    # classification. This prevents description-only assumptions.
    reviewed = []
    for tx in posted:
        requires_annotation = tx["type"] in ATM_TYPES or (
            tx["type"] in POSSIBLE_CREDIT_TYPES and tx["amount"] > 0
        )
        if not requires_annotation:
            continue
        annotation = annotations.get(tx["id"])
        classification = annotation.get("classification") if isinstance(annotation, dict) else None
        if classification not in VALID_CLASSES or classification == "unknown":
            unresolved.append(tx["id"])
            continue
        reviewed.append((tx, annotation, classification))

    # Do not let annotations point at data that was not actually provided.
    for tid in annotations:
        if tid not in seen_ids:
            errors.append("annotation references absent transaction_id: %s" % tid)

    result = {
        "account_id": account_id,
        "period": {"year": year, "month": month},
        "safe_to_credit": False,
        "recommendation": None,
        "components": {},
        "evidence_transaction_ids": [],
        "pending_atm_transaction_ids": pending,
        "unresolved_transaction_ids": sorted(set(unresolved)),
        "validation_errors": errors,
    }

    if account_class == "Bluest Account":
        fees, rebates, evidence = Decimal("0"), Decimal("0"), []
        for tx, _annotation, classification in reviewed:
            if classification == "bluest_eligible_third_party_atm_fee":
                if tx["type"] != "atm_fee" or tx["amount"] >= 0:
                    errors.append("Bluest eligible fee %s must be a negative posted atm_fee" % tx["id"])
                else:
                    fees += -tx["amount"]
                    evidence.append(tx["id"])
            elif classification == "bluest_existing_atm_rebate":
                if tx["amount"] <= 0:
                    errors.append("Bluest existing rebate %s must be a positive credit" % tx["id"])
                else:
                    rebates += tx["amount"]
                    evidence.append(tx["id"])
            elif classification.startswith("lg_"):
                errors.append("Light Green classification %s used for Bluest transaction %s" % (classification, tx["id"]))
        entitled = min(fees, Decimal("50.00"))
        correction = max(Decimal("0"), entitled - rebates)
        result["components"] = {
            "eligible_third_party_atm_fees": fmt(fees),
            "monthly_rebate_cap": "50.00",
            "rebate_entitlement_before_prior_credits": fmt(entitled),
            "existing_related_atm_rebates": fmt(rebates),
            "missing_rebate": fmt(correction),
        }
        credit_type = "rebate_credit"
    elif account_class == "Light Green Account":
        domestic_withdrawals, domestic_fees = [], Decimal("0")
        foreign_expected_total, foreign_fees, prior_refunds = Decimal("0"), Decimal("0"), Decimal("0")
        evidence = []
        for tx, annotation, classification in reviewed:
            if classification == "lg_domestic_oon_withdrawal":
                if tx["type"] != "atm_withdrawal" or tx["amount"] >= 0:
                    errors.append("domestic withdrawal %s must be a negative posted atm_withdrawal" % tx["id"])
                else:
                    domestic_withdrawals.append(tx["id"])
                    evidence.append(tx["id"])
            elif classification == "lg_domestic_oon_rho_fee":
                if tx["type"] != "atm_fee" or tx["amount"] >= 0:
                    errors.append("domestic fee %s must be a negative posted atm_fee" % tx["id"])
                else:
                    domestic_fees += -tx["amount"]
                    evidence.append(tx["id"])
            elif classification == "lg_foreign_withdrawal":
                if tx["type"] != "atm_withdrawal" or tx["amount"] >= 0:
                    errors.append("foreign withdrawal %s must be a negative posted atm_withdrawal" % tx["id"])
                    continue
                try:
                    cash = money(annotation.get("cash_withdrawal_amount"))
                    if cash <= 0:
                        raise ValueError("must be positive")
                except (ValueError, TypeError) as exc:
                    errors.append("foreign withdrawal %s needs reliable cash_withdrawal_amount: %s" % (tx["id"], exc))
                    continue
                foreign_expected_total += foreign_expected(cash)
                evidence.append(tx["id"])
            elif classification == "lg_foreign_rho_fee":
                if tx["type"] != "atm_fee" or tx["amount"] >= 0:
                    errors.append("foreign Rho fee %s must be a negative posted atm_fee" % tx["id"])
                else:
                    foreign_fees += -tx["amount"]
                    evidence.append(tx["id"])
            elif classification == "lg_existing_atm_fee_refund":
                if tx["amount"] <= 0:
                    errors.append("existing ATM refund %s must be a positive credit" % tx["id"])
                else:
                    prior_refunds += tx["amount"]
                    evidence.append(tx["id"])
            elif classification.startswith("bluest_"):
                errors.append("Bluest classification %s used for Light Green transaction %s" % (classification, tx["id"]))
        domestic_expected = Decimal(max(0, len(domestic_withdrawals) - 4)) * Decimal("1.50")
        charged = domestic_fees + foreign_fees
        expected = domestic_expected + foreign_expected_total
        correction = max(Decimal("0"), charged - prior_refunds - expected)
        result["components"] = {
            "domestic_out_of_network_withdrawal_count": len(domestic_withdrawals),
            "domestic_rho_fees_charged": fmt(domestic_fees),
            "domestic_rho_fees_expected": fmt(domestic_expected),
            "foreign_rho_fees_charged": fmt(foreign_fees),
            "foreign_rho_fees_expected": fmt(foreign_expected_total),
            "existing_related_atm_fee_refunds": fmt(prior_refunds),
            "net_fee_mischarge": fmt(correction),
        }
        credit_type = "fee_refund"
    else:
        correction = Decimal("0")
        credit_type = None

    result["evidence_transaction_ids"] = sorted(set(evidence))
    result["validation_errors"] = errors
    if not errors and not result["unresolved_transaction_ids"]:
        result["safe_to_credit"] = True
        result["recommendation"] = {
            "amount": fmt(correction),
            "credit_type": credit_type if correction > 0 else None,
            "action": "apply_one_credit" if correction > 0 else "no_credit_due",
        }
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("top-level JSON must be an object")
        main(payload)
    except Exception as exc:
        output_error([str(exc)])
