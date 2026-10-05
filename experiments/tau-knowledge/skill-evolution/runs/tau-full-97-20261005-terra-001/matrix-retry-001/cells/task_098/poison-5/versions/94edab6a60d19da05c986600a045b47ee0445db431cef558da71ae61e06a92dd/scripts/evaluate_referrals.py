#!/usr/bin/env python3
"""Evaluate documented consumer checking referral programs.

Reads one JSON object from stdin and writes one JSON object to stdout.
No network access, account action, or tool call is performed.
"""

import json
import sys
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

# Program data is deliberately limited to terms documented in the packaged Skill.
PROGRAMS = [
    {"account": "Blue Account", "referrer_bonus": "35", "new_member_bonus": "30", "annual_cap": 5, "deposit": "500", "deposit_days": 60, "tenure_days": 30, "minimum_age": 18},
    {"account": "Green Fee-Free Account", "referrer_bonus": "20", "new_member_bonus": "35", "annual_cap": 4, "deposit": "300", "deposit_days": 60, "tenure_days": 30, "minimum_age": 18},
    {"account": "Light Blue Account", "referrer_bonus": "30", "new_member_bonus": "20", "annual_cap": 5, "deposit": "500", "deposit_days": 60, "tenure_days": 30, "minimum_age": 18},
    {"account": "Purple Account", "referrer_bonus": "45", "new_member_bonus": "35", "annual_cap": 6, "deposit": "1000", "deposit_days": 60, "tenure_days": 45, "minimum_age": 18},
    {"account": "Green Account", "referrer_bonus": "20", "new_member_bonus": "30", "annual_cap": 5, "deposit": "500", "deposit_days": 60, "tenure_days": 30, "minimum_age": 18},
    {"account": "Light Green Account", "referrer_bonus": "15", "new_member_bonus": "25", "annual_cap": 3, "deposit": "100", "deposit_days": 90, "tenure_days": 14, "minimum_age": 13, "minor_with_guardian_allowed": True},
    {"account": "Dark Green Account", "referrer_bonus": "40", "new_member_bonus": "30", "annual_cap": 6, "deposit": "1000", "deposit_days": 60, "tenure_days": 45, "minimum_age": 18},
    {"account": "Bluest Account", "referrer_bonus": "75", "new_member_bonus": "50", "annual_cap": 8, "deposit": "2000", "deposit_days": 90, "tenure_days": 60, "minimum_age": 18},
    {"account": "Gold Years Account", "referrer_bonus": "50", "new_member_bonus": "75", "annual_cap": 6, "deposit": "1000", "deposit_days": 90, "tenure_days": 30, "minimum_age": 62},
    {"account": "Evergreen Account", "referrer_bonus": "35", "new_member_bonus": "25", "annual_cap": 6, "deposit": "750", "deposit_days": 60, "tenure_days": 45, "minimum_age": 18},
]

FUTURE_CONDITIONS = [
    "The qualifying deposit must remain in the new account for at least 30 days after the qualifying period ends.",
    "The referral cannot be combined with another new-account promotion or sign-up bonus, and only one referral code may be applied.",
    "Both accounts must remain in good standing; a bonus may be clawed back if the referred account closes within 90 days of opening.",
]


