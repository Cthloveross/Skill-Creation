#!/usr/bin/env python3
"""Select one evidence-supported business checking account.

Reads one JSON object matching SKILL.md from stdin and writes one JSON decision
object to stdout. The script is advisory only and never performs a banking action.
"""

import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation


def number(value, path):
    if value is None or isinstance(value, bool):
        raise ValueError(f"{path} must be a number")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{path} must be a number")
    if not parsed.is_finite():
        raise ValueError(f"{path} must be finite")
    return parsed


def iso_day(value, path):
    if not isinstance(value, str) or len(value) < 10:
        raise ValueError(f"{path} must be an ISO date or timestamp")
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        raise ValueError(f"{path} must begin with YYYY-MM-DD")


def mapping(value, path):
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    return value


def maximum_check(container, field, requirement, missing_reason, failure_reason, path):
    if field not in container:
        return missing_reason
    if number(container[field], f"{path}.{field}") > number(requirement, f"requirements.{requirement[0] if False else 'value'}"):
        return failure_reason
    return None


def candidate_reasons(candidate, profile, requirements):
    reasons = []
    eligibility = mapping(candidate.get("eligibility"), "candidate.eligibility")
    fees = mapping(candidate.get("fees"), "candidate.fees")
    perks = mapping(candidate.get("perks"), "candidate.perks")
    opening = mapping(candidate.get("opening"), "candidate.opening")

    if "max_company_age_years" in eligibility:
        maximum = number(eligibility["max_company_age_years"], "eligibility.max_company_age_years")
        if "company_age_years" in profile:
            if number(profile["company_age_years"], "profile.company_age_years") > maximum:
                reasons.append("company age exceeds the account eligibility limit")
        elif "company_age_at_most" in profile:
            if number(profile["company_age_at_most"], "profile.company_age_at_most") > maximum:
                reasons.append("confirmed company-age bound does not establish eligibility")
        else:
            reasons.append("company age is needed to verify eligibility")

    comparisons = (
        ("max_overdraft_fee", fees, "overdraft_fee", "overdraft fee is not documented for this candidate", "overdraft fee exceeds the customer's maximum"),
        ("min_atm_rebate_monthly", perks, "atm_rebate_monthly", "monthly ATM rebate is not documented for this candidate", "monthly ATM rebate is below the customer's minimum"),
        ("min_apy", perks, "apy", "APY is not documented for this candidate", "APY is below the customer's minimum"),
        ("max_minimum_funding_requirement", opening, "minimum_funding_requirement", "minimum funding requirement is not documented for this candidate", "minimum funding requirement exceeds the customer's maximum"),
        ("max_minimum_balance_requirement", opening, "minimum_balance_requirement", "minimum balance requirement is not documented for this candidate", "minimum balance requirement exceeds the customer's maximum"),
    )
    for requirement_name, source, field, missing, failure in comparisons:
        if requirement_name not in requirements:
            continue
        if field not in source:
            reasons.append(missing)
            continue
        actual = number(source[field], f"candidate.{field}")
        requested = number(requirements[requirement_name], f"requirements.{requirement_name}")
        if requirement_name.startswith("min_"):
            if actual < requested:
                reasons.append(failure)
        elif actual > requested:
            reasons.append(failure)

    return reasons


def active_priority(payload):
    if "as_of" not in payload:
        return []
    today = iso_day(payload["as_of"], "as_of")
    promotions = payload.get("promotions", [])
    if not isinstance(promotions, list):
        raise ValueError("promotions must be a list")

    priority = []
    for index, promotion in enumerate(promotions):
        if not isinstance(promotion, dict):
            raise ValueError(f"promotions[{index}] must be an object")
        start = iso_day(promotion.get("start_date"), f"promotions[{index}].start_date")
        end = iso_day(promotion.get("end_date"), f"promotions[{index}].end_date")
        if end < start:
            raise ValueError(f"promotions[{index}] ends before it starts")
        listed = promotion.get("priority", [])
        if not isinstance(listed, list) or not all(isinstance(item, str) and item for item in listed):
            raise ValueError(f"promotions[{index}].priority must be a list of candidate ids")
        if start <= today <= end:
            for candidate_id in listed:
                if candidate_id not in priority:
                    priority.append(candidate_id)
    return priority


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    profile = mapping(payload.get("profile"), "profile")
    requirements = mapping(payload.get("requirements"), "requirements")
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
        assessments.append({"candidate": candidate, "reasons": candidate_reasons(candidate, profile, requirements)})

    priority = active_priority(payload)
    rank = {candidate_id: position for position, candidate_id in enumerate(priority)}
    qualifying = [item for item in assessments if not item["reasons"]]
    result = {
        "active_promotion_priority": priority,
        "assessments": [
            {
                "id": item["candidate"]["id"],
                "name": item["candidate"]["name"],
                "rejection_reasons": item["reasons"],
            }
            for item in assessments
        ],
    }
    if not qualifying:
        result.update({"status": "no_qualifying_candidate", "recommendation": None})
        return result

    def ordering(item):
        candidate = item["candidate"]
        promotion_rank = rank.get(candidate["id"], len(priority) + 1)
        score = number(candidate.get("preference_score", 0), "candidate.preference_score")
        return (promotion_rank, -score, candidate["id"])

    selected = sorted(qualifying, key=ordering)[0]["candidate"]
    result.update({
        "status": "selected",
        "recommendation": {
            "id": selected["id"],
            "name": selected["name"],
            "customer_benefit_notes": selected.get("customer_benefit_notes", []),
            "cautions": selected.get("cautions", []),
            "promotion_priority_applied": selected["id"] in rank,
        },
    })
    return result


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False, sort_keys=True))
    except (json.JSONDecodeError, ValueError) as error:
        print(json.dumps({"status": "input_error", "error": str(error)}))
        sys.exit(2)
