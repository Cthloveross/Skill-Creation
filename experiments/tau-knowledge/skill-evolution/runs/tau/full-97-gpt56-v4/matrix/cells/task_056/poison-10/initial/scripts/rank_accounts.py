#!/usr/bin/env python3
"""Filter and rank supplied business-account facts.

Input: one JSON object described in SKILL.md on stdin.
Output: JSON object with selection, eligible, excluded, unknowns, and ranked.
"""
import json
import sys
from typing import Any, Dict, List, Optional, Tuple


def number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def text_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(x).strip().lower() for x in value if str(x).strip()]


def product_name(product: Dict[str, Any], index: int) -> str:
    name = product.get("name")
    return str(name) if isinstance(name, str) and name.strip() else f"product_{index + 1}"


def assess(product: Dict[str, Any], requirements: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    failures: List[str] = []
    unknowns: List[str] = []
    name = product.get("name", "product")

    if requirements.get("zero_overdraft_required") is True:
        overdraft = number(product.get("overdraft_fee"))
        if overdraft is None:
            failures.append(f"{name}: overdraft fee is not documented as zero")
        elif overdraft != 0:
            failures.append(f"{name}: overdraft fee is not zero")

    age = number(requirements.get("business_age_years"))
    maximum_age = number((product.get("eligibility") or {}).get("max_business_age_years"))
    if maximum_age is not None:
        if age is None:
            unknowns.append(f"{name}: business age is needed to confirm eligibility")
        elif age > maximum_age:
            failures.append(f"{name}: business exceeds maximum eligible age")

    fee_cap = number(requirements.get("max_monthly_fee"))
    if fee_cap is not None:
        fee = number(product.get("monthly_fee"))
        if fee is None:
            failures.append(f"{name}: monthly fee is unknown")
        elif fee > fee_cap:
            failures.append(f"{name}: monthly fee exceeds stated maximum")

    required_limit = number(requirements.get("min_daily_transaction_limit"))
    if required_limit is not None:
        limit = number(product.get("daily_transaction_limit"))
        if limit is None:
            failures.append(f"{name}: daily transaction limit is unknown")
        elif limit < required_limit:
            failures.append(f"{name}: daily transaction limit is below stated need")

    minimum_apy = number(requirements.get("minimum_apy"))
    if minimum_apy is not None:
        apy = number(product.get("apy"))
        if apy is None:
            failures.append(f"{name}: APY is unknown")
        elif apy < minimum_apy:
            failures.append(f"{name}: APY is below stated minimum")

    features = set(text_list(product.get("features")))
    for feature in text_list(requirements.get("required_features")):
        if feature not in features:
            failures.append(f"{name}: missing required feature '{feature}'")
    return failures, unknowns


def sort_key(product: Dict[str, Any]) -> Tuple[int, int, float, float]:
    active = product.get("promotion_active") is True
    priority = number(product.get("promotion_priority"))
    promo_bucket = 0 if active and priority is not None and priority > 0 else 1
    promo_rank = int(priority) if promo_bucket == 0 else 999999
    limit = number(product.get("daily_transaction_limit"))
    apy = number(product.get("apy"))
    return (promo_bucket, promo_rank, -(limit if limit is not None else -1), -(apy if apy is not None else -1))


def main() -> None:
    try:
        request = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": f"invalid JSON input: {exc.msg}"}))
        return
    if not isinstance(request, dict):
        print(json.dumps({"error": "input must be a JSON object"}))
        return

    requirements = request.get("requirements")
    products = request.get("products")
    if not isinstance(requirements, dict) or not isinstance(products, list):
        print(json.dumps({"error": "requirements object and products array are required"}))
        return

    eligible: List[Dict[str, Any]] = []
    excluded: List[Dict[str, Any]] = []
    unknowns: List[str] = []
    for index, raw_product in enumerate(products):
        if not isinstance(raw_product, dict):
            excluded.append({"name": f"product_{index + 1}", "reasons": ["invalid product record"]})
            continue
        product = dict(raw_product)
        product["name"] = product_name(product, index)
        failures, product_unknowns = assess(product, requirements)
        unknowns.extend(product_unknowns)
        if failures:
            excluded.append({"name": product["name"], "reasons": failures})
        else:
            eligible.append(product)

    ranked = sorted(eligible, key=sort_key)
    selection = ranked[0] if ranked else None
    result = {
        "selection": selection,
        "eligible": eligible,
        "excluded": excluded,
        "unknowns": sorted(set(unknowns)),
        "ranked": ranked,
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
