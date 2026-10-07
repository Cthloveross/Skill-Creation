#!/usr/bin/env python3
"""Deterministic checking-referral eligibility and comparison helper.

Reads one JSON request from stdin and writes a JSON assessment to stdout.
This helper is advisory only: it never calls banking systems or creates referrals.
"""
import json
import sys
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

PROGRAMS = (
    {"account_type": "Blue Account", "referrer_bonus": "35", "recipient_bonus": "30", "annual_cap": 5, "deposit": "500", "deposit_days": 60, "tenure_days": 30, "min_age": 18},
    {"account_type": "Green Fee-Free Account", "referrer_bonus": "20", "recipient_bonus": "35", "annual_cap": 4, "deposit": "300", "deposit_days": 60, "tenure_days": 30, "min_age": 18},
    {"account_type": "Light Blue Account", "referrer_bonus": "30", "recipient_bonus": "20", "annual_cap": 5, "deposit": "500", "deposit_days": 60, "tenure_days": 30, "min_age": 18},
    {"account_type": "Green Account", "referrer_bonus": "20", "recipient_bonus": "30", "annual_cap": 5, "deposit": "500", "deposit_days": 60, "tenure_days": 30, "min_age": 18},
    {"account_type": "Light Green Account", "referrer_bonus": "15", "recipient_bonus": "25", "annual_cap": 3, "deposit": "100", "deposit_days": 90, "tenure_days": 14, "min_age": 13, "max_age": 24, "minor_guardian_required": True},
    {"account_type": "Dark Green Account", "referrer_bonus": "40", "recipient_bonus": "30", "annual_cap": 6, "deposit": "1000", "deposit_days": 60, "tenure_days": 45, "min_age": 18},
    {"account_type": "Bluest Account", "referrer_bonus": "75", "recipient_bonus": "50", "annual_cap": 8, "deposit": "2000", "deposit_days": 90, "tenure_days": 60, "min_age": 18},
    {"account_type": "Gold Years Account", "referrer_bonus": "50", "recipient_bonus": "75", "annual_cap": 6, "deposit": "1000", "deposit_days": 90, "tenure_days": 30, "min_age": 62},
    {"account_type": "Evergreen Account", "referrer_bonus": "35", "recipient_bonus": "25", "annual_cap": 6, "deposit": "750", "deposit_days": 60, "tenure_days": 45, "min_age": 18},
)


def parse_as_of(value):
    if not isinstance(value, str):
        raise ValueError("as_of must be an ISO-8601 timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("as_of must include a UTC offset")
    return parsed


def parse_open_date(value):
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def decimal_amount(value):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return amount if amount >= 0 else None


def event_in_window(event, now):
    """Return (in_window, needs_exact_timestamp)."""
    value = event.get("bonus_received_at")
    if not isinstance(value, str):
        return False, True
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if stamp.tzinfo is not None:
            return stamp >= now - timedelta(days=9), False
    except ValueError:
        pass
    try:
        event_day = date.fromisoformat(value)
    except ValueError:
        return False, True
    # A date more than nine full calendar days earlier is safely outside.
    if (now.date() - event_day).days > 9:
        return False, False
    return False, True


def same_calendar_year(event, now):
    value = event.get("bonus_received_at")
    if not isinstance(value, str):
        return False
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).year == now.year
    except ValueError:
        try:
            return date.fromisoformat(value).year == now.year
        except ValueError:
            return False


def blocked(missing, rolling_count=0, rolling_uncertain=False):
    missing = list(dict.fromkeys(missing))
    return {
        "review_status": "blocked",
        "missing_confirmations": missing,
        "rolling_window": {
            "complete_bonus_count": rolling_count,
            "cap": 2,
            "eligible_for_another_bonus_now": None if rolling_uncertain else rolling_count < 2,
            "exact_timestamp_needed": rolling_uncertain,
        },
        "candidate_ranking": [],
        "safe_user_message": (
            "I can’t recommend a referral account or discuss program terms yet because "
            "required referral-eligibility details have not been confirmed. Please provide "
            "the requested confirmations, and I can reassess eligibility."
        ),
    }


