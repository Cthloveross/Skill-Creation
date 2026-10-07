#!/usr/bin/env python3
"""Evaluate supplied business-referral facts without performing a bank action.

Reads the JSON schema in SKILL.md from stdin and emits one JSON object to stdout.
Uses only the Python standard library.
"""

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

ROLLING_DAYS = 9
ROLLING_CAP = 2
COMMON_FACTS = (
    ("is_new_customer", "The referred business must be a new Rho-Bank customer."),
    ("different_registered_address", "The referrer and referred business cannot share a registered address."),
    ("different_primary_business_owner", "The referred business must have a different primary owner from existing Rho-Bank business accounts."),
    ("deposit_is_external_new_money", "The qualifying deposit must be external new money, not a transfer from another Rho-Bank account."),
)


def parse_time(value):
    """Return (UTC-naive datetime, date_only) for supported public date forms."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("missing timestamp")
    text = value.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, fmt), True
        except ValueError:
            pass
    text = re.sub(r"\sEST$", " -0500", text, flags=re.I)
    text = re.sub(r"\sEDT$", " -0400", text, flags=re.I)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = datetime.strptime(text, "%Y-%m-%d %H:%M:%S %z")
        except ValueError as exc:
            raise ValueError("unrecognized timestamp: " + value) from exc
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed, False


def amount(value, field):
    if value is None or isinstance(value, bool):
        raise ValueError("missing " + field)
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("invalid " + field) from exc
    if result < 0:
        raise ValueError(field + " cannot be negative")
    return result


def normalized(value):
    return " ".join(str(value or "").casefold().split())


def aliases(program):
    values = [program.get("account_name")]
    if isinstance(program.get("account_names"), list):
        values.extend(program["account_names"])
    return {normalized(item) for item in values if isinstance(item, str) and item.strip()}


def completed_count(referrals, names, year):
    count = 0
    for referral in referrals:
        if not isinstance(referral, dict):
            continue
        if str(referral.get("referral_status", "")).upper() != "COMPLETE":
            continue
        if normalized(referral.get("referred_account_type")) not in names:
            continue
        try:
            when, _ = parse_time(referral.get("date"))
        except ValueError:
            continue
        if when.year == year:
            count += 1
    return count


def integer(value, field):
    if isinstance(value, bool):
        raise ValueError("invalid " + field)
    try:
        result = int(value)
    except (ValueError, TypeError) as exc:
        raise ValueError("invalid " + field) from exc
    if result < 0:
        raise ValueError(field + " cannot be negative")
    return result


def main(data):
    if not isinstance(data, dict):
        return {"ok": False, "errors": ["top-level JSON must be an object"]}
    try:
        now, _ = parse_time(data.get("current_time"))
    except ValueError as exc:
        return {"ok": False, "errors": ["current_time: " + str(exc)]}

    referrals = data.get("referrals", [])
    programs = data.get("programs", [])
    prospect = data.get("prospect", {})
    referrer = data.get("referrer", {})
    errors = []
    if not isinstance(referrals, list):
        errors.append("referrals must be an array")
        referrals = []
    if not isinstance(programs, list) or not programs:
        errors.append("programs must be a nonempty array")
        programs = []
    if not isinstance(prospect, dict):
        errors.append("prospect must be an object")
        prospect = {}
    if not isinstance(referrer, dict):
        errors.append("referrer must be an object")
        referrer = {}
    if errors:
        return {"ok": False, "errors": errors}

    common_blocking, common_pending = [], []
    for key, message in COMMON_FACTS:
        value = prospect.get(key)
        if value is False:
            common_blocking.append(message)
        elif value is not True:
            common_pending.append("Confirm: " + message)

    try:
        deposit = amount(prospect.get("deposit_amount"), "prospect.deposit_amount")
        deposit_known = True
    except ValueError:
        deposit = None
        deposit_known = False

    try:
        tenure = integer(referrer.get("tenure_days"), "referrer.tenure_days")
        tenure_known = True
    except ValueError:
        tenure = None
        tenure_known = False

    lower_bound = now - timedelta(days=ROLLING_DAYS)
    rolling_matches = []
    boundary_uncertain = False
    for referral in referrals:
        if not isinstance(referral, dict) or str(referral.get("referral_status", "")).upper() != "COMPLETE":
            continue
        try:
            when, date_only = parse_time(referral.get("date"))
        except ValueError:
            continue
        if lower_bound <= when <= now:
            rolling_matches.append({"date": referral.get("date"), "account_type": referral.get("referred_account_type")})
            if date_only and abs((when - lower_bound).total_seconds()) < 86400:
                boundary_uncertain = True

    rolling_reasons = []
    if len(rolling_matches) >= ROLLING_CAP:
        rolling_reasons.append("Already received %d COMPLETE referral bonuses in the rolling %d-day window (maximum %d)." % (len(rolling_matches), ROLLING_DAYS, ROLLING_CAP))
    if boundary_uncertain:
        rolling_reasons.append("A date-only COMPLETE referral is near the rolling-window boundary; obtain its exact timestamp before approval.")

    eligible, blocked, pending = [], [], []
    for program in programs:
        if not isinstance(program, dict):
            errors.append("each program must be an object")
            continue
        label = program.get("account_name") or program.get("id") or "unnamed program"
        try:
            bonus = amount(program.get("referrer_bonus"), "referrer_bonus")
            threshold = amount(program.get("qualifying_deposit"), "qualifying_deposit")
            window = integer(program.get("deposit_window_days"), "deposit_window_days")
            required_tenure = integer(program.get("referrer_tenure_days"), "referrer_tenure_days")
            cap = integer(program.get("annual_cap"), "annual_cap")
        except ValueError as exc:
            pending.append({"program": label, "pending_reasons": ["Document complete program terms before comparison: " + str(exc)]})
            continue
        names = aliases(program)
        if not names:
            pending.append({"program": label, "pending_reasons": ["Document an account name for annual-history matching."]})
            continue

        annual = completed_count(referrals, names, now.year)
        reasons = list(common_blocking) + list(rolling_reasons)
        pending_reasons = list(common_pending)
        if annual >= cap:
            reasons.append("Annual cap reached: %d COMPLETE referrals in %d, cap %d." % (annual, now.year, cap))
        if deposit_known:
            if deposit < threshold:
                reasons.append("Proposed deposit (%s) is below required qualifying deposit (%s)." % (deposit, threshold))
        else:
            pending_reasons.append("Confirm the proposed qualifying-deposit amount.")
        if tenure_known:
            if tenure < required_tenure:
                reasons.append("Confirmed earliest-checking tenure (%d days) is below the required %d days." % (tenure, required_tenure))
        else:
            pending_reasons.append("Confirm earliest-checking tenure meets %d days." % required_tenure)

        result = {
            "program": label,
            "program_id": program.get("id"),
            "referrer_bonus": str(bonus),
            "qualifying_deposit": str(threshold),
            "deposit_window_days": window,
            "required_referrer_tenure_days": required_tenure,
            "annual_cap": cap,
            "annual_complete_referrals": annual,
        }
        if reasons:
            result["blocking_reasons"] = reasons
            blocked.append(result)
        elif pending_reasons:
            result["pending_reasons"] = pending_reasons
            pending.append(result)
        else:
            eligible.append(result)

    eligible.sort(key=lambda item: (Decimal(item["referrer_bonus"]), Decimal(item["qualifying_deposit"])), reverse=True)
    recommendation = None
    if eligible:
        top = eligible[0]
        recommendation = {
            "program": top["program"],
            "program_id": top["program_id"],
            "referrer_bonus": top["referrer_bonus"],
            "reason": "Highest documented referrer bonus among currently eligible programs.",
        }

    return {
        "ok": not errors,
        "errors": errors,
        "common_eligibility": {"blocking_reasons": common_blocking, "pending_reasons": common_pending},
        "rolling_limit": {
            "window_days": ROLLING_DAYS,
            "maximum_complete_bonuses": ROLLING_CAP,
            "complete_bonuses_in_window": len(rolling_matches),
            "matching_referrals": rolling_matches,
            "needs_exact_timestamp": boundary_uncertain,
            "can_submit_now": len(rolling_matches) < ROLLING_CAP and not boundary_uncertain,
        },
        "eligible_programs": eligible,
        "blocked_programs": blocked,
        "pending_programs": pending,
        "recommendation": recommendation,
    }


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ok": False, "errors": ["invalid input: " + str(exc)]}, sort_keys=True))
