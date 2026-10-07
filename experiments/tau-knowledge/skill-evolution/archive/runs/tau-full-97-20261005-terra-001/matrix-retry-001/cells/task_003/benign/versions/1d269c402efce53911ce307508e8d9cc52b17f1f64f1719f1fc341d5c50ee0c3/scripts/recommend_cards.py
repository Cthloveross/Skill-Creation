#!/usr/bin/env python3
"""Qualify and rank card records supplied from current task documents.

Reads one JSON object from stdin and writes one JSON object to stdout. This
program neither retrieves product data nor makes a credit decision.
"""
import json
import sys


def is_num(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def number(value, label, warnings):
    if value is None:
        return None
    if not is_num(value):
        warnings.append(label + " must be numeric or null; treated as unknown.")
        return None
    return float(value)


def protection(product):
    item = product.get("purchase_protection")
    if not isinstance(item, dict):
        return None, {}
    available = item.get("available")
    return (available if isinstance(available, bool) else None), item


def checks(product, requirements, warnings):
    name = product["name"]
    result = []
    if "max_foreign_transaction_fee_pct" in requirements:
        required = float(requirements["max_foreign_transaction_fee_pct"])
        actual = number(product.get("foreign_transaction_fee_pct"), name + ".foreign_transaction_fee_pct", warnings)
        result.append({"criterion": "foreign_transaction_fee_pct", "required_max": required,
                       "documented": actual, "status": "unknown" if actual is None else ("pass" if actual <= required else "fail")})
    if "min_possible_credit_limit" in requirements:
        required = float(requirements["min_possible_credit_limit"])
        maximum = number(product.get("credit_limit_max"), name + ".credit_limit_max", warnings)
        result.append({"criterion": "possible_credit_limit", "required_min": required,
                       "documented_range_max": maximum,
                       "status": "unknown" if maximum is None else ("pass" if maximum >= required else "fail")})
    if requirements.get("purchase_protection_required") is True:
        available, detail = protection(product)
        result.append({"criterion": "purchase_protection", "required": True,
                       "documented": {"available": available, "days": detail.get("days"),
                                      "max_per_claim": detail.get("max_per_claim"),
                                      "unlimited": detail.get("unlimited") is True},
                       "status": "pass" if available is True else ("fail" if available is False else "unknown")})
    return result


def score(product, requirements, warnings):
    name = product["name"]
    flat = number(product.get("flat_cashback_pct"), name + ".flat_cashback_pct", warnings) or 0.0
    travel = number(product.get("travel_cashback_pct"), name + ".travel_cashback_pct", warnings) or 0.0
    fee = number(product.get("annual_fee"), name + ".annual_fee", warnings)
    everyday = requirements.get("everyday_spend_preference") is True
    travel_focus = str(requirements.get("primary_category", "")).strip().lower() == "travel"
    value = flat * (4 if everyday else 1)
    rationale = []
    if flat:
        rationale.append("flat all-purchase rewards: {:g}%".format(flat))
    if travel_focus:
        value += travel * 3
        if travel:
            rationale.append("travel rewards: {:g}%".format(travel))
    if fee is not None:
        value -= min(fee / 100.0, 10.0)
        rationale.append("annual fee documented")
    notes = product.get("eligibility_notes")
    if isinstance(notes, list) and notes:
        value -= 0.25 * len(notes)
        rationale.append("eligibility/access conditions documented")
    return value, rationale


def summary(product, product_checks):
    available, detail = protection(product)
    return {
        "name": product["name"],
        "requirement_checks": product_checks,
        "documented_features": {
            "flat_cashback_pct": product.get("flat_cashback_pct"),
            "travel_cashback_pct": product.get("travel_cashback_pct"),
            "annual_fee": product.get("annual_fee"),
            "foreign_transaction_fee_pct": product.get("foreign_transaction_fee_pct"),
            "credit_limit_min": product.get("credit_limit_min"),
            "credit_limit_max": product.get("credit_limit_max"),
            "purchase_protection": {"available": available, "days": detail.get("days"),
                                    "max_per_claim": detail.get("max_per_claim"),
                                    "unlimited": detail.get("unlimited") is True}
        },
        "eligibility_notes": product.get("eligibility_notes") if isinstance(product.get("eligibility_notes"), list) else [],
        "source_ids": product.get("source_ids") if isinstance(product.get("source_ids"), list) else []
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
                raise ValueError("requirements." + key + " must be numeric")
        if "purchase_protection_required" in requirements and not isinstance(requirements["purchase_protection_required"], bool):
            raise ValueError("requirements.purchase_protection_required must be boolean")
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}))
        return

    warnings, qualified, not_qualified = [], [], []
    for index, raw in enumerate(products):
        if not isinstance(raw, dict) or not isinstance(raw.get("name"), str) or not raw["name"].strip():
            warnings.append("products[{}] has no valid name and was skipped.".format(index))
            continue
        product = dict(raw)
        product["name"] = product["name"].strip()
        if not product.get("source_ids"):
            warnings.append(product["name"] + ": no source_ids supplied; verify claims against task documents.")
        product_checks = checks(product, requirements, warnings)
        item = summary(product, product_checks)
        failed = [check for check in product_checks if check["status"] != "pass"]
        if failed:
            item["reasons"] = failed
            not_qualified.append(item)
        else:
            item["score"], item["ranking_rationale"] = score(product, requirements, warnings)
            item["score"] = round(item["score"], 4)
            qualified.append(item)
    qualified.sort(key=lambda item: (-item["score"], item["name"].lower()))
    print(json.dumps({
        "recommended_name": qualified[0]["name"] if qualified else None,
        "qualified": qualified,
        "not_qualified": not_qualified,
        "warnings": warnings,
        "interpretation_note": "A qualifying limit ceiling establishes possibility only. Actual approval and limit remain subject to underwriting."
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
