#!/usr/bin/env python3
"""Calculate documented Gold savings APY components.

Reads one JSON object from stdin and writes one JSON object to stdout.
Input:
{
  "savings_class": "Gold Account",
  "checking_accounts": [{"account_class": str, "status": str}],
  "credit_cards": [{"card_type": str, "account_status": str}]
}
Only documented mappings are calculated; unknown possibly qualifying checkings are
reported for human documentation review rather than assigned an invented rate.
"""
import json
import sys

CARD_BONUSES = {
    "Bronze Rewards Card": 0.15,
    "Silver Rewards Card": 0.2,
    "Gold Rewards Card": 0.025,
    "Platinum Rewards Card": 0.15,
    "Diamond Elite Card": 0.3,
    "EcoCard": 0.6,
    "Green Rewards Card": 0.35,
    "Crypto-Cash Back Card": 0.0,
}
# Exact rates documented in the packaged evidence for Gold savings.
GOLD_CHECKING_BOOSTS = {
    "Green Account": 0.75,
    "Purple Account": 0.1,
}


def active(value):
    return str(value or "").strip().upper() == "ACTIVE"


def main(payload):
    savings_class = str(payload.get("savings_class", "")).strip()
    result = {
        "actionable": False,
        "expected_apy": None,
        "base_apy": None,
        "checking_boost": None,
        "card_bonus": None,
        "relationship_bonus": None,
        "components": [],
        "warnings": [],
    }
    if savings_class != "Gold Account":
        result["warnings"].append(
            "This helper only supports the documented Gold Account calculation."
        )
        return result

    checking = payload.get("checking_accounts", [])
    cards = payload.get("credit_cards", [])
    if not isinstance(checking, list) or not isinstance(cards, list):
        result["warnings"].append("checking_accounts and credit_cards must be arrays.")
        return result

    base = 5.5
    result["base_apy"] = base
    result["components"].append({"kind": "base", "label": "Gold Account base APY", "apy": base})

    known_checkings = []
    for account in checking:
        if not isinstance(account, dict) or not active(account.get("status")):
            continue
        account_class = str(account.get("account_class", "")).strip()
        if account_class in GOLD_CHECKING_BOOSTS:
            known_checkings.append((GOLD_CHECKING_BOOSTS[account_class], account_class))
        elif account_class:
            result["warnings"].append(
                "No Gold-savings checking boost rate is documented in this helper for active "
                + account_class + ". Verify whether it is a qualifying pairing before finalizing APY."
            )

    checking_boost, checking_name = max(known_checkings, default=(0.0, None))
    result["checking_boost"] = checking_boost
    if checking_name:
        result["components"].append({"kind": "checking_boost", "label": checking_name, "apy": checking_boost})

    eligible_cards = []
    for card in cards:
        if not isinstance(card, dict) or not active(card.get("account_status")):
            continue
        card_type = str(card.get("card_type", "")).strip()
        if card_type in CARD_BONUSES:
            eligible_cards.append((CARD_BONUSES[card_type], card_type))

    card_bonus, card_name = max(eligible_cards, default=(0.0, None))
    result["card_bonus"] = card_bonus
    if card_name:
        result["components"].append({"kind": "highest_card_bonus", "label": card_name, "apy": card_bonus})

    has_gold_rewards = any(name == "Gold Rewards Card" for _, name in eligible_cards)
    relationship_bonus = 0.025 if has_gold_rewards else 0.0
    result["relationship_bonus"] = relationship_bonus
    if has_gold_rewards:
        result["components"].append({"kind": "relationship_bonus", "label": "Gold Rewards Card relationship bonus", "apy": relationship_bonus})

    result["expected_apy"] = round(base + checking_boost + card_bonus + relationship_bonus, 6)
    result["actionable"] = not result["warnings"]
    return result


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("Top-level JSON must be an object.")
        print(json.dumps(main(payload), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"actionable": False, "error": str(exc)}))
