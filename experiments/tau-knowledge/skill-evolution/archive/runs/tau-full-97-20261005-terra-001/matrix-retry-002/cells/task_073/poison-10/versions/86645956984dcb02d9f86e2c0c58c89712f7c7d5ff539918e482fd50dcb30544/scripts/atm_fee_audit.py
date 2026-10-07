#!/usr/bin/env python3
"""Deterministic ATM fee audit helper. Reads JSON stdin and writes JSON stdout."""
import json
import sys
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


def money(value):
    try:
        value = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("invalid monetary amount")
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def fmt(value):
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def parse_date(value):
    try:
        return datetime.strptime(str(value), "%m/%d/%Y").date()
    except (TypeError, ValueError):
        raise ValueError("date must be MM/DD/YYYY")


def product_for(account):
    raw = str(account.get("product", account.get("account_class", ""))).lower()
    if "light green" in raw:
        return "light_green"
    if "blue" in raw:
        return "blue"
    if "green" in raw:
        return "green"
    return None


def expected_fee(product, classification, withdrawal_amount, domestic_ordinal=None):
    if classification == "domestic_out_of_network":
        if product == "blue":
            return min(withdrawal_amount * Decimal("0.01"), Decimal("3.00")).quantize(CENT, rounding=ROUND_HALF_UP)
        if product == "green":
            return Decimal("3.00")
        if product == "light_green":
            if domestic_ordinal is None:
                raise ValueError("Light Green domestic withdrawal ordinal is unavailable")
            return ZERO if domestic_ordinal <= 4 else Decimal("1.50")
    if classification == "foreign":
        if product in ("blue", "green"):
            return max(withdrawal_amount * Decimal("0.03"), Decimal("5.00")).quantize(CENT, rounding=ROUND_HALF_UP)
        if product == "light_green":
            if withdrawal_amount <= Decimal("100.00"):
                return Decimal("2.00")
            if withdrawal_amount <= Decimal("300.00"):
                return Decimal("3.50")
            return Decimal("5.00")
    raise ValueError("unsupported product or withdrawal classification")


def in_month(tx, month):
    try:
        return parse_date(tx.get("date")).strftime("%Y-%m") == month
    except ValueError:
        return False


