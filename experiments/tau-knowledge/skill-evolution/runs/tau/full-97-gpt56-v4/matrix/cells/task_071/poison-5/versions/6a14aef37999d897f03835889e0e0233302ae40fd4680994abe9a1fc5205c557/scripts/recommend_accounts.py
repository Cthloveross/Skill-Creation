#!/usr/bin/env python3
"""Filter and rank documented business account products.

Input: JSON object described in SKILL.md on stdin.
Output: JSON recommendation analysis on stdout.
"""
import json
import sys
from datetime import date


def parse_date(value):
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def active_priority(as_of, promotions):
    ranks = {}
    for promotion in promotions if isinstance(promotions, list) else []:
        start, end = parse_date(promotion.get("start")), parse_date(promotion.get("end"))
        if not (as_of and start and end and start <= as_of <= end):
            continue
        for index, name in enumerate(promotion.get("priorities", []), start=1):
            if isinstance(name, str) and name not in ranks:
                ranks[name] = index
    return ranks


def assess_eligibility(product, customer_facts):
    reasons, unknowns = [], []
    eligibility = product.get("eligibility") or {}
    comparisons = (
        ("company_age_years_max", "company_age_years", "at most"),
        ("company_age_years_min", "company_age_years", "at least"),
    )
    for rule_key, fact_key, wording in comparisons:
        if rule_key not in eligibility:
            continue
        if fact_key not in customer_facts:
            unknowns.append("eligibility requires %s" % fact_key)
            continue
        actual, limit = customer_facts[fact_key], eligibility[rule_key]
        passes = actual <= limit if wording == "at most" else actual >= limit
        if not passes:
            reasons.append("%s is %s %s, required %s %s" %
                           (fact_key, actual, wording, wording, limit))
    return reasons, unknowns


def assess_requirements(product, requirements):
    failures, unknowns = [], []
    checks = (
        ("mobile_deposit_daily_min", "mobile_deposit_daily_limit", "daily mobile-deposit limit"),
    )
    for required_key, product_key, label in checks:
        if required_key in requirements:
            if product_key not in product:
                unknowns.append("%s is undocumented" % label)
            elif product[product_key] < requirements[required_key]:
                failures.append("%s (%s) is below required minimum (%s)" %
                                (label, product[product_key], requirements[required_key]))
    if requirements.get("same_day_ach_required") is True:
        if "same_day_ach" not in product:
            unknowns.append("same-day ACH availability is undocumented")
        elif product["same_day_ach"] is not True:
            failures.append("same-day ACH is not available")
    return failures, unknowns


def main(payload):
    as_of = parse_date(payload.get("as_of"))
    customer_facts = payload.get("customer_facts") or {}
    requirements_by_type = payload.get("requirements") or {}
    priorities = active_priority(as_of, payload.get("promotions") or [])
    output = {"recommendations": {}, "confirmed_candidates": [],
              "needs_confirmation": [], "rejected_candidates": []}

    evaluated = []
    for product in payload.get("products") or []:
        product_type = product.get("type")
        if product_type not in requirements_by_type:
            continue
        failures_a, unknown_a = assess_requirements(product, requirements_by_type[product_type] or {})
        failures_b, unknown_b = assess_eligibility(product, customer_facts)
        failures, unknowns = failures_a + failures_b, unknown_a + unknown_b
        item = {
            "name": product.get("name"), "type": product_type,
            "reasons": failures, "unknowns": unknowns,
            "sources": product.get("sources") or [],
            "promotion_rank": priorities.get(product.get("name")),
        }
        if failures:
            item["status"] = "rejected"
            output["rejected_candidates"].append(item)
        elif unknowns:
            item["status"] = "needs_confirmation"
            output["needs_confirmation"].append(item)
        else:
            item["status"] = "confirmed"
            output["confirmed_candidates"].append(item)
            evaluated.append(item)

    for product_type in requirements_by_type:
        candidates = [x for x in evaluated if x["type"] == product_type]
        # Active promotion ranks first; unranked products follow alphabetically for deterministic output.
        candidates.sort(key=lambda x: (x["promotion_rank"] is None,
                                       x["promotion_rank"] if x["promotion_rank"] is not None else 10**9,
                                       x["name"] or ""))
        output["recommendations"][product_type] = candidates[0] if candidates else None
    return output


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(data), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
