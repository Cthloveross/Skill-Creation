#!/usr/bin/env python3
"""Rank explicitly supplied savings/checking/card APY combinations.

The caller supplies documented candidate data; this script does not contain a product
catalog or determine whether a customer is approved, linked, or in good standing.
"""
import json
import sys
from decimal import Decimal, InvalidOperation


def money_or_rate(value, field):
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be a decimal-compatible value")


def main(payload):
    amount = money_or_rate(payload.get("amount"), "amount")
    if amount < 0:
        raise ValueError("amount must not be negative")
    require_insurance = payload.get("require_travel_insurance") is True
    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        raise ValueError("candidates must be a list")

    eligible = []
    excluded = []
    required = {
        "name", "base_apy", "minimum_balance", "checking_boost",
        "card_bonus", "card_has_travel_insurance"
    }
    for candidate in candidates:
        if not isinstance(candidate, dict):
            excluded.append({"name": None, "reasons": ["candidate is not an object"]})
            continue
        missing = sorted(required - set(candidate))
        name = candidate.get("name")
        if missing:
            excluded.append({"name": name, "reasons": ["missing fields: " + ", ".join(missing)]})
            continue
        try:
            minimum = money_or_rate(candidate["minimum_balance"], "minimum_balance")
            base = money_or_rate(candidate["base_apy"], "base_apy")
            checking = money_or_rate(candidate["checking_boost"], "checking_boost")
            card = money_or_rate(candidate["card_bonus"], "card_bonus")
        except ValueError as exc:
            excluded.append({"name": name, "reasons": [str(exc)]})
            continue
        reasons = []
        if amount < minimum:
            reasons.append("intended balance is below the supplied minimum balance")
        if require_insurance and candidate["card_has_travel_insurance"] is not True:
            reasons.append("candidate lacks documented required travel insurance")
        if reasons:
            excluded.append({"name": name, "reasons": reasons})
            continue
        total = base + checking + card
        eligible.append({
            "name": name,
            "effective_apy": str(total),
            "components": {
                "base_apy": str(base),
                "checking_boost": str(checking),
                "card_bonus": str(card),
            },
            "assumptions": [
                "supplied minimum balance is met",
                "supplied checking boost is the single highest applicable boost",
                "supplied card bonus is the single highest applicable card bonus",
                "linkage, account status, and card eligibility require independent verification",
            ],
        })

    eligible.sort(key=lambda item: (Decimal(item["effective_apy"]), item["name"]), reverse=True)
    return {
        "amount": str(amount),
        "require_travel_insurance": require_insurance,
        "best": eligible[0] if eligible else None,
        "eligible": eligible,
        "excluded": excluded,
    }


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(1)
