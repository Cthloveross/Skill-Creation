#!/usr/bin/env python3
"""Evaluate normalized credit-card constraints from JSON stdin to JSON stdout.

The program does not perform external I/O, make approval decisions, or apply for
products. Null eligibility prerequisites are treated as not published, rather
than prerequisites that may be invented. Null requested feature facts produce
insufficient-information results.
"""

import json
import math
import sys
from typing import Any, Dict, List, Optional, Tuple


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def is_nonnegative_number(value: Any) -> bool:
    return is_number(value) and float(value) >= 0


def check(bucket: List[Dict[str, str]], name: str, result: str, detail: str) -> None:
    bucket.append({"check": name, "result": result, "detail": detail})


def evaluate_card(card: Dict[str, Any], profile: Dict[str, Any], requirements: Dict[str, Any]) -> Dict[str, Any]:
    passed: List[Dict[str, str]] = []
    failed: List[Dict[str, str]] = []
    unknown: List[Dict[str, str]] = []
    not_assessed: List[Dict[str, str]] = []

    minimum_score = card.get("minimum_credit_score")
    customer_score = profile.get("credit_score")
    if minimum_score is None:
        check(not_assessed, "minimum_credit_score", "not_published", "No minimum credit score is published in the supplied card facts.")
    elif customer_score is None:
        check(unknown, "minimum_credit_score", "unknown", "Customer credit score is needed to compare with the published minimum.")
    elif float(customer_score) >= float(minimum_score):
        check(passed, "minimum_credit_score", "pass", "Customer score meets the published minimum credit score.")
    else:
        check(failed, "minimum_credit_score", "fail", "Customer score is below the published minimum credit score.")

    subscription_required = card.get("premium_subscription_required")
    has_subscription = profile.get("has_premium_subscription")
    if subscription_required is None:
        check(not_assessed, "premium_subscription", "not_published", "No subscription prerequisite is published in the supplied card facts.")
    elif subscription_required is False:
        check(passed, "premium_subscription", "pass", "The published terms do not require a premium subscription.")
    elif has_subscription is None:
        check(unknown, "premium_subscription", "unknown", "Customer subscription status is needed for the published prerequisite.")
    elif has_subscription:
        check(passed, "premium_subscription", "pass", "Customer has the published required subscription.")
    else:
        check(failed, "premium_subscription", "fail", "Card requires a subscription the customer does not have.")

    invitation_only = card.get("invitation_only")
    invitation_received = profile.get("invitation_received")
    if invitation_only is None:
        check(not_assessed, "invitation", "not_published", "No invitation prerequisite is published in the supplied card facts.")
    elif invitation_only is False:
        check(passed, "invitation", "pass", "The card is not invitation-only.")
    elif invitation_received is None:
        check(unknown, "invitation", "unknown", "Customer invitation status is needed for the published prerequisite.")
    elif invitation_received:
        check(passed, "invitation", "pass", "Customer has the required invitation.")
    else:
        check(failed, "invitation", "fail", "Card is invitation-only and the customer has no invitation.")

    maximum_foreign_fee = requirements.get("max_foreign_transaction_fee_pct")
    foreign_fee = card.get("foreign_transaction_fee_pct")
    if maximum_foreign_fee is not None:
        if foreign_fee is None:
            check(unknown, "foreign_transaction_fee", "unknown", "Published foreign transaction fee is missing.")
        elif float(foreign_fee) <= float(maximum_foreign_fee):
            check(passed, "foreign_transaction_fee", "pass", "Published foreign transaction fee is within the requested maximum.")
        else:
            check(failed, "foreign_transaction_fee", "fail", "Published foreign transaction fee exceeds the requested maximum.")

    maximum_payment = requirements.get("max_minimum_payment_pct")
    minimum_payment = card.get("minimum_payment_pct")
    basis = card.get("minimum_payment_basis")
    if maximum_payment is not None:
        if minimum_payment is None:
            check(unknown, "minimum_payment", "unknown", "Published minimum-payment percentage is missing.")
        elif float(minimum_payment) <= float(maximum_payment):
            detail = "Published minimum-payment percentage is within the requested maximum."
            if basis:
                detail += " Published basis: {}.".format(basis)
            check(passed, "minimum_payment", "pass", detail)
        else:
            detail = "Published minimum-payment percentage exceeds the requested maximum."
            if basis:
                detail += " Published basis: {}.".format(basis)
            check(failed, "minimum_payment", "fail", detail)

    if requirements.get("requires_virtual_card_management", False):
        virtual_cards = card.get("virtual_card_management")
        if virtual_cards is None:
            check(unknown, "virtual_card_management", "unknown", "Virtual-card-management availability is missing.")
        elif virtual_cards:
            check(passed, "virtual_card_management", "pass", "Virtual-card management is available.")
        else:
            check(failed, "virtual_card_management", "fail", "Virtual-card management is not available.")

    status = "incompatible" if failed else ("insufficient_information" if unknown else "compatible")
    return {
        "name": card["name"],
        "status": status,
        "passed": passed,
        "failed": failed,
        "unknown": unknown,
        "not_assessed": not_assessed,
    }


