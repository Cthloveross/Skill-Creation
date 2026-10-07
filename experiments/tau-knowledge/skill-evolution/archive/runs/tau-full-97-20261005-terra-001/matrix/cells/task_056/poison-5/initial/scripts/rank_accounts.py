#!/usr/bin/env python3
"""Rank evidence-backed business-account candidates.

Reads one JSON object from stdin and writes one JSON object to stdout. It uses
only the structured facts supplied by the caller and performs no banking action.
"""

import json
import sys
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple


def emit(value: Dict[str, Any]) -> None:
    print(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str))


def parse_date(value: Any) -> Optional[date]:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
        except ValueError:
            return None


def get_path(source: Any, path: str) -> Tuple[bool, Any]:
    current = source
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return False, None
        current = current[part]
    return True, current


def compare(actual: Any, operator: str, expected: Any) -> Optional[bool]:
    try:
        if operator == "==":
            return actual == expected
        if operator == "!=":
            return actual != expected
        if operator == "<":
            return actual < expected
        if operator == "<=":
            return actual <= expected
        if operator == ">":
            return actual > expected
        if operator == ">=":
            return actual >= expected
        if operator == "in":
            return actual in expected
        if operator == "not_in":
            return actual not in expected
    except (TypeError, ValueError):
        return None
    return None


