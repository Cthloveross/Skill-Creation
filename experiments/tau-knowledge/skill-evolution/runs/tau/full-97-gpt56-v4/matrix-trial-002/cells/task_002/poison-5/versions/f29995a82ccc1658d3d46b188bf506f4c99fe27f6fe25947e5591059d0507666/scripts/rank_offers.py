#!/usr/bin/env python3
"""Rank disclosed personal everyday cash-back offers from JSON stdin.

This helper intentionally ranks advertised terms only. It never approves,
denies, applies for, or otherwise determines credit eligibility.
"""

import json
import sys
from decimal import Decimal, InvalidOperation


VALID_COVERAGE = {"all_eligible_purchases", "restricted_categories"}


def decimal_nonnegative(value, field, offer_name):
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{offer_name}: {field} must be numeric")
    if not parsed.is_finite() or parsed < 0:
        raise ValueError(f"{offer_name}: {field} must be a finite nonnegative number")
    return parsed


def json_number(value):
    """Preserve readable JSON numeric output without Decimal serialization."""
    if value == value.to_integral_value():
        return int(value)
    return float(value)


def eligibility_for(offer, customer):
    approved = customer.get("preapproved_or_approved")
    if approved is True:
        return "not_guaranteed_by_helper"

    if offer.get("invitation_only") is True:
        return "unconfirmed"

    required = offer.get("minimum_credit_score")
    score = customer.get("credit_score")
    if required is None:
        return "not_stated"
    if score is None:
        return "unconfirmed"
    if not isinstance(score, int) or isinstance(score, bool):
        return "unconfirmed"
    if score < required:
        return "does_not_meet_disclosed_score_minimum"
    return "meets_disclosed_score_minimum_only"


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    offers = payload.get("offers")
    customer = payload.get("customer", {})
    if not isinstance(offers, list) or not offers:
        raise ValueError("offers must be a nonempty array")
    if not isinstance(customer, dict):
        raise ValueError("customer must be an object")

    normalized = []
    for index, offer in enumerate(offers):
        if not isinstance(offer, dict):
            raise ValueError(f"offers[{index}] must be an object")
        name = offer.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"offers[{index}].name must be a nonempty string")
        if not isinstance(offer.get("personal_consumer"), bool):
            raise ValueError(f"{name}: personal_consumer must be boolean")
        coverage = offer.get("coverage")
        if coverage not in VALID_COVERAGE:
            raise ValueError(f"{name}: coverage must be one of {sorted(VALID_COVERAGE)}")
        rate = decimal_nonnegative(offer.get("rate_pct"), "rate_pct", name)
        fee = None
        if "annual_fee" in offer and offer["annual_fee"] is not None:
            fee = decimal_nonnegative(offer["annual_fee"], "annual_fee", name)
        if "minimum_credit_score" in offer and offer["minimum_credit_score"] is not None:
            minimum = offer["minimum_credit_score"]
            if not isinstance(minimum, int) or isinstance(minimum, bool) or minimum < 0:
                raise ValueError(f"{name}: minimum_credit_score must be a nonnegative integer")
        if "invitation_only" in offer and not isinstance(offer["invitation_only"], bool):
            raise ValueError(f"{name}: invitation_only must be boolean when supplied")
        normalized.append((offer, name, rate, fee))

    candidates = [
        item for item in normalized
        if item[0]["personal_consumer"] and item[0]["coverage"] == "all_eligible_purchases"
    ]
    if not candidates:
        return {
            "status": "no_matching_flat_rate_offer",
            "message": "No personal consumer offer with all_eligible_purchases coverage was supplied."
        }

    candidates.sort(key=lambda item: (-item[2], item[1].casefold()))
    top_rate = candidates[0][2]
    top = [item for item in candidates if item[2] == top_rate]

    def render(item):
        offer, name, rate, fee = item
        result = {
            "name": name,
            "rate_pct": json_number(rate),
            "coverage": offer["coverage"],
            "eligibility": eligibility_for(offer, customer),
        }
        if fee is not None:
            result["annual_fee"] = json_number(fee)
        if offer.get("minimum_credit_score") is not None:
            result["minimum_credit_score"] = offer["minimum_credit_score"]
        if offer.get("invitation_only") is not None:
            result["invitation_only"] = offer["invitation_only"]
        return result

    return {
        "status": "ok",
        "ranked_flat_rate_offers": [render(item) for item in candidates],
        "top_offers": [render(item) for item in top],
        "interpretation": "Top offers are ranked by disclosed flat cash-back rate only; fees and eligibility must be explained separately."
    }


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        print(json.dumps(main(data), ensure_ascii=False, sort_keys=True))
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, sort_keys=True))
