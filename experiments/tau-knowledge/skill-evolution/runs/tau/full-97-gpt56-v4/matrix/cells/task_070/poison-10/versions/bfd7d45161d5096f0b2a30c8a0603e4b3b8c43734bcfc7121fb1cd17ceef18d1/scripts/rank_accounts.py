#!/usr/bin/env python3
"""Filter and rank documented business-checking candidates.

Reads JSON from stdin; emits JSON to stdout.  It deliberately does not make
banking calls or infer eligibility from absent information.
"""

import json
import sys
from decimal import Decimal, InvalidOperation


def number(value, field, candidate_name):
    """Return a finite Decimal-like numeric input, raising ValueError otherwise."""
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{candidate_name}: {field} must be numeric")
    try:
        converted = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{candidate_name}: {field} must be numeric")
    if not converted.is_finite():
        raise ValueError(f"{candidate_name}: {field} must be finite")
    return converted


def rank_value(candidate, field):
    value = candidate.get(field)
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return 10 ** 12


def exclusion(candidate, requirements):
    name = str(candidate.get("name", "Unnamed candidate"))
    eligibility = candidate.get("eligibility")
    if eligibility not in {"confirmed", "not_confirmed", "ineligible"}:
        return f"{name}: eligibility must be confirmed, not_confirmed, or ineligible"
    if eligibility == "ineligible":
        return f"{name}: documented eligibility is not met"
    if eligibility == "not_confirmed":
        return f"{name}: required eligibility cannot be established from available information"

    if "max_overdraft_fee" in requirements:
        if "overdraft_fee" not in candidate:
            return f"{name}: overdraft-fee evidence is unavailable"
        fee = number(candidate["overdraft_fee"], "overdraft_fee", name)
        maximum = number(requirements["max_overdraft_fee"], "max_overdraft_fee", "requirements")
        if fee > maximum:
            return f"{name}: overdraft fee exceeds the stated maximum"

    if "min_atm_rebate_monthly" in requirements:
        if "atm_rebate_monthly" not in candidate:
            return f"{name}: monthly ATM-rebate evidence is unavailable"
        rebate = number(candidate["atm_rebate_monthly"], "atm_rebate_monthly", name)
        minimum = number(requirements["min_atm_rebate_monthly"], "min_atm_rebate_monthly", "requirements")
        if rebate < minimum:
            return f"{name}: monthly ATM rebate is below the stated minimum"
    return None


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("top-level input must be an object")
    requirements = payload.get("requirements", {})
    candidates = payload.get("candidates", [])
    if not isinstance(requirements, dict):
        raise ValueError("requirements must be an object")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("candidates must be a nonempty array")

    promotion_active = payload.get("promotion_active", False)
    if not isinstance(promotion_active, bool):
        raise ValueError("promotion_active must be boolean")

    matches, excluded = [], []
    for candidate in candidates:
        if not isinstance(candidate, dict) or not isinstance(candidate.get("name"), str) or not candidate["name"].strip():
            raise ValueError("every candidate must have a nonempty name")
        why = exclusion(candidate, requirements)
        if why:
            excluded.append({"name": candidate["name"], "reason": why})
        else:
            matches.append(candidate)

    if not matches:
        return {"status": "no_confirmed_match", "recommendation": None, "excluded": excluded}

    def sort_key(candidate):
        # Promotional order is relevant only when the caller has established it is active.
        promo = rank_value(candidate, "promotion_rank") if promotion_active else 10 ** 12
        return (promo, rank_value(candidate, "ordinary_rank"), candidate["name"].casefold())

    chosen = sorted(matches, key=sort_key)[0]
    recommendation = {
        "name": chosen["name"],
        "overdraft_fee": chosen.get("overdraft_fee"),
        "atm_rebate_monthly": chosen.get("atm_rebate_monthly"),
        "facts": chosen.get("facts", []),
        "promotion_priority_applied": promotion_active and rank_value(chosen, "promotion_rank") < 10 ** 12,
    }
    return {"status": "recommended", "recommendation": recommendation, "excluded": excluded}


if __name__ == "__main__":
    try:
        request = json.load(sys.stdin)
        response = main(request)
    except (json.JSONDecodeError, ValueError) as exc:
        response = {"status": "invalid_input", "error": str(exc)}
    json.dump(response, sys.stdout, ensure_ascii=False, sort_keys=True)
    sys.stdout.write("\n")