def validate(payload: Any) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    if not isinstance(payload, dict):
        return None, ["Input must be a JSON object."]
    profile = payload.get("profile", {})
    requirements = payload.get("requirements")
    cards = payload.get("cards")
    errors: List[str] = []
    if not isinstance(profile, dict):
        errors.append("profile must be an object.")
    if not isinstance(requirements, dict):
        errors.append("requirements must be an object.")
    if not isinstance(cards, list) or not cards:
        errors.append("cards must be a nonempty array.")

    if isinstance(profile, dict):
        if profile.get("credit_score") is not None and not is_nonnegative_number(profile.get("credit_score")):
            errors.append("profile.credit_score must be a nonnegative number or null.")
        for key in ("has_premium_subscription", "invitation_received"):
            if profile.get(key) is not None and not isinstance(profile.get(key), bool):
                errors.append("profile.{} must be a boolean or null.".format(key))
    if isinstance(requirements, dict):
        for key in ("max_foreign_transaction_fee_pct", "max_minimum_payment_pct"):
            if requirements.get(key) is not None and not is_nonnegative_number(requirements.get(key)):
                errors.append("requirements.{} must be a nonnegative number or null.".format(key))
        if "requires_virtual_card_management" in requirements and not isinstance(requirements["requires_virtual_card_management"], bool):
            errors.append("requirements.requires_virtual_card_management must be a boolean.")
    if isinstance(cards, list):
        for index, card in enumerate(cards):
            prefix = "cards[{}]".format(index)
            if not isinstance(card, dict):
                errors.append(prefix + " must be an object.")
                continue
            if not isinstance(card.get("name"), str) or not card["name"].strip():
                errors.append(prefix + ".name must be a nonempty string.")
            for key in ("minimum_credit_score", "foreign_transaction_fee_pct", "minimum_payment_pct"):
                if card.get(key) is not None and not is_nonnegative_number(card.get(key)):
                    errors.append(prefix + ".{} must be a nonnegative number or null.".format(key))
            for key in ("premium_subscription_required", "invitation_only", "virtual_card_management"):
                if card.get(key) is not None and not isinstance(card.get(key), bool):
                    errors.append(prefix + ".{} must be a boolean or null.".format(key))
            if card.get("minimum_payment_basis") is not None and not isinstance(card.get("minimum_payment_basis"), str):
                errors.append(prefix + ".minimum_payment_basis must be a string or null.")
    if errors:
        return None, errors
    return {"profile": profile, "requirements": requirements, "cards": cards}, []


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "errors": ["Invalid JSON: {}".format(exc.msg)]}, sort_keys=True))
        return
    request, errors = validate(payload)
    if errors:
        print(json.dumps({"ok": False, "errors": errors}, sort_keys=True))
        return
    results = [evaluate_card(card, request["profile"], request["requirements"]) for card in request["cards"]]
    compatible = [result["name"] for result in results if result["status"] == "compatible"]
    print(json.dumps({"ok": True, "compatible_cards": compatible, "results": results}, sort_keys=True))


if __name__ == "__main__":
    main()
