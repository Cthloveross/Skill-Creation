#!/usr/bin/env python3
"""Validate, screen, and rank caller-supplied business checking account records.

The program reads one JSON object from stdin and writes one JSON object to stdout.
It deliberately contains no product catalog: all terms, features, and promotions are
provided by the caller from the current task materials.
"""

import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation


MISSING_RANK = Decimal("999999999")


def error(message):
    print(json.dumps({"status": "error", "error": message}, sort_keys=True))
    raise SystemExit(0)


def decimal(value, label):
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("%s must be a nonnegative number or null" % label)
    try:
        value = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("%s must be a nonnegative number or null" % label)
    if not value.is_finite() or value < 0:
        raise ValueError("%s must be a nonnegative number or null" % label)
    return value


def money(value):
    return None if value is None else format(value.quantize(Decimal("0.01")), "f")


def day(value, label):
    if not isinstance(value, str) or len(value) < 10:
        raise ValueError("%s must begin with an ISO YYYY-MM-DD date" % label)
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        raise ValueError("%s must begin with an ISO YYYY-MM-DD date" % label)


def states(value, label):
    """Return known-false and unknown conditions for a bool/null/object status."""
    if value is True:
        return [], []
    if value is False:
        return [label], []
    if value is None:
        return [], [label]
    if not isinstance(value, dict):
        raise ValueError("%s must be true, false, null, or an object" % label)
    failed, unknown = [], []
    for key, state in value.items():
        condition = "%s:%s" % (label, key)
        if state is False:
            failed.append(condition)
        elif state is None:
            unknown.append(condition)
        elif state is not True:
            raise ValueError("%s values must be true, false, or null" % label)
    return failed, unknown


def feature_state(features, key, name):
    if features is None:
        return None
    if isinstance(features, list):
        if not all(isinstance(item, str) for item in features):
            raise ValueError("features for %s must contain strings" % name)
        return key in features
    if isinstance(features, dict):
        state = features.get(key)
        if state not in (True, False, None):
            raise ValueError("feature %s for %s must be true, false, or null" % (key, name))
        return state
    raise ValueError("features for %s must be a list, object, or null" % name)


def reliable_balance(requirements):
    if requirements.get("reliably_maintainable_balance") is not None:
        return decimal(requirements["reliably_maintainable_balance"], "reliably_maintainable_balance")
    interval = requirements.get("balance_range")
    if interval is None:
        return None
    if not isinstance(interval, dict):
        raise ValueError("balance_range must be an object")
    minimum = decimal(interval.get("minimum", interval.get("min")), "balance_range.minimum")
    maximum_raw = interval.get("maximum", interval.get("max"))
    maximum = decimal(maximum_raw, "balance_range.maximum") if maximum_raw is not None else None
    if minimum is not None and maximum is not None and minimum > maximum:
        raise ValueError("balance_range.minimum cannot exceed balance_range.maximum")
    return minimum