def main(payload):
    now = parse_as_of(payload.get("as_of"))
    referrer = payload.get("referrer") if isinstance(payload.get("referrer"), dict) else {}
    recipient = payload.get("recipient") if isinstance(payload.get("recipient"), dict) else {}
    deposit_info = payload.get("deposit") if isinstance(payload.get("deposit"), dict) else {}
    history = referrer.get("referrals")
    missing = []

    if payload.get("identity_verified") is not True:
        missing.append("verified referrer identity and authority")
    opened = parse_open_date(referrer.get("first_checking_opened"))
    if opened is None:
        missing.append("exact first Rho-Bank checking-account opening date")
    if referrer.get("referral_history_complete") is not True or not isinstance(history, list):
        missing.append("complete referrer referral history")
        history = []
    if not isinstance(recipient.get("age"), int):
        missing.append("prospective customer's age")
    if recipient.get("new_customer_confirmed") is not True:
        missing.append("confirmation that the prospective customer has no current or recently closed Rho-Bank account")
    if recipient.get("different_registered_address_confirmed") is not True:
        missing.append("confirmation of different registered addresses")
    if recipient.get("no_conflicting_promotion_confirmed") is not True:
        missing.append("confirmation that no conflicting new-account promotion will be used")
    amount = decimal_amount(deposit_info.get("amount"))
    if amount is None:
        missing.append("anticipated qualifying-deposit amount")
    if deposit_info.get("new_money_confirmed") is not True:
        missing.append("confirmation that the deposit is new money")

    rolling_count = 0
    rolling_uncertain = False
    for event in history:
        if not isinstance(event, dict) or event.get("status") != "COMPLETE":
            continue
        inside, uncertain = event_in_window(event, now)
        rolling_count += int(inside)
        rolling_uncertain = rolling_uncertain or uncertain
    if rolling_uncertain:
        missing.append("exact timestamps for recent complete referral bonuses")
    if rolling_count >= 2:
        missing.append("rolling nine-day referral-bonus capacity")

    if missing:
        return blocked(missing, rolling_count, rolling_uncertain)

    age = recipient["age"]
    tenure_days = (now.date() - opened).days
    candidates = []
    for program in PROGRAMS:
        reasons = []
        if tenure_days < program["tenure_days"]:
            reasons.append("referrer tenure")
        if amount < Decimal(program["deposit"]):
            reasons.append("deposit amount")
        if age < program["min_age"] or ("max_age" in program and age > program["max_age"]):
            reasons.append("recipient age/product eligibility")
        if program.get("minor_guardian_required") and age < 18 and recipient.get("minor_guardian_confirmed") is not True:
            reasons.append("minor guardian requirement")
        annual_complete = sum(
            1 for event in history
            if isinstance(event, dict)
            and event.get("status") == "COMPLETE"
            and event.get("account_type") == program["account_type"]
            and same_calendar_year(event, now)
        )
        if annual_complete >= program["annual_cap"]:
            reasons.append("annual program cap")
        if reasons:
            continue
        ref_bonus = Decimal(program["referrer_bonus"])
        member_bonus = Decimal(program["recipient_bonus"])
        candidates.append({
            "account_type": program["account_type"],
            "combined_bonus": f"{ref_bonus + member_bonus:.2f}",
            "referrer_bonus": f"{ref_bonus:.2f}",
            "recipient_bonus": f"{member_bonus:.2f}",
            "qualifying_deposit": f"{Decimal(program['deposit']):.2f}",
            "deposit_deadline_days": program["deposit_days"],
            "required_referrer_tenure_days": program["tenure_days"],
            "annual_cap": program["annual_cap"],
        })
    candidates.sort(key=lambda item: (Decimal(item["combined_bonus"]), item["account_type"]), reverse=True)
    if not candidates:
        return {
            "review_status": "no_qualifying_program",
            "missing_confirmations": [],
            "rolling_window": {"complete_bonus_count": rolling_count, "cap": 2, "eligible_for_another_bonus_now": True, "exact_timestamp_needed": False},
            "candidate_ranking": [],
            "safe_user_message": "Based on the confirmed facts, no listed checking referral program currently qualifies. Do not submit a referral based on this review.",
        }
    return {
        "review_status": "ready",
        "missing_confirmations": [],
        "rolling_window": {"complete_bonus_count": rolling_count, "cap": 2, "eligible_for_another_bonus_now": True, "exact_timestamp_needed": False},
        "candidate_ranking": candidates,
        "safe_user_message": "The ranking is conditional on the verified information and program requirements. Before submitting a referral, re-check current eligibility, promotion conflicts, annual limits, and the rolling nine-day limit.",
    }


if __name__ == "__main__":
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(request), sort_keys=True))
    except (ValueError, TypeError) as exc:
        print(json.dumps({"review_status": "error", "error": str(exc), "candidate_ranking": []}, sort_keys=True))
        sys.exit(2)
