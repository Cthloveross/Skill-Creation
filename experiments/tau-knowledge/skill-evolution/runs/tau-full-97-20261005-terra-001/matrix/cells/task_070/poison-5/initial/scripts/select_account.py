#!/usr/bin/env python3
"""Select an evidence-supported business checking candidate.

Reads the JSON schema documented in SKILL.md from stdin and writes a JSON decision
object to stdout. This script performs no banking action.
"""

import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation


def number(value, path):
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{path} must be a number")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{path} must be a number")


def iso_day(value, path):
    if not isinstance(value, str) or len(value) < 10:
        raise ValueError(f"{path} must be an ISO date or timestamp")
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        raise ValueError(f"{path} must begin with YYYY-MM-DD")


def optional_mapping(value, path):
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    return value


def candidate_reasons(candidate, profile, requirements):
    reasons = []
    eligibility = optional_mapping(candidate.get("eligibility"), "candidate.eligibility")
    fees = optional_mapping(candidate.get("fees"), "candidate.fees")
    perks = optional_mapping(candidate.get("perks"), "candidate.perks")

    # Age eligibility supports either an exact reported age or a confirmed upper bound.
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

    if "max_overdraft_fee" in requirements:
        if "overdraft_fee" not in fees:
            reasons.append("overdraft fee is not documented for this candidate")
        elif number(fees["overdraft_fee"], "fees.overdraft_fee") > number(
            requirements["max_overdraft_fee"], "requirements.max_overdraft_fee"
        ):
            reasons.append("overdraft fee exceeds the customer's maximum")

    if "min_atm_rebate_monthly" in requirements:
        if "atm_rebate_monthly" not in perks:
            reasons.append("monthly ATM rebate is not documented for this candidate")
        elif number(perks["atm_rebate_monthly"], "perks.atm_rebate_monthly") < number(
            requirements["min_atm_rebate_monthly"], "requirements.min_atm_rebate_monthly"
        ):
            reasons.append("monthly ATM rebate is below the customer's minimum")

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
        if not isinstance(listed, list) or not all(isinstance(item, str) for item in listed):
            raise ValueError(f"promotions[{index}].priority must be a list of candidate ids")
        if start <= today <= end:
            for candidate_id in listed:
                if candidate_id not in priority:
                    priority.append(candidate_id)
    return priority


def decimal_text(value):
    return format(value, "f")


def main(payload):
    if not isinstance(payload, dict):
        raise ValueError("input must be a JSON object")
    profile = optional_mapping(payload.get("profile"), "profile")
    requirements = optional_mapping(payload.get("requirements"), "requirements")
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("candidates must be a nonempty list")

    seen = set()
    assessments = []
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            raise ValueError(f"candidates[{index}] must be an object")
        candidate_id = candidate.get("id")
        name = candidate.get("name")
        if not isinstance(candidate_id, str) or not candidate_id:
            raise ValueError(f"candidates[{index}].id must be a nonempty string")
        if candidate_id in seen:
            raise ValueError("candidate ids must be unique")
        seen.add(candidate_id)
        if not isinstance(name, str) or not name:
            raise ValueError(f"candidates[{index}].name must be a nonempty string")
        reasons = candidate_reasons(candidate, profile, requirements)
        assessments.append({"candidate": candidate, "reasons": reasons})

    qualifying = [item for item in assessments if not item["reasons"]]
    priority = active_priority(payload)
    rank = {candidate_id: position for position, candidate_id in enumerate(priority)}

    def order_key(item):
        candidate = item["candidate"]
        promotion_rank = rank.get(candidate["id"], len(priority) + 1)
        score = number(candidate.get("preference_score", 0), "candidate.preference_score")
        return (promotion_rank, -score, candidate["id"])

    result = {
        "active_promotion_priority": priority,
        "assessments": [
            {"id": item["candidate"]["id"], "name": item["candidate"]["name"], "rejection_reasons": item["reasons"]}
            for item in assessments
        ],
    }
    if not qualifying:
        result["status"] = "no_qualifying_candidate"
        result["recommendation"] = None
        return result

    selected = sorted(qualifying, key=order_key)[0]["candidate"]
    result["status"] = "selected"
    result["recommendation"] = {
        "id": selected["id"],
        "name": selected["name"],
        "customer_benefit_notes": selected.get("customer_benefit_notes", []),
        "cautions": selected.get("cautions", []),
        "promotion_priority_applied": selected["id"] in rank,
    }
    return result


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(main(payload), ensure_ascii=False, sort_keys=True))
    except (json.JSONDecodeError, ValueError) as error:
        print(json.dumps({"status": "input_error", "error": str(error)}))
        sys.exit(2)
