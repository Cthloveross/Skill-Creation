#!/usr/bin/env python3
"""Rank caller-supplied everyday card records by cash-back rate.

Reads JSON from stdin and writes JSON to stdout. Exit code 2 denotes invalid input.
"""
import json
import sys
from typing import Any, Dict, List


def fail(message: str) -> None:
    print(json.dumps({"error": message}))
    raise SystemExit(2)


def number(value: Any, field: str, index: int) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        fail("cards[%d].%s must be a number" % (index, field))
    return float(value)


def normalize(card: Dict[str, Any], index: int) -> Dict[str, Any]:
    if not isinstance(card, dict):
        fail("cards[%d] must be an object" % index)
    name = card.get("name")
    if not isinstance(name, str) or not name.strip():
        fail("cards[%d].name must be a nonempty string" % index)
    rate = number(card.get("cash_back_rate_percent"), "cash_back_rate_percent", index)
    fee = number(card.get("annual_fee"), "annual_fee", index)
    if rate < 0 or fee < 0:
        fail("cards[%d] rates and fees must not be negative" % index)
    personal = card.get("is_personal", True)
    everyday = card.get("everyday_rate", True)
    if not isinstance(personal, bool) or not isinstance(everyday, bool):
        fail("cards[%d] is_personal and everyday_rate must be booleans" % index)
    requirements = card.get("requirements", [])
    if not isinstance(requirements, list) or not all(isinstance(x, str) for x in requirements):
        fail("cards[%d].requirements must be an array of strings" % index)
    cost = card.get("recurring_non_card_cost_monthly", 0)
    cost = number(cost, "recurring_non_card_cost_monthly", index)
    if cost < 0:
        fail("cards[%d].recurring_non_card_cost_monthly must not be negative" % index)
    return {
        "name": name,
        "cash_back_rate_percent": rate,
        "annual_fee": fee,
        "is_personal": personal,
        "everyday_rate": everyday,
        "requirements": requirements,
        "recurring_non_card_cost_monthly": cost,
    }


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        fail("stdin must contain one JSON object: " + str(exc))
    if not isinstance(payload, dict) or not isinstance(payload.get("cards"), list):
        fail("input must be an object with a cards array")
    if not payload["cards"]:
        fail("cards must not be empty")
    zero_fee = payload.get("require_zero_annual_fee", True)
    if not isinstance(zero_fee, bool):
        fail("require_zero_annual_fee must be boolean")

    cards = [normalize(card, i) for i, card in enumerate(payload["cards"])]
    warnings: List[str] = []
    eligible = [c for c in cards if c["is_personal"] and c["everyday_rate"]]
    if zero_fee:
        eligible = [c for c in eligible if c["annual_fee"] == 0]
    eligible.sort(key=lambda c: (-c["cash_back_rate_percent"], c["name"].casefold()))
    for card in eligible:
        if card["recurring_non_card_cost_monthly"] > 0:
            warnings.append(
                "%s has a separate recurring non-card cost of $%.2f/month."
                % (card["name"], card["recurring_non_card_cost_monthly"])
            )
        if card["requirements"]:
            warnings.append("%s has requirements that must be confirmed." % card["name"])
    if not eligible:
        warnings.append("No supplied personal card meets the selected constraints.")
    print(json.dumps({"recommended": eligible[0] if eligible else None,
                      "qualifying_cards": eligible,
                      "warnings": warnings}, sort_keys=True))


if __name__ == "__main__":
    main()
