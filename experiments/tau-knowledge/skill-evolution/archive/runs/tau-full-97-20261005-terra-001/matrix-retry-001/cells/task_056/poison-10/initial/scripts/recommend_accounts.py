#!/usr/bin/env python3
"""Screen and rank supplied business-checking candidate records.

Input and output are JSON objects on stdin/stdout. The program is intentionally
fact-neutral: account terms and promotions must be supplied by the caller.
"""

import json
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation


def fail(message):
    print(json.dumps({"status": "error", "error": message}, sort_keys=True))
    raise SystemExit(0)


def as_decimal(value, field, candidate_name):
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("%s for %s must be numeric or null" % (field, candidate_name))
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("%s for %s must be numeric or null" % (field, candidate_name))
    if result < 0:
        raise ValueError("%s for %s cannot be negative" % (field, candidate_name))
    return result


def money(value):
    if value is None:
        return None
    return format(value.quantize(Decimal("0.01")), "f")


def parse_day(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("%s must be a nonempty ISO date or timestamp" % field)
    text = value.strip()
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        raise ValueError("%s must begin with YYYY-MM-DD" % field)


def state_items(value, label, candidate_name):
    """Return (failed criteria, unknown criteria) from a bool/null/map status."""
    if value is None:
        return ([], [label])
    if isinstance(value, bool):
        return ([] if value else [label], [])
    if not isinstance(value, dict):
        raise ValueError("%s for %s must be true, false, null, or an object" % (label, candidate_name))
    failed, unknown = [], []
    for key, status in value.items():
        criterion = "%s:%s" % (label, key)
        if status is False:
            failed.append(criterion)
        elif status is None:
            unknown.append(criterion)
        elif status is not True:
            raise ValueError("%s for %s must contain only true, false, or null" % (label, candidate_name))
    return failed, unknown


def reliable_balance(requirements):
    direct = requirements.get("reliably_maintainable_balance")
    if direct is not None:
        return as_decimal(direct, "reliably_maintainable_balance", "requirements")
    interval = requirements.get("balance_range")
    if interval is None:
        return None
    if not isinstance(interval, dict):
        raise ValueError("balance_range must be an object")
    lower = interval.get("minimum", interval.get("min"))
    upper = interval.get("maximum", interval.get("max"))
    result = as_decimal(lower, "balance_range.minimum", "requirements")
    upper_value = as_decimal(upper, "balance_range.maximum", "requirements") if upper is not None else None
    if result is not None and upper_value is not None and result > upper_value:
        raise ValueError("balance_range.minimum cannot exceed balance_range.maximum")
    return result


def active_promotion(promotions, candidate_name, today):
    matches = []
    for promotion in promotions:
        if not isinstance(promotion, dict):
            raise ValueError("each promotion must be an object")
        if promotion.get("name") != candidate_name:
            continue
        start = parse_day(promotion.get("starts_on"), "promotion.starts_on")
        end = parse_day(promotion.get("ends_on"), "promotion.ends_on")
        if end < start:
            raise ValueError("promotion.ends_on cannot precede promotion.starts_on")
        priority = promotion.get("priority")
        if not isinstance(priority, int) or isinstance(priority, bool) or priority < 1:
            raise ValueError("promotion.priority must be a positive integer")
        if start <= today <= end:
            matches.append(priority)
    return min(matches) if matches else None


def feature_status(features, key, candidate_name):
    if features is None:
        return None
    if isinstance(features, list):
        if not all(isinstance(item, str) for item in features):
            raise ValueError("features list for %s must contain strings" % candidate_name)
        return key in features
    if isinstance(features, dict):
        result = features.get(key)
        if result not in (True, False, None):
            raise ValueError("feature status for %s on %s must be true, false, or null" % (key, candidate_name))
        return result
    raise ValueError("features for %s must be a list, object, or null" % candidate_name)


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    today = parse_day(payload.get("as_of"), "as_of")
    requirements = payload.get("requirements", {})
    if not isinstance(requirements, dict):
        raise ValueError("requirements must be an object")
    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        raise ValueError("candidates must be an array")
    promotions = payload.get("promotions", [])
    if not isinstance(promotions, list):
        raise ValueError("promotions must be an array")
    excluded_names = payload.get("exclude_names", [])
    if not isinstance(excluded_names, list) or not all(isinstance(x, str) for x in excluded_names):
        raise ValueError("exclude_names must be an array of strings")

    zero_od = requirements.get("zero_overdraft_required", False)
    if not isinstance(zero_od, bool):
        raise ValueError("zero_overdraft_required must be boolean")
    avoid_fee = requirements.get("avoid_monthly_fee", False)
    must_waive = requirements.get("must_waive_monthly_fee", False)
    if not isinstance(avoid_fee, bool) or not isinstance(must_waive, bool):
        raise ValueError("monthly-fee preferences must be boolean")
    required_features = requirements.get("required_features", [])
    if not isinstance(required_features, list) or not all(isinstance(x, str) and x for x in required_features):
        raise ValueError("required_features must be an array of nonempty strings")
    balance = reliable_balance(requirements)

    qualified, conditional, excluded = [], [], []
    seen_names = set()
    for raw in candidates:
        if not isinstance(raw, dict):
            raise ValueError("each candidate must be an object")
        name = raw.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("each candidate needs a nonempty name")
        name = name.strip()
        if name in seen_names:
            raise ValueError("candidate names must be unique")
        seen_names.add(name)

        if name in excluded_names:
            excluded.append({"name": name, "reasons": ["excluded by caller"]})
            continue

        overdraft = as_decimal(raw.get("overdraft_fee"), "overdraft_fee", name)
        monthly = as_decimal(raw.get("monthly_fee"), "monthly_fee", name)
        waiver = as_decimal(raw.get("waiver_balance"), "waiver_balance", name)
        failures, unknowns = state_items(raw.get("eligibility", True), "eligibility", name)

        if zero_od:
            if overdraft is None:
                unknowns.append("overdraft_fee")
            elif overdraft != 0:
                failures.append("overdraft fee is not zero")

        for feature in required_features:
            status = feature_status(raw.get("features"), feature, name)
            if status is False:
                failures.append("required feature unavailable:%s" % feature)
            elif status is None:
                unknowns.append("required feature unknown:%s" % feature)

        waiver_reliably_possible = None
        if monthly is not None and monthly == 0:
            waiver_reliably_possible = True
        elif monthly is not None:
            if waiver is None or balance is None:
                waiver_reliably_possible = None
            else:
                waiver_reliably_possible = balance >= waiver

        if must_waive:
            if waiver_reliably_possible is False:
                failures.append("monthly fee cannot be reliably waived at supplied balance")
            elif waiver_reliably_possible is None:
                unknowns.append("monthly-fee waiver feasibility")

        record = {
            "name": name,
            "monthly_fee": money(monthly),
            "waiver_balance": money(waiver),
            "overdraft_fee": money(overdraft),
            "waiver_reliably_possible": waiver_reliably_possible,
            "sources": raw.get("sources", []),
        }
        if not isinstance(record["sources"], list):
            raise ValueError("sources for %s must be an array" % name)

        if failures:
            record["reasons"] = sorted(set(failures))
            excluded.append(record)
        elif unknowns:
            record["conditions"] = sorted(set(unknowns))
            conditional.append(record)
        else:
            promo_priority = active_promotion(promotions, name, today)
            record["active_promotion_priority"] = promo_priority
            if waiver_reliably_possible is True:
                fee_rank = Decimal("0")
            elif monthly is None:
                fee_rank = Decimal("999999999")
            else:
                fee_rank = monthly
            waiver_rank = waiver if waiver is not None else Decimal("999999999")
            # An active promotion is intentionally first only among confirmed fits.
            record["_rank"] = (0 if promo_priority is not None else 1,
                               promo_priority if promo_priority is not None else 999999,
                               fee_rank, waiver_rank, name.casefold())
            qualified.append(record)

    qualified.sort(key=lambda item: item["_rank"])
    for item in qualified:
        item.pop("_rank", None)
    conditional.sort(key=lambda item: item["name"].casefold())
    excluded.sort(key=lambda item: item["name"].casefold())

    questions = []
    if not qualified:
        if conditional:
            conditions = sorted({condition for item in conditional for condition in item.get("conditions", [])})
            questions.append("Confirm the unresolved eligibility, fee, or feature facts: " + "; ".join(conditions))
        elif not candidates:
            questions.append("Provide account-specific fee, waiver, overdraft, eligibility, and feature records to compare.")
        else:
            questions.append("No supplied candidate meets all hard requirements; identify which requirement may be flexible.")
    elif avoid_fee and balance is None:
        questions.append("Provide the balance the customer can reliably maintain to assess monthly-fee waivers.")

    return {
        "status": "ok",
        "as_of": today.isoformat(),
        "reliable_balance_used": money(balance),
        "recommendation": qualified[0] if qualified else None,
        "qualified": qualified,
        "conditional": conditional,
        "excluded": excluded,
        "questions": questions,
    }


if __name__ == "__main__":
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            fail("stdin must contain one JSON object")
        result = main(json.loads(raw))
        print(json.dumps(result, sort_keys=True))
    except json.JSONDecodeError as exc:
        fail("invalid JSON: %s" % exc.msg)
    except ValueError as exc:
        fail(str(exc))
