#!/usr/bin/env python3
"""Evaluate normalized credit-card eligibility and feature constraints.

Input and output are JSON objects on stdin/stdout. This program performs no
external I/O and intentionally makes no approval or application decision.
"""

import json
import math
import sys
from typing import Any, Dict, List, Optional, Tuple


def is_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def nonnegative_number(value: Any) -> bool:
    return is_number(value) and float(value) >= 0


def add_check(
    bucket: List[Dict[str, Any]],
    check: str,
    result: str,
    detail: str,
) -> None:
    bucket.append({"check": check, "result": result, "detail": detail})


def evaluate_card(
    card: Dict[str, Any], profile: Dict[str, Any], requirements: Dict[str, Any]
) -> Dict[str, Any]:
    passed: List[Dict[str, Any]] = []
    failed: List[Dict[str, Any]] = []
    unknown: List[Dict[str, Any]] = []

    score_min = card.get("minimum_credit_score")
    score = profile.get("credit_score")
    if score_min is None:
        add_check(unknown, "minimum_credit_score", "unknown", "Published minimum credit score is missing.")
    elif score is None:
        add_check(unknown, "minimum_credit_score", "unknown", "Customer credit score is missing.")
    elif float(score) >= float(score_min):
        add_check(passed, "minimum_credit_score", "pass", "Customer score meets the published minimum.")
    else:
        add_check(failed, "minimum_credit_score", "fail", "Customer score is below the published minimum.")

    subscription_required = card.get("premium_subscription_required")
    has_subscription = profile.get("has_premium_subscription")
    if subscription_required is None:
        add_check(unknown, "premium_subscription", "unknown", "Subscription requirement is missing.")
    elif subscription_required is False:
        add_check(passed, "premium_subscription", "pass", "No premium subscription is required.")
    elif has_subscription is None:
        add_check(unknown, "premium_subscription", "unknown", "Customer subscription status is missing.")
    elif has_subscription is True:
        add_check(passed, "premium_subscription", "pass", "Customer has the required subscription.")
    else:
        add_check(failed, "premium_subscription", "fail", "Card requires a subscription the customer does not have.")

    invitation_only = card.get("invitation_only")
    invitation_received = profile.get("invitation_received")
    if invitation_only is None:
        add_check(unknown, "invitation", "unknown", "Invitation requirement is missing.")
    elif invitation_only is False:
        add_check(passed, "invitation", "pass", "Card is not invitation-only.")
    elif invitation_received is None:
        add_check(unknown, "invitation", "unknown", "Customer invitation status is missing.")
    elif invitation_received is True:
        add_check(passed, "invitation", "pass", "Customer has an invitation.")
    else:
        add_check(failed, "invitation", "fail", "Card is invitation-only and the customer has no invitation.")

    max_foreign_fee = requirements.get("max_foreign_transaction_fee_pct")
    foreign_fee = card.get("foreign_transaction_fee_pct")
    if max_foreign_fee is not None:
        if foreign_fee is None:
            add_check(unknown, "foreign_transaction_fee", "unknown", "Published foreign transaction fee is missing.")
        elif float(foreign_fee) <= float(max_foreign_fee):
            add_check(passed, "foreign_transaction_fee", "pass", "Published foreign transaction fee is within the requested maximum.")
        else:
            add_check(failed, "foreign_transaction_fee", "fail", "Published foreign transaction fee exceeds the requested maximum.")

    max_min_payment = requirements.get("max_minimum_payment_pct")
    min_payment = card.get("minimum_payment_pct")
    basis = card.get("minimum_payment_basis")
    if max_min_payment is not None:
        if min_payment is None:
            add_check(unknown, "minimum_payment", "unknown", "Published minimum-payment percentage is missing.")
        elif float(min_payment) <= float(max_min_payment):
            detail = "Published minimum-payment percentage is within the requested maximum."
            if basis:
                detail += " Published basis: {}.".format(basis)
            add_check(passed, "minimum_payment", "pass", detail)
        else:
            detail = "Published minimum-payment percentage exceeds the requested maximum."
            if basis:
                detail += " Published basis: {}.".format(basis)
            add_check(failed, "minimum_payment", "fail", detail)

    require_virtual = requirements.get("requires_virtual_card_management", False)
    virtual = card.get("virtual_card_management")
    if require_virtual:
        if virtual is None:
            add_check(unknown, "virtual_card_management", "unknown", "Virtual-card-management availability is missing.")
        elif virtual is True:
            add_check(passed, "virtual_card_management", "pass", "Virtual-card management is available.")
        else:
            add_check(failed, "virtual_card_management", "fail", "Virtual-card management is not available.")

    if failed:
        status = "incompatible"
    elif unknown:
        status = "insufficient_information"
    else:
        status = "compatible"

    return {
        "name": card["name"],
        "status": status,
        "passed": passed,
        "failed": failed,
        "unknown": unknown,
    }


