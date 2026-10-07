#!/usr/bin/env python3
"""Screen source-backed checking-account candidates.

Reads a JSON case object from stdin and writes a JSON decision object to stdout.
It is deliberately informational: it never calls bank tools or changes accounts.
"""

import json
import sys
from decimal import Decimal, InvalidOperation


def decimal_value(value):
    """Return Decimal for comparable numeric JSON values, else None."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def compare(actual, op, expected):
    if op == "exists":
        return actual is not None
    if actual is None:
        return None

    if op in {"gte", "lte"}:
        a_num, e_num = decimal_value(actual), decimal_value(expected)
        if a_num is None or e_num is None:
            return None
        return a_num >= e_num if op == "gte" else a_num <= e_num

    if op == "eq":
        a_num, e_num = decimal_value(actual), decimal_value(expected)
        if a_num is not None and e_num is not None:
            return a_num == e_num
        return actual == expected
    if op == "ne":
        a_num, e_num = decimal_value(actual), decimal_value(expected)
        if a_num is not None and e_num is not None:
            return a_num != e_num
        return actual != expected
    raise ValueError("unsupported requirement operator: %s" % op)


def assess(candidate, requirements):
    facts = candidate.get("facts", {})
    failed_hard, unknown_hard, failed_soft, unknown_soft = [], [], [], []
    for requirement in requirements:
        key = requirement["key"]
        result = compare(facts.get(key), requirement["op"], requirement.get("value"))
        hard = bool(requirement.get("hard", False))
        if result is False:
            (failed_hard if hard else failed_soft).append(key)
        elif result is None:
            (unknown_hard if hard else unknown_soft).append(key)

    failed_eligibility, unknown_eligibility = [], []
    for rule in candidate.get("eligibility_requirements", []):
        status = rule.get("status")
        if status is False:
            failed_eligibility.append(rule.get("key", "unnamed eligibility condition"))
        elif status is not True:
            unknown_eligibility.append(rule.get("key", "unnamed eligibility condition"))

    confirmed = not (failed_hard or unknown_hard or failed_eligibility or unknown_eligibility)
    return {
        "name": candidate["name"],
        "confirmed_qualifier": confirmed,
        "failed_hard_requirements": failed_hard,
        "unknown_hard_requirements": unknown_hard,
        "failed_eligibility": failed_eligibility,
        "unknown_eligibility": unknown_eligibility,
        "failed_soft_requirements": failed_soft,
        "unknown_soft_requirements": unknown_soft,
    }


def comparison(candidates, baseline_name, metrics):
    if not baseline_name or not metrics:
        return {}
    baseline = next((c for c in candidates if c["name"] == baseline_name), None)
    if baseline is None:
        return {}
    baseline_facts = baseline.get("facts", {})
    result = {}
    for candidate in candidates:
        if candidate["name"] == baseline_name:
            continue
        changes = {}
        for metric in metrics:
            if metric in candidate.get("facts", {}) and metric in baseline_facts:
                changes[metric] = {
                    "candidate": candidate["facts"][metric],
                    "baseline": baseline_facts[metric],
                }
        if changes:
            result[candidate["name"]] = changes
    return result


def main(payload):
    candidates = payload.get("candidates")
    requirements = payload.get("requirements")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("candidates must be a nonempty array")
    if not isinstance(requirements, list):
        raise ValueError("requirements must be an array")
    for candidate in candidates:
        if not isinstance(candidate, dict) or not isinstance(candidate.get("name"), str):
            raise ValueError("each candidate needs a string name")
        if not isinstance(candidate.get("facts", {}), dict):
            raise ValueError("candidate facts must be an object")
    for requirement in requirements:
        if not isinstance(requirement, dict) or "key" not in requirement or "op" not in requirement:
            raise ValueError("each requirement needs key and op")

    assessments = [assess(candidate, requirements) for candidate in candidates]
    assessment_by_name = {item["name"]: item for item in assessments}
    candidate_by_name = {item["name"]: item for item in candidates}

    promotion = payload.get("promotion") or {}
    ordered = promotion.get("ordered_accounts", []) if promotion.get("active") is True else []
    promotion_rank = {name: index for index, name in enumerate(ordered)}

    confirmed = [item for item in assessments if item["confirmed_qualifier"]]
    confirmed.sort(key=lambda item: (
        promotion_rank.get(item["name"], len(ordered) + 1),
        -float(candidate_by_name[item["name"]].get("feature_score", 0)),
        item["name"],
    ))
    selected = confirmed[0]["name"] if confirmed else None

    return {
        "selection": selected,
        "selection_basis": (
            "active promotion priority after confirmed hard-requirement and eligibility screening"
            if selected is not None and selected in promotion_rank else
            "confirmed hard-requirement and eligibility screening; source-backed feature tie-breaker"
            if selected is not None else
            "no confirmed qualifying candidate"
        ),
        "assessments": assessments,
        "unconfirmed_candidates": [
            item["name"] for item in assessments
            if item["unknown_hard_requirements"] or item["unknown_eligibility"]
        ],
        "comparison_to_baseline": comparison(
            candidates, payload.get("baseline_name"), payload.get("comparison_metrics", [])
        ),
    }


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        print(json.dumps(main(data), sort_keys=True))
    except (json.JSONDecodeError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
