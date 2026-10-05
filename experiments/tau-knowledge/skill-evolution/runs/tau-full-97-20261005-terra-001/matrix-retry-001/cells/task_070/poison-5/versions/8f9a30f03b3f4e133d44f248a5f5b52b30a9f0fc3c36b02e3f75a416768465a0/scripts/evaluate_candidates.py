#!/usr/bin/env python3
"""Evaluate structured business-checking candidates against hard requirements.

Reads a JSON object from stdin and writes a JSON object to stdout. Uses only the
Python standard library. See SKILL.md for the input contract.
"""
import json
import sys
from decimal import Decimal, InvalidOperation


class InputError(ValueError):
    pass


def money(value, field):
    if isinstance(value, bool) or value is None:
        raise InputError(f"{field} must be a decimal number or decimal string")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise InputError(f"{field} must be a decimal number or decimal string")


def optional_money(obj, key, label):
    if key not in obj or obj[key] is None:
        return None
    return money(obj[key], f"{label}.{key}")


def main(payload):
    if not isinstance(payload, dict):
        raise InputError("input must be a JSON object")
    requirements = payload.get("requirements", {})
    candidates = payload.get("candidates", [])
    promotion = payload.get("promotion", {})
    if not isinstance(requirements, dict):
        raise InputError("requirements must be an object")
    if not isinstance(candidates, list) or not candidates:
        raise InputError("candidates must be a nonempty array")
    if not isinstance(promotion, dict):
        raise InputError("promotion must be an object")

    required_overdraft = (
        money(requirements["overdraft_fee_must_equal"],
              "requirements.overdraft_fee_must_equal")
        if "overdraft_fee_must_equal" in requirements else None
    )
    required_rebate = (
        money(requirements["minimum_monthly_atm_rebate"],
              "requirements.minimum_monthly_atm_rebate")
        if "minimum_monthly_atm_rebate" in requirements else None
    )

    evaluations = []
    qualifying = []
    all_blockers = []
    for index, candidate in enumerate(candidates):
        label = f"candidates[{index}]"
        if (not isinstance(candidate, dict)
                or not isinstance(candidate.get("name"), str)
                or not candidate["name"].strip()):
            raise InputError(f"{label}.name must be a nonempty string")
        eligibility = candidate.get("product_eligibility", "unknown")
        if eligibility not in {"eligible", "ineligible", "unknown"}:
            raise InputError(
                f"{label}.product_eligibility must be eligible, ineligible, or unknown"
            )

        overdraft = optional_money(candidate, "overdraft_fee", label)
        rebate = optional_money(candidate, "monthly_atm_rebate_cap", label)
        reasons = []
        blockers = []
        if eligibility != "eligible":
            blockers.append(f"product eligibility is {eligibility}")
        if required_overdraft is not None:
            if overdraft is None:
                blockers.append("overdraft fee is not documented")
            elif overdraft != required_overdraft:
                blockers.append(
                    f"overdraft fee is {overdraft}, not required {required_overdraft}"
                )
            else:
                reasons.append("overdraft-fee requirement met")
        if required_rebate is not None:
            if rebate is None:
                blockers.append("monthly ATM-rebate cap is not documented")
            elif rebate < required_rebate:
                blockers.append(
                    f"monthly ATM-rebate cap is {rebate}, below required {required_rebate}"
                )
            else:
                reasons.append("monthly ATM-rebate requirement met")

        confirmed = not blockers
        result = {
            "name": candidate["name"],
            "confirmed_qualifying": confirmed,
            "reasons": reasons,
            "blockers": blockers,
        }
        if "facts" in candidate:
            result["facts"] = candidate["facts"]
        evaluations.append(result)
        if confirmed:
            qualifying.append(candidate["name"])
        else:
            all_blockers.extend(
                f"{candidate['name']}: {item}" for item in blockers
            )

    active = promotion.get("active", False)
    if not isinstance(active, bool):
        raise InputError("promotion.active must be boolean")
    ranking = promotion.get("ranking", [])
    if (not isinstance(ranking, list)
            or not all(isinstance(name, str) for name in ranking)):
        raise InputError("promotion.ranking must be an array of strings")

    recommendation = None
    selection_basis = None
    if qualifying:
        if active:
            by_rank = {name: position for position, name in enumerate(ranking)}
            recommendation = min(
                qualifying,
                key=lambda name: (by_rank.get(name, len(ranking)), qualifying.index(name)),
            )
            if recommendation in by_rank:
                selection_basis = (
                    "active promotion ranking among confirmed qualifying candidates"
                )
            else:
                selection_basis = (
                    "first confirmed qualifying candidate; no qualifying candidate "
                    "was promotion-ranked"
                )
        else:
            recommendation = qualifying[0]
            selection_basis = (
                "first confirmed qualifying candidate; promotion inactive or unavailable"
            )

    return {
        "candidate_evaluations": evaluations,
        "confirmed_qualifying_candidates": qualifying,
        "recommendation": recommendation,
        "selection_basis": selection_basis,
        "missing_or_blocking_facts": all_blockers,
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), ensure_ascii=False, sort_keys=True))
    except (json.JSONDecodeError, InputError) as error:
        print(json.dumps({"error": str(error)}))
        sys.exit(2)
