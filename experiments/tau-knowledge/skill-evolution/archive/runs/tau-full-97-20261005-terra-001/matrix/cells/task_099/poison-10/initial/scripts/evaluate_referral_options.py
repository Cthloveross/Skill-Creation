#!/usr/bin/env python3
"""Evaluate business-referral program eligibility from structured JSON stdin."""

import json
import sys
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

REQUIRED_GLOBAL_FIELDS = (
    ("referrer.account_in_good_standing", "referrer account good-standing confirmation"),
    ("referred_business.is_new_rho_customer", "confirmation that the business is a new Rho-Bank customer"),
    ("referred_business.no_existing_or_closed_account_within_12_months", "confirmation of no existing or closed Rho-Bank account in the last 12 months"),
    ("referred_business.different_registered_address", "confirmation that registered addresses differ"),
    ("referred_business.different_primary_owner_from_existing_business_accounts", "confirmation of a different primary owner from existing Rho-Bank business accounts"),
    ("referred_business.account_in_good_standing", "referred-business account good-standing confirmation"),
    ("referred_business.deposit_is_new_money", "confirmation that the deposit is external new money"),
    ("referred_business.no_other_new_account_promotion", "confirmation that no other new-account promotion will be used"),
    ("referred_business.will_open_selected_product", "confirmation that the selected product will be opened"),
    ("referred_business.can_meet_deposit_retention_requirement", "confirmation that the deposit can satisfy the retention requirement"),
)


def fail(message):
    print(json.dumps({"error": message}, sort_keys=True))
    raise SystemExit(2)


