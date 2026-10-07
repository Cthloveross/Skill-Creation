#!/usr/bin/env python3
"""Compare documented savings APY candidates without performing account actions.

Input JSON schema:
{
  "deposit_amount": number|string,
  "checking_classes": ["full official checking class", ...],
  "active_credit_cards": ["card name", ...]
}

Output JSON lists modeled candidates. effective_apy_percent is base APY plus the
single highest applicable active-card bonus and the single highest documented
matching checking boost. It does not include unconfirmed relationship, direct-
deposit, or tier bonuses. A candidate meeting an opening deposit does not imply
that its ongoing balance condition is met or that the customer is eligible to
open it.
"""
import json
import sys
from decimal import Decimal, InvalidOperation

BASE = {
    "Gold Account": (Decimal("5.5"), Decimal("5000"), Decimal("10000")),
    "Gold Plus Account": (Decimal("6.0"), Decimal("10000"), Decimal("25000")),
    "Platinum Account": (Decimal("6.5"), Decimal("25000"), Decimal("50000")),
    "Platinum Plus Account": (Decimal("7.0"), Decimal("50000"), Decimal("100000")),
    "Diamond Elite Account": (Decimal("7.5"), Decimal("100000"), Decimal("250000")),
}
PAIR_BOOSTS = {
    ("Green Account (checking)", "Gold Account"): Decimal("0"),
    ("Green Fee-Free Account", "Gold Plus Account"): Decimal("0.35"),
    ("Blue Account", "Platinum Account"): Decimal("0.8"),
    ("Purple Account", "Platinum Plus Account"): Decimal("0.3"),
    ("Light Green Account", "Diamond Elite Account"): Decimal("0.2"),
}
CARD_BONUSES = {
    "Gold Account": {"Bronze Rewards Card": ".15", "Silver Rewards Card": ".2", "Gold Rewards Card": ".025", "Platinum Rewards Card": ".15", "Diamond Elite Card": ".3", "EcoCard": ".6", "Green Rewards Card": ".35", "Crypto-Cash Back Card": "0"},
    "Gold Plus Account": {"Bronze Rewards Card": ".15", "Silver Rewards Card": ".1", "Gold Rewards Card": ".35", "Platinum Rewards Card": ".2", "Diamond Elite Card": ".25", "EcoCard": ".1", "Green Rewards Card": ".05", "Crypto-Cash Back Card": ".3"},
    "Platinum Account": {"Bronze Rewards Card": "0", "Silver Rewards Card": "0", "Gold Rewards Card": ".15", "Platinum Rewards Card": ".25", "Diamond Elite Card": ".35", "EcoCard": "0", "Green Rewards Card": "0", "Crypto-Cash Back Card": "0"},
    "Platinum Plus Account": {"Bronze Rewards Card": "0", "Silver Rewards Card": "0", "Gold Rewards Card": ".1", "Platinum Rewards Card": ".4", "Diamond Elite Card": ".6", "EcoCard": ".05", "Green Rewards Card": "0", "Crypto-Cash Back Card": ".25"},
    "Diamond Elite Account": {"Bronze Rewards Card": "0", "Silver Rewards Card": "0", "Gold Rewards Card": "0", "Platinum Rewards Card": ".1", "Diamond Elite Card": ".5", "EcoCard": "0", "Green Rewards Card": "0", "Crypto-Cash Back Card": ".15"},
}


def as_money(v):
    try:
        return Decimal(str(v).replace("$", "").replace(",", "").strip())
    except (InvalidOperation, ValueError, AttributeError):
        raise ValueError("deposit_amount must be a valid USD amount")


def main(data):
    amount = as_money(data.get("deposit_amount"))
    checking = set(data.get("checking_classes") or [])
    cards = set(data.get("active_credit_cards") or [])
    candidates = []
    for product, (base, opening, ongoing) in BASE.items():
        boosts = [value for (check, saving), value in PAIR_BOOSTS.items() if saving == product and check in checking]
        check_boost = max(boosts) if boosts else Decimal("0")
        card_values = [Decimal(value) for card, value in CARD_BONUSES[product].items() if card in cards]
        card_boost = max(card_values) if card_values else Decimal("0")
        candidates.append({
            "account_class": product,
            "base_apy_percent": str(base),
            "highest_documented_checking_boost_percent": str(check_boost),
            "highest_documented_card_boost_percent": str(card_boost),
            "effective_apy_percent": str(base + check_boost + card_boost),
            "opening_deposit_minimum_usd": str(opening),
            "ongoing_minimum_balance_usd": str(ongoing),
            "deposit_meets_opening_minimum": amount >= opening,
            "deposit_meets_ongoing_minimum": amount >= ongoing,
        })
    candidates.sort(key=lambda x: Decimal(x["effective_apy_percent"]), reverse=True)
    return {"deposit_amount_usd": str(amount), "candidates": candidates, "limitations": ["Only documented products and bonuses modeled by this helper are included.", "Only the highest credit-card bonus and highest matching checking boost are used; card bonuses do not stack.", "Eligibility, account status, customer selection, and funding authorization must be validated separately."]}


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        print(json.dumps(main(payload), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
