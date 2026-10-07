#!/usr/bin/env python3
"""Deterministically filter documented referral options from gathered facts.

Reads a JSON object on stdin and writes a JSON object on stdout. Unknown facts must
be represented by null, not guessed. This script is advisory only and never calls
banking tools or creates a referral.
"""
import json
import sys
from datetime import datetime, timedelta, timezone

GLOBAL_GATES = (
    "identity_confirmed",
    "new_customer",
    "different_address",
    "age_eligible",
    "primary_signer_confirmed",
    "distinct_business_primary_owner",
    "new_money_deposit",
    "deposit_retention_possible",
    "no_conflicting_promotion",
    "account_opening_eligible",
)


def parse_time(value):
    if not isinstance(value, str):
        raise ValueError("timestamps must be ISO-8601 strings")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamps must include a timezone")
    return parsed.astimezone(timezone.utc)


def main(data):
    now = parse_time(data["now"])
    referrer = data.get("referrer", {})
    referred = data.get("referred", {})
    missing = []
    blockers = []

    tenure = referrer.get("tenure_days")
    annual_count = referrer.get("annual_complete_count")
    timestamps = referrer.get("complete_bonus_timestamps")
    if tenure is None:
        missing.append("referrer.tenure_days")
    if annual_count is None:
        missing.append("referrer.annual_complete_count")
    if timestamps is None:
        missing.append("referrer.complete_bonus_timestamps")
        recent_count = None
    else:
        try:
            recent_count = sum(
                0 <= (now - parse_time(stamp)).total_seconds() <= timedelta(days=9).total_seconds()
                for stamp in timestamps
            )
        except (TypeError, ValueError) as exc:
            blockers.append("invalid complete-bonus timestamp: %s" % exc)
            recent_count = None

    if recent_count is not None and recent_count >= 2:
        blockers.append("rolling nine-day referral-bonus cap reached")

    for gate in GLOBAL_GATES:
        value = referred.get(gate)
        if value is None:
            missing.append("referred.%s" % gate)
        elif value is not True:
            blockers.append("referred.%s is not satisfied" % gate)

    planned = data.get("planned_deposit")
    if planned is None:
        missing.append("planned_deposit")
    company_age = data.get("company_age_years")
    request = data.get("request", {})
    products = data.get("products", [])
    qualifying = []
    excluded = {}

    if missing or blockers:
        return {
            "recommendation": None,
            "qualifying_products": [],
            "missing_evidence": sorted(set(missing)),
            "blockers": blockers,
            "recent_complete_bonus_count": recent_count,
            "excluded_products": excluded,
        }

    for product in products:
        name = product.get("name", "unnamed product")
        reasons = []
        required = ("referrer_bonus", "annual_cap", "required_deposit", "deposit_window_days", "required_tenure_days")
        absent = [field for field in required if product.get(field) is None]
        if absent:
            excluded[name] = ["missing product policy fields: " + ", ".join(absent)]
            continue
        if tenure < product["required_tenure_days"]:
            reasons.append("referrer tenure below requirement")
        if planned < product["required_deposit"]:
            reasons.append("planned deposit below qualifying threshold")
        if annual_count >= product["annual_cap"]:
            reasons.append("product annual referral cap reached")
        max_age = product.get("company_max_age_years")
        if max_age is not None:
            if company_age is None:
                reasons.append("company age is unknown")
            elif company_age > max_age:
                reasons.append("company exceeds product formation-age limit")
        if reasons:
            excluded[name] = reasons
        else:
            qualifying.append(product)

    if not qualifying:
        return {
            "recommendation": None,
            "qualifying_products": [],
            "missing_evidence": [],
            "blockers": ["no product meets all verified requirements"],
            "recent_complete_bonus_count": recent_count,
            "excluded_products": excluded,
        }

    # The caller's maximum-bonus requirement is honored before promotional tie-breaking.
    if request.get("maximize_referrer_bonus", False):
        largest = max(item["referrer_bonus"] for item in qualifying)
        finalists = [item for item in qualifying if item["referrer_bonus"] == largest]
    else:
        finalists = qualifying[:]

    priority = request.get("active_promotion_priority") or []
    rank = {name: index for index, name in enumerate(priority)}
    finalists.sort(key=lambda item: (rank.get(item.get("name"), len(rank)), item.get("name", "")))
    selected = finalists[0]
    return {
        "recommendation": {
            "name": selected["name"],
            "referrer_bonus": selected["referrer_bonus"],
            "required_deposit": selected["required_deposit"],
            "deposit_window_days": selected["deposit_window_days"],
            "required_tenure_days": selected["required_tenure_days"],
        },
        "qualifying_products": [item.get("name") for item in qualifying],
        "missing_evidence": [],
        "blockers": [],
        "recent_complete_bonus_count": recent_count,
        "excluded_products": excluded,
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), sort_keys=True))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"error": "invalid input: %s" % error}))
        sys.exit(2)
