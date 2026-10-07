#!/usr/bin/env python3
"""Select one evidence-supported business checking account.

Reads a JSON object matching the schema in SKILL.md from stdin and writes a JSON
assessment to stdout. This is advisory only and never performs a banking action.
"""

import json
import sys
from datetime import date
from decimal import Decimal, InvalidOperation


def mapping(value, path):
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{path} must be an object")
    return value


def number(value, path):
    if value is None or isinstance(value, bool):
        raise ValueError(f"{path} must be a finite number")
    try:
        value = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{path} must be a finite number")
    if not value.is_finite():
        raise ValueError(f"{path} must be a finite number")
    return value


def parse_date(value, path):
    if not isinstance(value, str) or len(value) < 10:
        raise ValueError(f"{path} must be an ISO date or timestamp")
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        raise ValueError(f"{path} must begin YYYY-MM-DD")


def evaluate_age(profile, eligibility):
    if "max_company_age_years" not in eligibility:
        return [], []
    maximum = number(eligibility["max_company_age_years"], "eligibility.max_company_age_years")
    if "company_age_years" in profile:
        if number(profile["company_age_years"], "profile.company_age_years") > maximum:
            return ["company age exceeds account eligibility limit"], []
        return [], []
    if "company_age_at_most" in profile:
        if number(profile["company_age_at_most"], "profile.company_age_at_most") > maximum:
            return [], ["confirmed company-age bound does not establish eligibility"]
        return [], []
    return [], ["company age is needed to verify eligibility"]


def evaluate_requirements(requirements, fees, perks, opening):
    checks = (
        ("max_overdraft_fee", fees, "overdraft_fee", "overdraft fee", "max"),
        ("min_atm_rebate_monthly", perks, "atm_rebate_monthly", "monthly ATM rebate", "min"),
        ("min_apy", perks, "apy", "APY", "min"),
        ("max_minimum_funding_requirement", opening, "minimum_funding_requirement", "minimum funding requirement", "max"),
        ("max_minimum_balance_requirement", opening, "minimum_balance_requirement", "minimum balance requirement", "max"),
    )
    failed, unresolved = [], []
    for request_key, source, fact_key, label, direction in checks:
        if request_key not in requirements:
            continue
        if fact_key not in source:
            unresolved.append(f"{label} is not documented")
            continue
        actual = number(source[fact_key], f"candidate.{fact_key}")
        requested = number(requirements[request_key], f"requirements.{request_key}")
        fails = actual > requested if direction == "max" else actual < requested
        if fails:
            failed.append(f"{label} does not meet customer requirement")
    return failed, unresolved


def assess(candidate, profile, requirements):
    eligibility = mapping(candidate.get("eligibility"), "candidate.eligibility")
    fees = mapping(candidate.get("fees"), "candidate.fees")
    perks = mapping(candidate.get("perks"), "candidate.perks")
    opening = mapping(candidate.get("opening"), "candidate.opening")
    age_failed, age_unknown = evaluate_age(profile, eligibility)
    term_failed, term_unknown = evaluate_requirements(requirements, fees, perks, opening)
    return age_failed + term_failed, age_unknown + term_unknown


def active_priority(payload):
    if "as_of" not in payload:
        return []
    today = parse_date(payload["as_of"], "as_of")
    promotions = payload.get("promotions", [])
    if not isinstance(promotions, list):
        raise ValueError("promotions must be a list")
    priority = []
    for index, promotion in enumerate(promotions):
        if not isinstance(promotion, dict):
            raise ValueError(f"promotions[{index}] must be an object")
        start = parse_date(promotion.get("start_date"), f"promotions[{index}].start_date")
        end = parse_date(promotion.get("end_date"), f"promotions[{index}].end_date")
        if end < start:
            raise ValueError(f"promotions[{index}] ends before it starts")
        listed = promotion.get("priority", [])
        if not isinstance(listed, list) or not all(isinstance(x, str) and x for x in listed):
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

    assessed = []
    ids = set()
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            raise ValueError(f"candidates[{index}] must be an object")
        candidate_id, name = candidate.get("id"), candidate.get("name")
        if not isinstance(candidate_id, str) or not candidate_id:
            raise ValueError(f"candidates[{index}].id must be a nonempty string")
        if candidate_id in ids:
            raise ValueError("candidate ids must be unique")
        ids.add(candidate_id)
        if not isinstance(name, str) or not name:
            raise ValueError(f"candidates[{index}].name must be a nonempty string")
        failed, unresolved = assess(candidate, profile, requirements)
        assessed.append({"candidate": candidate, "failed": failed, "unresolved": unresolved})

    priority = active_priority(payload)
    ranks = {candidate_id: index for index, candidate_id in enumerate(priority)}
    result = {
        "active_promotion_priority": priority,
        "assessments": [
            {
                "id": item["candidate"]["id"],
                "name": item["candidate"]["name"],
                "failed_requirements": item["failed"],
                "unresolved_requirements": item["unresolved"],
            }
            for item in assessed
        ],
    }
    qualifying = [item for item in assessed if not item["failed"] and not item["unresolved"]]
    if qualifying:
        def order(item):
            candidate = item["candidate"]
            promotion_rank = ranks.get(candidate["id"], len(priority) + 1)
            score = number(candidate.get("preference_score", 0), "candidate.preference_score")
            return promotion_rank, -score, candidate["id"]
        selected = min(qualifying, key=order)["candidate"]
        result.update({
            "status": "selected",
            "recommendation": {
                "id": selected["id"],
                "name": selected["name"],
                "customer_benefit_notes": selected.get("customer_benefit_notes", []),
                "cautions": selected.get("cautions", []),
                "promotion_priority_applied": selected["id"] in ranks,
            },
        })
        return result

    candidates_without_failures = [item for item in assessed if not item["failed"]]
    if candidates_without_failures:
        result.update({"status": "insufficient_evidence", "recommendation": None})
    else:
        result.update({"status": "no_qualifying_candidate", "recommendation": None})
    return result


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), ensure_ascii=False, sort_keys=True))
    except (json.JSONDecodeError, ValueError) as error:
        print(json.dumps({"status": "input_error", "error": str(error)}))
        sys.exit(2)
