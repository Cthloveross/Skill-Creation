#!/usr/bin/env python3
"""Select a business checking account using verified structured facts.

Input JSON object:
{
  "requirements": [{"field": str, "operator": "equals"|"at_least"|
                    "at_most"|"contains", "value": scalar}],
  "offers": [{"name": str, "facts": {str: scalar},
              "evidence": {str: str}, "promotion_rank": positive number optional}],
  "promotion_active": bool optional,
  "tie_breakers": [{"field": str, "direction": "highest"|"lowest"}] optional
}

A fact omitted from an offer is unknown, not false. `contains` requires a list,
set, tuple, or string fact. Values must already be normalized to comparable units.

Output JSON object has `status` of selected, no_verified_match, ambiguous, or
invalid_input. It never chooses an account with an unknown or failed hard
requirement.
"""
import json
import math
import sys
from typing import Any, Dict, List, Tuple

OPERATORS = {"equals", "at_least", "at_most", "contains"}
DIRECTIONS = {"highest", "lowest"}


def finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def compare(actual: Any, operator: str, expected: Any) -> bool:
    if operator == "equals":
        return actual == expected
    if operator == "at_least":
        return finite_number(actual) and finite_number(expected) and actual >= expected
    if operator == "at_most":
        return finite_number(actual) and finite_number(expected) and actual <= expected
    if operator == "contains":
        if isinstance(actual, (list, tuple, set, str)):
            return expected in actual
        return False
    raise ValueError("unsupported operator")


def clean_requirement(requirement: Any, index: int) -> Tuple[Dict[str, Any], str]:
    if not isinstance(requirement, dict):
        return {}, "requirement %d must be an object" % index
    field = requirement.get("field")
    operator = requirement.get("operator")
    if not isinstance(field, str) or not field:
        return {}, "requirement %d needs a nonempty field" % index
    if operator not in OPERATORS:
        return {}, "requirement %d has unsupported operator" % index
    if "value" not in requirement:
        return {}, "requirement %d needs a value" % index
    if operator in {"at_least", "at_most"} and not finite_number(requirement["value"]):
        return {}, "requirement %d comparison value must be a finite number" % index
    return {"field": field, "operator": operator, "value": requirement["value"]}, ""


def assessment(offer: Dict[str, Any], requirements: List[Dict[str, Any]]) -> Dict[str, Any]:
    facts = offer["facts"]
    evidence = offer.get("evidence", {})
    matched, failed, unknown = [], [], []
    for req in requirements:
        field = req["field"]
        item = {"field": field, "operator": req["operator"], "required_value": req["value"]}
        # A structured fact without a usable source is not verified evidence.
        # Treat it as unknown rather than letting an unsupported claim qualify.
        source = evidence.get(field)
        if field not in facts or facts[field] is None or not isinstance(source, str) or not source.strip():
            unknown.append(item)
            continue
        item["actual_value"] = facts[field]
        if compare(facts[field], req["operator"], req["value"]):
            item["evidence"] = source
            matched.append(item)
        else:
            failed.append(item)
    return {
        "name": offer["name"],
        "matched_requirements": matched,
        "failed_requirements": failed,
        "unknown_requirements": unknown,
        "eligible": not failed and not unknown,
    }


