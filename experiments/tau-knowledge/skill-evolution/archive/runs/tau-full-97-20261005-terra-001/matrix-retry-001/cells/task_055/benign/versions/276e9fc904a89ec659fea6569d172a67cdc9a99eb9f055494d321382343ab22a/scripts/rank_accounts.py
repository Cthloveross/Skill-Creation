#!/usr/bin/env python3
"""Conservative, evidence-aware ranking of normalized account candidates.

Input and output are JSON objects on stdin/stdout. This program has no network,
file, or banking-tool side effects.
"""

import json
import math
import sys
from decimal import Decimal, InvalidOperation


def decimal_value(value):
    if isinstance(value, bool):
        raise ValueError("boolean is not numeric")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("not a finite numeric value")


def normalized(value):
    """Normalize numeric values for exact comparisons without changing other types."""
    if isinstance(value, bool) or value is None:
        return value
    try:
        return decimal_value(value).normalize()
    except ValueError:
        return value


def exact_match(actual, expected):
    a = normalized(actual)
    b = normalized(expected)
    return a == b and type(a) is type(b) if isinstance(a, bool) or isinstance(b, bool) else a == b


def require_object(value, label):
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(label + " must be an object")
    return value


def numeric_preference_score(value, higher, weight):
    # log scaling keeps very large monetary fields from dwarfing fee/feature signals.
    number = float(decimal_value(value))
    if not math.isfinite(number):
        raise ValueError("numeric preference is not finite")
    magnitude = math.log1p(abs(number))
    signed = magnitude if higher else -magnitude
    return signed * float(decimal_value(weight))


def evaluate_candidate(candidate, requirements):
    result = {
        "account_class": None,
        "eligible": False,
        "score": None,
        "hard_failures": [],
        "unknown_required_facts": [],
        "matched_required_facts": [],
        "preference_notes": [],
        "evidence_ids": [],
    }
    if not isinstance(candidate, dict):
        result["hard_failures"].append("candidate must be an object")
        return result

    account_class = candidate.get("account_class")
    facts = candidate.get("facts")
    evidence_ids = candidate.get("evidence_ids")
    result["account_class"] = account_class
    if not isinstance(account_class, str) or not account_class.strip():
        result["hard_failures"].append("missing account_class")
    if not isinstance(facts, dict):
        result["hard_failures"].append("facts must be an object")
        facts = {}
    if not isinstance(evidence_ids, list) or not evidence_ids or not all(isinstance(x, str) and x for x in evidence_ids):
        result["hard_failures"].append("missing evidence_ids")
    else:
        result["evidence_ids"] = evidence_ids

    def get_required(field):
        if field not in facts or facts[field] is None:
            result["unknown_required_facts"].append(field)
            return None, False
        return facts[field], True

    for field, expected in requirements["must_equal"].items():
        actual, known = get_required(field)
        if not known:
            continue
        if exact_match(actual, expected):
            result["matched_required_facts"].append(field)
        else:
            result["hard_failures"].append(field + " does not equal required value")

    for field, minimum in requirements["minimum"].items():
        actual, known = get_required(field)
        if not known:
            continue
        try:
            if decimal_value(actual) >= decimal_value(minimum):
                result["matched_required_facts"].append(field)
            else:
                result["hard_failures"].append(field + " is below required minimum")
        except ValueError:
            result["hard_failures"].append(field + " is not numeric")

    for field, maximum in requirements["maximum"].items():
        actual, known = get_required(field)
        if not known:
            continue
        try:
            if decimal_value(actual) <= decimal_value(maximum):
                result["matched_required_facts"].append(field)
            else:
                result["hard_failures"].append(field + " exceeds permitted maximum")
        except ValueError:
            result["hard_failures"].append(field + " is not numeric")

    # An unknown hard requirement is intentionally disqualifying. It must be sourced
    # before a candidate can be presented as satisfying the customer's must-have.
    result["eligible"] = not result["hard_failures"] and not result["unknown_required_facts"]
    if not result["eligible"]:
        return result

    score = 0.0
    for field, weight in requirements["prefer_higher"].items():
        if field not in facts or facts[field] is None:
            result["preference_notes"].append(field + ": unknown; not scored")
            continue
        try:
            score += numeric_preference_score(facts[field], True, weight)
            result["preference_notes"].append(field + ": higher preferred")
        except ValueError:
            result["preference_notes"].append(field + ": nonnumeric; not scored")

    for field, weight in requirements["prefer_lower"].items():
        if field not in facts or facts[field] is None:
            result["preference_notes"].append(field + ": unknown; not scored")
            continue
        try:
            score += numeric_preference_score(facts[field], False, weight)
            result["preference_notes"].append(field + ": lower preferred")
        except ValueError:
            result["preference_notes"].append(field + ": nonnumeric; not scored")

    for field, rule in requirements["prefer_equal"].items():
        if not isinstance(rule, dict) or "value" not in rule or "weight" not in rule:
            result["preference_notes"].append(field + ": invalid equality preference; not scored")
            continue
        if field not in facts or facts[field] is None:
            result["preference_notes"].append(field + ": unknown; not scored")
            continue
        try:
            if exact_match(facts[field], rule["value"]):
                score += float(decimal_value(rule["weight"]))
                result["preference_notes"].append(field + ": preferred value matched")
        except ValueError:
            result["preference_notes"].append(field + ": invalid weight; not scored")

    result["score"] = round(score, 12)
    return result


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("top-level JSON must be an object")
        candidates = payload.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            raise ValueError("candidates must be a nonempty array")
        raw = require_object(payload.get("requirements"), "requirements")
        requirements = {
            "must_equal": require_object(raw.get("must_equal"), "must_equal"),
            "minimum": require_object(raw.get("minimum"), "minimum"),
            "maximum": require_object(raw.get("maximum"), "maximum"),
            "prefer_higher": require_object(raw.get("prefer_higher"), "prefer_higher"),
            "prefer_lower": require_object(raw.get("prefer_lower"), "prefer_lower"),
            "prefer_equal": require_object(raw.get("prefer_equal"), "prefer_equal"),
        }
        results = [evaluate_candidate(item, requirements) for item in candidates]
        eligible = [item for item in results if item["eligible"]]
        eligible.sort(key=lambda item: (-item["score"], item["account_class"] or ""))
        results.sort(key=lambda item: (not item["eligible"], -(item["score"] or 0.0), item["account_class"] or ""))
        output = {
            "recommended_account_class": eligible[0]["account_class"] if eligible else None,
            "recommendation_status": "eligible_candidate_found" if eligible else "no_candidate_satisfies_all_hard_requirements",
            "ranked_candidates": results,
        }
        print(json.dumps(output, sort_keys=True))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": "invalid_input", "message": str(exc)}, sort_keys=True))
        sys.exit(2)


if __name__ == "__main__":
    main()
