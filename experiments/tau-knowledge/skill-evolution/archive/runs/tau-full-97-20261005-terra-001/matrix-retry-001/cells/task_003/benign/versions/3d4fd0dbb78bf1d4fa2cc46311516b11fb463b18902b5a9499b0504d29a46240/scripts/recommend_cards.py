#!/usr/bin/env python3
"""Qualify and rank caller-supplied card records from current task documents.

Reads one JSON object from stdin and writes one JSON object to stdout. It does
not retrieve facts, make a credit decision, or take any customer action.
"""
import json
import sys


def is_num(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def numeric(value, label, warnings):
    if value is None:
        return None
    if not is_num(value):
        warnings.append(f"{label} must be numeric or null; treated as unknown.")
        return None
    return float(value)


def protection_details(product):
    detail = product.get("purchase_protection")
    if not isinstance(detail, dict):
        return None, {}
    available = detail.get("available")
    return (available if isinstance(available, bool) else None), detail


def requirement_checks(product, requirements, warnings):
    name = product["name"]
    checks = []
    if "max_foreign_transaction_fee_pct" in requirements:
        maximum = float(requirements["max_foreign_transaction_fee_pct"])
        actual = numeric(product.get("foreign_transaction_fee_pct"), f"{name}.foreign_transaction_fee_pct", warnings)
        checks.append({
            "criterion": "foreign_transaction_fee_pct",
            "required_max": maximum,
            "documented": actual,
            "status": "unknown" if actual is None else ("pass" if actual <= maximum else "fail"),
        })
    if "min_possible_credit_limit" in requirements:
        minimum = float(requirements["min_possible_credit_limit"])
        ceiling = numeric(product.get("credit_limit_max"), f"{name}.credit_limit_max", warnings)
        checks.append({
            "criterion": "possible_credit_limit",
            "required_min": minimum,
            "documented_range_max": ceiling,
            "status": "unknown" if ceiling is None else ("pass" if ceiling >= minimum else "fail"),
        })
    if requirements.get("purchase_protection_required") is True:
        available, detail = protection_details(product)
        checks.append({
            "criterion": "purchase_protection",
            "required": True,
            "documented": {
                "available": available,
                "days": detail.get("days"),
                "max_per_claim": detail.get("max_per_claim"),
                "unlimited": detail.get("unlimited") is True,
            },
            "status": "pass" if available is True else ("fail" if available is False else "unknown"),
        })
    return checks


def rank_score(product, requirements, warnings):
    name = product["name"]
    flat = numeric(product.get("flat_cashback_pct"), f"{name}.flat_cashback_pct", warnings) or 0.0
    travel = numeric(product.get("travel_cashback_pct"), f"{name}.travel_cashback_pct", warnings) or 0.0
    fee = numeric(product.get("annual_fee"), f"{name}.annual_fee", warnings)
    travel_focus = str(requirements.get("primary_category", "")).strip().lower() == "travel"
    everyday = requirements.get("everyday_spend_preference") is True

    score = flat * (4 if everyday else 1)
    rationale = []
    if flat:
        rationale.append(f"flat all-purchase rewards: {flat:g}%")
    if travel_focus and travel:
        score += travel * 3
        rationale.append(f"travel rewards: {travel:g}%")
    if fee is not None:
        score -= min(fee / 100.0, 10.0)
        rationale.append("annual fee documented")
    notes = product.get("eligibility_notes")
    if isinstance(notes, list) and notes:
        score -= 0.25 * len(notes)
        rationale.append("eligibility/access conditions documented")
    return round(score, 4), rationale


def record(product, checks):
    available, detail = protection_details(product)
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
                "days": detail.get("days"),
                "max_per_claim": detail.get("max_per_claim"),
                "unlimited": detail.get("unlimited") is True,
            },
        },
        "eligibility_notes": product.get("eligibility_notes") if isinstance(product.get("eligibility_notes"), list) else [],
        "source_ids": product.get("source_ids") if isinstance(product.get("source_ids"), list) else [],
    }


def main():
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be an object")
        requirements = payload.get("requirements", {})
        products = payload.get("products", [])
        if not isinstance(requirements, dict) or not isinstance(products, list):
            raise ValueError("requirements must be an object and products must be an array")
        for key in ("max_foreign_transaction_fee_pct", "min_possible_credit_limit"):
            if key in requirements and not is_num(requirements[key]):
                raise ValueError(f"requirements.{key} must be numeric")
        if "purchase_protection_required" in requirements and not isinstance(requirements["purchase_protection_required"], bool):
            raise ValueError("requirements.purchase_protection_required must be boolean")
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        return

    warnings, qualified, not_qualified = [], [], []
    for index, raw in enumerate(products):
        if not isinstance(raw, dict) or not isinstance(raw.get("name"), str) or not raw["name"].strip():
            warnings.append(f"products[{index}] has no valid name and was skipped.")
            continue
        product = dict(raw)
        product["name"] = product["name"].strip()
        if not product.get("source_ids"):
            warnings.append(f"{product['name']}: no source_ids supplied; verify claims against task documents.")
        checks = requirement_checks(product, requirements, warnings)
        item = record(product, checks)
        failures = [check for check in checks if check["status"] != "pass"]
        if failures:
            item["reasons"] = failures
            not_qualified.append(item)
        else:
            item["score"], item["ranking_rationale"] = rank_score(product, requirements, warnings)
            qualified.append(item)

    qualified.sort(key=lambda item: (-item["score"], item["name"].lower()))
    print(json.dumps({
        "recommended_name": qualified[0]["name"] if qualified else None,
        "qualified": qualified,
        "not_qualified": not_qualified,
        "warnings": warnings,
        "interpretation_note": "A qualifying limit ceiling establishes possibility only. Actual approval and the exact limit remain subject to underwriting.",
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
