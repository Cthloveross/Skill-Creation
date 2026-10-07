#!/usr/bin/env python3
"""Extract commonly labeled card terms from raw documents and screen the cards."""
import json
import re
import sys

from screen_cards import screen


def card_name(title):
    if not isinstance(title, str) or ":" not in title:
        return None
    name = title.split(":", 1)[0].strip()
    return name or None


def first_match(pattern, text):
    match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
    return match.group(1).strip() if match else None


def add_fact(card, key, value, source, warnings):
    if value is None:
        return
    previous = card.get(key)
    if previous is None:
        card[key] = value
    elif previous != value:
        card[key] = None
        warnings.append("conflicting %s values for %s; retained as unknown" % (key, card["name"]))
    if source not in card["source_notes"]:
        card["source_notes"].append(source)


def empty_card(name):
    return {
        "name": name,
        "foreign_transaction_fee_pct": None,
        "minimum_payment_pct": None,
        "virtual_card_management": None,
        "minimum_credit_score": None,
        "subscription_requirement": "unknown",
        "invitation_only": None,
        "minimum_annual_income": None,
        "source_notes": [],
    }


def extract(documents):
    cards, warnings = {}, []
    for index, document in enumerate(documents):
        if not isinstance(document, dict) or not isinstance(document.get("content"), str):
            warnings.append("documents[%d] is not an object with text content" % index)
            continue
        name = card_name(document.get("title"))
        if not name:
            warnings.append("documents[%d] has no card-name title prefix and was skipped" % index)
            continue
        card = cards.setdefault(name, empty_card(name))
        text = document["content"]
        source = str(document.get("document_id") or document.get("title") or "document[%d]" % index)

        fee = first_match(r"foreign\s+transaction\s+fee[^:\n]*:\s*\$?([0-9]+(?:\.[0-9]+)?)\s*%", text)
        payment = first_match(r"minimum\s+(?:monthly\s+)?payment\s*(?:is|:)[^0-9\n]*\$?([0-9]+(?:\.[0-9]+)?)\s*%", text)
        virtual = first_match(r"virtual\s+card\s+management(?:\s+features)?\s+(?:are\s+)?(?:available\s*)?:?\s*(yes|no)", text)
        score = first_match(r"minimum\s+credit\s+score(?:\s+required)?(?:\s+to\s+apply)?\s*:\s*\$?([0-9]+)", text)
        invitation = first_match(r"invitation\s+only\s*\(?\s*:\s*\)?\s*(yes|no)", text)
        income = first_match(r"minimum\s+(?:annual\s+)?income(?:\s+required)?\s*:\s*\$?([0-9][0-9,]*)", text)
        subscription = re.search(r"([A-Za-z][A-Za-z0-9+\-\u2011 ]*?)\s+(?:premium\s+)?subscription\s+required\s*:\s*(yes|no)", text, re.IGNORECASE)

        for key, raw, converter in (
            ("foreign_transaction_fee_pct", fee, float),
            ("minimum_payment_pct", payment, float),
            ("minimum_credit_score", score, int),
            ("minimum_annual_income", income, lambda x: int(x.replace(",", ""))),
        ):
            if raw is not None:
                add_fact(card, key, converter(raw), source, warnings)
        if virtual is not None:
            add_fact(card, "virtual_card_management", virtual.casefold() == "yes", source, warnings)
        if invitation is not None:
            add_fact(card, "invitation_only", invitation.casefold() == "yes", source, warnings)
        if subscription:
            requirement = subscription.group(1).strip() if subscription.group(2).casefold() == "yes" else "none"
            add_fact(card, "subscription_requirement", requirement, source, warnings)
    return list(cards.values()), warnings


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception as exc:
        print(json.dumps({"ok": False, "errors": ["stdin must contain one JSON object: %s" % exc]}))
        return
    if not isinstance(payload, dict) or not isinstance(payload.get("documents"), list):
        print(json.dumps({"ok": False, "errors": ["documents must be a list"]}))
        return
    if not isinstance(payload.get("customer"), dict) or not isinstance(payload.get("criteria"), dict):
        print(json.dumps({"ok": False, "errors": ["customer and criteria must be objects"]}))
        return
    cards, warnings = extract(payload["documents"])
    result = screen({"customer": payload["customer"], "criteria": payload["criteria"], "cards": cards})
    result["cards"] = cards
    result["extraction_warnings"] = warnings
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
