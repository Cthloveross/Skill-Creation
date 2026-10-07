#!/usr/bin/env python3
"""Compare caller-extracted product facts with stated numeric requirements.

Reads one JSON object from stdin and emits one JSON object to stdout. This helper
never retrieves documents or infers missing product facts or eligibility.
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

EMPTY = {"confirmed_matches": [], "needs_confirmation": [], "excluded": [], "recommended_order": []}


def numeric(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


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


def promotion_rank(candidate: dict[str, Any], as_of: date | None) -> int | None:
    promo = candidate.get("promotion")
    if as_of is None or not isinstance(promo, dict):
        return None
    rank, start, end = promo.get("rank"), parse_date(promo.get("start")), parse_date(promo.get("end"))
    if isinstance(rank, bool) or not isinstance(rank, int) or not start or not end or start > end:
        return None
    return rank if start <= as_of <= end else None


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
        group = requirements.get(label, {})
        if not isinstance(group, dict):
            errors.append(f"requirements.{label} must be an object")
            group = {}
        groups[label] = group
    as_of = parse_date(payload.get("as_of"))
    if payload.get("as_of") is not None and as_of is None:
        errors.append("as_of must be an ISO-8601 date or timestamp")

    confirmed: list[dict[str, Any]] = []
    unknown: list[dict[str, Any]] = []
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
        failed: list[str] = []
        missing: list[str] = []
        eligibility = candidate.get("eligibility", "eligible")
        if eligibility not in {"eligible", "unknown", "ineligible"}:
            errors.append(f"candidate {ident}: invalid eligibility")
            eligibility = "unknown"
        if eligibility == "ineligible":
            failed.append("eligibility")
        elif eligibility == "unknown":
            missing.append("eligibility")
        for field, target in groups["minimum"].items():
            needed, actual = numeric(target), numeric(facts.get(field))
            if needed is None:
                errors.append(f"requirements.minimum.{field} must be numeric")
            elif actual is None:
                missing.append(field)
            elif actual < needed:
                failed.append(field)
        for field, target in groups["maximum"].items():
            needed, actual = numeric(target), numeric(facts.get(field))
            if needed is None:
                errors.append(f"requirements.maximum.{field} must be numeric")
            elif actual is None:
                missing.append(field)
            elif actual > needed:
                failed.append(field)
        for field, target in groups["equals"].items():
            if field not in facts or facts[field] is None:
                missing.append(field)
            elif facts[field] != target:
                failed.append(field)
        record = {"id": ident, "name": candidate.get("name", ident),
                  "failed_constraints": sorted(set(failed)),
                  "unknown_constraints": sorted(set(missing))}
        if failed:
            excluded.append(record)
        elif missing:
            unknown.append(record)
        else:
            record["active_promotion_rank"] = promotion_rank(candidate, as_of)
            confirmed.append(record)
    confirmed.sort(key=lambda item: (item["active_promotion_rank"] is None,
                                     item["active_promotion_rank"] if item["active_promotion_rank"] is not None else 10**9,
                                     item["id"]))
    return {"errors": errors, "confirmed_matches": confirmed,
            "needs_confirmation": unknown, "excluded": excluded,
            "recommended_order": [item["id"] for item in confirmed]}


if __name__ == "__main__":
    try:
        raw = sys.stdin.read()
        output = evaluate(json.loads(raw) if raw.strip() else {})
    except json.JSONDecodeError as exc:
        output = {"errors": [f"invalid JSON: {exc.msg}"], **EMPTY}
    except Exception as exc:
        output = {"errors": [f"unexpected evaluator error: {type(exc).__name__}"], **EMPTY}
    print(json.dumps(output, sort_keys=True))
