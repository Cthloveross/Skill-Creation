#!/usr/bin/env python3
"""Compare business referral programs from JSON stdin and emit JSON stdout.

This helper performs only deterministic policy comparison; it never submits a
referral or treats unconfirmed referred-business eligibility as confirmed.
"""
import json
import sys
from datetime import datetime, date, time, timedelta
from decimal import Decimal, InvalidOperation

DEFAULT_PROGRAMS = [
    {"name": "Navy Blue", "referrer_bonus": 100, "required_deposit": 5000,
     "deposit_window_days": 90, "tenure_days": 60, "annual_cap": 10},
    {"name": "Lime Green", "referrer_bonus": 200, "required_deposit": 15000,
     "deposit_window_days": 90, "tenure_days": 90, "annual_cap": 12},
    {"name": "True Blue", "referrer_bonus": 350, "required_deposit": 50000,
     "deposit_window_days": 120, "tenure_days": 90, "annual_cap": 15},
    {"name": "Beige", "referrer_bonus": 500, "required_deposit": 100000,
     "deposit_window_days": 120, "tenure_days": 120, "annual_cap": 15},
]
REQUIRED_PROGRAM_KEYS = {
    "name", "referrer_bonus", "required_deposit", "deposit_window_days",
    "tenure_days", "annual_cap"
}


def fail(message):
    print(json.dumps({"error": message}, sort_keys=True))
    raise SystemExit(2)


