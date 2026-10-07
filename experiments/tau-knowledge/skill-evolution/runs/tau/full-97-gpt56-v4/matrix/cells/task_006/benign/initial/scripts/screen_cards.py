#!/usr/bin/env python3
"""Screen a card catalog against explicit customer constraints.
Reads one JSON object from stdin and writes one JSON object to stdout.
"""
import json
import sys
from pathlib import Path


REQUIRED_CRITERIA = (
    "max_foreign_transaction_fee_percent",
    "max_minimum_payment_percent",
    "require_virtual_card_management",
)


def load_default_cards():
    catalog = Path(__file__).resolve().parents[1] / "references" / "card_catalog.json"
    with catalog.open("r", encoding="utf-8") as handle:
        return json.load(handle)["cards"]


def fee_for_customer(card, has_premium_subscription):
    if "foreign_transaction_fee_percent" in card:
        return card["foreign_transaction_fee_percent"]
    options = card.get("foreign_transaction_fee_by_subscription")
    if not isinstance(options, dict):
        return None
    key = "with_premium" if has_premium_subscription else "without_premium"
    return options.get(key)


def main(payload):
    if not isinstance(payload, dict):
        return {"error": "Input must be a JSON object."}
    customer = payload.get("customer")
    criteria = payload.get("criteria")
    if not isinstance(customer, dict) or not isinstance(criteria, dict):
        return {"error": "customer and criteria must both be objects."}

    missing = [key for key in REQUIRED_CRITERIA if key not in criteria]
    if missing:
        return {"error": "Missing required criteria: " + ", ".join(missing)}
    try:
        score = float(customer["credit_score"])
        max_foreign_fee = float(criteria["max_foreign_transaction_fee_percent"])
        max_min_payment = float(criteria["max_minimum_payment_percent"])
    except (KeyError, TypeError, ValueError):
        return {"error": "customer.credit_score and both numeric fee/payment criteria must be numbers."}
    if not isinstance(criteria["require_virtual_card_management"], bool):
        return {"error": "criteria.require_virtual_card_management must be boolean."}

    cards = payload.get("cards")
    if cards is None:
        try:
            cards = load_default_cards()
        except (OSError, ValueError, KeyError) as exc:
            return {"error": "Could not load packaged card catalog: " + str(exc)}
    if not isinstance(cards, list):
        return {"error": "cards must be an array when supplied."}

    premium = bool(customer.get("has_premium_subscription", False))
    eligible, rejected, indeterminate = [], [], []
    for card in cards:
        if not isinstance(card, dict) or not card.get("name"):
            indeterminate.append({"name": "unnamed card", "reasons": ["invalid card record"]})
            continue
        reasons, unknown = [], []
        minimum_score = card.get("minimum_credit_score")
        if minimum_score is None:
            unknown.append("minimum credit-score requirement is not documented")
        elif score < float(minimum_score):
            reasons.append("credit score is below the documented minimum of {}".format(minimum_score))

        foreign_fee = fee_for_customer(card, premium)
        if foreign_fee is None:
            unknown.append("applicable foreign transaction fee is not documented")
        elif float(foreign_fee) > max_foreign_fee:
            reasons.append("foreign transaction fee of {}% exceeds {}%".format(foreign_fee, max_foreign_fee))

        minimum_payment = card.get("minimum_payment_percent")
        if minimum_payment is None:
            unknown.append("minimum payment percentage is not documented")
        elif float(minimum_payment) > max_min_payment:
            reasons.append("minimum payment of {}% exceeds {}%".format(minimum_payment, max_min_payment))

        virtual = card.get("virtual_card_management")
        if virtual is None:
            unknown.append("virtual card availability is not documented")
        elif criteria["require_virtual_card_management"] and virtual is not True:
            reasons.append("virtual card management is not available")

        summary = {
            "name": card["name"],
            "minimum_credit_score": minimum_score,
            "foreign_transaction_fee_percent": foreign_fee,
            "minimum_payment_percent": minimum_payment,
            "virtual_card_management": virtual,
        }
        if unknown:
            summary["reasons"] = unknown
            indeterminate.append(summary)
        elif reasons:
            summary["reasons"] = reasons
            rejected.append(summary)
        else:
            eligible.append(summary)

    return {
        "eligible": eligible,
        "rejected": rejected,
        "indeterminate": indeterminate,
        "criteria_used": {
            "credit_score": score,
            "has_premium_subscription": premium,
            **{key: criteria[key] for key in REQUIRED_CRITERIA},
        },
    }


if __name__ == "__main__":
    try:
        raw = json.load(sys.stdin)
        result = main(raw)
    except json.JSONDecodeError:
        result = {"error": "stdin must contain valid JSON."}
    except Exception as exc:  # Keep the executable interface JSON-only.
        result = {"error": "Unexpected screening error: " + str(exc)}
    print(json.dumps(result, sort_keys=True))
