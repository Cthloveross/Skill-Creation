#!/usr/bin/env python3
"""Gate and optimize documented checking-referral plans.

Reads the JSON schema documented in SKILL.md from stdin and emits JSON only.
No bank action is performed.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from itertools import product
from pathlib import Path

CATALOG_PATH = Path(__file__).resolve().parent.parent / "references" / "referral_programs.json"


def parse_time(value, field):
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a nonempty ISO-8601 timestamp")
    normalized = value.replace("Z", "+00:00")
    try:
        moment = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"{field} is not a valid ISO-8601 timestamp") from exc
    if moment.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return moment.astimezone(timezone.utc)


def amount(value, field):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if result < 0:
        raise ValueError(f"{field} cannot be negative")
    return result


def money(value):
    return f"${value.quantize(Decimal('0.01'))}"


def load_catalog():
    with CATALOG_PATH.open(encoding="utf-8") as source:
        return json.load(source)["programs"]


def add_missing(missing, label, condition, detail):
    if not condition:
        missing.append({"subject": label, "required_confirmation": detail})


def prerequisite_failures(data):
    missing = []
    referrer = data.get("referrer")
    if not isinstance(referrer, dict):
        return [{"subject": "referrer", "required_confirmation": "referrer information is required"}]
    add_missing(missing, "referrer", referrer.get("active_checking") is True,
                "active Rho-Bank checking status")
    add_missing(missing, "referrer", isinstance(referrer.get("tenure_days"), (int, float)) and referrer.get("tenure_days") >= 0,
                "tenure in days since the first Rho-Bank checking account was opened")
    add_missing(missing, "referrer", referrer.get("referral_history_complete") is True,
                "complete current-calendar-year referral history")
    if not isinstance(referrer.get("referrals"), list):
        missing.append({"subject": "referrer", "required_confirmation": "referrals must be supplied as a complete list"})

    prospects = data.get("prospects")
    if not isinstance(prospects, list) or not prospects:
        missing.append({"subject": "prospects", "required_confirmation": "at least one prospective referee is required"})
        return missing
    for index, prospect in enumerate(prospects, start=1):
        label = prospect.get("name") if isinstance(prospect, dict) else None
        label = label or f"prospect {index}"
        if not isinstance(prospect, dict):
            missing.append({"subject": label, "required_confirmation": "prospect details are required"})
            continue
        kind = prospect.get("kind")
        add_missing(missing, label, kind in ("individual", "business"), "whether the prospect is an individual or business")
        eligibility = prospect.get("eligibility")
        if not isinstance(eligibility, dict):
            missing.append({"subject": label, "required_confirmation": "all referral eligibility confirmations"})
            continue
        for key, wording in [
            ("new_customer_no_current_or_closed_12mo", "no current Rho-Bank account and no account closed within the last 12 months"),
            ("no_stacking_promotion", "no other new-account promotion or sign-up bonus"),
            ("one_referral_code", "only one referral code will be used"),
            ("qualifying_deposit_is_new_money", "qualifying deposit will be new money, not a transfer from another Rho-Bank account"),
            ("will_hold_qualifying_deposit", "qualifying deposit will remain at least 30 days after the qualifying period ends"),
        ]:
            add_missing(missing, label, eligibility.get(key) is True, wording)
        if kind == "individual":
            add_missing(missing, label, eligibility.get("different_registered_address") is True,
                        "registered address differs from the referrer's address")
        elif kind == "business":
            add_missing(missing, label, eligibility.get("distinct_business_primary_owner") is True,
                        "primary authorized signer/owner differs from every existing Rho-Bank business account's primary owner")
    return missing


def annual_usage(referrals, year):
    usage = {}
    parsed = []
    for index, referral in enumerate(referrals, start=1):
        if not isinstance(referral, dict):
            raise ValueError(f"referrals[{index}] must be an object")
        if referral.get("referral_status") != "COMPLETE":
            continue
        when = parse_time(referral.get("completed_at"), f"referrals[{index}].completed_at")
        account = referral.get("referred_account_type")
        if not isinstance(account, str) or not account:
            raise ValueError(f"referrals[{index}].referred_account_type is required")
        parsed.append(when)
        if when.year == year:
            usage[account] = usage.get(account, 0) + 1
    return usage, parsed


def candidate(program, prospect, tenure):
    if program["kind"] != prospect.get("kind"):
        return False
    if tenure < program["tenure_days"]:
        return False
    if amount(prospect.get("qualifying_deposit"), "qualifying_deposit") < Decimal(str(program["deposit_required"])):
        return False
    if program["kind"] == "individual":
        age = prospect.get("age")
        if not isinstance(age, (int, float)):
            return False
        if "age_min" in program and age < program["age_min"]:
            return False
        if "age_max" in program and age > program["age_max"]:
            return False
    else:
        if program.get("startup_required") and prospect.get("is_startup") is not True:
            return False
        if "company_age_max" in program:
            company_age = prospect.get("company_age_years")
            if not isinstance(company_age, (int, float)) or company_age > program["company_age_max"]:
                return False
    return True


def serialize_program(program, prospect):
    referrer_bonus = Decimal(str(program["referrer_bonus"]))
    member_bonus = Decimal(str(program["member_bonus"]))
    return {
        "prospect": prospect.get("name"),
        "account": program["account"],
        "referrer_bonus": money(referrer_bonus),
        "new_member_bonus": money(member_bonus),
        "combined_bonus": money(referrer_bonus + member_bonus),
        "qualifying_deposit": money(Decimal(str(program["deposit_required"]))),
        "deposit_window_days": program["deposit_window_days"],
        "referrer_tenure_days": program["tenure_days"],
        "annual_cap": program["annual_cap"],
    }


def optimize(candidates, initial_usage):
    best = None
    for picks in product(*candidates):
        usage = dict(initial_usage)
        possible = True
        for program in picks:
            usage[program["account"]] = usage.get(program["account"], 0) + 1
            if usage[program["account"]] > program["annual_cap"]:
                possible = False
                break
        if not possible:
            continue
        value = sum(Decimal(str(item["referrer_bonus"])) + Decimal(str(item["member_bonus"])) for item in picks)
        # Deterministic account-name tie breaker.
        tie_key = tuple(item["account"] for item in picks)
        record = (value, tie_key, picks, usage)
        if best is None or value > best[0] or (value == best[0] and tie_key < best[1]):
            best = record
    return best


def make_schedule(as_of, existing_times, count):
    # Conservative timing: a prior bonus remains in-window through exactly nine days;
    # therefore the next cohort is scheduled one second after the restrictive boundary.
    scheduled = []
    cursor = as_of
    all_times = list(existing_times)
    for _ in range(count):
        while sum(1 for old in all_times if cursor - old <= timedelta(days=9) and cursor >= old) >= 2:
            relevant = [old for old in all_times if cursor - old <= timedelta(days=9) and cursor >= old]
            cursor = min(relevant) + timedelta(days=9, seconds=1)
        scheduled.append(cursor)
        all_times.append(cursor)
    groups = []
    for index in range(0, len(scheduled), 2):
        groups.append({
            "maximum_successful_bonuses": len(scheduled[index:index + 2]),
            "not_before": scheduled[index].isoformat(),
            "plan_items": list(range(index + 1, min(index + 2, len(scheduled)) + 1)),
        })
    return groups


def main(data):
    missing = prerequisite_failures(data)
    if missing:
        return {"status": "blocked", "missing_or_unconfirmed": missing,
                "message": "Eligibility is incomplete; no referral account comparison or recommendation was produced."}
    as_of = parse_time(data.get("as_of"), "as_of")
    referrer = data["referrer"]
    tenure = referrer["tenure_days"]
    if not isinstance(tenure, (int, float)):
        raise ValueError("referrer.tenure_days must be numeric")
    usage, complete_times = annual_usage(referrer["referrals"], as_of.year)
    programs = load_catalog()
    per_prospect = []
    for index, prospect in enumerate(data["prospects"], start=1):
        options = [p for p in programs if candidate(p, prospect, tenure)]
        if not options:
            return {"status": "no_eligible_plan", "prospect": prospect.get("name", f"prospect {index}"),
                    "message": "No documented program fits this prospect's confirmed type, stated funding capacity, tenure, and documented constraints."}
        per_prospect.append(options)
    chosen = optimize(per_prospect, usage)
    if chosen is None:
        return {"status": "no_eligible_plan",
                "message": "Every otherwise fitting combination would exceed a documented annual referral cap."}
    total, _, picks, after_usage = chosen
    plan = [serialize_program(p, prospect) for p, prospect in zip(picks, data["prospects"])]
    for item in plan:
        item["annual_used_after"] = after_usage[item["account"]]
    schedule = make_schedule(as_of, complete_times, len(plan))
    return {
        "status": "ok",
        "objective": "maximum documented combined referrer and new-member bonuses",
        "total_combined_bonus": money(total),
        "plan": plan,
        "annual_usage_after": after_usage,
        "rolling_9_day_schedule_constraint": {
            "maximum_successful_bonuses_in_any_rolling_9_days": 2,
            "suggested_bonus_credit_cohorts": schedule,
            "warning": "These are not application dates and do not guarantee qualification or payout timing."
        },
        "ongoing_conditions": [
            "All supplied eligibility confirmations must remain true.",
            "Each qualifying deposit must be new money and remain for at least 30 days after the qualifying period ends.",
            "Both accounts must remain in good standing; an account closed within 90 days may trigger a clawback.",
            "A rolling-window denial cannot be reinstated within that same window."
        ]
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), indent=2, sort_keys=True))
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "invalid_input", "error": str(exc)}, indent=2, sort_keys=True))
        sys.exit(2)
