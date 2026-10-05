#!/usr/bin/env python3
"""Evaluate packaged card products against supplied selection criteria.

Input: one JSON object on stdin as documented in SKILL.md.
Output: one JSON object on stdout. No account or banking action is performed.
"""

import json
import sys
from pathlib import Path

CATALOG_PATH = Path(__file__).resolve().parent.parent / "references" / "card_catalog.json"


def fail(message):
    print(json.dumps({"status": "error", "message": message}, sort_keys=True))
    return 0


def get_object(value, name):
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return value


def optional_number(value, name):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number or null")
    return value


def optional_bool(value, name):
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be true, false, or null")
    return value


def eligibility_assessment(card, score, access):
    blockers = []
    conditions = []
    minimum = card.get("minimum_credit_score")
    if minimum is not None:
        if score is None:
            conditions.append(f"minimum credit score of {minimum} must be met")
        elif score < minimum:
            blockers.append(f"supplied credit score {score} is below the stated minimum of {minimum}")

    for access_key, label in card.get("required_access", {}).items():
        supplied = access.get(access_key)
        if supplied is False:
            blockers.append(f"requires {label}")
        elif supplied is None:
            conditions.append(f"requires {label}; status is unknown")

    if card.get("invitation_only"):
        invitation = access.get("diamond_elite_invitation")
        if invitation is False:
            blockers.append("membership is invitation-only and no invitation is available")
        elif invitation is None:
            conditions.append("membership is invitation-only; invitation status is unknown")

    return {
        "known_blockers": blockers,
        "unknown_or_needed_conditions": conditions,
        "published_eligibility_is_not_approval": True,
    }


def product_reasons(card, requirements):
    reasons = []
    requested_limit = requirements.get("min_credit_limit")
    if requested_limit is not None and card["credit_limit_range"][1] < requested_limit:
        reasons.append(
            f"published maximum possible limit of {card['credit_limit_range'][1]} is below requested {requested_limit}"
        )

    fee_max = requirements.get("foreign_transaction_fee_percent_max")
    if fee_max is not None and card["foreign_transaction_fee_percent"] > fee_max:
        reasons.append(
            f"foreign transaction fee of {card['foreign_transaction_fee_percent']}% exceeds requested maximum {fee_max}%"
        )

    if requirements.get("purchase_protection_required") is True and not card["purchase_protection"]["available"]:
        reasons.append("does not include published purchase protection")
    return reasons


def public_card(card, assessment, reasons=None):
    result = {
        "card": card["name"],
        "credit_limit_range": card["credit_limit_range"],
        "annual_fee": card["annual_fee"],
        "foreign_transaction_fee_percent": card["foreign_transaction_fee_percent"],
        "cash_back_percent_on_eligible_purchases": card["cash_back_percent_on_eligible_purchases"],
        "purchase_protection": card["purchase_protection"],
        "eligibility": card["eligibility_text"],
        "source_documents": card["source_documents"],
    }
    if assessment is not None:
        result["eligibility_assessment"] = assessment
    if reasons:
        result["reasons"] = reasons
    return result


def main():
    try:
        raw = json.load(sys.stdin)
        if not isinstance(raw, dict):
            raise ValueError("input must be a JSON object")
        requirements = get_object(raw.get("requirements"), "requirements")
        preferences = get_object(raw.get("preferences"), "preferences")
        access = get_object(raw.get("access"), "access")

        normalized_requirements = {
            "min_credit_limit": optional_number(requirements.get("min_credit_limit"), "requirements.min_credit_limit"),
            "foreign_transaction_fee_percent_max": optional_number(
                requirements.get("foreign_transaction_fee_percent_max"),
                "requirements.foreign_transaction_fee_percent_max",
            ),
            "purchase_protection_required": optional_bool(
                requirements.get("purchase_protection_required"),
                "requirements.purchase_protection_required",
            ),
        }
        score = optional_number(preferences.get("credit_score"), "preferences.credit_score")
        for key in ("diamond_elite_invitation", "rho_bank_plus_subscription"):
            if key in access:
                access[key] = optional_bool(access[key], f"access.{key}")

        with CATALOG_PATH.open("r", encoding="utf-8") as handle:
            catalog = json.load(handle)["cards"]

        matches = []
        excluded = []
        for card in catalog:
            reasons = product_reasons(card, normalized_requirements)
            assessment = eligibility_assessment(card, score, access)
            if reasons:
                excluded.append(public_card(card, None, reasons))
            else:
                matches.append(public_card(card, assessment))

        prioritize_rewards = preferences.get("prioritize_everyday_rewards", True)
        if not isinstance(prioritize_rewards, bool):
            raise ValueError("preferences.prioritize_everyday_rewards must be true or false")

        def rank(item):
            blockers = len(item["eligibility_assessment"]["known_blockers"])
            unknowns = len(item["eligibility_assessment"]["unknown_or_needed_conditions"])
            reward = item["cash_back_percent_on_eligible_purchases"]
            fee = item["annual_fee"]
            # Known eligibility blockers always rank after candidates without them.
            return (blockers, -reward if prioritize_rewards else 0, fee, unknowns, item["card"])

        matches.sort(key=rank)
        excluded.sort(key=lambda item: item["card"])
        output = {
            "status": "ok",
            "requirements": normalized_requirements,
            "feature_matches": matches,
            "excluded_by_product_features": excluded,
            "recommendation_basis": (
                "Higher published flat cash-back rate, then lower annual fee, after known eligibility blockers"
                if prioritize_rewards
                else "Lower annual fee, after known eligibility blockers"
            ),
            "limit_disclosure": "A published range that reaches the requested amount indicates possibility only; assigned limits remain subject to underwriting.",
        }
        if matches:
            output["recommended"] = matches[0]
        print(json.dumps(output, indent=2, sort_keys=True))
        return 0
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        return fail(str(exc))


if __name__ == "__main__":
    sys.exit(main())
