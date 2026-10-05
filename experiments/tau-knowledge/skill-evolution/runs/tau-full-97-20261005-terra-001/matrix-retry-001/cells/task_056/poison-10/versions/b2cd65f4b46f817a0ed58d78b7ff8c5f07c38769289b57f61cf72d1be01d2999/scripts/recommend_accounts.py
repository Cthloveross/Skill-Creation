#!/usr/bin/env python3
"""Screen and rank caller-supplied business checking account records.

The program reads one JSON object from stdin and emits one JSON object on stdout.
It deliberately has no embedded product catalog or customer-specific values.
"""
import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation


BIG = Decimal("999999999")


def fail(message):
    print(json.dumps({"status": "error", "error": message}, sort_keys=True))
    raise SystemExit(0)


def numeric(value, label):
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


def rendered(value):
    if value is None:
        return None
    return format(value.quantize(Decimal("0.01")), "f")


def parse_day(value, label):
    if not isinstance(value, str) or len(value) < 10:
        raise ValueError(label + " must begin with YYYY-MM-DD")
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        raise ValueError(label + " must begin with YYYY-MM-DD")


def eligibility_state(raw, name):
    if raw is None:
        return "confirmed", None
    if not isinstance(raw, dict):
        raise ValueError("eligibility for " + name + " must be an object")
    status = raw.get("status", "confirmed")
    if status not in ("confirmed", "conditional", "ineligible"):
        raise ValueError("eligibility.status for " + name + " is invalid")
    condition = raw.get("condition")
    if status == "confirmed":
        if condition is not None and (not isinstance(condition, str) or not condition.strip()):
            raise ValueError("eligibility.condition for " + name + " must be nonempty when supplied")
        return status, condition.strip() if isinstance(condition, str) else None
    if not isinstance(condition, str) or not condition.strip():
        raise ValueError("eligibility.condition is required for " + status + " account " + name)
    return status, condition.strip()


def feature_state(features, key, name):
    if features is None:
        return None
    if not isinstance(features, dict):
        raise ValueError("features for " + name + " must be an object")
    state = features.get(key)
    if state not in (True, False, None):
        raise ValueError("feature " + key + " for " + name + " must be true, false, or null")
    return state


