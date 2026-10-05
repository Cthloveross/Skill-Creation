#!/usr/bin/env python3
"""Compare caller-extracted product facts with stated numeric requirements.

Reads one JSON object from stdin and emits one JSON object to stdout. This helper
never retrieves documents, infers missing facts, resolves source conflicts, or
establishes product eligibility.
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


def numeric(value: Any) -> Decimal | None:
    """Return a finite Decimal, preserving zero as a known valid value."""
    if value is None or isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() else None


def parse_date(value: Any) -> date | None:
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


def active_promotion_rank(candidate: dict[str, Any], as_of: date | None) -> int | None:
    promotion = candidate.get("promotion")
    if as_of is None or not isinstance(promotion, dict):
        return None
    rank = promotion.get("rank")
    start = parse_date(promotion.get("start"))
    end = parse_date(promotion.get("end"))
    if isinstance(rank, bool) or not isinstance(rank, int) or not start or not end or start > end:
        return None
    return rank if start <= as_of <= end else None


def compare_numeric(
    facts: dict[str, Any],
    constraints: dict[str, Any],
    direction: str,
    missing: list[str],
    failed: list[str],
    errors: list[str],
    path: str,
) -> None:
    for field, target in constraints.items():
        required = numeric(target)
        actual = numeric(facts.get(field))
        if required is None:
            errors.append(f"{path}.{field} must be numeric")
        elif actual is None:
            missing.append(field)
        elif (direction == "minimum" and actual < required) or (
            direction == "maximum" and actual > required
        ):
            failed.append(field)


def evaluate(payload: Any) -> dict[str, Any]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return {"errors": ["input must be a JSON object"], **EMPTY}

    requirements = payload.get("requirements", {})
    candidates = payload.get("candidates", [])
    if not isinstance(requirements, dict):
        errors.append("requirements must be an object")
        requirements = {}
    if not isinstance(candidates, list):
        errors.append("candidates must be an array")
        candidates = []

    groups: dict[str, dict[str, Any]] = {}
    for label in ("minimum", "maximum", "equals"):
        value = requirements.get(label, {})
        if not isinstance(value, dict):
            errors.append(f"requirements.{label} must be an object")
            value = {}
        groups[label] = value

    as_of = parse_date(payload.get("as_of"))
    if payload.get("as_of") is not None and as_of is None:
        errors.append("as_of must be an ISO-8601 date or timestamp")

    confirmed: list[dict[str, Any]] = []
    needs_confirmation: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []

    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            errors.append(f"candidates[{index}] must be an object")
            continue
        ident = candidate.get("id")
        if not isinstance(ident, str) or not ident.strip():
            errors.append(f"candidates[{index}].id must be a nonempty string")
            continue

        facts = candidate.get("facts", {})
        if not isinstance(facts, dict):
            errors.append(f"candidate {ident}: facts must be an object")
            facts = {}
        eligibility = candidate.get("eligibility", "eligible")
        if eligibility not in {"eligible", "unknown", "ineligible"}:
            errors.append(f"candidate {ident}: invalid eligibility")
            eligibility = "unknown"

        missing: list[str] = []
        failed: list[str] = []
        if eligibility == "unknown":
            missing.append("eligibility")
        elif eligibility == "ineligible":
            failed.append("eligibility")

        compare_numeric(
            facts, groups["minimum"], "minimum", missing, failed, errors, "requirements.minimum"
        )
        compare_numeric(
            facts, groups["maximum"], "maximum", missing, failed, errors, "requirements.maximum"
        )
        for field, target in groups["equals"].items():
            actual = facts.get(field)
            if actual is None:
                missing.append(field)
                continue
            expected_number = numeric(target)
            actual_number = numeric(actual)
            if expected_number is not None and actual_number is not None:
                matches = actual_number == expected_number
            else:
                matches = actual == target
            if not matches:
                failed.append(field)

        record = {
            "id": ident,
            "name": candidate.get("name", ident),
            "failed_constraints": sorted(set(failed)),
            "unknown_constraints": sorted(set(missing)),
        }
        if failed:
            excluded.append(record)
        elif missing:
            needs_confirmation.append(record)
        else:
            record["active_promotion_rank"] = active_promotion_rank(candidate, as_of)
            confirmed.append(record)

    confirmed.sort(
        key=lambda item: (
            item["active_promotion_rank"] is None,
            item["active_promotion_rank"] if item["active_promotion_rank"] is not None else 10**9,
            item["id"],
        )
    )
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
        output = evaluate(json.loads(raw) if raw.strip() else {})
    except json.JSONDecodeError as exc:
        output = {"errors": [f"invalid JSON: {exc.msg}"], **EMPTY}
    except Exception as exc:  # Defensive JSON-only failure behavior.
        output = {"errors": [f"unexpected evaluator error: {type(exc).__name__}"], **EMPTY}
    print(json.dumps(output, sort_keys=True))