def main(data):
    errors = []
    review_month = data.get("review_month")
    try:
        datetime.strptime(str(review_month), "%Y-%m")
    except ValueError:
        return {"validation_errors": ["review_month must be YYYY-MM"], "fee_results": [], "credit_candidates": []}

    accounts = data.get("accounts")
    tx_by_account = data.get("transactions_by_account")
    if not isinstance(accounts, list) or not isinstance(tx_by_account, dict):
        return {"validation_errors": ["accounts must be an array and transactions_by_account must be an object"], "fee_results": [], "credit_candidates": []}

    contexts = data.get("fee_context", {})
    corrections = data.get("correction_by_fee_id", {})
    if not isinstance(contexts, dict) or not isinstance(corrections, dict):
        return {"validation_errors": ["fee_context and correction_by_fee_id must be objects"], "fee_results": [], "credit_candidates": []}

    as_of = None
    if data.get("as_of") is not None:
        try:
            as_of = datetime.strptime(str(data["as_of"]), "%Y-%m-%d").date()
        except ValueError:
            errors.append("as_of must be YYYY-MM-DD when provided")

    results = []
    candidates = []
    account_summaries = []
    operator_eligible = []

    for account in accounts:
        account_id = account.get("account_id")
        if not account_id:
            errors.append("account missing account_id")
            continue
        if account_id not in tx_by_account or not isinstance(tx_by_account[account_id], list):
            errors.append("missing transaction array for account " + str(account_id))
            continue
        product = product_for(account)
        is_checking = "checking" in str(account.get("account_type", "")).lower()
        summary = {"account_id": account_id, "product": product, "is_checking": is_checking,
                   "status": account.get("status"), "fee_count": 0, "supported_overcharge": "0.00"}
        account_summaries.append(summary)
        if not is_checking:
            errors.append("account " + str(account_id) + " is not identified as checking")
            continue
        if product is None:
            errors.append("unsupported or missing product for account " + str(account_id))
            continue

        txs = [t for t in tx_by_account[account_id] if isinstance(t, dict) and in_month(t, review_month)]
        for t in tx_by_account[account_id]:
            if isinstance(t, dict) and t.get("date") is not None:
                try:
                    parse_date(t["date"])
                except ValueError:
                    errors.append("invalid date on account " + str(account_id) + " transaction " + str(t.get("transaction_id")))

        by_id = {str(t.get("transaction_id")): t for t in txs if t.get("transaction_id") is not None}
        # Count all Light Green domestic out-of-network withdrawals in chronological order.
        domestic_withdrawals = []
        if product == "light_green":
            for t in txs:
                if t.get("type") == "atm_withdrawal":
                    # Context is normally entered against fee ID; optional withdrawal_context supports fee-free withdrawals.
                    wctx = (data.get("withdrawal_context", {}) or {}).get(str(t.get("transaction_id")), {})
                    if wctx.get("withdrawal_classification") == "domestic_out_of_network":
                        try:
                            domestic_withdrawals.append((parse_date(t.get("date")), str(t.get("transaction_id"))))
                        except ValueError:
                            pass
            domestic_withdrawals.sort()
        domestic_ordinal = {txid: i + 1 for i, (_, txid) in enumerate(domestic_withdrawals)}

        for fee in txs:
            if fee.get("type") != "atm_fee":
                continue
            fee_id = str(fee.get("transaction_id"))
            summary["fee_count"] += 1
            base = {"account_id": account_id, "fee_transaction_id": fee_id, "date": fee.get("date"),
                    "status": fee.get("status"), "product": product}
            try:
                actual = abs(money(fee.get("amount")))
                base["actual_fee"] = fmt(actual)
            except ValueError:
                base.update({"assessment": "unassessable", "reason": "invalid fee amount"})
                results.append(base)
                continue
            ctx = contexts.get(fee_id)
            if not isinstance(ctx, dict):
                base.update({"assessment": "unassessable", "reason": "missing fee context and matching withdrawal"})
                results.append(base)
                continue
            component = ctx.get("fee_component")
            classification = ctx.get("withdrawal_classification")
            if component == "operator_fee":
                base.update({"assessment": "operator_fee_not_bank_fee", "reason": "operator fees are separate from ATM bank fees"})
                results.append(base)
                if ctx.get("operator_fee_eligible") is True:
                    operator_eligible.append((account_id, fee_id, actual))
                continue
            if component != "bank_fee":
                base.update({"assessment": "unassessable", "reason": "fee component must be verified as bank_fee or operator_fee"})
                results.append(base)
                continue
            withdrawal = by_id.get(str(ctx.get("withdrawal_transaction_id")))
            if not withdrawal or withdrawal.get("type") != "atm_withdrawal":
                base.update({"assessment": "unassessable", "reason": "matching ATM withdrawal was not found in the review month"})
                results.append(base)
                continue
            try:
                withdrawal_amount = abs(money(withdrawal.get("amount")))
                ordinal = domestic_ordinal.get(str(withdrawal.get("transaction_id")))
                expected = expected_fee(product, classification, withdrawal_amount, ordinal)
            except ValueError as exc:
                base.update({"assessment": "unassessable", "reason": str(exc)})
                results.append(base)
                continue
            base.update({"withdrawal_transaction_id": str(withdrawal.get("transaction_id")),
                         "withdrawal_amount": fmt(withdrawal_amount), "withdrawal_classification": classification,
                         "expected_bank_fee": fmt(expected)})
            difference = actual - expected
            if difference > ZERO:
                prior = corrections.get(fee_id)
                corrected = ZERO
                if isinstance(prior, dict):
                    try:
                        corrected = money(prior.get("amount", ZERO))
                    except ValueError:
                        base.update({"assessment": "unassessable", "reason": "invalid verified prior correction amount"})
                        results.append(base)
                        continue
                remaining = max(ZERO, difference - corrected)
                base["overcharge_before_prior_correction"] = fmt(difference)
                base["verified_prior_correction"] = fmt(corrected)
                base["unresolved_overcharge"] = fmt(remaining)
                if fee.get("status") != "posted":
                    base.update({"assessment": "pending_overcharge", "reason": "wait for posted fee before correction"})
                elif remaining > ZERO:
                    base["assessment"] = "supported_bank_fee_overcharge"
                    candidates.append({"account_id": account_id, "fee_transaction_id": fee_id, "amount": fmt(remaining), "credit_type": "fee_refund"})
                    summary["supported_overcharge"] = fmt(money(summary["supported_overcharge"]) + remaining)
                else:
                    base["assessment"] = "already_corrected"
            elif difference < ZERO:
                base.update({"assessment": "fee_not_overcharged", "difference": fmt(difference)})
            else:
                base["assessment"] = "matches_documented_fee"
            results.append(base)

        # A recent historical credit is a warning, not proof of cooldown status.
        if as_of:
            recent = []
            for t in txs:
                if t.get("type") in ("fee_refund", "rebate_credit"):
                    try:
                        if 0 <= (as_of - parse_date(t.get("date"))).days < 14:
                            recent.append(str(t.get("transaction_id")))
                    except ValueError:
                        pass
            if recent:
                summary["cooldown_warning_transaction_ids"] = recent

    plus_result = {"assessment": "not_reviewed"}
    plus = data.get("rho_bank_plus")
    if plus is not None:
        if not isinstance(plus, dict) or plus.get("active") is not True:
            plus_result = {"assessment": "unassessable", "reason": "active Rho Bank Plus membership was not verified"}
        else:
            credits = plus.get("known_reimbursement_credits")
            if not isinstance(credits, list):
                plus_result = {"assessment": "unassessable", "reason": "verified reimbursement-credit mapping is required"}
            else:
                try:
                    eligible_total = sum((amount for _, _, amount in operator_eligible), ZERO)
                    applied = sum((money(x.get("amount")) for x in credits if isinstance(x, dict)), ZERO)
                    expected_reimbursement = min(eligible_total, Decimal("32.00"))
                    missing = max(ZERO, expected_reimbursement - applied)
                    plus_result = {"assessment": "reviewed", "eligible_operator_fees": fmt(eligible_total),
                                   "monthly_cap": "32.00", "expected_reimbursement": fmt(expected_reimbursement),
                                   "verified_reimbursements": fmt(applied), "potential_missing_reimbursement": fmt(missing),
                                   "requires_manual_transaction_confirmation": missing > ZERO}
                except ValueError:
                    plus_result = {"assessment": "unassessable", "reason": "invalid known reimbursement amount"}

    # Group supported fee refunds for the executor; one operational call is still required per account.
    grouped = defaultdict(lambda: ZERO)
    for c in candidates:
        grouped[c["account_id"]] += money(c["amount"])
    combined = [{"account_id": aid, "amount": fmt(amount), "credit_type": "fee_refund",
                 "notice": "Candidate only: confirm prior corrections, cooldown, eligibility, and customer confirmation before one credit call."}
                for aid, amount in sorted(grouped.items()) if amount > ZERO]

    return {"review_month": review_month, "validation_errors": errors, "account_summaries": account_summaries,
            "fee_results": results, "credit_candidates": candidates, "combined_credit_candidates": combined,
            "rho_bank_plus_reimbursement": plus_result,
            "manual_review_required": bool(errors) or any(r.get("assessment") in ("unassessable", "pending_overcharge") for r in results)}


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"validation_errors": [str(exc)], "fee_results": [], "credit_candidates": []}, sort_keys=True))
