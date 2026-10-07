#!/usr/bin/env python3
"""Evidence-only business-account ranking helper.

Read one JSON object from stdin and write one JSON object to stdout. No banking
operation, retrieval, or filesystem input is performed.
"""
import json
import sys
from datetime import date, datetime


def emit(value):
    print(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str))


def parse_date(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError:
        try:
            return datetime.fromisoformat(value.strip().replace("Z", "+00:00")).date()
        except ValueError:
            return None


def path_get(source, path):
    value = source
    for part in str(path).split("."):
        if not isinstance(value, dict) or part not in value:
            return False, None
        value = value[part]
    return True, value


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def compare(actual, operator, expected):
    try:
        if operator == "==": return actual == expected
        if operator == "!=": return actual != expected
        if operator == "<": return actual < expected
        if operator == "<=": return actual <= expected
        if operator == ">": return actual > expected
        if operator == ">=": return actual >= expected
        if operator == "in": return actual in expected
        if operator == "not_in": return actual not in expected
    except (TypeError, ValueError):
        return None
    return None


def promotion_status(promotion, as_of):
    if not isinstance(promotion, dict) or as_of is None:
        return False, None
    start, end = parse_date(promotion.get("start")), parse_date(promotion.get("end"))
    priority = promotion.get("priority")
    if start is None or end is None or not isinstance(priority, int):
        return False, None
    return start <= as_of <= end, priority


def evaluate(candidate, customer, requirements, as_of):
    features = candidate.get("features") if isinstance(candidate.get("features"), dict) else {}
    failed, unknown = [], []
    rules = candidate.get("eligibility_rules", [])
    if not isinstance(rules, list):
        rules = []
        failed.append("invalid eligibility_rules")
    for rule in rules:
        if not isinstance(rule, dict) or not isinstance(rule.get("field"), str):
            failed.append("invalid eligibility rule")
            continue
        label = str(rule.get("reason") or "eligibility rule: " + rule["field"])
        source = candidate if rule.get("source") == "candidate" else customer
        present, actual = path_get(source, rule["field"])
        if not present:
            unknown.append(label + " (required fact is missing)")
            continue
        outcome = compare(actual, rule.get("operator", "=="), rule.get("value"))
        if outcome is None:
            unknown.append(label + " (cannot compare supplied values)")
        elif not outcome:
            failed.append(label)
    for group, relation in (("required_features", "exact"), ("min_features", "min"), ("max_features", "max")):
        values = requirements.get(group, {})
        for field, expected in values.items():
            present, actual = path_get(features, field)
            if not present:
                unknown.append(group + " is undocumented: " + str(field))
                continue
            if relation == "exact" and actual != expected:
                failed.append("does not meet required " + str(field))
            elif relation != "exact":
                actual_num, expected_num = number(actual), number(expected)
                if actual_num is None or expected_num is None:
                    unknown.append(group + " is not numeric: " + str(field))
                elif relation == "min" and actual_num < expected_num:
                    failed.append("below required minimum for " + str(field))
                elif relation == "max" and actual_num > expected_num:
                    failed.append("above allowed maximum for " + str(field))
    active, priority = promotion_status(candidate.get("promotion"), as_of)
    preference, rank = number(candidate.get("preference_score", 0)), number(candidate.get("selection_rank", 0))
    return {
        "name": candidate["name"],
        "status": "excluded" if failed else ("conditional" if unknown else "qualified"),
        "failed_checks": failed,
        "unconfirmed_checks": unknown,
        "promotion_active": active,
        "promotion_priority": priority,
        "preference_score": 0.0 if preference is None else preference,
        "selection_rank": 0.0 if rank is None else rank,
        "features": features,
    }


def rank_key(item):
    return (
        0 if item["promotion_active"] else 1,
        item["promotion_priority"] if item["promotion_active"] else 10 ** 9,
        -item["preference_score"], item["selection_rank"], item["name"].casefold(),
    )


def build_comparison(selected, existing, directions):
    result = {"improvements": [], "regressions": [], "differences": []}
    if not selected or not isinstance(existing, dict) or not isinstance(existing.get("features"), dict):
        return result
    directions = directions if isinstance(directions, dict) else {}
    for field, direction in directions.items():
        has_new, new = path_get(selected["features"], field)
        has_old, old = path_get(existing["features"], field)
        if not has_new or not has_old or new == old:
            continue
        entry = {"feature": field, "selected_value": new, "existing_value": old}
        new_num, old_num = number(new), number(old)
        if direction == "higher" and new_num is not None and old_num is not None:
            result["improvements" if new_num > old_num else "regressions"].append(entry)
        elif direction == "lower" and new_num is not None and old_num is not None:
            result["improvements" if new_num < old_num else "regressions"].append(entry)
        else:
            result["differences"].append(entry)
    return result


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        emit({"ok": False, "errors": ["invalid JSON: " + str(exc)]})
        return
    if not isinstance(payload, dict):
        emit({"ok": False, "errors": ["top-level JSON value must be an object"]})
        return
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        emit({"ok": False, "errors": ["candidates must be a non-empty array"]})
        return
    requirements = payload.get("requirements", {})
    customer = payload.get("customer_facts", {})
    errors = []
    if not isinstance(requirements, dict):
        errors.append("requirements must be an object"); requirements = {}
    if not isinstance(customer, dict):
        errors.append("customer_facts must be an object"); customer = {}
    for key in ("required_features", "min_features", "max_features"):
        if key in requirements and not isinstance(requirements[key], dict):
            errors.append("requirements." + key + " must be an object"); requirements[key] = {}
    as_of = parse_date(payload.get("as_of")) if payload.get("as_of") is not None else None
    if payload.get("as_of") is not None and as_of is None:
        errors.append("as_of must be an ISO-8601 date or timestamp")
    names, evaluated = set(), []
    for candidate in candidates:
        if not isinstance(candidate, dict) or not isinstance(candidate.get("name"), str) or not candidate["name"].strip():
            errors.append("each candidate must have a non-empty string name"); continue
        if candidate["name"] in names:
            errors.append("candidate names must be unique: " + candidate["name"]); continue
        names.add(candidate["name"])
        evaluated.append(evaluate(candidate, customer, requirements, as_of))
    if errors:
        emit({"ok": False, "errors": errors}); return
    qualified = sorted((x for x in evaluated if x["status"] == "qualified"), key=rank_key)
    conditional = sorted((x for x in evaluated if x["status"] == "conditional"), key=rank_key)
    excluded = sorted((x for x in evaluated if x["status"] == "excluded"), key=lambda x: x["name"].casefold())
    selected = qualified[0] if qualified else None
    pending = []
    for item in payload.get("opening_prerequisites", []):
        if isinstance(item, dict) and not item.get("confirmed", False) and isinstance(item.get("name"), str):
            pending.append(item["name"])
    emit({
        "ok": True,
        "as_of_used": as_of.isoformat() if as_of else None,
        "recommendation": selected["name"] if selected else None,
        "recommendation_basis": "active promotional priority, then preference_score and selection_rank" if selected else None,
        "qualified_candidates": qualified,
        "conditional_candidates": conditional,
        "excluded_candidates": excluded,
        "comparison_to_existing": build_comparison(selected, payload.get("existing_account"), payload.get("comparison_directions")),
        "opening_prerequisites_to_verify": pending,
    })


if __name__ == "__main__":
    main()
