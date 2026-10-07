#!/usr/bin/env python3
"""Compare documented savings APY components without performing account actions.

stdin JSON:
{
  "deposit_amount": number|string,
  "checking_classes": ["official checking class", ...],
  "active_credit_cards": ["official card name", ...]
}

stdout JSON contains candidates with numeric components only where their source
rates/boosts are documented in this Skill's evidence.  A result is advisory:
it does not establish account/card approval, eligibility, direct-deposit status,
or authorization.  Credit-card and checking boosts independently use only their
highest applicable values.
"""
import json
import sys
from decimal import Decimal, InvalidOperation

D = Decimal
# Base rate, opening minimum, continuing minimum. None is deliberately not
# modeled rather than guessed from a product name.
PRODUCTS = {
    "Green Account (savings)": (D("4.0"), D("100"), D("500")),
    "Silver Plus Account": (D("3.0"), D("1000"), D("2500")),  # 4.5% tier 2 at >= $15,000
    "Gold Account": (D("5.5"), D("5000"), D("10000")),
    "Gold Plus Account": (D("6.0"), D("10000"), D("25000")),
    "Platinum Account": (D("6.5"), D("25000"), D("50000")),
    "Platinum Plus Account": (D("7.0"), D("50000"), D("100000")),
    "Diamond Elite Account": (D("7.5"), D("100000"), D("250000")),
}
# Only exact numeric boost amounts stated in the evidence are represented.
CHECKING_BOOSTS = {
    ("Green Fee-Free Account", "Bronze Account"): D("0.4"),
    ("Green Fee-Free Account", "Gold Plus Account"): D("0.35"),
    ("Evergreen Account", "Green Account (savings)"): D("0.55"),
    ("Evergreen Account", "Diamond Elite Account"): D("0.15"),
    ("Blue Account", "Silver Plus Account"): D("0.35"),
    ("Blue Account", "Platinum Account"): D("0.8"),
    ("Light Green Account", "Diamond Elite Account"): D("0.2"),
    ("Light Green Account", "Platinum Account"): D("0.65"),
    ("Bluest Account", "Silver Account"): D("0.45"),
    ("Bluest Account", "Bronze Account"): D("0.7"),
    ("Purple Account", "Platinum Plus Account"): D("0.3"),
    ("Purple Account", "Gold Account"): D("0.1"),
    ("Gold Years Account", "Gold Plus Account"): D("0.5"),
    ("Gold Years Account", "Silver Account"): D("0.6"),
}
CARD_BONUSES = {
    "Green Account (savings)": {
        "Bronze Rewards Card": "0", "Silver Rewards Card": ".45",
        "Gold Rewards Card": "0", "Platinum Rewards Card": ".35",
        "Diamond Elite Card": ".6", "EcoCard": ".5",
        "Green Rewards Card": ".4", "Crypto-Cash Back Card": "0",
    },
    "Silver Plus Account": {
        "Bronze Rewards Card": ".15", "Silver Rewards Card": ".15",
        "Gold Rewards Card": ".2", "Platinum Rewards Card": ".15",
        "Diamond Elite Card": ".4", "EcoCard": ".45",
        "Green Rewards Card": ".1", "Crypto-Cash Back Card": "0",
    },
    "Gold Account": {
        "Bronze Rewards Card": ".15", "Silver Rewards Card": ".2",
        "Gold Rewards Card": ".025", "Platinum Rewards Card": ".15",
        "Diamond Elite Card": ".3", "EcoCard": ".6",
        "Green Rewards Card": ".35", "Crypto-Cash Back Card": "0",
    },
    "Gold Plus Account": {
        "Bronze Rewards Card": ".15", "Silver Rewards Card": ".1",
        "Gold Rewards Card": ".35", "Platinum Rewards Card": ".2",
        "Diamond Elite Card": ".25", "EcoCard": ".1",
        "Green Rewards Card": ".05", "Crypto-Cash Back Card": ".3",
    },
    "Platinum Account": {
        "Bronze Rewards Card": "0", "Silver Rewards Card": "0",
        "Gold Rewards Card": ".15", "Platinum Rewards Card": ".25",
        "Diamond Elite Card": ".35", "EcoCard": "0",
        "Green Rewards Card": "0", "Crypto-Cash Back Card": "0",
    },
    "Platinum Plus Account": {
        "Bronze Rewards Card": "0", "Silver Rewards Card": "0",
        "Gold Rewards Card": ".1", "Platinum Rewards Card": ".4",
        "Diamond Elite Card": ".6", "EcoCard": ".05",
        "Green Rewards Card": "0", "Crypto-Cash Back Card": ".25",
    },
    "Diamond Elite Account": {
        "Bronze Rewards Card": "0", "Silver Rewards Card": "0",
        "Gold Rewards Card": "0", "Platinum Rewards Card": ".1",
        "Diamond Elite Card": ".5", "EcoCard": "0",
        "Green Rewards Card": "0", "Crypto-Cash Back Card": ".15",
    },
}


