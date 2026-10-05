#!/usr/bin/env python3
"""Filter normalized product candidates without embedded account-specific facts.

Reads one JSON object from stdin and emits one JSON object on stdout. See SKILL.md.
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

EMPTY = {
    "confirmed_matches": [],
    "needs_confirmation": [],
    "excluded": [],
    "recommended_order": [],
}


def decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def day(value: Any) -> date | None:
    if value is None:
        return None
    text = str(value).strip()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None


def active_rank(candidate: dict[str, Any], as_of: date | None) -> int | None:
    promotion = candidate.get("promotion")
    if not isinstance(promotion, dict) or as_of is None:
        return None
    rank = promotion.get("rank")
    start, end = day(promotion.get("start")), day(promotion.get("end"))
    if isinstance(rank, bool) or not isinstance(rank, int) or not start or not end or start > end:
        return None
    return rank if start <= as_of <= end else None


def equivalent(left: Any, right: Any) -> bool:
    if isinstance(left, (dict, list)) or isinstance(right, (dict, list)):
        return json.dumps(left, sort_keys=True) == json.dumps(right, sort_keys=True)
    return left == right


def evaluate(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"errors": ["input must be a JSON object"], **EMPTY}
    errors: list[str] = []
    req = payload.get("requirements", {})
    candidates = payload.get("candidates", [])
    if not isinstance(req, dict):
        errors.append("requirements must be an object")
        req = {}
    if not isinstance(candidates, list):
        errors.append("candidates must be an array")
        candidates = []
    minima = req.get("numeric_min", {})
    maxima = req.get("numeric_max", {})
    equalities = req.get("equals", {})
    for label, value in (("numeric_min", minima), ("numeric_max", maxima), ("equals", equalities)):
        if not isinstance(value, dict):
            errors.append(f"requirements.{label} must be an object")
    minima = minima if isinstance(minima, dict) else {}
    maxima = maxima if isinstance(maxima, dict) else {}
    equalities = equalities if isinstance(equalities, dict) else {}
    as_of = day(payload.get("as_of"))
    if payload.get("as_of") is not None and as_of is None:
        errors.append("as_of must be an ISO-8601 date or timestamp")

    confirmed: list[dict[str, Any]] = []
    uncertain: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            errors.append(f"candidates[{index}] must be an object")
            continue
        identifier = candidate.get("id")
        if not isinstance(identifier, str) or not identifier:
            errors.append(f"candidates[{index}].id must be a nonempty string")
            continue
        facts = candidate.get("facts", {})
        if not isinstance(facts, dict):
            errors.append(f"candidate {identifier}: facts must be an object")
            facts = {}
        failed: list[str] = []
        unknown: list[str] = []
        eligibility = candidate.get("eligibility", "eligible")
        if eligibility not in {"eligible", "unknown", "ineligible"}:
            errors.append(f"candidate {identifier}: invalid eligibility")
            eligibility = "unknown"
        if eligibility == "ineligible":
            failed.append("eligibility")
        elif eligibility == "unknown":
            unknown.append("eligibility")
        for field, needed in minima.items():
            actual, target = decimal(facts.get(field)), decimal(needed)
            if target is None:
                errors.append(f"numeric_min.{field} must be numeric")
            elif actual is None:
                unknown.append(field)
            elif actual < target:
                failed.append(field)
        for field, needed in maxima.items():
            actual, target = decimal(facts.get(field)), decimal(needed)
            if target is None:
                errors.append(f"numeric_max.{field} must be numeric")
            elif actual is None:
                unknown.append(field)
            elif actual > target:
                failed.append(field)
        for field, needed in equalities.items():
            if field not in facts or facts[field] is None:
                unknown.append(field)
            elif not equivalent(facts[field], needed):
                failed.append(field)
        record = {
            "id": identifier,
            "name": candidate.get("name", identifier),
            "failed_constraints": sorted(set(failed)),
            "unknown_constraints": sorted(set(unknown)),
        }
        if failed:
            excluded.append(record)
        elif unknown:
            uncertain.append(record)
        else:
            record["active_promotion_rank"] = active_rank(candidate, as_of)
            confirmed.append(record)
    confirmed.sort(key=lambda item: (
        item["active_promotion_rank"] is None,
        item["active_promotion_rank"] if item["active_promotion_rank"] is not None else 10**9,
        item["id"],
    ))
    return {
        "errors": errors,
        "confirmed_matches": confirmed,
        "needs_confirmation": uncertain,
        "excluded": excluded,
        "recommended_order": [item["id"] for item in confirmed],
    }


if __name__ == "__main__":
    try:
        raw = sys.stdin.read()
        output = evaluate(json.loads(raw) if raw.strip() else {})
    except json.JSONDecodeError as exc:
        output = {"errors": [f"invalid JSON: {exc.msg}"], **EMPTY}
    except Exception as exc:
        output = {"errors": [f"unexpected evaluator error: {type(exc).__name__}"], **EMPTY}
    print(json.dumps(output, sort_keys=True))
