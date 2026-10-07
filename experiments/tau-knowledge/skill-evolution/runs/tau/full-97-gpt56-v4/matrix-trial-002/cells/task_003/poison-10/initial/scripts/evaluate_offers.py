#!/usr/bin/env python3
"""Evaluate explicit credit-card offer facts against stated hard requirements.

Reads a JSON object from stdin and writes JSON to stdout. It deliberately does
not infer terms absent from an offer and treats a conditional zero-fee benefit
as non-qualifying for an unconditional zero-fee requirement.
"""
import json
import sys
from typing import Any, Dict, List, Tuple


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def validate_request(payload: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    if not isinstance(payload.get("requirements"), dict):
        errors.append("requirements must be an object")
    if not isinstance(payload.get("offers"), list):
        errors.append("offers must be an array")
    return errors


def assess_offer(offer: Dict[str, Any], req: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    """Return (hard failures, explanatory notes) for one offer."""
    failures: List[str] = []
    notes: List[str] = []
    name = offer.get("name", "Unnamed offer")

    if req.get("require_zero_foreign_transaction_fee") is True:
        fee = offer.get("foreign_transaction_fee_percent")
        condition = offer.get("foreign_transaction_fee_conditions")
        if not is_number(fee):
            failures.append("foreign transaction fee is not documented")
        elif fee != 0:
            failures.append("foreign transaction fee is not 0%")
        elif condition not in (None, ""):
            failures.append("0% foreign transaction fee is conditional: " + str(condition))
        else:
            notes.append("has an unconditional 0% foreign transaction fee")

    if req.get("require_purchase_protection") is True:
        days = offer.get("purchase_protection_days")
        claim_max = offer.get("purchase_protection_max_per_claim")
        if not is_number(days) or days <= 0:
            failures.append("purchase-protection duration is not documented")
        else:
            detail = f"purchase protection is documented for {days:g} days"
            if is_number(claim_max):
                detail += f" up to ${claim_max:,.2f} per claim"
            notes.append(detail)

    minimum_limit = req.get("minimum_possible_credit_limit")
    if minimum_limit is not None:
        if not is_number(minimum_limit) or minimum_limit < 0:
            failures.append("minimum_possible_credit_limit must be a nonnegative number")
        else:
            offered_max = offer.get("max_possible_credit_limit")
            if not is_number(offered_max):
                failures.append("maximum possible credit limit is not documented")
            elif offered_max < minimum_limit:
                failures.append(
                    f"published maximum possible limit (${offered_max:,.2f}) is below requested ${minimum_limit:,.2f}"
                )
            else:
                notes.append(
                    f"published maximum possible limit is ${offered_max:,.2f}, subject to approval"
                )

    focus = req.get("spending_focus")
    rewards = offer.get("rewards")
    if isinstance(focus, str) and focus.strip() and isinstance(rewards, dict):
        applies_to = rewards.get("applies_to", [])
        applies_lower = {str(item).lower() for item in applies_to} if isinstance(applies_to, list) else set()
        if focus.lower() in applies_lower or "all categories" in applies_lower or "all purchases" in applies_lower:
            rate = rewards.get("rate_percent")
            if is_number(rate):
                notes.append(f"rewards include {rate:g}% for {focus} spending")
            else:
                notes.append(f"rewards explicitly include {focus} spending")
        else:
            notes.append(f"rewards for {focus} spending are not explicitly established by supplied facts")

    if not isinstance(offer.get("name"), str) or not offer["name"].strip():
        failures.append(f"{name}: offer name is missing")
    return failures, notes


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"errors": [f"invalid JSON: {exc.msg}"]}))
        return
    if not isinstance(payload, dict):
        print(json.dumps({"errors": ["input must be a JSON object"]}))
        return

    errors = validate_request(payload)
    if errors:
        print(json.dumps({"errors": errors}))
        return

    req = payload["requirements"]
    full: List[Dict[str, Any]] = []
    partial: List[Dict[str, Any]] = []
    for offer in payload["offers"]:
        if not isinstance(offer, dict):
            partial.append({"name": "Unnamed offer", "failures": ["offer must be an object"], "notes": []})
            continue
        failures, notes = assess_offer(offer, req)
        result = {
            "name": offer.get("name", "Unnamed offer"),
            "sources": offer.get("sources", []),
            "notes": notes,
            "failures": failures,
        }
        if failures:
            partial.append(result)
        else:
            full.append(result)

    print(json.dumps({
        "fully_qualifying_offers": full,
        "conditional_or_partial_offers": partial,
        "errors": []
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