def amount(value):
    if value is None or isinstance(value, bool):
        raise ValueError("deposit_amount must be a valid non-negative USD amount")
    try:
        parsed = D(str(value).replace("$", "").replace(",", "").strip())
    except (InvalidOperation, ValueError):
        raise ValueError("deposit_amount must be a valid non-negative USD amount")
    if parsed < 0:
        raise ValueError("deposit_amount must be non-negative")
    return parsed


def as_text(value):
    return format(value, "f")


def candidate(product, data_amount, checking, cards):
    base, opening, ongoing = PRODUCTS[product]
    # Silver Plus has a documented two-tier rate, so derive its base rate from
    # the stated balance rather than always presenting its higher tier.
    tier = None
    if product == "Silver Plus Account":
        if data_amount >= D("15000"):
            base, tier = D("4.5"), "tier_2_at_or_above_15000"
        else:
            tier = "tier_1_below_15000"
    check_matches = [
        (klass, boost) for (klass, savings), boost in CHECKING_BOOSTS.items()
        if savings == product and klass in checking
    ]
    card_matches = [
        (card, D(boost)) for card, boost in CARD_BONUSES[product].items() if card in cards
    ]
    check_boost = max((boost for _, boost in check_matches), default=D("0"))
    card_boost = max((boost for _, boost in card_matches), default=D("0"))
    return {
        "account_class": product,
        "base_apy_percent": as_text(base),
        "rate_tier": tier,
        "highest_documented_checking_boost_percent": as_text(check_boost),
        "highest_documented_card_boost_percent": as_text(card_boost),
        "effective_documented_apy_percent": as_text(base + check_boost + card_boost),
        "matching_checking_boosts": [
            {"checking_class": klass, "apy_boost_percent": as_text(boost)}
            for klass, boost in sorted(check_matches)
        ],
        "matching_card_bonuses": [
            {"card": card, "apy_bonus_percent": as_text(boost)}
            for card, boost in sorted(card_matches)
        ],
        "opening_deposit_minimum_usd": as_text(opening),
        "ongoing_minimum_balance_usd": as_text(ongoing),
        "deposit_meets_opening_minimum": data_amount >= opening,
        "deposit_meets_ongoing_minimum": data_amount >= ongoing,
        "sustainable_at_stated_balance": data_amount >= opening and data_amount >= ongoing,
    }


def main(data):
    if not isinstance(data, dict):
        raise ValueError("input must be a JSON object")
    deposit = amount(data.get("deposit_amount"))
    checking = {x for x in data.get("checking_classes", []) if isinstance(x, str)}
    cards = {x for x in data.get("active_credit_cards", []) if isinstance(x, str)}
    output = [candidate(product, deposit, checking, cards) for product in PRODUCTS]
    output.sort(key=lambda row: D(row["effective_documented_apy_percent"]), reverse=True)
    sustainable = [row for row in output if row["sustainable_at_stated_balance"]]
    best_sustainable = None
    if sustainable:
        best_rate = max(D(row["effective_documented_apy_percent"]) for row in sustainable)
        best_sustainable = {
            "effective_documented_apy_percent": as_text(best_rate),
            "account_classes": [
                row["account_class"] for row in sustainable
                if D(row["effective_documented_apy_percent"]) == best_rate
            ],
        }
    return {
        "deposit_amount_usd": as_text(deposit),
        "candidates": output,
        "highest_documented_sustainable_candidate": best_sustainable,
        "limitations": [
            "Results include only products with documented base APY and balance data.",
            "Only exact, numeric documented boost amounts are included; a qualifying pairing with no stated amount is not treated as zero.",
            "Only active cards supplied as input are included. Card bonuses do not stack; checking boosts do not stack.",
            "The sustainable-candidate field tests only documented opening and ongoing balance thresholds; it does not prove eligibility, product selection, account/card approval, or funding authorization.",
        ],
    }


if __name__ == "__main__":
    try:
        print(json.dumps(main(json.load(sys.stdin)), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        sys.exit(2)
