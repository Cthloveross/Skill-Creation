#!/usr/bin/env python3
"""Select an evidenced business-checking recommendation from JSON stdin.

This is a decision helper only. It never performs an account or banking action.
"""
import json
import sys
from decimal import Decimal, InvalidOperation

ELIGIBILITY = {"confirmed", "unknown", "ineligible"}
MONEY_FIELDS = (
    "overdraft_fee",
    "monthly_atm_rebate_cap",
    "minimum_balance_requirement",
)


def money(value, field, errors):
    if value is None:
        return None
    if isinstance(value, bool):
        errors.append(f"{field} must be a decimal amount or null")
        return None
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        errors.append(f"{field} must be a decimal amount or null")
        return None
    if not amount.is_finite() or amount < 0:
        errors.append(f"{field} must be a non-negative decimal amount")
        return None
    return amount


def public_candidate(candidate):
    """Return JSON-safe candidate facts, leaving source strings intact."""
    return {
        "name": candidate["name"],
        "eligibility": candidate["eligibility"],
        "overdraft_fee": candidate["overdraft_fee"],
        "monthly_atm_rebate_cap": candidate["monthly_atm_rebate_cap"],
        "minimum_balance_requirement": candidate["minimum_balance_requirement"],
        "promotion_priority": candidate.get("promotion_priority"),
        "disclosures": candidate.get("disclosures", []),
        "perks": candidate.get("perks", []),
    }


def requirements_met(candidate, criteria):
    failures = []
    if criteria.get("require_zero_overdraft_fee"):
        value = candidate["_money"]["overdraft_fee"]
        if value is None:
            failures.append("overdraft fee is not evidenced")
        elif value != Decimal("0"):
            failures.append("overdraft fee is not zero")

    rebate_needed = criteria["minimum_monthly_atm_rebate"]
    if rebate_needed is not None:
        value = candidate["_money"]["monthly_atm_rebate_cap"]
        if value is None:
            failures.append("monthly ATM-rebate cap is not evidenced")
        elif value < rebate_needed:
            failures.append("monthly ATM-rebate cap is below the required amount")

    maximum_balance = criteria["maximum_minimum_balance"]
    if maximum_balance is not None:
        value = candidate["_money"]["minimum_balance_requirement"]
        if value is None:
            failures.append("minimum balance requirement is not evidenced")
        elif value > maximum_balance:
            failures.append("minimum balance requirement exceeds the customer's ceiling")
    return failures


def rank_key(candidate, promotion_active):
    # Promotions are an explicit policy tie-breaker among products that already qualify.
    priority = candidate.get("promotion_priority")
    if promotion_active and isinstance(priority, int) and priority > 0:
        return (0, priority, candidate["name"].casefold())
    if promotion_active:
        return (1, 0, candidate["name"].casefold())
    return (0, 0, candidate["name"].casefold())