def validate_request(payload: Any) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    errors: List[str] = []
    if not isinstance(payload, dict):
        return None, ["Input must be a JSON object."]

    profile = payload.get("profile", {})
    requirements = payload.get("requirements")
    cards = payload.get("cards")
    if not isinstance(profile, dict):
        errors.append("profile must be an object when provided.")
    if not isinstance(requirements, dict):
        errors.append("requirements must be an object.")
    if not isinstance(cards, list) or not cards:
        errors.append("cards must be a nonempty array.")

    if isinstance(profile, dict):
        for key in ("credit_score",):
            if key in profile and profile[key] is not None and not nonnegative_number(profile[key]):
                errors.append("profile.{} must be a nonnegative number or null.".format(key))
        for key in ("has_premium_subscription", "invitation_received"):
            if key in profile and profile[key] is not None and not isinstance(profile[key], bool):
                errors.append("profile.{} must be a boolean or null.".format(key))

    if isinstance(requirements, dict):
        for key in ("max_foreign_transaction_fee_pct", "max_minimum_payment_pct"):
            if key in requirements and requirements[key] is not None and not nonnegative_number(requirements[key]):
                errors.append("requirements.{} must be a nonnegative number or null.".format(key))
        if "requires_virtual_card_management" in requirements and not isinstance(requirements["requires_virtual_card_management"], bool):
            errors.append("requirements.requires_virtual_card_management must be a boolean.")

    if isinstance(cards, list):
        numeric_fields = ("minimum_credit_score", "foreign_transaction_fee_pct", "minimum_payment_pct")
        bool_fields = ("premium_subscription_required", "invitation_only", "virtual_card_management")
        for index, card in enumerate(cards):
            prefix = "cards[{}]".format(index)
            if not isinstance(card, dict):
                errors.append(prefix + " must be an object.")
                continue
            if not isinstance(card.get("name"), str) or not card["name"].strip():
                errors.append(prefix + ".name must be a nonempty string.")
            for key in numeric_fields:
                if key in card and card[key] is not None and not nonnegative_number(card[key]):
                    errors.append(prefix + ".{} must be a nonnegative number or null.".format(key))
            for key in bool_fields:
                if key in card and card[key] is not None and not isinstance(card[key], bool):
                    errors.append(prefix + ".{} must be a boolean or null.".format(key))
            if "minimum_payment_basis" in card and card["minimum_payment_basis"] is not None and not isinstance(card["minimum_payment_basis"], str):
                errors.append(prefix + ".minimum_payment_basis must be a string or null.")

    if errors:
        return None, errors
    return {
        "profile": profile,
        "requirements": requirements,
        "cards": cards,
    }, []


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "errors": ["Invalid JSON: {}".format(exc.msg)]}))
        return

    request, errors = validate_request(payload)
    if errors:
        print(json.dumps({"ok": False, "errors": errors}, sort_keys=True))
        return

    results = [evaluate_card(card, request["profile"], request["requirements"]) for card in request["cards"]]
    compatible = [result["name"] for result in results if result["status"] == "compatible"]
    print(json.dumps({"ok": True, "compatible_cards": compatible, "results": results}, sort_keys=True))


if __name__ == "__main__":
    main()
