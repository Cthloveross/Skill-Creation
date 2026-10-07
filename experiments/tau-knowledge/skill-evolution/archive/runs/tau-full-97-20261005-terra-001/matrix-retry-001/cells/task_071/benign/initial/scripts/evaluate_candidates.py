#!/usr/bin/env python3
"""Deterministically filter normalized account candidates.

Read JSON from stdin and write JSON to stdout. See SKILL.md for the schema.
This helper intentionally knows no product names, rates, or task-instance facts.
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any


def as_decimal(value: Any) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def parse_day(value: Any) -> date | None:
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


def active_promotion(candidate: dict[str, Any], as_of: date | None) -> tuple[bool, int | None]:
    promo = candidate.get("promotion")
    if not isinstance(promo, dict):
        return False, None
    rank = promo.get("rank")
    if not isinstance(rank, int) or isinstance(rank, bool):
        return False, None
    start = parse_day(promo.get("start"))
    end = parse_day(promo.get("end"))
    if as_of is None or start is None or end is None or start > end:
        return False, None
    return start <= as_of <= end, rank


def normalize_equal(value: Any) -> Any:
    # JSON values are compared predictably while preserving booleans distinctly.
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    return value


def main(payload: Any) -> dict[str, Any]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return {"errors": ["input must be a JSON object"], "confirmed_matches": [],
                "needs_confirmation": [], "excluded": [], "recommended_order": []}

    requirements = payload.get("requirements", {})
    candidates = payload.get("candidates", [])
    if not isinstance(requirements, dict):
        errors.append("requirements must be an object")
        requirements = {}
    if not isinstance(candidates, list):
        errors.append("candidates must be an array")
        candidates = []

    numeric_min = requirements.get("numeric_min", {})
    numeric_max = requirements.get("numeric_max", {})
    equals = requirements.get("equals", {})
    preferences = requirements.get("preferences", [])
    for label, value in (("numeric_min", numeric_min), ("numeric_max", numeric_max), ("equals", equals)):
        if not isinstance(value, dict):
            errors.append(f"requirements.{label} must be an object")
    if not isinstance(numeric_min, dict):
        numeric_min = {}
    if not isinstance(numeric_max, dict):
        numeric_max = {}
    if not isinstance(equals, dict):
        equals = {}
    if not isinstance(preferences, list):
        errors.append("requirements.preferences must be an array")
        preferences = []

    as_of = parse_day(payload.get("as_of"))
    if payload.get("as_of") is not None and as_of is None:
        errors.append("as_of must be an ISO-8601 date or timestamp")

    confirmed: list[dict[str, Any]] = []
    needs_confirmation: list[dict[str, Any]] = []
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
        status = candidate.get("eligibility", "eligible")
        if status not in {"eligible", "unknown", "ineligible"}:
            errors.append(f"candidate {identifier}: eligibility must be eligible, unknown, or ineligible")
            status = "unknown"
        if status == "ineligible":
            failed.append("eligibility")
        elif status == "unknown":
            unknown.append("eligibility")

        for field, required in numeric_min.items():
            actual = as_decimal(facts.get(field))
            expected = as_decimal(required)
            if expected is None:
                errors.append(f"numeric_min.{field} must be numeric")
            elif actual is None:
                unknown.append(field)
            elif actual < expected:
                failed.append(field)

        for field, required in numeric_max.items():
            actual = as_decimal(facts.get(field))
            expected = as_decimal(required)
            if expected is None:
                errors.append(f"numeric_max.{field} must be numeric")
            elif actual is None:
                unknown.append(field)
            elif actual > expected:
                failed.append(field)

        for field, required in equals.items():
            if field not in facts or facts[field] is None:
                unknown.append(field)
            elif normalize_equal(facts[field]) != normalize_equal(required):
                failed.append(field)

        record: dict[str, Any] = {
            "id": identifier,
            "name": candidate.get("name", identifier),
            "failed_constraints": sorted(set(failed)),
            "unknown_constraints": sorted(set(unknown)),
        }
        if failed:
            excluded.append(record)
            continue
        if unknown:
            needs_confirmation.append(record)
            continue

        score = Decimal("0")
        for preference in preferences:
            if not isinstance(preference, dict):
                errors.append("each preference must be an object")
                continue
            field = preference.get("field")
            direction = preference.get("direction")
            weight = as_decimal(preference.get("weight", 1))
            actual = as_decimal(facts.get(field)) if isinstance(field, str) else None
            if direction not in {"higher", "lower"} or weight is None:
                errors.append("each preference needs a field, direction of higher/lower, and numeric weight")
                continue
            if actual is not None:
                score += actual * weight * (Decimal("1") if direction == "higher" else Decimal("-1"))

        promotion_is_active, promotion_rank = active_promotion(candidate, as_of)
        record["preference_score"] = str(score)
        record["active_promotion_rank"] = promotion_rank if promotion_is_active else None
        confirmed.append(record)

    # Active promotions are a tie-breaker only among confirmed matches. Unpromoted
    # candidates sort after active ranked promotions; preferences resolve each group.
    def sort_key(item: dict[str, Any]) -> tuple[int, int, Decimal, str]:
        rank = item["active_promotion_rank"]
        return (
            0 if rank is not None else 1,
            rank if rank is not None else 10**9,
            -Decimal(item["preference_score"]),
            item["id"],
        )

    confirmed.sort(key=sort_key)
    return {
        "errors": errors,
        "confirmed_matches": confirmed,
        "needs_confirmation": needs_confirmation,
        "excluded": excluded,
        "recommended_order": [item["id"] for item in confirmed],
    }


if __name__ == "__main__":
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
        result = main(payload)
    except json.JSONDecodeError as exc:
        result = {"errors": [f"invalid JSON: {exc.msg}"], "confirmed_matches": [],
                  "needs_confirmation": [], "excluded": [], "recommended_order": []}
    except Exception as exc:  # Keep the declared JSON-only interface on malformed input.
        result = {"errors": [f"unexpected evaluator error: {type(exc).__name__}"],
                  "confirmed_matches": [], "needs_confirmation": [], "excluded": [],
                  "recommended_order": []}
    print(json.dumps(result, sort_keys=True))
