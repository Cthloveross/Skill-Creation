#!/usr/bin/env python3
"""Filter and rank documented card candidates.

Input: JSON object documented in SKILL.md.
Output: JSON object with qualified, not_qualified, and warnings arrays.
The program is deliberately data-driven: product facts are supplied at runtime.
"""

import json
import sys
from typing import Any, Dict, List, Optional, Tuple


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def numeric_or_none(value: Any, field: str, product_name: str, warnings: List[str]) -> Optional[float]:
    if value is None:
        return None
    if not is_number(value):
        warnings.append(f"{product_name}: {field} must be a number or null; treated as unknown.")
        return None
    return float(value)


def protection_status(product: Dict[str, Any]) -> Tuple[Optional[bool], Dict[str, Any]]:
    protection = product.get("purchase_protection")
    if not isinstance(protection, dict):
        return None, {}
    available = protection.get("available")
    return (available if isinstance(available, bool) else None), protection


def hard_requirement_results(product: Dict[str, Any], requirements: Dict[str, Any], warnings: List[str]) -> List[Dict[str, Any]]:
    name = product["name"]
    results: List[Dict[str, Any]] = []

    if "max_foreign_transaction_fee_pct" in requirements:
        required = requirements["max_foreign_transaction_fee_pct"]
        actual = numeric_or_none(product.get("foreign_transaction_fee_pct"), "foreign_transaction_fee_pct", name, warnings)
        status = "unknown" if actual is None else ("pass" if actual <= required else "fail")
        results.append({"criterion": "foreign_transaction_fee_pct", "required_max": required, "documented": actual, "status": status})

    if "min_possible_credit_limit" in requirements:
        required = requirements["min_possible_credit_limit"]
        actual = numeric_or_none(product.get("credit_limit_max"), "credit_limit_max", name, warnings)
        status = "unknown" if actual is None else ("pass" if actual >= required else "fail")
        results.append({"criterion": "possible_credit_limit", "required_min": required, "documented_range_max": actual, "status": status})

    if requirements.get("purchase_protection_required") is True:
        actual, protection = protection_status(product)
        documented_details = {
            "available": actual,
            "days": protection.get("days"),
            "max_per_claim": protection.get("max_per_claim"),
            "unlimited": protection.get("unlimited") is True,
        }
        status = "pass" if actual is True else ("fail" if actual is False else "unknown")
        results.append({"criterion": "purchase_protection", "required": True, "documented": documented_details, "status": status})

    return results


def rank_score(product: Dict[str, Any], requirements: Dict[str, Any], warnings: List[str]) -> Tuple[float, List[str]]:
    """Return an explainable preference score only after hard qualification."""
    name = product["name"]
    flat = numeric_or_none(product.get("flat_cashback_pct"), "flat_cashback_pct", name, warnings) or 0.0
    travel = numeric_or_none(product.get("travel_cashback_pct"), "travel_cashback_pct", name, warnings) or 0.0
    annual_fee = numeric_or_none(product.get("annual_fee"), "annual_fee", name, warnings)
    category = str(requirements.get("primary_category", "")).strip().lower()
    everyday = requirements.get("everyday_spend_preference") is True

    score = 0.0
    reasons: List[str] = []
    if everyday:
        score += flat * 4
        if flat > 0:
            reasons.append(f"documented flat rewards rate: {flat:g}%")
    else:
        score += flat
    if category == "travel":
        score += travel * 3
        if travel > 0:
            reasons.append(f"documented travel rewards rate: {travel:g}%")
    elif category:
        # A category is stated but no generic category-rate field exists in the schema.
        reasons.append("ranking uses supplied flat and travel rates; verify any other category rate manually")
    if annual_fee is not None:
        # A small, bounded fee penalty prevents fee from obscuring substantial reward differences.
        score -= min(annual_fee / 100.0, 10.0)
        reasons.append(f"documented annual fee: {annual_fee:g}")
    else:
        reasons.append("annual fee not established in supplied data")

    eligibility = product.get("eligibility_notes", [])
    if isinstance(eligibility, list) and eligibility:
        reasons.append("eligibility considerations documented")
        score -= 0.25 * len(eligibility)
    return score, reasons


def validate_root(data: Any) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    if not isinstance(data, dict):
        raise ValueError("Input must be a JSON object.")
    requirements = data.get("requirements", {})
    products = data.get("products", [])
    if not isinstance(requirements, dict):
        raise ValueError("requirements must be an object.")
    if not isinstance(products, list):
        raise ValueError("products must be an array.")
    return requirements, products


def main() -> None:
    try:
        data = json.load(sys.stdin)
        requirements, products = validate_root(data)
    except (json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}))
        return

    warnings: List[str] = []
    qualified: List[Dict[str, Any]] = []
    not_qualified: List[Dict[str, Any]] = []

    for index, product in enumerate(products):
        if not isinstance(product, dict) or not isinstance(product.get("name"), str) or not product["name"].strip():
            warnings.append(f"products[{index}] has no valid name and was skipped.")
            continue
        product = dict(product)
        product["name"] = product["name"].strip()
        raw_sources = product.get("source_ids", [])
        sources = raw_sources if isinstance(raw_sources, list) else []
        if not sources:
            warnings.append(f"{product['name']}: no source_ids supplied; do not present uncited factual claims.")

        results = hard_requirement_results(product, requirements, warnings)
        failed = [item for item in results if item["status"] != "pass"]
        protection_available, protection = protection_status(product)
        record: Dict[str, Any] = {
            "name": product["name"],
            "requirement_checks": results,
            "source_ids": sources,
            "eligibility_notes": product.get("eligibility_notes", []) if isinstance(product.get("eligibility_notes", []), list) else [],
            "purchase_protection": {
                "available": protection_available,
                "days": protection.get("days"),
                "max_per_claim": protection.get("max_per_claim"),
                "unlimited": protection.get("unlimited") is True,
            },
        }
        if failed:
            record["reasons"] = failed
            not_qualified.append(record)
        else:
            score, tradeoffs = rank_score(product, requirements, warnings)
            record["score"] = round(score, 4)
            record["tradeoffs"] = tradeoffs
            qualified.append(record)

    qualified.sort(key=lambda item: (-item["score"], item["name"].lower()))
    result = {
        "qualified": qualified,
        "not_qualified": not_qualified,
        "warnings": warnings,
        "interpretation_note": "Qualification is based only on supplied documented fields. A qualifying maximum credit limit is a possible ceiling, not an approval guarantee.",
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
