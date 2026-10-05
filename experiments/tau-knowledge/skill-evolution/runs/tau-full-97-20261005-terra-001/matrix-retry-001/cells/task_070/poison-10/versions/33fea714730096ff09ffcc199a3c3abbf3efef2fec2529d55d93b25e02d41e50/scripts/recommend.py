#!/usr/bin/env python3
"""Select one fully eligible business-checking candidate from JSON on stdin."""

import json
import sys
from decimal import Decimal, InvalidOperation

REQUIRED_FIELDS = {
    "max_overdraft_fee": "overdraft_fee",
    "max_minimum_balance": "minimum_balance",
    "min_monthly_atm_rebate": "monthly_atm_rebate",
    "min_apy": "apy",
}


def response(recommended=None, qualifying=None, blocked=None, errors=None):
    return {
        "recommended": recommended,
        "qualifying_candidates": qualifying or [],
        "blocked_candidates": blocked or [],
        "errors": errors or [],
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


def normalized_decimal(value):
    return format(value, "f")


def validate_requirements(requirements):
    errors = []
    for key, value in requirements.items():
        if key not in REQUIRED_FIELDS:
            errors.append(f"unsupported requirement: {key}")
            continue
        try:
            decimal_value(value, key)
        except ValueError as exc:
            errors.append(str(exc))
    return errors


def assess_constraints(candidate, requirements):
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

    if "max_overdraft_fee" in requirements and values["overdraft_fee"] > decimal_value(requirements["max_overdraft_fee"], "max_overdraft_fee"):
        reasons.append("overdraft fee exceeds the customer's maximum")
    if "max_minimum_balance" in requirements and values["minimum_balance"] > decimal_value(requirements["max_minimum_balance"], "max_minimum_balance"):
        reasons.append("minimum balance exceeds the customer's maximum")
    if "min_monthly_atm_rebate" in requirements and values["monthly_atm_rebate"] < decimal_value(requirements["min_monthly_atm_rebate"], "min_monthly_atm_rebate"):
        reasons.append("monthly ATM rebate is below the customer's minimum")
    if "min_apy" in requirements and values["apy"] < decimal_value(requirements["min_apy"], "min_apy"):
        reasons.append("APY is below the customer's minimum")
    return reasons, values


def promotion_rank(candidate):
    rank = candidate.get("promotion_rank")
    if isinstance(rank, int) and not isinstance(rank, bool) and rank >= 1:
        return rank
    return 10**9


def main(payload):
    if not isinstance(payload, dict):
        return response(errors=["input must be a JSON object"])
    requirements = payload.get("requirements")
    candidates = payload.get("candidates")
    errors = []
    if not isinstance(requirements, dict):
        errors.append("requirements must be an object")
    if not isinstance(candidates, list) or not candidates:
        errors.append("candidates must be a nonempty array")
    if errors:
        return response(errors=errors)

    errors.extend(validate_requirements(requirements))
    promotion_active = payload.get("promotion_active", False)
    if not isinstance(promotion_active, bool):
        errors.append("promotion_active must be boolean")
    if errors:
        return response(errors=errors)

    qualifying = []
    blocked = []
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            errors.append(f"candidate at index {index} must be an object")
            continue
        name = candidate.get("name")
        if not isinstance(name, str) or not name.strip():
            errors.append(f"candidate at index {index} requires a nonempty name")
            continue
        name = name.strip()
        eligibility = candidate.get("eligibility")
        if not isinstance(eligibility, dict):
            errors.append(f"{name}: eligibility must be an object")
            continue
        status = eligibility.get("status")
        if status not in {"eligible", "ineligible", "unknown"}:
            errors.append(f"{name}: eligibility.status must be eligible, ineligible, or unknown")
            continue
        if status != "eligible":
            reason = eligibility.get("reason")
            if not isinstance(reason, str) or not reason.strip():
                errors.append(f"{name}: non-eligible status requires an eligibility reason")
            else:
                blocked.append({"name": name, "reasons": [f"eligibility is {status}: {reason.strip()}"]})
            continue

        reasons, values = assess_constraints(candidate, requirements)
        if reasons:
            blocked.append({"name": name, "reasons": reasons})
        else:
            qualifying.append((candidate, values))

    if errors:
        return response(blocked=blocked, errors=errors)
    if not qualifying:
        return response(blocked=blocked)

    def selection_key(item):
        candidate, values = item
        active_rank = promotion_rank(candidate) if promotion_active else 0
        return (
            active_rank,
            -values.get("apy", Decimal("0")),
            values.get("minimum_balance", Decimal("0")),
            candidate["name"].casefold(),
        )

    qualifying.sort(key=selection_key)
    selected, values = qualifying[0]
    matched_values = {
        field: normalized_decimal(values[field])
        for requirement, field in REQUIRED_FIELDS.items()
        if requirement in requirements and field in values
    }
    reasons = [
        f"{field} satisfies {requirement}"
        for requirement, field in REQUIRED_FIELDS.items()
        if requirement in requirements
    ]
    if promotion_active and promotion_rank(selected) < 10**9:
        reasons.append("selected using active promotion priority after satisfying all hard requirements")

    return response(
        recommended={
            "name": selected["name"].strip(),
            "reasons": reasons,
            "matched_values": matched_values,
        },
        qualifying=[candidate["name"].strip() for candidate, _ in qualifying],
        blocked=blocked,
    )


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), separators=(",", ":")))
    except json.JSONDecodeError:
        print(json.dumps(response(errors=["stdin must contain valid JSON"]), separators=(",", ":")))
    except Exception as exc:
        print(json.dumps(response(errors=[f"unexpected input error: {exc}"]), separators=(",", ":")))
