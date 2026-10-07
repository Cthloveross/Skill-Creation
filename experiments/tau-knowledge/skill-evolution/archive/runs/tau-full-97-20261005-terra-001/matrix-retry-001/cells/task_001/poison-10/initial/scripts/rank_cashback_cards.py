#!/usr/bin/env python3
"""Rank documented cash-back card records against stated customer preferences.

Reads one JSON object from stdin and writes one JSON object to stdout. It makes
no network calls and contains no product catalog; callers must supply current,
source-verified product records.
"""

from __future__ import annotations

import json
import sys
from decimal import Decimal, InvalidOperation
from typing import Any


def decimal_value(value: Any, field: str, errors: list[str], default: Decimal | None = None) -> Decimal | None:
    if value is None:
        return default
    if isinstance(value, bool):
        errors.append(f"{field} must be numeric, not boolean")
        return None
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        errors.append(f"{field} must be numeric")
        return None
    if not result.is_finite() or result < 0:
        errors.append(f"{field} must be a finite nonnegative number")
        return None
    return result


def display_number(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def validate_profile(raw: Any, errors: list[str]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        errors.append("profile must be an object")
        raw = {}
    preference = raw.get("annual_fee_preference", "any")
    if preference not in ("no_annual_fee", "any"):
        errors.append("profile.annual_fee_preference must be 'no_annual_fee' or 'any'")
    subscription = raw.get("has_required_subscription")
    if subscription is not None and not isinstance(subscription, bool):
        errors.append("profile.has_required_subscription must be true, false, or null")
        subscription = None
    score = decimal_value(raw.get("credit_score"), "profile.credit_score", errors)
    focus = raw.get("spend_focus", "everyday")
    if not isinstance(focus, str) or not focus.strip():
        errors.append("profile.spend_focus must be a nonempty string")
        focus = "everyday"
    return {
        "annual_fee_preference": preference,
        "has_required_subscription": subscription,
        "credit_score": score,
        "spend_focus": focus.strip().lower(),
    }


def validate_products(raw: Any, errors: list[str]) -> list[dict[str, Any]]:
    if not isinstance(raw, list) or not raw:
        errors.append("products must be a nonempty array")
        return []
    records: list[dict[str, Any]] = []
    for index, item in enumerate(raw):
        prefix = f"products[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} must be an object")
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            errors.append(f"{prefix}.name must be a nonempty string")
            continue
        fee = decimal_value(item.get("annual_fee"), f"{prefix}.annual_fee", errors)
        base_rate = decimal_value(item.get("all_purchase_cashback_percent"), f"{prefix}.all_purchase_cashback_percent", errors)
        minimum_score = decimal_value(item.get("minimum_credit_score"), f"{prefix}.minimum_credit_score", errors)
        required = item.get("subscription_required", False)
        if not isinstance(required, bool):
            errors.append(f"{prefix}.subscription_required must be boolean")
            continue
        categories_raw = item.get("category_cashback_percent", {})
        categories: dict[str, Decimal] = {}
        if not isinstance(categories_raw, dict):
            errors.append(f"{prefix}.category_cashback_percent must be an object")
            continue
        for category, rate in categories_raw.items():
            if not isinstance(category, str) or not category.strip():
                errors.append(f"{prefix}.category_cashback_percent keys must be nonempty strings")
                continue
            parsed = decimal_value(rate, f"{prefix}.category_cashback_percent[{category!r}]", errors)
            if parsed is not None:
                categories[category.strip().lower()] = parsed
        if fee is None or base_rate is None:
            continue
        source = item.get("source")
        if source is not None and not isinstance(source, str):
            errors.append(f"{prefix}.source must be a string when supplied")
            source = None
        records.append({
            "name": name.strip(), "annual_fee": fee, "minimum_credit_score": minimum_score,
            "subscription_required": required, "all_rate": base_rate,
            "categories": categories, "source": source,
        })
    return records


def candidate_for(product: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    exclusion_reasons: list[str] = []
    conditions: list[str] = []
    unknowns: list[str] = []
    if profile["annual_fee_preference"] == "no_annual_fee" and product["annual_fee"] > 0:
        exclusion_reasons.append("has an annual fee, contrary to the no-annual-fee preference")
    if product["subscription_required"]:
        if profile["has_required_subscription"] is False:
            exclusion_reasons.append("requires a subscription the customer does not have")
        elif profile["has_required_subscription"] is None:
            conditions.append("requires confirmation that the customer has or will obtain the required subscription")
            unknowns.append("subscription status")
    minimum = product["minimum_credit_score"]
    score = profile["credit_score"]
    if minimum is None:
        unknowns.append("published minimum credit score")
    elif score is None:
        conditions.append(f"requires a credit score of at least {display_number(minimum):g}")
        unknowns.append("credit score")
    elif score < minimum:
        exclusion_reasons.append(f"documented minimum credit score is {display_number(minimum):g}")
    status = "ineligible" if exclusion_reasons else ("conditional" if conditions else "eligible")
    focus = profile["spend_focus"]
    focus_rate = product["categories"].get(focus, product["all_rate"])
    return {
        "name": product["name"],
        "status": status,
        "annual_fee": display_number(product["annual_fee"]),
        "all_purchase_cashback_percent": display_number(product["all_rate"]),
        "focus_cashback_percent": display_number(focus_rate),
        "subscription_required": product["subscription_required"],
        "minimum_credit_score": display_number(minimum),
        "source": product["source"],
        "reasons": exclusion_reasons if exclusion_reasons else conditions,
        "unknown_requirements": sorted(set(unknowns)),
    }


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"valid": False, "errors": [f"invalid JSON: {exc.msg}"], "recommendations": []}))
        return
    if not isinstance(payload, dict):
        print(json.dumps({"valid": False, "errors": ["input must be a JSON object"], "recommendations": []}))
        return
    errors: list[str] = []
    profile = validate_profile(payload.get("profile"), errors)
    products = validate_products(payload.get("products"), errors)
    if errors:
        print(json.dumps({"valid": False, "errors": errors, "recommendations": []}, sort_keys=True))
        return

    candidates = [candidate_for(product, profile) for product in products]
    status_rank = {"eligible": 0, "conditional": 1, "ineligible": 2}
    # For everyday use, focus rate resolves to the all-purchases rate. For an
    # explicit category, a matching documented category rate is considered.
    candidates.sort(key=lambda x: (status_rank[x["status"]], -x["focus_cashback_percent"], x["annual_fee"], x["name"].lower()))
    grouped = {status: [item for item in candidates if item["status"] == status] for status in status_rank}
    missing = sorted({item for candidate in candidates if candidate["status"] == "conditional" for item in candidate["unknown_requirements"]})
    result = {
        "valid": True,
        "spend_focus": profile["spend_focus"],
        "recommendations": candidates,
        "best_eligible": grouped["eligible"][0] if grouped["eligible"] else None,
        "best_conditional": grouped["conditional"][0] if grouped["conditional"] else None,
        "missing_information": missing,
        "counts": {status: len(items) for status, items in grouped.items()},
    }
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
