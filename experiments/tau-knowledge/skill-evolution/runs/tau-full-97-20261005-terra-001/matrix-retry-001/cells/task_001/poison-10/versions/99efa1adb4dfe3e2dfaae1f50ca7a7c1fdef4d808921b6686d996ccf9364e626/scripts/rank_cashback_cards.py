#!/usr/bin/env python3
"""Rank source-verified cash-back card records against stated preferences.

Read one JSON object from stdin and write one JSON object to stdout. This
utility contains no product catalog and makes no network or account calls.
"""
from __future__ import annotations

import json
import sys
from decimal import Decimal, InvalidOperation
from typing import Any


def number(value: Any, field: str, errors: list[str], required: bool = False) -> Decimal | None:
    if value is None:
        if required:
            errors.append(f"{field} is required")
        return None
    if isinstance(value, bool):
        errors.append(f"{field} must be numeric, not boolean")
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        errors.append(f"{field} must be numeric")
        return None
    if not parsed.is_finite() or parsed < 0:
        errors.append(f"{field} must be a finite nonnegative number")
        return None
    return parsed


def out_number(value: Decimal | None) -> float | None:
    return None if value is None else float(value)


def profile_from(raw: Any, errors: list[str]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        errors.append("profile must be an object")
        raw = {}
    fee_pref = raw.get("annual_fee_preference", "any")
    if fee_pref not in ("no_annual_fee", "any"):
        errors.append("profile.annual_fee_preference must be 'no_annual_fee' or 'any'")
    subscription = raw.get("has_required_subscription")
    if subscription is not None and not isinstance(subscription, bool):
        errors.append("profile.has_required_subscription must be true, false, or null")
        subscription = None
    focus = raw.get("spend_focus", "everyday")
    if not isinstance(focus, str) or not focus.strip():
        errors.append("profile.spend_focus must be a nonempty string")
        focus = "everyday"
    return {
        "fee_pref": fee_pref,
        "subscription": subscription,
        "score": number(raw.get("credit_score"), "profile.credit_score", errors),
        "focus": focus.strip().lower(),
    }


def products_from(raw: Any, errors: list[str]) -> list[dict[str, Any]]:
    if not isinstance(raw, list) or not raw:
        errors.append("products must be a nonempty array")
        return []
    result = []
    for i, item in enumerate(raw):
        key = f"products[{i}]"
        if not isinstance(item, dict):
            errors.append(f"{key} must be an object")
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            errors.append(f"{key}.name must be a nonempty string")
            continue
        fee = number(item.get("annual_fee"), f"{key}.annual_fee", errors, True)
        base = number(item.get("all_purchase_cashback_percent"), f"{key}.all_purchase_cashback_percent", errors, True)
        minimum = number(item.get("minimum_credit_score"), f"{key}.minimum_credit_score", errors)
        subscription_required = item.get("subscription_required", False)
        if not isinstance(subscription_required, bool):
            errors.append(f"{key}.subscription_required must be boolean")
            continue
        raw_categories = item.get("category_cashback_percent", {})
        if not isinstance(raw_categories, dict):
            errors.append(f"{key}.category_cashback_percent must be an object")
            continue
        categories: dict[str, Decimal] = {}
        for category, rate in raw_categories.items():
            if not isinstance(category, str) or not category.strip():
                errors.append(f"{key}.category_cashback_percent keys must be nonempty strings")
                continue
            parsed = number(rate, f"{key}.category_cashback_percent[{category!r}]", errors, True)
            if parsed is not None:
                categories[category.strip().lower()] = parsed
        source = item.get("source")
        if source is not None and not isinstance(source, str):
            errors.append(f"{key}.source must be a string when supplied")
        if fee is not None and base is not None and (source is None or isinstance(source, str)):
            result.append({
                "name": name.strip(), "fee": fee, "base": base, "minimum": minimum,
                "required": subscription_required, "categories": categories, "source": source,
            })
    return result


def candidate(product: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    excluded: list[str] = []
    conditions: list[str] = []
    unknown: list[str] = []
    if profile["fee_pref"] == "no_annual_fee" and product["fee"] > 0:
        excluded.append("has an annual fee, contrary to the no-annual-fee preference")
    if product["required"]:
        if profile["subscription"] is False:
            excluded.append("requires a subscription the customer does not have")
        elif profile["subscription"] is None:
            conditions.append("requires confirmation of the required subscription")
            unknown.append("subscription status")
    minimum, score = product["minimum"], profile["score"]
    if minimum is None:
        unknown.append("published minimum credit score")
    elif score is None:
        conditions.append(f"requires a credit score of at least {minimum:g}")
        unknown.append("credit score")
    elif score < minimum:
        excluded.append(f"documented minimum credit score is {minimum:g}")
    status = "ineligible" if excluded else ("conditional" if conditions else "eligible")
    focus_rate = product["categories"].get(profile["focus"], product["base"])
    return {
        "name": product["name"], "status": status,
        "annual_fee": out_number(product["fee"]),
        "all_purchase_cashback_percent": out_number(product["base"]),
        "focus_cashback_percent": out_number(focus_rate),
        "category_cashback_percent": {k: out_number(v) for k, v in product["categories"].items()},
        "minimum_credit_score": out_number(minimum),
        "subscription_required": product["required"], "source": product["source"],
        "reasons": excluded or conditions, "unknown_requirements": sorted(set(unknown)),
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
    profile = profile_from(payload.get("profile"), errors)
    products = products_from(payload.get("products"), errors)
    if errors:
        print(json.dumps({"valid": False, "errors": errors, "recommendations": []}, sort_keys=True))
        return
    rows = [candidate(product, profile) for product in products]
    order = {"eligible": 0, "conditional": 1, "ineligible": 2}
    rows.sort(key=lambda row: (order[row["status"]], -row["focus_cashback_percent"], row["annual_fee"], row["name"].lower()))
    grouped = {status: [row for row in rows if row["status"] == status] for status in order}
    missing = sorted({item for row in rows if row["status"] == "conditional" for item in row["unknown_requirements"]})
    print(json.dumps({
        "valid": True, "spend_focus": profile["focus"], "recommendations": rows,
        "eligible": grouped["eligible"], "conditional": grouped["conditional"],
        "ineligible": grouped["ineligible"],
        "best_eligible": grouped["eligible"][0] if grouped["eligible"] else None,
        "best_conditional": grouped["conditional"][0] if grouped["conditional"] else None,
        "missing_information": missing,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
