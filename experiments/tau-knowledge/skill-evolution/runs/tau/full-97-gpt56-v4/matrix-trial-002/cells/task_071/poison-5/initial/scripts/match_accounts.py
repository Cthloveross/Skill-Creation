#!/usr/bin/env python3
"""Match business account products to explicit, structured requirements.

Reads one JSON object from stdin and emits one JSON object to stdout.  See
SKILL.md for the public input and output schema.
"""
from __future__ import annotations

import json
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, List


CATALOG_PATH = Path(__file__).resolve().parents[1] / "references" / "product_capabilities.json"


def fail(message: str) -> None:
    print(json.dumps({"error": message}, sort_keys=True))
    raise SystemExit(2)


def as_nonnegative_decimal(value: Any, field: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{field} must be a non-negative number")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be a non-negative number")
    if not result.is_finite() or result < 0:
        raise ValueError(f"{field} must be a non-negative number")
    return result


def validate_products(items: Any, product_type: str) -> List[Dict[str, Any]]:
    if not isinstance(items, list):
        raise ValueError(f"catalog.{product_type} must be an array")
    valid: List[Dict[str, Any]] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict) or not isinstance(item.get("name"), str) or not item["name"].strip():
            raise ValueError(f"catalog.{product_type}[{index}].name must be a non-empty string")
        copied = dict(item)
        copied["preferred"] = bool(copied.get("preferred", False))
        if product_type == "checking":
            copied["mobile_deposit_daily_limit"] = as_nonnegative_decimal(
                copied.get("mobile_deposit_daily_limit"),
                f"catalog.checking[{index}].mobile_deposit_daily_limit",
            )
        else:
            if not isinstance(copied.get("same_day_ach"), bool):
                raise ValueError(f"catalog.savings[{index}].same_day_ach must be boolean")
        valid.append(copied)
    return valid


def checking_result(requirements: Any, products: List[Dict[str, Any]]) -> Dict[str, Any]:
    if requirements is None:
        return {"status": "not_requested"}
    if not isinstance(requirements, dict):
        raise ValueError("checking must be an object")
    if "minimum_mobile_deposit_daily" not in requirements:
        return {
            "status": "requirements_not_provided",
            "missing": ["minimum_mobile_deposit_daily"],
        }
    minimum = as_nonnegative_decimal(requirements["minimum_mobile_deposit_daily"], "checking.minimum_mobile_deposit_daily")
    matches = [p for p in products if p["mobile_deposit_daily_limit"] >= minimum]
    if not matches:
        return {
            "status": "no_match",
            "requirement": {"minimum_mobile_deposit_daily": str(minimum)},
            "reason": "No supplied checking product has a documented mobile deposit limit meeting this minimum.",
        }
    # Prefer an explicitly curated fit, then the greatest documented capacity, then stable name order.
    winner = sorted(matches, key=lambda p: (not p["preferred"], -p["mobile_deposit_daily_limit"], p["name"].casefold()))[0]
    return {
        "status": "matched",
        "requirement": {"minimum_mobile_deposit_daily": str(minimum)},
        "recommendation": {
            "name": winner["name"],
            "mobile_deposit_daily_limit": str(winner["mobile_deposit_daily_limit"]),
            "notes": winner.get("notes", []),
        },
    }


def savings_result(requirements: Any, products: List[Dict[str, Any]]) -> Dict[str, Any]:
    if requirements is None:
        return {"status": "not_requested"}
    if not isinstance(requirements, dict):
        raise ValueError("savings must be an object")
    if "same_day_ach_required" not in requirements:
        return {"status": "requirements_not_provided", "missing": ["same_day_ach_required"]}
    required = requirements["same_day_ach_required"]
    if not isinstance(required, bool):
        raise ValueError("savings.same_day_ach_required must be boolean")
    matches = [p for p in products if (p["same_day_ach"] or not required)]
    if not matches:
        return {
            "status": "no_match",
            "requirement": {"same_day_ach_required": required},
            "reason": "No supplied savings product has documented same-day ACH availability.",
        }
    winner = sorted(matches, key=lambda p: (not p["preferred"], p["name"].casefold()))[0]
    return {
        "status": "matched",
        "requirement": {"same_day_ach_required": required},
        "recommendation": {
            "name": winner["name"],
            "same_day_ach": winner["same_day_ach"],
            "notes": winner.get("notes", []),
        },
    }


def main() -> None:
    try:
        request = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        fail(f"stdin must contain a JSON object: {exc.msg}")
    if not isinstance(request, dict):
        fail("stdin must contain a JSON object")

    try:
        catalog = request.get("catalog")
        if catalog is None:
            with CATALOG_PATH.open(encoding="utf-8") as handle:
                catalog = json.load(handle)
        if not isinstance(catalog, dict):
            raise ValueError("catalog must be an object")
        checking_products = validate_products(catalog.get("checking"), "checking")
        savings_products = validate_products(catalog.get("savings"), "savings")
        result = {
            "checking": checking_result(request.get("checking"), checking_products),
            "savings": savings_result(request.get("savings"), savings_products),
        }
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        fail(str(exc))
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
