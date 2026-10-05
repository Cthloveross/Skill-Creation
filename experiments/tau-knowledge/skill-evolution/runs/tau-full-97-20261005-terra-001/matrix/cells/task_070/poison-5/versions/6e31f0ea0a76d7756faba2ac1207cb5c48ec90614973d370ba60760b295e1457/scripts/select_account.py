#!/usr/bin/env python3
"""Select one evidence-supported business checking account.

Reads one JSON object matching the schema in SKILL.md from stdin and writes one
JSON decision object to stdout. This helper is advisory only and never performs
a banking action.
"""

import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation


def as_mapping(value, path):
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    return value


def as_number(value, path):
    if value is None or isinstance(value, bool):
        raise ValueError(f"{path} must be a number")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{path} must be a number")
    if not result.is_finite():
        raise ValueError(f"{path} must be finite")
    return result


def as_date(value, path):
    if not isinstance(value, str) or len(value) < 10:
        raise ValueError(f"{path} must be an ISO date or timestamp")
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        raise ValueError(f"{path} must begin with YYYY-MM-DD")


def age_reasons(profile, eligibility):
    """Return a reason only when the candidate states an age cap."""
    if "max_company_age_years" not in eligibility:
        return []
    maximum = as_number(
        eligibility["max_company_age_years"],
        "candidate.eligibility.max_company_age_years",
    )
    if "company_age_years" in profile:
        if as_number(profile["company_age_years"], "profile.company_age_years") > maximum:
            return ["company age exceeds the account eligibility limit"]
        return []
    if "company_age_at_most" in profile:
        # An upper-bound confirmation establishes eligibility only if the entire
        # confirmed bound is within the account's documented maximum.
        if as_number(profile["company_age_at_most"], "profile.company_age_at_most") > maximum:
            return ["confirmed company-age bound does not establish eligibility"]
        return []
    return ["company age is needed to verify eligibility"]


def requirement_reasons(requirements, fees, perks, opening):
    checks = (
        (
            "max_overdraft_fee", fees, "overdraft_fee",
            "overdraft fee is not documented for this candidate",
            "overdraft fee exceeds the customer's maximum", "maximum",
        ),
        (
            "min_atm_rebate_monthly", perks, "atm_rebate_monthly",
            "monthly ATM rebate is not documented for this candidate",
            "monthly ATM rebate is below the customer's minimum", "minimum",
        ),
        (
            "min_apy", perks, "apy",
            "APY is not documented for this candidate",
            "APY is below the customer's minimum", "minimum",
        ),
        (
            "max_minimum_funding_requirement", opening, "minimum_funding_requirement",
            "minimum funding requirement is not documented for this candidate",
            "minimum funding requirement exceeds the customer's maximum", "maximum",
        ),
        (
            "max_minimum_balance_requirement", opening, "minimum_balance_requirement",
            "minimum balance requirement is not documented for this candidate",
            "minimum balance requirement exceeds the customer's maximum", "maximum",
        ),
    )
    reasons = []
    for requirement_key, source, fact_key, missing, failure, direction in checks:
        if requirement_key not in requirements:
            continue
        if fact_key not in source:
            reasons.append(missing)
            continue
        actual = as_number(source[fact_key], f"candidate.{fact_key}")
        requested = as_number(requirements[requirement_key], f"requirements.{requirement_key}")
        fails = actual > requested if direction == "maximum" else actual < requested
        if fails:
            reasons.append(failure)
    return reasons


def candidate_reasons(candidate, profile, requirements):
    eligibility = as_mapping(candidate.get("eligibility"), "candidate.eligibility")
    fees = as_mapping(candidate.get("fees"), "candidate.fees")
    perks = as_mapping(candidate.get("perks"), "candidate.perks")
    opening = as_mapping(candidate.get("opening"), "candidate.opening")
    return age_reasons(profile, eligibility) + requirement_reasons(
        requirements, fees, perks, opening
    )


def active_priority(payload):
    """Return the de-duplicated priority list from promotions active on as_of."""
    if "as_of" not in payload:
        return []
    today = as_date(payload["as_of"], "as_of")
    promotions = payload.get("promotions", [])
    if not isinstance(promotions, list):
        raise ValueError("promotions must be a list")

    priority = []
    for index, promotion in enumerate(promotions):
        if not isinstance(promotion, dict):
            raise ValueError(f"promotions[{index}] must be an object")
        start = as_date(promotion.get("start_date"), f"promotions[{index}].start_date")
        end = as_date(promotion.get("end_date"), f"promotions[{index}].end_date")
        if end < start:
            raise ValueError(f"promotions[{index}] ends before it starts")
        listed = promotion.get("priority", [])
        if not isinstance(listed, list) or not all(
            isinstance(item, str) and item for item in listed
        ):
            raise ValueError(
                f"promotions[{index}].priority must be a list of candidate ids"
            )
        if start <= today <= end:
            for candidate_id in listed:
                if candidate_id not in priority:
                    priority.append(candidate_id)
    return priority


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    profile = as_mapping(payload.get("profile"), "profile")
    requirements = as_mapping(payload.get("requirements"), "requirements")
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("candidates must be a nonempty list")

    assessments = []
    seen_ids = set()
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            raise ValueError(f"candidates[{index}] must be an object")
        candidate_id = candidate.get("id")
        name = candidate.get("name")
        if not isinstance(candidate_id, str) or not candidate_id:
            raise ValueError(f"candidates[{index}].id must be a nonempty string")
        if candidate_id in seen_ids:
            raise ValueError("candidate ids must be unique")
        seen_ids.add(candidate_id)
        if not isinstance(name, str) or not name:
            raise ValueError(f"candidates[{index}].name must be a nonempty string")
        assessments.append({
            "candidate": candidate,
            "reasons": candidate_reasons(candidate, profile, requirements),
        })

    priority = active_priority(payload)
    priority_rank = {candidate_id: index for index, candidate_id in enumerate(priority)}
    qualifying = [assessment for assessment in assessments if not assessment["reasons"]]
    result = {
        "active_promotion_priority": priority,
        "assessments": [
            {
                "id": assessment["candidate"]["id"],
                "name": assessment["candidate"]["name"],
                "rejection_reasons": assessment["reasons"],
            }
            for assessment in assessments
        ],
    }
    if not qualifying:
        result.update({"status": "no_qualifying_candidate", "recommendation": None})
        return result

    def sort_key(assessment):
        candidate = assessment["candidate"]
        promotion_rank = priority_rank.get(candidate["id"], len(priority) + 1)
        score = as_number(candidate.get("preference_score", 0), "candidate.preference_score")
        return (promotion_rank, -score, candidate["id"])

    selected = sorted(qualifying, key=sort_key)[0]["candidate"]
    result.update({
        "status": "selected",
        "recommendation": {
            "id": selected["id"],
            "name": selected["name"],
            "customer_benefit_notes": selected.get("customer_benefit_notes", []),
            "cautions": selected.get("cautions", []),
            "promotion_priority_applied": selected["id"] in priority_rank,
        },
    })
    return result


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False, sort_keys=True))
    except (json.JSONDecodeError, ValueError) as error:
        print(json.dumps({"status": "input_error", "error": str(error)}))
        sys.exit(2)
