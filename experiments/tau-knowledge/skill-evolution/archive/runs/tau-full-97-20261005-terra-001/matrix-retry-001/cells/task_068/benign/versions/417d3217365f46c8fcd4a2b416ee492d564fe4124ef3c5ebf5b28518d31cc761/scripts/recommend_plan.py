#!/usr/bin/env python3
"""Recommend documented account/card combinations without performing any action.

Input JSON:
{
  "deposit_amount": number,
  "requirements": {
    "early_direct_deposit_min_days": 0|1|2,
    "documented_travel_insurance": bool
  },
  "card_status": {"Silver Rewards Card": "held"|"pending_application"|"unavailable", ...}
}

Output JSON includes valid_input, eligible_recommendations, recommended, and errors.
A pending application is treated as conditional, never as an already active benefit.
"""
import json
import sys
from decimal import Decimal, InvalidOperation


def money(value):
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not parsed.is_finite() or parsed < 0:
        return None
    return parsed


def main(data):
    errors = []
    amount = money(data.get("deposit_amount"))
    req = data.get("requirements")
    if amount is None:
        errors.append("deposit_amount must be a non-negative numeric USD amount")
    if not isinstance(req, dict):
        errors.append("requirements must be an object")
        req = {}

    early_days = req.get("early_direct_deposit_min_days", 0)
    if not isinstance(early_days, int) or early_days < 0:
        errors.append("requirements.early_direct_deposit_min_days must be a non-negative integer")
    travel_required = req.get("documented_travel_insurance", False)
    if not isinstance(travel_required, bool):
        errors.append("requirements.documented_travel_insurance must be boolean")

    statuses = data.get("card_status", {})
    if not isinstance(statuses, dict):
        errors.append("card_status must be an object when supplied")
        statuses = {}

    output = {
        "valid_input": not errors,
        "errors": errors,
        "eligible_recommendations": [],
        "recommended": None,
        "policy_notes": [
            "At most one qualifying checking boost and one qualifying card bonus may apply.",
            "A card marked pending_application is approval-contingent and is not currently active.",
            "Documented travel insurance requires more than card ownership; applicable travel must be charged in full to the covered card and policy terms apply."
        ]
    }
    if errors:
        return output

    # Documented candidates for this upgrade scenario. Gold's $10,000 ongoing
    # minimum makes it viable only at or above that balance.
    candidates = [
        {
            "checking_account": "Green Account (checking)",
            "savings_account": "Gold Account",
            "card": None,
            "base_apy": Decimal("5.5"),
            "checking_bonus": Decimal("0.75"),
            "card_bonus": Decimal("0"),
            "early_direct_deposit_days": 1,
            "documented_travel_insurance": False,
            "minimum_balance": Decimal("10000"),
            "conditions": []
        },
        {
            "checking_account": "Green Account (checking)",
            "savings_account": "Gold Account",
            "card": "Silver Rewards Card",
            "base_apy": Decimal("5.5"),
            "checking_bonus": Decimal("0.75"),
            "card_bonus": Decimal("0.2"),
            "early_direct_deposit_days": 1,
            "documented_travel_insurance": True,
            "minimum_balance": Decimal("10000"),
            "conditions": ["Silver Rewards Card approval and active ownership are required for the card bonus."]
        },
        {
            "checking_account": "Green Account (checking)",
            "savings_account": "Gold Account",
            "card": "EcoCard",
            "base_apy": Decimal("5.5"),
            "checking_bonus": Decimal("0.75"),
            "card_bonus": Decimal("0.6"),
            "early_direct_deposit_days": 1,
            "documented_travel_insurance": False,
            "minimum_balance": Decimal("10000"),
            "conditions": ["EcoCard approval and active ownership are required for the card bonus.", "No EcoCard travel-insurance benefit is documented in the supplied materials."]
        }
    ]

    for candidate in candidates:
        reasons = []
        if amount < candidate["minimum_balance"]:
            reasons.append("deposit amount is below the documented Gold Account ongoing minimum balance")
        if candidate["early_direct_deposit_days"] < early_days:
            reasons.append("does not meet requested early-direct-deposit timing")
        if travel_required and not candidate["documented_travel_insurance"]:
            reasons.append("does not have documented travel insurance")

        card_state = "not_applicable"
        if candidate["card"]:
            card_state = statuses.get(candidate["card"], "pending_application")
            if card_state not in {"held", "pending_application"}:
                reasons.append("required card is unavailable or not approved")

        if not reasons:
            apy = candidate["base_apy"] + candidate["checking_bonus"] + candidate["card_bonus"]
            output["eligible_recommendations"].append({
                "checking_account": candidate["checking_account"],
                "savings_account": candidate["savings_account"],
                "card": candidate["card"],
                "effective_documented_apy_percent": float(apy),
                "early_direct_deposit_days": candidate["early_direct_deposit_days"],
                "documented_travel_insurance": candidate["documented_travel_insurance"],
                "card_status": card_state,
                "conditional": card_state == "pending_application",
                "conditions": candidate["conditions"],
                "minimum_balance": float(candidate["minimum_balance"])
            })

    if output["eligible_recommendations"]:
        output["eligible_recommendations"].sort(
            key=lambda item: item["effective_documented_apy_percent"], reverse=True
        )
        output["recommended"] = output["eligible_recommendations"][0]
    else:
        output["no_supported_match"] = True
        output["next_step"] = "Explain which documented requirement prevents a match; do not promise an undocumented card benefit."
    return output


if __name__ == "__main__":
    try:
        supplied = json.load(sys.stdin)
        if not isinstance(supplied, dict):
            raise ValueError("top-level JSON must be an object")
        result = main(supplied)
    except Exception as exc:
        result = {"valid_input": False, "errors": [str(exc)], "eligible_recommendations": [], "recommended": None}
    print(json.dumps(result, sort_keys=True))
