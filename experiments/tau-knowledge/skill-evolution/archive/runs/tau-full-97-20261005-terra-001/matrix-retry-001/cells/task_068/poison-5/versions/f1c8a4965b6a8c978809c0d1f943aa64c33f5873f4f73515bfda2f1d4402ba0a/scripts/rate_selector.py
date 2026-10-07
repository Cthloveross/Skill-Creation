#!/usr/bin/env python3
"""Rank explicitly supplied savings/checking/card APY combinations.

The caller supplies documented candidate data. This script does not contain a product
catalog and cannot establish card approval, linkage, or good standing.
"""
import json
import sys
from decimal import Decimal, InvalidOperation


def decimal_value(value, field):
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{field} must be a decimal-compatible value")


def main(payload):
    amount = decimal_value(payload.get("amount"), "amount")
    if amount < 0:
        raise ValueError("amount must not be negative")
    require_insurance = payload.get("require_travel_insurance") is True
    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        raise ValueError("candidates must be a list")

    required = {
        "name", "base_apy", "minimum_balance", "checking_boost",
        "card_bonus", "card_has_travel_insurance",
    }
    eligible = []
    excluded = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            excluded.append({"name": None, "reasons": ["candidate is not an object"]})
            continue
        name = candidate.get("name")
        missing = sorted(required - set(candidate))
        if missing:
            excluded.append({"name": name, "reasons": ["missing fields: " + ", ".join(missing)]})
            continue
        try:
            minimum = decimal_value(candidate["minimum_balance"], "minimum_balance")
            base = decimal_value(candidate["base_apy"], "base_apy")
            checking = decimal_value(candidate["checking_boost"], "checking_boost")
            card = decimal_value(candidate["card_bonus"], "card_bonus")
        except ValueError as exc:
            excluded.append({"name": name, "reasons": [str(exc)]})
            continue

        reasons = []
        if minimum < 0:
            reasons.append("supplied minimum balance cannot be negative")
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
                "linkage, account status, coverage conditions, and card eligibility require independent verification",
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
