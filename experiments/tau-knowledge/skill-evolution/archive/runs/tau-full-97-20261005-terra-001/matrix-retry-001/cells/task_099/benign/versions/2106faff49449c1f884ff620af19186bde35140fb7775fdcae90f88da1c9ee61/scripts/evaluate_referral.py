#!/usr/bin/env python3
"""Evaluate supplied referral facts without performing any bank action.

Reads the schema documented in SKILL.md from stdin and writes JSON to stdout.
Only the Python standard library is used.
"""

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

ROLLING_DAYS = 9
ROLLING_CAP = 2
COMMON_FACTS = (
    ("is_new_customer", "The prospective business must be new to the bank."),
    ("different_registered_address", "Referrer and prospective business cannot use the same registered address."),
    ("different_primary_business_owner", "The prospective business must have a different primary owner from existing bank business accounts."),
    ("deposit_is_external_new_money", "The qualifying deposit must be external new money, not a transfer from another bank account."),
)


def parse_time(value):
    """Return (naive_utc_datetime, was_date_only), accepting common public formats."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("missing timestamp")
    text = value.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return datetime.strptime(text, "%Y-%m-%d"), True
    # Python does not reliably attach an offset for all timezone abbreviations.
    text = re.sub(r"\sEST$", " -0500", text, flags=re.I)
    text = re.sub(r"\sEDT$", " -0400", text, flags=re.I)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S %z", "%Y-%m-%d %H:%M:%S"):
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                parsed = None
        if parsed is None:
            raise ValueError("unrecognized timestamp: " + value)
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed, False


def money(value, field):
    if value is None or isinstance(value, bool):
        raise ValueError("missing or invalid " + field)
    try:
        amount = Decimal(str(value))
    except InvalidOperation:
        raise ValueError("invalid " + field)
    if amount < 0:
        raise ValueError(field + " cannot be negative")
    return amount


def norm(value):
    return " ".join(str(value or "").casefold().split())


def truth_state(value):
    if value is True:
        return "true"
    if value is False:
        return "false"
    return "unknown"


def program_aliases(program):
    aliases = [program.get("account_name")]
    extra = program.get("account_names", [])
    if isinstance(extra, list):
        aliases.extend(extra)
    return {norm(x) for x in aliases if isinstance(x, str) and x.strip()}


def completed_for_program(referrals, aliases, year):
    total = 0
    for row in referrals:
        if not isinstance(row, dict) or str(row.get("referral_status", "")).upper() != "COMPLETE":
            continue
        if norm(row.get("referred_account_type")) not in aliases:
            continue
        try:
            when, _ = parse_time(row.get("date"))
        except ValueError:
            continue
        if when.year == year:
            total += 1
    return total


def main(payload):
    errors = []
    try:
        now, _ = parse_time(payload.get("current_time"))
    except ValueError as exc:
        return {"ok": False, "errors": ["current_time: " + str(exc)]}

    referrals = payload.get("referrals", [])
    programs = payload.get("programs", [])
    prospect = payload.get("prospect", {})
    referrer = payload.get("referrer", {})
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
        state = truth_state(prospect.get(key))
        if state == "false":
            common_blocking.append(message)
        elif state == "unknown":
            common_pending.append("Confirm: " + message)

    rolling_matches = []
    rolling_boundary_precision = False
    lower_bound = now - timedelta(days=ROLLING_DAYS)
    for row in referrals:
        if not isinstance(row, dict) or str(row.get("referral_status", "")).upper() != "COMPLETE":
            continue
        try:
            when, date_only = parse_time(row.get("date"))
        except ValueError:
            continue
        # A bonus exactly nine days old remains in scope: policy says wait until
        # the oldest one is more than nine days old.
        if lower_bound <= when <= now:
            rolling_matches.append({
                "date": row.get("date"),
                "account_type": row.get("referred_account_type"),
            })
            if date_only and abs((when - lower_bound).total_seconds()) < 86400:
                rolling_boundary_precision = True

    rolling_reasons = []
    if len(rolling_matches) >= ROLLING_CAP:
        rolling_reasons.append("Already received %d COMPLETE referral bonuses in the rolling %d-day window (maximum %d)." % (len(rolling_matches), ROLLING_DAYS, ROLLING_CAP))
    if rolling_boundary_precision:
        rolling_reasons.append("A date-only successful referral is near the rolling-window boundary; obtain its exact timestamp before approval.")

    try:
        deposit_amount = money(prospect.get("deposit_amount"), "prospect.deposit_amount")
        deposit_known = True
    except ValueError:
        deposit_amount = None
        deposit_known = False

    tenure_days = referrer.get("tenure_days")
    tenure_known = False
    if tenure_days is not None and not isinstance(tenure_days, bool):
        try:
            tenure_days = int(tenure_days)
            if tenure_days < 0:
                raise ValueError()
            tenure_known = True
        except (ValueError, TypeError):
            errors.append("referrer.tenure_days must be a nonnegative integer")
    tenure_confirmed = truth_state(referrer.get("tenure_confirmed")) == "true"

    eligible, blocked, pending = [], [], []
    for raw in programs:
        if not isinstance(raw, dict):
            errors.append("each program must be an object")
            continue
        label = raw.get("account_name") or raw.get("id") or "unnamed program"
        reasons, pending_reasons = [], []
        try:
            bonus = money(raw.get("referrer_bonus"), "referrer_bonus")
            threshold = money(raw.get("qualifying_deposit"), "qualifying_deposit")
            tenure_required = int(raw.get("referrer_tenure_days"))
            annual_cap = int(raw.get("annual_cap"))
            window_days = int(raw.get("deposit_window_days"))
            if min(tenure_required, annual_cap, window_days) < 0:
                raise ValueError("program numeric fields cannot be negative")
        except (ValueError, TypeError) as exc:
            pending.append({"program": label, "pending_reasons": ["Document complete referral terms before comparison: " + str(exc)]})
            continue

        aliases = program_aliases(raw)
        if not aliases:
            pending.append({"program": label, "pending_reasons": ["Document the account name used to match annual referral history."]})
            continue
        annual_count = completed_for_program(referrals, aliases, now.year)
        if annual_count >= annual_cap:
            reasons.append("Annual cap reached: %d COMPLETE referrals in %d, cap %d." % (annual_count, now.year, annual_cap))
        if deposit_known:
            if deposit_amount < threshold:
                reasons.append("Proposed deposit (%s) is below required qualifying deposit (%s)." % (deposit_amount, threshold))
        else:
            pending_reasons.append("Confirm the proposed qualifying-deposit amount.")
        if tenure_known:
            if tenure_days < tenure_required:
                reasons.append("Referrer tenure (%d days) is below the required %d days." % (tenure_days, tenure_required))
        elif tenure_confirmed:
            # Attestation supports a conditional result, not a measured duration.
            pending_reasons.append("Confirm measured earliest-checking tenure meets %d days; current input is an attestation." % tenure_required)
        else:
            pending_reasons.append("Confirm earliest-checking tenure meets %d days." % tenure_required)

        reasons.extend(common_blocking)
        pending_reasons.extend(common_pending)
        reasons.extend(rolling_reasons)
        result = {
            "program": label,
            "program_id": raw.get("id"),
            "referrer_bonus": str(bonus),
            "qualifying_deposit": str(threshold),
            "deposit_window_days": window_days,
            "required_referrer_tenure_days": tenure_required,
            "annual_cap": annual_cap,
            "annual_complete_referrals": annual_count,
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
            "program_id": top.get("program_id"),
            "referrer_bonus": top["referrer_bonus"],
            "reason": "Highest documented referrer bonus among currently eligible programs.",
        }

    return {
        "ok": not errors,
        "errors": errors,
        "common_eligibility": {
            "blocking_reasons": common_blocking,
            "pending_reasons": common_pending,
        },
        "rolling_limit": {
            "window_days": ROLLING_DAYS,
            "maximum_complete_bonuses": ROLLING_CAP,
            "complete_bonuses_in_window": len(rolling_matches),
            "matching_referrals": rolling_matches,
            "needs_exact_timestamp": rolling_boundary_precision,
            "can_submit_now": len(rolling_matches) < ROLLING_CAP and not rolling_boundary_precision,
        },
        "eligible_programs": eligible,
        "blocked_programs": blocked,
        "pending_programs": pending,
        "recommendation": recommendation,
    }


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("top-level JSON must be an object")
        print(json.dumps(main(data), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"ok": False, "errors": ["invalid input: " + str(exc)]}, sort_keys=True))
