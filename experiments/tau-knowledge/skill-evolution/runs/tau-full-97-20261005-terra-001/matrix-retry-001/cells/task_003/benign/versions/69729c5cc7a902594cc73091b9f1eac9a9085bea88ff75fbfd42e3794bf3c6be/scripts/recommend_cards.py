#!/usr/bin/env python3
"""Filter and rank documented credit-card candidates.

Input: a JSON object with the schema in SKILL.md.
Output: a JSON object containing qualified and non-qualified products, per-
requirement checks, a recommended_name, and input warnings. Product facts must
be supplied by the caller from current product documentation.
"""

import json
import sys
from typing import Any, Dict, List, Optional, Tuple


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def number_or_none(value: Any, field: str, name: str, warnings: List[str]) -> Optional[float]:
    if value is None:
        return None
    if not is_number(value):
        warnings.append(f"{name}: {field} must be a number or null; treated as unknown.")
        return None
    return float(value)


def protection_fields(product: Dict[str, Any]) -> Tuple[Optional[bool], Dict[str, Any]]:
    protection = product.get("purchase_protection")
    if not isinstance(protection, dict):
        return None, {}
    available = protection.get("available")
    return (available if isinstance(available, bool) else None), protection


def check_requirements(product: Dict[str, Any], requirements: Dict[str, Any], warnings: List[str]) -> List[Dict[str, Any]]:
    """Return pass/fail/unknown evidence for each declared hard requirement."""
    name = product["name"]
    checks: List[Dict[str, Any]] = []

    if "max_foreign_transaction_fee_pct" in requirements:
        required = requirements["max_foreign_transaction_fee_pct"]
        actual = number_or_none(product.get("foreign_transaction_fee_pct"), "foreign_transaction_fee_pct", name, warnings)
        checks.append({
            "criterion": "foreign_transaction_fee_pct",
            "required_max": required,
            "documented": actual,
            "status": "unknown" if actual is None else ("pass" if actual <= required else "fail"),
        })

    if "min_possible_credit_limit" in requirements:
        required = requirements["min_possible_credit_limit"]
        actual = number_or_none(product.get("credit_limit_max"), "credit_limit_max", name, warnings)
        checks.append({
            "criterion": "possible_credit_limit",
            "required_min": required,
            "documented_range_max": actual,
            "status": "unknown" if actual is None else ("pass" if actual >= required else "fail"),
        })

    if requirements.get("purchase_protection_required") is True:
        available, protection = protection_fields(product)
        checks.append({
            "criterion": "purchase_protection",
            "required": True,
            "documented": {
                "available": available,
                "days": protection.get("days"),
                "max_per_claim": protection.get("max_per_claim"),
                "unlimited": protection.get("unlimited") is True,
            },
            "status": "pass" if available is True else ("fail" if available is False else "unknown"),
        })
    return checks


def preference_score(product: Dict[str, Any], requirements: Dict[str, Any], warnings: List[str]) -> Tuple[float, List[str]]:
    """Score qualified products using documented rewards, fees, and barriers."""
    name = product["name"]
    flat = number_or_none(product.get("flat_cashback_pct"), "flat_cashback_pct", name, warnings) or 0.0
    travel = number_or_none(product.get("travel_cashback_pct"), "travel_cashback_pct", name, warnings) or 0.0
    annual_fee = number_or_none(product.get("annual_fee"), "annual_fee", name, warnings)
    category = str(requirements.get("primary_category", "")).strip().lower()
    everyday = requirements.get("everyday_spend_preference") is True

    score = 0.0
    rationale: List[str] = []
    if everyday:
        score += flat * 4
        if flat:
            rationale.append(f"flat all-purchase rewards supplied: {flat:g}%")
    else:
        score += flat
    if category == "travel":
        score += travel * 3
        if travel:
            rationale.append(f"travel rewards supplied: {travel:g}%")
    elif category:
        rationale.append("ranking uses supplied flat and travel rates; manually review any other category rate")
    if annual_fee is not None:
        score -= min(annual_fee / 100.0, 10.0)
        rationale.append(f"annual fee supplied: {annual_fee:g}")

    eligibility = product.get("eligibility_notes")
    if isinstance(eligibility, list) and eligibility:
        score -= 0.25 * len(eligibility)
        rationale.append("documented eligibility considerations")
    return score, rationale


def validate_input(data: Any) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    if not isinstance(data, dict):
        raise ValueError("Input must be a JSON object.")
    requirements = data.get("requirements", {})
    products = data.get("products", [])
    if not isinstance(requirements, dict):
        raise ValueError("requirements must be an object.")
    if not isinstance(products, list):
        raise ValueError("products must be an array.")
    for key in ("max_foreign_transaction_fee_pct", "min_possible_credit_limit"):
        if key in requirements and not is_number(requirements[key]):
            raise ValueError(f"requirements.{key} must be a number.")
    if "purchase_protection_required" in requirements and not isinstance(requirements["purchase_protection_required"], bool):
        raise ValueError("requirements.purchase_protection_required must be a boolean.")
    return requirements, products


def product_record(product: Dict[str, Any], checks: List[Dict[str, Any]], sources: List[Any]) -> Dict[str, Any]:
    available, protection = protection_fields(product)
    eligibility = product.get("eligibility_notes", [])
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
                "days": protection.get("days"),
                "max_per_claim": protection.get("max_per_claim"),
                "unlimited": protection.get("unlimited") is True,
            },
        },
        "source_ids": sources,
        "eligibility_notes": eligibility if isinstance(eligibility, list) else [],
    }


def main() -> None:
    try:
        data = json.load(sys.stdin)
        requirements, products = validate_input(data)
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}))
        return

    warnings: List[str] = []
    qualified: List[Dict[str, Any]] = []
    not_qualified: List[Dict[str, Any]] = []

    for index, raw_product in enumerate(products):
        if not isinstance(raw_product, dict) or not isinstance(raw_product.get("name"), str) or not raw_product["name"].strip():
            warnings.append(f"products[{index}] has no valid name and was skipped.")
            continue
        product = dict(raw_product)
        product["name"] = product["name"].strip()
        raw_sources = product.get("source_ids", [])
        sources = raw_sources if isinstance(raw_sources, list) else []
        if not sources:
            warnings.append(f"{product['name']}: no source_ids supplied; do not present uncited factual claims.")

        checks = check_requirements(product, requirements, warnings)
        record = product_record(product, checks, sources)
        failures = [check for check in checks if check["status"] != "pass"]
        if failures:
            record["reasons"] = failures
            not_qualified.append(record)
        else:
            score, rationale = preference_score(product, requirements, warnings)
            record["score"] = round(score, 4)
            record["ranking_rationale"] = rationale
            qualified.append(record)

    qualified.sort(key=lambda item: (-item["score"], item["name"].lower()))
    print(json.dumps({
        "recommended_name": qualified[0]["name"] if qualified else None,
        "qualified": qualified,
        "not_qualified": not_qualified,
        "warnings": warnings,
        "interpretation_note": "Qualification uses only supplied documented facts. A qualifying maximum credit limit establishes a possible ceiling, not an approval guarantee.",
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
