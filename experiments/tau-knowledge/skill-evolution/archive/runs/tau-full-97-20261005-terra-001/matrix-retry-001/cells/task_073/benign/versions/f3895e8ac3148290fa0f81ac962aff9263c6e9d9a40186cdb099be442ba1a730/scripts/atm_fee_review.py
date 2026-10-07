#!/usr/bin/env python3
"""Calculate evidence-backed ATM-fee refund candidates from JSON stdin."""
import json
import sys
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

CENT = Decimal("0.01")
PRODUCTS = {"blue", "green", "light_green"}
LIMITS = {
    "blue": Decimal("500"),
    "green": Decimal("600"),
    "light_green": Decimal("150"),
}


class InputError(Exception):
    pass


def money(value, field):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise InputError(f"{field} must be a decimal amount")
    if not result.is_finite():
        raise InputError(f"{field} must be finite")
    return result.quantize(CENT, rounding=ROUND_HALF_UP)


def fmt(value):
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def parse_date(value, field):
    text = str(value)
    for pattern in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            pass
    raise InputError(f"{field} must be MM/DD/YYYY or YYYY-MM-DD")


def require_dict(value, field):
    if not isinstance(value, dict):
        raise InputError(f"{field} must be an object")
    return value


def expected_fee(product, withdrawal, light_domestic_count):
    """Return expected fee, updated Light Green allowance count, and issue."""
    location = withdrawal["location"]
    amount = withdrawal["amount"]
    if location == "unknown":
        return None, light_domestic_count, "withdrawal location is unknown"
    if location == "foreign":
        if product in ("blue", "green"):
            return (
                max(amount * Decimal("0.03"), Decimal("5.00")).quantize(CENT),
                light_domestic_count,
                None,
            )
        if amount <= Decimal("100"):
            return Decimal("2.00"), light_domestic_count, None
        if amount <= Decimal("300"):
            return Decimal("3.50"), light_domestic_count, None
        return Decimal("5.00"), light_domestic_count, None

    # Domestic withdrawal.
    if withdrawal["out_of_network"] is None:
        return None, light_domestic_count, "domestic network status is unknown"
    if not withdrawal["out_of_network"]:
        return Decimal("0.00"), light_domestic_count, None
    if product == "blue":
        return min(amount * Decimal("0.01"), Decimal("3.00")).quantize(CENT), light_domestic_count, None
    if product == "green":
        return Decimal("3.00"), light_domestic_count, None
    light_domestic_count += 1
    return (
        Decimal("0.00") if light_domestic_count <= 4 else Decimal("1.50"),
        light_domestic_count,
        None,
    )