def promotion_priority(promotions, name, as_of):
    active = []
    for promotion in promotions:
        if not isinstance(promotion, dict):
            raise ValueError("each promotion must be an object")
        if promotion.get("name") != name:
            continue
        start = parse_day(promotion.get("starts_on"), "promotion.starts_on")
        end = parse_day(promotion.get("ends_on"), "promotion.ends_on")
        priority = promotion.get("priority")
        if end < start:
            raise ValueError("promotion ends before it starts")
        if not isinstance(priority, int) or isinstance(priority, bool) or priority < 1:
            raise ValueError("promotion.priority must be a positive integer")
        if start <= as_of <= end:
            active.append(priority)
    return min(active) if active else None


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    as_of = parse_day(payload.get("as_of"), "as_of")
    requirements = payload.get("requirements", {})
    candidates = payload.get("candidates")
    promotions = payload.get("promotions", [])
    if not isinstance(requirements, dict) or not isinstance(candidates, list) or not isinstance(promotions, list):
        raise ValueError("requirements must be an object and candidates/promotions must be arrays")

    for key in ("zero_overdraft_required", "must_waive_monthly_fee"):
        if not isinstance(requirements.get(key, False), bool):
            raise ValueError(key + " must be boolean")
    required_features = requirements.get("required_features", [])
    preferred_features = requirements.get("preferred_features", [])
    for values, label in ((required_features, "required_features"), (preferred_features, "preferred_features")):
        if not isinstance(values, list) or not all(isinstance(v, str) and v.strip() for v in values):
            raise ValueError(label + " must be an array of nonempty strings")

    reliable_balance = numeric(requirements.get("reliably_maintainable_balance"), "reliably_maintainable_balance")
    maximum_fee = numeric(requirements.get("maximum_monthly_fee"), "maximum_monthly_fee")
    qualified, conditional, excluded, names = [], [], [], set()

    for raw in candidates:
        if not isinstance(raw, dict) or not isinstance(raw.get("name"), str) or not raw["name"].strip():
            raise ValueError("each candidate needs a nonempty name")
        name = raw["name"].strip()
        if name in names:
            raise ValueError("candidate names must be unique")
        names.add(name)

        overdraft = numeric(raw.get("overdraft_fee"), "overdraft_fee for " + name)
        monthly = numeric(raw.get("monthly_fee"), "monthly_fee for " + name)
        waiver = numeric(raw.get("waiver_balance"), "waiver_balance for " + name)
        waiver_basis = raw.get("waiver_basis")
        if waiver_basis is not None and (not isinstance(waiver_basis, str) or not waiver_basis.strip()):
            raise ValueError("waiver_basis for " + name + " must be a nonempty string")
        sources = raw.get("sources", [])
        if not isinstance(sources, list):
            raise ValueError("sources for " + name + " must be an array")

        status, condition = eligibility_state(raw.get("eligibility"), name)
        failures, unknowns = [], []
        if status == "ineligible":
            failures.append(condition)
        elif status == "conditional":
            unknowns.append(condition)

        if requirements.get("zero_overdraft_required"):
            if overdraft is None:
                unknowns.append("overdraft-fee term is unknown")
            elif overdraft != 0:
                failures.append("overdraft fee is not zero")
        if maximum_fee is not None:
            if monthly is None:
                unknowns.append("monthly-fee term is unknown")
            elif monthly > maximum_fee:
                failures.append("monthly fee exceeds the customer maximum")
        for key in required_features:
            value = feature_state(raw.get("features"), key, name)
            if value is False:
                failures.append("required feature unavailable: " + key)
            elif value is None:
                unknowns.append("required feature unknown: " + key)

        if monthly == 0:
            waiver_possible = True
        elif monthly is None or waiver is None or reliable_balance is None:
            waiver_possible = None
        else:
            waiver_possible = reliable_balance >= waiver
        if requirements.get("must_waive_monthly_fee"):
            if waiver_possible is False:
                failures.append("monthly fee cannot be reliably waived")
            elif waiver_possible is None:
                unknowns.append("monthly-fee waiver feasibility is unknown")

        record = {
            "name": name,
            "overdraft_fee": rendered(overdraft),
            "monthly_fee": rendered(monthly),
            "waiver_balance": rendered(waiver),
            "waiver_basis": waiver_basis.strip() if isinstance(waiver_basis, str) else None,
            "waiver_reliably_possible": waiver_possible,
            "sources": sources,
        }
        if failures:
            record["reasons"] = sorted(set(failures))
            excluded.append(record)
        elif unknowns:
            record["conditions"] = sorted(set(unknowns))
            conditional.append(record)
        else:
            priority = promotion_priority(promotions, name, as_of)
            preference_count = sum(feature_state(raw.get("features"), key, name) is True for key in preferred_features)
            effective_fee = Decimal("0") if waiver_possible is True else (monthly if monthly is not None else BIG)
            record["active_promotion_priority"] = priority
            record["preferred_feature_count"] = preference_count
            record["_rank"] = (
                0 if priority is not None else 1,
                priority if priority is not None else 999999,
                -preference_count,
                0 if waiver_possible is True else 1,
                effective_fee,
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
            conditions = sorted({condition for item in conditional for condition in item["conditions"]})
            questions.append("Confirm: " + "; ".join(conditions))
        elif candidates:
            questions.append("No supplied candidate meets every hard requirement.")
        else:
            questions.append("Provide evidence-backed account records to compare.")

    return {
        "status": "ok",
        "as_of": as_of.isoformat(),
        "reliable_balance_used": rendered(reliable_balance),
        "recommendation": qualified[0] if qualified else None,
        "qualified": qualified,
        "conditional": conditional,
        "excluded": excluded,
        "questions": questions,
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
