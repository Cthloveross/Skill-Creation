#!/usr/bin/env python3
"""Audit documented checking ATM bank-fee charges. JSON stdin to JSON stdout."""
import json
import sys
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


def monetary(value):
    try:
        return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("invalid monetary amount")


def text(value):
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def tx_date(value):
    try:
        return datetime.strptime(str(value), "%m/%d/%Y").date()
    except (TypeError, ValueError):
        raise ValueError("date must be MM/DD/YYYY")


def product(account):
    value = str(account.get("product", account.get("account_class", ""))).lower()
    if "light green" in value:
        return "light_green"
    if "blue" in value:
        return "blue"
    if "green" in value:
        return "green"
    return None


def in_review_month(record, month):
    return tx_date(record.get("date")).strftime("%Y-%m") == month


def classify_description(withdrawal):
    """Return only classifications established by a withdrawal description."""
    desc = str(withdrawal.get("description", "")).upper()
    if "RHO-BANK" in desc or "RHO BANK" in desc:
        return "in_network"
    if any(word in desc for word in ("FOREIGN", "INTERNATIONAL", "OVERSEAS")):
        return "foreign"
    if "NON-RHO" in desc or "NON RHO" in desc or "OUT-OF-NETWORK" in desc or "OUT OF NETWORK" in desc:
        return "domestic_out_of_network"
    return None


def infer_component(fee):
    desc = str(fee.get("description", "")).upper()
    # This label denotes the bank's asserted non-network fee. A user-provided
    # context can override it when records positively establish an operator fee.
    if "NON-RHO ATM FEE" in desc or "NON RHO ATM FEE" in desc:
        return "bank_fee"
    if "FOREIGN ATM" in desc or "INTERNATIONAL ATM" in desc:
        return "bank_fee"
    return None


def allowed_fee(kind, classification, amount, light_ordinal=None):
    if classification == "in_network":
        return ZERO
    if classification == "domestic_out_of_network":
        if kind == "blue":
            return min(amount * Decimal("0.01"), Decimal("3.00")).quantize(CENT, rounding=ROUND_HALF_UP)
        if kind == "green":
            return Decimal("3.00")
        if kind == "light_green":
            if light_ordinal is None:
                raise ValueError("Light Green domestic ordinal is unavailable")
            return ZERO if light_ordinal <= 4 else Decimal("1.50")
    if classification == "foreign":
        if kind in ("blue", "green"):
            return max(amount * Decimal("0.03"), Decimal("5.00")).quantize(CENT, rounding=ROUND_HALF_UP)
        if kind == "light_green":
            if amount <= Decimal("100.00"):
                return Decimal("2.00")
            if amount <= Decimal("300.00"):
                return Decimal("3.50")
            return Decimal("5.00")
    raise ValueError("unsupported product or withdrawal classification")


def result_base(account_id, fee, kind):
    return {"account_id": account_id, "fee_transaction_id": str(fee.get("transaction_id")),
            "date": fee.get("date"), "status": fee.get("status"), "product": kind}


