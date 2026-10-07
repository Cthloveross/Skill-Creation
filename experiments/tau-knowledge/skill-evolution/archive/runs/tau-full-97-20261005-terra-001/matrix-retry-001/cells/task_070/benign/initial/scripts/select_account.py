#!/usr/bin/env python3
"""Deterministically select one eligible candidate from structured account evidence.

Reads a JSON object from stdin and emits a JSON result to stdout.  This module uses
only the Python standard library and deliberately does not perform banking actions.
"""

import json
import sys
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple


VALID_OPS = {"eq", "gte", "lte", "contains", "in"}
VALID_STATUSES = {"true", "false", "unknown"}


def parse_date(value: Any, field: str) -> date:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a nonempty date string")
    text = value.strip()
    try:
        return date.fromisoformat(text[:10])
    except ValueError as exc:
        raise ValueError(f"{field} must begin with an ISO date (YYYY-MM-DD)") from exc


def compare(actual: Any, op: str, expected: Any) -> bool:
    if op == "eq":
        return actual == expected
    if op == "gte":
        try:
            return actual >= expected
        except TypeError:
            return False
    if op == "lte":
        try:
            return actual <= expected
        except TypeError:
            return False
    if op == "contains":
        try:
            return expected in actual
        except TypeError:
            return False
    if op == "in":
        try:
            return actual in expected
        except TypeError:
            return False
    return False


def validate_request(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    parse_date(payload.get("as_of"), "as_of")
    requirements = payload.get("requirements")
    candidates = payload.get("candidates")
    if not isinstance(requirements, list):
        raise ValueError("requirements must be a list")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("candidates must be a nonempty list")
    for index, requirement in enumerate(requirements):
        if not isinstance(requirement, dict):
            raise ValueError(f"requirements[{index}] must be an object")
        if not isinstance(requirement.get("key"), str) or not requirement["key"]:
            raise ValueError(f"requirements[{index}].key must be a nonempty string")
        op = requirement.get("op", "eq")
        if op not in VALID_OPS:
            raise ValueError(f"requirements[{index}].op must be one of {sorted(VALID_OPS)}")
        if "value" not in requirement:
            raise ValueError(f"requirements[{index}].value is required")
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            raise ValueError(f"candidates[{index}] must be an object")
        if not isinstance(candidate.get("name"), str) or not candidate["name"].strip():
            raise ValueError(f"candidates[{index}].name must be a nonempty string")
        if not isinstance(candidate.get("attributes", {}), dict):
            raise ValueError(f"candidates[{index}].attributes must be an object")
        if not isinstance(candidate.get("eligibility", []), list):
            raise ValueError(f"candidates[{index}].eligibility must be a list")
        for item in candidate.get("eligibility", []):
            if not isinstance(item, dict) or item.get("status") not in VALID_STATUSES:
                raise ValueError("each eligibility item requires status true, false, or unknown")
    promotion = payload.get("promotion")
    if promotion is not None:
        if not isinstance(promotion, dict):
            raise ValueError("promotion must be an object when supplied")
        parse_date(promotion.get("start"), "promotion.start")
        parse_date(promotion.get("end"), "promotion.end")
        if not isinstance(promotion.get("priority"), list) or not all(
            isinstance(name, str) for name in promotion["priority"]
        ):
            raise ValueError("promotion.priority must be a list of account names")
    return payload


def assess_candidate(candidate: Dict[str, Any], requirements: List[Dict[str, Any]]) -> Tuple[bool, List[str]]:
    reasons: List[str] = []
    attributes = candidate.get("attributes", {})
    for requirement in requirements:
        if not requirement.get("hard", True):
            continue
        key = requirement["key"]
        if key not in attributes:
            reasons.append(f"missing required attribute: {key}")
            continue
        if not compare(attributes[key], requirement.get("op", "eq"), requirement["value"]):
            reasons.append(f"does not satisfy {key} {requirement.get('op', 'eq')} {requirement['value']}")
    for condition in candidate.get("eligibility", []):
        status = condition["status"]
        if status != "true":
            key = condition.get("key", "required eligibility condition")
            detail = condition.get("reason")
            suffix = f" ({detail})" if isinstance(detail, str) and detail else ""
            reasons.append(f"eligibility {status}: {key}{suffix}")
    return (not reasons), reasons


def promotion_is_active(promotion: Optional[Dict[str, Any]], as_of: date) -> bool:
    if not promotion:
        return False
    return parse_date(promotion["start"], "promotion.start") <= as_of <= parse_date(promotion["end"], "promotion.end")


def candidate_summary(candidate: Dict[str, Any], promotion_rank: Optional[int]) -> Dict[str, Any]:
    return {
        "name": candidate["name"],
        "attributes": candidate.get("attributes", {}),
        "sources": candidate.get("sources", []),
        "soft_score": candidate.get("soft_score", 0),
        "promotion_rank": promotion_rank,
    }


def main() -> None:
    try:
        payload = validate_request(json.load(sys.stdin))
        as_of = parse_date(payload["as_of"], "as_of")
        promotion = payload.get("promotion")
        active = promotion_is_active(promotion, as_of)
        priority = promotion.get("priority", []) if active and promotion else []
        ranks = {name: index for index, name in enumerate(priority)}

        qualified: List[Dict[str, Any]] = []
        excluded: List[Dict[str, Any]] = []
        for candidate in payload["candidates"]:
            qualifies, reasons = assess_candidate(candidate, payload["requirements"])
            if qualifies:
                qualified.append(candidate)
            else:
                excluded.append({"name": candidate["name"], "reasons": reasons})

        recommended = None
        if qualified:
            # Promotion ordering is primary only for products specifically named in an
            # active promotion. Other qualifiers remain possible but rank after them.
            def sort_key(candidate: Dict[str, Any]) -> Tuple[int, int, str]:
                promotion_bucket = ranks.get(candidate["name"], len(priority) + 1)
                raw_score = candidate.get("soft_score", 0)
                if not isinstance(raw_score, (int, float)):
                    raw_score = 0
                return (promotion_bucket, -raw_score, candidate["name"].casefold())

            selected = sorted(qualified, key=sort_key)[0]
            recommended = candidate_summary(selected, ranks.get(selected["name"]))

        result = {
            "as_of": as_of.isoformat(),
            "promotion_active": active,
            "promotion_priority": priority if active else [],
            "recommended": recommended,
            "qualified": [candidate_summary(item, ranks.get(item["name"])) for item in qualified],
            "excluded": excluded,
        }
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, sort_keys=True), file=sys.stdout)
        sys.exit(2)


if __name__ == "__main__":
    main()