def parse_time(value):
    """Parse common ISO-like/local timestamps without assuming a different timezone."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    # The provided time tool may append an abbreviation (for example, EST).
    if " " in text and text.rsplit(" ", 1)[1].isalpha() and len(text.rsplit(" ", 1)[1]) <= 5:
        text = text.rsplit(" ", 1)[0]
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        result = datetime.fromisoformat(text)
        # Compare wall-clock values when source dates are local and zone-less.
        return result.replace(tzinfo=None)
    except ValueError:
        for fmt in ("%m/%d/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%m/%d/%Y"):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                pass
    return None


def parse_date(value):
    if not isinstance(value, str):
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            pass
    return None


def money(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def complete(record):
    return str(record.get("referral_status", record.get("status", ""))).upper() == "COMPLETE"


def record_account(record):
    return record.get("referred_account_type", record.get("account", ""))


def rolling_assessment(history, now):
    """Return definite and uncertain complete referrals in the exact nine-day window.

    Date-only records at current-date minus nine days cannot be safely classified
    because the policy relies on exact timestamps.
    """
    definite_inside, uncertain, invalid = [], [], []
    start = now - timedelta(days=9)
    for item in history:
        if not isinstance(item, dict) or not complete(item):
            continue
        stamp = parse_time(item.get("bonus_timestamp"))
        label = item.get("bonus_timestamp") or item.get("date")
        if stamp is not None:
            if start <= stamp <= now:
                definite_inside.append(label)
            continue
        day = parse_date(item.get("date"))
        if day is None:
            invalid.append(label)
        elif day <= now.date() - timedelta(days=10):
            # Even a late timestamp on this calendar date is more than nine days old.
            continue
        elif day >= now.date() - timedelta(days=8):
            definite_inside.append(label)
        else:
            # Exactly nine calendar dates ago; time of day determines the result.
            uncertain.append(label)
    return definite_inside, uncertain, invalid


def annual_completed(history, account, year):
    count = 0
    for item in history:
        if not isinstance(item, dict) or not complete(item) or record_account(item) != account:
            continue
        stamp = parse_time(item.get("bonus_timestamp"))
        day = stamp.date() if stamp else parse_date(item.get("date"))
        if day and day.year == year:
            count += 1
    return count


def main(data):
    now = parse_time(data.get("current_time"))
    if now is None:
        return {"error": "current_time is required and must be a parseable timestamp."}

    referrer = data.get("referrer") if isinstance(data.get("referrer"), dict) else {}
    referred = data.get("referred") if isinstance(data.get("referred"), dict) else {}
    history = data.get("history") if isinstance(data.get("history"), list) else []
    tenure = referrer.get("tenure_days")
    age_floor = referred.get("age_at_least")
    deposit_amount = money(referred.get("deposit_amount"))
    deposit_deadline = referred.get("deposit_within_days")

    inside, uncertain, invalid_dates = rolling_assessment(history, now)
    rolling_block = len(inside) >= 2
    rolling_uncertain = not rolling_block and len(inside) + len(uncertain) >= 2

    shared_missing = []
    if tenure is None:
        shared_missing.append("referrer.tenure_days")
    if referred.get("is_new_customer") is not True:
        shared_missing.append("confirmation that the referred person is a new Rho-Bank customer")
    if referred.get("different_registered_address") is not True:
        shared_missing.append("confirmation of different registered addresses")
    if age_floor is None:
        shared_missing.append("referred.age_at_least")
    if deposit_amount is None:
        shared_missing.append("referred.deposit_amount")
    if referred.get("deposit_is_new_money") is not True:
        shared_missing.append("confirmation that the deposit is new money")
    if deposit_deadline is None:
        shared_missing.append("referred.deposit_within_days")

    eligible, blocked = [], []
    for program in PROGRAMS:
        reasons = []
        if tenure is not None:
            try:
                if int(tenure) < program["tenure_days"]:
                    reasons.append("referrer tenure is below %d days" % program["tenure_days"])
            except (ValueError, TypeError):
                reasons.append("referrer.tenure_days is not numeric")
        if age_floor is not None:
            try:
                if int(age_floor) < program["minimum_age"]:
                    reasons.append("referred age confirmation does not meet the product minimum of %d" % program["minimum_age"])
            except (ValueError, TypeError):
                reasons.append("referred.age_at_least is not numeric")
        required_deposit = Decimal(program["deposit"])
        if deposit_amount is not None and deposit_amount < required_deposit:
            reasons.append("planned deposit is below $%s" % program["deposit"])
        if deposit_deadline is not None:
            try:
                if int(deposit_deadline) > program["deposit_days"]:
                    reasons.append("planned deposit timing exceeds the %d-day deadline" % program["deposit_days"])
            except (ValueError, TypeError):
                reasons.append("referred.deposit_within_days is not numeric")
        annual = annual_completed(history, program["account"], now.year)
        if annual >= program["annual_cap"]:
            reasons.append("annual cap of %d completed bonuses for this program has been reached" % program["annual_cap"])
        if rolling_block:
            reasons.append("two successful bonuses are already confirmed in the current rolling nine-day window")
        if rolling_uncertain:
            reasons.append("exact successful-bonus timestamps are required to verify the rolling nine-day limit")
        if shared_missing:
            reasons.extend(shared_missing)

        combined = Decimal(program["referrer_bonus"]) + Decimal(program["new_member_bonus"])
        item = {
            "account": program["account"],
            "referrer_bonus": "%.2f" % Decimal(program["referrer_bonus"]),
            "new_member_bonus": "%.2f" % Decimal(program["new_member_bonus"]),
            "combined_bonus": "%.2f" % combined,
            "qualifying_deposit": "%.2f" % required_deposit,
            "deposit_deadline_days": program["deposit_days"],
            "referrer_tenure_days": program["tenure_days"],
            "annual_cap": program["annual_cap"],
            "completed_this_calendar_year": annual,
        }
        if reasons:
            item["reasons"] = reasons
            blocked.append(item)
        else:
            eligible.append(item)

    eligible.sort(key=lambda x: Decimal(x["combined_bonus"]), reverse=True)
    blocked.sort(key=lambda x: (x["account"]))
    return {
        "best_option": eligible[0] if eligible else None,
        "eligible_options": eligible,
        "blocked_options": blocked,
        "missing_or_unverified": shared_missing,
        "rolling_window": {
            "confirmed_successful_bonus_count": len(inside),
            "confirmed_inside_records": inside,
            "date_boundary_records_requiring_exact_timestamps": uncertain,
            "unparseable_complete_record_dates": invalid_dates,
            "cap": 2,
        },
        "rolling_window_verification_required": rolling_uncertain or bool(invalid_dates),
        "future_conditions": FUTURE_CONDITIONS,
        "notes": [
            "The rolling cap is shared across checking products; annual caps are program-specific.",
            "Only COMPLETE records are counted as successful referral bonuses.",
            "This result evaluates documented terms and does not submit or guarantee a referral."
        ],
    }


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        if not isinstance(raw, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(raw), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
