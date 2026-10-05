#!/usr/bin/env python3
"""Screen and rank caller-supplied checking-account records.
Reads one JSON object on stdin and writes one JSON object on stdout.  Product
terms are deliberately not embedded in this program.
"""
import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation

BIG = Decimal("999999999")


def fail(message):
    print(json.dumps({"status": "error", "error": message}, sort_keys=True))
    raise SystemExit(0)


def number(value, label):
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(label + " must be a nonnegative number or null")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(label + " must be a nonnegative number or null")
    if not result.is_finite() or result < 0:
        raise ValueError(label + " must be a nonnegative number or null")
    return result


def display(value):
    return None if value is None else format(value.quantize(Decimal("0.01")), "f")


def parse_date(value, label):
    if not isinstance(value, str) or len(value) < 10:
        raise ValueError(label + " must begin with YYYY-MM-DD")
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        raise ValueError(label + " must begin with YYYY-MM-DD")


def condition_states(value, label):
    if value is True:
        return [], []
    if value is False:
        return [label], []
    if value is None:
        return [], [label]
    if not isinstance(value, dict):
        raise ValueError(label + " must be true, false, null, or an object")
    failed, unknown = [], []
    for key, state in value.items():
        item = label + ":" + str(key)
        if state is False:
            failed.append(item)
        elif state is None:
            unknown.append(item)
        elif state is not True:
            raise ValueError(label + " values must be true, false, or null")
    return failed, unknown


def feature(features, key, account_name):
    if features is None:
        return None
    if not isinstance(features, dict):
        raise ValueError("features for " + account_name + " must be an object or null")
    state = features.get(key)
    if state not in (True, False, None):
        raise ValueError("feature " + key + " for " + account_name + " must be true, false, or null")
    return state


def active_priority(promotions, name, as_of):
    values = []
    for promotion in promotions:
        if not isinstance(promotion, dict):
            raise ValueError("each promotion must be an object")
        if promotion.get("name") != name:
            continue
        start = parse_date(promotion.get("starts_on"), "promotion.starts_on")
        end = parse_date(promotion.get("ends_on"), "promotion.ends_on")
        priority = promotion.get("priority")
        if end < start:
            raise ValueError("promotion.ends_on cannot precede promotion.starts_on")
        if not isinstance(priority, int) or isinstance(priority, bool) or priority < 1:
            raise ValueError("promotion.priority must be a positive integer")
        if start <= as_of <= end:
            values.append(priority)
    return min(values) if values else None


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    as_of = parse_date(payload.get("as_of"), "as_of")
    requirements = payload.get("requirements", {})
    candidates = payload.get("candidates")
    promotions = payload.get("promotions", [])
    if not isinstance(requirements, dict) or not isinstance(candidates, list) or not isinstance(promotions, list):
        raise ValueError("requirements must be an object and candidates/promotions must be arrays")
    for key in ("zero_overdraft_required", "must_waive_monthly_fee"):
        if not isinstance(requirements.get(key, False), bool):
            raise ValueError(key + " must be boolean")
    required = requirements.get("required_features", [])
    preferred = requirements.get("preferred_features", [])
    if not all(isinstance(items, list) and all(isinstance(x, str) and x for x in items) for items in (required, preferred)):
        raise ValueError("feature lists must contain nonempty strings")
    reliable = number(requirements.get("reliably_maintainable_balance"), "reliably_maintainable_balance")
    maximum_fee = number(requirements.get("maximum_monthly_fee"), "maximum_monthly_fee")

    qualified, conditional, excluded, seen = [], [], [], set()
    for raw in candidates:
        if not isinstance(raw, dict) or not isinstance(raw.get("name"), str) or not raw["name"].strip():
            raise ValueError("each candidate needs a nonempty name")
        name = raw["name"].strip()
        if name in seen:
            raise ValueError("candidate names must be unique")
        seen.add(name)
        overdraft = number(raw.get("overdraft_fee"), "overdraft_fee for " + name)
        monthly = number(raw.get("monthly_fee"), "monthly_fee for " + name)
        waiver = number(raw.get("waiver_balance"), "waiver_balance for " + name)
        failures, unknown = condition_states(raw.get("eligibility", True), "eligibility")
        if requirements.get("zero_overdraft_required"):
            if overdraft is None:
                unknown.append("overdraft_fee")
            elif overdraft != 0:
                failures.append("overdraft fee is not zero")
        if maximum_fee is not None:
            if monthly is None:
                unknown.append("monthly_fee")
            elif monthly > maximum_fee:
                failures.append("monthly fee exceeds customer maximum")
        for key in required:
            state = feature(raw.get("features"), key, name)
            if state is False:
                failures.append("required feature unavailable:" + key)
            elif state is None:
                unknown.append("required feature unknown:" + key)
        if monthly == 0:
            waiver_possible = True
        elif monthly is None or waiver is None or reliable is None:
            waiver_possible = None
        else:
            waiver_possible = reliable >= waiver
        if requirements.get("must_waive_monthly_fee"):
            if waiver_possible is False:
                failures.append("monthly fee cannot be reliably waived")
            elif waiver_possible is None:
                unknown.append("monthly-fee waiver feasibility")
        record = {
            "name": name,
            "overdraft_fee": display(overdraft),
            "monthly_fee": display(monthly),
            "waiver_balance": display(waiver),
            "waiver_reliably_possible": waiver_possible,
            "sources": raw.get("sources", []),
        }
        if not isinstance(record["sources"], list):
            raise ValueError("sources for " + name + " must be an array")
        if failures:
            record["reasons"] = sorted(set(failures))
            excluded.append(record)
        elif unknown:
            record["conditions"] = sorted(set(unknown))
            conditional.append(record)
        else:
            priority = active_priority(promotions, name, as_of)
            preference_count = sum(feature(raw.get("features"), key, name) is True for key in preferred)
            effective_cost = Decimal("0") if waiver_possible is True else (monthly if monthly is not None else BIG)
            record["active_promotion_priority"] = priority
            record["preferred_feature_count"] = preference_count
            record["_rank"] = (
                0 if priority is not None else 1,
                priority if priority is not None else 999999,
                -preference_count,
                0 if waiver_possible is True else 1,
                effective_cost,
                waiver if waiver is not None else BIG,
                name.casefold(),
            )
            qualified.append(record)
    qualified.sort(key=lambda item: item["_rank"])
    for item in qualified:
        item.pop("_rank")
    conditional.sort(key=lambda item: item["name"].casefold())
    excluded.sort(key=lambda item: item["name"].casefold())
    questions = []
    if not qualified:
        if conditional:
            unresolved = sorted({reason for item in conditional for reason in item["conditions"]})
            questions.append("Confirm unresolved facts: " + "; ".join(unresolved))
        elif candidates:
            questions.append("No supplied candidate meets every hard requirement.")
        else:
            questions.append("Provide account-specific terms and eligibility records to compare.")
    return {
        "status": "ok", "as_of": as_of.isoformat(), "reliable_balance_used": display(reliable),
        "recommendation": qualified[0] if qualified else None, "qualified": qualified,
        "conditional": conditional, "excluded": excluded, "questions": questions,
    }


if __name__ == "__main__":
    try:
        source = sys.stdin.read()
        if not source.strip():
            fail("stdin must contain one JSON object")
        print(json.dumps(main(json.loads(source)), sort_keys=True))
    except json.JSONDecodeError as exc:
        fail("invalid JSON: " + exc.msg)
    except ValueError as exc:
        fail(str(exc))
