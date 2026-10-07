#!/usr/bin/env python3
"""Evaluate documented business-checking candidates without taking banking actions.

Reads one JSON object from stdin and emits one JSON object to stdout.  See SKILL.md
for the input and output schema.
"""

import json
import re
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation


def clean_text(value):
    return str(value).strip().casefold()


def money(value):
    """Parse a numeric amount or a conventional currency string."""
    if isinstance(value, bool) or value is None:
        raise ValueError("not a monetary value")
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value))
    if isinstance(value, str):
        text = value.strip().replace(",", "")
        text = re.sub(r"^\$", "", text)
        try:
            return Decimal(text)
        except InvalidOperation as exc:
            raise ValueError("not a monetary value") from exc
    raise ValueError("not a monetary value")


def get_number(record, key):
    if key not in record:
        return None
    try:
        return money(record[key])
    except ValueError:
        return None


def iso_date(value):
    if not isinstance(value, str):
        raise ValueError("date must be an ISO date string")
    # Accept a timestamp by considering its leading ISO calendar date.
    return date.fromisoformat(value.strip()[:10])


def active_promotions(promotions, current_day, errors):
    active = []
    if promotions is None:
        return active
    if not isinstance(promotions, list):
        errors.append("promotions must be a list when supplied")
        return active
    for index, promo in enumerate(promotions):
        if not isinstance(promo, dict):
            errors.append("promotions[%d] must be an object" % index)
            continue
        priority = promo.get("priority")
        if not isinstance(priority, list) or not all(isinstance(x, str) and x.strip() for x in priority):
            errors.append("promotions[%d].priority must be a nonempty list of account-class strings" % index)
            continue
        try:
            start = iso_date(promo["start"])
            end = iso_date(promo["end"])
        except (KeyError, ValueError):
            errors.append("promotions[%d] needs valid start and end ISO dates" % index)
            continue
        if end < start:
            errors.append("promotions[%d] ends before it starts" % index)
            continue
        if start <= current_day <= end:
            active.append({"index": index, "start": start.isoformat(), "end": end.isoformat(), "priority": priority})
    return active


def candidate_reasons(candidate, requirements):
    reasons = []
    if not isinstance(candidate, dict):
        return ["candidate is not an object"]
    name = candidate.get("account_class")
    if not isinstance(name, str) or not name.strip():
        reasons.append("missing account_class")

    if requirements.get("zero_overdraft_fee") is True:
        fee = get_number(candidate, "overdraft_fee")
        if fee is None:
            reasons.append("overdraft fee is not documented")
        elif fee != Decimal("0"):
            reasons.append("overdraft fee is not $0.00")
    elif requirements.get("zero_overdraft_fee") not in (None, False):
        reasons.append("zero_overdraft_fee must be true or false")

    numeric_rules = (
        ("max_overdraft_fee", "overdraft_fee", "is above maximum overdraft fee", lambda actual, wanted: actual <= wanted),
        ("min_daily_transaction_limit", "daily_transaction_limit", "is below required daily transaction limit", lambda actual, wanted: actual >= wanted),
        ("min_apy", "apy", "is below required APY", lambda actual, wanted: actual >= wanted),
        ("max_monthly_maintenance_fee", "monthly_maintenance_fee", "is above maximum monthly maintenance fee", lambda actual, wanted: actual <= wanted),
        ("max_waiver_balance", "waiver_balance", "requires a higher fee-waiver balance", lambda actual, wanted: actual <= wanted),
    )
    for requirement_key, candidate_key, failure, comparator in numeric_rules:
        if requirement_key not in requirements:
            continue
        wanted = get_number(requirements, requirement_key)
        actual = get_number(candidate, candidate_key)
        if wanted is None:
            reasons.append("requirement %s is not numeric" % requirement_key)
        elif actual is None:
            reasons.append("%s is not documented" % candidate_key)
        elif not comparator(actual, wanted):
            reasons.append(failure)

    if "features_all" in requirements:
        wanted_features = requirements["features_all"]
        if not isinstance(wanted_features, list) or not all(isinstance(x, str) and x.strip() for x in wanted_features):
            reasons.append("features_all must be a list of nonempty strings")
        else:
            supplied = candidate.get("features")
            if not isinstance(supplied, list):
                reasons.append("features are not documented")
            else:
                actual_features = {clean_text(item) for item in supplied if isinstance(item, str)}
                missing = [item for item in wanted_features if clean_text(item) not in actual_features]
                if missing:
                    reasons.append("missing required features: " + ", ".join(missing))

    if "exact_attributes" in requirements:
        expected = requirements["exact_attributes"]
        actual = candidate.get("attributes")
        if not isinstance(expected, dict):
            reasons.append("exact_attributes must be an object")
        elif not isinstance(actual, dict):
            reasons.append("attributes are not documented")
        else:
            for key, value in expected.items():
                if key not in actual:
                    reasons.append("attribute %s is not documented" % key)
                elif actual[key] != value:
                    reasons.append("attribute %s does not match" % key)
    return reasons


def main(payload):
    if not isinstance(payload, dict):
        return {"status": "error", "errors": ["top-level JSON value must be an object"]}
    errors = []
    requirements = payload.get("requirements", {})
    candidates = payload.get("candidates")
    if not isinstance(requirements, dict):
        errors.append("requirements must be an object")
    if not isinstance(candidates, list):
        errors.append("candidates must be a list")
    try:
        current_day = iso_date(payload.get("as_of", ""))
    except ValueError:
        errors.append("as_of must be a valid ISO date")
        current_day = None
    if errors:
        return {"status": "error", "errors": errors}

    active = active_promotions(payload.get("promotions", []), current_day, errors)
    if errors:
        return {"status": "error", "errors": errors}

    qualifying = []
    excluded = []
    for index, candidate in enumerate(candidates):
        reasons = candidate_reasons(candidate, requirements)
        label = candidate.get("account_class") if isinstance(candidate, dict) else None
        entry = {"input_index": index, "account_class": label}
        if reasons:
            entry["reasons"] = reasons
            excluded.append(entry)
        else:
            qualifying.append(entry)

    # Merge active policy order. Earlier active promotions take precedence if callers
    # deliberately provide more than one; accounts absent from each priority remain after it.
    priority_position = {}
    for promo_order, promo in enumerate(active):
        for position, account_class in enumerate(promo["priority"]):
            key = clean_text(account_class)
            priority_position.setdefault(key, (promo_order, position))

    def rank_key(entry):
        class_key = clean_text(entry["account_class"])
        if class_key in priority_position:
            return (0,) + priority_position[class_key] + (entry["input_index"],)
        return (1, 0, 0, entry["input_index"])

    ranking = sorted(qualifying, key=rank_key)
    recommendation = None
    if ranking:
        winner = ranking[0]
        promoted = clean_text(winner["account_class"]) in priority_position
        recommendation = {
            "account_class": winner["account_class"],
            "selection_basis": "active promotion priority among qualifying accounts" if promoted else "first qualifying candidate in supplied non-promotion order",
        }

    return {
        "status": "ok",
        "as_of": current_day.isoformat(),
        "active_promotions": active,
        "qualifying": qualifying,
        "excluded": excluded,
        "ranking": ranking,
        "recommendation": recommendation,
    }


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        result = main(raw)
    except json.JSONDecodeError as exc:
        result = {"status": "error", "errors": ["invalid JSON input: " + str(exc)]}
    except Exception as exc:  # Keep the command interface JSON-only on malformed runtime data.
        result = {"status": "error", "errors": ["unexpected evaluator error: " + str(exc)]}
    print(json.dumps(result, sort_keys=True, default=str))
