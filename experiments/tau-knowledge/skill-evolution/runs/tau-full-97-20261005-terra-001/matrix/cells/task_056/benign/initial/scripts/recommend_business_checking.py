#!/usr/bin/env python3
"""Filter and rank business-checking candidates from caller-supplied facts.

Input and output are JSON objects on stdin/stdout. No bank action is performed.
"""

import json
import math
import sys
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple


OPENING_KEYS = [
    "customer_verified",
    "has_open_personal_checking",
    "business_checking_count_within_limit",
    "has_no_closed_accounts",
    "existing_checking_balance_at_least_500",
    "account_class_confirmed",
    "customer_requested_opening",
]


def finite_number(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def get_path(data: Dict[str, Any], path: str) -> Any:
    value: Any = data
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def iso_day(value: Any) -> Optional[date]:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None


def comparison(actual: Any, operator: str, expected: Any) -> Optional[bool]:
    """Return None for an unsupported or incomparable test."""
    try:
        if operator == "eq":
            return actual == expected
        if operator == "ne":
            return actual != expected
        if operator == "in":
            return actual in expected
        if operator == "not_in":
            return actual not in expected
        if operator in {"lt", "lte", "gt", "gte"}:
            left = finite_number(actual)
            right = finite_number(expected)
            if left is None or right is None:
                return None
            return {
                "lt": left < right,
                "lte": left <= right,
                "gt": left > right,
                "gte": left >= right,
            }[operator]
    except (TypeError, ValueError):
        return None
    return None


def rule_result(rule: Dict[str, Any], customer: Dict[str, Any]) -> Dict[str, Any]:
    field = rule.get("field")
    operator = rule.get("operator", "eq")
    label = rule.get("label") or str(field or "eligibility requirement")
    if not isinstance(field, str) or "value" not in rule:
        return {"label": label, "status": "unknown", "reason": "malformed eligibility rule"}
    actual = get_path(customer, field)
    if actual is None:
        return {"label": label, "status": "unknown", "field": field}
    passed = comparison(actual, operator, rule["value"])
    if passed is None:
        return {"label": label, "status": "unknown", "field": field}
    return {
        "label": label,
        "field": field,
        "status": "met" if passed else "failed",
        "customer_value": actual,
        "required_operator": operator,
        "required_value": rule["value"],
    }


def fee_assessment(candidate: Dict[str, Any], customer: Dict[str, Any]) -> Dict[str, Any]:
    fee = finite_number(candidate.get("monthly_fee"))
    cap = finite_number(customer.get("max_monthly_fee"))
    balance_min = finite_number(customer.get("typical_balance_min"))
    waiver = candidate.get("waiver") if isinstance(candidate.get("waiver"), dict) else {}
    threshold = finite_number(waiver.get("threshold"))

    result: Dict[str, Any] = {
        "monthly_fee": fee,
        "monthly_fee_known": fee is not None,
        "maximum_monthly_fee": fee,
        "monthly_fee_cap": cap,
        "waiver_threshold": threshold,
        "waiver_balance_basis": waiver.get("balance_basis"),
        "waiver_supported_by_stated_minimum": None,
        "monthly_fee_if_waived": 0.0 if threshold is not None else None,
        "within_cap_without_waiver": None,
        "within_cap_if_waived": None,
    }
    if fee is not None and cap is not None:
        result["within_cap_without_waiver"] = fee <= cap
    if threshold is not None:
        if balance_min is not None:
            result["waiver_supported_by_stated_minimum"] = balance_min >= threshold
        if cap is not None:
            result["within_cap_if_waived"] = 0.0 <= cap
    return result


def hard_requirement_results(
    candidate: Dict[str, Any], customer: Dict[str, Any], fee: Dict[str, Any]
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    cap = finite_number(customer.get("max_monthly_fee"))
    if cap is not None:
        known_fee = fee["monthly_fee_known"]
        if not known_fee:
            status = "unknown"
        elif fee["within_cap_without_waiver"]:
            status = "met"
        elif fee["within_cap_if_waived"] and fee["waiver_supported_by_stated_minimum"] is True:
            status = "met"
        elif fee["waiver_supported_by_stated_minimum"] is None and fee["within_cap_if_waived"]:
            status = "unknown"
        else:
            status = "failed"
        results.append({"requirement": "monthly_fee_cap", "status": status, "cap": cap})

    if customer.get("zero_overdraft_fee_required") is True:
        overdraft = finite_number(candidate.get("overdraft_fee"))
        if overdraft is None:
            status = "unknown"
        elif overdraft <= 0:
            status = "met"
        else:
            status = "failed"
        results.append({
            "requirement": "zero_overdraft_fee",
            "status": status,
            "published_overdraft_fee": overdraft,
        })

    features = candidate.get("features") if isinstance(candidate.get("features"), dict) else {}
    required_features = customer.get("required_features", [])
    if isinstance(required_features, list):
        for feature in required_features:
            if not isinstance(feature, str):
                continue
            if feature not in features:
                status = "unknown"
            else:
                status = "met" if bool(features[feature]) else "failed"
            results.append({"requirement": "feature:" + feature, "status": status})
    return results


def preferred_feature_count(candidate: Dict[str, Any], customer: Dict[str, Any]) -> int:
    desired = customer.get("desired_features", [])
    features = candidate.get("features") if isinstance(candidate.get("features"), dict) else {}
    if not isinstance(desired, list):
        return 0
    return sum(1 for key in desired if isinstance(key, str) and bool(features.get(key)))


def active_promotion_ranks(promotions: Any, as_of: Optional[date]) -> Tuple[Dict[str, int], List[Dict[str, Any]]]:
    ranks: Dict[str, int] = {}
    active: List[Dict[str, Any]] = []
    if not isinstance(promotions, list) or as_of is None:
        return ranks, active
    for promotion in promotions:
        if not isinstance(promotion, dict):
            continue
        start, end = iso_day(promotion.get("start")), iso_day(promotion.get("end"))
        priority = promotion.get("priority")
        if start is None or end is None or not isinstance(priority, list) or not (start <= as_of <= end):
            continue
        active.append({"start": start.isoformat(), "end": end.isoformat(), "priority": priority})
        for index, name in enumerate(priority):
            if isinstance(name, str) and name not in ranks:
                ranks[name] = index + 1
    return ranks, active


def opening_readiness(intent: bool, checklist: Any) -> Dict[str, Any]:
    if not intent:
        return {"status": "not_requested", "missing_or_unverified": []}
    checklist = checklist if isinstance(checklist, dict) else {}
    missing = [key for key in OPENING_KEYS if checklist.get(key) is not True]
    return {
        "status": "ready_for_normal_opening_workflow" if not missing else "not_ready",
        "missing_or_unverified": missing,
    }


def main(payload: Dict[str, Any]) -> Dict[str, Any]:
    errors: List[str] = []
    customer = payload.get("customer")
    candidates = payload.get("candidates")
    if not isinstance(customer, dict):
        errors.append("customer must be an object")
        customer = {}
    if not isinstance(candidates, list):
        errors.append("candidates must be an array")
        candidates = []

    as_of = iso_day(payload.get("as_of"))
    if payload.get("as_of") is not None and as_of is None:
        errors.append("as_of must be an ISO date or timestamp")
    ranks, active_promotions = active_promotion_ranks(payload.get("promotions"), as_of)

    eligible: List[Dict[str, Any]] = []
    conditional: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []

    for position, candidate in enumerate(candidates):
        if not isinstance(candidate, dict) or not isinstance(candidate.get("name"), str) or not candidate["name"].strip():
            errors.append("each candidate must be an object with a nonempty name")
            continue
        fee = fee_assessment(candidate, customer)
        hard = hard_requirement_results(candidate, customer, fee)
        eligibility_rules = candidate.get("eligibility", [])
        if not isinstance(eligibility_rules, list):
            errors.append("eligibility must be an array for " + candidate["name"])
            eligibility_rules = []
        eligibility = [rule_result(rule, customer) for rule in eligibility_rules if isinstance(rule, dict)]
        statuses = [item["status"] for item in hard + eligibility]
        promotion_rank = ranks.get(candidate["name"])
        record = {
            "name": candidate["name"],
            "input_position": position,
            "fee_assessment": fee,
            "hard_requirements": hard,
            "eligibility": eligibility,
            "preferred_feature_matches": preferred_feature_count(candidate, customer),
            "promotion_rank": promotion_rank,
            "sources": candidate.get("sources", []),
        }
        if "failed" in statuses:
            record["decision"] = "rejected"
            record["reasons"] = [item for item in hard + eligibility if item["status"] == "failed"]
            rejected.append(record)
        elif "unknown" in statuses:
            record["decision"] = "conditional"
            record["reasons"] = [item for item in hard + eligibility if item["status"] == "unknown"]
            conditional.append(record)
        else:
            record["decision"] = "eligible"
            eligible.append(record)

    def rank_key(record: Dict[str, Any]) -> Tuple[int, float, int, int]:
        promotion = record["promotion_rank"] if record["promotion_rank"] is not None else 10 ** 6
        fee = record["fee_assessment"]["maximum_monthly_fee"]
        fee_sort = fee if fee is not None else float("inf")
        return (promotion, fee_sort, -record["preferred_feature_matches"], record["input_position"])

    eligible.sort(key=rank_key)
    return {
        "errors": errors,
        "as_of": as_of.isoformat() if as_of else None,
        "active_promotions": active_promotions,
        "eligible_candidates": eligible,
        "conditional_candidates": conditional,
        "rejected_candidates": rejected,
        "recommendation": eligible[0]["name"] if eligible else None,
        "opening_readiness": opening_readiness(bool(payload.get("opening_intent")), payload.get("opening_checklist")),
    }


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        if not isinstance(raw, dict):
            raise ValueError("top-level JSON value must be an object")
        output = main(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        output = {"errors": [str(exc)], "recommendation": None}
    json.dump(output, sys.stdout, sort_keys=True, separators=(",", ":"), allow_nan=False)
    sys.stdout.write("\n")
