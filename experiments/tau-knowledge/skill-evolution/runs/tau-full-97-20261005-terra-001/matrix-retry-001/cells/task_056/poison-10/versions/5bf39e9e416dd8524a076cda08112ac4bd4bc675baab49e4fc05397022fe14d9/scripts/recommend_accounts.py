#!/usr/bin/env python3
"""Screen and rank caller-supplied business checking account records.

Reads one JSON object from stdin and emits one JSON object to stdout. This
program deliberately contains no account catalog and no customer-specific data.
"""
import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation

BIG = Decimal("999999999")


def error(message):
    print(json.dumps({"status": "error", "error": message}, sort_keys=True))
    raise SystemExit(0)


def numeric(value, label):
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(label + " must be a nonnegative number or null")
    try:
        value = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(label + " must be a nonnegative number or null")
    if not value.is_finite() or value < 0:
        raise ValueError(label + " must be a nonnegative number or null")
    return value


def display(value):
    return None if value is None else format(value.quantize(Decimal("0.01")), "f")


def day(value, label):
    if not isinstance(value, str) or len(value) < 10:
        raise ValueError(label + " must begin with YYYY-MM-DD")
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        raise ValueError(label + " must begin with YYYY-MM-DD")


def feature(features, key, name):
    if features is None:
        return None
    if not isinstance(features, dict):
        raise ValueError("features for " + name + " must be an object")
    value = features.get(key)
    if value not in (True, False, None):
        raise ValueError("feature " + key + " for " + name + " must be true, false, or null")
    return value


def eligibility(raw, name):
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


def priority(promotions, name, as_of):
    matches = []
    for promo in promotions:
        if not isinstance(promo, dict):
            raise ValueError("each promotion must be an object")
        if promo.get("name") != name:
            continue
        start = day(promo.get("starts_on"), "promotion.starts_on")
        end = day(promo.get("ends_on"), "promotion.ends_on")
        rank = promo.get("priority")
        if end < start:
            raise ValueError("promotion ends before it starts")
        if not isinstance(rank, int) or isinstance(rank, bool) or rank < 1:
            raise ValueError("promotion.priority must be a positive integer")
        if start <= as_of <= end:
            matches.append(rank)
    return min(matches) if matches else None


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    as_of = day(payload.get("as_of"), "as_of")
    req = payload.get("requirements", {})
    candidates = payload.get("candidates")
    promotions = payload.get("promotions", [])
    if not isinstance(req, dict) or not isinstance(candidates, list) or not isinstance(promotions, list):
        raise ValueError("requirements must be an object and candidates/promotions must be arrays")
    for key in ("zero_overdraft_required", "must_waive_monthly_fee"):
        if not isinstance(req.get(key, False), bool):
            raise ValueError(key + " must be boolean")
    required = req.get("required_features", [])
    preferred = req.get("preferred_features", [])
    for values, label in ((required, "required_features"), (preferred, "preferred_features")):
        if not isinstance(values, list) or not all(isinstance(v, str) and v.strip() for v in values):
            raise ValueError(label + " must be an array of nonempty strings")

    reliable = numeric(req.get("reliably_maintainable_balance"), "reliably_maintainable_balance")
    maximum_fee = numeric(req.get("maximum_monthly_fee"), "maximum_monthly_fee")
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
        basis = raw.get("waiver_basis")
        if basis is not None and (not isinstance(basis, str) or not basis.strip()):
            raise ValueError("waiver_basis for " + name + " must be a nonempty string")
        sources = raw.get("sources", [])
        if not isinstance(sources, list):
            raise ValueError("sources for " + name + " must be an array")

        state, condition = eligibility(raw.get("eligibility"), name)
        failures, unknowns = [], []
        if state == "ineligible":
            failures.append(condition)
        elif state == "conditional":
            unknowns.append(condition)
        if req.get("zero_overdraft_required"):
            if overdraft is None:
                unknowns.append("overdraft-fee term is unknown")
            elif overdraft != 0:
                failures.append("overdraft fee is not zero")
        if maximum_fee is not None:
            if monthly is None:
                unknowns.append("monthly-fee term is unknown")
            elif monthly > maximum_fee:
                failures.append("monthly fee exceeds the customer maximum")
        for key in required:
            value = feature(raw.get("features"), key, name)
            if value is False:
                failures.append("required feature unavailable: " + key)
            elif value is None:
                unknowns.append("required feature unknown: " + key)

        if monthly == 0:
            waiver_possible = True
        elif monthly is None or waiver is None or reliable is None:
            waiver_possible = None
        else:
            waiver_possible = reliable >= waiver
        if req.get("must_waive_monthly_fee"):
            if waiver_possible is False:
                failures.append("monthly fee cannot be reliably waived")
            elif waiver_possible is None:
                unknowns.append("monthly-fee waiver feasibility is unknown")

        record = {"name": name, "overdraft_fee": display(overdraft), "monthly_fee": display(monthly), "waiver_balance": display(waiver), "waiver_basis": basis.strip() if isinstance(basis, str) else None, "waiver_reliably_possible": waiver_possible, "sources": sources}
        if failures:
            record["reasons"] = sorted(set(failures))
            excluded.append(record)
        elif unknowns:
            record["conditions"] = sorted(set(unknowns))
            conditional.append(record)
        else:
            promo = priority(promotions, name, as_of)
            matches = sum(feature(raw.get("features"), key, name) is True for key in preferred)
            effective_fee = Decimal("0") if waiver_possible is True else (monthly if monthly is not None else BIG)
            record["active_promotion_priority"] = promo
            record["preferred_feature_count"] = matches
            record["_rank"] = (0 if promo is not None else 1, promo if promo is not None else 999999, -matches, 0 if waiver_possible is True else 1, effective_fee, waiver if waiver is not None else BIG, name.casefold())
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

    return {"status": "ok", "as_of": as_of.isoformat(), "reliable_balance_used": display(reliable), "recommendation": qualified[0] if qualified else None, "qualified": qualified, "conditional": conditional, "excluded": excluded, "questions": questions}


if __name__ == "__main__":
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            error("stdin must contain one JSON object")
        print(json.dumps(main(json.loads(raw)), sort_keys=True))
    except json.JSONDecodeError as exc:
        error("invalid JSON: " + exc.msg)
    except ValueError as exc:
        error(str(exc))