def parse_datetime(value):
    """Return (datetime, has_explicit_time). Date-only values use midnight."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("must be a non-empty date or timestamp string")
    text = value.strip()
    try:
        if len(text) == 10:
            return datetime.combine(date.fromisoformat(text), time.min), False
        normalized = text.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is not None:
            # Make comparisons deterministic without mixing naive and aware values.
            parsed = parsed.astimezone().replace(tzinfo=None)
        return parsed, True
    except ValueError as exc:
        raise ValueError("invalid ISO date/timestamp: " + text) from exc


def normalized_program_name(value):
    text = str(value or "").lower().replace("account", " ")
    return " ".join(text.split())


def money(value, field):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(field + " must be numeric") from exc
    if result < 0:
        raise ValueError(field + " cannot be negative")
    return result


def main(data):
    for key in ("now", "planned_deposit", "referrer_tenure_days", "referrals"):
        if key not in data:
            fail("missing required input field: " + key)
    if not isinstance(data["referrals"], list):
        fail("referrals must be an array")
    try:
        now, _ = parse_datetime(data["now"])
        deposit = money(data["planned_deposit"], "planned_deposit")
        tenure = int(data["referrer_tenure_days"])
        if tenure < 0:
            raise ValueError("referrer_tenure_days cannot be negative")
    except (ValueError, TypeError) as exc:
        fail(str(exc))

    programs = data.get("programs", DEFAULT_PROGRAMS)
    if not isinstance(programs, list) or not programs:
        fail("programs must be a non-empty array when supplied")
    for program in programs:
        if not isinstance(program, dict) or not REQUIRED_PROGRAM_KEYS.issubset(program):
            fail("each program must contain: " + ", ".join(sorted(REQUIRED_PROGRAM_KEYS)))

    # Completed bonuses matter for both the all-program rolling cap and annual caps.
    completed = []
    for referral in data["referrals"]:
        if not isinstance(referral, dict):
            fail("each referral must be an object")
        if str(referral.get("referral_status", "")).upper() != "COMPLETE":
            continue
        if "date" not in referral:
            fail("a COMPLETE referral is missing date")
        try:
            when, exact = parse_datetime(referral["date"])
        except ValueError as exc:
            fail("invalid COMPLETE referral date: " + str(exc))
        completed.append((referral, when, exact))

    # An event definitely within the preceding 9x24 hours counts. A date-only event
    # exactly nine calendar days ago is boundary-ambiguous, so exact timestamps are
    # required before declaring capacity clear.
    definitely_recent = []
    boundary_ambiguous = []
    for referral, when, exact in completed:
        age = now - when
        if age < timedelta(0):
            continue
        if age < timedelta(days=9):
            definitely_recent.append(referral)
        elif not exact and when.date() == (now.date() - timedelta(days=9)):
            boundary_ambiguous.append(referral)

    if len(definitely_recent) >= 2:
        rolling = {
            "status": "blocked",
            "completed_bonus_count": len(definitely_recent),
            "message": "Two or more completed bonuses are within the rolling nine-day window."
        }
    elif boundary_ambiguous:
        rolling = {
            "status": "needs_exact_timestamps",
            "completed_bonus_count": len(definitely_recent),
            "message": "A date-only completed referral is on the nine-day boundary; exact timestamps are required."
        }
    else:
        rolling = {
            "status": "clear",
            "completed_bonus_count": len(definitely_recent),
            "message": "Fewer than two completed bonuses are within the rolling nine-day window."
        }

    evaluations = []
    for program in programs:
        try:
            required_deposit = money(program["required_deposit"], "required_deposit")
            bonus = money(program["referrer_bonus"], "referrer_bonus")
            threshold = int(program["tenure_days"])
            cap = int(program["annual_cap"])
            window = int(program["deposit_window_days"])
            if min(threshold, cap, window) < 0:
                raise ValueError("program day and cap values cannot be negative")
        except (ValueError, TypeError) as exc:
            fail("invalid program " + str(program.get("name", "")) + ": " + str(exc))
        target = normalized_program_name(program["name"])
        annual_completed = sum(
            1 for referral, when, _ in completed
            if when.year == now.year and normalized_program_name(referral.get("referred_account_type")) == target
        )
        deposit_ok = deposit >= required_deposit
        tenure_ok = tenure >= threshold
        cap_ok = annual_completed < cap
        evaluations.append({
            "name": program["name"],
            "referrer_bonus": float(bonus),
            "required_deposit": float(required_deposit),
            "deposit_window_days": window,
            "required_tenure_days": threshold,
            "annual_cap": cap,
            "completed_this_calendar_year": annual_completed,
            "deposit_qualified": deposit_ok,
            "tenure_qualified": tenure_ok,
            "annual_cap_available": cap_ok,
            "numerically_qualified": deposit_ok and tenure_ok and cap_ok,
            "reasons_not_qualified": [
                reason for ok, reason in (
                    (deposit_ok, "planned deposit is below the required qualifying deposit"),
                    (tenure_ok, "referrer tenure is below the program threshold"),
                    (cap_ok, "program annual referral cap has been reached"),
                ) if not ok
            ],
        })

    candidates = [item for item in evaluations if item["numerically_qualified"]]
    recommendation = None
    if rolling["status"] == "clear" and candidates:
        recommendation = max(candidates, key=lambda item: item["referrer_bonus"])["name"]

    confirmations = {
        "new_money_confirmed": bool(data.get("new_money_confirmed", False)),
        "referred_business_new_confirmed": bool(data.get("referred_business_new_confirmed", False)),
        "different_primary_owner_confirmed": bool(data.get("different_primary_owner_confirmed", False)),
        "different_address_confirmed": bool(data.get("different_address_confirmed", False)),
        "no_other_promotion_confirmed": bool(data.get("no_other_promotion_confirmed", False)),
    }
    labels = {
        "new_money_confirmed": "qualifying deposit must be new money, not an internal Rho-Bank transfer",
        "referred_business_new_confirmed": "referred business must be new to Rho-Bank with no disqualifying existing or recently closed account",
        "different_primary_owner_confirmed": "referred business must have a different primary owner/authorized signer SSN from existing Rho-Bank business accounts",
        "different_address_confirmed": "referrer and referred person/business must not share a registered address",
        "no_other_promotion_confirmed": "referral must not be combined with another new-account promotion and must use only one referral code",
    }
    output = {
        "rolling_window": rolling,
        "evaluations": evaluations,
        "recommendation": recommendation,
        "unresolved_requirements": [labels[key] for key, confirmed in confirmations.items() if not confirmed],
        "deposit_retention_requirement": "Qualifying new money must remain for at least 30 days after the qualifying period ends.",
        "clawback_notice": "A bonus may be reversed if the referred account closes within 90 days of opening.",
    }
    print(json.dumps(output, sort_keys=True))


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        fail("stdin must contain one JSON object: " + str(exc))
    if not isinstance(raw, dict):
        fail("stdin JSON must be an object")
    main(raw)
