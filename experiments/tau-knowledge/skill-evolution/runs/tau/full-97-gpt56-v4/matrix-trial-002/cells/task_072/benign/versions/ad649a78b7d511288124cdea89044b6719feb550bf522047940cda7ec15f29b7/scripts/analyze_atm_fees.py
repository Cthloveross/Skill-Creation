#!/usr/bin/env python3
"""Deterministic ATM-fee arithmetic for explicitly classified transaction records.

Reads one JSON object from stdin and writes one JSON result to stdout. See SKILL.md
for the schema. This program does not infer account eligibility, geography, or fee
linkage from ambiguous descriptions.
"""
import json
import sys
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")


def money(value):
    try:
        return Decimal(str(value)).copy_abs().quantize(CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        return None


def out_money(value):
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def tx_month(tx):
    value = str(tx.get("date", ""))
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m")
        except ValueError:
            pass
    return None


def tx_date_key(tx):
    value = str(tx.get("date", ""))
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            pass
    return "9999-99-99"


def product_name(account):
    return " ".join(str(account.get(k, "")) for k in ("product", "account_class", "account_type")).lower()


def issue(code, detail):
    return {"code": code, "detail": detail}


def relevant_transactions(transactions, month):
    month_txs = []
    warnings = []
    for tx in transactions:
        parsed = tx_month(tx)
        if parsed is None:
            warnings.append(issue("invalid_date", "A transaction has an unparseable date and was ignored."))
        elif parsed == month:
            month_txs.append(tx)
    return month_txs, warnings


def analyze_bluest(account, txs, context, classified):
    warnings = []
    ids = {str(t.get("transaction_id", "")): t for t in txs}
    fees = classified.get("fee_links", {})
    credits = classified.get("credits", {})
    operator_fees = Decimal("0")
    rebate_credits = Decimal("0")
    included_fees = []
    included_credits = []

    for fee_id, link in fees.items():
        tx = ids.get(str(fee_id))
        if tx is None:
            warnings.append(issue("unmatched_fee", "A classified fee is not in the requested month."))
            continue
        if tx.get("type") != "atm_fee":
            warnings.append(issue("not_atm_fee", "A classified fee does not have transaction type atm_fee."))
            continue
        if isinstance(link, dict) and link.get("fee_scope") == "operator":
            amount = money(tx.get("amount"))
            if amount is None:
                warnings.append(issue("invalid_amount", "An operator-fee amount is invalid."))
            else:
                operator_fees += amount
                included_fees.append(str(fee_id))

    for credit_id, kind in credits.items():
        tx = ids.get(str(credit_id))
        if tx is None or kind != "atm_rebate":
            if tx is None:
                warnings.append(issue("unmatched_credit", "A classified rebate credit is not in the requested month."))
            continue
        amount = money(tx.get("amount"))
        if amount is None or Decimal(str(tx.get("amount", 0))) <= 0:
            warnings.append(issue("invalid_credit", "A rebate credit must be a positive transaction."))
        else:
            rebate_credits += amount
            included_credits.append(str(credit_id))

    active = context.get("bluest_benefits_active") is True
    result = {
        "policy": "Bluest third-party ATM fees are rebated up to $50 per statement cycle only while benefits are active.",
        "confirmed_operator_fee_total": out_money(operator_fees),
        "confirmed_rebate_credit_total": out_money(rebate_credits),
        "operator_fee_transaction_ids": included_fees,
        "rebate_credit_transaction_ids": included_credits,
        "benefits_active_confirmed": active,
        "warnings": warnings,
    }
    if not active:
        result["review_status"] = "eligibility_unconfirmed"
        result["possible_missing_rebate"] = None
        result["warnings"].append(issue("benefit_eligibility_required", "Do not determine a missing Bluest rebate without confirming the cycle benefit condition."))
    else:
        ceiling = min(operator_fees, Decimal("50.00"))
        shortfall = max(Decimal("0"), ceiling - rebate_credits)
        result.update({
            "review_status": "calculated_from_classified_transactions",
            "maximum_eligible_rebate": out_money(ceiling),
            "possible_missing_rebate": out_money(shortfall),
        })
    return result


def foreign_expected(withdrawal_amount):
    if withdrawal_amount <= Decimal("100.00"):
        return Decimal("2.00")
    if withdrawal_amount <= Decimal("300.00"):
        return Decimal("3.50")
    return Decimal("5.00")


def analyze_light_green(account, txs, classified):
    warnings = []
    ids = {str(t.get("transaction_id", "")): t for t in txs}
    withdrawals = classified.get("withdrawals", {})
    fee_links = classified.get("fee_links", {})
    eligible = []

    for withdrawal_id, classification in withdrawals.items():
        tx = ids.get(str(withdrawal_id))
        if tx is None:
            warnings.append(issue("unmatched_withdrawal", "A classified withdrawal is not in the requested month."))
            continue
        if tx.get("type") != "atm_withdrawal":
            warnings.append(issue("not_atm_withdrawal", "A classified withdrawal does not have type atm_withdrawal."))
            continue
        amount = money(tx.get("amount"))
        if amount is None:
            warnings.append(issue("invalid_amount", "A withdrawal amount is invalid."))
            continue
        if not isinstance(classification, dict):
            warnings.append(issue("invalid_classification", "A withdrawal classification must be an object."))
            continue
        location = classification.get("location")
        network = classification.get("network")
        if location not in ("domestic", "foreign"):
            warnings.append(issue("unknown_location", "A classified withdrawal has no confirmed domestic/foreign location."))
            continue
        if location == "domestic" and network != "out_of_network":
            continue
        eligible.append((tx_date_key(tx), str(withdrawal_id), amount, location))

    eligible.sort(key=lambda item: (item[0], item[1]))
    domestic_count = 0
    expected_by_withdrawal = {}
    for _, withdrawal_id, amount, location in eligible:
        if location == "foreign":
            expected_by_withdrawal[withdrawal_id] = foreign_expected(amount)
        else:
            domestic_count += 1
            expected_by_withdrawal[withdrawal_id] = Decimal("0") if domestic_count <= 4 else Decimal("1.50")

    actual_by_withdrawal = defaultdict(lambda: Decimal("0"))
    fee_ids_by_withdrawal = defaultdict(list)
    for fee_id, link in fee_links.items():
        tx = ids.get(str(fee_id))
        if tx is None:
            warnings.append(issue("unmatched_fee", "A linked ATM fee is not in the requested month."))
            continue
        if tx.get("type") != "atm_fee":
            warnings.append(issue("not_atm_fee", "A linked fee does not have type atm_fee."))
            continue
        if not isinstance(link, dict) or link.get("fee_scope") != "rho_bank":
            continue
        withdrawal_id = str(link.get("withdrawal_id", ""))
        if withdrawal_id not in expected_by_withdrawal:
            warnings.append(issue("fee_link_not_reviewable", "A Rho-Bank fee is linked to an unclassified or ineligible withdrawal."))
            continue
        amount = money(tx.get("amount"))
        if amount is None:
            warnings.append(issue("invalid_amount", "A linked fee amount is invalid."))
            continue
        actual_by_withdrawal[withdrawal_id] += amount
        fee_ids_by_withdrawal[withdrawal_id].append(str(fee_id))

    rows = []
    total_overcharge = Decimal("0")
    total_expected = Decimal("0")
    total_actual = Decimal("0")
    for _, withdrawal_id, amount, location in eligible:
        expected = expected_by_withdrawal[withdrawal_id]
        actual = actual_by_withdrawal[withdrawal_id]
        overcharge = max(Decimal("0"), actual - expected)
        total_expected += expected
        total_actual += actual
        total_overcharge += overcharge
        rows.append({
            "withdrawal_id": withdrawal_id,
            "location": location,
            "withdrawal_amount": out_money(amount),
            "expected_rho_bank_fee": out_money(expected),
            "linked_rho_bank_fee_total": out_money(actual),
            "possible_overcharge": out_money(overcharge),
            "linked_fee_transaction_ids": fee_ids_by_withdrawal[withdrawal_id],
        })

    return {
        "policy": "Light Green has four free domestic out-of-network withdrawals monthly; later domestic fees are $1.50. Foreign fees are assessed separately per withdrawal tier.",
        "review_status": "calculated_from_classified_transactions",
        "domestic_out_of_network_withdrawal_count": domestic_count,
        "expected_rho_bank_fee_total": out_money(total_expected),
        "linked_rho_bank_fee_total": out_money(total_actual),
        "possible_fee_refund_total": out_money(total_overcharge),
        "withdrawal_fee_comparisons": rows,
        "warnings": warnings,
    }


def main(payload):
    month = payload.get("month")
    if not isinstance(month, str) or len(month) != 7 or month[4] != "-":
        raise ValueError("month must use YYYY-MM")
    accounts = payload.get("accounts")
    transactions_by_account = payload.get("transactions_by_account")
    if not isinstance(accounts, list) or not isinstance(transactions_by_account, dict):
        raise ValueError("accounts must be a list and transactions_by_account must be an object")
    contexts = payload.get("context_by_account", {})
    classifications = payload.get("classifications_by_account", {})
    results = []
    for account in accounts:
        account_id = str(account.get("account_id", ""))
        if not account_id:
            results.append({"review_status": "skipped", "warnings": [issue("missing_account_id", "Account record lacks account_id.")]})
            continue
        raw = transactions_by_account.get(account_id, [])
        if not isinstance(raw, list):
            raw = []
        month_txs, date_warnings = relevant_transactions(raw, month)
        product = product_name(account)
        context = contexts.get(account_id, {}) if isinstance(contexts.get(account_id, {}), dict) else {}
        classified = classifications.get(account_id, {}) if isinstance(classifications.get(account_id, {}), dict) else {}
        if "bluest" in product:
            review = analyze_bluest(account, month_txs, context, classified)
        elif "light green" in product:
            review = analyze_light_green(account, month_txs, classified)
        else:
            review = {"review_status": "unsupported_product", "warnings": [issue("unsupported_product", "Only Bluest and Light Green policy arithmetic is supported.")]}
        review["account_id"] = account_id
        review["transaction_month"] = month
        review["transaction_count_in_month"] = len(month_txs)
        review.setdefault("warnings", []).extend(date_warnings)
        results.append(review)
    return {"ok": True, "month": month, "accounts": results}


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