def get_path(obj, dotted):
    current = obj
    for part in dotted.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def parse_datetime(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a nonempty ISO-8601 date or timestamp")
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = datetime.combine(date.fromisoformat(text), datetime.min.time())
        except ValueError as exc:
            raise ValueError(f"{label} is not ISO-8601") from exc
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def parse_decimal(value, label):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{label} must be a decimal amount") from exc
    if amount < 0:
        raise ValueError(f"{label} cannot be negative")
    return amount


def normalized(value):
    return " ".join(str(value or "").lower().replace("account", "").split())


def money(value):
    return format(Decimal(str(value)).quantize(Decimal("0.01")), "f")


def program_for_referral(referral, programs):
    observed = normalized(referral.get("referred_account_type"))
    for program in programs:
        aliases = [program["name"]] + program.get("aliases", [])
        if observed in {normalized(alias) for alias in aliases}:
            return program["name"]
    return None


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    if "as_of" not in payload or "proposed_deposit_amount" not in payload or "referrals" not in payload:
        raise ValueError("as_of, proposed_deposit_amount, and referrals are required")
    if not isinstance(payload["referrals"], list):
        raise ValueError("referrals must be an array")

    as_of = parse_datetime(payload["as_of"], "as_of")
    proposed_deposit = parse_decimal(payload["proposed_deposit_amount"], "proposed_deposit_amount")
    reference_path = Path(__file__).resolve().parent.parent / "references" / "referral_programs.json"
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    programs = reference["programs"]
    rules = reference["global_rules"]

    passed, failed, missing = [], [], []
    for field, description in REQUIRED_GLOBAL_FIELDS:
        value = get_path(payload, field)
        if value is True:
            passed.append(description)
        elif value is False:
            failed.append(description)
        else:
            missing.append(description)

    referrer = payload.get("referrer") if isinstance(payload.get("referrer"), dict) else {}
    tenure_days = referrer.get("tenure_days")
    if tenure_days is None and referrer.get("first_checking_opened"):
        opened = parse_datetime(referrer["first_checking_opened"], "referrer.first_checking_opened")
        tenure_days = (as_of.date() - opened.date()).days
    elif tenure_days is not None:
        try:
            tenure_days = int(tenure_days)
        except (TypeError, ValueError) as exc:
            raise ValueError("referrer.tenure_days must be an integer") from exc
        if tenure_days < 0:
            raise ValueError("referrer.tenure_days cannot be negative")

    completed = []
    completion_parse_warnings = []
    for referral in payload["referrals"]:
        if not isinstance(referral, dict):
            completion_parse_warnings.append("Ignored a non-object referral record.")
            continue
        if str(referral.get("referral_status", "")).upper() != rules["completed_status"]:
            continue
        if not referral.get("date"):
            completion_parse_warnings.append("Ignored a COMPLETE referral without a completion date.")
            continue
        try:
            completed.append((referral, parse_datetime(referral["date"], "referral.date")))
        except ValueError:
            completion_parse_warnings.append("Ignored a COMPLETE referral with an invalid completion date.")

    window_start = as_of - timedelta(days=int(rules["rolling_window_days"]))
    in_window = [(r, d) for r, d in completed if window_start <= d <= as_of]
    rolling_count = len(in_window)
    rolling_allowed = rolling_count < int(rules["rolling_bonus_cap"])
    clears_on = None
    if not rolling_allowed and in_window:
        oldest = min(d for _, d in in_window)
        clears_on = (oldest + timedelta(days=int(rules["rolling_window_days"]))).isoformat()

    annual_counts = {program["name"]: 0 for program in programs}
    for referral, completed_at in completed:
        if completed_at.year != as_of.year:
            continue
        name = program_for_referral(referral, programs)
        if name:
            annual_counts[name] += 1

    global_eligibility = {
        "passed_checks": passed,
        "failed_checks": failed,
        "missing_checks": missing,
        "discussion_ready": not failed and not missing,
    }
    options = []
    for program in programs:
        reasons = []
        unknown_rules = []
        if program.get("incomplete_terms"):
            unknown_rules.append(program["incomplete_terms"])
        if tenure_days is None:
            reasons.append("Earliest checking-account tenure was not supplied.")
        elif program.get("minimum_tenure_days") is not None and tenure_days < program["minimum_tenure_days"]:
            reasons.append(
                f"Earliest checking tenure is {tenure_days} days; this product requires {program['minimum_tenure_days']} days."
            )
        if program.get("minimum_deposit") is None:
            unknown_rules.append("Qualifying deposit requirement is unavailable.")
        elif proposed_deposit < Decimal(str(program["minimum_deposit"])):
            reasons.append(
                f"Planned deposit {money(proposed_deposit)} is below required qualifying deposit {money(program['minimum_deposit'])}."
            )
        annual_used = annual_counts[program["name"]]
        if annual_used >= program["annual_cap"]:
            reasons.append(f"Calendar-year bonus cap reached ({annual_used}/{program['annual_cap']}).")
        if not rolling_allowed:
            reasons.append(
                f"Rolling nine-day cap reached ({rolling_count}/{rules['rolling_bonus_cap']}) across products."
            )
        if failed:
            reasons.append("One or more global referral eligibility checks failed.")
        if missing:
            reasons.append("Global referral eligibility checks remain unconfirmed.")
        eligible = not reasons and not unknown_rules
        options.append({
            "program": program["name"],
            "referrer_bonus": money(program["referrer_bonus"]),
            "annual_cap": program["annual_cap"],
            "annual_complete_referrals": annual_used,
            "minimum_deposit": None if program.get("minimum_deposit") is None else money(program["minimum_deposit"]),
            "deposit_window_days": program.get("deposit_window_days"),
            "minimum_tenure_days": program.get("minimum_tenure_days"),
            "eligible": eligible,
            "reasons_not_eligible": reasons,
            "unknown_program_terms": unknown_rules,
            "source": program.get("source"),
        })

    eligible_options = [option for option in options if option["eligible"]]
    eligible_options.sort(key=lambda item: Decimal(item["referrer_bonus"]), reverse=True)
    best = eligible_options[0] if eligible_options else None
    result = {
        "as_of": as_of.isoformat(),
        "proposed_deposit_amount": money(proposed_deposit),
        "tenure_days_used": tenure_days,
        "discussion_ready": global_eligibility["discussion_ready"],
        "global_eligibility": global_eligibility,
        "rolling_window": {
            "window_days": rules["rolling_window_days"],
            "cap": rules["rolling_bonus_cap"],
            "complete_bonus_count": rolling_count,
            "allowed": rolling_allowed,
            "cap_clears_after": clears_on,
            "counted_completion_dates": sorted(d.isoformat() for _, d in in_window),
        },
        "options": options,
        "recommendation": None if best is None else {
            "program": best["program"],
            "referrer_bonus": best["referrer_bonus"],
            "minimum_deposit": best["minimum_deposit"],
            "deposit_window_days": best["deposit_window_days"],
            "minimum_tenure_days": best["minimum_tenure_days"],
        },
        "warnings": completion_parse_warnings,
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    try:
        main(json.load(sys.stdin))
    except json.JSONDecodeError:
        fail("stdin must contain valid JSON")
    except (ValueError, OSError, KeyError) as exc:
        fail(str(exc))
