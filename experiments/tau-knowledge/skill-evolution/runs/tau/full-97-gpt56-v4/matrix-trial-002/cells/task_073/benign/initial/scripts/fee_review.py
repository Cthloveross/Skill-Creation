#!/usr/bin/env python3
"""Deterministic ATM bank-fee schedule analyzer.

Reads one JSON object from stdin and writes one JSON object to stdout.  This
helper analyzes bank fees only; it never accesses accounts or recommends an
automatic banking action.
"""
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from datetime import datetime

CENT = Decimal("0.01")
ZERO = Decimal("0")


def money(value, field):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be a decimal amount")
    if not amount.is_finite() or amount < ZERO:
        raise ValueError(f"{field} must be a nonnegative finite amount")
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


def fmt(value):
    return format(value.quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def expected_fee(account_class, channel, withdrawal, domestic_index):
    """Return (fee or None, explanation). domestic_index is zero-based."""
    if account_class == "Blue":
        if channel == "domestic_out_of_network":
            return min(withdrawal * Decimal("0.01"), Decimal("3.00")).quantize(CENT, rounding=ROUND_HALF_UP), "1% of withdrawal, capped at $3.00"
        return max(withdrawal * Decimal("0.03"), Decimal("5.00")).quantize(CENT, rounding=ROUND_HALF_UP), "greater of 3% of USD-equivalent withdrawal or $5.00"
    if account_class == "Green":
        if channel == "domestic_out_of_network":
            return None, "unresolved: Green domestic schedules conflict in available documents ($3.00 versus four free then $1.50)"
        return max(withdrawal * Decimal("0.03"), Decimal("5.00")).quantize(CENT, rounding=ROUND_HALF_UP), "greater of 3% of USD-equivalent withdrawal or $5.00"
    # Light Green
    if channel == "domestic_out_of_network":
        if domestic_index < 4:
            return ZERO, "one of first four domestic out-of-network withdrawals in the month"
        return Decimal("1.50"), "domestic out-of-network withdrawal after four free monthly withdrawals"
    if withdrawal <= Decimal("100.00"):
        return Decimal("2.00"), "foreign withdrawal of $100.00 or less"
    if withdrawal <= Decimal("300.00"):
        return Decimal("3.50"), "foreign withdrawal above $100.00 through $300.00"
    return Decimal("5.00"), "foreign withdrawal above $300.00"


def main(payload):
    account_class = payload.get("account_class")
    if account_class not in {"Blue", "Green", "Light Green"}:
        raise ValueError("account_class must be Blue, Green, or Light Green")
    events = payload.get("events")
    if not isinstance(events, list):
        raise ValueError("events must be a list")
    prior = payload.get("prior_month_domestic_withdrawals", 0)
    if not isinstance(prior, int) or prior < 0:
        raise ValueError("prior_month_domestic_withdrawals must be a nonnegative integer")

    domestic_count = prior
    analyzed = []
    supportable_overcharge = ZERO
    unresolved_count = 0
    for index, event in enumerate(events):
        if not isinstance(event, dict):
            raise ValueError(f"events[{index}] must be an object")
        channel = event.get("channel")
        if channel not in {"domestic_out_of_network", "foreign"}:
            raise ValueError(f"events[{index}].channel is unsupported")
        status = event.get("status")
        if status not in {"posted", "pending"}:
            raise ValueError(f"events[{index}].status must be posted or pending")
        date = event.get("date")
        try:
            datetime.strptime(date, "%m/%d/%Y")
        except (TypeError, ValueError):
            raise ValueError(f"events[{index}].date must be MM/DD/YYYY")
        withdrawal = money(event.get("withdrawal_amount"), f"events[{index}].withdrawal_amount")
        actual = money(event.get("bank_fee"), f"events[{index}].bank_fee")
        operator = money(event.get("operator_fee", "0"), f"events[{index}].operator_fee")
        domestic_index = domestic_count
        if channel == "domestic_out_of_network" and status == "posted":
            domestic_count += 1
        expected, rationale = expected_fee(account_class, channel, withdrawal, domestic_index)
        item = {
            "index": index,
            "date": date,
            "channel": channel,
            "status": status,
            "withdrawal_amount": fmt(withdrawal),
            "actual_bank_fee": fmt(actual),
            "operator_fee_not_in_bank_fee_test": fmt(operator),
            "rationale": rationale,
        }
        if expected is None:
            item["expected_bank_fee"] = None
            item["discrepancy"] = None
            item["requires_authoritative_review"] = True
            unresolved_count += 1
        elif status == "pending":
            item["expected_bank_fee"] = fmt(expected)
            item["discrepancy"] = None
            item["requires_authoritative_review"] = False
            item["not_credit_eligible_yet"] = True
        else:
            discrepancy = (actual - expected).quantize(CENT, rounding=ROUND_HALF_UP)
            item["expected_bank_fee"] = fmt(expected)
            item["discrepancy"] = fmt(discrepancy)
            item["requires_authoritative_review"] = False
            if discrepancy > ZERO:
                supportable_overcharge += discrepancy
        analyzed.append(item)
    return {
        "account_class": account_class,
        "events": analyzed,
        "supportable_bank_fee_overcharge": fmt(supportable_overcharge),
        "unresolved_policy_event_count": unresolved_count,
        "note": "A positive total is only a schedule comparison. Confirm transaction pairing, duplicate credits, account eligibility, and credit cooldown before any bank action. Operator-fee reimbursement eligibility is not calculated here.",
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), separators=(",", ":")))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
