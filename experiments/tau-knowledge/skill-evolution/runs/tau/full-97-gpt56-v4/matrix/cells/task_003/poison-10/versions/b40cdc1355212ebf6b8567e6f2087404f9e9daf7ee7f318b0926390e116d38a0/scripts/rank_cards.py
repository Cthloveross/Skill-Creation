#!/usr/bin/env python3
"""Rank documented card products against explicit, hard customer requirements.

Reads one JSON object from stdin and writes one JSON object to stdout.  It performs
no I/O other than stdin/stdout and intentionally treats absent hard-filter facts as
unconfirmed rather than favorable.
"""

import json
import sys
from typing import Any, Dict, List


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def reward_score(product: Dict[str, Any], spend_priority: Any) -> float:
    """Return a small, explainable score; never substitutes for hard filters."""
    rewards = product.get("rewards")
    if not isinstance(rewards, dict):
        return 0.0
    rate = rewards.get("rate_pct")
    if not is_number(rate):
        return 0.0
    eligible = str(rewards.get("eligible_spend", "")).lower()
    reward_type = str(rewards.get("type", "")).lower()
    priority = str(spend_priority or "").lower()
    # A documented flat all-purchase rate applies to travel only if its stated
    # eligibility says all purchases; category bonuses must be described by input.
    if priority == "travel":
        if "all" in eligible or reward_type == "flat_cash_back":
            return float(rate)
        if "travel" in eligible or "travel" in reward_type:
            return float(rate)
        return 0.0
    return float(rate)


def failures(product: Dict[str, Any], requirements: Dict[str, Any]) -> List[str]:
    failed: List[str] = []

    if "max_foreign_transaction_fee_pct" in requirements:
        target = requirements["max_foreign_transaction_fee_pct"]
        actual = product.get("foreign_transaction_fee_pct")
        if not is_number(target) or not is_number(actual) or actual > target:
            failed.append("foreign_transaction_fee_pct")

    if "min_credit_limit" in requirements:
        target = requirements["min_credit_limit"]
        maximum = product.get("credit_limit_max")
        if not is_number(target) or not is_number(maximum) or maximum < target:
            failed.append("credit_limit_max")

    if requirements.get("purchase_protection_required") is True:
        # A positive documented protection period establishes that protection is
        # documented; coverage qualifications remain available to the caller.
        days = product.get("purchase_protection_days")
        if not is_number(days) or days <= 0:
            failed.append("purchase_protection_days")

    if "min_purchase_protection_days" in requirements:
        target = requirements["min_purchase_protection_days"]
        days = product.get("purchase_protection_days")
        if not is_number(target) or not is_number(days) or days < target:
            failed.append("purchase_protection_days")

    return failed


def public_product(product: Dict[str, Any], hard_failures: List[str], score: float) -> Dict[str, Any]:
    return {
        "name": product.get("name", "Unnamed product"),
        "hard_filter_failures": hard_failures,
        "reward_fit_score": score,
        "foreign_transaction_fee_pct": product.get("foreign_transaction_fee_pct"),
        "credit_limit_min": product.get("credit_limit_min"),
        "credit_limit_max": product.get("credit_limit_max"),
        "purchase_protection_days": product.get("purchase_protection_days"),
        "purchase_protection_coverage": product.get("purchase_protection_coverage"),
        "rewards": product.get("rewards"),
    }


def main() -> None:
    payload = json.load(sys.stdin)
    if not isinstance(payload, dict):
        raise ValueError("Input must be a JSON object")
    requirements = payload.get("requirements", {})
    products = payload.get("products", [])
    if not isinstance(requirements, dict) or not isinstance(products, list):
        raise ValueError("requirements must be an object and products must be an array")

    qualifying: List[Dict[str, Any]] = []
    excluded: List[Dict[str, Any]] = []
    for product in products:
        if not isinstance(product, dict):
            excluded.append({"name": "Invalid product", "hard_filter_failures": ["invalid_product"]})
            continue
        hard_failures = failures(product, requirements)
        score = reward_score(product, requirements.get("spend_priority"))
        view = public_product(product, hard_failures, score)
        if hard_failures:
            excluded.append(view)
        else:
            qualifying.append(view)

    qualifying.sort(key=lambda item: (-item["reward_fit_score"], str(item["name"])))
    print(json.dumps({
        "requirements": requirements,
        "qualifying_products": qualifying,
        "excluded_products": excluded,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