def audit_account(account, all_records, month, contexts, corrections, errors):
    account_id = account.get("account_id")
    output = []
    candidates = []
    summary = {"account_id": account_id, "product": product(account),
               "is_checking": "checking" in str(account.get("account_type", "")).lower(),
               "status": account.get("status"), "balance": account.get("balance"),
               "supported_overcharge": "0.00"}
    kind = summary["product"]
    if not summary["is_checking"]:
        errors.append("account %s is not identified as checking" % account_id)
        return summary, output, candidates
    if kind is None:
        errors.append("unsupported or missing product for account %s" % account_id)
        return summary, output, candidates

    month_records = []
    for record in all_records:
        if not isinstance(record, dict):
            errors.append("non-object transaction on account %s" % account_id)
            continue
        try:
            if in_review_month(record, month):
                month_records.append(record)
        except ValueError:
            errors.append("invalid date on account %s transaction %s" % (account_id, record.get("transaction_id")))

    withdrawals = [r for r in month_records if r.get("type") == "atm_withdrawal"]
    fees = [r for r in month_records if r.get("type") == "atm_fee"]
    by_id = {str(r.get("transaction_id")): r for r in withdrawals if r.get("transaction_id") is not None}

    # Create reliable same-date pairing only where there is exactly one withdrawal.
    withdrawals_by_date = defaultdict(list)
    for withdrawal in withdrawals:
        withdrawals_by_date[str(withdrawal.get("date"))].append(withdrawal)

    fee_withdrawal = {}
    for fee in fees:
        fee_id = str(fee.get("transaction_id"))
        context = contexts.get(fee_id, {})
        selected = None
        if isinstance(context, dict) and context.get("withdrawal_transaction_id") is not None:
            selected = by_id.get(str(context["withdrawal_transaction_id"]))
        elif len(withdrawals_by_date[str(fee.get("date"))]) == 1:
            selected = withdrawals_by_date[str(fee.get("date"))][0]
        if selected is not None:
            fee_withdrawal[fee_id] = selected

    # Light Green's allowance counts all known domestic non-network withdrawals,
    # including fee-free withdrawals. A NON-RHO fee paired with an otherwise
    # unlabelled withdrawal establishes that withdrawal's domestic classification.
    linked_non_rho = set()
    for fee in fees:
        fee_id = str(fee.get("transaction_id"))
        if "NON-RHO ATM FEE" in str(fee.get("description", "")).upper():
            withdrawal = fee_withdrawal.get(fee_id)
            if withdrawal is not None:
                linked_non_rho.add(str(withdrawal.get("transaction_id")))
    domestic = []
    if kind == "light_green":
        for withdrawal in withdrawals:
            wid = str(withdrawal.get("transaction_id"))
            context = (account.get("withdrawal_context", {}) or {}).get(wid, {})
            classified = context.get("withdrawal_classification") if isinstance(context, dict) else None
            classified = classified or classify_description(withdrawal)
            if classified == "domestic_out_of_network" or wid in linked_non_rho:
                try:
                    domestic.append((tx_date(withdrawal.get("date")), wid))
                except ValueError:
                    pass
        domestic.sort(key=lambda pair: (pair[0], pair[1]))
    domestic_ordinal = {wid: index + 1 for index, (_, wid) in enumerate(domestic)}

    # Fee lines are processed in deterministic order. For several asserted bank
    # fees against one withdrawal, the allowed fee is allocated once; every later
    # line is a duplicate/overcharge to the extent it exceeds remaining allowance.
    allocated = defaultdict(lambda: ZERO)
    ordered_fees = sorted(fees, key=lambda r: (str(r.get("date")), str(r.get("transaction_id"))))
    supported_total = ZERO
    for fee in ordered_fees:
        fee_id = str(fee.get("transaction_id"))
        base = result_base(account_id, fee, kind)
        try:
            actual = abs(monetary(fee.get("amount")))
            base["actual_fee"] = text(actual)
        except ValueError:
            base.update({"assessment": "unassessable", "reason": "invalid fee amount"})
            output.append(base)
            continue
        context = contexts.get(fee_id, {})
        if not isinstance(context, dict):
            context = {}
        component = context.get("fee_component") or infer_component(fee)
        if component == "operator_fee":
            base.update({"assessment": "operator_fee_not_bank_fee", "reason": "verified operator fee is separate from bank ATM fee"})
            output.append(base)
            continue
        if component != "bank_fee":
            base.update({"assessment": "unassessable", "reason": "fee component is not established; provide fee_context"})
            output.append(base)
            continue
        withdrawal = fee_withdrawal.get(fee_id)
        if withdrawal is None:
            base.update({"assessment": "unassessable", "reason": "no unambiguous matching ATM withdrawal; provide withdrawal_transaction_id"})
            output.append(base)
            continue
        wid = str(withdrawal.get("transaction_id"))
        classification = context.get("withdrawal_classification") or classify_description(withdrawal)
        if classification is None and wid in linked_non_rho:
            classification = "domestic_out_of_network"
        if classification not in ("in_network", "domestic_out_of_network", "foreign"):
            base.update({"assessment": "unassessable", "reason": "withdrawal classification is not established; provide fee_context"})
            output.append(base)
            continue
        try:
            withdrawal_amount = abs(monetary(withdrawal.get("amount")))
            full_allowed = allowed_fee(kind, classification, withdrawal_amount, domestic_ordinal.get(wid))
        except ValueError as exc:
            base.update({"assessment": "unassessable", "reason": str(exc)})
            output.append(base)
            continue
        remaining_allowed = max(ZERO, full_allowed - allocated[wid])
        allowed_on_line = min(actual, remaining_allowed)
        allocated[wid] += allowed_on_line
        overcharge = actual - allowed_on_line
        base.update({"withdrawal_transaction_id": wid, "withdrawal_amount": text(withdrawal_amount),
                     "withdrawal_classification": classification, "expected_bank_fee_for_withdrawal": text(full_allowed),
                     "allowed_fee_allocated_to_line": text(allowed_on_line),
                     "overcharge_before_prior_correction": text(overcharge)})
        prior = ZERO
        if fee_id in corrections:
            prior_value = corrections[fee_id]
            try:
                prior = monetary(prior_value.get("amount", ZERO)) if isinstance(prior_value, dict) else monetary(prior_value)
            except ValueError:
                base.update({"assessment": "unassessable", "reason": "invalid verified prior correction amount"})
                output.append(base)
                continue
        unresolved = max(ZERO, overcharge - prior)
        base["verified_prior_correction"] = text(prior)
        base["unresolved_overcharge"] = text(unresolved)
        if fee.get("status") != "posted":
            base.update({"assessment": "pending_overcharge", "reason": "do not correct until the fee is posted"})
        elif unresolved > ZERO:
            base["assessment"] = "supported_bank_fee_overcharge"
            candidates.append({"account_id": account_id, "fee_transaction_id": fee_id,
                               "amount": text(unresolved), "credit_type": "fee_refund"})
            supported_total += unresolved
        elif overcharge > ZERO:
            base["assessment"] = "already_corrected"
        else:
            base["assessment"] = "matches_documented_fee"
        output.append(base)
    summary["supported_overcharge"] = text(supported_total)
    if kind == "light_green":
        summary["light_green_domestic_out_of_network_withdrawal_count"] = len(domestic)
    return summary, output, candidates


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    month = payload.get("review_month")
    try:
        datetime.strptime(str(month), "%Y-%m")
    except ValueError:
        return {"validation_errors": ["review_month must be YYYY-MM"], "fee_results": [], "credit_candidates": [], "combined_credit_candidates": []}
    accounts = payload.get("accounts")
    histories = payload.get("transactions_by_account")
    contexts = payload.get("fee_context", {})
    corrections = payload.get("correction_by_fee_id", {})
    if not isinstance(accounts, list) or not isinstance(histories, dict):
        return {"validation_errors": ["accounts must be an array and transactions_by_account must be an object"], "fee_results": [], "credit_candidates": [], "combined_credit_candidates": []}
    if not isinstance(contexts, dict) or not isinstance(corrections, dict):
        return {"validation_errors": ["fee_context and correction_by_fee_id must be objects"], "fee_results": [], "credit_candidates": [], "combined_credit_candidates": []}

    errors = []
    summaries, all_results, all_candidates = [], [], []
    for account in accounts:
        if not isinstance(account, dict) or not account.get("account_id"):
            errors.append("each account must be an object with account_id")
            continue
        aid = account["account_id"]
        records = histories.get(aid)
        if not isinstance(records, list):
            errors.append("missing transaction array for account %s" % aid)
            continue
        summary, results, candidates = audit_account(account, records, month, contexts, corrections, errors)
        summaries.append(summary)
        all_results.extend(results)
        all_candidates.extend(candidates)

    totals = defaultdict(lambda: ZERO)
    for candidate in all_candidates:
        totals[candidate["account_id"]] += monetary(candidate["amount"])
    combined = [{"account_id": aid, "amount": text(amount), "credit_type": "fee_refund",
                 "notice": "Calculation candidate only. Confirm prior credits, cooldown, eligibility, and immediate customer authorization before one credit call."}
                for aid, amount in sorted(totals.items()) if amount > ZERO]
    unresolved = {"unassessable", "pending_overcharge"}
    return {"review_month": month, "validation_errors": errors, "account_summaries": summaries,
            "fee_results": all_results, "credit_candidates": all_candidates,
            "combined_credit_candidates": combined,
            "manual_review_required": bool(errors) or any(r.get("assessment") in unresolved for r in all_results)}


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"validation_errors": [str(exc)], "fee_results": [], "credit_candidates": [], "combined_credit_candidates": []}, sort_keys=True))
