#!/usr/bin/env python3
"""Resolve documented APY components for a verified Bronze or Gold Plus account.

Reads a JSON object from stdin and writes a JSON result to stdout. This program does
not verify account ownership, account linkage, card status, or same-profile status;
the caller must pass only items already verified by banking tools.
"""
import json
import sys
from decimal import Decimal
from pathlib import Path


def norm(value):
    return " ".join(str(value).strip().casefold().split())


def decimal_text(value):
    return format(Decimal(str(value)), "f")


def fail(message):
    print(json.dumps({"ok": False, "error": message}, sort_keys=True))
    return 2


def canonical_from(value, names):
    wanted = norm(value)
    for name in names:
        if norm(name) == wanted:
            return name
    return None


def main():
    try:
        request = json.load(sys.stdin)
        if not isinstance(request, dict):
            raise ValueError("input must be a JSON object")
        product_input = request.get("savings_product")
        if not isinstance(product_input, str) or not product_input.strip():
            raise ValueError("savings_product must be a nonempty string")
        cards = request.get("active_cards", [])
        checkings = request.get("linked_checking_products", [])
        if not isinstance(cards, list) or not all(isinstance(x, str) for x in cards):
            raise ValueError("active_cards must be an array of strings")
        if not isinstance(checkings, list) or not all(isinstance(x, str) for x in checkings):
            raise ValueError("linked_checking_products must be an array of strings")

        rules_path = Path(__file__).resolve().parents[1] / "references" / "interest_apy_rules.json"
        rules = json.loads(rules_path.read_text(encoding="utf-8"))
        products = rules["products"]
        product_name = None
        product = None
        for name, candidate in products.items():
            aliases = [name] + candidate.get("aliases", [])
            if norm(product_input) in {norm(a) for a in aliases}:
                product_name, product = name, candidate
                break
        if product is None:
            raise ValueError("unsupported savings_product; only personal Bronze and Gold Plus are supported")

        card_table = product["card_bonuses_percent"]
        known_card_names = list(card_table)
        card_items, card_candidates = [], []
        seen = set()
        for supplied in cards:
            key = norm(supplied)
            if key in seen:
                continue
            seen.add(key)
            canonical = canonical_from(supplied, known_card_names)
            if canonical is None:
                card_items.append({"card": supplied, "status": "not_listed_in_documented_table", "bonus_percent": "0"})
            else:
                bonus = Decimal(card_table[canonical])
                entry = {"card": canonical, "status": "eligible", "bonus_percent": decimal_text(bonus)}
                card_items.append(entry)
                card_candidates.append((bonus, canonical))
        selected_card_bonus, selected_card = Decimal("0"), None
        if card_candidates:
            selected_card_bonus, selected_card = max(card_candidates, key=lambda item: item[0])

        checking_table = product["checking_bonuses_percent"]
        qualifying = product["qualifying_checking_products"]
        checking_items, checking_candidates, unresolved = [], [], []
        seen = set()
        for supplied in checkings:
            key = norm(supplied)
            if key in seen:
                continue
            seen.add(key)
            known_rate = canonical_from(supplied, list(checking_table))
            qualifying_name = canonical_from(supplied, qualifying)
            if known_rate is not None:
                bonus = Decimal(checking_table[known_rate])
                checking_items.append({"checking": known_rate, "status": "eligible_with_documented_rate", "boost_percent": decimal_text(bonus)})
                checking_candidates.append((bonus, known_rate))
            elif qualifying_name is not None:
                checking_items.append({"checking": qualifying_name, "status": "qualifying_rate_not_in_packaged_evidence", "boost_percent": None})
                unresolved.append(qualifying_name)
            else:
                checking_items.append({"checking": supplied, "status": "not_a_documented_qualifying_pairing", "boost_percent": "0"})
        selected_checking_bonus, selected_checking = Decimal("0"), None
        if checking_candidates:
            selected_checking_bonus, selected_checking = max(checking_candidates, key=lambda item: item[0])

        base = Decimal(product["base_apy_percent"])
        expected = base + selected_card_bonus + selected_checking_bonus
        result = {
            "ok": True,
            "savings_product": product_name,
            "base_apy_percent": decimal_text(base),
            "card_candidates": card_items,
            "selected_card": selected_card,
            "selected_card_bonus_percent": decimal_text(selected_card_bonus),
            "checking_candidates": checking_items,
            "selected_checking": selected_checking,
            "selected_checking_boost_percent": decimal_text(selected_checking_bonus),
            "unresolved_qualifying_checking_products": unresolved,
            "ready_for_rate_determination": not unresolved,
            "expected_apy_percent": decimal_text(expected) if not unresolved else None,
            "selection_policy": "Highest eligible card bonus and highest eligible checking boost only; the two selected components add to base APY."
        }
        print(json.dumps(result, sort_keys=True))
        return 0
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        return fail(str(exc))


if __name__ == "__main__":
    sys.exit(main())