def promotion_priority(promotions, name, as_of):
    active = []
    for item in promotions:
        if not isinstance(item, dict):
            raise ValueError("each promotion must be an object")
        if item.get("name") != name:
            continue
        start, end = day(item.get("starts_on"), "promotion.starts_on"), day(item.get("ends_on"), "promotion.ends_on")
        priority = item.get("priority")
        if end < start:
            raise ValueError("promotion.ends_on cannot precede promotion.starts_on")
        if not isinstance(priority, int) or isinstance(priority, bool) or priority < 1:
            raise ValueError("promotion.priority must be a positive integer")
        if start <= as_of <= end:
            active.append(priority)
    return min(active) if active else None


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    as_of = day(payload.get("as_of"), "as_of")
    requirements = payload.get("requirements", {})
    candidates = payload.get("candidates")
    promotions = payload.get("promotions", [])
    excluded_names = payload.get("exclude_names", [])
    if not isinstance(requirements, dict) or not isinstance(candidates, list) or not isinstance(promotions, list):
        raise ValueError("requirements must be an object and candidates/promotions must be arrays")
    if not isinstance(excluded_names, list) or not all(isinstance(name, str) for name in excluded_names):
        raise ValueError("exclude_names must be an array of strings")

    for flag in ("zero_overdraft_required", "avoid_monthly_fee", "must_waive_monthly_fee"):
        if not isinstance(requirements.get(flag, False), bool):
            raise ValueError("%s must be boolean" % flag)
    required = requirements.get("required_features", [])
    preferred = requirements.get("preferred_features", [])
    if not all(isinstance(group, list) and all(isinstance(x, str) and x for x in group) for group in (required, preferred)):
        raise ValueError("feature requirement lists must contain nonempty strings")

    balance = reliable_balance(requirements)
    qualified, conditional, excluded, names = [], [], [], set()
    for raw in candidates:
        if not isinstance(raw, dict) or not isinstance(raw.get("name"), str) or not raw["name"].strip():
            raise ValueError("each candidate needs a nonempty name")
        name = raw["name"].strip()
        if name in names:
            raise ValueError("candidate names must be unique")
        names.add(name)
        if name in excluded_names:
            excluded.append({"name": name, "reasons": ["excluded by caller"]})
            continue

        overdraft = decimal(raw.get("overdraft_fee"), "overdraft_fee for " + name)
        monthly = decimal(raw.get("monthly_fee"), "monthly_fee for " + name)
        waiver = decimal(raw.get("waiver_balance"), "waiver_balance for " + name)
        failures, unknown = states(raw.get("eligibility", True), "eligibility")
        if requirements.get("zero_overdraft_required"):
            if overdraft is None:
                unknown.append("overdraft_fee")
            elif overdraft != 0:
                failures.append("overdraft fee is not zero")
        for key in required:
            state = feature_state(raw.get("features"), key, name)
            if state is False:
                failures.append("required feature unavailable:" + key)
            elif state is None:
                unknown.append("required feature unknown:" + key)

        if monthly == 0:
            waiver_possible = True
        elif monthly is None or waiver is None or balance is None:
            waiver_possible = None
        else:
            waiver_possible = balance >= waiver
        if requirements.get("must_waive_monthly_fee"):
            if waiver_possible is False:
                failures.append("monthly fee cannot be reliably waived at supplied balance")
            elif waiver_possible is None:
                unknown.append("monthly-fee waiver feasibility")

        record = {"name": name, "monthly_fee": money(monthly), "waiver_balance": money(waiver),
                  "overdraft_fee": money(overdraft), "waiver_reliably_possible": waiver_possible,
                  "sources": raw.get("sources", [])}
        if not isinstance(record["sources"], list):
            raise ValueError("sources for %s must be an array" % name)
        if failures:
            record["reasons"] = sorted(set(failures))
            excluded.append(record)
        elif unknown:
            record["conditions"] = sorted(set(unknown))
            conditional.append(record)
        else:
            priority = promotion_priority(promotions, name, as_of)
            preferred_count = sum(feature_state(raw.get("features"), key, name) is True for key in preferred)
            fee_rank = Decimal("0") if waiver_possible is True else (monthly if monthly is not None else MISSING_RANK)
            record["active_promotion_priority"] = priority
            record["preferred_feature_count"] = preferred_count
            record["_rank"] = (0 if priority is not None else 1, priority if priority is not None else 999999,
                               fee_rank, waiver if waiver is not None else MISSING_RANK, -preferred_count, name.casefold())
            qualified.append(record)

    qualified.sort(key=lambda item: item["_rank"])
    for record in qualified:
        record.pop("_rank")
    conditional.sort(key=lambda item: item["name"].casefold())
    excluded.sort(key=lambda item: item["name"].casefold())
    questions = []
    if not qualified:
        if conditional:
            conditions = sorted({x for record in conditional for x in record["conditions"]})
            questions.append("Confirm unresolved facts: " + "; ".join(conditions))
        elif candidates:
            questions.append("No supplied candidate meets every hard requirement; identify which requirement can change.")
        else:
            questions.append("Provide account-specific terms and eligibility records to compare.")
    return {"status": "ok", "as_of": as_of.isoformat(), "reliable_balance_used": money(balance),
            "recommendation": qualified[0] if qualified else None, "qualified": qualified,
            "conditional": conditional, "excluded": excluded, "questions": questions}


if __name__ == "__main__":
    try:
        source = sys.stdin.read()
        if not source.strip():
            error("stdin must contain one JSON object")
        print(json.dumps(main(json.loads(source)), sort_keys=True))
    except json.JSONDecodeError as exc:
        error("invalid JSON: " + exc.msg)
    except ValueError as exc:
        error(str(exc))