def rank_by_tiebreakers(offers: List[Dict[str, Any]], tie_breakers: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    """Return all offers tied for best; unknown tie-breaker facts cannot win."""
    remaining = offers[:]
    for rule in tie_breakers:
        field, direction = rule["field"], rule["direction"]
        known = [offer for offer in remaining if finite_number(offer["facts"].get(field))]
        if not known:
            continue
        values = [offer["facts"][field] for offer in known]
        best = max(values) if direction == "highest" else min(values)
        winners = [offer for offer in known if offer["facts"][field] == best]
        # A tie-breaker only resolves candidates when every remaining candidate
        # has a documented comparable value; otherwise it would reward missing data.
        if len(known) == len(remaining):
            remaining = winners
        if len(remaining) == 1:
            break
    return remaining


def main(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {"status": "invalid_input", "errors": ["top-level JSON must be an object"]}
    raw_requirements = payload.get("requirements")
    raw_offers = payload.get("offers")
    if not isinstance(raw_requirements, list) or not raw_requirements:
        return {"status": "invalid_input", "errors": ["requirements must be a nonempty list"]}
    if not isinstance(raw_offers, list) or not raw_offers:
        return {"status": "invalid_input", "errors": ["offers must be a nonempty list"]}

    errors, requirements = [], []
    for i, raw in enumerate(raw_requirements):
        item, error = clean_requirement(raw, i)
        if error:
            errors.append(error)
        else:
            requirements.append(item)

    offers = []
    seen_names = set()
    for i, raw in enumerate(raw_offers):
        if not isinstance(raw, dict):
            errors.append("offer %d must be an object" % i)
            continue
        name, facts = raw.get("name"), raw.get("facts")
        if not isinstance(name, str) or not name:
            errors.append("offer %d needs a nonempty name" % i)
            continue
        if name in seen_names:
            errors.append("offer names must be unique")
            continue
        seen_names.add(name)
        if not isinstance(facts, dict):
            errors.append("offer %s facts must be an object" % name)
            continue
        evidence = raw.get("evidence", {})
        if not isinstance(evidence, dict):
            errors.append("offer %s evidence must be an object" % name)
            continue
        rank = raw.get("promotion_rank")
        if rank is not None and (not finite_number(rank) or rank <= 0):
            errors.append("offer %s promotion_rank must be a positive number" % name)
            continue
        offers.append({"name": name, "facts": facts, "evidence": evidence, "promotion_rank": rank})

    raw_tiebreakers = payload.get("tie_breakers", [])
    tie_breakers = []
    if not isinstance(raw_tiebreakers, list):
        errors.append("tie_breakers must be a list")
    else:
        for i, rule in enumerate(raw_tiebreakers):
            if not isinstance(rule, dict) or not isinstance(rule.get("field"), str) or rule.get("direction") not in DIRECTIONS:
                errors.append("tie_breaker %d needs field and direction (highest or lowest)" % i)
            else:
                tie_breakers.append({"field": rule["field"], "direction": rule["direction"]})
    if errors:
        return {"status": "invalid_input", "errors": errors}

    assessments = [assessment(offer, requirements) for offer in offers]
    eligible_names = {item["name"] for item in assessments if item["eligible"]}
    eligible = [offer for offer in offers if offer["name"] in eligible_names]
    if not eligible:
        return {"status": "no_verified_match", "offer_assessments": assessments}

    active_promotion = payload.get("promotion_active", False)
    if not isinstance(active_promotion, bool):
        return {"status": "invalid_input", "errors": ["promotion_active must be boolean"]}
    if active_promotion:
        promoted = [offer for offer in eligible if offer["promotion_rank"] is not None]
        if promoted:
            top_rank = min(offer["promotion_rank"] for offer in promoted)
            finalists = [offer for offer in promoted if offer["promotion_rank"] == top_rank]
            basis = "active promotional priority among offers verified to meet every requirement"
        else:
            finalists = eligible
            basis = "verified requirements; no eligible offer has an applicable promotion rank"
    else:
        finalists = eligible
        basis = "verified requirements"

    if len(finalists) > 1 and tie_breakers:
        narrowed = rank_by_tiebreakers(finalists, tie_breakers)
        if len(narrowed) < len(finalists):
            finalists = narrowed
            basis += "; customer-relevant evidence-supported tie breaker"

    if len(finalists) != 1:
        return {
            "status": "ambiguous",
            "selection_basis": basis,
            "remaining_offers": [offer["name"] for offer in finalists],
            "offer_assessments": assessments,
        }

    chosen = finalists[0]
    chosen_assessment = next(item for item in assessments if item["name"] == chosen["name"])
    return {
        "status": "selected",
        "recommendation": chosen["name"],
        "selection_basis": basis,
        "matched_requirements": chosen_assessment["matched_requirements"],
        "selected_facts": chosen["facts"],
        "selected_evidence": chosen["evidence"],
        "offer_assessments": assessments,
    }


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        result = main(payload)
    except json.JSONDecodeError as exc:
        result = {"status": "invalid_input", "errors": ["invalid JSON: " + str(exc)]}
    except Exception as exc:  # Keep the executable interface JSON-only.
        result = {"status": "invalid_input", "errors": ["unexpected input error: " + str(exc)]}
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
