#!/usr/bin/env python3
"""Compare documented credit-card facts to stated requirements.

Reads a JSON object from stdin and writes JSON to stdout. See SKILL.md for schema.
"""
import json
import sys
from decimal import Decimal, InvalidOperation


def number(value, field, errors):
    if value is None:
        return None
    if isinstance(value, bool):
        errors.append(f"{field} must be a number or null")
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        errors.append(f"{field} must be a number or null")
        return None


def compare(card, requirements):
    name = card.get("name")
    errors = []
    if not isinstance(name, str) or not name.strip():
        errors.append("card.name is required")
        name = "Unnamed card"

    reasons = []
    checks = {}
    fields = (
        ("credit_score", "minimum_credit_score", "credit score", "minimum"),
        ("max_foreign_transaction_fee_percent", "foreign_transaction_fee_percent",
         "foreign transaction fee", "maximum"),
        ("max_minimum_payment_percent", "minimum_payment_percent",
         "minimum payment", "maximum"),
    )

    for req_key, card_key, label, mode in fields:
        required = number(requirements.get(req_key), f"requirements.{req_key}", errors)
        actual = number(card.get(card_key), f"cards[].{card_key}", errors)
        if requirements.get(req_key) is None:
            continue
        if actual is None:
            checks[card_key] = "unknown"
            reasons.append(f"{label} is not documented")
            continue
        passed = actual >= required if mode == "minimum" else actual <= required
        checks[card_key] = "pass" if passed else "fail"
        if not passed:
            comparator = "below" if mode == "minimum" else "above"
            reasons.append(f"{label} is {comparator} the requested threshold")

    virtual_required = requirements.get("require_virtual_card_management")
    if virtual_required is not None:
        if not isinstance(virtual_required, bool):
            errors.append("requirements.require_virtual_card_management must be boolean or null")
        else:
            available = card.get("virtual_card_management")
            if not isinstance(available, bool):
                checks["virtual_card_management"] = "unknown"
                reasons.append("virtual card management is not documented")
            elif virtual_required and not available:
                checks["virtual_card_management"] = "fail"
                reasons.append("virtual card management is unavailable")
            else:
                checks["virtual_card_management"] = "pass"

    basis = card.get("minimum_payment_basis")
    if basis is not None and not isinstance(basis, str):
        errors.append("cards[].minimum_payment_basis must be a string or null")
    qualifies = not errors and all(value == "pass" for value in checks.values())
    # With no applicable checks, a card cannot be established as a fit.
    if not checks:
        qualifies = False
        reasons.append("no comparable requirements were supplied")
    return {
        "name": name,
        "qualifies": qualifies,
        "checks": checks,
        "minimum_payment_basis": basis,
        "reasons": reasons,
        "validation_errors": errors,
    }


def main():
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": f"invalid JSON: {exc.msg}"}))
        return
    if not isinstance(payload, dict):
        print(json.dumps({"error": "top-level JSON value must be an object"}))
        return
    requirements = payload.get("requirements")
    cards = payload.get("cards")
    if not isinstance(requirements, dict) or not isinstance(cards, list):
        print(json.dumps({"error": "requirements must be an object and cards must be an array"}))
        return
    results = [compare(card, requirements) if isinstance(card, dict) else {
        "name": "Unnamed card", "qualifies": False, "checks": {},
        "minimum_payment_basis": None, "reasons": ["card must be an object"],
        "validation_errors": ["cards[] must be an object"]
    } for card in cards]
    print(json.dumps({
        "results": results,
        "qualifying_cards": [item["name"] for item in results if item["qualifies"]],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
