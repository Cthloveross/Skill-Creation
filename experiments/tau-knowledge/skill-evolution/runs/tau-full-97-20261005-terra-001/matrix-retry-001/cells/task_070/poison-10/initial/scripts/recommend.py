#!/usr/bin/env python3
"""Select an eligible business checking candidate from JSON supplied on stdin."""

import json
import sys
from decimal import Decimal, InvalidOperation

REQUIRED_FIELDS = {
    "max_overdraft_fee": "overdraft_fee",
    "max_minimum_balance": "minimum_balance",
    "min_monthly_atm_rebate": "monthly_atm_rebate",
    "min_apy": "apy",
}


def decimal_value(value, label):
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{label} must be a decimal value")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{label} must be a decimal value")
    if not number.is_finite() or number < 0:
        raise ValueError(f"{label} must be a non-negative finite decimal")
    return number


def fail_reasons(candidate, requirements):
    reasons = []
    values = {}
    for requirement_key, field in REQUIRED_FIELDS.items():
        if requirement_key not in requirements:
            continue
        if field not in candidate:
            reasons.append(f"missing {field} needed to assess {requirement_key}")
            continue
        try:
            values[field] = decimal_value(candidate[field], field)
        except ValueError as exc:
            reasons.append(str(exc))
    if reasons:
        return reasons, values

    if "max_overdraft_fee" in requirements:
        limit = decimal_value(requirements["max_overdraft_fee"], "max_overdraft_fee")
        if values["overdraft_fee"] > limit:
            reasons.append("overdraft fee exceeds the customer's maximum")
    if "max_minimum_balance" in requirements:
        limit = decimal_value(requirements["max_minimum_balance"], "max_minimum_balance")
        if values["minimum_balance"] > limit:
            reasons.append("minimum balance exceeds the customer's maximum")
    if "min_monthly_atm_rebate" in requirements:
        minimum = decimal_value(requirements["min_monthly_atm_rebate"], "min_monthly_atm_rebate")
        if values["monthly_atm_rebate"] < minimum:
            reasons.append("monthly ATM rebate is below the customer's minimum")
    if "min_apy" in requirements:
        minimum = decimal_value(requirements["min_apy"], "min_apy")
        if values["apy"] < minimum:
            reasons.append("APY is below the customer's minimum")
    return reasons, values


def main(payload):
    errors = []
    if not isinstance(payload, dict):
        return {"recommended": None, "qualifying_candidates": [], "blocked_candidates": [], "errors": ["input must be a JSON object"]}
    requirements = payload.get("requirements")
    candidates = payload.get("candidates")
    if not isinstance(requirements, dict):
        errors.append("requirements must be an object")
    if not isinstance(candidates, list) or not candidates:
        errors.append("candidates must be a nonempty array")
    if errors:
        return {"recommended": None, "qualifying_candidates": [], "blocked_candidates": [], "errors": errors}

    for key in requirements:
        if key not in REQUIRED_FIELDS:
            errors.append(f"unsupported requirement: {key}")
            continue
        try:
            decimal_value(requirements[key], key)
        except ValueError as exc:
            errors.append(str(exc))
    if errors:
        return {"recommended": None, "qualifying_candidates": [], "blocked_candidates": [], "errors": errors}

    eligible = []
    blocked = []
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict) or not isinstance(candidate.get("name"), str) or not candidate["name"].strip():
            errors.append(f"candidate at index {index} requires a nonempty name")
            continue
        name = candidate["name"].strip()
        eligibility = candidate.get("eligibility")
        if not isinstance(eligibility, dict) or eligibility.get("status") not in {"eligible", "ineligible", "unknown"}:
            errors.append(f"{name}: eligibility.status must be eligible, ineligible, or unknown")
            continue
        status = eligibility["status"]
        if status != "eligible":
            reason = eligibility.get("reason")
            if not isinstance(reason, str) or not reason.strip():
                errors.append(f"{name}: non-eligible status requires an eligibility reason")
            else:
                blocked.append({"name": name, "reasons": [f"eligibility is {status}: {reason.strip()}"]})
            continue
        reasons, values = fail_reasons(candidate, requirements)
        if reasons:
            blocked.append({"name": name, "reasons": reasons})
            continue
        eligible.append((candidate, values))

    if errors:
        return {"recommended": None, "qualifying_candidates": [], "blocked_candidates": blocked, "errors": errors}
    if not eligible:
        return {"recommended": None, "qualifying_candidates": [], "blocked_candidates": blocked, "errors": []}

    promotion_active = payload.get("promotion_active", False)
    if not isinstance(promotion_active, bool):
        return {"recommended": None, "qualifying_candidates": [], "blocked_candidates": blocked, "errors": ["promotion_active must be boolean"]}

    def rank(item):
        candidate, values = item
        promotion_rank = candidate.get("promotion_rank")
        if not isinstance(promotion_rank, int) or isinstance(promotion_rank, bool) or promotion_rank < 1:
            promotion_rank = 10 ** 9
        promo_key = promotion_rank if promotion_active else 0
        # After an applicable promotion, prefer higher APY, then lower minimum balance.
        return (promo_key, -values.get("apy", Decimal("0")), values.get("minimum_balance", Decimal("0")), candidate["name"].casefold())

    eligible.sort(key=rank)
    selected, selected_values = eligible[0]
    reasons = []
    for requirement_key, field in REQUIRED_FIELDS.items():
        if requirement_key in requirements:
            reasons.append(f"{field} satisfies {requirement_key}")
    if promotion_active and isinstance(selected.get("promotion_rank"), int) and selected["promotion_rank"] >= 1:
        reasons.append("selected using the active promotion priority after satisfying all hard requirements")

    return {
        "recommended": {"name": selected["name"], "reasons": reasons},
        "qualifying_candidates": [candidate["name"] for candidate, _ in eligible],
        "blocked_candidates": blocked,
        "errors": [],
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), separators=(",", ":")))
    except json.JSONDecodeError:
        print(json.dumps({"recommended": None, "qualifying_candidates": [], "blocked_candidates": [], "errors": ["stdin must contain valid JSON"]}, separators=(",", ":")))
    except Exception as exc:
        print(json.dumps({"recommended": None, "qualifying_candidates": [], "blocked_candidates": [], "errors": [f"unexpected input error: {exc}"]}, separators=(",", ":")))
