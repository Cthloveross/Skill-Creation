#!/usr/bin/env python3
"""Qualify and rank documented credit-card records.

Reads one JSON object from stdin and writes one JSON object to stdout.
Input schema is documented in SKILL.md. Facts are supplied by the caller from
current product documents; this program does not retrieve or invent facts.
"""

import json
import sys
from typing import Any, Dict, List, Optional, Tuple


def numeric(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def as_number(value: Any, field: str, name: str, warnings: List[str]) -> Optional[float]:
    if value is None:
        return None
    if not numeric(value):
        warnings.append(f"{name}: {field} must be numeric or null; treated as unknown.")
        return None
    return float(value)


def protection(product: Dict[str, Any]) -> Tuple[Optional[bool], Dict[str, Any]]:
    value = product.get("purchase_protection")
    if not isinstance(value, dict):
        return None, {}
    available = value.get("available")
    return (available if isinstance(available, bool) else None), value


def requirement_checks(product: Dict[str, Any], requirements: Dict[str, Any], warnings: List[str]) -> List[Dict[str, Any]]:
    name = product["name"]
    checks: List[Dict[str, Any]] = []

    if "max_foreign_transaction_fee_pct" in requirements:
        required = float(requirements["max_foreign_transaction_fee_pct"])
        actual = as_number(product.get("foreign_transaction_fee_pct"), "foreign_transaction_fee_pct", name, warnings)
        checks.append({
            "criterion": "foreign_transaction_fee_pct",
            "required_max": required,
            "documented": actual,
            "status": "unknown" if actual is None else ("pass" if actual <= required else "fail"),
        })

    if "min_possible_credit_limit" in requirements:
        required = float(requirements["min_possible_credit_limit"])
        ceiling = as_number(product.get("credit_limit_max"), "credit_limit_max", name, warnings)
        checks.append({
            "criterion": "possible_credit_limit",
            "required_min": required,
            "documented_range_max": ceiling,
            "status": "unknown" if ceiling is None else ("pass" if ceiling >= required else "fail"),
        })

    if requirements.get("purchase_protection_required") is True:
        available, details = protection(product)
        checks.append({
            "criterion": "purchase_protection",
            "required": True,
            "documented": {
                "available": available,
                "days": details.get("days"),
                "max_per_claim": details.get("max_per_claim"),
                "unlimited": details.get("unlimited") is True,
            },
            "status": "pass" if available is True else ("fail" if available is False else "unknown"),
        })
    return checks


def preference_score(product: Dict[str, Any], requirements: Dict[str, Any], warnings: List[str]) -> Tuple[float, List[str]]:
    """Rank documented qualified records without turning preferences into hard rules."""
    name = product["name"]
    flat = as_number(product.get("flat_cashback_pct"), "flat_cashback_pct", name, warnings) or 0.0
    travel = as_number(product.get("travel_cashback_pct"), "travel_cashback_pct", name, warnings) or 0.0
    annual_fee = as_number(product.get("annual_fee"), "annual_fee", name, warnings)
    everyday = requirements.get("everyday_spend_preference") is True
    category = str(requirements.get("primary_category", "")).strip().lower()

    score = flat * (4 if everyday else 1)
    rationale: List[str] = []
    if flat:
        rationale.append(f"documented flat all-purchase rewards: {flat:g}%")
    if category == "travel":
        score += travel * 3
        if travel:
            rationale.append(f"documented travel rewards: {travel:g}%")
    if annual_fee is not None:
        score -= min(annual_fee / 100.0, 10.0)
        rationale.append(f"documented annual fee: {annual_fee:g}")
    notes = product.get("eligibility_notes")
    if isinstance(notes, list) and notes:
        score -= 0.25 * len(notes)
        rationale.append("documented eligibility/access considerations")
    return score, rationale


def record(product: Dict[str, Any], checks: List[Dict[str, Any]]) -> Dict[str, Any]:
    available, details = protection(product)
    source_ids = product.get("source_ids")
    notes = product.get("eligibility_notes")
    return {
        "name": product["name"],
        "requirement_checks": checks,
        "documented_features": {
            "flat_cashback_pct": product.get("flat_cashback_pct"),
            "travel_cashback_pct": product.get("travel_cashback_pct"),
            "annual_fee": product.get("annual_fee"),
            "foreign_transaction_fee_pct": product.get("foreign_transaction_fee_pct"),
            "credit_limit_min": product.get("credit_limit_min"),
            "credit_limit_max": product.get("credit_limit_max"),
            "purchase_protection": {
                "available": available,
                "days": details.get("days"),
                "max_per_claim": details.get("max_per_claim"),
                "unlimited": details.get("unlimited") is True,
            },
        },
        "source_ids": source_ids if isinstance(source_ids, list) else [],
        "eligibility_notes": notes if isinstance(notes, list) else [],
    }


def main() -> None:
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be an object")
        requirements = data.get("requirements", {})
        products = data.get("products", [])
        if not isinstance(requirements, dict) or not isinstance(products, list):
            raise ValueError("requirements must be an object and products must be an array")
        for key in ("max_foreign_transaction_fee_pct", "min_possible_credit_limit"):
            if key in requirements and not numeric(requirements[key]):
                raise ValueError(f"requirements.{key} must be numeric")
        if "purchase_protection_required" in requirements and not isinstance(requirements["purchase_protection_required"], bool):
            raise ValueError("requirements.purchase_protection_required must be boolean")
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}))
        return

    warnings: List[str] = []
    qualified: List[Dict[str, Any]] = []
    not_qualified: List[Dict[str, Any]] = []
    for index, raw in enumerate(products):
        if not isinstance(raw, dict) or not isinstance(raw.get("name"), str) or not raw["name"].strip():
            warnings.append(f"products[{index}] has no valid name and was skipped.")
            continue
        product = dict(raw)
        product["name"] = product["name"].strip()
        if not isinstance(product.get("source_ids"), list) or not product["source_ids"]:
            warnings.append(f"{product['name']}: no source_ids supplied; verify factual claims before presenting them.")
        checks = requirement_checks(product, requirements, warnings)
        item = record(product, checks)
        unresolved = [check for check in checks if check["status"] != "pass"]
        if unresolved:
            item["reasons"] = unresolved
            not_qualified.append(item)
        else:
            score, rationale = preference_score(product, requirements, warnings)
            item["score"] = round(score, 4)
            item["ranking_rationale"] = rationale
            qualified.append(item)

    qualified.sort(key=lambda item: (-item["score"], item["name"].lower()))
    print(json.dumps({
        "recommended_name": qualified[0]["name"] if qualified else None,
        "qualified": qualified,
        "not_qualified": not_qualified,
        "warnings": warnings,
        "interpretation_note": "A qualifying documented limit ceiling establishes possibility only; the actual limit remains subject to underwriting and approval.",
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
