#!/usr/bin/env python3
"""Filter card records against explicit hard requirements.

Reads one JSON object from stdin and writes one JSON object to stdout. See SKILL.md
for the schema. The program performs no network, account, or banking operations.
"""
import json
import re
import sys
from decimal import Decimal, InvalidOperation


def number(value):
    """Return Decimal from a numeric value or the first numeric token in a string."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float, Decimal)):
        try:
            return Decimal(str(value))
        except InvalidOperation:
            return None
    if isinstance(value, str):
        match = re.search(r"[-+]?\d[\d,]*(?:\.\d+)?", value)
        if match:
            try:
                return Decimal(match.group(0).replace(",", ""))
            except InvalidOperation:
                return None
    return None


def bool_value(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"yes", "true", "available"}:
            return True
        if lowered in {"no", "false", "unavailable"}:
            return False
    return None


def add_check(failures, unknowns, condition, unknown, label):
    if unknown:
        unknowns.append(label)
    elif not condition:
        failures.append(label)


def evaluate(card, req):
    failures, unknowns = [], []

    if "credit_score" in req:
        customer_score = number(req.get("credit_score"))
        card_minimum = number(card.get("minimum_credit_score"))
        if customer_score is None or card_minimum is None:
            unknowns.append("credit_score_eligibility")
        elif customer_score < card_minimum:
            failures.append("credit_score_below_minimum")

    if "foreign_transaction_fee_max" in req:
        maximum = number(req.get("foreign_transaction_fee_max"))
        fee = number(card.get("foreign_transaction_fee"))
        if maximum is None or fee is None:
            unknowns.append("foreign_transaction_fee")
        elif fee > maximum:
            failures.append("foreign_transaction_fee_exceeds_max")

    if "minimum_payment_pct_max" in req:
        maximum = number(req.get("minimum_payment_pct_max"))
        payment = number(card.get("minimum_payment_pct"))
        if maximum is None or payment is None:
            unknowns.append("minimum_payment_pct")
        elif payment > maximum:
            failures.append("minimum_payment_pct_exceeds_max")

    if req.get("virtual_card_required") is True:
        available = bool_value(card.get("virtual_card_management"))
        add_check(failures, unknowns, available is True, available is None,
                  "virtual_card_management")
    elif req.get("virtual_card_required") is False:
        available = bool_value(card.get("virtual_card_management"))
        add_check(failures, unknowns, available is False, available is None,
                  "virtual_card_management")

    required_subs = req.get("required_subscriptions", {})
    if required_subs is not None and not isinstance(required_subs, dict):
        unknowns.append("required_subscriptions_invalid")
    elif isinstance(required_subs, dict):
        card_subs = card.get("required_subscriptions", {})
        if not isinstance(card_subs, dict):
            card_subs = {}
        for subscription, required_value in required_subs.items():
            has_value = bool_value(card_subs.get(subscription))
            wanted = bool_value(required_value)
            label = "subscription:" + str(subscription)
            if wanted is None or has_value is None:
                unknowns.append(label)
            elif has_value != wanted:
                failures.append(label)

    return failures, unknowns


def public_card(card):
    fields = (
        "name", "minimum_credit_score", "foreign_transaction_fee",
        "minimum_payment_pct", "virtual_card_management",
        "required_subscriptions", "source"
    )
    return {field: card[field] for field in fields if field in card}


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": "invalid_json", "detail": str(exc)}))
        return 2

    if not isinstance(data, dict) or not isinstance(data.get("requirements", {}), dict):
        print(json.dumps({"error": "requirements_must_be_an_object"}))
        return 2
    cards = data.get("cards")
    if not isinstance(cards, list):
        print(json.dumps({"error": "cards_must_be_a_list"}))
        return 2

    matches, nonmatches, unknown = [], [], []
    for index, card in enumerate(cards):
        if not isinstance(card, dict) or not isinstance(card.get("name"), str) or not card["name"].strip():
            unknown.append({"index": index, "unknown": ["valid_card_name"]})
            continue
        failures, unknowns = evaluate(card, data.get("requirements", {}))
        item = public_card(card)
        if failures:
            item["failures"] = failures
            if unknowns:
                item["unknown"] = unknowns
            nonmatches.append(item)
        elif unknowns:
            item["unknown"] = unknowns
            unknown.append(item)
        else:
            matches.append(item)

    print(json.dumps({
        "matches": matches,
        "nonmatches": nonmatches,
        "unknown": unknown,
        "match_count": len(matches)
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