def main(payload):
    errors = []
    if not isinstance(payload, dict):
        return {"status": "needs_data", "selected": None, "qualified_candidates": [],
                "unconfirmed_candidates": [], "reasons": [],
                "missing_fields": ["input must be a JSON object"]}

    raw_criteria = payload.get("criteria")
    raw_candidates = payload.get("candidates")
    if not isinstance(raw_criteria, dict):
        errors.append("criteria must be an object")
        raw_criteria = {}
    if not isinstance(raw_candidates, list) or not raw_candidates:
        errors.append("candidates must be a non-empty array")
        raw_candidates = []

    criteria = {
        "require_zero_overdraft_fee": raw_criteria.get("require_zero_overdraft_fee", False),
        "minimum_monthly_atm_rebate": money(raw_criteria.get("minimum_monthly_atm_rebate"), "criteria.minimum_monthly_atm_rebate", errors),
        "maximum_minimum_balance": money(raw_criteria.get("maximum_minimum_balance"), "criteria.maximum_minimum_balance", errors),
    }
    if not isinstance(criteria["require_zero_overdraft_fee"], bool):
        errors.append("criteria.require_zero_overdraft_fee must be boolean")

    promotion = payload.get("promotion", {})
    if not isinstance(promotion, dict):
        errors.append("promotion must be an object")
        promotion = {}
    promotion_active = promotion.get("active", False)
    if not isinstance(promotion_active, bool):
        errors.append("promotion.active must be boolean")

    candidates = []
    for index, raw in enumerate(raw_candidates):
        prefix = f"candidates[{index}]"
        if not isinstance(raw, dict):
            errors.append(f"{prefix} must be an object")
            continue
        name = raw.get("name")
        status = raw.get("eligibility")
        if not isinstance(name, str) or not name.strip():
            errors.append(f"{prefix}.name must be a non-empty string")
            continue
        if status not in ELIGIBILITY:
            errors.append(f"{prefix}.eligibility must be confirmed, unknown, or ineligible")
            continue
        candidate = dict(raw)
        candidate["name"] = name.strip()
        candidate["eligibility"] = status
        candidate["_money"] = {}
        for field in MONEY_FIELDS:
            candidate[field] = raw.get(field)
            candidate["_money"][field] = money(raw.get(field), f"{prefix}.{field}", errors)
        priority = raw.get("promotion_priority")
        if priority is not None and (not isinstance(priority, int) or isinstance(priority, bool) or priority < 1):
            errors.append(f"{prefix}.promotion_priority must be a positive integer or null")
        candidate["disclosures"] = raw.get("disclosures", [])
        candidate["perks"] = raw.get("perks", [])
        if not isinstance(candidate["disclosures"], list) or not all(isinstance(x, str) for x in candidate["disclosures"]):
            errors.append(f"{prefix}.disclosures must be an array of strings")
        if not isinstance(candidate["perks"], list) or not all(isinstance(x, str) for x in candidate["perks"]):
            errors.append(f"{prefix}.perks must be an array of strings")
        candidates.append(candidate)

    if errors:
        return {"status": "needs_data", "selected": None, "qualified_candidates": [],
                "unconfirmed_candidates": [], "reasons": [], "missing_fields": errors}

    qualified = []
    unknown = []
    reasons = []
    for candidate in candidates:
        failures = requirements_met(candidate, criteria)
        if candidate["eligibility"] == "confirmed" and not failures:
            qualified.append(candidate)
        elif candidate["eligibility"] == "unknown" and not failures:
            unknown.append(candidate)
        else:
            if candidate["eligibility"] == "ineligible":
                reasons.append({"candidate": candidate["name"], "reason": "eligibility is not met"})
            elif failures:
                reasons.append({"candidate": candidate["name"], "reason": "; ".join(failures)})

    qualified.sort(key=lambda c: rank_key(c, promotion_active))
    unknown.sort(key=lambda c: rank_key(c, promotion_active))
    qualified_public = [public_candidate(c) for c in qualified]
    unknown_public = [public_candidate(c) for c in unknown]

    if not qualified:
        return {
            "status": "no_confirmed_match",
            "selected": None,
            "qualified_candidates": [],
            "unconfirmed_candidates": unknown_public,
            "reasons": reasons,
            "missing_fields": [],
        }

    selected = qualified[0]
    reasons.insert(0, {"candidate": selected["name"], "reason": "confirmed eligible candidate meets every stated hard requirement"})
    return {
        "status": "selected",
        "selected": public_candidate(selected),
        "qualified_candidates": qualified_public,
        "unconfirmed_candidates": unknown_public,
        "reasons": reasons,
        "missing_fields": [],
    }


if __name__ == "__main__":
    try:
        incoming = json.load(sys.stdin)
        result = main(incoming)
    except json.JSONDecodeError as exc:
        result = {"status": "needs_data", "selected": None, "qualified_candidates": [],
                  "unconfirmed_candidates": [], "reasons": [],
                  "missing_fields": [f"invalid JSON input: {exc.msg}"]}
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
