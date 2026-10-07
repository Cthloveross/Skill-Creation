#!/usr/bin/env python3
"""Offline ATM-limit eligibility evaluator.

Reads one JSON object from stdin and writes one JSON object to stdout. No bank
records are read and no bank action is performed.

Required for a conclusive decision: card.status, card.daily_atm_limit,
card.daily_atm_used, card.temporary_increase_last_24h, account.status,
account.age_days, requested_new_limit, today, and overdraft_fee_dates. To determine whether an increase can provide a particular cash amount, also supply requested_cash_amount.
Dates use YYYY-MM-DD. overdraft_fee_dates contains only actual overdraft-fee
posting dates relevant to the linked account.
"""
import json
import sys
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation


def as_money(value, field, missing):
    if value is None:
        missing.append(field)
        return None
    try:
        result = Decimal(str(value))
        if result < 0:
            raise InvalidOperation
        return result
    except (InvalidOperation, ValueError):
        missing.append(field + " (must be a non-negative number)")
        return None


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": "invalid_json", "detail": str(exc)}))
        return
    if not isinstance(payload, dict):
        print(json.dumps({"error": "input_must_be_object"}))
        return

    card = payload.get("card") if isinstance(payload.get("card"), dict) else {}
    account = payload.get("account") if isinstance(payload.get("account"), dict) else {}
    missing = []
    status = card.get("status")
    account_status = account.get("status")
    if status is None:
        missing.append("card.status")
    if account_status is None:
        missing.append("account.status")
    limit = as_money(card.get("daily_atm_limit"), "card.daily_atm_limit", missing)
    used = as_money(card.get("daily_atm_used"), "card.daily_atm_used", missing)
    requested = as_money(payload.get("requested_new_limit"), "requested_new_limit", missing)
    cash_request_missing = []
    cash_requested = as_money(payload.get("requested_cash_amount"), "requested_cash_amount", cash_request_missing)
    age = account.get("age_days")
    if not isinstance(age, (int, float)) or isinstance(age, bool):
        missing.append("account.age_days")
        age = None
    frequency = card.get("temporary_increase_last_24h")
    if not isinstance(frequency, bool):
        missing.append("card.temporary_increase_last_24h")
        frequency = None

    today_text = payload.get("today")
    try:
        today = date.fromisoformat(today_text)
    except (TypeError, ValueError):
        missing.append("today (YYYY-MM-DD)")
        today = None
    fee_dates = payload.get("overdraft_fee_dates")
    parsed_fees = []
    if not isinstance(fee_dates, list):
        missing.append("overdraft_fee_dates")
    else:
        for index, text in enumerate(fee_dates):
            try:
                parsed_fees.append(date.fromisoformat(text))
            except (TypeError, ValueError):
                missing.append("overdraft_fee_dates[%d] (YYYY-MM-DD)" % index)

    remaining = None
    required_new_limit_for_cash = None
    can_cover_requested_cash_with_requested_limit = None
    if limit is not None and used is not None:
        remaining = max(Decimal("0"), limit - used)
    if used is not None and cash_requested is not None:
        # The tool's new_limit is a total daily limit, not an extra allowance.
        required_new_limit_for_cash = used + cash_requested
    if requested is not None and required_new_limit_for_cash is not None:
        can_cover_requested_cash_with_requested_limit = requested >= required_new_limit_for_cash
    checks = {
        "active_card": None if status is None else str(status).upper() == "ACTIVE",
        "open_account": None if account_status is None else str(account_status).upper() == "OPEN",
        "account_age_at_least_60_days": None if age is None else age >= 60,
        "no_prior_temporary_increase_in_24h": None if frequency is None else not frequency,
        "within_150_percent_of_current_limit": None if limit is None or requested is None else requested <= limit * Decimal("1.5"),
        "no_overdraft_fee_in_prior_30_days": None,
    }
    if today is not None and isinstance(fee_dates, list) and not any(x.startswith("overdraft_fee_dates[") for x in missing):
        start = today - timedelta(days=30)
        checks["no_overdraft_fee_in_prior_30_days"] = not any(start <= entry <= today for entry in parsed_fees)

    conclusive = not missing
    eligible = conclusive and all(checks.values())
    blockers = [name for name, value in checks.items() if value is False]
    recommendations = []
    if missing:
        recommendations.append("Retrieve the listed missing eligibility evidence before requesting an increase.")
    if blockers:
        recommendations.append("Do not submit a temporary limit-increase request while any listed eligibility check fails.")
    if remaining is not None:
        recommendations.append("Confirm available funds and any security, PIN, account, or ATM-operator restriction separately; remaining limit alone does not guarantee cash access.")
    if required_new_limit_for_cash is not None and limit is not None and required_new_limit_for_cash > limit * Decimal("1.5"):
        recommendations.append("The requested cash cannot be made available today by a temporary increase alone because the needed total daily limit exceeds the 150% ceiling.")
    elif can_cover_requested_cash_with_requested_limit is False:
        recommendations.append("The proposed new daily limit is too low to cover the amount already withdrawn plus the requested cash amount.")
    if eligible and can_cover_requested_cash_with_requested_limit is not False:
        recommendations.append("After identity verification and explicit customer authorization, the ATM increase may be submitted for the requested new daily limit.")
    elif eligible and can_cover_requested_cash_with_requested_limit is False:
        recommendations.append("Although the base eligibility checks pass, do not submit this proposed limit as a solution for the requested cash amount.")

    result = {
        "temporary_increase_eligible": eligible,
        "conclusive": conclusive,
        "eligibility_checks": checks,
        "missing_evidence": missing,
        "failed_checks": blockers,
        "current_atm_limit": None if limit is None else str(limit),
        "atm_used_today": None if used is None else str(used),
        "remaining_atm_capacity": None if remaining is None else str(remaining),
        "maximum_permitted_temporary_limit": None if limit is None else str(limit * Decimal("1.5")),
        "requested_cash_amount": None if cash_requested is None else str(cash_requested),
        "minimum_new_daily_limit_for_requested_cash": None if required_new_limit_for_cash is None else str(required_new_limit_for_cash),
        "proposed_limit_covers_requested_cash": can_cover_requested_cash_with_requested_limit,
        "recommendations": recommendations,
        "note": "This offline result is not a bank action and does not override external ATM, balance, PIN, fraud, velocity, or account restrictions."
    }
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