def main(payload):
    if not isinstance(payload, dict):
        raise InputError("input must be a JSON object")

    account = require_dict(payload.get("account"), "account")
    account_id = str(account.get("account_id", "")).strip()
    product = str(account.get("product", "")).strip().lower().replace(" ", "_").replace("-", "_")
    if not account_id:
        raise InputError("account.account_id is required")
    if product not in PRODUCTS:
        raise InputError("account.product must be blue, green, or light_green")
    try:
        review_month = datetime.strptime(str(payload.get("review_month", "")), "%Y-%m").strftime("%Y-%m")
    except ValueError:
        raise InputError("review_month must be YYYY-MM")
    if not isinstance(payload.get("coverage_complete"), bool):
        raise InputError("coverage_complete must be true or false")

    raw_withdrawals = payload.get("withdrawals")
    raw_fees = payload.get("fees")
    if not isinstance(raw_withdrawals, list) or not isinstance(raw_fees, list):
        raise InputError("withdrawals and fees must be arrays")

    fees = {}
    for index, raw in enumerate(raw_fees):
        item = require_dict(raw, f"fees[{index}]")
        tid = str(item.get("transaction_id", "")).strip()
        if not tid or tid in fees:
            raise InputError("each fee requires a unique transaction_id")
        date = parse_date(item.get("date"), f"fees[{index}].date")
        if date.strftime("%Y-%m") != review_month:
            raise InputError(f"fee {tid} is outside review_month")
        status = item.get("status")
        kind = item.get("kind")
        if status not in ("posted", "pending"):
            raise InputError(f"fees[{index}].status must be posted or pending")
        if kind not in ("bank", "operator", "unknown"):
            raise InputError(f"fees[{index}].kind must be bank, operator, or unknown")
        debit = money(item.get("amount"), f"fees[{index}].amount")
        if debit > 0:
            raise InputError(f"fees[{index}].amount must be a zero or negative debit")
        fees[tid] = {
            "transaction_id": tid,
            "date": date,
            "status": status,
            "kind": kind,
            "charge": abs(debit),
        }

    withdrawals = []
    seen_withdrawals = set()
    for index, raw in enumerate(raw_withdrawals):
        item = require_dict(raw, f"withdrawals[{index}]")
        tid = str(item.get("transaction_id", "")).strip()
        if not tid or tid in seen_withdrawals:
            raise InputError("each withdrawal requires a unique transaction_id")
        seen_withdrawals.add(tid)
        date = parse_date(item.get("date"), f"withdrawals[{index}].date")
        if date.strftime("%Y-%m") != review_month:
            raise InputError(f"withdrawal {tid} is outside review_month")
        status = item.get("status")
        location = item.get("location")
        if status not in ("posted", "pending"):
            raise InputError(f"withdrawals[{index}].status must be posted or pending")
        if location not in ("domestic", "foreign", "unknown"):
            raise InputError(f"withdrawals[{index}].location must be domestic, foreign, or unknown")
        out_of_network = item.get("out_of_network")
        if out_of_network not in (True, False, None):
            raise InputError(f"withdrawals[{index}].out_of_network must be true, false, or null")
        amount = money(item.get("amount"), f"withdrawals[{index}].amount")
        if amount <= 0:
            raise InputError(f"withdrawals[{index}].amount must be positive")
        fee_ids = item.get("fee_transaction_ids", [])
        if not isinstance(fee_ids, list) or any(not isinstance(value, str) for value in fee_ids):
            raise InputError(f"withdrawals[{index}].fee_transaction_ids must be an array of strings")
        if len(set(fee_ids)) != len(fee_ids):
            raise InputError(f"withdrawal {tid} repeats a fee transaction ID")
        withdrawals.append({
            "transaction_id": tid,
            "date": date,
            "status": status,
            "location": location,
            "out_of_network": out_of_network,
            "amount": amount,
            "fee_ids": fee_ids,
        })

    withdrawals.sort(key=lambda item: (item["date"], item["transaction_id"]))
    used_fee_ids = set()
    unresolved = []
    assessments = []
    pending_withdrawals = []
    daily_totals = {}
    light_count = 0
    refund_total = Decimal("0.00")

    for withdrawal in withdrawals:
        for fee_id in withdrawal["fee_ids"]:
            if fee_id not in fees:
                unresolved.append(f"{withdrawal['transaction_id']}: referenced fee {fee_id} was not supplied")
            elif fee_id in used_fee_ids:
                unresolved.append(f"fee {fee_id} is associated with more than one withdrawal")
            else:
                used_fee_ids.add(fee_id)

        associated = [fees[fee_id] for fee_id in withdrawal["fee_ids"] if fee_id in fees]
        if withdrawal["status"] != "posted":
            pending_withdrawals.append(withdrawal["transaction_id"])
            if any(fee["kind"] in ("bank", "unknown") for fee in associated):
                unresolved.append(f"{withdrawal['transaction_id']}: associated bank-fee evidence has a pending withdrawal")
            continue

        daily_totals[withdrawal["date"]] = daily_totals.get(withdrawal["date"], Decimal("0.00")) + withdrawal["amount"]
        if any(fee["kind"] == "unknown" for fee in associated):
            unresolved.append(f"{withdrawal['transaction_id']}: an associated fee has unknown ownership")
        if any(fee["kind"] == "bank" and fee["status"] != "posted" for fee in associated):
            unresolved.append(f"{withdrawal['transaction_id']}: an associated bank fee is pending")

        actual = sum(
            (fee["charge"] for fee in associated if fee["kind"] == "bank" and fee["status"] == "posted"),
            Decimal("0.00"),
        )
        expected, light_count, issue = expected_fee(product, withdrawal, light_count)
        if issue:
            unresolved.append(f"{withdrawal['transaction_id']}: {issue}")
            assessments.append({
                "withdrawal_id": withdrawal["transaction_id"],
                "date": withdrawal["date"].isoformat(),
                "expected_bank_fee": None,
                "actual_bank_fee": fmt(actual),
                "difference": None,
                "refund_component": None,
                "status": "unresolved",
            })
            continue

        difference = (actual - expected).quantize(CENT)
        # A missing or low charge is not a customer refund and must not offset
        # an independently documented overcharge on this account.
        refund_component = max(difference, Decimal("0.00"))
        refund_total += refund_component
        assessments.append({
            "withdrawal_id": withdrawal["transaction_id"],
            "date": withdrawal["date"].isoformat(),
            "expected_bank_fee": fmt(expected),
            "actual_bank_fee": fmt(actual),
            "difference": fmt(difference),
            "refund_component": fmt(refund_component),
            "status": "assessed",
        })

    unmatched = sorted(
        tid for tid, fee in fees.items()
        if fee["kind"] in ("bank", "unknown") and tid not in used_fee_ids
    )
    for tid in unmatched:
        unresolved.append(f"fee {tid} is not associated with a withdrawal")
    if not payload["coverage_complete"]:
        unresolved.append("coverage_complete is false; the extracted month is not confirmed complete")

    daily_observations = []
    for date, total in sorted(daily_totals.items()):
        if total > LIMITS[product]:
            daily_observations.append({
                "date": date.isoformat(),
                "total_withdrawn": fmt(total),
                "limit": fmt(LIMITS[product]),
                "note": "Limit observation only; not a fee-refund calculation.",
            })

    eligible = bool(assessments) and not unresolved and refund_total > 0
    return {
        "ok": True,
        "account_id": account_id,
        "product": product,
        "review_month": review_month,
        "assessments": assessments,
        "pending_withdrawal_ids": pending_withdrawals,
        "unmatched_fee_ids": unmatched,
        "unresolved": unresolved,
        "daily_limit_observations": daily_observations,
        "refund_total": fmt(refund_total),
        "candidate_credit": {
            "amount": fmt(refund_total),
            "credit_type": "fee_refund",
            "eligible_for_submission": eligible,
            "note": "Candidate equals documented posted overcharges only and requires independent identity, checking-account, transaction-evidence, and one-credit-per-account checks.",
        },
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), sort_keys=True))
    except (InputError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