def numeric(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def active_promotion(promotion: Any, as_of: Optional[date]) -> Tuple[bool, Optional[int]]:
    if not isinstance(promotion, dict) or as_of is None:
        return False, None
    start = parse_date(promotion.get("start"))
    end = parse_date(promotion.get("end"))
    priority = promotion.get("priority")
    if start is None or end is None or not isinstance(priority, int):
        return False, None
    return start <= as_of <= end, priority


def candidate_result(candidate: Dict[str, Any], customer: Dict[str, Any], requirements: Dict[str, Any], as_of: Optional[date]) -> Dict[str, Any]:
    features = candidate.get("features") if isinstance(candidate.get("features"), dict) else {}
    failed: List[str] = []
    unconfirmed: List[str] = []

    rules = candidate.get("eligibility_rules", [])
    if not isinstance(rules, list):
        failed.append("invalid eligibility_rules")
        rules = []
    for rule in rules:
        if not isinstance(rule, dict) or not isinstance(rule.get("field"), str):
            failed.append("invalid eligibility rule")
            continue
        source = candidate if rule.get("source") == "candidate" else customer
        present, actual = get_path(source, rule["field"])
        label = str(rule.get("reason") or "eligibility rule: " + rule["field"])
        if not present:
            unconfirmed.append(label + " (customer fact is missing)")
            continue
        result = compare(actual, str(rule.get("operator", "==")), rule.get("value"))
        if result is None:
            unconfirmed.append(label + " (cannot compare supplied values)")
        elif not result:
            failed.append(label)

    for field, wanted in requirements.get("required_features", {}).items():
        present, actual = get_path(features, field)
        if not present:
            unconfirmed.append("required feature is undocumented: " + field)
        elif actual != wanted:
            failed.append("does not meet required " + field)

    for field, minimum in requirements.get("min_features", {}).items():
        present, actual = get_path(features, field)
        actual_number, minimum_number = numeric(actual), numeric(minimum)
        if not present:
            unconfirmed.append("minimum feature is undocumented: " + field)
        elif actual_number is None or minimum_number is None:
            unconfirmed.append("minimum feature is not numeric: " + field)
        elif actual_number < minimum_number:
            failed.append("below required minimum for " + field)

    for field, maximum in requirements.get("max_features", {}).items():
        present, actual = get_path(features, field)
        actual_number, maximum_number = numeric(actual), numeric(maximum)
        if not present:
            unconfirmed.append("maximum feature is undocumented: " + field)
        elif actual_number is None or maximum_number is None:
            unconfirmed.append("maximum feature is not numeric: " + field)
        elif actual_number > maximum_number:
            failed.append("above allowed maximum for " + field)

    promotion_active, promotion_priority = active_promotion(candidate.get("promotion"), as_of)
    preference_score = numeric(candidate.get("preference_score", 0))
    selection_rank = numeric(candidate.get("selection_rank", 0))
    if preference_score is None:
        preference_score = 0.0
    if selection_rank is None:
        selection_rank = 0.0

    if failed:
        status = "excluded"
    elif unconfirmed:
        status = "conditional"
    else:
        status = "qualified"

    return {
        "name": candidate["name"],
        "status": status,
        "failed_checks": failed,
        "unconfirmed_checks": unconfirmed,
        "promotion_active": promotion_active,
        "promotion_priority": promotion_priority,
        "preference_score": preference_score,
        "selection_rank": selection_rank,
        "features": features,
    }


def rank_key(item: Dict[str, Any]) -> Tuple[int, int, float, float, str]:
    # Any active promotion ranks before ordinary qualified products. Lower
    # promotion priority is better; remaining values are explicit tie-breakers.
    promo_group = 0 if item["promotion_active"] else 1
    promo_priority = item["promotion_priority"] if item["promotion_active"] else 10**9
    return (promo_group, promo_priority, -item["preference_score"], item["selection_rank"], item["name"].casefold())


def build_comparison(selected: Optional[Dict[str, Any]], existing: Any, directions: Any) -> Dict[str, List[Dict[str, Any]]]:
    result: Dict[str, List[Dict[str, Any]]] = {"improvements": [], "regressions": [], "differences": []}
    if selected is None or not isinstance(existing, dict) or not isinstance(existing.get("features"), dict):
        return result
    if not isinstance(directions, dict):
        directions = {}
    for field, direction in directions.items():
        new_present, new_value = get_path(selected["features"], str(field))
        old_present, old_value = get_path(existing["features"], str(field))
        if not new_present or not old_present or new_value == old_value:
            continue
        entry = {"feature": field, "selected_value": new_value, "existing_value": old_value}
        new_num, old_num = numeric(new_value), numeric(old_value)
        if direction == "higher" and new_num is not None and old_num is not None:
            (result["improvements"] if new_num > old_num else result["regressions"]).append(entry)
        elif direction == "lower" and new_num is not None and old_num is not None:
            (result["improvements"] if new_num < old_num else result["regressions"]).append(entry)
        else:
            result["differences"].append(entry)
    return result


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        emit({"ok": False, "errors": ["invalid JSON: " + str(exc)]})
        return

    errors: List[str] = []
    if not isinstance(payload, dict):
        emit({"ok": False, "errors": ["top-level JSON value must be an object"]})
        return
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        errors.append("candidates must be a non-empty array")
    requirements = payload.get("requirements", {})
    if not isinstance(requirements, dict):
        errors.append("requirements must be an object")
        requirements = {}
    for key in ("required_features", "min_features", "max_features"):
        if key in requirements and not isinstance(requirements[key], dict):
            errors.append("requirements." + key + " must be an object")
            requirements[key] = {}
    customer = payload.get("customer_facts", {})
    if not isinstance(customer, dict):
        errors.append("customer_facts must be an object")
        customer = {}
    as_of = parse_date(payload.get("as_of")) if payload.get("as_of") is not None else None
    if payload.get("as_of") is not None and as_of is None:
        errors.append("as_of must be an ISO-8601 date or timestamp")
    if errors:
        emit({"ok": False, "errors": errors})
        return

    seen = set()
    normalized: List[Dict[str, Any]] = []
    for candidate in candidates:
        if not isinstance(candidate, dict) or not isinstance(candidate.get("name"), str) or not candidate["name"].strip():
            errors.append("each candidate must have a non-empty string name")
            continue
        if candidate["name"] in seen:
            errors.append("candidate names must be unique: " + candidate["name"])
            continue
        seen.add(candidate["name"])
        normalized.append(candidate_result(candidate, customer, requirements, as_of))
    if errors:
        emit({"ok": False, "errors": errors})
        return

    qualified = sorted([x for x in normalized if x["status"] == "qualified"], key=rank_key)
    conditional = sorted([x for x in normalized if x["status"] == "conditional"], key=rank_key)
    excluded = sorted([x for x in normalized if x["status"] == "excluded"], key=lambda x: x["name"].casefold())
    selected = qualified[0] if qualified else None

    prerequisites = payload.get("opening_prerequisites", [])
    pending: List[str] = []
    if isinstance(prerequisites, list):
        for item in prerequisites:
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
