#!/usr/bin/env python3
"""Select the highest supported flat everyday cash-back card from JSON stdin."""

import json
import sys
from typing import Any, Dict, List

REQUIRED_FIELDS = (
    "name",
    "flat_cash_back_rate",
    "applies_to_all_eligible_purchases",
    "invitation_only",
    "application_available",
)


def invalid(errors: List[str]) -> Dict[str, Any]:
    return {"status": "invalid_input", "errors": errors}


def validate_card(card: Any, index: int) -> List[str]:
    prefix = f"cards[{index}]"
    if not isinstance(card, dict):
        return [f"{prefix} must be an object"]
    errors = []
    for field in REQUIRED_FIELDS:
        if field not in card:
            errors.append(f"{prefix}.{field} is required")
    if "name" in card and (not isinstance(card["name"], str) or not card["name"].strip()):
        errors.append(f"{prefix}.name must be a nonempty string")
    if "flat_cash_back_rate" in card:
        rate = card["flat_cash_back_rate"]
        if isinstance(rate, bool) or not isinstance(rate, (int, float)) or rate < 0:
            errors.append(f"{prefix}.flat_cash_back_rate must be a nonnegative number")
    for field in ("applies_to_all_eligible_purchases", "invitation_only", "application_available"):
        if field in card and not isinstance(card[field], bool):
            errors.append(f"{prefix}.{field} must be boolean")
    if "eligible_for_customer" in card and card["eligible_for_customer"] not in (True, False, None):
        errors.append(f"{prefix}.eligible_for_customer must be true, false, or null")
    return errors


def select(cards: List[Dict[str, Any]]) -> Dict[str, Any]:
    candidates = [
        card for card in cards
        if card["applies_to_all_eligible_purchases"]
        and not card["invitation_only"]
        and card["application_available"]
        and card.get("eligible_for_customer") is not False
    ]
    if not candidates:
        return {
            "status": "no_recommendation",
            "reason": "no_application_available_non_invitation_flat_everyday_candidate",
        }

    # Stable tie behavior preserves supplied ordering, so callers can resolve ties explicitly.
    winner = max(candidates, key=lambda card: card["flat_cash_back_rate"])
    qualification = (
        "appears_eligible" if winner.get("eligible_for_customer") is True else "unknown"
    )
    return {
        "status": "ok",
        "recommended_card": winner,
        "selection_basis": (
            "highest flat cash-back rate on all eligible purchases among "
            "application-available, non-invitation-only cards"
        ),
        "qualification_status": qualification,
    }


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps(invalid([f"stdin is not valid JSON: {exc.msg}"])))
        return

    if not isinstance(payload, dict):
        print(json.dumps(invalid(["top-level input must be an object"])))
        return
    cards = payload.get("cards")
    if not isinstance(cards, list):
        print(json.dumps(invalid(["cards must be an array"])))
        return

    errors: List[str] = []
    for index, card in enumerate(cards):
        errors.extend(validate_card(card, index))
    if errors:
        print(json.dumps(invalid(errors)))
        return

    print(json.dumps(select(cards), ensure_ascii=False))


if __name__ == "__main__":
    main()
